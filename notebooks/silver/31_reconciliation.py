-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 31 · Reconciliation — Silver vs Bronze (proxy sgHermes)
-- MAGIC
-- MAGIC V3: Compara totales de silver con bronze. Tolerancia: < 0.5%.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Reconciliación fact_ventas (mes pasado)

-- COMMAND ----------

WITH params AS (
  SELECT
    DATE_TRUNC('MONTH', DATE_SUB(CURRENT_DATE(), 1)) AS month_start,
    LAST_DAY(DATE_SUB(CURRENT_DATE(), 1)) AS month_end
),
bronze_ventas AS (
  SELECT
    COUNT(*) AS facturas,
    COALESCE(SUM(CAST(totfven AS DOUBLE)), 0) AS total_ventas
  FROM motoshop.bronze.facventas, params p
  WHERE estfven = 'A'
    AND CAST(fecfven AS DATE) >= p.month_start
    AND CAST(fecfven AS DATE) <= p.month_end
),
silver_ventas AS (
  SELECT
    COUNT(*) AS facturas,
    COALESCE(SUM(total_factura), 0) AS total_ventas
  FROM motoshop.silver.fact_ventas, params p
  WHERE business_date >= p.month_start
    AND business_date <= p.month_end
)
SELECT
  b.facturas AS bronze_facturas,
  s.facturas AS silver_facturas,
  b.total_ventas AS bronze_total,
  s.total_ventas AS silver_total,
  ABS(b.total_ventas - s.total_ventas) AS diferencia_abs,
  CASE WHEN b.total_ventas > 0
    THEN ROUND(ABS(b.total_ventas - s.total_ventas) / b.total_ventas * 100, 2)
    ELSE 0
  END AS diferencia_pct,
  CASE WHEN ABS(b.total_ventas - s.total_ventas) / NULLIF(b.total_ventas, 0) < 0.005
    THEN 'PASS' ELSE 'FAIL'
  END AS status
FROM bronze_ventas b, silver_ventas s;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · Reconciliación fact_compras (mes pasado)

-- COMMAND ----------

WITH params AS (
  SELECT
    DATE_TRUNC('MONTH', DATE_SUB(CURRENT_DATE(), 1)) AS month_start,
    LAST_DAY(DATE_SUB(CURRENT_DATE(), 1)) AS month_end
),
bronze_compras AS (
  SELECT
    COUNT(*) AS compras,
    COALESCE(SUM(CAST(totcom AS DOUBLE)), 0) AS total_compras
  FROM motoshop.bronze.compras, params p
  WHERE estcom = 'A'
    AND CAST(feccom AS DATE) >= p.month_start
    AND CAST(feccom AS DATE) <= p.month_end
),
silver_compras AS (
  SELECT
    COUNT(*) AS compras,
    COALESCE(SUM(total_compra), 0) AS total_compras
  FROM motoshop.silver.fact_compras, params p
  WHERE business_date >= p.month_start
    AND business_date <= p.month_end
)
SELECT
  b.compras AS bronze_compras,
  s.compras AS silver_compras,
  b.total_compras AS bronze_total,
  s.total_compras AS silver_total,
  ABS(b.total_compras - s.total_compras) AS diferencia_abs,
  CASE WHEN b.total_compras > 0
    THEN ROUND(ABS(b.total_compras - s.total_compras) / b.total_compras * 100, 2)
    ELSE 0
  END AS diferencia_pct,
  CASE WHEN ABS(b.total_compras - s.total_compras) / NULLIF(b.total_compras, 0) < 0.005
    THEN 'PASS' ELSE 'FAIL'
  END AS status
FROM bronze_compras b, silver_compras s;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Top 10 SKUs por ventas (mes pasado)

-- COMMAND ----------

WITH params AS (
  SELECT
    DATE_TRUNC('MONTH', DATE_SUB(CURRENT_DATE(), 1)) AS month_start,
    LAST_DAY(DATE_SUB(CURRENT_DATE(), 1)) AS month_end
)
SELECT
  d.cod_producto,
  SUM(d.total_detalle) AS total_ventas
FROM motoshop.silver.fact_ventas_detalle d, params p
WHERE d.business_date >= p.month_start
  AND d.business_date <= p.month_end
GROUP BY d.cod_producto
ORDER BY total_ventas DESC
LIMIT 10;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Conteos generales

-- COMMAND ----------

SELECT
  'bronze_facventas' AS tabla, COUNT(*) AS rows FROM motoshop.bronze.facventas WHERE estfven = 'A'
UNION ALL SELECT 'silver_fact_ventas', COUNT(*) FROM motoshop.silver.fact_ventas
UNION ALL SELECT 'bronze_compras', COUNT(*) FROM motoshop.bronze.compras WHERE estcom = 'A'
UNION ALL SELECT 'silver_fact_compras', COUNT(*) FROM motoshop.silver.fact_compras
UNION ALL SELECT 'silver_dim_producto', COUNT(*) FROM motoshop.silver.dim_producto
UNION ALL SELECT 'silver_dim_bodega', COUNT(*) FROM motoshop.silver.dim_bodega
UNION ALL SELECT 'silver_dim_tercero', COUNT(*) FROM motoshop.silver.dim_tercero
UNION ALL SELECT 'silver_dim_sucursal', COUNT(*) FROM motoshop.silver.dim_sucursal
UNION ALL SELECT 'silver_dim_formapago', COUNT(*) FROM motoshop.silver.dim_formapago
UNION ALL SELECT 'silver_dim_tiempo', COUNT(*) FROM motoshop.silver.dim_tiempo;
