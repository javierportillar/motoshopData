# Databricks notebook source
# MAGIC %md
# MAGIC # 10 · fact_ventas — desde bronze.facventas
# MAGIC
# MAGIC `business_date` de `fecfven`. Solo activos (`estfven = 'A'`).

# COMMAND ----------

-- MAGIC %sql

CREATE OR REPLACE TABLE motoshop.silver.fact_ventas AS
SELECT
  TRIM(numfven)                      AS num_documento,
  TRIM(codclas)                      AS cod_clase,
  TRIM(prefven)                      AS prefijo,
  CAST(fecfven AS TIMESTAMP)         AS fecha_documento_ts,
  CAST(fecfven AS DATE)              AS business_date,
  TRIM(nitter)                       AS nit_cliente,
  TRIM(clifven)                      AS nombre_cliente,
  TRIM(nitvend)                      AS nit_vendedor,
  TRIM(venfven)                      AS nombre_vendedor,
  TRIM(codpag)                       AS cod_formapago,
  CAST(diasfven AS INT)              AS dias_formapago,
  CAST(subfven AS DOUBLE)            AS subtotal,
  CAST(totdct AS DOUBLE)             AS total_descuentos,
  CAST(totiva AS DOUBLE)             AS total_iva,
  CAST(totipo AS DOUBLE)             AS total_impuesto,
  CAST(retfte AS DOUBLE)             AS retencion_fuente,
  CAST(retiva AS DOUBLE)             AS retencion_iva,
  CAST(retica AS DOUBLE)             AS retencion_ica,
  CAST(totfven AS DOUBLE)            AS total_factura,
  TRIM(obsfven)                      AS observaciones,
  TRIM(estfven)                      AS estado_documento,
  TRIM(codsuc)                       AS cod_sucursal,
  TRIM(codemp)                       AS cod_empresa,
  TRIM(empcod)                       AS cod_empresa_alt,
  TRIM(codres)                       AS cod_resolucion,
  CURRENT_DATE()                     AS ingest_date_silver
FROM motoshop.bronze.facventas
WHERE estfven = 'A'
  AND fecfven IS NOT NULL
  AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
  AND CAST(fecfven AS DATE) <= CURRENT_DATE();

# COMMAND ----------

-- MAGIC %sql

SELECT COUNT(*) AS fact_ventas_rows FROM motoshop.silver.fact_ventas;

# COMMAND ----------

-- MAGIC %sql

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS distintos,
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS duplicados
FROM motoshop.silver.fact_ventas;

# COMMAND ----------

-- MAGIC %sql

SELECT * FROM motoshop.silver.fact_ventas LIMIT 10;
