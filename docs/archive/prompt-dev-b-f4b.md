# Prompt Dev B · Sprint F4-B · Data Engineering (FIX + DDLs + Classifier + Tests)

```
Soy Dev B · Track B (Data Engineering) para F4-B del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f4-b.md COMPLETO
4. Leé SEGUIMIENTO.md §Fase 4
5. Verificá que sqlparse esté instalado:
   python -c "import sqlparse; print('OK')"

CONTEXTO:
- Feature store listo: gold.feature_store_sku (34,838 filas, 4,392 SKUs)
- forecast_baseline_sku está VACÍA por SQL syntax error — MI FIX es PRIORITARIO
- Dev A necesita forecast_baseline_sku para A-3 (evaluación)
- Los scripts corren en Mac O Windows

MI MISIÓN:
FIX el baseline, crear DDLs, entrenar classifier, escribir tests.

TAREAS (en orden):

### B-1: FIX 16_forecast_baseline_sku.py (PRIORITARIO)
Archivo: notebooks/gold/16_forecast_baseline_sku.py

PROBLEMA: PARSE_SYNTAX_ERROR en INSERT OVERWRITE ... PARTITION (business_date) WITH ...
CAUSA: Databricks serverless no acepta CTEs con WITH dentro de INSERT OVERWRITE PARTITION.

FIX: Separar en temporary view + INSERT:
```sql
-- Paso 1
CREATE OR REPLACE TEMPORARY VIEW baseline_calc AS
WITH
demanda_diaria AS (
  SELECT business_date, cod_producto, SUM(cantidad_total) AS demanda
  FROM motoshop.gold.mart_ventas_diarias_sku
  GROUP BY business_date, cod_producto
),
... (resto del CTE)
SELECT * FROM con_fallback JOIN naive_seasonal USING (...);

-- Paso 2
INSERT OVERWRITE motoshop.gold.forecast_baseline_sku
PARTITION (business_date)
SELECT * FROM baseline_calc;
```

VERIFICACIÓN: Ejecutar en Databricks y confirmar que COUNT(*) > 0.

### B-2: DDL forecast_demanda_sku
Archivo: notebooks/gold/24_forecast_demanda_sku_ddl.sql

```sql
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
) USING DELTA PARTITIONED BY (business_date);
```

### B-3: DDL alertas_quiebre
Archivo: notebooks/gold/25_alertas_quiebre_ddl.sql

```sql
CREATE TABLE IF NOT EXISTS motoshop.gold.alertas_quiebre (
  sku STRING,
  nom_producto STRING,
  stock_actual DOUBLE,
  demanda_predicha DOUBLE,
  dias_hasta_quiebre DOUBLE,
  urgencia STRING,
  business_date DATE
) USING DELTA PARTITIONED BY (business_date);
```

### B-4: Clasificador de quiebre
Archivo: infra/run_classifier_stockout.py

1. Leer gold.feature_store_sku + gold.mart_inventario_actual
2. Label: quiebre=1 si stock_actual < media_movil_7d * 0.5
3. Features: mismas que LightGBM + stock_actual + dias_sin_venta
4. Split: stratified (70/30)
5. LGBMClassifier(objective="binary", metric="binary_logloss", is_unbalance=True, num_leaves=31, lr=0.05, n_estimators=300)
6. Evaluar: F1, precision, recall
7. Clasificar urgencia:
   - dias_hasta_quiebre = stock_actual / media_movil_7d
   - ≤ 7 → alta, ≤ 14 → media, > 14 → baja
8. MLflow: tags modelo=lightgbm_classifier metric=F1
9. Escribir a gold.alertas_quiebre

Notebook: notebooks/gold/22_classifier_stockout.py — solo CREATE TABLE + validación

### B-5: Tests
Archivo: tests/gold/test_forecasts.py

Tests sqlparse para notebooks 20/21/22/23:
- CREATE TABLE presente
- Columnas correctas
- INSERT OVERWRITE particionado
- Validación SELECTs

Tests unitarios para run_classifier_stockout.py:
- Clasificación de urgencia correcta
- 0 negative forecasts

### B-6: Orquestador + Evidencia
Archivo: infra/run_all_f4b.py

Script que ejecuta todo en orden:
1. FIX baseline (via Databricks SQL)
2. Prophet (via run_forecast_prophet.py de Dev A)
3. LightGBM (via run_forecast_lightgbm.py de Dev A)
4. Evaluate (via run_evaluate_models.py de Dev A)
5. Classifier (via run_classifier_stockout.py)
6. Resumen + métricas

Evidencia:
- notebooks/gold/_runs/v_classifier_stockout_<ts>.md
- notebooks/gold/_runs/v_forecast_baseline_fix_<ts>.md

VERIFICACIÓN OBLIGATORIA:
- forecast_baseline_sku tiene > 0 filas (V-M0)
- Classifier F1 > 0.7 (V-M3)
- alertas_quiebre tiene registros con urgencia (V-M5)
- Tests pasan: pytest tests/gold/test_forecasts.py (V-M7)

LO QUE NO TOCO:
- infra/run_forecast_prophet.py (Dev A)
- infra/run_forecast_lightgbm.py (Dev A)
- infra/run_evaluate_models.py (Dev A)
- notebooks/silver/** (intacto)
- motoshop-app/** (Track T no participa)
- Credenciales / .env

COMMITS:
- prefijo: feat(F4-B-de): ...

ARRANQUE:
Empezá por B-1 (FIX baseline) — es PRIORITARIO porque Dev A lo necesita para A-3.
Después B-2 + B-3 (DDLs, rápidos).
Después B-4 (Classifier).
Al final B-5 (Tests) + B-6 (Evidencia + run_all_f4b.py).
```
