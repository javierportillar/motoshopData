-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 02 · dim_bodega — SCD Type 1 desde bronze.bodegas

-- COMMAND ----------

CREATE OR REPLACE TABLE motoshop.silver.dim_bodega AS
SELECT
  TRIM(codbod)   AS cod_bodega,
  TRIM(nombod)   AS nombre_bodega,
  TRIM(telbod)   AS telefono,
  TRIM(ubibod)   AS ubicacion,
  TRIM(resbod)   AS responsable,
  CURRENT_DATE() AS snapshot_date
FROM motoshop.bronze.bodegas
WHERE codbod IS NOT NULL;

-- COMMAND ----------

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT cod_bodega) AS distintos,
  COUNT(*) - COUNT(DISTINCT cod_bodega) AS duplicados
FROM motoshop.silver.dim_bodega;

-- COMMAND ----------

SELECT COUNT(*) AS dim_bodega_rows FROM motoshop.silver.dim_bodega;
