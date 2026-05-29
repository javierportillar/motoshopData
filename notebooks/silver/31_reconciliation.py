-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 31 · Reconciliation — Silver vs Bronze (proxy sgHermes)
-- MAGIC
-- MAGIC V3: Compara totales de silver con bronze.
-- MAGIC Tolerancia: < 0.5%.
-- MAGIC Mes usado: último mes con datos (no "mes pasado" que puede estar vacío).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Determinar el mes con datos

-- COMMAND ----------

SELECT
  'metadata' AS seccion,
  DATE_TRUNC('MONTH', MAX(fecfven)) AS mes_usado_start,
  LAST_DAY(MAX(fecfven)) AS mes_usado_end,
  COUNT(*) AS facturas_en_mes,
  'Se usa el último mes con datos, no mes actual (que puede estar vacío)' AS nota
FROM motoshop.bronze.facventas
WHERE estfven = 'A';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · Reconciliación fact_ventas (último mes con datos)

-- COMMAND ----------

WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
),
bv AS (
  SELECT COUNT(*) AS n, COALESCE(SUM(CAST(totfven AS DOUBLE)), 0) AS t
  FROM motoshop.bronze.facventas, last_month p
  WHERE estfven = 'A' AND CAST(fecfven AS DATE) >= ms AND CAST(fecfven AS DATE) <= me
),
sv AS (
  SELECT COUNT(*) AS n, COALESCE(SUM(total_factura), 0) AS t
  FROM motoshop.silver.fact_ventas, last_month p
  WHERE business_date >= ms AND business_date <= me
)
SELECT
  b.n AS bronze_facturas,
  s.n AS silver_facturas,
  b.t AS bronze_total,
  s.t AS silver_total,
  ABS(b.t - s.t) AS diff_abs,
  CASE WHEN b.t > 0 THEN ROUND(ABS(b.t - s.t) / b.t * 100, 2) ELSE 0 END AS diff_pct,
  CASE WHEN ABS(b.t - s.t) / NULLIF(b.t, 0) < 0.005 THEN 'PASS' ELSE 'FAIL' END AS status
FROM bv b, sv s;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Reconciliación fact_compras (último mes con datos)

-- COMMAND ----------

WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
),
bc AS (
  SELECT COUNT(*) AS n, COALESCE(SUM(CAST(totcom AS DOUBLE)), 0) AS t
  FROM motoshop.bronze.compras, last_month p
  WHERE estcom = 'A' AND CAST(feccom AS DATE) >= ms AND CAST(feccom AS DATE) <= me
),
sc AS (
  SELECT COUNT(*) AS n, COALESCE(SUM(total_compra), 0) AS t
  FROM motoshop.silver.fact_compras, last_month p
  WHERE business_date >= ms AND business_date <= me
)
SELECT
  b.n AS bronze_compras,
  s.n AS silver_compras,
  b.t AS bronze_total,
  s.t AS silver_total,
  ABS(b.t - s.t) AS diff_abs,
  CASE WHEN b.t > 0 THEN ROUND(ABS(b.t - s.t) / b.t * 100, 2) ELSE 0 END AS diff_pct,
  CASE WHEN ABS(b.t - s.t) / NULLIF(b.t, 0) < 0.005 THEN 'PASS' ELSE 'FAIL' END AS status
FROM bc b, sc s;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Top 10 SKUs por ventas (último mes con datos)

-- COMMAND ----------

WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
)
SELECT
  d.cod_producto,
  pr.nombre_producto,
  COUNT(DISTINCT d.num_documento) AS facturas,
  SUM(d.cantidad) AS cantidad_total,
  SUM(d.total_detalle) AS total_ventas
FROM motoshop.silver.fact_ventas_detalle d
INNER JOIN motoshop.silver.fact_ventas h
  ON d.num_documento = h.num_documento AND d.cod_clase = h.cod_clase
LEFT JOIN motoshop.silver.dim_producto pr ON d.cod_producto = pr.cod_producto
, last_month lm
WHERE h.business_date >= lm.ms AND h.business_date <= lm.me
GROUP BY d.cod_producto, pr.nombre_producto
ORDER BY total_ventas DESC
LIMIT 10;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5 · Top 5 clientes por compras

-- COMMAND ----------

WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
)
SELECT
  h.nit_cliente,
  tc.nombre_completo,
  COUNT(*) AS facturas,
  SUM(h.total_factura) AS total_compras
FROM motoshop.silver.fact_ventas h
LEFT JOIN motoshop.silver.dim_tercero tc ON h.nit_cliente = tc.nit_tercero
, last_month lm
WHERE h.business_date >= lm.ms AND h.business_date <= lm.me
GROUP BY h.nit_cliente, tc.nombre_completo
ORDER BY total_compras DESC
LIMIT 5;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 6 · Conteos generales

-- COMMAND ----------

SELECT
  'bronze_facventas' AS tabla, COUNT(*) AS rows FROM motoshop.bronze.facventas WHERE estfven = 'A'
UNION ALL SELECT 'silver_fact_ventas', COUNT(*) FROM motoshop.silver.fact_ventas
UNION ALL SELECT 'silver_fact_ventas_detalle', COUNT(*) FROM motoshop.silver.fact_ventas_detalle
UNION ALL SELECT 'bronze_compras', COUNT(*) FROM motoshop.bronze.compras WHERE estcom = 'A'
UNION ALL SELECT 'silver_fact_compras', COUNT(*) FROM motoshop.silver.fact_compras
UNION ALL SELECT 'silver_fact_compras_detalle', COUNT(*) FROM motoshop.silver.fact_compras_detalle
UNION ALL SELECT 'silver_fact_inventario', COUNT(*) FROM motoshop.silver.fact_inventario
UNION ALL SELECT 'silver_dim_producto', COUNT(*) FROM motoshop.silver.dim_producto
UNION ALL SELECT 'silver_dim_bodega', COUNT(*) FROM motoshop.silver.dim_bodega
UNION ALL SELECT 'silver_dim_tercero', COUNT(*) FROM motoshop.silver.dim_tercero
UNION ALL SELECT 'silver_dim_sucursal', COUNT(*) FROM motoshop.silver.dim_sucursal
UNION ALL SELECT 'silver_dim_formapago', COUNT(*) FROM motoshop.silver.dim_formapago
UNION ALL SELECT 'silver_dim_tiempo', COUNT(*) FROM motoshop.silver.dim_tiempo;
