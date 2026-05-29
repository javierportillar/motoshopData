-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 12 · fact_compras — desde bronze.compras
-- MAGIC
-- MAGIC Patrón idempotente: DELETE + INSERT por `business_date`.
-- MAGIC Estados incluidos: 'B' (746 compras, dominante), 'A' (16 compras).
-- MAGIC En sgHermes Colombia, 'B' corresponde a documentos válidos; 'A' puede ser
-- MAGIC anuladas u otro estado. Se incluyen ambos para preservar el universo completo.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.silver.fact_compras (
  num_documento STRING,
  cod_clase STRING,
  prefijo STRING,
  fecha_documento_ts TIMESTAMP,
  business_date DATE,
  nit_proveedor STRING,
  nombre_proveedor STRING,
  cod_sucursal STRING,
  cod_formapago STRING,
  subtotal DOUBLE,
  total_descuentos DOUBLE,
  total_iva DOUBLE,
  total_impuesto DOUBLE,
  retencion_fuente DOUBLE,
  retencion_iva DOUBLE,
  retencion_ica DOUBLE,
  total_compra DOUBLE,
  observaciones STRING,
  estado_documento STRING,
  cod_empresa STRING,
  cod_empresa_alt STRING,
  nit_vendedor STRING,
  ingest_date_silver DATE
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

DELETE FROM motoshop.silver.fact_compras
WHERE business_date IN (
  SELECT DISTINCT CAST(feccom AS DATE)
  FROM motoshop.bronze.compras
  WHERE estcom IN ('A', 'B')
    AND feccom IS NOT NULL
    AND CAST(feccom AS DATE) >= DATE '2020-01-01'
    AND CAST(feccom AS DATE) <= CURRENT_DATE()
);

-- COMMAND ----------

INSERT INTO motoshop.silver.fact_compras
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
WHERE estcom IN ('A', 'B')
  AND feccom IS NOT NULL
  AND CAST(feccom AS DATE) >= DATE '2020-01-01'
  AND CAST(feccom AS DATE) <= CURRENT_DATE();

-- COMMAND ----------

SELECT COUNT(*) AS fact_compras_rows FROM motoshop.silver.fact_compras;

-- COMMAND ----------

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS distintos,
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS duplicados
FROM motoshop.silver.fact_compras;

-- COMMAND ----------

SELECT * FROM motoshop.silver.fact_compras LIMIT 10;
