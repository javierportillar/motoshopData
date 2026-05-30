-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 23 · Evaluate Models
-- MAGIC
-- MAGIC DDL para la tabla consolidada de demanda forecast.
-- MAGIC Los datos se insertan desde infra/run_evaluate_models.py vía Databricks SQL.

-- COMMAND ----------

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

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS total_predicciones,
  COUNT(DISTINCT sku) AS skus_unicos,
  COLLECT_SET(horizon) AS horizontes,
  COLLECT_SET(model_version) AS modelos,
  MIN(forecast_date) AS min_fecha,
  MAX(forecast_date) AS max_fecha
FROM motoshop.gold.forecast_demanda_sku;

-- COMMAND ----------

SELECT * FROM motoshop.gold.forecast_demanda_sku LIMIT 10;

-- COMMAND ----------

SELECT
  model_version,
  COUNT(DISTINCT sku) AS skus,
  ROUND(AVG(mape), 2) AS avg_mape,
  ROUND(AVG(smape), 2) AS avg_smape
FROM motoshop.gold.forecast_demanda_sku
GROUP BY model_version;
