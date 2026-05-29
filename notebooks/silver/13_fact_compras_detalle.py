-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 13 · fact_compras_detalle — desde bronze.detcompras
-- MAGIC
-- MAGIC Patrón idempotente: DELETE + INSERT por `business_date`.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.silver.fact_compras_detalle (
  num_documento STRING,
  cod_clase STRING,
  cod_producto STRING,
  nombre_detalle STRING,
  cantidad DOUBLE,
  valor_unitario DOUBLE,
  descuento_porcentaje DOUBLE,
  descuento_valor DOUBLE,
  iva_porcentaje DOUBLE,
  iva_valor DOUBLE,
  ipo_porcentaje DOUBLE,
  ipo_valor DOUBLE,
  total_detalle DOUBLE,
  costo_producto DOUBLE,
  num_item INT,
  cod_bodega STRING,
  cod_centro_costo STRING,
  business_date DATE
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

DELETE FROM motoshop.silver.fact_compras_detalle
WHERE business_date IN (
  SELECT DISTINCT h.business_date
  FROM motoshop.bronze.detcompras d
  INNER JOIN motoshop.silver.fact_compras h
    ON TRIM(d.numcom) = h.num_documento AND TRIM(d.codclas) = h.cod_clase
);

-- COMMAND ----------

INSERT INTO motoshop.silver.fact_compras_detalle
SELECT
  TRIM(d.numcom)      AS num_documento,
  TRIM(d.codclas)     AS cod_clase,
  TRIM(d.codprod)     AS cod_producto,
  TRIM(d.nomdet)      AS nombre_detalle,
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
FROM motoshop.bronze.detcompras d
INNER JOIN motoshop.silver.fact_compras h
  ON TRIM(d.numcom) = h.num_documento
  AND TRIM(d.codclas) = h.cod_clase;

-- COMMAND ----------

SELECT COUNT(*) AS fact_compras_detalle_rows FROM motoshop.silver.fact_compras_detalle;

-- COMMAND ----------

SELECT * FROM motoshop.silver.fact_compras_detalle LIMIT 10;
