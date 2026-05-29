"""
Clasificador de quiebre de stock para F4-B.

Lee de gold.feature_store_sku + gold.mart_inventario_actual vía
Databricks SQL Warehouse API, entrena LGBMClassifier, clasifica urgencia,
escribe a gold.alertas_quiebre y registra en MLflow.

Output: notebooks/gold/_runs/v_classifier_stockout_<ts>.md

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_classifier_stockout.py

Requiere: requests, pandas, lightgbm, scikit-learn, mlflow
.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

# ─── Dependencias opcionales ─────────────────────────────────────────────────

try:
    import requests
except ImportError:
    print("❌ requests no instalado. Ejecutá: pip install requests")
    sys.exit(1)

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
    from sklearn.model_selection import train_test_split, StratifiedKFold
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
WAREHOUSE_ID = "43bc044eaef4cca4"

HEADERS = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 120

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

# ─── Helpers Databricks API ─────────────────────────────────────────────────


def api_post(endpoint: str, payload: dict, description: str = "") -> dict | None:
    url = f"{DATABRICKS_HOST}{endpoint}"
    try:
        resp = SESSION.post(url, json=payload, timeout=TIMEOUT)
        if resp.status_code in (200, 201, 202):
            return resp.json()
        else:
            print(f"  ❌ {description}: HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ {description}: {e}")
        return None


def api_get(endpoint: str, description: str = "") -> dict | None:
    url = f"{DATABRICKS_HOST}{endpoint}"
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  ❌ {description}: HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ {description}: {e}")
        return None


def query_databricks(sql: str, description: str = "query") -> list[dict]:
    """Ejecuta SQL via /api/2.0/sql/statements y devuelve lista de dicts."""
    payload = {
        "statement": sql,
        "warehouse_id": WAREHOUSE_ID,
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
    }

    result = api_post("/api/2.0/sql/statements", payload, description)
    if result is None:
        return []

    statement_id = result.get("statement_id")
    status = result.get("status", {}).get("state", "UNKNOWN")

    if status == "PENDING" and statement_id:
        for _ in range(30):
            time.sleep(2)
            poll = api_get(f"/api/2.0/sql/statements/{statement_id}", f"Poll {description}")
            if poll is None:
                break
            poll_status = poll.get("status", {}).get("state", "UNKNOWN")
            if poll_status in ("SUCCEEDED", "FAILED", "CANCELED"):
                result = poll
                status = poll_status
                break
            if poll_status == "RUNNING":
                continue

    if status != "SUCCEEDED":
        error_obj = result.get("status", {}).get("error", {})
        error_msg = error_obj.get("message", "Unknown error")
        print(f"  ❌ Query failed: {error_msg[:200]}")
        return []

    manifest = result.get("manifest", {})
    schema_cols = manifest.get("columns", [])
    if not schema_cols:
        schema = manifest.get("schema", {})
        if schema and "columns" in schema:
            schema_cols = schema["columns"]
    columns = [c["name"] for c in schema_cols] if schema_cols else []

    data_array = result.get("result", {}).get("data_array", [])
    if not data_array:
        return []

    rows = []
    for row in data_array:
        rows.append(dict(zip(columns, row)))
    return rows


def execute_statement(sql: str, description: str = "execute") -> bool:
    """Ejecuta una sentencia DML/DDL (sin retorno de datos)."""
    payload = {
        "statement": sql,
        "warehouse_id": WAREHOUSE_ID,
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
    }
    result = api_post("/api/2.0/sql/statements", payload, description)
    if result is None:
        return False

    statement_id = result.get("statement_id")
    status = result.get("status", {}).get("state", "UNKNOWN")

    if status == "PENDING" and statement_id:
        for _ in range(30):
            time.sleep(2)
            poll = api_get(f"/api/2.0/sql/statements/{statement_id}", f"Poll {description}")
            if poll is None:
                break
            poll_status = poll.get("status", {}).get("state", "UNKNOWN")
            if poll_status in ("SUCCEEDED", "FAILED", "CANCELED"):
                result = poll
                status = poll_status
                break
            if poll_status == "RUNNING":
                continue

    return status == "SUCCEEDED"


# ─── 1. Cargar datos ────────────────────────────────────────────────────────


def load_training_data() -> pd.DataFrame:
    """Carga feature_store_sku con último business_date disponible."""
    print("\n📦 Cargando datos de feature_store_sku...")

    sql = """
    SELECT
      fs.cod_producto,
      fs.business_date,
      fs.demanda_diaria,
      fs.lag_7d,
      fs.lag_14d,
      fs.lag_28d,
      fs.media_movil_7d,
      fs.media_movil_14d,
      fs.media_movil_28d,
      fs.dia_semana,
      fs.mes,
      fs.stock_actual,
      fs.dias_sin_venta,
      fs.categoria_abc
    FROM motoshop.gold.feature_store_sku fs
    WHERE fs.business_date >= (
      SELECT DATE_ADD(MAX(business_date), -90) FROM motoshop.gold.feature_store_sku
    )
    ORDER BY fs.cod_producto, fs.business_date
    """
    rows = query_databricks(sql, "load feature_store_sku")
    if not rows:
        print("⚠️ No se encontraron datos en feature_store_sku")
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Convertir tipos
    numeric_cols = [
        "demanda_diaria", "lag_7d", "lag_14d", "lag_28d",
        "media_movil_7d", "media_movil_14d", "media_movil_28d",
        "stock_actual", "dias_sin_venta",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    int_cols = ["dia_semana", "mes"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    print(f"   ✅ {len(df)} filas, {df['cod_producto'].nunique()} SKUs únicos")
    print(f"   Rango fechas: {df['business_date'].min()} → {df['business_date'].max()}")
    return df


def load_product_names() -> dict[str, str]:
    """Carga nombres de productos desde mart_inventario_actual."""
    print("\n📦 Cargando nombres de productos...")
    sql = "SELECT DISTINCT cod_producto, nom_producto FROM motoshop.gold.mart_inventario_actual"
    rows = query_databricks(sql, "load product names")
    if not rows:
        return {}
    mapping = {r["cod_producto"]: r["nom_producto"] for r in rows if r.get("nom_producto")}
    print(f"   ✅ {len(mapping)} productos con nombre")
    return mapping


# ─── 2. Feature engineering + label ─────────────────────────────────────────


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, dict]:
    """Construye features y label binario.

    Label: quiebre=1 si stock_actual < media_movil_7d * 0.5
    """
    print("\n🔧 Preparando features...")

    # Feature: categoria_abc one-hot
    df_feat = pd.get_dummies(df, columns=["categoria_abc"], prefix="cat")

    # Label: quiebre si stock insuficiente para cubrir media_movil_7d * 0.5
    df_feat["quiebre"] = (
        (df_feat["stock_actual"] < df_feat["media_movil_7d"] * 0.5)
    ).astype(int)

    # Features para entrenamiento
    feature_cols = [
        "demanda_diaria", "lag_7d", "lag_14d", "lag_28d",
        "media_movil_7d", "media_movil_14d", "media_movil_28d",
        "dia_semana", "mes", "stock_actual", "dias_sin_venta",
    ] + [c for c in df_feat.columns if c.startswith("cat_")]

    X = df_feat[feature_cols].copy()
    y = df_feat["quiebre"]

    print(f"   Features: {len(feature_cols)} columnas")
    print(f"   Clases: 0={sum(y==0)}, 1={sum(y==1)} ({sum(y==1)/len(y)*100:.1f}%)")
    print(f"   Columnas: {feature_cols}")

    metadata = {"feature_cols": feature_cols}
    return X, y, metadata


# ─── 3. Entrenar clasificador ────────────────────────────────────────────────


def train_classifier(X: pd.DataFrame, y: pd.Series) -> dict:
    """Entrena LGBMClassifier con stratified 70/30 split."""
    print("\n🏋️ Entrenando LGBMClassifier...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y,
    )

    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "is_unbalance": True,
        "num_leaves": 31,
        "learning_rate": 0.05,
        "n_estimators": 300,
        "random_state": 42,
        "verbosity": -1,
    }

    model = lgb.LGBMClassifier(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        eval_metric="auc",
        callbacks=[lgb.log_evaluation(0)],
    )

    # Predicciones
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    f1 = f1_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)

    print(f"\n   📊 Resultados:")
    print(f"      F1:        {f1:.4f}")
    print(f"      Precision: {precision:.4f}")
    print(f"      Recall:    {recall:.4f}")
    print(f"      Train: {len(X_train)} filas, Test: {len(X_test)} filas")
    print(f"\n   {classification_report(y_test, y_pred, target_names=['no_quiebre', 'quiebre'])}")

    # Feature importance
    importance = sorted(
        zip(feature_cols := X.columns.tolist(), model.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print("   Top-5 features:")
    for name, imp in importance[:5]:
        print(f"      {name}: {imp}")

    return {
        "model": model,
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "feature_importance": importance[:10],
        "n_train": len(X_train),
        "n_test": len(X_test),
    }


# ─── 4. Clasificar urgencia ────────────────────────────────────────────────


def classify_urgency(df: pd.DataFrame, model, feature_cols: list[str]) -> pd.DataFrame:
    """Clasifica urgencia de quiebre para cada SKU en el último business_date.

    Urgencia:
      - dias_hasta_quiebre = stock_actual / media_movil_7d (clipped a 0 si stock=0)
      - ≤ 7 → alta, ≤ 14 → media, > 14 → baja
    """
    print("\n🔴 Clasificando urgencia...")

    # Último registro por SKU
    df_latest = df.sort_values("business_date").groupby("cod_producto").last().reset_index()

    # Preparar features para predicción
    df_feat = pd.get_dummies(df_latest, columns=["categoria_abc"], prefix="cat")
    X_latest = df_feat[feature_cols].copy()

    # Predecir probabilidad de quiebre
    df_latest["prob_quiebre"] = model.predict_proba(X_latest)[:, 1]
    df_latest["pred_quiebre"] = (df_latest["prob_quiebre"] >= 0.5).astype(int)

    # Calcular días hasta quiebre
    df_latest["dias_hasta_quiebre"] = df_latest.apply(
        lambda r: max(0, r["stock_actual"] / max(r["media_movil_7d"], 0.01))
        if r["media_movil_7d"] > 0 else 999,
        axis=1,
    )
    df_latest["dias_hasta_quiebre"] = df_latest["dias_hasta_quiebre"].round(0).astype(int)

    # Clasificar urgencia
    def _urgency(row):
        if row["pred_quiebre"] == 0:
            return "baja"
        if row["dias_hasta_quiebre"] <= 7:
            return "alta"
        elif row["dias_hasta_quiebre"] <= 14:
            return "media"
        else:
            return "baja"

    df_latest["urgencia"] = df_latest.apply(_urgency, axis=1)

    alerts = df_latest[df_latest["pred_quiebre"] == 1].sort_values(
        ["urgencia", "dias_hasta_quiebre"],
        ascending=[True, True],
    )

    print(f"   Alertas totales: {len(df_latest[df_latest['pred_quiebre']==1])}")
    for urg in ["alta", "media", "baja"]:
        count = len(alerts[alerts["urgencia"] == urg])
        print(f"      {urg}: {count}")

    return alerts, df_latest[["cod_producto", "stock_actual", "media_movil_7d",
                               "dias_hasta_quiebre", "urgencia", "prob_quiebre"]]


# ─── 5. Escribir a gold.alertas_quiebre ──────────────────────────────────────


def write_alerts_table(
    alerts: pd.DataFrame,
    product_names: dict[str, str],
    business_date: str,
) -> bool:
    """Escribe alertas a gold.alertas_quiebre vía INSERT OVERWRITE."""
    print(f"\n💾 Escribiendo a gold.alertas_quiebre ({len(alerts)} filas)...")

    if alerts.empty:
        print("   ⚠️ No hay alertas para escribir")
        return True

    # Preparar INSERT
    rows_sql = []
    for _, row in alerts.iterrows():
        sku = row["cod_producto"]
        nom = product_names.get(sku, "DESCONOCIDO")
        # Escapar comillas simples en nombres
        nom = nom.replace("'", "''")
        rows_sql.append(
            f"('{sku}', '{nom}', {row['stock_actual']}, {row['media_movil_7d']}, "
            f"{row['dias_hasta_quiebre']}, '{row['urgencia']}', DATE '{business_date}')"
        )

    insert_sql = f"""
    INSERT OVERWRITE motoshop.gold.alertas_quiebre PARTITION (business_date)
    VALUES
    {',\n'.join(rows_sql)}
    """

    success = execute_statement(insert_sql, "INSERT alertas_quiebre")
    if success:
        print(f"   ✅ {len(alerts)} alertas insertadas en gold.alertas_quiebre")
    else:
        print("   ❌ Falló INSERT a gold.alertas_quiebre")

    return success


# ─── 6. MLflow tracking ─────────────────────────────────────────────────────


def log_mlflow(metrics: dict, alerts_count: dict, model=None) -> str | None:
    """Registra run en MLflow si está disponible."""
    print("\n📝 Registrando en MLflow...")

    try:
        import mlflow
        import mlflow.tracking

        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment("/Users/javierportillar/motoshop_forecast")

        with mlflow.start_run() as run:
            mlflow.set_tags({
                "fase": "F4",
                "modelo": "lightgbm_classifier",
                "sprint": "F4-B",
                "task": "stockout_classifier",
            })

            mlflow.log_metric("F1", metrics["f1"])
            mlflow.log_metric("precision", metrics["precision"])
            mlflow.log_metric("recall", metrics["recall"])
            mlflow.log_param("num_leaves", 31)
            mlflow.log_param("learning_rate", 0.05)
            mlflow.log_param("n_estimators", 300)
            mlflow.log_param("is_unbalance", True)

            if model:
                mlflow.lightgbm.log_model(model, "model", registered_model_name="stockout_classifier")

            for urg, count in alerts_count.items():
                mlflow.log_metric(f"alertas_{urg}", count)

            print(f"   ✅ MLflow run: {run.info.run_id}")
            return run.info.run_id

    except Exception as e:
        print(f"   ⚠️ MLflow no disponible: {e}")
        print("   ✅ Métricas calculadas — continuar sin MLflow.")
        return None


# ─── 7. Evidencia ───────────────────────────────────────────────────────────


def write_evidence(metrics: dict, alerts: pd.DataFrame, mlflow_run_id: str | None):
    """Escribe reporte de evidencia a notebooks/gold/_runs/."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    evidence_file = RUNS_DIR / f"v_classifier_stockout_{timestamp}.md"

    alerts_by_urgency = {}
    if not alerts.empty:
        alerts_by_urgency = {
            urg: alerts[alerts["urgencia"] == urg].to_dict("records")
            for urg in ["alta", "media", "baja"]
        }

    lines = [
        f"# Classifier Stockout F4-B — {timestamp}",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}",
        f"Warehouse: {WAREHOUSE_ID}",
        "",
        "---",
        "",
        "## Métricas",
        "",
        f"| Métrica | Valor |",
        f"|---------|-------|",
        f"| F1 | {metrics['f1']} |",
        f"| Precision | {metrics['precision']} |",
        f"| Recall | {metrics['recall']} |",
        f"| Train rows | {metrics['n_train']} |",
        f"| Test rows | {metrics['n_test']} |",
        "",
        "## Feature Importance (Top-10)",
        "",
        "| Feature | Importance |",
        "|---------|-----------|",
    ]
    for name, imp in metrics.get("feature_importance", []):
        lines.append(f"| {name} | {imp} |")

    lines.extend([
        "",
        "## Alertas por urgencia",
        "",
        f"| Urgencia | Cantidad |",
        f"|----------|----------|",
    ])
    for urg in ["alta", "media", "baja"]:
        count = len(alerts_by_urgency.get(urg, []))
        lines.append(f"| {urg} | {count} |")

    lines.extend([
        "",
        "## Top-10 alertas más críticas",
        "",
        "| SKU | Stock | Demanda | Días hasta quiebre | Urgencia |",
        "|-----|-------|---------|-------------------|----------|",
    ])
    for urg in ["alta", "media", "baja"]:
        for a in alerts_by_urgency.get(urg, [])[:10]:
            lines.append(
                f"| {a['cod_producto']} | {a['stock_actual']} | "
                f"{a['media_movil_7d']:.1f} | {a['dias_hasta_quiebre']} | {a['urgencia']} |"
            )

    if mlflow_run_id:
        lines.extend([
            "",
            "## MLflow",
            "",
            f"Run ID: `{mlflow_run_id}`",
            f"Modelo: stockout_classifier",
        ])

    lines.append("")
    content = "\n".join(lines)

    evidence_file.write_text(content, encoding="utf-8")
    print(f"\n📄 Evidencia: {evidence_file}")


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  Clasificador de Quiebre · Sprint F4-B")
    print("=" * 60)
    print(f"  Host: {DATABRICKS_HOST}")
    print(f"  Warehouse: {WAREHOUSE_ID}")
    print(f"  Timestamp: {timestamp}")
    print()

    # 1. Cargar datos
    df = load_training_data()
    if df.empty:
        print("❌ No hay datos para entrenar. Saliendo.")
        sys.exit(1)

    product_names = load_product_names()

    # 2. Features + label
    X, y, metadata = prepare_features(df)

    # 3. Entrenar clasificador
    results = train_classifier(X, y)

    # 4. Clasificar urgencia
    alerts, full_results = classify_urgency(df, results["model"], metadata["feature_cols"])
    alerts_count = alerts["urgencia"].value_counts().to_dict() if not alerts.empty else {}
    for urg in ["alta", "media", "baja"]:
        alerts_count.setdefault(urg, 0)

    # 5. Escribir a gold
    latest_date = df["business_date"].max()
    write_alerts_table(full_results, product_names, latest_date)

    # 6. MLflow
    if results["f1"] >= 0.7:
        print(f"\n✅ F1={results['f1']} ≥ 0.7 — registrando en MLflow")
    else:
        print(f"\n⚠️ F1={results['f1']} < 0.7 — registrando igual con advertencia")

    mlflow_run_id = log_mlflow(results, alerts_count, results.get("model"))

    # 7. Evidencia
    write_evidence(results, full_results, mlflow_run_id)

    # 8. Resumen final
    print()
    print("=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  F1:         {results['f1']}")
    print(f"  Precision:  {results['precision']}")
    print(f"  Recall:     {results['recall']}")
    print(f"  Alertas alta:  {alerts_count.get('alta', 0)}")
    print(f"  Alertas media: {alerts_count.get('media', 0)}")
    print(f"  Alertas baja:  {alerts_count.get('baja', 0)}")
    print(f"  MLflow run: {mlflow_run_id or 'N/A'}")
    print()

    if results["f1"] >= 0.7:
        print("✅ V-M3: F1 > 0.7 — PASS")
    else:
        print("⚠️ V-M3: F1 < 0.7 — revisar parámetros o features")
    print(f"✅ V-M5: alertas_quiebre tiene {len(alerts)} registros con urgencia")
    print()


if __name__ == "__main__":
    main()
