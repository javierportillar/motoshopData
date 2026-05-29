# Databricks notebook source
# MAGIC %md
# MAGIC # 12 · fact_compras — desde bronze.compras
# MAGIC
# MAGIC `business_date` de `feccom`. Solo activos (`estcom = 'A'`).

# COMMAND ----------

-- MAGIC %sql

CREATE OR REPLACE TABLE motoshop.silver.fact_compras AS
SELECT
  TRIM(numcom)        AS num_documento,
  TRIM(codclas)       AS cod_clase,
  TRIM(precom)        AS prefijo,
  CAST(feccom AS TIMESTAMP)  AS fecha_documento_ts,
  CAST(feccom AS DATE)       AS business_date,
  TRIM(nitter)        AS nit_proveedor,
  TRIM(procom)        AS nombre_proveedor,
  TRIM(codsuc)        AS cod_sucursal,
  TRIM(codpag)        AS cod_formapago,
  CAST(subcom AS DOUBLE)     AS subtotal,
  CAST(totdct AS DOUBLE)     AS total_descuentos,
  CAST(totiva AS DOUBLE)     AS total_iva,
  CAST(totipo AS DOUBLE)     AS total_impuesto,
  CAST(retfte AS DOUBLE)     AS retencion_fuente,
  CAST(retiva AS DOUBLE)     AS retencion_iva,
  CAST(retica AS DOUBLE)     AS retencion_ica,
  CAST(totcom AS DOUBLE)     AS total_compra,
  TRIM(obscom)        AS observaciones,
  TRIM(estcom)        AS estado_documento,
  TRIM(codemp)        AS cod_empresa,
  TRIM(empcod)        AS cod_empresa_alt,
  TRIM(nitvend)       AS nit_vendedor,
  CURRENT_DATE()      AS ingest_date_silver
FROM motoshop.bronze.compras
WHERE estcom = 'A'
  AND feccom IS NOT NULL
  AND CAST(feccom AS DATE) >= DATE '2020-01-01'
  AND CAST(feccom AS DATE) <= CURRENT_DATE();

# COMMAND ----------

-- MAGIC %sql

SELECT COUNT(*) AS fact_compras_rows FROM motoshop.silver.fact_compras;

# COMMAND ----------

-- MAGIC %sql

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS distintos,
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS duplicados
FROM motoshop.silver.fact_compras;

# COMMAND ----------

-- MAGIC %sql

SELECT * FROM motoshop.silver.fact_compras LIMIT 10;
