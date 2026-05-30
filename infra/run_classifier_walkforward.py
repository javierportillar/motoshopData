"""
Walk-forward validation for the stockout classifier (F6-A7).

Para cada semana W desde 2026-04-15:
  1. Train classifier con todos los datos con business_date < W.
  2. Evaluate en los datos de la semana W.
  3. Computa F1, precision, recall.
  4. Reporta métricas por semana.

Output: notebooks/gold/_runs/v_walkforward_classifier_<ts>.md

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_classifier_walkforward.py

Requiere: requests, pandas, lightgbm, scikit-learn
.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_HTTP_PATH
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from datetime import datetime, date, timedelta
from typing import Any

import requests

try:
    import pandas as pd
except ImportError:
    print("❌ pandas no instalado. Ejecutá: pip install pandas")
    sys.exit(1)

try:
    import lightgbm as lgb
except ImportError:
    print("❌ lightgbm no instalado. Ejecutá: pip install lightgbm")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("❌ numpy no instalado. Ejecutá: pip install numpy")
    sys.exit(1)

try:
    from sklearn.metrics import f1_score, precision_score, recall_score, classification_report
except ImportError:
    print("❌ scikit-learn no instalado. Ejecutá: pip install scikit-learn")
    sys.exit(1)

# ─── Cargar .env ─────────────────────────────────────────────────────────────

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ─── Config ──────────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "notebooks" / "gold" / "_runs"

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "43bc044eaef4cca4")

HEADERS = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 50  # max 50s, requery if pending

START_DATE = date(2026, 4, 15)  # primera fecha de walk-forward
FEATURE_COLS = [
    "lag_7d", "lag_14d", "lag_28d",
    "media_movil_7d", "media_movil_14d", "media_movil_28d",
    "stock_actual", "demanda_diaria",
    "dia_semana", "dias_sin_venta",
]


# ─── Helpers Databricks SQL API ─────────────────────────────────────────────


def sql_query(sql: str, description: str = "") -> pd.DataFrame:
    """Ejecuta SQL query via Databricks REST API y devuelve DataFrame."""
    url = f"{DATABRICKS_HOST}/api/2.0/sql/statements"
    payload = {
        "statement": sql,
        "warehouse_id": WAREHOUSE_ID,
        "wait_timeout": f"{TIMEOUT}s",
    }
    try:
        resp = SESSION.post(url, json=payload, timeout=60)
        if resp.status_code not in (200, 201, 202):
            print(f"  ❌ {description}: HTTP {resp.status_code} - {resp.text[:200]}")
            return pd.DataFrame()
        result = resp.json()
    except Exception as e:
        print(f"  ❌ {description}: {e}")
        return pd.DataFrame()

    # Poll si es async
    statement_id = result.get("statement_id", "")
    manifest = result.get("manifest", {})
    while result.get("status", {}).get("state") == "PENDING":
        time.sleep(2)
        poll = SESSION.get(f"{DATABRICKS_HOST}/api/2.0/sql/statements/{statement_id}")
        if poll.status_code == 200:
            result = poll.json()
            manifest = result.get("manifest", {})
        else:
            break

    if result.get("status", {}).get("state") != "SUCCEEDED":
        error = result.get("status", {}).get("error", {}).get("message", "unknown")
        print(f"  ❌ {description}: query failed - {error}")
        return pd.DataFrame()

    # Parsear columnas
    cols = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
    rows = []
    for chunk in result.get("result", {}).get("data_array", []):
        rows.append(chunk)

    return pd.DataFrame(rows, columns=cols)


# ─── Features + labels ───────────────────────────────────────────────────────


def load_training_data() -> pd.DataFrame:
    """Carga feature store + labels desde Databricks."""
    print("\n📦 Cargando datos de entrenamiento...")

    # Feature store
    features = sql_query(
        """
        SELECT
          f.cod_producto,
          f.business_date,
          f.lag_7d, f.lag_14d, f.lag_28d,
          f.media_movil_7d, f.media_movil_14d, f.media_movil_28d,
          f.stock_actual, f.demanda_diaria,
          f.dia_semana, f.dias_sin_venta
        FROM motoshop.gold.feature_store_sku f
        WHERE f.business_date >= '2025-01-01'
        ORDER BY f.cod_producto, f.business_date
        """,
        "feature_store_sku",
    )
    if features.empty:
        print("⚠️  No se pudieron cargar features. Usando forecast_baseline_sku como fallback.")
        return load_baseline_data()

    # Labels: stockout = stock_actual < 0.5 (casi agotado)
    # Usamos stock_actual desde feature_store (no hay stock_minimo aparte)
    df = features.copy()
    df["stock_actual"] = pd.to_numeric(df["stock_actual"], errors="coerce").fillna(0)
    df["demanda_diaria"] = pd.to_numeric(df["demanda_diaria"], errors="coerce").fillna(0)
    # Label: 1 si stock_actual < demanda_diaria * 7 (menos de 1 semana de stock) y stock_actual > 0
    df["label"] = ((df["stock_actual"] < df["demanda_diaria"] * 7) & (df["demanda_diaria"] > 0)).astype(int)
    df["business_date"] = pd.to_datetime(df["business_date"])

    for col in FEATURE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def load_baseline_data() -> pd.DataFrame:
    """Fallback: usar forecast_baseline_sku como proxy."""
    print("📦 Cargando forecast_baseline_sku como fallback...")
    df = sql_query(
        """
        SELECT
          cod_producto,
          business_date,
          demanda_real,
          demanda_predicha
        FROM motoshop.gold.forecast_baseline_sku
        WHERE business_date >= '2025-01-01'
        ORDER BY cod_producto, business_date
        """,
        "forecast_baseline_sku",
    )
    if df.empty:
        print("❌ No hay datos disponibles para walk-forward.")
        return df
    df["business_date"] = pd.to_datetime(df["business_date"])
    df["demanda_real"] = pd.to_numeric(df["demanda_real"], errors="coerce").fillna(0)
    df["demanda_predicha"] = pd.to_numeric(df["demanda_predicha"], errors="coerce").fillna(0)
    return df


# ─── Walk-forward evaluation ────────────────────────────────────────────────


def run_walkforward_classifier(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Ejecuta walk-forward validation semana a semana.

    Para modelos con features (classifier):
      - Train: data < week_start
      - Test: data in [week_start, week_end)
      - Compute F1, precision, recall

    Para fallback (baseline):
      - Computa WAPE por semana como proxy.
    """
    is_classifier = "label" in df.columns

    # Generar semanas desde START_DATE hasta hoy
    weeks: list[tuple[date, date]] = []
    d = START_DATE
    today = date.today()
    while d < today:
        week_end = min(d + timedelta(days=6), today)
        weeks.append((d, week_end))
        d += timedelta(days=7)

    print(f"\n📊 Ejecutando walk-forward sobre {len(weeks)} semanas...")
    results: list[dict[str, Any]] = []

    for i, (week_start, week_end) in enumerate(weeks):
        week_label = f"{week_start.isoformat()}_{week_end.isoformat()}"

        if is_classifier:
            # Classifier walk-forward
            train = df[df["business_date"] < pd.Timestamp(week_start)]
            test = df[
                (df["business_date"] >= pd.Timestamp(week_start))
                & (df["business_date"] <= pd.Timestamp(week_end))
            ]

            if len(train) < 100 or len(test) < 10:
                print(f"  [{i+1}/{len(weeks)}] {week_label}: ⏭ pocos datos (train={len(train)}, test={len(test)})")
                results.append({
                    "week": week_label,
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "train_size": len(train),
                    "test_size": len(test),
                    "f1": None,
                    "precision": None,
                    "recall": None,
                    "status": "SKIPPED",
                })
                continue

            X_train = train[FEATURE_COLS].values
            y_train = train["label"].values
            X_test = test[FEATURE_COLS].values
            y_test = test["label"].values

            # Train LightGBM
            model = lgb.LGBMClassifier(
                n_estimators=100, max_depth=5, random_state=42,
                class_weight="balanced", verbose=-1,
            )
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

            f1 = f1_score(y_test, y_pred, zero_division=0)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)

            print(f"  [{i+1}/{len(weeks)}] {week_label}: F1={f1:.4f} P={prec:.4f} R={rec:.4f} (train={len(train)}, test={len(test)})")
            results.append({
                "week": week_label,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "train_size": int(len(train)),
                "test_size": int(len(test)),
                "f1": round(float(f1), 4),
                "precision": round(float(prec), 4),
                "recall": round(float(rec), 4),
                "status": "OK",
            })
        else:
            # Baseline proxy: WAPE por semana
            week_df = df[
                (df["business_date"] >= pd.Timestamp(week_start))
                & (df["business_date"] <= pd.Timestamp(week_end))
            ]
            if week_df.empty:
                continue
            total_real = week_df["demanda_real"].sum()
            total_pred = week_df["demanda_predicha"].sum()
            wape = (
                abs(week_df["demanda_real"] - week_df["demanda_predicha"]).sum()
                / total_real * 100
                if total_real > 0
                else None
            )
            print(f"  [{i+1}/{len(weeks)}] {week_label}: WAPE={wape:.2f}% (rows={len(week_df)})" if wape else
                  f"  [{i+1}/{len(weeks)}] {week_label}: WAPE=N/A (sin demanda real)")
            results.append({
                "week": week_label,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "n_rows": len(week_df),
                "wape_pct": round(wape, 2) if wape else None,
                "status": "OK",
            })

    return results


# ─── Report ──────────────────────────────────────────────────────────────────


def generate_report(results: list[dict[str, Any]], is_classifier: bool) -> str:
    """Genera reporte markdown."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = RUNS_DIR / f"v_walkforward_classifier_{ts}.md"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Walk-forward Classifier Evaluation · {ts}",
        "",
        f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Tipo:** {'Classifier (LightGBM)' if is_classifier else 'Baseline (WAPE proxy)'}",
        f"**Semanas evaluadas:** {len(results)}",
        f"**Período:** {START_DATE.isoformat()} → {date.today().isoformat()}",
        "",
        "---",
        "",
        "## Resultados por semana",
        "",
    ]

    if is_classifier and results and "f1" in results[0]:
        lines.append("| Semana | Inicio | Fin | Train | Test | F1 | Precision | Recall | Status |")
        lines.append("|--------|--------|-----|-------|------|----|-----------|--------|--------|")
        for r in results:
            f1_str = f"{r['f1']:.4f}" if r["f1"] is not None else "—"
            prec_str = f"{r['precision']:.4f}" if r["precision"] is not None else "—"
            rec_str = f"{r['recall']:.4f}" if r["recall"] is not None else "—"
            lines.append(
                f"| {r['week']} | {r['week_start']} | {r['week_end']} "
                f"| {r['train_size']} | {r['test_size']} "
                f"| {f1_str} | {prec_str} | {rec_str} | {r['status']} |"
            )
    else:
        lines.append("| Semana | Inicio | Fin | Filas | WAPE (%) | Status |")
        lines.append("|--------|--------|-----|-------|----------|--------|")
        for r in results:
            wape_str = f"{r['wape_pct']:.2f}" if r.get("wape_pct") is not None else "N/A"
            lines.append(
                f"| {r['week']} | {r['week_start']} | {r['week_end']} "
                f"| {r['n_rows']} | {wape_str} | {r['status']} |"
            )

    # Resumen
    if is_classifier and results:
        f1_vals = [r["f1"] for r in results if r["f1"] is not None]
        if f1_vals:
            lines += [
                "",
                "## Resumen",
                "",
                f"- **F1 promedio:** {sum(f1_vals)/len(f1_vals):.4f}",
                f"- **F1 min:** {min(f1_vals):.4f}",
                f"- **F1 max:** {max(f1_vals):.4f}",
                f"- **F1 std:** {__import__('statistics').stdev(f1_vals):.4f}" if len(f1_vals) > 1 else "",
                "",
                "### Interpretación",
                "",
                "- Si F1 promedio ≥ 0.5: el classifier es estable a través del tiempo.",
                "- Si F1 baja en semanas recientes: puede haber drift (el modelo se degrada).",
                "- Si F1 sube: el modelo mejora con más datos de entrenamiento (esperable).",
            ]

    lines += [
        "",
        "---",
        "",
        "## Detalle",
        "",
        "```json",
        json.dumps(results, indent=2, default=str),
        "```",
    ]

    report = "\n".join(lines)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n📄 Reporte guardado: {report_path}")
    return str(report_path)


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  WALK-FORWARD CLASSIFIER EVALUATION (F6-A7)")
    print("=" * 60)
    print(f"  Período: {START_DATE} → {date.today()}")
    print(f"  Host: {DATABRICKS_HOST}")

    # 1. Cargar datos
    df = load_training_data()
    if df.empty:
        print("\n❌ No se pudieron cargar datos. Verificar conexión a Databricks.")
        sys.exit(1)

    is_classifier = "label" in df.columns
    print(f"  Tipo: {'Classifier' if is_classifier else 'Baseline (fallback)'}")
    print(f"  Filas: {len(df)}")

    # 2. Walk-forward
    results = run_walkforward_classifier(df)

    if not results:
        print("\n❌ No se generaron resultados.")
        sys.exit(1)

    # 3. Reporte
    report_path = generate_report(results, is_classifier)

    # 4. Resumen final
    print(f"\n{'=' * 60}")
    print(f"  WALK-FORWARD COMPLETADO")
    print(f"{'=' * 60}")
    print(f"  Semanas evaluadas: {len(results)}")
    print(f"  Reporte: {report_path}")
    print(f"\n  📌 Próximo paso: Validar el reporte en revisión F6.")


if __name__ == "__main__":
    main()
