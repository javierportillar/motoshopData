-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 20 · Quality Gold — Reglas de calidad gold marts
-- MAGIC
-- MAGIC Valida cada mart gold. Si hay reglas CRITICAL, el notebook falla.
-- MAGIC Misma estructura que notebooks/silver/20_quality_run.py pero para gold.

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold._quality_runs (
  run_id STRING,
  table_name STRING,
  rule STRING,
  failed_rows BIGINT,
  severity STRING,
  timestamp TIMESTAMP
) USING DELTA;

-- COMMAND ----------

DELETE FROM motoshop.gold._quality_runs WHERE 1=1;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## mart_ventas_diarias_sku: checks

-- COMMAND ----------

-- PK nula
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_ventas_diarias_sku', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_ventas_diarias_sku
WHERE business_date IS NULL OR cod_producto IS NULL OR cod_bodega IS NULL
HAVING COUNT(*) > 0;

-- Valores negativos
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_ventas_diarias_sku', 'negative_cantidad_total', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_ventas_diarias_sku
WHERE cantidad_total < 0
HAVING COUNT(*) > 0;

INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_ventas_diarias_sku', 'negative_valor_total', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_ventas_diarias_sku
WHERE valor_total < 0
HAVING COUNT(*) > 0;

-- Fechas futuras
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_ventas_diarias_sku', 'future_business_date', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_ventas_diarias_sku
WHERE business_date > CURRENT_DATE()
HAVING COUNT(*) > 0;

-- Mart vacío
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_ventas_diarias_sku', 'empty_mart', 1, 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_ventas_diarias_sku
HAVING COUNT(*) = 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## mart_inventario_actual: checks

-- COMMAND ----------

-- PK nula
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_inventario_actual', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_inventario_actual
WHERE cod_producto IS NULL OR cod_bodega IS NULL
HAVING COUNT(*) > 0;

-- Cantidad negativa
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_inventario_actual', 'negative_cantidad', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_inventario_actual
WHERE cantidad_actual < 0
HAVING COUNT(*) > 0;

-- Mart vacío
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_inventario_actual', 'empty_mart', 1, 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_inventario_actual
HAVING COUNT(*) = 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## mart_rotacion_abc: checks

-- COMMAND ----------

-- PK nula
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_rotacion_abc', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_rotacion_abc
WHERE business_month IS NULL OR cod_producto IS NULL
HAVING COUNT(*) > 0;

-- Valor total negativo
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_rotacion_abc', 'negative_valor_total', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_rotacion_abc
WHERE valor_total < 0
HAVING COUNT(*) > 0;

-- Categoría inválida
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_rotacion_abc', 'invalid_categoria', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_rotacion_abc
WHERE categoria_abc NOT IN ('A', 'B', 'C')
HAVING COUNT(*) > 0;

-- Fechas futuras
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_rotacion_abc', 'future_business_month', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_rotacion_abc
WHERE business_month > DATE_TRUNC('MONTH', CURRENT_DATE())
HAVING COUNT(*) > 0;

-- Mart vacío
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_rotacion_abc', 'empty_mart', 1, 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_rotacion_abc
HAVING COUNT(*) = 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## mart_cohortes_clientes: checks

-- COMMAND ----------

-- PK nula
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_cohortes_clientes', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_cohortes_clientes
WHERE business_month IS NULL OR nit_cliente IS NULL
HAVING COUNT(*) > 0;

-- Ingresos negativos
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_cohortes_clientes', 'negative_ingresos', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_cohortes_clientes
WHERE ingresos_totales < 0
HAVING COUNT(*) > 0;

-- Ticket promedio negativo
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_cohortes_clientes', 'negative_ticket', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_cohortes_clientes
WHERE ticket_promedio < 0
HAVING COUNT(*) > 0;

-- Fechas futuras
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_cohortes_clientes', 'future_business_month', COUNT(*), 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_cohortes_clientes
WHERE business_month > DATE_TRUNC('MONTH', CURRENT_DATE())
HAVING COUNT(*) > 0;

-- Mart vacío
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_cohortes_clientes', 'empty_mart', 1, 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_cohortes_clientes
HAVING COUNT(*) = 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## mart_productos_dormidos: checks

-- COMMAND ----------

-- PK nula
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_productos_dormidos', 'null_pk', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_productos_dormidos
WHERE cod_producto IS NULL OR cod_bodega IS NULL
HAVING COUNT(*) > 0;

-- Días sin venta negativos (excluye sentinel 99999 = nunca vendido)
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_productos_dormidos', 'negative_dias_sin_venta', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_productos_dormidos
WHERE dias_sin_venta < 0 AND dias_sin_venta != 99999
HAVING COUNT(*) > 0;

-- Stock negativo
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_productos_dormidos', 'negative_stock', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_productos_dormidos
WHERE stock_actual < 0
HAVING COUNT(*) > 0;

-- Categoría inválida
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_productos_dormidos', 'invalid_categoria', COUNT(*), 'CRITICAL', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_productos_dormidos
WHERE categoria NOT IN ('dormido_con_stock', 'dormido_sin_stock')
HAVING COUNT(*) > 0;

-- Mart vacío
INSERT INTO motoshop.gold._quality_runs
SELECT UUID(),
  'mart_productos_dormidos', 'empty_mart', 1, 'WARNING', CURRENT_TIMESTAMP()
FROM motoshop.gold.mart_productos_dormidos
HAVING COUNT(*) = 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## ASSERT: fallar si hay errores CRITICAL

-- COMMAND ----------

SELECT assert_true(
  (SELECT COUNT(*) FROM motoshop.gold._quality_runs WHERE severity = 'CRITICAL') = 0,
  CONCAT('Quality gold encontró ', CAST((SELECT COUNT(*) FROM motoshop.gold._quality_runs WHERE severity = 'CRITICAL') AS STRING), ' errores CRITICAL')
) AS assert_no_critical_errors;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Resumen

-- COMMAND ----------

SELECT table_name, rule, failed_rows, severity, timestamp
FROM motoshop.gold._quality_runs
ORDER BY severity DESC, table_name;
