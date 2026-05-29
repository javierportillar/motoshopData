-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 20 · Quality Run — Reglas de calidad silver
-- MAGIC
-- MAGIC Valida cada tabla silver. Si hay reglas CRITICAL, el notebook falla.

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
-- MAGIC ## Helper: registrar resultado

-- COMMAND ----------

-- Se usa una tabla temporal para acumular resultados de esta corrida
CREATE OR REPLACE TEMPORARY VIEW _qr_results AS
SELECT
  CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd')) AS run_id,
  '' AS table_name,
  '' AS rule,
  0L AS failed_rows,
  '' AS severity,
  CURRENT_TIMESTAMP() AS timestamp
WHERE FALSE;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## fact_ventas: checks

-- COMMAND ----------

-- PK nula
INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
WHERE num_documento IS NULL OR cod_clase IS NULL OR business_date IS NULL
HAVING COUNT(*) > 0;

-- Totales negativos
INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'negative_total_factura', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
WHERE total_factura < 0
HAVING COUNT(*) > 0;

-- Fechas futuras
INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

-- Duplicados
INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_ventas
HAVING (COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date))) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## fact_compras: checks

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
WHERE num_documento IS NULL OR cod_clase IS NULL OR business_date IS NULL
HAVING COUNT(*) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'negative_total_compra', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
WHERE total_compra < 0
HAVING COUNT(*) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_compras
HAVING (COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date))) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## fact_inventario: checks

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_inventario', 'negative_cantidad', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_inventario
WHERE cantidad < 0
HAVING COUNT(*) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_inventario', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.silver.fact_inventario
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Completeness checks (Silver ≅ Bronze)

-- COMMAND ----------

-- fact_ventas completeness: silver ≈ bronze (≤1% difference in row count)
-- tolerancia amplia (1%) para cubrir casos donde Bronze tenga outliers de fecha
INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_ventas', 'silver_completeness', CAST(ABS(b.n - s.n) AS BIGINT), 'CRITICAL', CURRENT_TIMESTAMP()
FROM (
  SELECT COUNT(*) AS n FROM motoshop.bronze.facventas
  WHERE estfven IN ('A','B')
    AND fecfven IS NOT NULL
    AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
    AND CAST(fecfven AS DATE) <= CURRENT_DATE()
) b,
(
  SELECT COUNT(*) AS n FROM motoshop.silver.fact_ventas
) s
WHERE ABS(b.n - s.n) * 1.0 / NULLIF(b.n, 0) > 0.01;

-- fact_compras completeness
INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'fact_compras', 'silver_completeness', CAST(ABS(b.n - s.n) AS BIGINT), 'CRITICAL', CURRENT_TIMESTAMP()
FROM (
  SELECT COUNT(*) AS n FROM motoshop.bronze.compras
  WHERE estcom IN ('A','B')
    AND feccom IS NOT NULL
    AND CAST(feccom AS DATE) >= DATE '2020-01-01'
    AND CAST(feccom AS DATE) <= CURRENT_DATE()
) b,
(
  SELECT COUNT(*) AS n FROM motoshop.silver.fact_compras
) s
WHERE ABS(b.n - s.n) * 1.0 / NULLIF(b.n, 0) > 0.01;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Dimensions: PK duplicadaensiones: PK duplicada

-- COMMAND ----------

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_producto', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_producto), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_producto
HAVING (COUNT(*) - COUNT(DISTINCT cod_producto)) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_bodega', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_bodega), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_bodega
HAVING (COUNT(*) - COUNT(DISTINCT cod_bodega)) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_tercero', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT nit_tercero), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_tercero
HAVING (COUNT(*) - COUNT(DISTINCT nit_tercero)) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_sucursal', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_sucursal), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_sucursal
HAVING (COUNT(*) - COUNT(DISTINCT cod_sucursal)) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_formapago', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT cod_formapago), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_formapago
HAVING (COUNT(*) - COUNT(DISTINCT cod_formapago)) > 0;

INSERT INTO motoshop.silver._quality_runs
SELECT CONCAT('qr_', DATE_FORMAT(CURRENT_DATE(), 'yyyyMMdd'), '_', CAST(FLOOR(RAND() * 10000) AS STRING)),
  'dim_tiempo', 'duplicate_pk',
  COUNT(*) - COUNT(DISTINCT business_date), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.silver.dim_tiempo
HAVING (COUNT(*) - COUNT(DISTINCT business_date)) > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## ASSERT: fallar si hay errores CRITICAL

-- COMMAND ----------

SELECT assert_true(
  (SELECT COUNT(*) FROM motoshop.silver._quality_runs WHERE severity = 'CRITICAL' AND DATE(timestamp) = CURRENT_DATE()) = 0,
  CONCAT('Quality run encontró ', CAST((SELECT COUNT(*) FROM motoshop.silver._quality_runs WHERE severity = 'CRITICAL' AND DATE(timestamp) = CURRENT_DATE()) AS STRING), ' errores CRITICAL')
) AS assert_no_critical_errors;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Resumen

-- COMMAND ----------

SELECT table_name, rule, failed_rows, severity, timestamp
FROM motoshop.silver._quality_runs
WHERE DATE(timestamp) = CURRENT_DATE()
ORDER BY severity DESC, table_name;
