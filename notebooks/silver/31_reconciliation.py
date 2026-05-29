-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 31 · Reconciliation — Silver vs Bronze (Full Universe)
-- MAGIC
-- MAGIC **V3 rediseñada** según DT-F3.5-4: valida el universo COMPLETO, no solo
-- MAGIC el último mes con datos. Previene regresiones como la de F3 donde Silver
-- MAGIC perdió ~99.7% del histórico por un filtro destructivo no detectado.
-- MAGIC
-- MAGIC Estados documentados: 'B' es el estado dominante en sgHermes para facturas
-- MAGIC y compras válidas (~99.7% del total). 'A' representa un número menor.
-- MAGIC Se incluyen ambos para preservar el universo completo.

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 1 · Definir filtros canónicos
-- MAGIC
-- MAGIC Los mismos filtros que usan 10_fact_ventas.py y 12_fact_compras.py.

-- COMMAND ----------

-- Filtros canónicos para ventas y compras
-- Se declaran como CTE para mantenerlos en un solo lugar.
-- Ventas: estfven IN ('A','B'), fecfven NOT NULL, fecha >= 2020-01-01, <= today
-- Compras: estcom IN ('A','B'), feccom NOT NULL, fecha >= 2020-01-01, <= today

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 2 · Universo ventas: bronce completo vs silver completo

-- COMMAND ----------

WITH bronze_ventas AS (
  SELECT
    COUNT(*) AS total_rows,
    COALESCE(SUM(CAST(totfven AS DOUBLE)), 0) AS total_monetario
  FROM motoshop.bronze.facventas
  WHERE estfven IN ('A', 'B')
    AND fecfven IS NOT NULL
    AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
    AND CAST(fecfven AS DATE) <= CURRENT_DATE()
),
silver_ventas AS (
  SELECT
    COUNT(*) AS total_rows,
    COALESCE(SUM(total_factura), 0) AS total_monetario
  FROM motoshop.silver.fact_ventas
)
SELECT
  'VENTAS' AS seccion,
  b.total_rows AS bronze_rows,
  s.total_rows AS silver_rows,
  b.total_rows - s.total_rows AS diff_rows,
  CASE WHEN b.total_rows > 0
    THEN ROUND((b.total_rows - s.total_rows) * 100.0 / b.total_rows, 2)
    ELSE 0 END AS diff_rows_pct,
  b.total_monetario AS bronze_total,
  s.total_monetario AS silver_total,
  ROUND(b.total_monetario - s.total_monetario, 2) AS diff_monetario,
  CASE WHEN b.total_monetario > 0
    THEN ROUND(ABS(b.total_monetario - s.total_monetario) / b.total_monetario * 100, 4)
    ELSE 0 END AS diff_monetario_pct,
  CASE
    WHEN b.total_rows = s.total_rows AND ABS(b.total_monetario - s.total_monetario) / NULLIF(b.total_monetario, 0) < 0.005
    THEN '✅ PASS'
    ELSE '❌ FAIL'
  END AS status
FROM bronze_ventas b, silver_ventas s;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 3 · Universo compras: bronce completo vs silver completo

-- COMMAND ----------

WITH bronze_compras AS (
  SELECT
    COUNT(*) AS total_rows,
    COALESCE(SUM(CAST(totcom AS DOUBLE)), 0) AS total_monetario
  FROM motoshop.bronze.compras
  WHERE estcom IN ('A', 'B')
    AND feccom IS NOT NULL
    AND CAST(feccom AS DATE) >= DATE '2020-01-01'
    AND CAST(feccom AS DATE) <= CURRENT_DATE()
),
silver_compras AS (
  SELECT
    COUNT(*) AS total_rows,
    COALESCE(SUM(total_compra), 0) AS total_monetario
  FROM motoshop.silver.fact_compras
)
SELECT
  'COMPRAS' AS seccion,
  b.total_rows AS bronze_rows,
  s.total_rows AS silver_rows,
  b.total_rows - s.total_rows AS diff_rows,
  CASE WHEN b.total_rows > 0
    THEN ROUND((b.total_rows - s.total_rows) * 100.0 / b.total_rows, 2)
    ELSE 0 END AS diff_rows_pct,
  b.total_monetario AS bronze_total,
  s.total_monetario AS silver_total,
  ROUND(b.total_monetario - s.total_monetario, 2) AS diff_monetario,
  CASE WHEN b.total_monetario > 0
    THEN ROUND(ABS(b.total_monetario - s.total_monetario) / b.total_monetario * 100, 4)
    ELSE 0 END AS diff_monetario_pct,
  CASE
    WHEN b.total_rows = s.total_rows AND ABS(b.total_monetario - s.total_monetario) / NULLIF(b.total_monetario, 0) < 0.005
    THEN '✅ PASS'
    ELSE '❌ FAIL'
  END AS status
FROM bronze_compras b, silver_compras s;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 4 · Distribución por año-mes (ventas)
-- MAGIC
-- MAGIC Valida que cada (year, month) en Bronze tenga su equivalente en Silver.

-- COMMAND ----------

WITH bronze_dist AS (
  SELECT
    YEAR(CAST(fecfven AS DATE)) AS ano,
    MONTH(CAST(fecfven AS DATE)) AS mes,
    COUNT(*) AS n_bronze,
    COALESCE(SUM(CAST(totfven AS DOUBLE)), 0) AS t_bronze
  FROM motoshop.bronze.facventas
  WHERE estfven IN ('A', 'B')
    AND fecfven IS NOT NULL
    AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
    AND CAST(fecfven AS DATE) <= CURRENT_DATE()
  GROUP BY YEAR(CAST(fecfven AS DATE)), MONTH(CAST(fecfven AS DATE))
),
silver_dist AS (
  SELECT
    YEAR(business_date) AS ano,
    MONTH(business_date) AS mes,
    COUNT(*) AS n_silver,
    COALESCE(SUM(total_factura), 0) AS t_silver
  FROM motoshop.silver.fact_ventas
  GROUP BY YEAR(business_date), MONTH(business_date)
)
SELECT
  COALESCE(b.ano, s.ano) AS ano,
  COALESCE(b.mes, s.mes) AS mes,
  COALESCE(b.n_bronze, 0) AS bronze_rows,
  COALESCE(s.n_silver, 0) AS silver_rows,
  COALESCE(b.n_bronze, 0) - COALESCE(s.n_silver, 0) AS diff_rows,
  CASE WHEN COALESCE(b.n_bronze, 0) > 0
    THEN ROUND(ABS(COALESCE(b.n_bronze, 0) - COALESCE(s.n_silver, 0)) * 100.0 / b.n_bronze, 1)
    ELSE 0 END AS diff_pct,
  ROUND(COALESCE(b.t_bronze, 0), 2) AS bronze_total,
  ROUND(COALESCE(s.t_silver, 0), 2) AS silver_total,
  CASE WHEN COALESCE(b.n_bronze, 0) = COALESCE(s.n_silver, 0) THEN '✅' ELSE '⚠️' END AS match
FROM bronze_dist b
FULL OUTER JOIN silver_dist s ON b.ano = s.ano AND b.mes = s.mes
ORDER BY ano DESC, mes DESC;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 5 · Top 10 SKUs por ventas (universo completo)

-- COMMAND ----------

SELECT
  d.cod_producto,
  pr.nombre_producto,
  COUNT(DISTINCT d.num_documento) AS facturas,
  SUM(d.cantidad) AS cantidad_total,
  ROUND(SUM(d.total_detalle), 2) AS total_ventas
FROM motoshop.silver.fact_ventas_detalle d
INNER JOIN motoshop.silver.fact_ventas h
  ON d.num_documento = h.num_documento AND d.cod_clase = h.cod_clase
LEFT JOIN motoshop.silver.dim_producto pr ON d.cod_producto = pr.cod_producto
GROUP BY d.cod_producto, pr.nombre_producto
ORDER BY total_ventas DESC
LIMIT 10;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 6 · Top 5 clientes (universo completo)

-- COMMAND ----------

SELECT
  h.nit_cliente,
  tc.nombre_completo,
  COUNT(*) AS facturas,
  ROUND(SUM(h.total_factura), 2) AS total_compras
FROM motoshop.silver.fact_ventas h
LEFT JOIN motoshop.silver.dim_tercero tc ON h.nit_cliente = tc.nit_tercero
GROUP BY h.nit_cliente, tc.nombre_completo
ORDER BY total_compras DESC
LIMIT 5;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## 7 · Conteos generales de todas las tablas silver

-- COMMAND ----------

SELECT
  'bronze_facventas' AS tabla, COUNT(*) AS rows FROM motoshop.bronze.facventas WHERE estfven IN ('A', 'B')
UNION ALL SELECT 'silver_fact_ventas', COUNT(*) FROM motoshop.silver.fact_ventas
UNION ALL SELECT 'silver_fact_ventas_detalle', COUNT(*) FROM motoshop.silver.fact_ventas_detalle
UNION ALL SELECT 'bronze_compras', COUNT(*) FROM motoshop.bronze.compras WHERE estcom IN ('A', 'B')
UNION ALL SELECT 'silver_fact_compras', COUNT(*) FROM motoshop.silver.fact_compras
UNION ALL SELECT 'silver_fact_compras_detalle', COUNT(*) FROM motoshop.silver.fact_compras_detalle
UNION ALL SELECT 'silver_fact_inventario', COUNT(*) FROM motoshop.silver.fact_inventario
UNION ALL SELECT 'silver_dim_producto', COUNT(*) FROM motoshop.silver.dim_producto
UNION ALL SELECT 'silver_dim_bodega', COUNT(*) FROM motoshop.silver.dim_bodega
UNION ALL SELECT 'silver_dim_tercero', COUNT(*) FROM motoshop.silver.dim_tercero
UNION ALL SELECT 'silver_dim_sucursal', COUNT(*) FROM motoshop.silver.dim_sucursal
UNION ALL SELECT 'silver_dim_formapago', COUNT(*) FROM motoshop.silver.dim_formapago
UNION ALL SELECT 'silver_dim_tiempo', COUNT(*) FROM motoshop.silver.dim_tiempo
ORDER BY tabla;
