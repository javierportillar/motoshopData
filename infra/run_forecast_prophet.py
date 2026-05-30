#!/usr/bin/env python3
"""
Forecast Prophet para F4-B sprint.

Lee de gold.feature_store_sku, entrena Prophet para top-100 SKUs,
genera predicciones a horizonte 7/14/30 días y escribe en
gold.forecast_prophet_sku. Loggea métricas a MLflow.

Output: notebooks/gold/_runs/v_forecast_prophet_<ts>.md

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_forecast_prophet.py

Requiere: prophet, mlflow, requests, pandas, numpy
    pip install prophet mlflow requests pandas numpy

.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import os
import pathlib
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

try:
    import numpy as np
except ImportError:
    print("numpy no instalado. Ejecutá: pip install numpy")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("pandas no instalado. Ejecutá: pip install pandas")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("requests no instalado. Ejecutá: pip install requests")
    sys.exit(1)

try:
    from prophet import Prophet
except ImportError:
    print("prophet no instalado. Ejecutá: pip install prophet")
    sys.exit(1)

try:
    import mlflow
except ImportError:
    print("mlflow no instalado. Ejecutá: pip install mlflow")
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
today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ─── Parámetros ────────────────────────────────────────────────────────────

TOP_N = 100
HORIZONS = [7, 14, 30]
FIT_TIMEOUT_SEC = 30
MODEL_VERSION = "prophet-v1.0"

# ─── Timeout helper ───────────────────────────────────────────────────────


class FitTimeoutError(Exception):
    """Se lanza cuando Prophet.fit() excede el timeout."""


def _timeout_handler(signum, frame):
    raise FitTimeoutError(f"Prophet fit timeout (>{FIT_TIMEOUT_SEC}s)")


signal.signal(signal.SIGALRM, _timeout_handler)


# ─── Helpers Databricks ───────────────────────────────────────────────────


def api_post(endpoint: str, payload: dict, description: str = "") -> dict | None:
    url = f"{DATABRICKS_HOST}{endpoint}"
    try:
        resp = SESSION.post(url, json=payload, timeout=TIMEOUT)
        if resp.status_code in (200, 201, 202):
            return resp.json()
        else:
            print(f"  HTTP {resp.status_code} — {description}")
            return None
    except Exception as e:
        print(f"  {e} — {description}")
        return None


def api_get(endpoint: str, description: str = "") -> dict | None:
    url = f"{DATABRICKS_HOST}{endpoint}"
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  HTTP {resp.status_code} — {description}")
            return None
    except Exception as e:
        print(f"  {e} — {description}")
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
            poll = api_get(
                f"/api/2.0/sql/statements/{statement_id}", f"Poll {description}"
            )
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
        print(f"  Query failed: {error_msg[:200]}")
        return []

    manifest = result.get("manifest", {})
    schema_cols = manifest.get("columns", [])
    if not schema_cols:
        schema = manifest.get("schema", {})
        if schema and "columns" in schema:
            schema_cols = schema["columns"]
    columns = [c["name"] for c in schema_cols] if schema_cols else []

    data_array = result.get("result", {}).get("data_array", [])
    if not columns:
        columns = [f"col_{i}" for i in range(len(data_array[0]))] if data_array else []

    rows = []
    for row in data_array:
        row_dict = {}
        for i, col in enumerate(columns):
            val = row[i] if i < len(row) else None
            if val is not None:
                try:
                    if col in ("business_date",) and isinstance(val, str):
                        pass
                    elif isinstance(val, str):
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


def execute_sql(sql: str, description: str = "execute") -> bool:
    """Ejecuta SQL sin esperar resultados (DDL o INSERT)."""
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
            poll = api_get(
                f"/api/2.0/sql/statements/{statement_id}", f"Poll {description}"
            )
            if poll is None:
                break
            poll_status = poll.get("status", {}).get("state", "UNKNOWN")
            if poll_status in ("SUCCEEDED", "FAILED", "CANCELED"):
                status = poll_status
                break
            if poll_status == "RUNNING":
                continue

    if status != "SUCCEEDED":
        print(f"  SQL failed — {description}")
        return False
    return True


# ─── Métricas ─────────────────────────────────────────────────────────────


def calc_mape(actual: float, predicted: float) -> float | None:
    """MAPE: Mean Absolute Percentage Error."""
    if actual == 0:
        return None
    return abs(actual - predicted) / actual * 100


# ─── Main ─────────────────────────────────────────────────────────────────


def main():
    if not DATABRICKS_HOST:
        print("DATABRICKS_HOST no configurado en .env")
        sys.exit(1)
    if not DATABRICKS_TOKEN:
        print("DATABRICKS_TOKEN no configurado en .env")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Warehouse: {WAREHOUSE_ID}")
    print(f"Timestamp: {timestamp}")
    print(f"Top SKUs: {TOP_N}")
    print(f"Horizons: {HORIZONS}")
    print("=" * 60)

    # ── 1. Crear tabla destino si no existe ──
    print("\n1. Creando/verificando gold.forecast_prophet_sku...")
    ddl = """
        CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_prophet_sku (
          sku STRING,
          forecast_date DATE,
          horizon INT,
          predicted_qty DOUBLE,
          confidence_lower DOUBLE,
          confidence_upper DOUBLE,
          model_version STRING,
          business_date DATE
        ) USING DELTA PARTITIONED BY (business_date)
    """
    if not execute_sql(ddl, "Create forecast_prophet_sku table"):
        print("No se pudo crear la tabla destino. Abortando.")
        sys.exit(1)
    print("   Tabla lista.")

    # ── 2. Obtener top-100 SKUs por demanda total ──
    print("\n2. Obteniendo top-100 SKUs por demanda total...")
    top_rows = query_databricks(
        """
        SELECT cod_producto, ROUND(SUM(demanda_diaria), 2) AS total_demand
        FROM motoshop.gold.feature_store_sku
        GROUP BY cod_producto
        ORDER BY total_demand DESC
        LIMIT 100
        """,
        "Top-100 SKUs",
    )
    if not top_rows:
        print("No se obtuvieron SKUs.")
        sys.exit(1)

    top_skus = [r["cod_producto"] for r in top_rows]
    sku_demand_map = {r["cod_producto"]: r["total_demand"] for r in top_rows}
    print(f"   {len(top_skus)} SKUs seleccionados.")

    # ── 3. Cargar datos de feature_store para esos SKUs ──
    print("\n3. Cargando datos de feature_store_sku...")
    # Build IN clause chunked to avoid overly long statements
    chunk_size = 50
    all_data = []
    for i in range(0, len(top_skus), chunk_size):
        chunk = top_skus[i : i + chunk_size]
        sku_list = ", ".join(f"'{s}'" for s in chunk)
        chunk_rows = query_databricks(
            f"""
            SELECT cod_producto, business_date, demanda_diaria
            FROM motoshop.gold.feature_store_sku
            WHERE cod_producto IN ({sku_list})
            ORDER BY cod_producto, business_date
            """,
            f"Load data SKUs {i+1}-{i+len(chunk)}",
        )
        all_data.extend(chunk_rows)

    print(f"   {len(all_data)} filas cargadas.")

    # Agrupar por SKU
    sku_data: dict[str, list[dict]] = {}
    for r in all_data:
        sku = r["cod_producto"]
        if sku not in sku_data:
            sku_data[sku] = []
        sku_data[sku].append(r)

    # ── 4. MLflow setup ──
    print("\n4. Inicializando MLflow...")
    mlflow.set_tracking_uri(f"file:{REPO_ROOT}/mlruns")
    experiment_name = "motoshop-forecast"
    try:
        mlflow.set_experiment(experiment_name)
    except Exception as e:
        print(f"   MLflow experiment warning: {e}")

    # ── 5. Procesar cada SKU con Prophet ──
    print(f"\n5. Entrenando Prophet para {len(top_skus)} SKUs...")
    print("=" * 60)

    all_predictions: list[dict] = []
    sku_mape: dict[str, dict[int, float | None]] = {}

    skus_ok = 0
    skus_zero = 0
    skus_short = 0
    skus_timeout = 0
    skus_error = 0
    skus_no_eval = 0

    with mlflow.start_run(run_name=f"prophet-forecast-{timestamp}") as run:
        run_id = run.info.run_id
        mlflow.set_tags({"modelo": "prophet", "sprint": "F4-B"})
        mlflow.log_params(
            {
                "top_n": TOP_N,
                "horizons": str(HORIZONS),
                "model_version": MODEL_VERSION,
                "fit_timeout_sec": FIT_TIMEOUT_SEC,
            }
        )

        for idx, sku in enumerate(top_skus, 1):
            print(f"\n   [{idx}/{len(top_skus)}] {sku} ...")

            rows_sku = sku_data.get(sku, [])
            if not rows_sku:
                print(f"     Sin datos, skip.")
                skus_zero += 1
                continue

            # Build dataframe
            df = pd.DataFrame(
                {
                    "ds": pd.to_datetime([r["business_date"] for r in rows_sku]),
                    "y": [float(r["demanda_diaria"]) for r in rows_sku],
                }
            ).sort_values("ds").reset_index(drop=True)

            n_days = len(df)
            total_demand = float(df["y"].sum())

            print(f"     días={n_days}, demanda_total={total_demand:.1f}")

            # Edge case: demanda cero
            if total_demand == 0:
                print(f"     Demanda total cero, skip.")
                skus_zero += 1
                mlflow.log_metric(f"{sku}_status", 0)
                continue

            # Edge case: pocos datos
            if n_days < 14:
                print(f"     Solo {n_days} días (< 14), skip.")
                skus_short += 1
                mlflow.log_metric(f"{sku}_status", -1)
                continue

            # Determinar changepoint_prior_scale
            if n_days < 14:
                cps = 0.01
            elif n_days < 30:
                cps = 0.05
            else:
                cps = 0.05  # Prophet default

            # ── Evaluación: holdout + train ──
            holdout = min(30, n_days - 14)  # al menos 14 días de train
            if holdout < 7:
                # Muy pocos datos para evaluar, solo predecir forward
                print(f"     Holdout={holdout}<7, solo forward prediction.")
                train_df = df
                sku_mape[sku] = {h: None for h in HORIZONS}
                skus_no_eval += 1
            else:
                train_df_eval = df.iloc[:-holdout].copy()
                test_df = df.iloc[-holdout:].copy()

                signal.alarm(FIT_TIMEOUT_SEC)
                try:
                    m_eval = Prophet(
                        yearly_seasonality=True,
                        weekly_seasonality=True,
                        changepoint_prior_scale=cps,
                    )
                    m_eval.fit(train_df_eval)
                    signal.alarm(0)
                except FitTimeoutError:
                    signal.alarm(0)
                    print(f"     Timeout en evaluación (>30s), skip.")
                    skus_timeout += 1
                    continue
                except Exception as e:
                    signal.alarm(0)
                    print(f"     Error en evaluación: {e}")
                    skus_error += 1
                    continue

                # Predecir fechas del holdout explícitamente
                future_eval = pd.DataFrame({"ds": test_df["ds"].values})
                forecast_eval = m_eval.predict(future_eval)

                # MAPE por horizonte
                mape_per_horizon: dict[int, float | None] = {}
                for h in HORIZONS:
                    if holdout >= h:
                        actual = float(test_df.iloc[h - 1]["y"])
                        predicted = float(forecast_eval.iloc[h - 1]["yhat"])
                        m = calc_mape(actual, predicted)
                        mape_per_horizon[h] = round(m, 2) if m is not None else None
                    else:
                        mape_per_horizon[h] = None

                sku_mape[sku] = mape_per_horizon

                # Log per-SKU MAPE a MLflow
                for h in HORIZONS:
                    val = mape_per_horizon.get(h)
                    if val is not None:
                        mlflow.log_metric(f"{sku}_mape_{h}d", val)

                # ── Store holdout predictions for evaluation ──
                for h in HORIZONS:
                    if holdout >= h:
                        row_pred = forecast_eval.iloc[h - 1]
                        pred_date = test_df.iloc[h - 1]["ds"].strftime("%Y-%m-%d")
                        all_predictions.append({
                            "sku": sku,
                            "forecast_date": pred_date,
                            "horizon": h,
                            "predicted_qty": round(float(row_pred["yhat"]), 4),
                            "confidence_lower": round(float(row_pred["yhat_lower"]), 4),
                            "confidence_upper": round(float(row_pred["yhat_upper"]), 4),
                            "model_version": MODEL_VERSION,
                            "business_date": pred_date,
                        })

                # Usar train completo para forward prediction
                train_df = df

            # ── Forward prediction: entrenar con TODO ──
            signal.alarm(FIT_TIMEOUT_SEC)
            try:
                m_full = Prophet(
                    yearly_seasonality=True,
                    weekly_seasonality=True,
                    changepoint_prior_scale=cps,
                )
                m_full.fit(train_df)
                signal.alarm(0)
            except FitTimeoutError:
                signal.alarm(0)
                print(f"     Timeout en forward fit (>30s), skip.")
                skus_timeout += 1
                continue
            except Exception as e:
                signal.alarm(0)
                print(f"     Error en forward fit: {e}")
                skus_error += 1
                continue

            # Generar predicciones 30 días adelante
            future_fwd = m_full.make_future_dataframe(
                periods=30, include_history=False
            )
            forecast_fwd = m_full.predict(future_fwd)

            # Extraer horizontes
            for h in HORIZONS:
                row_pred = forecast_fwd.iloc[h - 1]
                pred_qty = float(row_pred["yhat"])
                conf_low = float(row_pred["yhat_lower"])
                conf_up = float(row_pred["yhat_upper"])
                forecast_date = row_pred["ds"].strftime("%Y-%m-%d")

                all_predictions.append(
                    {
                        "sku": sku,
                        "forecast_date": forecast_date,
                        "horizon": h,
                        "predicted_qty": round(pred_qty, 4),
                        "confidence_lower": round(conf_low, 4),
                        "confidence_upper": round(conf_up, 4),
                        "model_version": MODEL_VERSION,
                        "business_date": today_str,
                    }
                )

            skus_ok += 1
            mlflow.log_metric(f"{sku}_status", 1)

            # Progress cada 10 SKUs
            if idx % 10 == 0:
                print(f"     --- {idx}/{len(top_skus)} procesados ---")

    # ── 6. Escribir predicciones a Databricks ──
    print(f"\n6. Escribiendo {len(all_predictions)} predicciones a Databricks...")

    if all_predictions:
        batch_size = 100
        written = 0
        for i in range(0, len(all_predictions), batch_size):
            batch = all_predictions[i : i + batch_size]
            value_rows = []
            for p in batch:
                sku_esc = str(p["sku"]).replace("'", "''")
                vals = (
                    f"'{sku_esc}'",
                    f"'{p['forecast_date']}'",
                    str(p["horizon"]),
                    str(p["predicted_qty"]),
                    str(p["confidence_lower"]),
                    str(p["confidence_upper"]),
                    f"'{p['model_version']}'",
                    f"'{p['business_date']}'",
                )
                value_rows.append(f"({', '.join(vals)})")

            insert_sql = f"""
                INSERT INTO motoshop.gold.forecast_prophet_sku
                (sku, forecast_date, horizon, predicted_qty,
                 confidence_lower, confidence_upper,
                 model_version, business_date)
                VALUES
                {', '.join(value_rows)}
            """
            ok = execute_sql(
                insert_sql, f"Insert batch {i//batch_size + 1}"
            )
            if ok:
                written += len(batch)

        print(f"   {written}/{len(all_predictions)} escritas.")

        # ── 7. Vaciar datos viejos? No, acumulamos por business_date ──
        # Simplemente loggeamos
    else:
        print("   Sin predicciones para escribir.")

    # ── 8. Métricas agregadas ──
    print("\n7. Métricas agregadas...")

    # Aggregate MAPE por horizonte
    agg_mape: dict[int, list[float]] = {h: [] for h in HORIZONS}
    for sku, horizons_map in sku_mape.items():
        for h in HORIZONS:
            val = horizons_map.get(h)
            if val is not None:
                agg_mape[h].append(val)

    with mlflow.start_run(run_id=run_id) as active_run:
        for h in HORIZONS:
            vals = agg_mape[h]
            if vals:
                avg_mape = round(float(np.mean(vals)), 2)
                mlflow.log_metric(f"avg_mape_{h}d", avg_mape)
                print(f"   MAPE promedio {h}d: {avg_mape}% ({len(vals)} SKUs)")
            else:
                print(f"   MAPE promedio {h}d: N/A")

        # MAPE promedio general
        all_mape_vals = []
        for vals in agg_mape.values():
            all_mape_vals.extend(vals)
        if all_mape_vals:
            overall_mape = round(float(np.mean(all_mape_vals)), 2)
            mlflow.log_metric("avg_mape_overall", overall_mape)
            print(f"   MAPE promedio global: {overall_mape}% ({len(all_mape_vals)} puntos)")

            # Baseline check
            baseline_mape = 43.7
            if overall_mape < baseline_mape:
                print(f"\n   ✅ Prophet MAPE ({overall_mape}%) < baseline ({baseline_mape}%) — V-M1 PASS")
            else:
                print(f"\n   ❌ Prophet MAPE ({overall_mape}%) >= baseline ({baseline_mape}%) — V-M1 FAIL")

    # ── 9. Evidencia ──
    print("\n8. Escribiendo evidencia...")
    write_evidence(
        skus_ok=skus_ok,
        skus_zero=skus_zero,
        skus_short=skus_short,
        skus_timeout=skus_timeout,
        skus_error=skus_error,
        skus_no_eval=skus_no_eval,
        total_predictions=len(all_predictions),
        sku_mape=sku_mape,
        agg_mape=agg_mape,
        sku_demand_map=sku_demand_map,
        run_id=run_id,
    )

    print("\n" + "=" * 60)
    print("Finalizado.")
    print(f"   SKUs procesados: {skus_ok}")
    print(f"   SKUs skip (demanda cero): {skus_zero}")
    print(f"   SKUs skip (<14 días): {skus_short}")
    print(f"   SKUs timeout: {skus_timeout}")
    print(f"   SKUs error: {skus_error}")
    print(f"   Predicciones totales: {len(all_predictions)}")

    if all_mape_vals:
        print(f"   MAPE global: {overall_mape}%")
        if overall_mape < 43.7:
            print("   ✅ V-M1 PASS: Prophet MAPE < 43.7%")
        else:
            print("   ❌ V-M1 FAIL: Prophet MAPE >= 43.7%")
    print(f"   MLflow Run ID: {run_id}")
    print(f"   Evidencia: notebooks/gold/_runs/v_forecast_prophet_{timestamp}.md")


def write_evidence(
    skus_ok: int,
    skus_zero: int,
    skus_short: int,
    skus_timeout: int,
    skus_error: int,
    skus_no_eval: int,
    total_predictions: int,
    sku_mape: dict[str, dict[int, float | None]],
    agg_mape: dict[int, list[float]],
    sku_demand_map: dict[str, float],
    run_id: str,
):
    """Escribe evidencia en markdown."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"v_forecast_prophet_{timestamp}.md"

    # Calcular MAPE global
    all_vals = []
    for vals in agg_mape.values():
        all_vals.extend(vals)
    overall_mape = round(float(np.mean(all_vals)), 2) if all_vals else None

    # MAPE por horizonte
    mape_7d = round(float(np.mean(agg_mape[7])), 2) if agg_mape[7] else None
    mape_14d = round(float(np.mean(agg_mape[14])), 2) if agg_mape[14] else None
    mape_30d = round(float(np.mean(agg_mape[30])), 2) if agg_mape[30] else None

    # Armar tabla de SKUs
    sku_rows_sorted = sorted(
        [
            (s, m.get(7), m.get(14), m.get(30))
            for s, m in sku_mape.items()
        ],
        key=lambda x: (
            x[1] if x[1] is not None else 999,
            x[2] if x[2] is not None else 999,
        ),
    )[:50]  # Top 50 para el detalle

    lines = [
        f"# Forecast Prophet — {timestamp}",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}",
        f"Fuente: gold.feature_store_sku → gold.forecast_prophet_sku",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- SKUs procesados: {skus_ok}",
        f"- SKUs skip (demanda cero): {skus_zero}",
        f"- SKUs skip (<14 días): {skus_short}",
        f"- SKUs timeout (>30s): {skus_timeout}",
        f"- SKUs error: {skus_error}",
        f"- SKUs sin evaluación (holdout<7d): {skus_no_eval}",
        f"- Total predicciones: {total_predictions}",
        "",
        "---",
        "",
        "## Configuration",
        "",
        f"- Top SKUs: {TOP_N}",
        f"- Horizons: {', '.join(str(h) for h in HORIZONS)} days",
        f"- Seasonality: yearly + weekly",
        f"- Model version: {MODEL_VERSION}",
        f"- Fit timeout: {FIT_TIMEOUT_SEC}s",
        "",
        "---",
        "",
        "## Global Metrics",
        "",
        "| Métrica | Valor | SKUs |",
        "|---------|-------|------|",
    ]

    for h in HORIZONS:
        val = {"7d": mape_7d, "14d": mape_14d, "30d": mape_30d}[f"{h}d"]
        count = len(agg_mape.get(h, []))
        lines.append(
            f"| MAPE {h}d | {val}% | {count} |" if val is not None
            else f"| MAPE {h}d | N/A | {count} |"
        )

    lines.append(
        f"| MAPE global | {overall_mape}% | {len(all_vals)} |"
        if overall_mape is not None
        else "| MAPE global | N/A | 0 |"
    )

    # Baseline comparison
    baseline_mape = 43.7
    if overall_mape is not None:
        if overall_mape < baseline_mape:
            lines.append(
                f"| V-M1 (vs baseline {baseline_mape}%) | ✅ PASS ({overall_mape}% < {baseline_mape}%) | |"
            )
        else:
            lines.append(
                f"| V-M1 (vs baseline {baseline_mape}%) | ❌ FAIL ({overall_mape}% >= {baseline_mape}%) | |"
            )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Results by SKU (top 50 por MAPE)",
            "",
            "| SKU | MAPE 7d | MAPE 14d | MAPE 30d | Demanda Total |",
            "|-----|---------|----------|----------|---------------|",
        ]
    )

    for sku, m7, m14, m30 in sku_rows_sorted:
        demand = sku_demand_map.get(sku, 0)
        lines.append(
            f"| {sku} | {m7 if m7 is not None else '-'}% | "
            f"{m14 if m14 is not None else '-'}% | "
            f"{m30 if m30 is not None else '-'}% | {demand} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## MLflow",
            "",
            f"- Experiment: {mlflow.get_experiment_by_name('motoshop-forecast').experiment_id if mlflow.get_experiment_by_name('motoshop-forecast') else 'motoshop-forecast'}",
            f"- Run ID: {run_id}",
            f"- Tracking URI: file:{REPO_ROOT}/mlruns",
            "",
            "---",
            "",
            "## Notas",
            "",
            "- Prophet se entrena con yearly_seasonality=True y weekly_seasonality=True",
            "- Changepoint_prior_scale se ajusta según cantidad de datos",
            "- Evaluación MAPE: holdout de últimos 30 días (o máximo posible con >=14 días de train)",
            "- V-M1: MAPE global debe ser < 43.7% (baseline de backtest)",
        ]
    )

    content = "\n".join(lines)
    with open(out_path, "w") as f:
        f.write(content)

    print(f"   Evidencia escrita en {out_path}")


if __name__ == "__main__":
    main()
