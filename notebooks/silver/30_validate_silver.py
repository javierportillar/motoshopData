-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 30 · Validate Silver — V1 (duplicados) + V2 (fechas inválidas)

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V1 · ¿Hay duplicados en silver?

-- COMMAND ----------

SELECT
  'fact_ventas' AS tabla,
  COUNT(*) AS filas,
  COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS distintas,
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS duplicadas,
  CASE WHEN COUNT(*) = COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) THEN 'PASS' ELSE 'FAIL' END AS status
FROM motoshop.silver.fact_ventas

UNION ALL

SELECT
  'fact_ventas_detalle',
  COUNT(*), COUNT(DISTINCT STRUCT(num_documento, cod_clase, cod_producto, num_item, business_date)),
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, cod_producto, num_item, business_date)),
  CASE WHEN COUNT(*) = COUNT(DISTINCT STRUCT(num_documento, cod_clase, cod_producto, num_item, business_date)) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.fact_ventas_detalle

UNION ALL

SELECT
  'fact_compras',
  COUNT(*), COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)),
  CASE WHEN COUNT(*) = COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.fact_compras

UNION ALL

SELECT
  'fact_compras_detalle',
  COUNT(*), COUNT(DISTINCT STRUCT(num_documento, cod_clase, cod_producto, num_item, business_date)),
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, cod_producto, num_item, business_date)),
  CASE WHEN COUNT(*) = COUNT(DISTINCT STRUCT(num_documento, cod_clase, cod_producto, num_item, business_date)) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.fact_compras_detalle

UNION ALL

SELECT
  'fact_inventario',
  COUNT(*), COUNT(DISTINCT STRUCT(id_inventario, business_date)),
  COUNT(*) - COUNT(DISTINCT STRUCT(id_inventario, business_date)),
  CASE WHEN COUNT(*) = COUNT(DISTINCT STRUCT(id_inventario, business_date)) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.fact_inventario;

-- COMMAND ----------

SELECT
  'dim_producto' AS tabla,
  COUNT(*) AS filas,
  COUNT(DISTINCT cod_producto) AS distintas,
  COUNT(*) - COUNT(DISTINCT cod_producto) AS duplicadas,
  CASE WHEN COUNT(*) = COUNT(DISTINCT cod_producto) THEN 'PASS' ELSE 'FAIL' END AS status
FROM motoshop.silver.dim_producto

UNION ALL

SELECT 'dim_bodega', COUNT(*), COUNT(DISTINCT cod_bodega), COUNT(*) - COUNT(DISTINCT cod_bodega),
  CASE WHEN COUNT(*) = COUNT(DISTINCT cod_bodega) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.dim_bodega

UNION ALL

SELECT 'dim_tercero', COUNT(*), COUNT(DISTINCT nit_tercero), COUNT(*) - COUNT(DISTINCT nit_tercero),
  CASE WHEN COUNT(*) = COUNT(DISTINCT nit_tercero) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.dim_tercero

UNION ALL

SELECT 'dim_formapago', COUNT(*), COUNT(DISTINCT cod_formapago), COUNT(*) - COUNT(DISTINCT cod_formapago),
  CASE WHEN COUNT(*) = COUNT(DISTINCT cod_formapago) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.dim_formapago

UNION ALL

SELECT 'dim_tiempo', COUNT(*), COUNT(DISTINCT business_date), COUNT(*) - COUNT(DISTINCT business_date),
  CASE WHEN COUNT(*) = COUNT(DISTINCT business_date) THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.dim_tiempo;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V2 · ¿Las fechas inválidas se descartan?

-- COMMAND ----------

SELECT
  'fact_ventas' AS tabla,
  SUM(CASE WHEN business_date IS NULL THEN 1 ELSE 0 END) AS nulas,
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) AS futuras,
  CASE WHEN SUM(CASE WHEN business_date IS NULL OR business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM motoshop.silver.fact_ventas

UNION ALL

SELECT
  'fact_compras',
  SUM(CASE WHEN business_date IS NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END),
  CASE WHEN SUM(CASE WHEN business_date IS NULL OR business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.fact_compras

UNION ALL

SELECT
  'fact_inventario',
  SUM(CASE WHEN business_date IS NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END),
  CASE WHEN SUM(CASE WHEN business_date IS NULL OR business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.silver.fact_inventario;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Conteos por tabla

-- COMMAND ----------

SELECT 'fact_ventas' AS tabla, COUNT(*) AS rows_silver FROM motoshop.silver.fact_ventas
UNION ALL SELECT 'fact_ventas_detalle', COUNT(*) FROM motoshop.silver.fact_ventas_detalle
UNION ALL SELECT 'fact_compras', COUNT(*) FROM motoshop.silver.fact_compras
UNION ALL SELECT 'fact_compras_detalle', COUNT(*) FROM motoshop.silver.fact_compras_detalle
UNION ALL SELECT 'fact_inventario', COUNT(*) FROM motoshop.silver.fact_inventario
UNION ALL SELECT 'dim_producto', COUNT(*) FROM motoshop.silver.dim_producto
UNION ALL SELECT 'dim_bodega', COUNT(*) FROM motoshop.silver.dim_bodega
UNION ALL SELECT 'dim_tercero', COUNT(*) FROM motoshop.silver.dim_tercero
UNION ALL SELECT 'dim_sucursal', COUNT(*) FROM motoshop.silver.dim_sucursal
UNION ALL SELECT 'dim_formapago', COUNT(*) FROM motoshop.silver.dim_formapago
UNION ALL SELECT 'dim_tiempo', COUNT(*) FROM motoshop.silver.dim_tiempo;
