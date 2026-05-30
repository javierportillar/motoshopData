-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 24 · Forecast Categoría — baseline + Prophet sobre serie agregada
-- MAGIC
-- MAGIC Agrega ventas diarias por categoría (`cod_grupo`) y aplica baseline
-- MAGIC (media móvil 7/14/28d) sobre la serie agregada.
-- MAGIC
-- MAGIC Hipótesis F4-FIX1: la agregación por categoría reduce intermitencia
-- MAGIC y permite que Prophet aprenda estacionalidad, superando baseline-SKU.
-- MAGIC
-- MAGIC Output: `gold.forecast_categoria`
-- MAGIC
-- MAGIC Evaluación WAPE comparativa vs Baseline-SKU (45.83%) se documenta
-- MAGIC en `_runs/v_forecast_categoria_eval_<ts>.md`.

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 1 · DDL — gold.forecast_categoria
-- MAGIC
-- MAGIC Particionada por `business_date`.
-- MAGIC `cod_grupo` = nivel de categoría desde `dim_producto.cod_grupo`.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.forecast_categoria (
  cod_grupo STRING,
  business_date DATE,
  demanda_real DOUBLE,
  demanda_predicha_baseline DOUBLE,
  metodo_baseline STRING
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 2 · Temporary view: demanda agregada por categoría
-- MAGIC
-- MAGIC Agrega `mart_ventas_diarias_sku` a nivel `cod_grupo × día`.
-- MAGIC SKUs sin `cod_grupo` en `dim_producto` van a `'SIN_GRUPO'`.

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW demanda_categoria AS
SELECT
  COALESCE(dp.cod_grupo, 'SIN_GRUPO') AS cod_grupo,
  mvd.business_date,
  ROUND(SUM(mvd.cantidad_total), 2) AS demanda_real
FROM motoshop.gold.mart_ventas_diarias_sku mvd
LEFT JOIN motoshop.silver.dim_producto dp
  ON mvd.cod_producto = dp.cod_producto
WHERE mvd.business_date >= DATE '2024-01-01'
  AND mvd.business_date <= CURRENT_DATE()
GROUP BY COALESCE(dp.cod_grupo, 'SIN_GRUPO'), mvd.business_date;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 3 · Temporary view: baseline (media móvil 7/14/28d)
-- MAGIC
-- MAGIC Misma lógica que `16_forecast_baseline_sku.py` pero sobre serie agregada.
-- MAGIC
-- MAGIC Estrategia:
-- MAGIC 1. Media móvil 7d (fallback primario)
-- MAGIC 2. Si no hay 7d → media móvil 14d
-- MAGIC 3. Si no hay 14d → media móvil 28d
-- MAGIC 4. Si no hay datos previos → NULL

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW baseline_categoria AS
WITH
medias_moviles AS (
  SELECT
    cod_grupo,
    business_date,
    demanda_real,
    AVG(demanda_real) OVER (
      PARTITION BY cod_grupo ORDER BY business_date
      ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    ) AS mm_7d,
    AVG(demanda_real) OVER (
      PARTITION BY cod_grupo ORDER BY business_date
      ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS mm_14d,
    AVG(demanda_real) OVER (
      PARTITION BY cod_grupo ORDER BY business_date
      ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
    ) AS mm_28d
  FROM demanda_categoria
)
SELECT
  cod_grupo,
  business_date,
  demanda_real,
  COALESCE(mm_7d, mm_14d, mm_28d) AS demanda_predicha_baseline,
  CASE
    WHEN mm_7d IS NOT NULL THEN 'moving_average_7d'
    WHEN mm_14d IS NOT NULL THEN 'moving_average_14d'
    WHEN mm_28d IS NOT NULL THEN 'moving_average_28d'
    ELSE CAST(NULL AS STRING)
  END AS metodo_baseline
FROM medias_moviles;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 4 · INSERT OVERWRITE — gold.forecast_categoria

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.forecast_categoria
PARTITION (business_date)
SELECT
  cod_grupo,
  business_date,
  demanda_real,
  demanda_predicha_baseline,
  metodo_baseline
FROM baseline_categoria;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 5 · Validación — conteos básicos

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT cod_grupo) AS grupos_unicos,
  MIN(business_date) AS min_date,
  MAX(business_date) AS max_date,
  COUNT(demanda_predicha_baseline) AS filas_con_prediccion,
  SUM(CASE WHEN demanda_predicha_baseline IS NULL THEN 1 ELSE 0 END) AS filas_sin_prediccion
FROM motoshop.gold.forecast_categoria;

-- COMMAND ----------

SELECT cod_grupo, COUNT(*) AS cnt
FROM motoshop.gold.forecast_categoria
GROUP BY cod_grupo
ORDER BY cnt DESC
LIMIT 20;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 6 · Distribución de métodos baseline

-- COMMAND ----------

SELECT
  metodo_baseline,
  COUNT(*) AS cnt,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM motoshop.gold.forecast_categoria
GROUP BY metodo_baseline
ORDER BY cnt DESC;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 7 · WAPE del baseline-categoría (métrica primaria)
-- MAGIC
-- MAGIC WAPE = Σ|actual - pred| / Σ actual
-- MAGIC Misma fórmula que ADR-0017.

-- COMMAND ----------

SELECT
  ROUND(
    SUM(ABS(demanda_real - demanda_predicha_baseline))
    / NULLIF(SUM(demanda_real), 0)
    * 100,
    2
  ) AS wape_baseline_categoria_pct
FROM motoshop.gold.forecast_categoria
WHERE demanda_predicha_baseline IS NOT NULL;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 8 · WAPE por categoría individual

-- COMMAND ----------

SELECT
  cod_grupo,
  COUNT(*) AS dias,
  ROUND(SUM(demanda_real), 2) AS ventas_totales,
  ROUND(
    SUM(ABS(demanda_real - demanda_predicha_baseline))
    / NULLIF(SUM(demanda_real), 0)
    * 100,
    2
  ) AS wape_pct
FROM motoshop.gold.forecast_categoria
WHERE demanda_predicha_baseline IS NOT NULL
GROUP BY cod_grupo
ORDER BY wape_pct DESC;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 9 · Cobertura: categorías con ≥ 90 días de historia
-- MAGIC
-- MAGIC Mismo filtro de elegibilidad que F4-FIX1 pero a nivel categoría.
-- MAGIC Esperamos cobertura ~100% vs 0.7% en SKU individual.

-- COMMAND ----------

SELECT
  COUNT(DISTINCT cod_grupo) AS categorias_totales,
  COUNT(DISTINCT CASE
    WHEN dias_historia >= 90 THEN cod_grupo
  END) AS categorias_elegibles,
  ROUND(
    COUNT(DISTINCT CASE
      WHEN dias_historia >= 90 THEN cod_grupo
    END) * 100.0 / NULLIF(COUNT(DISTINCT cod_grupo), 0),
    2
  ) AS pct_elegible
FROM (
  SELECT
    cod_grupo,
    COUNT(DISTINCT business_date) AS dias_historia
  FROM motoshop.gold.forecast_categoria
  GROUP BY cod_grupo
);

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 10 · Coeficiente de variación por categoría
-- MAGIC
-- MAGIC Mide qué tan intermitente es la demanda en cada categoría.
-- MAGIC CV alto → categoría difícil de pronosticar incluso agregada.

-- COMMAND ----------

SELECT
  cod_grupo,
  COUNT(*) AS dias,
  ROUND(AVG(demanda_real), 2) AS media_diaria,
  ROUND(STDDEV(demanda_real), 2) AS desvio,
  ROUND(
    STDDEV(demanda_real) / NULLIF(AVG(demanda_real), 0),
    2
  ) AS cv
FROM motoshop.gold.forecast_categoria
GROUP BY cod_grupo
HAVING AVG(demanda_real) > 0
ORDER BY cv DESC
LIMIT 20;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 11 · WAPE por mes (tendencia temporal)

-- COMMAND ----------

SELECT
  DATE_TRUNC('MONTH', business_date) AS business_month,
  ROUND(
    SUM(ABS(demanda_real - demanda_predicha_baseline))
    / NULLIF(SUM(demanda_real), 0)
    * 100,
    2
  ) AS wape_mensual_pct,
  COUNT(*) AS rows
FROM motoshop.gold.forecast_categoria
WHERE demanda_predicha_baseline IS NOT NULL
GROUP BY DATE_TRUNC('MONTH', business_date)
ORDER BY business_month;
