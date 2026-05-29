-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 05 · dim_formapago — SCD Type 1 desde bronze.formapago

-- COMMAND ----------

CREATE OR REPLACE TABLE motoshop.silver.dim_formapago AS
SELECT
  TRIM(codpag)    AS cod_formapago,
  TRIM(forpag)    AS nombre_formapago,
  CAST(afepag AS INT)    AS afecta_pago,
  CAST(tippag AS INT)    AS tipo_pago,
  TRIM(codcaj)    AS cod_caja,
  TRIM(codban)    AS cod_banco,
  TRIM(codcue)    AS cod_cuenta,
  TRIM(facven)    AS factura_venta,
  TRIM(venpos)    AS venta_pos,
  TRIM(compra)    AS es_compra,
  TRIM(financ)    AS es_financiacion,
  TRIM(empsino)   AS empresa_sino,
  CURRENT_DATE()  AS snapshot_date
FROM motoshop.bronze.formapago
WHERE codpag IS NOT NULL;

-- COMMAND ----------

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT cod_formapago) AS distintos,
  COUNT(*) - COUNT(DISTINCT cod_formapago) AS duplicados
FROM motoshop.silver.dim_formapago;

-- COMMAND ----------

SELECT COUNT(*) AS dim_formapago_rows FROM motoshop.silver.dim_formapago;
