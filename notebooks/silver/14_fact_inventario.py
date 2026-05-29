# Databricks notebook source
# MAGIC %md
# MAGIC # 14 · fact_inventario — desde bronze.auxinventario
# MAGIC
# MAGIC `business_date` de `docfec`. `valor3` = cantidad.

# COMMAND ----------

-- MAGIC %sql

CREATE OR REPLACE TABLE motoshop.silver.fact_inventario AS
SELECT
  monotonically_increasing_id() AS id_inventario,
  TRIM(codlis)         AS cod_lista,
  TRIM(nomlis)         AS nombre_lista,
  TRIM(codlin1)        AS cod_linea1,
  TRIM(nomlin)         AS nombre_linea,
  TRIM(codlin2)        AS cod_linea2,
  TRIM(nomlin2)        AS nombre_linea2,
  TRIM(codbod)         AS cod_bodega,
  TRIM(nombod)         AS nombre_bodega,
  TRIM(nitter)         AS nit_tercero,
  TRIM(nomter)         AS nombre_tercero,
  TRIM(numdoc)         AS num_documento,
  TRIM(nomdoc)         AS nombre_documento,
  TRIM(codprod)        AS cod_producto,
  TRIM(sernum)         AS num_serie,
  TRIM(nomprod)        AS nombre_producto,
  TRIM(unimed)         AS unidad_medida,
  CAST(valor1 AS DOUBLE)  AS valor_costo,
  CAST(valor2 AS DOUBLE)  AS valor_venta,
  CAST(valor3 AS DOUBLE)  AS cantidad,
  CAST(valor4 AS DOUBLE)  AS valor4,
  CAST(valor5 AS DOUBLE)  AS valor5,
  CAST(docfec AS DATE)     AS business_date,
  TRIM(docnum)         AS num_doc_referencia,
  TRIM(nomsub)         AS nombre_sub,
  CAST(multiplo AS DOUBLE) AS multiplo,
  TRIM(codcos)         AS cod_centro_costo,
  TRIM(nomcos)         AS nombre_centro_costo
FROM motoshop.bronze.auxinventario
WHERE docfec IS NOT NULL
  AND CAST(docfec AS DATE) >= DATE '2020-01-01'
  AND CAST(docfec AS DATE) <= CURRENT_DATE();

# COMMAND ----------

-- MAGIC %sql

SELECT COUNT(*) AS fact_inventario_rows FROM motoshop.silver.fact_inventario;

# COMMAND ----------

-- MAGIC %sql

SELECT * FROM motoshop.silver.fact_inventario LIMIT 10;
