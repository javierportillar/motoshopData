# Plan F4-B · Modelos ML + Clasificador Quiebre

- **Fecha apertura:** 2026-05-29
- **Origen:** cierre F4-A con feature store (34,838 filas, 4,392 SKUs) + MLflow configurado
- **Modo:** **paralelo · 2 devs** (Dev A = ML, Dev B = Data Engineering)
- **Duración estimada:** 8-12 h totales (~4-6 h por dev)
- **Estado:** 🟡 ABIERTA.

---

## 1 · Contexto post-F4-A

| Dato | Valor | Fuente |
|------|-------|--------|
| Feature store filas | 34,838 | `v_feature_store_20260529_223702.md` |
| Feature store SKUs | 4,392 | misma evidencia |
| Baseline MAPE | **43.7%** | `v_mlflow_baseline_20260529_174222.md` |
| Baseline sMAPE | 59.91% | misma evidencia |
| Baseline WAPE | 45.81% | misma evidencia |
| MLflow | ✅ Experimento registrado | Run ID `55071d05...` |
| `forecast_baseline_sku` | ⚠️ **Tabla vacía** — SQL syntax error en INSERT OVERWRITE | `v_feature_store_20260529_223702.md` línea 37 |

### ⚠️ Fix prioritario

`16_forecast_baseline_sku.py` falla con `PARSE_SYNTAX_ERROR` al hacer `INSERT OVERWRITE ... PARTITION (business_date) WITH ...`. La tabla `forecast_baseline_sku` tiene 0 filas. **Este fix es prerequisito** para que la evaluación comparativa (V-M1) pueda ejecutarse.

---

## 2 · Distribución de trabajo

### Track A · Dev ML (Prophet + LightGBM + Evaluate)

| # | Tarea | Archivo | Dependencia |
|---|-------|---------|-------------|
| A-1 | Prophet top-100 SKUs | `notebooks/gold/20_forecast_prophet.py` | feature_store_sku |
| A-2 | LightGBM global | `notebooks/gold/21_forecast_lightgbm.py` | feature_store_sku |
| A-3 | Evaluación comparativa | `notebooks/gold/23_evaluate_models.py` | A-1, A-2, B-1 |

### Track B · Dev Data Engineering (FIX + DDLs + Classifier + Tests)

| # | Tarea | Archivo | Dependencia |
|---|-------|---------|-------------|
| B-1 | **FIX** baseline SQL | `notebooks/gold/16_forecast_baseline_sku.py` | Ninguna |
| B-2 | DDL `forecast_demanda_sku` | `notebooks/gold/24_forecast_demanda_sku_ddl.sql` | Ninguna |
| B-3 | DDL `alertas_quiebre` | `notebooks/gold/25_alertas_quiebre_ddl.sql` | Ninguna |
| B-4 | Clasificador quiebre | `notebooks/gold/22_classifier_stockout.py` | feature_store_sku, B-2, B-3 |
| B-5 | Tests | `tests/gold/test_forecasts.py` | A-1, A-2, A-3, B-4 |
| B-6 | Evidencia | `notebooks/gold/_runs/v_forecast_*_<ts>.md` | Todos |

### Diagrama de dependencias

```
                    ┌─────────────┐
                    │ feature_    │
                    │ store_sku   │
                    │ (F4-A) ✅   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │                         │
        ┌─────┴─────┐           ┌──────┴──────┐
        │  Dev A    │           │   Dev B     │
        │           │           │             │
        │ A-1: Pro- │           │ B-1: FIX    │
        │ phet top  │           │ baseline    │
        │ 100       │           │ (PRIORITARIO│
        │           │           │             │
        │ A-2: Light│           │ B-2: DDL    │
        │ GMB global│           │ forecast_   │
        │           │           │ demanda_sku │
        │           │           │             │
        │           │           │ B-3: DDL    │
        │           │           │ alertas_    │
        │           │           │ quiebre     │
        │           │           │             │
        │           │           │ B-4: Classi-│
        │           │           │ fier stockout
        └─────┬─────┘           └──────┬──────┘
              │                         │
              └────────────┬────────────┘
                           │
                    ┌──────┴──────┐
                    │   Dev A     │
                    │             │
                    │ A-3: Evalua-│
                    │ ción +      │
                    │ comparación │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │   Dev B     │
                    │             │
                    │ B-5: Tests  │
                    │ B-6: Eviden-│
                    │ cia         │
                    └─────────────┘
```

---

## 3 · Detalle técnico por tarea

### B-1 · FIX `16_forecast_baseline_sku.py` (PRIORITARIO)

**Problema:** `PARSE_SYNTAX_ERROR` en `INSERT OVERWRITE ... PARTITION (business_date) WITH ...`

**Causa:** Databricks SQL Warehouse (serverless) no acepta CTEs con `WITH` dentro de `INSERT OVERWRITE ... PARTITION`.

**Fix:** Separar en temporary view + INSERT:

```sql
-- Paso 1: crear vista temporal con el cálculo
CREATE OR REPLACE TEMPORARY VIEW baseline_calc AS
WITH
demanda_diaria AS (
  SELECT business_date, cod_producto, SUM(cantidad_total) AS demanda
  FROM motoshop.gold.mart_ventas_diarias_sku
  GROUP BY business_date, cod_producto
),
... (resto del CTE)
SELECT * FROM con_fallback JOIN naive_seasonal USING (...);

-- Paso 2: insertar desde la vista
INSERT OVERWRITE motoshop.gold.forecast_baseline_sku
PARTITION (business_date)
SELECT * FROM baseline_calc;
```

**Verificación:** `SELECT COUNT(*) FROM forecast_baseline_sku` debe ser > 0.

---

### A-1 · Prophet top-100 SKUs

**Lógica:**
1. Leer `gold.feature_store_sku`
2. Top-100 por `SUM(demanda_diaria)` agrupado por `cod_producto`
3. Para cada SKU:
   - Preparar: `ds` = business_date, `y` = demanda_diaria
   - Si < 30 días de datos: `changepoint_prior_scale=0.05`
   - Entrenar: `yearly_seasonality=True`, `weekly_seasonality=True`
   - Predecir: horizon 7, 14, 30 días
   - Confidence interval: `yhat_lower`, `yhat_upper`
4. Guardar en `gold.forecast_prophet_sku`
5. MLflow: `mlflow.log_metric("MAPE", ...)`, tags `modelo=prophet, sprint=F4-B`

**Edge cases:**
- SKU con demanda 0 todos los días → skip
- SKU con < 14 días → usar `changepoint_prior_scale=0.01`
- Timeout fitting: 30s max por SKU

**Output:** `gold.forecast_prophet_sku` (misma estructura que forecast_demanda_sku)

---

### A-2 · LightGBM global

**Lógica:**
1. Leer `gold.feature_store_sku`
2. Features: lag_7d, lag_14d, lag_28d, media_movil_7d/14d/28d, dia_semana, mes, stock_actual, dias_sin_venta, categoria_abc
3. Target: `demanda_diaria` del día siguiente (shift -1)
4. Split temporal: train ≤ 2025-12, test ≥ 2026-01
5. Entrenar:
   ```python
   lgb.LGBMRegressor(
       objective="regression",
       metric="mape",
       num_leaves=31,
       learning_rate=0.05,
       n_estimators=500,
       early_stopping_rounds=50,
   )
   ```
6. Predecir 7/14/30 días recursivamente
7. Guardar en `gold.forecast_lightgbm_sku`
8. MLflow: tags `modelo=lightgbm, sprint=F4-B`

---

### A-3 · Evaluación comparativa

**Lógica:**
1. Leer las 3 tablas: `forecast_baseline_sku`, `forecast_prophet_sku`, `forecast_lightgbm_sku`
2. Para cada modelo y SKU:
   - MAPE = `AVG(ABS(real - pred) / real) * 100`
   - sMAPE = `AVG(2*ABS(real-pred)/(real+pred)) * 100`
   - WAPE = `SUM(ABS(real-pred)) / SUM(real) * 100`
3. Seleccionar mejor modelo por SKU (menor MAPE)
4. Materializar predicciones finales en `gold.forecast_demanda_sku`
5. MLflow: registrar comparación completa

**Output:** `gold.forecast_demanda_sku` (la tabla que F4-C consume)

---

### B-4 · Clasificador de quiebre

**Lógica:**
1. Leer `gold.feature_store_sku` + `gold.mart_inventario_actual`
2. Label: `quiebre = 1` si `stock_actual < media_movil_7d * 0.5` (o 0 si no hay media_movi7d y stock = 0)
3. Features: mismas que LightGBM + stock_actual + dias_sin_venta
4. Split: stratified (70/30)
5. Entrenar:
   ```python
   lgb.LGBMClassifier(
       objective="binary",
       metric="binary_logloss",
       is_unbalance=True,
       num_leaves=31,
       learning_rate=0.05,
       n_estimators=300,
   )
   ```
6. Evaluar: F1, precision, recall
7. Predecir para todos los SKUs con inventario
8. Clasificar urgencia:
   - `dias_hasta_quiebre = stock_actual / media_movil_7d`
   - ≤ 7 días → alta
   - ≤ 14 días → media
   - > 14 días → baja
9. Guardar en `gold.alertas_quiebre`
10. MLflow: tags `modelo=lightgbm_classifier, metric=F1`

---

### B-5 · Tests

**Archivo:** `tests/gold/test_forecasts.py`

Tests sqlparse para:
- `20_forecast_prophet.py`: CREATE TABLE, columnas, INSERT OVERWRITE
- `21_forecast_lightgbm.py`: CREATE TABLE, columnas, INSERT OVERWRITE
- `23_evaluate_models.py`: CREATE TABLE, lógica de selección
- `22_classifier_stockout.py`: CREATE TABLE, urgencia logic, clasificación

Patrón: mismo que `tests/gold/test_feature_store.py`

---

## 4 · Tablas output

### `gold.forecast_prophet_sku`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| sku | STRING | Código producto |
| forecast_date | DATE | Fecha de la predicción |
| horizon | INT | 7, 14, 30 |
| predicted_qty | DOUBLE | Cantidad predicha |
| confidence_lower | DOUBLE | Límite inferior IC |
| confidence_upper | DOUBLE | Límite superior IC |
| model_version | STRING | ej. "prophet-v1" |
| business_date | DATE | Partition key |

### `gold.forecast_lightgbm_sku`

Misma estructura que prophet.

### `gold.forecast_demanda_sku` (tabla consolidada)

| Columna | Tipo | Descripción |
|---------|------|-------------|
| sku | STRING | Código producto |
| forecast_date | DATE | Fecha de la predicción |
| horizon | INT | 7, 14, 30 |
| predicted_qty | DOUBLE | Mejor predicción (min MAPE) |
| confidence_lower | DOUBLE | IC inferior |
| confidence_upper | DOUBLE | IC superior |
| model_version | STRING | "prophet-v1" o "lightgbm-v1" |
| mape | DOUBLE | MAPE del modelo seleccionado |
| smape | DOUBLE | sMAPE del modelo seleccionado |
| business_date | DATE | Partition key |

### `gold.alertas_quiebre`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| sku | STRING | Código producto |
| nom_producto | STRING | Nombre |
| stock_actual | DOUBLE | Stock actual |
| demanda_predicha | DOUBLE | Demanda 7d predicha |
| dias_hasta_quiebre | DOUBLE | stock / demanda_diaria |
| urgencia | STRING | alta/media/baja |
| business_date | DATE | Partition key |

---

## 5 · V-checks

| ID | Verificación | Pass criterion | Track |
|----|-------------|----------------|-------|
| V-M0 | Baseline fix funciona | `forecast_baseline_sku` tiene > 0 filas | B |
| V-M1 | Prophet supera baseline | MAPE Prophet < 43.7% para top-100 | A |
| V-M2 | LightGBM supera baseline | MAPE LightGBM < 43.7% global | A |
| V-M3 | Classifier F1 | F1 > 0.7 en holdout | B |
| V-M4 | `forecast_demanda_sku` poblada | ≥ 100 SKUs con predicciones | A |
| V-M5 | `alertas_quiebre` poblada | Registros con urgencia alta/media/baja | B |
| V-M6 | Sanity check | 0 negative forecasts, 0 null SKU | B |
| V-M7 | Tests pasan | `pytest tests/gold/test_forecasts.py` verde | B |
| V-M8 | MLflow registrado | ≥ 3 experimentos (prophet, lightgbm, classifier) | A+B |

---

## 6 · Stack

| Componente | Tecnología | Notas |
|------------|-----------|-------|
| Prophet | `prophet` | pip install en Mac |
| LightGBM | `lightgbm` | pip install en Mac |
| ML tracking | MLflow | Remote tracking en Databricks |
| HPO (futuro) | Optuna | No en F4-B; posible en F6 |
| Tests | pytest + sqlparse | Patrón existente |

### Instalación previa

```bash
# En la Mac
pip install prophet lightgbm mlflow
```

---

## 7 · Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|----|--------|-------|---------|------------|
| R-B1 | Prophet no supera baseline (43.7%) | Media | Alto | LightGBM puede superar por features cross-SKU. Si ambos fallan: ensemble promedio |
| R-B2 | SQL syntax error persiste | Baja | Alto | FIX B-1 ya identificado: temporary view + INSERT |
| R-B3 | LightGBM overfitting | Media | Medio | early_stopping_rounds=50, val_fraction=0.2 |
| R-B4 | Classifier clases desbalanceadas | Alta | Medio | is_unbalance=True + umbral ajustable |
| R-B5 | Prophet lento (100 SKUs × ~30s) | Baja | Bajo | 50 min total, aceptable |
| R-B6 | Mac no tiene prophet instalado | Baja | Medio | `pip install prophet` antes de arrancar |

---

## 8 · Orden de ejecución

```
INICIO PARALELO (ambos devs arrancan al mismo tiempo)
│
├── Dev B: B-1 (FIX baseline) ← PRIORITARIO, ~30 min
├── Dev B: B-2 + B-3 (DDLs) ← ~15 min
├── Dev A: A-1 (Prophet) ← ~2-3 h
├── Dev A: A-2 (LightGBM) ← ~1-2 h
│
├── Dev B: B-4 (Classifier) ← ~2 h
│
├── Dev A: A-3 (Evaluate + comparación) ← requiere A-1, A-2, B-1
│
├── Dev B: B-5 (Tests) ← ~1 h
├── Dev B: B-6 (Evidencia) ← ~30 min
│
└── REVISOR: Validar V-M0 a V-M8
```

**Total estimado:** 8-12 h, 2 sesiones con 2 devs.

---

## 9 · Preguntas para el humano

1. **¿Prophet se instala en la Mac actual?** Requiere `pip install prophet` (~500MB). Si no hay espacio/network, alternativa: Databricks serverless notebooks (pero tiempo limitado).
2. **¿El label del classifier es aceptado como sintético?** Hoy es `stock < demanda*0.5`. Si se necesita validación con datos reales de quiebre, hay que definir cómo se obtienen.
3. **¿Se hace HPO con Optuna en F4-B o se deja para F6?** Si no, los hiperparámetros quedan fijos (num_leaves=31, lr=0.05, n_estimators=500).

---

## 10 · Próximo paso del revisor

1. Aprobar plan F4-B.
2. Dev B ejecuta B-1 (FIX baseline) primero.
3. Revisor valida V-M0.
4. Ambos devs arrancan en paralelo.
5. Revisor valida V-M1 a V-M8 al cierre.
