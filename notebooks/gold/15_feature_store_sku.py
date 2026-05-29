-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 15 · Feature Store SKU
-- MAGIC
-- MAGIC Feature engineering para forecasting de demanda.
-- MAGIC Features: lags 7/14/28d, medias móviles 7/14/28d, temporales (dia_semana, mes, es_festivo),
-- MAGIC stock actual, días sin venta, categoría ABC.
-- MAGIC INSERT OVERWRITE particionado por business_date.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.feature_store_sku (
  cod_producto STRING,
  business_date DATE,
  demanda_diaria DOUBLE,
  lag_7d DOUBLE,
  lag_14d DOUBLE,
  lag_28d DOUBLE,
  media_movil_7d DOUBLE,
  media_movil_14d DOUBLE,
  media_movil_28d DOUBLE,
  dia_semana INT,
  mes INT,
  es_festivo BOOLEAN,
  stock_actual DOUBLE,
  dias_sin_venta INT,
  categoria_abc STRING
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## INSERT OVERWRITE — feature engineering

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.feature_store_sku PARTITION (business_date)
WITH
demanda_diaria AS (
  SELECT
    business_date,
    cod_producto,
    SUM(cantidad_total) AS demanda
  FROM motoshop.gold.mart_ventas_diarias_sku
  GROUP BY business_date, cod_producto
),
lags_y_medias AS (
  SELECT
    cod_producto,
    business_date,
    demanda AS demanda_diaria,
    LAG(demanda, 7)  OVER (PARTITION BY cod_producto ORDER BY business_date) AS lag_7d,
    LAG(demanda, 14) OVER (PARTITION BY cod_producto ORDER BY business_date) AS lag_14d,
    LAG(demanda, 28) OVER (PARTITION BY cod_producto ORDER BY business_date) AS lag_28d,
    AVG(demanda) OVER (PARTITION BY cod_producto ORDER BY business_date ROWS BETWEEN 7  PRECEDING AND 1 PRECEDING) AS media_movil_7d,
    AVG(demanda) OVER (PARTITION BY cod_producto ORDER BY business_date ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING) AS media_movil_14d,
    AVG(demanda) OVER (PARTITION BY cod_producto ORDER BY business_date ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS media_movil_28d
  FROM demanda_diaria
),
features_temporales AS (
  SELECT
    cod_producto,
    business_date,
    demanda_diaria,
    COALESCE(lag_7d, 0) AS lag_7d,
    COALESCE(lag_14d, 0) AS lag_14d,
    COALESCE(lag_28d, 0) AS lag_28d,
    COALESCE(media_movil_7d, 0) AS media_movil_7d,
    COALESCE(media_movil_14d, 0) AS media_movil_14d,
    COALESCE(media_movil_28d, 0) AS media_movil_28d,
    DAYOFWEEK(business_date) AS dia_semana,
    MONTH(business_date) AS mes,
    FALSE AS es_festivo
  FROM lags_y_medias
)
SELECT
  ft.cod_producto,
  ft.business_date,
  ft.demanda_diaria,
  ft.lag_7d,
  ft.lag_14d,
  ft.lag_28d,
  ft.media_movil_7d,
  ft.media_movil_14d,
  ft.media_movil_28d,
  ft.dia_semana,
  ft.mes,
  ft.es_festivo,
  COALESCE(ia.cantidad_actual, 0) AS stock_actual,
  COALESCE(pd.dias_sin_venta, 99999) AS dias_sin_venta,
  COALESCE(ra.categoria_abc, 'C') AS categoria_abc
FROM features_temporales ft
LEFT JOIN motoshop.gold.mart_inventario_actual ia
  ON ft.cod_producto = ia.cod_producto
LEFT JOIN motoshop.gold.mart_productos_dormidos pd
  ON ft.cod_producto = pd.cod_producto
LEFT JOIN (
  SELECT DISTINCT cod_producto, categoria_abc
  FROM motoshop.gold.mart_rotacion_abc
  WHERE business_month = (SELECT MAX(business_month) FROM motoshop.gold.mart_rotacion_abc)
) ra
  ON ft.cod_producto = ra.cod_producto;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT cod_producto) AS skus_unicos,
  MIN(business_date) AS min_date,
  MAX(business_date) AS max_date
FROM motoshop.gold.feature_store_sku;

-- COMMAND ----------

SELECT * FROM motoshop.gold.feature_store_sku LIMIT 10;

-- COMMAND ----------

SELECT
  ROUND(AVG(lag_7d), 2) AS avg_lag_7d,
  ROUND(AVG(lag_14d), 2) AS avg_lag_14d,
  ROUND(AVG(lag_28d), 2) AS avg_lag_28d,
  ROUND(AVG(media_movil_7d), 2) AS avg_mm_7d,
  ROUND(AVG(media_movil_14d), 2) AS avg_mm_14d,
  ROUND(AVG(media_movil_28d), 2) AS avg_mm_28d,
  ROUND(AVG(stock_actual), 2) AS avg_stock,
  ROUND(AVG(dias_sin_venta), 2) AS avg_dias_sin_venta,
  COUNT(DISTINCT categoria_abc) AS categorias_abc
FROM motoshop.gold.feature_store_sku;

-- COMMAND ----------

SELECT categoria_abc, COUNT(*) AS cnt
FROM motoshop.gold.feature_store_sku
GROUP BY categoria_abc
ORDER BY categoria_abc;
