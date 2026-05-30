-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 33 · Archive forecasts — gold.forecast_demanda_sku → gold.forecast_demanda_sku_archive
-- MAGIC
-- MAGIC Guarda copia íntegra de `forecast_demanda_sku` ANTES de que el workflow
-- MAGIC la sobrescriba con `INSERT OVERWRITE` en la corrida siguiente.
-- MAGIC Cada fila recibe `archived_at = CURRENT_TIMESTAMP()`.
-- MAGIC
-- MAGIC **Schedule:** inmediatamente ANTES de `23_evaluate_models` en el workflow.
-- MAGIC **Balde B:** alimenta F3 (backtesting visual: predicho vs real) en dashboards/forecast.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · DDL — gold.forecast_demanda_sku_archive

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_demanda_sku_archive (
  sku STRING,
  forecast_date DATE,
  horizon INT,
  predicted_qty DOUBLE,
  confidence_lower DOUBLE,
  confidence_upper DOUBLE,
  model_version STRING,
  mape DOUBLE,
  smape DOUBLE,
  business_date DATE,
  archived_at TIMESTAMP
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · INSERT — copia completa con timestamp de archive

-- COMMAND ----------

INSERT INTO motoshop.gold.forecast_demanda_sku_archive
SELECT
  f.sku,
  f.forecast_date,
  f.horizon,
  f.predicted_qty,
  f.confidence_lower,
  f.confidence_upper,
  f.model_version,
  f.mape,
  f.smape,
  f.business_date,
  CURRENT_TIMESTAMP() AS archived_at
FROM motoshop.gold.forecast_demanda_sku f;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación — archivos acumulados

-- COMMAND ----------

SELECT
  DATE_TRUNC('HOUR', archived_at) AS archive_hour,
  model_version,
  COUNT(*) AS filas,
  COUNT(DISTINCT sku) AS skus
FROM motoshop.gold.forecast_demanda_sku_archive
GROUP BY DATE_TRUNC('HOUR', archived_at), model_version
ORDER BY archive_hour DESC
LIMIT 20;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Último archive vs tabla actual (sanity check)

-- COMMAND ----------

SELECT 'archive' AS origen, COUNT(*) AS filas
FROM motoshop.gold.forecast_demanda_sku_archive
WHERE archived_at = (
  SELECT MAX(archived_at)
  FROM motoshop.gold.forecast_demanda_sku_archive
)
UNION ALL
SELECT 'forecast_actual', COUNT(*)
FROM motoshop.gold.forecast_demanda_sku;
