-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 20 · Forecast Prophet SKU
-- MAGIC
-- MAGIC DDL para la tabla de predicciones del modelo Prophet.
-- MAGIC Los datos se insertan desde infra/run_forecast_prophet.py vía Databricks SQL.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_prophet_sku (
  sku STRING,
  forecast_date DATE,
  horizon INT,
  predicted_qty DOUBLE,
  confidence_lower DOUBLE,
  confidence_upper DOUBLE,
  model_version STRING,
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
  MIN(forecast_date) AS min_fecha,
  MAX(forecast_date) AS max_fecha
FROM motoshop.gold.forecast_prophet_sku;

-- COMMAND ----------

SELECT * FROM motoshop.gold.forecast_prophet_sku LIMIT 10;

-- COMMAND ----------

SELECT
  horizon,
  COUNT(*) AS cnt,
  ROUND(AVG(predicted_qty), 2) AS avg_pred,
  ROUND(AVG(confidence_lower), 2) AS avg_ci_lower,
  ROUND(AVG(confidence_upper), 2) AS avg_ci_upper
FROM motoshop.gold.forecast_prophet_sku
GROUP BY horizon
ORDER BY horizon;
