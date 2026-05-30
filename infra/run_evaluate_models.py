"""
Evaluate all forecasting models and materialize the best one per SKU per horizon.

Reads from:
  - gold.forecast_prophet_sku
  - gold.forecast_lightgbm_sku
  - gold.forecast_baseline_sku (if available — Dev B may still be fixing it)
  - gold.feature_store_sku (for actual demand)

Calculates MAPE/sMAPE/WAPE per model per SKU per horizon, picks the winner,
materialises gold.forecast_demanda_sku, logs to MLflow, and writes evidence.

Outputs:
  - gold.forecast_demanda_sku (best predictions per SKU per horizon)
  - notebooks/gold/_runs/v_model_evaluation_<ts>.md (evidence report)
  - MLflow experiment (optional, best-effort)

Usage:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_evaluate_models.py

Requires: requests
.env must have DATABRICKS_HOST, DATABRICKS_TOKEN
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
TIMEOUT = 180

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

# Constantes de modelo
MODEL_PROPHET = "prophet"
MODEL_LIGHTGBM = "lightgbm"
MODEL_BASELINE = "baseline"

BASELINE_VERSION = "baseline_v1"


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

    if status in ("PENDING", "RUNNING") and statement_id:
        for _ in range(60):
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
        print(f"  ❌ Query failed: {error_msg[:300]}")
        return []

    manifest = result.get("manifest", {})
    schema_cols = manifest.get("columns", [])
    if not schema_cols:
        schema = manifest.get("schema", {})
        if schema and "columns" in schema:
            schema_cols = schema["columns"]
    columns = [c["name"] for c in schema_cols] if schema_cols else []

    data_array = result.get("result", {}).get("data_array", [])

    if not columns and data_array:
        columns = [f"col_{i}" for i in range(len(data_array[0]))]

    rows = []
    for row in data_array:
        row_dict = {}
        for i, col in enumerate(columns):
            val = row[i] if i < len(row) else None
            if val is not None and isinstance(val, str):
                try:
                    if "." in val:
                        val = float(val)
                    else:
                        val = int(val)
                except (ValueError, TypeError):
                    pass
            row_dict[col] = val
        rows.append(row_dict)
    return rows


def execute_ddl(sql: str, description: str = "DDL") -> bool:
    """Ejecuta DDL/DML y retorna True si fue exitoso."""
    payload = {
        "statement": sql,
        "warehouse_id": WAREHOUSE_ID,
        "wait_timeout": "50s",
        "on_wait_timeout": "CONTINUE",
    }

    result = api_post("/api/2.0/sql/statements", payload, description)
    if result is None:
        return False

    statement_id = result.get("statement_id")
    status = result.get("status", {}).get("state", "UNKNOWN")

    if status in ("PENDING", "RUNNING") and statement_id:
        for _ in range(60):
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
        print(f"  ❌ {description}: {error_msg[:300]}")
        return False

    return True


def safe_query(sql: str, description: str = "query") -> list[dict]:
    """Wrapper de query_databricks que captura tablas faltantes."""
    try:
        return query_databricks(sql, description)
    except Exception as e:
        print(f"  ⚠️ Error al leer {description}: {e}")
        return []


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


# ─── Carga de datos ───────────────────────────────────────────────────────


def load_prophet_forecast() -> list[dict]:
    """Carga predicciones de Prophet."""
    print("\n  📦 Cargando gold.forecast_prophet_sku...")
    rows = safe_query(
        "SELECT sku, forecast_date, horizon, predicted_qty, "
        "confidence_lower, confidence_upper, model_version, business_date "
        "FROM motoshop.gold.forecast_prophet_sku "
        "WHERE predicted_qty IS NOT NULL",
        "Load prophet",
    )
    print(f"     → {len(rows)} filas")
    return rows


def load_lightgbm_forecast() -> list[dict]:
    """Carga predicciones de LightGBM."""
    print("\n  📦 Cargando gold.forecast_lightgbm_sku...")
    rows = safe_query(
        "SELECT sku, forecast_date, horizon, predicted_qty, "
        "confidence_lower, confidence_upper, model_version, business_date "
        "FROM motoshop.gold.forecast_lightgbm_sku "
        "WHERE predicted_qty IS NOT NULL",
        "Load lightgbm",
    )
    print(f"     → {len(rows)} filas")
    return rows


def load_baseline_forecast() -> list[dict]:
    """Carga baseline si existe y tiene datos."""
    print("\n  📦 Cargando gold.forecast_baseline_sku...")
    rows = safe_query(
        "SELECT cod_producto, business_date, demanda_real, demanda_predicha, metodo "
        "FROM motoshop.gold.forecast_baseline_sku "
        "WHERE demanda_predicha IS NOT NULL AND demanda_real > 0",
        "Load baseline",
    )
    print(f"     → {len(rows)} filas")
    return rows


def load_actual_demand() -> dict[tuple[str, str], float]:
    """Carga demanda real desde feature_store_sku.

    Returns:
        Dict con key (cod_producto, business_date) -> demanda_diaria
    """
    print("\n  📦 Cargando demanda real desde gold.feature_store_sku...")
    rows = safe_query(
        "SELECT cod_producto, business_date, demanda_diaria "
        "FROM motoshop.gold.feature_store_sku "
        "WHERE demanda_diaria IS NOT NULL AND demanda_diaria > 0",
        "Load actual demand",
    )
    print(f"     → {len(rows)} filas")

    lookup: dict[tuple[str, str], float] = {}
    for r in rows:
        key = (r["cod_producto"], str(r["business_date"]))
        lookup[key] = float(r["demanda_diaria"])
    return lookup


# ─── Evaluación ────────────────────────────────────────────────────────────


def evaluate_model_forecasts(
    forecast_rows: list[dict],
    actual_lookup: dict[tuple[str, str], float],
    model_name: str,
    sku_col: str = "sku",
    date_col: str = "forecast_date",
    pred_col: str = "predicted_qty",
    actual_col: str | None = None,
) -> list[dict]:
    """Evalúa predicciones contra demanda real.

    Args:
        forecast_rows: Filas del modelo.
        actual_lookup: Dict con (cod_producto, date) -> demanda.
        model_name: Nombre del modelo para model_version.
        sku_col: Nombre de columna SKU en forecast_rows.
        date_col: Nombre de columna de fecha en forecast_rows.
        pred_col: Nombre de columna de predicción.
        actual_col: Si el modelo ya tiene la demanda real en la misma fila.

    Returns:
        Lista de dicts con métricas por SKU/fecha/horizon.
    """
    evaluated: list[dict] = []

    for r in forecast_rows:
        sku = r[sku_col]
        date = str(r[date_col])
        horizon = r.get("horizon", 1)
        predicted = float(r[pred_col])

        if actual_col and actual_col in r:
            actual = float(r[actual_col])
        else:
            key = (sku, date)
            actual = actual_lookup.get(key)

        if actual is None or actual == 0:
            continue

        mape = calc_mape(actual, predicted)
        smape = calc_smape(actual, predicted)

        if mape is None:
            continue

        evaluated.append({
            "sku": sku,
            "forecast_date": date,
            "horizon": horizon if isinstance(horizon, int) else int(horizon),
            "actual": actual,
            "predicted": predicted,
            "confidence_lower": r.get("confidence_lower"),
            "confidence_upper": r.get("confidence_upper"),
            "model_version": r.get("model_version", model_name),
            "model_name": model_name,
            "mape": round(mape, 4),
            "smape": round(smape, 4) if smape is not None else None,
            "business_date": r.get("business_date", date),
        })

    print(f"     → {len(evaluated)} evaluaciones con métrica válida")
    return evaluated


def compute_global_metrics(
    evaluated: list[dict],
) -> dict:
    """Calcula métricas globales para un modelo."""
    if not evaluated:
        return {"mape": None, "smape": None, "wape": None, "skus": set()}

    all_actuals = [e["actual"] for e in evaluated]
    all_preds = [e["predicted"] for e in evaluated]
    skus = set(e["sku"] for e in evaluated)

    mape_vals = [e["mape"] for e in evaluated if e["mape"] is not None]
    smape_vals = [e["smape"] for e in evaluated if e["smape"] is not None]

    global_mape = sum(mape_vals) / len(mape_vals) if mape_vals else None
    global_smape = sum(smape_vals) / len(smape_vals) if smape_vals else None
    global_wape = calc_wape(all_actuals, all_preds)

    return {
        "mape": round(global_mape, 2) if global_mape is not None else None,
        "smape": round(global_smape, 2) if global_smape is not None else None,
        "wape": round(global_wape, 2) if global_wape is not None else None,
        "skus": skus,
    }


# ─── Selección del mejor modelo ───────────────────────────────────────────


def select_best_per_sku_horizon(
    model_evaluations: dict[str, list[dict]],
) -> list[dict]:
    """Selecciona el mejor modelo por SKU + horizon según menor MAPE.

    Args:
        model_evaluations: Dict con nombre de modelo -> lista de evaluaciones.

    Returns:
        Lista de dicts con la mejor predicción para cada SKU+horizon.
    """
    # Agrupar por (sku, horizon)
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)

    for model_name, evals in model_evaluations.items():
        for e in evals:
            key = (e["sku"], e["horizon"])
            groups[key].append(e)

    best_predictions: list[dict] = []
    for key, entries in groups.items():
        # Elegir la entrada con menor MAPE
        valid = [e for e in entries if e["mape"] is not None]
        if not valid:
            continue
        best = min(valid, key=lambda e: e["mape"])
        best_predictions.append(best)

    print(f"\n     → {len(best_predictions)} mejores predicciones seleccionadas")
    return best_predictions


# ─── Materialización ──────────────────────────────────────────────────────


def format_sql_value(val) -> str:
    """Formatea un valor para INSERT SQL."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return "NULL"
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("'", "''")
        return f"'{escaped}'"
    return f"'{str(val)}'"


def materialize_best_predictions(best_predictions: list[dict]) -> bool:
    """INSERT OVERWRITE en gold.forecast_demanda_sku con las mejores predicciones."""
    print("\n  4. Materializando gold.forecast_demanda_sku...")

    # Crear tabla si no existe
    create_sql = """
    CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_demanda_sku (
      sku STRING,
      forecast_date DATE,
      horizon INT,
      predicted_qty DOUBLE,
      confidence_lower DOUBLE,
      confidence_upper DOUBLE,
      model_version STRING,
      mape DOUBLE,
      smape DOUBLE,
      business_date DATE
    ) USING DELTA PARTITIONED BY (business_date)
    """
    if not execute_ddl(create_sql, "Create forecast_demanda_sku"):
        print("  ❌ No se pudo crear la tabla")
        return False

    # Limpiar datos existentes
    execute_ddl("DELETE FROM motoshop.gold.forecast_demanda_sku", "Truncate forecast_demanda_sku")

    if not best_predictions:
        print("  ⚠️ No hay predicciones para insertar")
        return False

    # Insertar en batches de 100
    BATCH_SIZE = 100
    columns = [
        "sku", "forecast_date", "horizon", "predicted_qty",
        "confidence_lower", "confidence_upper", "model_version",
        "mape", "smape", "business_date",
    ]

    total_inserted = 0
    for i in range(0, len(best_predictions), BATCH_SIZE):
        batch = best_predictions[i : i + BATCH_SIZE]
        values_list: list[str] = []

        for bp in batch:
            vals = [
                str(bp.get("sku", "")),
                str(bp.get("forecast_date", "")),
                bp.get("horizon", 1),
                max(0.0, bp.get("predicted") or bp.get("predicted_qty") or 0),
                bp.get("confidence_lower"),
                bp.get("confidence_upper"),
                bp.get("model_version", "unknown"),
                bp.get("mape"),
                bp.get("smape"),
                bp.get("business_date", bp.get("forecast_date", "")),
            ]
            formatted = ", ".join(format_sql_value(v) for v in vals)
            values_list.append(f"({formatted})")

        values_str = ",\n  ".join(values_list)
        insert_sql = (
            "INSERT INTO motoshop.gold.forecast_demanda_sku\n"
            f"  ({', '.join(columns)})\n"
            "VALUES\n"
            f"  {values_str}"
        )

        if execute_ddl(insert_sql, f"Insert batch {i // BATCH_SIZE + 1}"):
            total_inserted += len(batch)
        else:
            print(f"  ⚠️ Error insertando batch {i // BATCH_SIZE + 1}")

    print(f"     → {total_inserted} filas insertadas")
    return total_inserted > 0


# ─── MLflow ────────────────────────────────────────────────────────────────


def log_to_mlflow(
    model_metrics: dict[str, dict],
    best_model_counts: dict[str, int],
    total_skus: int,
    total_best: int,
):
    """Registra métricas en MLflow (best-effort)."""
    print("\n  5. Registrando en MLflow...")
    try:
        import mlflow
        import mlflow.tracking

        REPO_ROOT_ML = pathlib.Path(__file__).resolve().parent.parent
        mlflow.set_tracking_uri(f"file:{REPO_ROOT_ML}/mlruns")
        experiment_name = "motoshop_forecast"
        mlflow.set_experiment(experiment_name)

        with mlflow.start_run() as run:
            mlflow.set_tags({
                "modelo": "evaluation",
                "sprint": "F4-B",
                "tipo": "model_selection",
            })

            # Métricas globales por modelo
            for model_name, metrics in model_metrics.items():
                if metrics["mape"] is not None:
                    mlflow.log_metric(f"{model_name}_mape", metrics["mape"])
                if metrics["smape"] is not None:
                    mlflow.log_metric(f"{model_name}_smape", metrics["smape"])
                if metrics["wape"] is not None:
                    mlflow.log_metric(f"{model_name}_wape", metrics["wape"])
                mlflow.log_metric(f"{model_name}_skus_evaluated", len(metrics["skus"]))

            # Distribución de modelos ganadores
            for model_name, count in best_model_counts.items():
                mlflow.log_metric(f"selected_{model_name}", count)
                pct = round(count / total_best * 100, 1) if total_best > 0 else 0
                mlflow.log_metric(f"selected_{model_name}_pct", pct)

            mlflow.log_param("total_skus", total_skus)
            mlflow.log_param("total_best_predictions", total_best)
            mlflow.log_param("models_evaluated", list(model_metrics.keys()))

            print(f"     ✅ MLflow run: {run.info.run_id}")
            return run.info.run_id

    except ImportError:
        print("     ⚠️ mlflow no instalado — saltando logging MLflow")
    except Exception as e:
        print(f"     ⚠️ Error en MLflow: {e}")

    return None


# ─── Evidencia ────────────────────────────────────────────────────────────


def write_evidence(
    model_metrics: dict[str, dict],
    model_evaluations: dict[str, list[dict]],
    best_model_counts: dict[str, int],
    total_skus: int,
    checks: dict[str, bool],
    mlflow_run_id: str | None,
):
    """Escribe evidencia en markdown."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"v_model_evaluation_{timestamp}.md"

    timestamp_iso = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# Model Evaluation — {timestamp}",
        "",
        f"Fecha: {timestamp_iso}",
        "",
        "---",
        "",
        "## Comparison Summary",
        "",
        "| Model | MAPE | sMAPE | WAPE | SKUs evaluated |",
        "|-------|------|-------|------|----------------|",
    ]

    for model_name in [MODEL_PROPHET, MODEL_LIGHTGBM, MODEL_BASELINE]:
        metrics = model_metrics.get(model_name, {})
        mape = f"{metrics.get('mape', 'N/A')}%" if metrics.get("mape") is not None else "N/A"
        smape = f"{metrics.get('smape', 'N/A')}%" if metrics.get("smape") is not None else "N/A"
        wape = f"{metrics.get('wape', 'N/A')}%" if metrics.get("wape") is not None else "N/A"
        skus = len(metrics.get("skus", set()))
        lines.append(f"| {model_name.capitalize()} | {mape} | {smape} | {wape} | {skus} |")

    total_best = sum(best_model_counts.values()) if best_model_counts else 0

    lines.extend([
        "",
        "---",
        "",
        "## Best Model Distribution (by SKU)",
        "",
        "| Model | # SKUs selected | % of total |",
        "|-------|-----------------|------------|",
    ])

    for model_name in [MODEL_PROPHET, MODEL_LIGHTGBM, MODEL_BASELINE]:
        count = best_model_counts.get(model_name, 0)
        pct = round(count / total_best * 100, 1) if total_best > 0 else 0
        lines.append(f"| {model_name.capitalize()} | {count} | {pct}% |")

    lines.extend([
        "",
        "---",
        "",
        "## Distribution by Horizon",
        "",
    ])

    # Contar por horizon según el mejor modelo
    horizon_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    model_evals_flat = {}
    for m_name, evals in model_evaluations.items():
        for e in evals:
            key = (e["sku"], e["horizon"])
            if key not in model_evals_flat or e["mape"] < model_evals_flat[key]["mape"]:
                model_evals_flat[key] = {**e, "model_name": m_name}

    for key, entry in model_evals_flat.items():
        _, horizon = key
        horizon_counts[horizon][entry["model_name"]] += 1

    if horizon_counts:
        lines.append("| Horizon | Prophet | LightGBM | Baseline | Total |")
        lines.append("|---------|---------|----------|---------|-------|")
        for horizon in sorted(horizon_counts.keys()):
            hc = horizon_counts[horizon]
            p = hc.get(MODEL_PROPHET, 0)
            l = hc.get(MODEL_LIGHTGBM, 0)
            b = hc.get(MODEL_BASELINE, 0)
            t = p + l + b
            lines.append(f"| {horizon}d | {p} | {l} | {b} | {t} |")

    lines.extend([
        "",
        "---",
        "",
        "## Verification",
        "",
    ])

    v_m4 = checks.get("V-M4", False)
    v_m6 = checks.get("V-M6", False)
    v_m8 = checks.get("V-M8", False)

    lines.append(f"- V-M4: forecast_demanda_sku has >= 100 SKUs with predictions → {'✅' if v_m4 else '❌'}")
    lines.append(f"- V-M6: Sanity check (0 negatives, 0 nulls) → {'✅' if v_m6 else '❌'}")
    lines.append(f"- V-M8: MLflow experiments created → {'✅' if v_m8 else '❌'}")

    if mlflow_run_id:
        lines.append(f"  - MLflow run ID: {mlflow_run_id}")

    content = "\n".join(lines)
    with open(out_path, "w") as f:
        f.write(content)

    print(f"\n  ✅ Evidencia escrita en {out_path}")
    return str(out_path)


# ─── Verificación ─────────────────────────────────────────────────────────


def verify_table(table_name: str) -> tuple[int, int, list[str]]:
    """Verifica contenido de forecast_demanda_sku.

    Returns:
        (total_rows, unique_skus, models_in_table)
    """
    rows = query_databricks(
        "SELECT COUNT(*) AS cnt FROM motoshop.gold.forecast_demanda_sku",
        f"Count {table_name}",
    )
    total = rows[0]["cnt"] if rows else 0

    skus = query_databricks(
        "SELECT COUNT(DISTINCT sku) AS sku_cnt FROM motoshop.gold.forecast_demanda_sku",
        f"Distinct SKUs {table_name}",
    )
    unique_skus = skus[0]["sku_cnt"] if skus else 0

    models = query_databricks(
        "SELECT DISTINCT model_version FROM motoshop.gold.forecast_demanda_sku",
        f"Models in {table_name}",
    )
    model_list = [r["model_version"] for r in models]

    return total, unique_skus, model_list


def check_sanity_forecast_demanda() -> dict[str, int]:
    """V-M6: Verifica integridad de forecast_demanda_sku.

    Returns:
        Dict con conteo de anomalías: negative_qty, null_sku, null_date, null_horizon
    """
    anomalies: dict[str, int] = {}
    checks_sql = {
        "negative_qty": "SELECT COUNT(*) AS cnt FROM motoshop.gold.forecast_demanda_sku WHERE predicted_qty < 0",
        "null_sku": "SELECT COUNT(*) AS cnt FROM motoshop.gold.forecast_demanda_sku WHERE sku IS NULL",
        "null_date": "SELECT COUNT(*) AS cnt FROM motoshop.gold.forecast_demanda_sku WHERE forecast_date IS NULL",
        "null_horizon": "SELECT COUNT(*) AS cnt FROM motoshop.gold.forecast_demanda_sku WHERE horizon IS NULL",
    }
    for name, sql in checks_sql.items():
        rows = query_databricks(sql, f"Sanity {name}")
        anomalies[name] = rows[0]["cnt"] if rows else -1
    return anomalies


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

    # ── 1. Cargar datos ──
    print("\n1. Cargando predicciones y demanda real...")

    prophet_rows = load_prophet_forecast()
    lightgbm_rows = load_lightgbm_forecast()
    baseline_rows = load_baseline_forecast()

    actual_lookup = load_actual_demand()

    print(f"\n   Demand lookup size: {len(actual_lookup)} entries")
    print("=" * 60)

    # ── 2. Evaluar modelos ──
    print("\n2. Evaluando modelos...")

    model_evaluations: dict[str, list[dict]] = {}

    if prophet_rows:
        print(f"\n   --- Prophet ---")
        model_evaluations[MODEL_PROPHET] = evaluate_model_forecasts(
            prophet_rows, actual_lookup, MODEL_PROPHET,
            sku_col="sku", date_col="forecast_date",
        )

    if lightgbm_rows:
        print(f"\n   --- LightGBM ---")
        model_evaluations[MODEL_LIGHTGBM] = evaluate_model_forecasts(
            lightgbm_rows, actual_lookup, MODEL_LIGHTGBM,
            sku_col="sku", date_col="forecast_date",
        )

    if baseline_rows:
        print(f"\n   --- Baseline ---")
        model_evaluations[MODEL_BASELINE] = evaluate_model_forecasts(
            baseline_rows, actual_lookup, MODEL_BASELINE,
            sku_col="cod_producto", date_col="business_date",
            pred_col="demanda_predicha",
            actual_col="demanda_real",
        )

    if not model_evaluations:
        print("❌ No hay evaluaciones de ningún modelo — abortando")
        sys.exit(1)

    # ── 3. Métricas globales ──
    print("\n3. Métricas globales por modelo...")

    model_metrics: dict[str, dict] = {}
    for model_name, evals in model_evaluations.items():
        metrics = compute_global_metrics(evals)
        model_metrics[model_name] = metrics
        print(f"\n   --- {model_name.capitalize()} ---")
        print(f"     MAPE: {metrics['mape']}%")
        print(f"     sMAPE: {metrics['smape']}%")
        print(f"     WAPE: {metrics['wape']}%")
        print(f"     SKUs: {len(metrics['skus'])}")

    # ── 4. Seleccionar mejor modelo ──
    print("\n" + "=" * 60)
    print("4. Seleccionando mejor modelo por SKU + horizon...")

    best_predictions = select_best_per_sku_horizon(model_evaluations)

    # Contar cuántos SKU ganó cada modelo
    best_model_counts: dict[str, int] = defaultdict(int)
    for bp in best_predictions:
        model_name = bp.get("model_name", "unknown")
        best_model_counts[model_name] += 1

    print(f"\n   Distribución de modelos ganadores:")
    total_best = sum(best_model_counts.values())
    for model_name in [MODEL_PROPHET, MODEL_LIGHTGBM, MODEL_BASELINE]:
        count = best_model_counts.get(model_name, 0)
        pct = round(count / total_best * 100, 1) if total_best > 0 else 0
        print(f"     {model_name.capitalize()}: {count} ({pct}%)")

    # ── 5. Materializar ──
    print("\n" + "=" * 60)
    materialize_best_predictions(best_predictions)

    # ── 6. Verificación post-materialización ──
    print("\n" + "=" * 60)
    print("5. Verificación...")

    total_rows, unique_skus, models_in_table = verify_table("forecast_demanda_sku")
    print(f"\n   gold.forecast_demanda_sku:")
    print(f"     Filas: {total_rows}")
    print(f"     SKUs únicos: {unique_skus}")
    print(f"     Modelos: {models_in_table}")

    # V-M4: >= 100 SKUs
    v_m4 = unique_skus >= 100
    print(f"\n   V-M4: forecast_demanda_sku has >= 100 SKUs: {'✅' if v_m4 else '❌'}")

    # V-M6: Sanity check
    print("\n   V-M6: Sanity check (0 negativos, 0 nulls)...")
    sanity = check_sanity_forecast_demanda()
    v_m6 = all(v == 0 for v in sanity.values())
    for check_name, cnt in sanity.items():
        status = "✅" if cnt == 0 else "❌"
        print(f"     {check_name}: {cnt} {'anomalías' if cnt != 1 else 'anomalía'} {status}")
    print(f"     → {'✅ PASS' if v_m6 else '❌ FAIL'}")

    # V-M8: MLflow runs created
    mlflow_run_id = log_to_mlflow(
        model_metrics, dict(best_model_counts),
        unique_skus, len(best_predictions),
    )
    v_m8 = mlflow_run_id is not None
    print(f"   V-M8: MLflow experiments created: {'✅' if v_m8 else '❌'}")

    checks = {"V-M4": v_m4, "V-M6": v_m6, "V-M8": v_m8}

    # ── 7. Evidencia ──
    print("\n" + "=" * 60)
    print("6. Escribiendo evidencia...")

    evidence_path = write_evidence(
        model_metrics, model_evaluations,
        dict(best_model_counts), unique_skus,
        checks, mlflow_run_id,
    )

    # ── Resumen final ──
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Modelos evaluados: {', '.join(model_evaluations.keys())}")
    print(f"  Mejores predicciones: {len(best_predictions)}")
    print(f"  SKUs en tabla final: {unique_skus}")
    print(f"  MLflow run: {mlflow_run_id or 'N/A'}")
    print(f"  Evidencia: {evidence_path}")
    print(f"  V-M4: forecast_demanda_sku >= 100 SKUs → {'✅' if v_m4 else '❌'}")
    print(f"  V-M6: Sanity (0 negatives, 0 nulls) → {'✅' if v_m6 else '❌'}")
    print(f"  V-M8: MLflow experiments created → {'✅' if v_m8 else '❌'}")
    print("=" * 60)
    print("✅ Evaluación completa.")


if __name__ == "__main__":
    main()
