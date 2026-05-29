-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 12 · mart_rotacion_abc — clasificación ABC por ingresos acumulados
-- MAGIC
-- MAGIC ABC 80/15/5 clásico (DT-F3-7):
-- MAGIC - A <= 80% del ingreso acumulado
-- MAGIC - B <= 95% del ingreso acumulado
-- MAGIC - C > 95% del ingreso acumulado
-- MAGIC
-- MAGIC Particionado por business_month. Patrón idempotente: DELETE + INSERT.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Crear tabla si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_rotacion_abc (
  business_month DATE,
  cod_producto STRING,
  nom_producto STRING,
  valor_total DOUBLE,
  porcentaje_acumulado DOUBLE,
  categoria_abc STRING
) USING DELTA PARTITIONED BY (business_month);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · DELETE + INSERT (idempotente por business_month)

-- COMMAND ----------

INSERT OVERWRITE motoshop.gold.mart_rotacion_abc
PARTITION (business_month)
WITH ingresos_mensuales AS (
  SELECT
    DATE_TRUNC('MONTH', fv.business_date) AS business_month,
    fvd.cod_producto,
    COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
    ROUND(SUM(fvd.valor_unitario * fvd.cantidad - COALESCE(fvd.descuento_valor, 0)), 2) AS valor_total
  FROM motoshop.silver.fact_ventas_detalle fvd
  INNER JOIN motoshop.silver.fact_ventas fv
    ON fvd.num_documento = fv.num_documento
    AND fvd.cod_clase = fv.cod_clase
    AND fvd.business_date = fv.business_date
  LEFT JOIN motoshop.silver.dim_producto dp
    ON fvd.cod_producto = dp.cod_producto
  WHERE fv.business_date >= DATE '2020-01-01'
    AND fv.business_date <= CURRENT_DATE()
  GROUP BY DATE_TRUNC('MONTH', fv.business_date), fvd.cod_producto, dp.nombre_producto
),
ingresos_ordenados AS (
  SELECT
    business_month,
    cod_producto,
    nom_producto,
    valor_total,
    SUM(valor_total) OVER (PARTITION BY business_month) AS total_mes,
    ROW_NUMBER() OVER (PARTITION BY business_month ORDER BY valor_total DESC, cod_producto) AS rn
  FROM ingresos_mensuales
),
ingresos_acumulados AS (
  SELECT
    business_month,
    cod_producto,
    nom_producto,
    valor_total,
    total_mes,
    SUM(valor_total) OVER (PARTITION BY business_month ORDER BY rn) AS running_total
  FROM ingresos_ordenados
)
SELECT
  business_month,
  cod_producto,
  nom_producto,
  valor_total,
  ROUND(CAST(running_total AS DOUBLE) / NULLIF(CAST(total_mes AS DOUBLE), 0) * 100, 2) AS porcentaje_acumulado,
  CASE
    WHEN CAST(running_total AS DOUBLE) / NULLIF(CAST(total_mes AS DOUBLE), 0) <= 0.80 THEN 'A'
    WHEN CAST(running_total AS DOUBLE) / NULLIF(CAST(total_mes AS DOUBLE), 0) <= 0.95 THEN 'B'
    ELSE 'C'
  END AS categoria_abc
FROM ingresos_acumulados
ORDER BY business_month, porcentaje_acumulado;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  MIN(business_month) AS min_month,
  MAX(business_month) AS max_month
FROM motoshop.gold.mart_rotacion_abc;

-- COMMAND ----------

SELECT
  business_month,
  categoria_abc,
  COUNT(*) AS productos,
  ROUND(SUM(valor_total), 2) AS valor_total,
  ROUND(AVG(porcentaje_acumulado), 2) AS pct_acumulado_promedio
FROM motoshop.gold.mart_rotacion_abc
GROUP BY business_month, categoria_abc
ORDER BY business_month, categoria_abc;

-- COMMAND ----------

SELECT * FROM motoshop.gold.mart_rotacion_abc LIMIT 10;
