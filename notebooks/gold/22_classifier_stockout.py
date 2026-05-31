-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 22 · Classifier Stockout — DDL + Validación
-- MAGIC
-- MAGIC Crea la tabla gold.alertas_quiebre y valúa esquema.
-- MAGIC Poblada por infra/run_classifier_stockout.py (B-4).
-- MAGIC
-- MAGIC Schema alineado con AlertItem de F4-C API.

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
-- MAGIC ## Validación de esquema

-- COMMAND ----------

DESCRIBE motoshop.gold.alertas_quiebre;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Validación: tabla vacía post-DDL

-- COMMAND ----------

SELECT COUNT(*) AS filas FROM motoshop.gold.alertas_quiebre;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Validación: columnas requeridas

-- COMMAND ----------

SELECT
  COUNT(*) AS total_columns,
  SUM(CASE WHEN column_name = 'sku' THEN 1 ELSE 0 END) AS has_sku,
  SUM(CASE WHEN column_name = 'urgencia' THEN 1 ELSE 0 END) AS has_urgencia,
  SUM(CASE WHEN column_name = 'dias_hasta_quiebre' THEN 1 ELSE 0 END) AS has_dias,
  SUM(CASE WHEN column_name = 'business_date' THEN 1 ELSE 0 END) AS has_partition
FROM motoshop.information_schema.columns
WHERE table_catalog = 'motoshop'
  AND table_schema = 'gold'
  AND table_name = 'alertas_quiebre';
