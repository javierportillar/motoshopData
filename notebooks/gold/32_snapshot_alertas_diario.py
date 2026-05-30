-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 32 · Snapshot diario — gold.alertas_quiebre → gold.alertas_quiebre_snapshots
-- MAGIC
-- MAGIC Copia idempotente de `alertas_quiebre` cada día.
-- MAGIC Si ya existe snapshot para `snapshot_date = CURRENT_DATE()`, no inserta.
-- MAGIC
-- MAGIC **Schedule:** diario (después del workflow gold, 02:30 COL).
-- MAGIC **Balde B:** alimenta AL5 (histórico alertas por día últimos 30d) en dashboards/alerts.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · DDL — gold.alertas_quiebre_snapshots

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.alertas_quiebre_snapshots (
  sku STRING,
  nom_producto STRING,
  stock_actual DOUBLE,
  demanda_predicha DOUBLE,
  dias_hasta_quiebre DOUBLE,
  urgencia STRING,
  business_date DATE,
  snapshot_date DATE
) USING DELTA PARTITIONED BY (snapshot_date);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · INSERT idempotente (salta si snapshot_date ya existe)

-- COMMAND ----------

INSERT INTO motoshop.gold.alertas_quiebre_snapshots
SELECT
  a.sku,
  a.nom_producto,
  a.stock_actual,
  a.demanda_predicha,
  a.dias_hasta_quiebre,
  a.urgencia,
  a.business_date,
  CURRENT_DATE() AS snapshot_date
FROM motoshop.gold.alertas_quiebre a
LEFT ANTI JOIN (
  SELECT DISTINCT snapshot_date
  FROM motoshop.gold.alertas_quiebre_snapshots
  WHERE snapshot_date = CURRENT_DATE()
) existentes
  ON 1 = 1;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación — conteos diarios (últimos 30 días)

-- COMMAND ----------

SELECT
  snapshot_date,
  COUNT(*) AS total_alertas,
  SUM(CASE WHEN urgencia = 'alta' THEN 1 ELSE 0 END) AS alta,
  SUM(CASE WHEN urgencia = 'media' THEN 1 ELSE 0 END) AS media,
  SUM(CASE WHEN urgencia = 'baja' THEN 1 ELSE 0 END) AS baja
FROM motoshop.gold.alertas_quiebre_snapshots
WHERE snapshot_date >= DATE_SUB(CURRENT_DATE(), 30)
GROUP BY snapshot_date
ORDER BY snapshot_date DESC;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Alertas de hoy (si existen)

-- COMMAND ----------

SELECT
  urgencia,
  sku,
  nom_producto,
  ROUND(stock_actual, 2) AS stock,
  ROUND(demanda_predicha, 2) AS demanda,
  ROUND(dias_hasta_quiebre, 1) AS dias_para_quiebre
FROM motoshop.gold.alertas_quiebre_snapshots
WHERE snapshot_date = CURRENT_DATE()
ORDER BY
  CASE urgencia
    WHEN 'alta' THEN 1
    WHEN 'media' THEN 2
    WHEN 'baja' THEN 3
  END,
  dias_hasta_quiebre ASC
LIMIT 20;
