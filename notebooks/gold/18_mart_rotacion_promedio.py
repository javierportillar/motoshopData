-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 18 · mart_rotacion_sku — rotación promedio y días de cobertura
-- MAGIC
-- MAGIC Calcula:
-- MAGIC - `venta_diaria_promedio`: ventas últimos 90 días / 90
-- MAGIC - `dias_de_cobertura`: stock_actual / venta_diaria_promedio
-- MAGIC
-- MAGIC Inputs: `mart_ventas_diarias_sku` + `mart_inventario_actual`
-- MAGIC Output: `gold.mart_rotacion_sku` — snapshot diario particionado
-- MAGIC
-- MAGIC Idempotente: INSERT OVERWRITE WHERE business_date = CURRENT_DATE()

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · DDL — gold.mart_rotacion_sku

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_rotacion_sku (
  cod_producto STRING,
  nom_producto STRING,
  stock_actual DOUBLE,
  venta_diaria_promedio DOUBLE,
  dias_de_cobertura DOUBLE,
  business_date DATE
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · INSERT OVERWRITE (idempotente)

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.mart_rotacion_sku PARTITION (business_date)
WITH ventas_90d AS (
  SELECT
    cod_producto,
    ROUND(SUM(cantidad_total) / 90.0, 4) AS venta_diaria_promedio
  FROM motoshop.gold.mart_ventas_diarias_sku
  WHERE business_date >= DATE_SUB(CURRENT_DATE(), 90)
    AND business_date <= CURRENT_DATE()
  GROUP BY cod_producto
)
SELECT
  COALESCE(vp.cod_producto, mi.cod_producto) AS cod_producto,
  COALESCE(mi.nom_producto, 'SIN NOMBRE') AS nom_producto,
  COALESCE(mi.cantidad_actual, 0) AS stock_actual,
  COALESCE(vp.venta_diaria_promedio, 0) AS venta_diaria_promedio,
  CASE
    WHEN vp.venta_diaria_promedio IS NOT NULL AND vp.venta_diaria_promedio > 0
      THEN ROUND(mi.cantidad_actual / vp.venta_diaria_promedio, 1)
    WHEN mi.cantidad_actual > 0 THEN 999.9
    ELSE 0
  END AS dias_de_cobertura,
  CURRENT_DATE() AS business_date
FROM motoshop.gold.mart_inventario_actual mi
FULL OUTER JOIN ventas_90d vp
  ON mi.cod_producto = vp.cod_producto;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación — conteos

-- COMMAND ----------

SELECT
  COUNT(*) AS filas,
  COUNT(DISTINCT cod_producto) AS skus,
  SUM(CASE WHEN venta_diaria_promedio > 0 THEN 1 ELSE 0 END) AS skus_con_venta,
  SUM(CASE WHEN stock_actual > 0 THEN 1 ELSE 0 END) AS skus_con_stock,
  ROUND(AVG(dias_de_cobertura), 1) AS cobertura_promedio_dias
FROM motoshop.gold.mart_rotacion_sku
WHERE business_date = CURRENT_DATE();

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Top 10 — mayor rotación

-- COMMAND ----------

SELECT
  cod_producto,
  nom_producto,
  stock_actual,
  venta_diaria_promedio,
  dias_de_cobertura
FROM motoshop.gold.mart_rotacion_sku
WHERE business_date = CURRENT_DATE()
  AND venta_diaria_promedio > 0
ORDER BY venta_diaria_promedio DESC
LIMIT 10;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5 · Top 10 — mayor riesgo (cobertura < 7 días)

-- COMMAND ----------

SELECT
  cod_producto,
  nom_producto,
  stock_actual,
  ROUND(venta_diaria_promedio, 2) AS vta_diaria,
  dias_de_cobertura
FROM motoshop.gold.mart_rotacion_sku
WHERE business_date = CURRENT_DATE()
  AND stock_actual > 0
  AND dias_de_cobertura > 0
  AND dias_de_cobertura < 7
ORDER BY dias_de_cobertura ASC
LIMIT 10;
