# Prompt Dev A · Sprint F4-B · ML (Prophet + LightGBM + Evaluate)

```
Soy Dev A · Track A (ML) para F4-B del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f4-b.md COMPLETO
4. Leé SEGUIMIENTO.md §Fase 4
5. Verificá que Prophet y LightGBM estén instalados:
   python -c "import prophet; import lightgbm; import mlflow; print('OK')"
   Si falta algo: pip install prophet lightgbm mlflow pandas databricks-sql-connector

CONTEXTO:
- Feature store listo: gold.feature_store_sku (34,838 filas, 4,392 SKUs)
- Baseline MAPE: 43.7% — DEBO superar esto
- MLflow configurado en Databricks workspace
- .env tiene DATABRICKS_HOST + DATABRICKS_TOKEN
- Los scripts corren en Mac O Windows (lee/escribe Databricks vía SQL)

MI MISIÓN:
Crear 3 scripts Python en infra/ que entrenen modelos de forecasting
y escriban predicciones a Databricks Gold tables.

TAREAS (en orden):

### A-1: Prophet top-100 SKUs
Archivo: infra/run_forecast_prophet.py

1. Conectar a Databricks vía databricks-sql-connector
2. Leer gold.feature_store_sku a pandas
3. Top-100 SKUs por SUM(demanda_diaria)
4. Para cada SKU:
   - ds = business_date, y = demanda_diaria
   - Prophet(yearly_seasonality=True, weekly_seasonality=True)
   - Si < 30 días: changepoint_prior_scale=0.05
   - Predecir 7/14/30 días
   - Guardar predicted_qty, confidence_lower, confidence_upper
5. MLflow: mlflow.log_metric("MAPE", value), tags modelo=prophet sprint=F4-B
6. Escribir a gold.forecast_prophet_sku via Databricks SQL

Edge cases:
- SKU con demanda 0 todos los días → skip
- SKU con < 14 días → changepoint_prior_scale=0.01
- Timeout 30s max por SKU

### A-2: LightGBM global
Archivo: infra/run_forecast_lightgbm.py

1. Leer gold.feature_store_sku
2. Features: lag_7d, lag_14d, lag_28d, media_movil_7d/14d/28d, dia_semana, mes, stock_actual, dias_sin_venta, categoria_abc
3. Target: demanda_diaria del día siguiente (shift -1)
4. Split: train ≤ 2025-12, test ≥ 2026-01
5. LGBMRegressor(objective="regression", metric="mape", num_leaves=31, lr=0.05, n_estimators=500, early_stopping_rounds=50)
6. Predecir 7/14/30 días recursivamente
7. MLflow: tags modelo=lightgbm sprint=F4-B
8. Escribir a gold.forecast_lightgbm_sku

### A-3: Evaluación comparativa
Archivo: infra/run_evaluate_models.py

1. Leer forecast_baseline_sku, forecast_prophet_sku, forecast_lightgbm_sku
2. Calcular MAPE/sMAPE/WAPE por modelo y SKU
3. Seleccionar mejor modelo por SKU (menor MAPE)
4. Materializar en gold.forecast_demanda_sku (la tabla que F4-C ya consume)
5. MLflow: registrar comparación completa

NOTA: A-3 depende de B-1 (FIX baseline). Si forecast_baseline_sku sigue vacía,
usar solo prophet vs lightgbm para la selección.

Notebooks Databricks:
- notebooks/gold/20_forecast_prophet.py — solo CREATE TABLE + validación SELECTs
- notebooks/gold/21_forecast_lightgbm.py — solo CREATE TABLE + validación
- notebooks/gold/23_evaluate_models.py — solo CREATE TABLE + validación

EVIDENCIA:
- notebooks/gold/_runs/v_forecast_prophet_<ts>.md
- notebooks/gold/_runs/v_forecast_lightgbm_<ts>.md
- notebooks/gold/_runs/v_model_evaluation_<ts>.md

VERIFICACIÓN OBLIGATORIA:
- Prophet MAPE < 43.7% para top-100 SKUs (V-M1)
- LightGBM MAPE < 43.7% global (V-M2)
- forecast_demanda_sku tiene ≥ 100 SKUs (V-M4)
- MLflow tiene ≥ 2 experimentos nuevos (V-M8)

LO QUE NO TOCO:
- notebooks/gold/16_forecast_baseline_sku.py (Dev B hace el FIX)
- notebooks/silver/** (intacto)
- motoshop-app/** (Track T no participa)
- Credenciales / .env

COMMITS:
- prefijo: feat(F4-B-ml): ...

ARRANQUE:
Empezá por A-1 (Prophet). Cuando termine, A-2 (LightGBM).
Después A-3 (Evaluate) — esperá a que Dev B cierre B-1 si necesitás baseline.
```
