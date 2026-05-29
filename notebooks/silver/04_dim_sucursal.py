-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 04 · dim_sucursal — SCD Type 1 desde bronze.sucursales

-- COMMAND ----------

CREATE OR REPLACE TABLE motoshop.silver.dim_sucursal AS
SELECT
  TRIM(codsuc)    AS cod_sucursal,
  TRIM(nitter)    AS nit_tercero,
  TRIM(nomsuc)    AS nombre_sucursal,
  TRIM(dirsuc)    AS direccion,
  TRIM(telsuc)    AS telefono,
  TRIM(movsuc)    AS movil,
  TRIM(nomrut)    AS nombre_ruta,
  TRIM(nomzon)    AS nombre_zona,
  TRIM(inasuc)    AS inactiva,
  TRIM(codciu)    AS cod_ciudad,
  TRIM(codest)    AS cod_establecimiento,
  TRIM(codcat)    AS cod_categoria,
  TRIM(corele)    AS email,
  TRIM(tiposuc)   AS tipo_sucursal,
  CURRENT_DATE()  AS snapshot_date
FROM motoshop.bronze.sucursales
WHERE codsuc IS NOT NULL;

-- COMMAND ----------

SELECT COUNT(*) AS dim_sucursal_rows FROM motoshop.silver.dim_sucursal;
