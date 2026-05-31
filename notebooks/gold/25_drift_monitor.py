-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 25 · Drift Monitor — Baseline WAPE Tracking
-- MAGIC
-- MAGIC Monitorea degradación del baseline de forecasting.
-- MAGIC
-- MAGIC Lógica:
-- MAGIC 1. Computa WAPE semanal de `gold.forecast_baseline_sku` para las últimas 8 semanas.
-- MAGIC 2. Compara la semana más reciente contra el promedio de las 4 semanas anteriores.
-- MAGIC 3. Si la desviación > 30%, escribe alerta en `gold.alertas_drift`.
-- MAGIC 4. Limpia alertas anteriores de la misma semana (upsert por week_end).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 1: Crear tabla de alertas si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.alertas_drift (
  week_end DATE,
  wape_actual DOUBLE,
  wape_historico DOUBLE,
  desviacion_pct DOUBLE,
  threshold_pct DOUBLE,
  severity STRING,
  alert_msg STRING,
  created_at TIMESTAMP
) USING DELTA;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 2: Computar WAPE semanal para las últimas 8 semanas
-- MAGIC
-- MAGIC WAPE = SUM(ABS(demanda_real - demanda_predicha)) / SUM(demanda_real)
-- MAGIC Solo considera SKUs con demanda_real > 0.

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW weekly_wape AS
WITH
semanas AS (
  SELECT DISTINCT
    CAST(DATE_TRUNC('WEEK', business_date) AS DATE) + 6 AS week_end,
    business_date
  FROM motoshop.gold.forecast_baseline_sku
  WHERE business_date >= DATE_ADD(CURRENT_DATE, -56)  -- últimas 8 semanas
),
baseline_errors AS (
  SELECT
    s.week_end,
    f.cod_producto,
    COALESCE(f.demanda_real, 0) AS demanda_real,
    COALESCE(f.demanda_predicha, 0) AS demanda_predicha
  FROM motoshop.gold.forecast_baseline_sku f
  INNER JOIN semanas s
    ON f.business_date = s.business_date
  WHERE f.demanda_real > 0
)
SELECT
  week_end,
  ROUND(SUM(ABS(demanda_real - demanda_predicha)) / NULLIF(SUM(demanda_real), 0) * 100, 2) AS wape_pct
FROM baseline_errors
GROUP BY week_end
ORDER BY week_end DESC;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 3: Detectar drift
-- MAGIC
-- MAGIC Compara la última semana (más reciente) vs promedio de las 4 anteriores.
-- MAGIC Si desviación > 30%, es alerta. Severidad HIGH si > 50%, MEDIUM si > 30%.

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW drift_detection AS
WITH
ranked AS (
  SELECT
    week_end,
    wape_pct,
    ROW_NUMBER() OVER (ORDER BY week_end DESC) AS rn
  FROM weekly_wape
),
current_week AS (
  SELECT week_end, wape_pct
  FROM ranked WHERE rn = 1
),
historical_weeks AS (
  SELECT AVG(wape_pct) AS avg_wape
  FROM ranked WHERE rn BETWEEN 2 AND 5  -- 4 semanas antes de la actual
)
SELECT
  cw.week_end,
  cw.wape_pct AS wape_actual,
  ROUND(hw.avg_wape, 2) AS wape_historico,
  CASE
    WHEN hw.avg_wape IS NULL OR hw.avg_wape = 0 THEN NULL
    ELSE ROUND(ABS(cw.wape_pct - hw.avg_wape) / hw.avg_wape * 100, 2)
  END AS desviacion_pct,
  30.0 AS threshold_pct,
  CASE
    WHEN hw.avg_wape IS NULL THEN 'UNKNOWN'
    WHEN cw.wape_pct > hw.avg_wape * 1.5 THEN 'HIGH'
    WHEN cw.wape_pct > hw.avg_wape * 1.3 THEN 'MEDIUM'
    ELSE 'OK'
  END AS severity
FROM current_week cw
CROSS JOIN historical_weeks hw;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 4: Guard — verificar si hay datos antes de insertar
-- MAGIC
-- MAGIC Si no hay semanas con datos (primeras corridas), insertar un registro informativo.

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW has_drift_data AS
SELECT COUNT(*) > 0 AS has_data FROM drift_detection;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 5: Insertar alerta si hay drift

-- COMMAND ----------

INSERT INTO motoshop.gold.alertas_drift
SELECT
  week_end,
  wape_actual,
  wape_historico,
  desviacion_pct,
  threshold_pct,
  severity,
  CASE
    WHEN severity = 'HIGH'   THEN CONCAT('⚠️ Drift ALTO: WAPE ', wape_actual, '% vs histórico ', wape_historico, '% (desviación ', desviacion_pct, '%)')
    WHEN severity = 'MEDIUM' THEN CONCAT('⚠️ Drift MEDIO: WAPE ', wape_actual, '% vs histórico ', wape_historico, '% (desviación ', desviacion_pct, '%)')
    ELSE CONCAT('✅ Drift OK: WAPE ', wape_actual, '% vs histórico ', wape_historico, '%')
  END AS alert_msg,
  CURRENT_TIMESTAMP() AS created_at
FROM drift_detection d
WHERE d.severity IN ('HIGH', 'MEDIUM')
  AND (SELECT has_data FROM has_drift_data) = true
  AND d.week_end NOT IN (SELECT DISTINCT week_end FROM motoshop.gold.alertas_drift);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 6: Si no hay datos, registrar info

-- COMMAND ----------

INSERT INTO motoshop.gold.alertas_drift
SELECT
  CAST(DATE_TRUNC('WEEK', CURRENT_DATE) AS DATE) + 6 AS week_end,
  NULL AS wape_actual,
  NULL AS wape_historico,
  NULL AS desviacion_pct,
  30.0 AS threshold_pct,
  'BOOTSTRAP' AS severity,
  'ℹ️ Drift monitor en bootstrap — sin datos históricos aún. Se activará tras 4 semanas de baseline.' AS alert_msg,
  CURRENT_TIMESTAMP() AS created_at
WHERE (SELECT has_data FROM has_drift_data) = false;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Paso 7: Resumen

-- COMMAND ----------

SELECT severity, COUNT(*) AS count, MAX(week_end) AS last_week
FROM motoshop.gold.alertas_drift
GROUP BY severity
ORDER BY severity;
