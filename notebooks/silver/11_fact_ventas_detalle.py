-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 11 · fact_ventas_detalle — desde bronze.detfventas

-- COMMAND ----------

CREATE OR REPLACE TABLE motoshop.silver.fact_ventas_detalle AS
SELECT
  TRIM(d.numfven)      AS num_documento,
  TRIM(d.codclas)      AS cod_clase,
  TRIM(d.codprod)      AS cod_producto,
  TRIM(d.nomdet)       AS nombre_detalle,
  CAST(d.candet AS DOUBLE)   AS cantidad,
  CAST(d.valuni AS DOUBLE)   AS valor_unitario,
  CAST(d.dctpor AS DOUBLE)   AS descuento_porcentaje,
  CAST(d.dctpes AS DOUBLE)   AS descuento_valor,
  CAST(d.ivapor AS DOUBLE)   AS iva_porcentaje,
  CAST(d.ivapes AS DOUBLE)   AS iva_valor,
  CAST(d.ipopor AS DOUBLE)   AS ipo_porcentaje,
  CAST(d.ipopes AS DOUBLE)   AS ipo_valor,
  CAST(d.totdet AS DOUBLE)   AS total_detalle,
  CAST(d.cosprod AS DOUBLE)  AS costo_producto,
  CAST(d.numite AS INT)      AS num_item,
  TRIM(d.codbod)      AS cod_bodega,
  TRIM(d.codcos)      AS cod_centro_costo,
  h.business_date
FROM motoshop.bronze.detfventas d
INNER JOIN motoshop.silver.fact_ventas h
  ON TRIM(d.numfven) = h.num_documento
  AND TRIM(d.codclas) = h.cod_clase;

-- COMMAND ----------

SELECT COUNT(*) AS fact_ventas_detalle_rows FROM motoshop.silver.fact_ventas_detalle;

-- COMMAND ----------

SELECT * FROM motoshop.silver.fact_ventas_detalle LIMIT 10;
