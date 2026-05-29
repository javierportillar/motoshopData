-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 11 · mart_inventario_actual — snapshot del último estado de inventario
-- MAGIC
-- MAGIC Último registro por (cod_producto, cod_bodega) desde silver.fact_inventario.
-- MAGIC JOIN con dim_producto y dim_bodega para nombres.
-- MAGIC Sin partición (snapshot global). Reemplazo completo.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Crear tabla si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_inventario_actual (
  cod_producto STRING,
  nom_producto STRING,
  cod_bodega STRING,
  nom_bodega STRING,
  cantidad_actual DOUBLE,
  ultimo_costo DOUBLE,
  ultima_actualizacion DATE
) USING DELTA;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · DELETE + INSERT (reemplazo completo)

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.mart_inventario_actual
WITH ultimo_inventario AS (
  SELECT
    cod_producto,
    cod_bodega,
    cantidad,
    valor_costo,
    business_date,
    ROW_NUMBER() OVER (
      PARTITION BY cod_producto, cod_bodega
      ORDER BY business_date DESC, id_inventario DESC
    ) AS rn
  FROM motoshop.silver.fact_inventario
  WHERE business_date >= DATE '2020-01-01'
    AND business_date <= CURRENT_DATE()
)
SELECT
  ui.cod_producto,
  COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
  ui.cod_bodega,
  COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
  ROUND(ui.cantidad, 2) AS cantidad_actual,
  ROUND(ui.valor_costo, 2) AS ultimo_costo,
  ui.business_date AS ultima_actualizacion
FROM ultimo_inventario ui
LEFT JOIN motoshop.silver.dim_producto dp
  ON ui.cod_producto = dp.cod_producto
LEFT JOIN motoshop.silver.dim_bodega db
  ON ui.cod_bodega = db.cod_bodega
WHERE ui.rn = 1;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT cod_producto) AS productos_distintos,
  COUNT(DISTINCT cod_bodega) AS bodegas_distintas,
  ROUND(SUM(cantidad_actual), 2) AS stock_total
FROM motoshop.gold.mart_inventario_actual;

-- COMMAND ----------

SELECT * FROM motoshop.gold.mart_inventario_actual LIMIT 10;
