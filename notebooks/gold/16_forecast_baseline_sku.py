-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 16 · Forecast Baseline SKU
-- MAGIC
-- MAGIC Baseline naive estacional para forecasting de demanda.
-- MAGIC
-- MAGIC Lógica:
-- MAGIC 1. Para cada SKU y business_date, buscar demanda del mismo día del año anterior
-- MAGIC    (±7 días de tolerancia).
-- MAGIC 2. Si existe dato en esa ventana → usar ese valor (metodo='naive_seasonal').
-- MAGIC 3. Si no → usar media_móvil_28d (metodo='moving_average_28d').
-- MAGIC 4. Si tampoco hay media_móvil → NULL.
-- MAGIC
-- MAGIC INSERT OVERWRITE particionado por business_date.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_baseline_sku (
  cod_producto STRING,
  business_date DATE,
  demanda_real DOUBLE,
  demanda_predicha DOUBLE,
  metodo STRING
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## INSERT OVERWRITE — baseline naive estacional
-- MAGIC
-- MAGIC Estrategia: self-join con ventana de ±7 días alrededor de la fecha del año anterior.
-- MAGIC Fallback a media_móvil_28d desde feature_store_sku.

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.forecast_baseline_sku PARTITION (business_date)
WITH
demanda_diaria AS (
  SELECT
    business_date,
    cod_producto,
    SUM(cantidad_total) AS demanda
  FROM motoshop.gold.mart_ventas_diarias_sku
  GROUP BY business_date, cod_producto
),
anio_anterior_candidates AS (
  SELECT
    dd.cod_producto,
    dd.business_date,
    dd.demanda AS demanda_real,
    prev.business_date AS prev_date,
    prev.demanda AS prev_demanda
  FROM demanda_diaria dd
  LEFT JOIN demanda_diaria prev
    ON dd.cod_producto = prev.cod_producto
    AND prev.business_date >= DATE_ADD(DATE_ADD(dd.business_date, -365), -7)
    AND prev.business_date <= DATE_ADD(DATE_ADD(dd.business_date, -365), 7)
),
naive_seasonal AS (
  SELECT
    cod_producto,
    business_date,
    demanda_real,
    AVG(prev_demanda) AS demanda_naive,
    COUNT(prev_demanda) AS matches_naive
  FROM anio_anterior_candidates
  GROUP BY cod_producto, business_date, demanda_real
),
con_fallback AS (
  SELECT
    ns.cod_producto,
    ns.business_date,
    ns.demanda_real,
    COALESCE(ns.demanda_naive, fs.media_movil_28d) AS demanda_predicha
  FROM naive_seasonal ns
  LEFT JOIN motoshop.gold.feature_store_sku fs
    ON ns.cod_producto = fs.cod_producto
    AND ns.business_date = fs.business_date
)
SELECT
  cod_producto,
  business_date,
  demanda_real,
  demanda_predicha,
  CASE
    WHEN demanda_predicha IS NULL THEN CAST(NULL AS STRING)
    WHEN matches_naive > 0 THEN 'naive_seasonal'
    ELSE 'moving_average_28d'
  END AS metodo
FROM con_fallback
JOIN naive_seasonal USING (cod_producto, business_date, demanda_real);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT cod_producto) AS skus_unicos,
  MIN(business_date) AS min_date,
  MAX(business_date) AS max_date,
  COUNT(demanda_predicha) AS filas_con_prediccion,
  SUM(CASE WHEN demanda_predicha IS NULL THEN 1 ELSE 0 END) AS filas_sin_prediccion
FROM motoshop.gold.forecast_baseline_sku;

-- COMMAND ----------

SELECT metodo, COUNT(*) AS cnt, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM motoshop.gold.forecast_baseline_sku
GROUP BY metodo
ORDER BY cnt DESC;

-- COMMAND ----------

SELECT * FROM motoshop.gold.forecast_baseline_sku LIMIT 10;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## MAPE baseline (aproximado)

-- COMMAND ----------

SELECT
  ROUND(
    AVG(ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real, 0)) * 100,
    2
  ) AS mape_pct
FROM motoshop.gold.forecast_baseline_sku
WHERE demanda_predicha IS NOT NULL AND demanda_real > 0;
