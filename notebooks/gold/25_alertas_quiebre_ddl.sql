-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 25 · DDL alertas_quiebre
-- MAGIC
-- MAGIC Tabla gold con alertas de quiebre de stock por SKU.
-- MAGIC Poblada por B-4 (run_classifier_stockout.py).
-- MAGIC Consumida por F4-C API: GET /alerts/stockout
-- MAGIC
-- MAGIC Schema alineado con AlertItem / AlertsResponse de motoshop_api.alerts.schemas.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.alertas_quiebre (
  sku STRING,
  nom_producto STRING,
  stock_actual DOUBLE,
  demanda_predicha DOUBLE,
  dias_hasta_quiebre DOUBLE,
  urgencia STRING,
  business_date DATE
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Validación

-- COMMAND ----------

DESCRIBE motoshop.gold.alertas_quiebre;

-- COMMAND ----------

SELECT * FROM motoshop.gold.alertas_quiebre LIMIT 10;
