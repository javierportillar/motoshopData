# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · dim_producto — SCD Type 1 desde bronze.productos

# COMMAND ----------

-- MAGIC %sql

CREATE OR REPLACE TABLE motoshop.silver.dim_producto AS
SELECT
  TRIM(codprod)        AS cod_producto,
  TRIM(nomprod)        AS nombre_producto,
  TRIM(codbar)         AS codigo_barras,
  TRIM(unimed)         AS unidad_medida,
  TRIM(codmed)         AS cod_medida,
  CAST(valmed AS DOUBLE)    AS valor_medida,
  TRIM(presen)         AS presentacion,
  CAST(stockmin AS DOUBLE)  AS stock_minimo,
  CAST(stockmax AS DOUBLE)  AS stock_maximo,
  CAST(exiprod AS DOUBLE)   AS existencia,
  CAST(cosprod AS DOUBLE)   AS costo_producto,
  CAST(cosulc AS DOUBLE)    AS costo_ultima_compra,
  CAST(pvsini AS DOUBLE)    AS precio_venta_sin_iva,
  CAST(pvconi AS DOUBLE)    AS precio_venta_con_iva,
  TRIM(actprod)        AS estado_producto,
  TRIM(codpor)         AS cod_grupo,
  TRIM(codlin1)        AS cod_linea1,
  TRIM(desprod)        AS descripcion,
  TRIM(nitter)         AS nit_proveedor,
  TRIM(codbod)         AS cod_bodega_default,
  CAST(fecapa AS DATE)      AS fecha_actualizacion,
  CURRENT_DATE()             AS snapshot_date
FROM motoshop.bronze.productos
WHERE codprod IS NOT NULL;

# COMMAND ----------

-- MAGIC %sql

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT cod_producto) AS distintos,
  COUNT(*) - COUNT(DISTINCT cod_producto) AS duplicados
FROM motoshop.silver.dim_producto;

# COMMAND ----------

-- MAGIC %sql

SELECT COUNT(*) AS dim_producto_rows FROM motoshop.silver.dim_producto;
