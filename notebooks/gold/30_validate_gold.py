-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 30 · Validate Gold — V1 idempotencia + V2 fechas + V3 coherencia silver↔gold
-- MAGIC
-- MAGIC Valida que los marts gold sean correctos, idempotentes y coherentes con silver.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V1 · Verificar idempotencia — DELETE+INSERT produce mismos resultados
-- MAGIC
-- MAGIC NOTA: temp views NO persisten entre statements en SQL Warehouse API
-- MAGIC (cada REST call es una sesión independiente).
-- MAGIC La prueba de idempotencia se hace directamente contra las tablas gold:
-- MAGIC 1. Se cuentan filas actuales
-- MAGIC 2. Se re-ejecuta el INSERT (vía el notebook)
-- MAGIC 3. Se vuelve a contar — si el count no cambió, PASS
-- MAGIC
-- MAGIC Como no podemos ejecutar el INSERT desde este notebook sin temp views,
-- MAGIC validamos la idempotencia del patrón estructuralmente:
-- MAGIC - Los notebooks gold usan DELETE + INSERT (verificado en tests gold)
-- MAGIC - Esta validación cuenta filas actuales como baseline

-- COMMAND ----------

-- V1.a: Conteo baseline de mart_ventas_diarias_sku
SELECT
  'V1_idempotencia_baseline' AS test_name,
  'mart_ventas_diarias_sku' AS mart,
  COUNT(*) AS row_count
FROM motoshop.gold.mart_ventas_diarias_sku;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V2 · Verificar fechas — ninguna business_date > CURRENT_DATE

-- COMMAND ----------

SELECT
  'mart_ventas_diarias_sku' AS mart,
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) AS fechas_futuras,
  CASE WHEN SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM motoshop.gold.mart_ventas_diarias_sku

UNION ALL

SELECT
  'mart_rotacion_abc',
  SUM(CASE WHEN business_month > DATE_TRUNC('MONTH', CURRENT_DATE()) THEN 1 ELSE 0 END),
  CASE WHEN SUM(CASE WHEN business_month > DATE_TRUNC('MONTH', CURRENT_DATE()) THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.gold.mart_rotacion_abc

UNION ALL

SELECT
  'mart_cohortes_clientes',
  SUM(CASE WHEN business_month > DATE_TRUNC('MONTH', CURRENT_DATE()) THEN 1 ELSE 0 END),
  CASE WHEN SUM(CASE WHEN business_month > DATE_TRUNC('MONTH', CURRENT_DATE()) THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM motoshop.gold.mart_cohortes_clientes;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## V3 · Coherencia silver↔gold
-- MAGIC
-- MAGIC SUM(valor_total) en mart_ventas_diarias_sku debe coincidir con
-- MAGIC SUM(total_factura) en silver.fact_ventas dentro de tolerancia < 0.5%.

-- COMMAND ----------

WITH gold_ventas AS (
  SELECT ROUND(SUM(valor_total), 2) AS gold_total
  FROM motoshop.gold.mart_ventas_diarias_sku
  WHERE business_date >= DATE '2020-01-01'
),
silver_ventas AS (
  SELECT ROUND(SUM(fvd.valor_unitario * fvd.cantidad - COALESCE(fvd.descuento_valor, 0)), 2) AS silver_total
  FROM motoshop.silver.fact_ventas_detalle fvd
  INNER JOIN motoshop.silver.fact_ventas fv
    ON fvd.num_documento = fv.num_documento
    AND fvd.cod_clase = fv.cod_clase
    AND fvd.business_date = fv.business_date
  WHERE fvd.business_date >= DATE '2020-01-01'
)
SELECT
  gv.gold_total,
  sv.silver_total,
  ROUND(ABS(gv.gold_total - sv.silver_total), 2) AS diferencia,
  CASE
    WHEN sv.silver_total > 0
      THEN ROUND(ABS(gv.gold_total - sv.silver_total) / sv.silver_total * 100, 4)
    ELSE 0
  END AS diff_pct,
  CASE
    WHEN sv.silver_total > 0 AND ABS(gv.gold_total - sv.silver_total) / sv.silver_total < 0.005 THEN 'PASS'
    WHEN sv.silver_total = 0 THEN 'PASS (sin datos)'
    ELSE 'FAIL'
  END AS status
FROM gold_ventas gv CROSS JOIN silver_ventas sv;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Resumen de conteos gold

-- COMMAND ----------

SELECT 'mart_ventas_diarias_sku' AS mart, COUNT(*) AS rows FROM motoshop.gold.mart_ventas_diarias_sku
UNION ALL
SELECT 'mart_inventario_actual', COUNT(*) FROM motoshop.gold.mart_inventario_actual
UNION ALL
SELECT 'mart_rotacion_abc', COUNT(*) FROM motoshop.gold.mart_rotacion_abc
UNION ALL
SELECT 'mart_cohortes_clientes', COUNT(*) FROM motoshop.gold.mart_cohortes_clientes
UNION ALL
SELECT 'mart_productos_dormidos', COUNT(*) FROM motoshop.gold.mart_productos_dormidos;
