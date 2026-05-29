-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 14 · mart_productos_dormidos — productos sin venta > 90 días
-- MAGIC
-- MAGIC DT-F3-8: Producto dormido = sin venta en los últimos 90 días.
-- MAGIC Incluye stock actual para distinguir "dormido con stock" vs "dormido sin stock".
-- MAGIC Sin partición (snapshot del día). Reemplazo completo.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Crear tabla si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_productos_dormidos (
  cod_producto STRING,
  nom_producto STRING,
  cod_bodega STRING,
  ultima_fecha_venta DATE,
  dias_sin_venta INT,
  stock_actual DOUBLE,
  categoria STRING
) USING DELTA;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · DELETE + INSERT (reemplazo completo)

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.mart_productos_dormidos
WITH ultima_venta AS (
  SELECT
    fvd.cod_producto,
    fvd.cod_bodega,
    MAX(fv.business_date) AS ultima_fecha_venta
  FROM motoshop.silver.fact_ventas_detalle fvd
  INNER JOIN motoshop.silver.fact_ventas fv
    ON fvd.num_documento = fv.num_documento
    AND fvd.cod_clase = fv.cod_clase
    AND fvd.business_date = fv.business_date
  GROUP BY fvd.cod_producto, fvd.cod_bodega
),
productos_con_stock AS (
  SELECT
    i.cod_producto,
    i.cod_bodega,
    ROUND(SUM(i.cantidad), 2) AS stock_total
  FROM motoshop.silver.fact_inventario i
  INNER JOIN (
    SELECT cod_producto, cod_bodega, MAX(business_date) AS max_date
    FROM motoshop.silver.fact_inventario
    WHERE business_date >= DATE '2020-01-01'
      AND business_date <= CURRENT_DATE()
    GROUP BY cod_producto, cod_bodega
  ) latest
    ON i.cod_producto = latest.cod_producto
    AND i.cod_bodega = latest.cod_bodega
    AND i.business_date = latest.max_date
  GROUP BY i.cod_producto, i.cod_bodega
),
productos_mart AS (
  SELECT DISTINCT fvd.cod_producto, fvd.cod_bodega
  FROM motoshop.silver.fact_ventas_detalle fvd
)
SELECT
  COALESCE(uv.cod_producto, p.cod_producto) AS cod_producto,
  COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
  COALESCE(uv.cod_bodega, p.cod_bodega) AS cod_bodega,
  uv.ultima_fecha_venta,
  CAST(COALESCE(DATEDIFF(CURRENT_DATE(), uv.ultima_fecha_venta), -1) AS INT) AS dias_sin_venta,
  COALESCE(ps.stock_total, 0) AS stock_actual,
  CASE
    WHEN COALESCE(ps.stock_total, 0) > 0 THEN 'dormido_con_stock'
    ELSE 'dormido_sin_stock'
  END AS categoria
FROM (
  -- Productos que han tenido venta alguna vez
  SELECT cod_producto, cod_bodega FROM productos_mart
  UNION
  -- Productos en inventario (pueden no haber tenido venta)
  SELECT cod_producto, cod_bodega FROM productos_con_stock
) p
LEFT JOIN ultima_venta uv
  ON p.cod_producto = uv.cod_producto AND p.cod_bodega = uv.cod_bodega
LEFT JOIN productos_con_stock ps
  ON p.cod_producto = ps.cod_producto AND p.cod_bodega = ps.cod_bodega
LEFT JOIN motoshop.silver.dim_producto dp
  ON p.cod_producto = dp.cod_producto
WHERE uv.ultima_fecha_venta IS NULL
   OR DATEDIFF(CURRENT_DATE(), uv.ultima_fecha_venta) > 90;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  SUM(CASE WHEN categoria = 'dormido_con_stock' THEN 1 ELSE 0 END) AS dormidos_con_stock,
  SUM(CASE WHEN categoria = 'dormido_sin_stock' THEN 1 ELSE 0 END) AS dormidos_sin_stock,
  ROUND(AVG(dias_sin_venta), 0) AS avg_dias_sin_venta
FROM motoshop.gold.mart_productos_dormidos;

-- COMMAND ----------

SELECT * FROM motoshop.gold.mart_productos_dormidos
ORDER BY dias_sin_venta DESC
LIMIT 20;
