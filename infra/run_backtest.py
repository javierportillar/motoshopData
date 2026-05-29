"""
Walk-forward backtest for F4-A baseline.

Lee de gold.feature_store_sku y gold.forecast_baseline_sku vía
Databricks SQL Warehouse API, calcula walk-forward validation con
MAPE/sMAPE/WAPE por SKU y global.

Output: notebooks/gold/_runs/v_backtest_baseline_<ts>.md

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_backtest.py

Requiere: requests
.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("❌ requests no instalado. Ejecutá: pip install requests")
    sys.exit(1)

# ─── Cargar .env ──────────────────────────────────────────────────────────

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ─── Config ───────────────────────────────────────────────────────────────

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


# ─── Helpers ──────────────────────────────────────────────────────────────


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
    # Fallback: if columns array is empty, check schema field
    if not schema_cols:
        schema = manifest.get("schema", {})
        if schema and "columns" in schema:
            schema_cols = schema["columns"]
    columns = [c["name"] for c in schema_cols] if schema_cols else []

    data_array = result.get("result", {}).get("data_array", [])

    # If still no columns, use positional (col_0, col_1, ...)
    if not columns:
        columns = [f"col_{i}" for i in range(len(data_array[0]))] if data_array else []

    rows = []
    for row in data_array:
        row_dict = {}
        for i, col in enumerate(columns):
            val = row[i] if i < len(row) else None
            if val is not None:
                # Convertir tipos
                try:
                    if col in ("business_date",) and isinstance(val, str):
                        pass  # mantener string para fecha
                    elif isinstance(val, str):
                        # Intentar convertir a float o int
                        try:
                            if "." in val:
                                val = float(val)
                            else:
                                val = int(val)
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    pass
            row_dict[col] = val
        rows.append(row_dict)
    return rows


# ─── Métricas ─────────────────────────────────────────────────────────────


def calc_mape(actual: float, predicted: float) -> float | None:
    """MAPE: Mean Absolute Percentage Error."""
    if actual == 0:
        return None
    return abs(actual - predicted) / actual * 100


def calc_smape(actual: float, predicted: float) -> float | None:
    """sMAPE: Symmetric Mean Absolute Percentage Error."""
    denom = abs(actual) + abs(predicted)
    if denom == 0:
        return None
    return 2 * abs(actual - predicted) / denom * 100


def calc_wape(actuals: list[float], predictions: list[float]) -> float | None:
    """WAPE: Weighted Absolute Percentage Error (global)."""
    total_actual = sum(actuals)
    if total_actual == 0:
        return None
    total_abs_err = sum(abs(a - p) for a, p in zip(actuals, predictions))
    return total_abs_err / total_actual * 100


# ─── Main ─────────────────────────────────────────────────────────────────


def main():
    if not DATABRICKS_HOST:
        print("❌ DATABRICKS_HOST no configurado en .env")
        sys.exit(1)
    if not DATABRICKS_TOKEN:
        print("❌ DATABRICKS_TOKEN no configurado en .env")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Warehouse: {WAREHOUSE_ID}")
    print("=" * 60)

    # ── Obtener datos de forecast_baseline ──
    print("\n1. Cargando forecast_baseline_sku...")
    rows = query_databricks("""
        SELECT
            cod_producto,
            business_date,
            demanda_real,
            demanda_predicha,
            metodo
        FROM motoshop.gold.forecast_baseline_sku
        WHERE demanda_real > 0 AND demanda_predicha IS NOT NULL
        ORDER BY cod_producto, business_date
    """, "Load baseline data")

    if not rows:
        print("❌ No se pudieron cargar datos de forecast_baseline_sku")
        sys.exit(1)

    print(f"   → {len(rows)} filas cargadas")

    # ── Obtener categoría ABC ──
    print("\n2. Cargando categorías ABC...")
    abc_rows = query_databricks("""
        SELECT DISTINCT cod_producto, categoria_abc
        FROM motoshop.gold.mart_rotacion_abc
        WHERE business_month = (SELECT MAX(business_month) FROM motoshop.gold.mart_rotacion_abc)
    """, "Load ABC categories")

    abc_map: dict[str, str] = {}
    for r in abc_rows:
        abc_map[r["cod_producto"]] = r.get("categoria_abc", "C")

    print(f"   → {len(abc_map)} SKUs con categoría ABC")

    # ── Agrupar por SKU ──
    sku_data: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        sku_data[r["cod_producto"]].append(r)

    skus = list(sku_data.keys())
    print(f"\n3. Total SKUs: {len(skus)}")

    # ── Walk-forward por mes ──
    print("\n4. Ejecutando walk-forward validation...")

    # Obtener meses únicos
    fechas = sorted(set(r["business_date"][:7] for r in rows))
    meses = sorted(set(f"{f}-01" for f in fechas))

    if len(meses) < 2:
        print("⚠️ Menos de 2 meses de datos, no se puede hacer walk-forward")
        # Fallback: calcular métricas globales
        global_actuals = [float(r["demanda_real"]) for r in rows]
        global_preds = [float(r["demanda_predicha"]) for r in rows]

        global_mape_list = []
        for a, p in zip(global_actuals, global_preds):
            m = calc_mape(a, p)
            if m is not None:
                global_mape_list.append(m)

        global_mape = sum(global_mape_list) / len(global_mape_list) if global_mape_list else 0
        global_smape_list = []
        for a, p in zip(global_actuals, global_preds):
            s = calc_smape(a, p)
            if s is not None:
                global_smape_list.append(s)
        global_smape = sum(global_smape_list) / len(global_smape_list) if global_smape_list else 0
        global_wape = calc_wape(global_actuals, global_preds)

        results = {
            "global_mape": round(global_mape, 2) if global_mape else 0,
            "global_smape": round(global_smape, 2) if global_smape else 0,
            "global_wape": round(global_wape, 2) if global_wape else 0,
            "sku_metrics": {},
        }

        print(f"   MAPE global: {results['global_mape']}%")
        print(f"   sMAPE global: {results['global_smape']}%")
        print(f"   WAPE global: {results['global_wape']}%")

        # Calcular por SKU
        for sku in skus[:100]:  # top 100 SKUs
            sku_actuals = []
            sku_preds = []
            for r in sku_data[sku]:
                sku_actuals.append(float(r["demanda_real"]))
                sku_preds.append(float(r["demanda_predicha"]))

            mape_list = []
            smape_list = []
            for a, p in zip(sku_actuals, sku_preds):
                m = calc_mape(a, p)
                s = calc_smape(a, p)
                if m is not None:
                    mape_list.append(m)
                if s is not None:
                    smape_list.append(s)

            results["sku_metrics"][sku] = {
                "mape": round(sum(mape_list) / len(mape_list), 2) if mape_list else None,
                "smape": round(sum(smape_list) / len(smape_list), 2) if smape_list else None,
                "dias": len(sku_actuals),
                "categoria": abc_map.get(sku, "?"),
            }

        write_evidence(results, skus, abc_map)
        return

    # Walk-forward: train meses 1..N, test mes N+1
    all_actuals = []
    all_preds = []
    sku_mape_list: dict[str, list[float]] = defaultdict(list)
    sku_smape_list: dict[str, list[float]] = defaultdict(list)
    sku_days: dict[str, int] = defaultdict(int)

    for test_month in meses[1:]:  # Necesitamos al menos 1 mes de train
        train_months = [m for m in meses if m < test_month]

        actuals = []
        preds = []

        for r in rows:
            if r["business_date"].startswith(test_month[:7]):
                actuals.append(float(r["demanda_real"]))
                preds.append(float(r["demanda_predicha"]))
                sku = r["cod_producto"]
                a = float(r["demanda_real"])
                p = float(r["demanda_predicha"])
                m = calc_mape(a, p)
                s = calc_smape(a, p)
                if m is not None:
                    sku_mape_list[sku].append(m)
                if s is not None:
                    sku_smape_list[sku].append(s)
                sku_days[sku] += 1

        if not actuals:
            continue

        all_actuals.extend(actuals)
        all_preds.extend(preds)

        wape = calc_wape(actuals, preds)
        print(f"   Test {test_month[:7]}: {len(actuals)} obs, WAPE={wape:.2f}%" if wape else f"   Test {test_month[:7]}: {len(actuals)} obs")

    # ── Métricas globales ──
    global_mape_list = []
    for a, p in zip(all_actuals, all_preds):
        m = calc_mape(a, p)
        if m is not None:
            global_mape_list.append(m)
    global_mape = sum(global_mape_list) / len(global_mape_list) if global_mape_list else 0

    global_smape_list = []
    for a, p in zip(all_actuals, all_preds):
        s = calc_smape(a, p)
        if s is not None:
            global_smape_list.append(s)
    global_smape = sum(global_smape_list) / len(global_smape_list) if global_smape_list else 0

    global_wape = calc_wape(all_actuals, all_preds)

    # ── Por SKU ──
    sku_metrics = {}
    for sku in skus:
        mape_vals = sku_mape_list.get(sku, [])
        smape_vals = sku_smape_list.get(sku, [])
        sku_metrics[sku] = {
            "mape": round(sum(mape_vals) / len(mape_vals), 2) if mape_vals else None,
            "smape": round(sum(smape_vals) / len(smape_vals), 2) if smape_vals else None,
            "dias": sku_days.get(sku, 0),
            "categoria": abc_map.get(sku, "?"),
        }

    results = {
        "global_mape": round(global_mape, 2),
        "global_smape": round(global_smape, 2),
        "global_wape": round(global_wape, 2) if global_wape else 0,
        "sku_metrics": sku_metrics,
    }

    print(f"\n5. Resultados walk-forward:")
    print(f"   MAPE global: {results['global_mape']}%")
    print(f"   sMAPE global: {results['global_smape']}%")
    print(f"   WAPE global: {results['global_wape']}%")
    print(f"   SKUs total: {len(skus)}")
    print(f"   Observaciones totales: {len(all_actuals)}")

    write_evidence(results, skus, abc_map)


def write_evidence(results: dict, skus: list[str], abc_map: dict[str, str]):
    """Escribe evidencia en markdown."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"v_backtest_baseline_{timestamp}.md"

    sku_metrics = results.get("sku_metrics", {})

    # Ordenar SKUs por MAPE
    sorted_skus = sorted(
        [(s, m) for s, m in sku_metrics.items() if m.get("mape") is not None],
        key=lambda x: x[1]["mape"],
    )

    best_10 = sorted_skus[:10]
    worst_10 = sorted_skus[-10:] if len(sorted_skus) >= 10 else sorted_skus

    # Distribución ABC
    abc_dist: dict[str, list[float]] = {"A": [], "B": [], "C": []}
    for sku, m in sku_metrics.items():
        if m["mape"] is not None:
            cat = abc_map.get(sku, "C")
            if cat in abc_dist:
                abc_dist[cat].append(m["mape"])

    # Conteos por rango MAPE
    mape_values = [m["mape"] for m in sku_metrics.values() if m["mape"] is not None]
    lt_25 = sum(1 for v in mape_values if v < 25)
    lt_50 = sum(1 for v in mape_values if v < 50)
    gt_50 = sum(1 for v in mape_values if v >= 50)

    lines = [
        f"# Backtest Baseline — {timestamp}",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}",
        f"Fuente: gold.forecast_baseline_sku",
        "",
        "---",
        "",
        "## Resumen Global",
        "",
        f"| Métrica | Valor |",
        f"|---------|-------|",
        f"| MAPE | {results['global_mape']}% |",
        f"| sMAPE | {results['global_smape']}% |",
        f"| WAPE | {results['global_wape']}% |",
        f"| SKUs total | {len(skus)} |",
        f"| SKUs con métrica | {len(mape_values)} |",
        f"| SKUs MAPE < 25% | {lt_25} |",
        f"| SKUs MAPE < 50% | {lt_50} |",
        f"| SKUs MAPE ≥ 50% | {gt_50} |",
        "",
        "---",
        "",
        "## Top-10 Mejores SKUs (menor MAPE)",
        "",
        "| SKU | MAPE | sMAPE | Días | Cat. |",
        "|-----|------|-------|------|------|",
    ]

    for sku, m in best_10:
        lines.append(
            f"| {sku} | {m['mape']}% | {m.get('smape', 'N/A')} | {m['dias']} | {m.get('categoria', '?')} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Top-10 Peores SKUs (mayor MAPE)",
        "",
        "| SKU | MAPE | sMAPE | Días | Cat. |",
        "|-----|------|-------|------|------|",
    ])

    for sku, m in reversed(worst_10):
        lines.append(
            f"| {sku} | {m['mape']}% | {m.get('smape', 'N/A')} | {m['dias']} | {m.get('categoria', '?')} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Distribución MAPE por Categoría ABC",
        "",
        "| Categoría | SKUs | MAPE promedio |",
        "|-----------|------|---------------|",
    ])

    for cat in ("A", "B", "C"):
        vals = abc_dist.get(cat, [])
        if vals:
            avg = sum(vals) / len(vals)
            lines.append(f"| {cat} | {len(vals)} | {avg:.2f}% |")
        else:
            lines.append(f"| {cat} | 0 | N/A |")

    lines.extend([
        "",
        "---",
        "",
        "## Distribución de MAPE",
        "",
        f"- SKUs total: {len(skus)}",
        f"- SKUs con MAPE < 25%: {lt_25} ({lt_25/len(mape_values)*100:.1f}% del total)" if mape_values else "",
        f"- SKUs con MAPE < 50%: {lt_50} ({lt_50/len(mape_values)*100:.1f}% del total)" if mape_values else "",
        f"- SKUs con MAPE ≥ 50%: {gt_50} ({gt_50/len(mape_values)*100:.1f}% del total)" if mape_values else "",
        "",
        "---",
        "",
        "## Detalle por SKU (primeros 50)",
        "",
        "| SKU | MAPE | sMAPE | Días | Cat. |",
        "|-----|------|-------|------|------|",
    ])

    for sku, m in sorted_skus[:50]:
        lines.append(
            f"| {sku} | {m['mape']}% | {m.get('smape', 'N/A')} | {m['dias']} | {m.get('categoria', '?')} |"
        )

    content = "\n".join(lines)
    with open(out_path, "w") as f:
        f.write(content)

    print(f"\n✅ Evidencia escrita en {out_path}")


if __name__ == "__main__":
    main()
