-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 10 · mart_ventas_diarias_sku — agregación diaria por SKU
-- MAGIC
-- MAGIC Agregación diaria desde silver.fact_ventas_detalle + fact_ventas.
-- MAGIC JOIN con dim_producto y dim_bodega para nombres.
-- MAGIC Patrón idempotente: DELETE + INSERT por business_date.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Crear tabla si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_ventas_diarias_sku (
  business_date DATE,
  cod_producto STRING,
  nom_producto STRING,
  cod_bodega STRING,
  nom_bodega STRING,
  cantidad_total DOUBLE,
  valor_total DOUBLE,
  num_facturas INT
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · DELETE + INSERT (idempotente por business_date)

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.mart_ventas_diarias_sku
PARTITION (business_date)
SELECT
  fv.business_date,
  fvd.cod_producto,
  COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
  fvd.cod_bodega,
  COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
  ROUND(SUM(fvd.cantidad), 2)         AS cantidad_total,
  ROUND(SUM(fvd.valor_unitario * fvd.cantidad - COALESCE(fvd.descuento_valor, 0)), 2) AS valor_total,
  COUNT(DISTINCT fv.num_documento)    AS num_facturas
FROM motoshop.silver.fact_ventas_detalle fvd
INNER JOIN motoshop.silver.fact_ventas fv
  ON fvd.num_documento = fv.num_documento
  AND fvd.cod_clase = fv.cod_clase
  AND fvd.business_date = fv.business_date
LEFT JOIN motoshop.silver.dim_producto dp
  ON fvd.cod_producto = dp.cod_producto
LEFT JOIN motoshop.silver.dim_bodega db
  ON fvd.cod_bodega = db.cod_bodega
WHERE fvd.business_date >= DATE '2020-01-01'
  AND fvd.business_date <= CURRENT_DATE()
GROUP BY fv.business_date, fvd.cod_producto, dp.nombre_producto, fvd.cod_bodega, db.nombre_bodega;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  MIN(business_date) AS min_date,
  MAX(business_date) AS max_date
FROM motoshop.gold.mart_ventas_diarias_sku;

-- COMMAND ----------

SELECT * FROM motoshop.gold.mart_ventas_diarias_sku LIMIT 10;
