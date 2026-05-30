-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 30 · Snapshot mensual — mart_rotacion_abc → gold.mart_rotacion_abc_snapshots
-- MAGIC
-- MAGIC Copia idempotente de `mart_rotacion_abc` al final de cada mes.
-- MAGIC Si ya existe snapshot para `snapshot_month = yyyy-MM` actual, no inserta.
-- MAGIC
-- MAGIC **Schedule:** mensual (día 1 de cada mes, después del workflow gold).
-- MAGIC **Balde B:** alimenta A2 (migración mensual A→B→C) en dashboards/abc.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · DDL — gold.mart_rotacion_abc_snapshots

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_rotacion_abc_snapshots (
  business_month DATE,
  cod_producto STRING,
  nom_producto STRING,
  valor_total DOUBLE,
  porcentaje_acumulado DOUBLE,
  categoria_abc STRING,
  snapshot_month STRING
) USING DELTA PARTITIONED BY (snapshot_month);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · INSERT idempotente (salta si snapshot_month ya existe)

-- COMMAND ----------

INSERT INTO motoshop.gold.mart_rotacion_abc_snapshots
SELECT
  m.business_month,
  m.cod_producto,
  m.nom_producto,
  m.valor_total,
  m.porcentaje_acumulado,
  m.categoria_abc,
  DATE_FORMAT(CURRENT_DATE(), 'yyyy-MM') AS snapshot_month
FROM motoshop.gold.mart_rotacion_abc m
LEFT ANTI JOIN (
  SELECT DISTINCT snapshot_month
  FROM motoshop.gold.mart_rotacion_abc_snapshots
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
  COUNT(DISTINCT cod_producto) AS skus,
  COUNT(DISTINCT business_month) AS meses_en_ventana
FROM motoshop.gold.mart_rotacion_abc_snapshots
GROUP BY snapshot_month
ORDER BY snapshot_month DESC
LIMIT 12;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Distribución ABC más reciente

-- COMMAND ----------

SELECT
  categoria_abc,
  COUNT(*) AS skus,
  ROUND(SUM(valor_total), 2) AS valor_total
FROM motoshop.gold.mart_rotacion_abc_snapshots
WHERE snapshot_month = DATE_FORMAT(CURRENT_DATE(), 'yyyy-MM')
GROUP BY categoria_abc
ORDER BY categoria_abc;
