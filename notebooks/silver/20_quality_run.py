-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 20 · Quality Run — Reglas de calidad silver
-- MAGIC
-- MAGIC Valida cada tabla silver y escribe resultados a `silver._quality_runs`.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.silver._quality_runs (
  run_id STRING,
  table_name STRING,
  rule STRING,
  failed_rows BIGINT,
  severity STRING,
  timestamp TIMESTAMP
) USING DELTA;

-- COMMAND ----------

DELETE FROM motoshop.silver._quality_runs
WHERE DATE(timestamp) = CURRENT_DATE();

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## fact_ventas

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
WHERE num_documento IS NULL OR cod_clase IS NULL OR business_date IS NULL
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'negative_total_factura', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
WHERE total_factura < 0
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
HAVING (COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date))) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## fact_compras

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
WHERE num_documento IS NULL OR cod_clase IS NULL OR business_date IS NULL
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'negative_total_compra', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
WHERE total_compra < 0
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
HAVING (COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date))) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## fact_inventario

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_inventario', 'negative_cantidad', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_inventario
WHERE cantidad < 0
HAVING COUNT(*) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_inventario', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_inventario
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Dimensiones: PK duplicada

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_producto', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_producto), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_producto
HAVING (COUNT(*) - COUNT(DISTINCT cod_producto)) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_bodega', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_bodega), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_bodega
HAVING (COUNT(*) - COUNT(DISTINCT cod_bodega)) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_tercero', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT nit_tercero), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_tercero
HAVING (COUNT(*) - COUNT(DISTINCT nit_tercero)) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_sucursal', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_sucursal), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_sucursal
HAVING (COUNT(*) - COUNT(DISTINCT cod_sucursal)) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_formapago', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_formapago), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_formapago
HAVING (COUNT(*) - COUNT(DISTINCT cod_formapago)) > 0;

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_tiempo', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT business_date), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_tiempo
HAVING (COUNT(*) - COUNT(DISTINCT business_date)) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Resumen

-- COMMAND ----------

SELECT table_name, rule, failed_rows, severity, timestamp
FROM motoshop.silver._quality_runs
WHERE DATE(timestamp) = CURRENT_DATE()
ORDER BY severity DESC, table_name;
