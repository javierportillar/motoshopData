-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 31 · Snapshot mensual — mart_productos_dormidos → gold.mart_productos_dormidos_snapshots
-- MAGIC
-- MAGIC Copia idempotente de `mart_productos_dormidos` al final de cada mes.
-- MAGIC Si ya existe snapshot para `snapshot_month = yyyy-MM` actual, no inserta.
-- MAGIC
-- MAGIC **Schedule:** mensual (día 1 de cada mes, después del workflow gold).
-- MAGIC **Balde B:** alimenta D5 (histórico: cuándo entró en dormido) en dashboards/dormidos.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · DDL — gold.mart_productos_dormidos_snapshots

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_productos_dormidos_snapshots (
  cod_producto STRING,
  nom_producto STRING,
  cod_bodega STRING,
  ultima_fecha_venta DATE,
  dias_sin_venta INT,
  stock_actual DOUBLE,
  categoria STRING,
  snapshot_month STRING
) USING DELTA PARTITIONED BY (snapshot_month);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · INSERT idempotente (salta si snapshot_month ya existe)

-- COMMAND ----------

INSERT INTO motoshop.gold.mart_productos_dormidos_snapshots
SELECT
  m.cod_producto,
  m.nom_producto,
  m.cod_bodega,
  m.ultima_fecha_venta,
  m.dias_sin_venta,
  m.stock_actual,
  m.categoria,
  DATE_FORMAT(CURRENT_DATE(), 'yyyy-MM') AS snapshot_month
FROM motoshop.gold.mart_productos_dormidos m
LEFT ANTI JOIN (
  SELECT DISTINCT snapshot_month
  FROM motoshop.gold.mart_productos_dormidos_snapshots
  WHERE snapshot_month = DATE_FORMAT(CURRENT_DATE(), 'yyyy-MM')
) existentes
  ON 1 = 1;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación — conteos snapshot

-- COMMAND ----------

SELECT
  snapshot_month,
  COUNT(*) AS filas,
  SUM(CASE WHEN categoria = 'dormido_con_stock' THEN 1 ELSE 0 END) AS con_stock,
  SUM(CASE WHEN categoria = 'dormido_sin_stock' THEN 1 ELSE 0 END) AS sin_stock,
  ROUND(SUM(stock_actual), 2) AS unidades_inmovilizadas
FROM motoshop.gold.mart_productos_dormidos_snapshots
GROUP BY snapshot_month
ORDER BY snapshot_month DESC
LIMIT 12;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Top 10 dormidos con mayor valor inmovilizado (snapshot actual)

-- COMMAND ----------

SELECT
  cod_producto,
  nom_producto,
  cod_bodega,
  dias_sin_venta,
  stock_actual,
  categoria
FROM motoshop.gold.mart_productos_dormidos_snapshots
WHERE snapshot_month = DATE_FORMAT(CURRENT_DATE(), 'yyyy-MM')
  AND categoria = 'dormido_con_stock'
ORDER BY stock_actual DESC
LIMIT 10;
