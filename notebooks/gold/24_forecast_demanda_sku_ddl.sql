-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 24 · DDL forecast_demanda_sku
-- MAGIC
-- MAGIC Tabla gold con predicciones de demanda por SKU y horizonte.
-- MAGIC Poblada por notebooks 20 (Prophet) y 21 (LightGBM) de Dev A.
-- MAGIC Consumida por F4-C API: GET /forecast/{sku}?horizon=N
-- MAGIC
-- MAGIC Schema alineado con ForecastItem / ForecastResponse de motoshop_api.forecast.schemas.

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

DESCRIBE motoshop.gold.forecast_demanda_sku;

-- COMMAND ----------

SELECT * FROM motoshop.gold.forecast_demanda_sku LIMIT 10;
