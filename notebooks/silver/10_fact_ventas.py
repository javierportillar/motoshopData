-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 10 · fact_ventas — desde bronze.facventas
-- MAGIC
-- MAGIC Patrón idempotente: DELETE + INSERT por `business_date`.
-- MAGIC `business_date` se deriva de `fecfven`.
-- MAGIC Estados incluidos: 'B' (6,325 facturas, dominante), 'A' (15 facturas).
-- MAGIC En sgHermes Colombia, 'B' corresponde a facturas válidas; 'A' puede ser
-- MAGIC anuladas u otro estado. Se incluyen ambos para preservar el universo completo.
-- MAGIC Repetible sin duplicar: si ya existe la partición, se sobreescribe.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Crear tabla si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.silver.fact_ventas (
  num_documento STRING,
  cod_clase STRING,
  prefijo STRING,
  fecha_documento_ts TIMESTAMP,
  business_date DATE,
  nit_cliente STRING,
  nombre_cliente STRING,
  nit_vendedor STRING,
  nombre_vendedor STRING,
  cod_formapago STRING,
  dias_formapago INT,
  subtotal DOUBLE,
  total_descuentos DOUBLE,
  total_iva DOUBLE,
  total_impuesto DOUBLE,
  retencion_fuente DOUBLE,
  retencion_iva DOUBLE,
  retencion_ica DOUBLE,
  total_factura DOUBLE,
  observaciones STRING,
  estado_documento STRING,
  cod_sucursal STRING,
  cod_empresa STRING,
  cod_empresa_alt STRING,
  cod_resolucion STRING,
  ingest_date_silver DATE
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · DELETE + INSERT (idempotente por business_date)

-- COMMAND ----------

DELETE FROM motoshop.silver.fact_ventas
WHERE business_date IN (
  SELECT DISTINCT CAST(fecfven AS DATE)
  FROM motoshop.bronze.facventas
  WHERE estfven IN ('A', 'B')
    AND fecfven IS NOT NULL
    AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
    AND CAST(fecfven AS DATE) <= CURRENT_DATE()
);

-- COMMAND ----------

INSERT INTO motoshop.silver.fact_ventas
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
WHERE estfven IN ('A', 'B')
  AND fecfven IS NOT NULL
  AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
  AND CAST(fecfven AS DATE) <= CURRENT_DATE();

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación

-- COMMAND ----------

SELECT COUNT(*) AS fact_ventas_rows FROM motoshop.silver.fact_ventas;

-- COMMAND ----------

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS distintos,
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS duplicados
FROM motoshop.silver.fact_ventas;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Idempotencia verificada
-- MAGIC
-- MAGIC Este notebook es idempotente: ejecutar dos veces seguidas produce
-- MAGIC el mismo resultado. El DELETE elimina la partición de business_date
-- MAGIC y el INSERT la recrea. No afecta datos de otros días.

-- COMMAND ----------

SELECT * FROM motoshop.silver.fact_ventas LIMIT 10;
