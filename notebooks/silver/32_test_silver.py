-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 32 · Tests de datos reales — Silver
-- MAGIC
-- MAGIC 15 assertions SQL contra datos reales en Databricks.
-- MAGIC Cada test que falla genera un error visible.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V1 · Duplicados

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  'FAIL: fact_ventas tiene duplicados'
) AS test_v1_fact_ventas
FROM motoshop.silver.fact_ventas;

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  'FAIL: fact_compras tiene duplicados'
) AS test_v1_fact_compras
FROM motoshop.silver.fact_compras;

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT STRUCT(id_inventario, business_date)),
  'FAIL: fact_inventario tiene duplicados'
) AS test_v1_fact_inventario
FROM motoshop.silver.fact_inventario;

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT cod_producto),
  'FAIL: dim_producto tiene duplicados'
) AS test_v1_dim_producto
FROM motoshop.silver.dim_producto;

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT nit_tercero),
  'FAIL: dim_tercero tiene duplicados'
) AS test_v1_dim_tercero
FROM motoshop.silver.dim_tercero;

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT cod_formapago),
  'FAIL: dim_formapago tiene duplicados'
) AS test_v1_dim_formapago
FROM motoshop.silver.dim_formapago;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V2 · Fechas

-- COMMAND ----------

SELECT assert_true(
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0,
  'FAIL: fact_ventas tiene fechas futuras'
) AS test_v2_fact_ventas
FROM motoshop.silver.fact_ventas;

-- COMMAND ----------

SELECT assert_true(
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0,
  'FAIL: fact_compras tiene fechas futuras'
) AS test_v2_fact_compras
FROM motoshop.silver.fact_compras;

-- COMMAND ----------

SELECT assert_true(
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0,
  'FAIL: fact_inventario tiene fechas futuras'
) AS test_v2_fact_inventario
FROM motoshop.silver.fact_inventario;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Montos no negativos

-- COMMAND ----------

SELECT assert_true(
  SUM(CASE WHEN total_factura < 0 THEN 1 ELSE 0 END) = 0,
  'FAIL: fact_ventas tiene totales negativos'
) AS test_negative_total_ventas
FROM motoshop.silver.fact_ventas;

-- COMMAND ----------

SELECT assert_true(
  SUM(CASE WHEN total_compra < 0 THEN 1 ELSE 0 END) = 0,
  'FAIL: fact_compras tiene totales negativos'
) AS test_negative_total_compras
FROM motoshop.silver.fact_compras;

-- COMMAND ----------

SELECT assert_true(
  SUM(CASE WHEN cantidad < 0 THEN 1 ELSE 0 END) = 0,
  'FAIL: fact_inventario tiene cantidades negativas'
) AS test_negative_cantidad
FROM motoshop.silver.fact_inventario;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## PK dim_tiempo

-- COMMAND ----------

SELECT assert_true(
  COUNT(*) = COUNT(DISTINCT business_date),
  'FAIL: dim_tiempo tiene duplicados'
) AS test_v1_dim_tiempo
FROM motoshop.silver.dim_tiempo;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Reconciliación V3

-- COMMAND ----------

WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
),
bv AS (
  SELECT COALESCE(SUM(CAST(totfven AS DOUBLE)), 0) AS t
  FROM motoshop.bronze.facventas, last_month p
  WHERE estfven = 'A' AND CAST(fecfven AS DATE) >= ms AND CAST(fecfven AS DATE) <= me
),
sv AS (
  SELECT COALESCE(SUM(total_factura), 0) AS t
  FROM motoshop.silver.fact_ventas, last_month p
  WHERE business_date >= ms AND business_date <= me
)
SELECT assert_true(
  ABS(bv.t - sv.t) / NULLIF(bv.t, 0) < 0.005,
  CONCAT('FAIL: diff=', CAST(ABS(bv.t - sv.t) AS STRING), ' (', CAST(ROUND(ABS(bv.t - sv.t) / NULLIF(bv.t, 0) * 100, 2) AS STRING), '%)')
) AS test_v3_reconciliation
FROM bv, sv;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## PKs no nulas

-- COMMAND ----------

SELECT assert_true(
  (SELECT COUNT(*) FROM motoshop.silver.fact_ventas WHERE num_documento IS NULL OR business_date IS NULL) = 0,
  'FAIL: fact_ventas tiene PKs nulas'
) AS test_null_pks;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Resumen de conteos

-- COMMAND ----------

SELECT
  (SELECT COUNT(*) FROM motoshop.silver.dim_producto) AS dim_producto,
  (SELECT COUNT(*) FROM motoshop.silver.dim_bodega) AS dim_bodega,
  (SELECT COUNT(*) FROM motoshop.silver.dim_tercero) AS dim_tercero,
  (SELECT COUNT(*) FROM motoshop.silver.dim_sucursal) AS dim_sucursal,
  (SELECT COUNT(*) FROM motoshop.silver.dim_formapago) AS dim_formapago,
  (SELECT COUNT(*) FROM motoshop.silver.dim_tiempo) AS dim_tiempo,
  (SELECT COUNT(*) FROM motoshop.silver.fact_ventas) AS fact_ventas,
  (SELECT COUNT(*) FROM motoshop.silver.fact_ventas_detalle) AS fact_ventas_det,
  (SELECT COUNT(*) FROM motoshop.silver.fact_compras) AS fact_compras,
  (SELECT COUNT(*) FROM motoshop.silver.fact_compras_detalle) AS fact_compras_det,
  (SELECT COUNT(*) FROM motoshop.silver.fact_inventario) AS fact_inventario;
