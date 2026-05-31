-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 19 - mart_abc_xyz - matriz ABC  XYZ combinada
-- MAGIC
-- MAGIC Clasificacion bidimensional de SKUs:
-- MAGIC - **ABC** (injetado de `mart_rotacion_abc`, mes mas reciente): A 80% / B 95% / C >95% del ingreso acumulado
-- MAGIC - **XYZ** (calculado sobre ventas diarias ultimos 90d): X = CV<0.5 / Y = 0.5CV<1 / Z = CV1
-- MAGIC - **bucket** = CONCAT(abc, xyz)  9 combinaciones (AX..CZ)
-- MAGIC
-- MAGIC Output: `gold.mart_abc_xyz` - snapshot diario particionado

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 - DDL - gold.mart_abc_xyz

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_abc_xyz (
  cod_producto STRING,
  abc STRING,
  xyz STRING,
  bucket STRING,
  business_date DATE
) USING DELTA PARTITIONED BY (business_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 - INSERT OVERWRITE (idempotente)

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.mart_abc_xyz PARTITION (business_date)
WITH ventas_90d AS (
  SELECT
    cod_producto,
    cantidad_total
  FROM motoshop.gold.mart_ventas_diarias_sku
  WHERE business_date >= DATE_SUB(CURRENT_DATE(), 90)
    AND business_date <= CURRENT_DATE()
),
cv_por_sku AS (
  SELECT
    cod_producto,
    CASE
      WHEN AVG(cantidad_total) > 0
        THEN STDDEV(cantidad_total) / AVG(cantidad_total)
      ELSE CAST(NULL AS DOUBLE)
    END AS cv
  FROM ventas_90d
  GROUP BY cod_producto
),
abc_mas_reciente AS (
  SELECT
    cod_producto,
    categoria_abc
  FROM motoshop.gold.mart_rotacion_abc
  WHERE business_month = (
    SELECT MAX(business_month)
    FROM motoshop.gold.mart_rotacion_abc
  )
),
clasificacion_xyz AS (
  SELECT
    cod_producto,
    cv,
    CASE
      WHEN cv IS NULL THEN 'Z'
      WHEN cv < 0.5 THEN 'X'
      WHEN cv < 1.0 THEN 'Y'
      ELSE 'Z'
    END AS xyz
  FROM cv_por_sku
)
SELECT
  COALESCE(cx.cod_producto, a.cod_producto) AS cod_producto,
  COALESCE(a.categoria_abc, 'C') AS abc,
  cx.xyz,
  CONCAT(COALESCE(a.categoria_abc, 'C'), cx.xyz) AS bucket,
  CURRENT_DATE() AS business_date
FROM clasificacion_xyz cx
FULL OUTER JOIN abc_mas_reciente a
  ON cx.cod_producto = a.cod_producto;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 - Validacion - distribucion 9 buckets

-- COMMAND ----------

SELECT
  bucket,
  COUNT(*) AS skus,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM motoshop.gold.mart_abc_xyz
WHERE business_date = CURRENT_DATE()
GROUP BY bucket
ORDER BY bucket;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 - Resumen dimensional

-- COMMAND ----------

SELECT
  abc,
  xyz,
  COUNT(*) AS skus
FROM motoshop.gold.mart_abc_xyz
WHERE business_date = CURRENT_DATE()
GROUP BY abc, xyz
ORDER BY abc, xyz;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5 - Top 10 AX (mas predecibles y mas valiosos)

-- COMMAND ----------

SELECT
  m.cod_producto,
  m.abc,
  m.xyz,
  m.bucket,
  ra.valor_total,
  ra.porcentaje_acumulado
FROM motoshop.gold.mart_abc_xyz m
LEFT JOIN motoshop.gold.mart_rotacion_abc ra
  ON m.cod_producto = ra.cod_producto
  AND ra.business_month = (
    SELECT MAX(business_month)
    FROM motoshop.gold.mart_rotacion_abc
  )
WHERE m.business_date = CURRENT_DATE()
  AND m.bucket = 'AX'
ORDER BY ra.valor_total DESC
LIMIT 10;
