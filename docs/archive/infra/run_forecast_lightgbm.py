"""
LightGBM demand forecasting for MotoShop — F4-B.

Predicts demand for horizons 7, 14, 30 days recursively,
logs metrics to MLflow, and writes results to gold.forecast_lightgbm_sku.

Usage:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_forecast_lightgbm.py

Requires: requests, lightgbm, pandas, numpy, mlflow (optional)
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:
    print("❌ requests no instalado. Ejecutá: pip install requests")
    sys.exit(1)

try:
    import lightgbm as lgb
except ImportError:
    print("❌ lightgbm no instalado. Ejecutá: pip install lightgbm")
    sys.exit(1)

try:
    import mlflow
    import mlflow.tracking
    HAS_MLFLOW = True
except ImportError:
    print("⚠️ mlflow no instalado. Se omitirá logging a MLflow.")
    HAS_MLFLOW = False

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
MODEL_VERSION = "lightgbm_v1"

TRAIN_SPLIT_DATE = "2025-12-31"

# Feature columns from gold.feature_store_sku (without target)
BASE_FEATURES = [
    "lag_7d", "lag_14d", "lag_28d",
    "media_movil_7d", "media_movil_14d", "media_movil_28d",
    "dia_semana", "mes", "es_festivo",
    "stock_actual", "dias_sin_venta",
]


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
        print(f"  ❌ SQL failed — {description}")
        return False
    return True


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
                f"/api/2.0/sql/statements/{statement_id}",
                f"Poll {description}",
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

    if not columns:
        columns = [f"col_{i}" for i in range(len(data_array[0]))] if data_array else []

    rows = []
    for row in data_array:
        row_dict = {}
        for i, col in enumerate(columns):
            val = row[i] if i < len(row) else None
            row_dict[col] = val
        rows.append(row_dict)
    return rows


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


def safe_float(val) -> float:
    """Convert to float, default 0."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


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

    # ── 0. Crear tabla si no existe ──────────────────────────────────────
    ddl = """CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_lightgbm_sku (
  sku STRING,
  forecast_date DATE,
  horizon INT,
  predicted_qty DOUBLE,
  confidence_lower DOUBLE,
  confidence_upper DOUBLE,
  model_version STRING,
  business_date DATE
) USING DELTA PARTITIONED BY (business_date)"""
    execute_sql(ddl, "Create forecast_lightgbm_sku")
    print("   Tabla lista.")

    # ── 1. Cargar gold.feature_store_sku ─────────────────────────────────
    print("\n1. Cargando gold.feature_store_sku...")
    rows = query_databricks(
        """
        SELECT
            cod_producto,
            business_date,
            demanda_diaria,
            lag_7d,
            lag_14d,
            lag_28d,
            media_movil_7d,
            media_movil_14d,
            media_movil_28d,
            dia_semana,
            mes,
            es_festivo,
            stock_actual,
            dias_sin_venta,
            categoria_abc
        FROM motoshop.gold.feature_store_sku
        ORDER BY cod_producto, business_date
        """,
        "Load feature store",
    )

    if not rows:
        print("❌ No se pudieron cargar datos de gold.feature_store_sku")
        sys.exit(1)

    print(f"   → {len(rows)} filas cargadas")

    # ── 2. Convertir a pandas ────────────────────────────────────────────
    print("\n2. Preparando datos...")
    df = pd.DataFrame(rows)

    # Parsear fechas
    df["business_date"] = pd.to_datetime(df["business_date"])

    # Columnas numéricas
    float_cols = [
        "demanda_diaria", "lag_7d", "lag_14d", "lag_28d",
        "media_movil_7d", "media_movil_14d", "media_movil_28d",
        "stock_actual",
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    int_cols = ["dia_semana", "mes", "dias_sin_venta"]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # es_festivo puede venir como string "true"/"false" o booleano
    df["es_festivo"] = df["es_festivo"].astype(str).str.lower().map(
        {"true": 1, "false": 0, "1": 1, "0": 0}
    ).fillna(0).astype(int)

    df["categoria_abc"] = df["categoria_abc"].fillna("C").astype(str)

    # ── 3. Feature engineering ───────────────────────────────────────────
    print("\n3. Feature engineering...")

    # Drop rows where target es nulo
    before = len(df)
    df = df.dropna(subset=["demanda_diaria"]).copy()
    print(f"   Filas después de drop target null: {before} → {len(df)}")

    # Fill NaN features con 0
    fill_cols = float_cols + int_cols
    for col in fill_cols:
        df[col] = df[col].fillna(0)

    df["dia_semana"] = df["dia_semana"].astype(int)
    df["mes"] = df["mes"].astype(int)
    df["dias_sin_venta"] = df["dias_sin_venta"].astype(int)

    # One-hot encode categoria_abc
    cat_dummies = pd.get_dummies(df["categoria_abc"], prefix="categoria_abc")
    cat_cols = sorted(cat_dummies.columns.tolist())
    df = pd.concat([df, cat_dummies.astype(int)], axis=1)

    feature_cols = BASE_FEATURES + cat_cols

    print(f"   Features: {len(BASE_FEATURES)} base + {len(cat_cols)} one-hot = {len(feature_cols)}")
    print(f"   Categorías ABC: {[c.replace('categoria_abc_', '') for c in cat_cols]}")

    # Shift target: predecir demanda del día siguiente (shift -1 por SKU)
    df = df.sort_values(["cod_producto", "business_date"]).reset_index(drop=True)
    df["target"] = df.groupby("cod_producto")["demanda_diaria"].shift(-1)
    df = df.dropna(subset=["target"]).copy()
    print(f"   Filas después de shift target: {len(df)}")

    # ── 4. Temporal split ────────────────────────────────────────────────
    print("\n4. Temporal split...")
    split_ts = pd.Timestamp(TRAIN_SPLIT_DATE)

    train_df = df[df["business_date"] <= split_ts].copy()
    test_df = df[df["business_date"] > split_ts].copy()

    print(f"   Train: {len(train_df)} filas (≤ {TRAIN_SPLIT_DATE})")
    print(f"   Test:  {len(test_df)} filas (≥ 2026-01-01)")

    skus_in_train = train_df["cod_producto"].nunique()
    skus_in_test = test_df["cod_producto"].nunique()
    print(f"   SKUs en train: {skus_in_train}")
    print(f"   SKUs en test:  {skus_in_test}")

    if len(train_df) < 100:
        print("❌ Datos de entrenamiento insuficientes")
        sys.exit(1)

    X_train = train_df[feature_cols].values
    y_train = train_df["target"].values
    X_test = test_df[feature_cols].values
    y_test = test_df["target"].values

    # ── 5. Entrenar LightGBM ─────────────────────────────────────────────
    print("\n5. Entrenando LightGBM...")

    model = lgb.LGBMRegressor(
        objective="regression",
        metric="mape",
        num_leaves=31,
        learning_rate=0.05,
        n_estimators=500,
        random_state=42,
        verbose=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        eval_names=["test"],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(50)],
    )

    best_iter = model.best_iteration_
    print(f"   Best iteration: {best_iter}")

    # ── 6. Feature importance ────────────────────────────────────────────
    print("\n6. Feature importance analysis...")
    importance = model.feature_importances_
    feat_imp = sorted(
        zip(feature_cols, importance), key=lambda x: x[1], reverse=True
    )

    print("   Top-10 features:")
    for name, imp in feat_imp[:10]:
        print(f"     {name}: {imp}")

    # ── 7. Residuals for confidence intervals ────────────────────────────
    print("\n7. Calculating residuals for confidence intervals...")
    y_train_pred = model.predict(X_train)
    residuals = y_train - y_train_pred
    residual_std = np.std(residuals)
    print(f"   Residual std: {residual_std:.4f}")
    print(f"   95% CI margin: {1.96 * residual_std:.4f}")

    # ── 8. Recursive multi-step forecasting ──────────────────────────────
    print("\n8. Recursive multi-step forecasting (horizons 1-30)...")

    # Group data by SKU
    train_by_sku = {
        sku: grp.sort_values("business_date")
        for sku, grp in train_df.groupby("cod_producto")
    }

    # test_df: rows with business_date > split_ts (actual test data for comparison)
    test_actuals_by_sku = {}
    for sku, grp in test_df.groupby("cod_producto"):
        s = grp.set_index("business_date")["demanda_diaria"]
        test_actuals_by_sku[sku] = s[~s.index.duplicated(keep="last")]

    # SKUs that have training data — we'll forecast for these
    all_skus = sorted(train_by_sku.keys())
    print(f"   Forecasting for {len(all_skus)} SKUs...")

    forecast_records = []  # for INSERT into gold.forecast_lightgbm_sku
    horizon_actuals: dict[int, list[float]] = defaultdict(list)
    horizon_preds: dict[int, list[float]] = defaultdict(list)

    for idx, sku in enumerate(all_skus):
        if (idx + 1) % 200 == 0:
            print(f"   → {idx + 1}/{len(all_skus)} SKUs procesados...")

        sku_train = train_by_sku[sku]

        # Last training row — this row has features_at_T and target = demand_at_T+1
        last_row = sku_train.iloc[-1]
        last_feature_date = last_row["business_date"]

        # Build a series of ALL known demand values for this SKU
        # (training data only — test data is NOT included)
        combined_demand = sku_train.set_index("business_date")["demanda_diaria"].copy()
        # Deduplicate index — same SKU can have multiple rows per date
        combined_demand = combined_demand[~combined_demand.index.duplicated(keep="last")]
        # Also include the target of the last row (which is demand at last_feature_date+1)
        # Actually, the last row's target = demand at last_feature_date+1
        # We don't have this in combined_demand yet — it's what we want to predict.

        # Get actuals from test period for MAPE comparison
        sku_test_actuals = test_actuals_by_sku.get(sku, pd.Series(dtype=float))

        # State variables for recursive forecast
        last_stock = safe_float(last_row.get("stock_actual", 0))
        dias_sin_venta = int(last_row.get("dias_sin_venta", 0) or 0)
        last_cat = str(last_row.get("categoria_abc", "C"))

        for step in range(1, 31):
            # ── Build feature vector ──

            if step == 1:
                # Step 1: Use the last training row's features directly
                # Model: features_at_T → demand_at_T+1
                feat_vec = last_row[feature_cols].values.reshape(1, -1)

            else:
                # Steps 2+: compute features at T+step-1
                # Model: features_at_T+step-1 → demand_at_T+step
                feat_date = last_feature_date + timedelta(days=step - 1)
                feat = {}

                # Lag features: look back from feat_date
                for lag_days, lag_name in [
                    (7, "lag_7d"), (14, "lag_14d"), (28, "lag_28d"),
                ]:
                    lookback = feat_date - timedelta(days=lag_days)
                    if lookback in combined_demand.index:
                        vals_at_lb = combined_demand.loc[lookback]
                        if isinstance(vals_at_lb, pd.Series):
                            feat[lag_name] = float(vals_at_lb.iloc[0])
                        else:
                            feat[lag_name] = float(vals_at_lb)
                    else:
                        feat[lag_name] = 0.0

                # Moving averages: trailing window ending at feat_date-1
                for window, mm_name in [
                    (7, "media_movil_7d"),
                    (14, "media_movil_14d"),
                    (28, "media_movil_28d"),
                ]:
                    vals = []
                    for d in range(1, window + 1):
                        lb = feat_date - timedelta(days=d)
                        if lb in combined_demand.index:
                            v_at_lb = combined_demand.loc[lb]
                            if isinstance(v_at_lb, pd.Series):
                                vals.append(float(v_at_lb.iloc[0]))
                            else:
                                vals.append(float(v_at_lb))
                    feat[mm_name] = sum(vals) / len(vals) if vals else 0.0

                # Calendar features
                feat["dia_semana"] = feat_date.weekday()  # 0=Monday
                feat["mes"] = feat_date.month
                feat["es_festivo"] = 0  # default, no tenemos datos futuros

                # Stock and days without sales
                feat["stock_actual"] = last_stock
                feat["dias_sin_venta"] = dias_sin_venta

                # One-hot category
                for col in cat_cols:
                    feat[col] = 0
                cat_key = f"categoria_abc_{last_cat}"
                if cat_key in cat_cols:
                    feat[cat_key] = 1

                feat_vec = np.array([[feat[col] for col in feature_cols]])

            # ── Predict ──
            pred = model.predict(feat_vec)[0]
            pred = max(0.0, pred)  # demanda no negativa

            pred_date = last_feature_date + timedelta(days=step)

            # Store prediction in combined series for future feature computation
            combined_demand.loc[pred_date] = pred

            # Update state
            if pred == 0:
                dias_sin_venta += 1
            else:
                dias_sin_venta = 0

            # ── Confidence interval ──
            ci_margin = 1.96 * residual_std
            ci_lower = max(0.0, pred - ci_margin)
            ci_upper = pred + ci_margin

            # ── Store for horizons 7, 14, 30 ──
            if step in (7, 14, 30):
                forecast_records.append({
                    "sku": sku,
                    "horizon": step,
                    "forecast_date": pred_date.strftime("%Y-%m-%d"),
                    "predicted_qty": round(pred, 4),
                    "ci_lower": round(ci_lower, 4),
                    "ci_upper": round(ci_upper, 4),
                    "business_date": pred_date.strftime("%Y-%m-%d"),
                })

            # ── Compare with actuals for MAPE ──
            if pred_date in sku_test_actuals.index:
                v_at_date = sku_test_actuals.loc[pred_date]
                if isinstance(v_at_date, pd.Series):
                    actual_val = float(v_at_date.iloc[0])
                else:
                    actual_val = float(v_at_date)
                if actual_val > 0:
                    horizon_actuals[step].append(actual_val)
                    horizon_preds[step].append(pred)

    print(f"\n   Total forecast records: {len(forecast_records)}")

    # ── 9. MAPE por horizonte ────────────────────────────────────────────
    print("\n9. MAPE por horizonte...")
    horizon_metrics: dict[int, dict] = {}

    for h in [7, 14, 30]:
        actuals = horizon_actuals.get(h, [])
        preds = horizon_preds.get(h, [])

        if not actuals or not preds:
            print(f"   Horizon {h:2d}d: N/A (no se encontraron pares real vs predicho)")
            horizon_metrics[h] = {"mape": None, "smape": None, "obs": 0}
            continue

        mape_vals = []
        smape_vals = []
        for a, p in zip(actuals, preds):
            m = calc_mape(a, p)
            s = calc_smape(a, p)
            if m is not None:
                mape_vals.append(m)
            if s is not None:
                smape_vals.append(s)

        h_mape = sum(mape_vals) / len(mape_vals) if mape_vals else None
        h_smape = sum(smape_vals) / len(smape_vals) if smape_vals else None

        horizon_metrics[h] = {
            "mape": round(h_mape, 2) if h_mape else None,
            "smape": round(h_smape, 2) if h_smape else None,
            "obs": len(actuals),
        }

        if horizon_metrics[h]["mape"] is not None:
            print(
                f"   Horizon {h:2d}d: MAPE={horizon_metrics[h]['mape']}%  "
                f"sMAPE={horizon_metrics[h]['smape']}%  obs={horizon_metrics[h]['obs']}"
            )
        else:
            print(f"   Horizon {h:2d}d: N/A (sin observaciones válidas)")

    # ── 10. MLflow logging ───────────────────────────────────────────────
    print("\n10. MLflow logging...")
    mlflow_run_id = None

    if HAS_MLFLOW:
        try:
            mlflow.set_tracking_uri(f"file:{REPO_ROOT}/mlruns")
            mlflow.set_experiment("motoshop_forecast")

            with mlflow.start_run() as run:
                mlflow_run_id = run.info.run_id
                mlflow.set_tags({
                    "modelo": "lightgbm",
                    "sprint": "F4-B",
                    "fase": "F4",
                })

                # Parameters
                mlflow.log_param("model", "lightgbm")
                mlflow.log_param("num_leaves", 31)
                mlflow.log_param("learning_rate", 0.05)
                mlflow.log_param("n_estimators", 500)
                mlflow.log_param("early_stopping_rounds", 50)
                mlflow.log_param("best_iteration", int(best_iter))
                mlflow.log_param("source_table", "gold.feature_store_sku")
                mlflow.log_param("train_rows", int(len(train_df)))
                mlflow.log_param("test_rows", int(len(test_df)))
                mlflow.log_param("skus_total", int(len(all_skus)))
                mlflow.log_param("residual_std", round(residual_std, 4))
                mlflow.log_param("model_version", MODEL_VERSION)

                # Feature importance as JSON
                top_features = {name: int(imp) for name, imp in feat_imp[:10]}
                mlflow.log_param("top_features", json.dumps(top_features))

                # Metrics per horizon
                for h in [7, 14, 30]:
                    if (
                        h in horizon_metrics
                        and horizon_metrics[h]["mape"] is not None
                    ):
                        mlflow.log_metric(f"MAPE_h{h}", horizon_metrics[h]["mape"])
                        mlflow.log_metric(f"sMAPE_h{h}", horizon_metrics[h]["smape"])
                        mlflow.log_metric(f"obs_h{h}", horizon_metrics[h]["obs"])

                print(f"   ✅ MLflow run: {mlflow_run_id}")

        except Exception as e:
            print(f"   ⚠️ MLflow logging falló: {e}")
    else:
        print("   ⚠️ MLflow no disponible, omitiendo logging.")

    # ── 11. INSERT a gold.forecast_lightgbm_sku ──────────────────────────
    print("\n11. Escribiendo a gold.forecast_lightgbm_sku...")

    if not forecast_records:
        print("   ⚠️ No hay predicciones para insertar.")
    else:
        total_inserted = 0
        BATCH_SIZE = 500

        for i in range(0, len(forecast_records), BATCH_SIZE):
            batch = forecast_records[i: i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            values = []
            for rec in batch:
                sku_esc = rec["sku"].replace("'", "''")
                values.append(
                    f"('{sku_esc}', '{rec['forecast_date']}', {rec['horizon']}, "
                    f"{rec['predicted_qty']}, {rec['ci_lower']}, {rec['ci_upper']}, "
                    f"'{MODEL_VERSION}', '{rec['business_date']}')"
                )

            sql = (
                "INSERT INTO motoshop.gold.forecast_lightgbm_sku "
                "(sku, forecast_date, horizon, predicted_qty, "
                "confidence_lower, confidence_upper, model_version, business_date) "
                "VALUES\n" + ",\n".join(values)
            )

            ok = execute_sql(
                sql, f"Insert batch {batch_num}/{math.ceil(len(forecast_records) / BATCH_SIZE)}"
            )
            if ok:
                total_inserted += len(batch)
                print(f"   ✅ Batch {batch_num}: {len(batch)} filas OK")
            else:
                print(f"   ❌ Batch {batch_num} falló")

        print(f"\n   ✅ {total_inserted}/{len(forecast_records)} filas insertadas "
              f"en gold.forecast_lightgbm_sku")

    # ── 12. Evidencia ────────────────────────────────────────────────────
    print("\n12. Escribiendo evidencia...")
    _write_evidence(
        model=model,
        best_iter=best_iter,
        feature_cols=feature_cols,
        feat_imp=feat_imp,
        horizon_metrics=horizon_metrics,
        forecast_records=forecast_records,
        train_df=train_df,
        test_df=test_df,
        all_skus=all_skus,
        residual_std=residual_std,
        mlflow_run_id=mlflow_run_id,
    )

    print("\n✅ Forecast LightGBM completado.")


# ─── Evidence writer ──────────────────────────────────────────────────────


def _write_evidence(
    model: lgb.LGBMRegressor,
    best_iter: int,
    feature_cols: list[str],
    feat_imp: list[tuple[str, int]],
    horizon_metrics: dict[int, dict],
    forecast_records: list[dict],
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    all_skus: list[str],
    residual_std: float,
    mlflow_run_id: str | None,
) -> None:
    """Write evidence markdown to notebooks/gold/_runs/."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"v_forecast_lightgbm_{timestamp}.md"

    total_predictions = len(forecast_records)

    # Feature importance top 5
    top5 = feat_imp[:5]

    # Horizon table rows
    horizon_rows = []
    for h in [7, 14, 30]:
        m = horizon_metrics.get(h, {})
        if m.get("mape") is not None:
            horizon_rows.append(
                f"| {h} | {m['mape']}% | {m['smape']}% | {m['obs']} |"
            )
        else:
            horizon_rows.append(f"| {h} | N/A | N/A | 0 |")

    # Global MAPE = average across horizons
    mape_vals = [
        v["mape"] for v in horizon_metrics.values()
        if v["mape"] is not None
    ]
    avg_mape = round(sum(mape_vals) / len(mape_vals), 2) if mape_vals else None

    # One-step test MAPE (quick eval)
    test_df_clean = test_df.dropna(subset=feature_cols + ["target"])
    if len(test_df_clean) > 0:
        y_test_pred = model.predict(test_df_clean[feature_cols].values)
        test_mape_vals = []
        for a, p in zip(test_df_clean["target"].values, y_test_pred):
            m = calc_mape(float(a), float(p))
            if m is not None:
                test_mape_vals.append(m)
        test_mape = round(sum(test_mape_vals) / len(test_mape_vals), 2) if test_mape_vals else "N/A"
    else:
        test_mape = "N/A"

    lines = [
        f"# Forecast LightGBM — {timestamp}",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Training rows | {len(train_df)} |",
        f"| Test rows | {len(test_df)} |",
        f"| SKUs in forecast | {len(all_skus)} |",
        f"| Total predictions | {total_predictions} |",
        f"| MAPE global (avg h7/14/30) | {avg_mape}% |" if avg_mape is not None else "| MAPE global (avg h7/14/30) | N/A |",
        f"| Test MAPE (one-step) | {test_mape} |",
        f"| Residual std (CI) | {residual_std:.4f} |",
        f"| Baseline MAPE (F4-A naive) | 43.72% |",
        "",
        "---",
        "",
        "## Configuration",
        "",
        "| Parámetro | Valor |",
        "|-----------|-------|",
        "| num_leaves | 31 |",
        "| learning_rate | 0.05 |",
        "| n_estimators | 500 |",
        "| early_stopping_rounds | 50 |",
        f"| best_iteration | {best_iter} |",
        f"| model_version | {MODEL_VERSION} |",
        f"| Total features | {len(feature_cols)} |",
        "",
        "---",
        "",
        "## Results by Horizon",
        "",
        "| Horizon | MAPE | sMAPE | Obs |",
        "|---------|------|-------|-----|",
    ]

    lines.extend(horizon_rows)

    lines.extend([
        "",
        "---",
        "",
        "## Feature Importance (Top 10)",
        "",
        "| Feature | Importance |",
        "|---------|-----------|",
    ])

    for name, imp in feat_imp[:10]:
        lines.append(f"| {name} | {imp} |")

    lines.extend([
        "",
        "---",
        "",
        "## Verification (V-M2)",
        "",
    ])

    if avg_mape is not None and avg_mape < 43.72:
        lines.append(
            f"✅ **LightGBM MAPE ({avg_mape}%) < 43.7% (baseline naive) — PASÓ.**"
        )
        lines.append("")
        lines.append(f"Mejora de {43.72 - avg_mape}pp sobre el baseline.")
    else:
        lines.append(
            f"❌ **LightGBM MAPE ({avg_mape}%) no es menor que 43.7% (baseline) — revisar.**"
            if avg_mape is not None
            else "❌ **No se pudo calcular MAPE global — revisar.**"
        )

    lines.extend([
        "",
        "---",
        "",
        "## MLflow",
        "",
    ])

    if mlflow_run_id:
        mlflow_url = (
            f"{DATABRICKS_HOST}/ml/experiments/-1/runs/{mlflow_run_id}"
        )
        lines.extend([
            f"**Run ID:** {mlflow_run_id}",
            f"**URL:** {mlflow_url}",
            "",
            "### Metrics logged",
            "| Métrica | Valor |",
            "|---------|-------|",
        ])
        for h in [7, 14, 30]:
            m = horizon_metrics.get(h, {})
            if m.get("mape") is not None:
                lines.append(f"| MAPE_h{h} | {m['mape']}% |")
                lines.append(f"| sMAPE_h{h} | {m['smape']}% |")
    else:
        lines.append("⚠️ MLflow no disponible o falló el logging.")

    content = "\n".join(lines)
    with open(out_path, "w") as f:
        f.write(content)

    print(f"   ✅ Evidencia escrita en {out_path}")


if __name__ == "__main__":
    main()
