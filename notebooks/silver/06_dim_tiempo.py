-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 06 · dim_tiempo — Calendario con festivos COL

-- COMMAND ----------

CREATE OR REPLACE TABLE motoshop.silver.dim_tiempo AS
WITH date_range AS (
  SELECT explode(sequence(
    TO_DATE('2020-01-01'),
    DATE_ADD(CURRENT_DATE(), 365),
    INTERVAL 1 DAY
  )) AS business_date
),
festivos AS (
  SELECT explode(ARRAY(
    TO_DATE('2024-01-01'), TO_DATE('2024-01-08'), TO_DATE('2024-03-25'),
    TO_DATE('2024-03-28'), TO_DATE('2024-03-29'), TO_DATE('2024-05-01'),
    TO_DATE('2024-05-13'), TO_DATE('2024-06-03'), TO_DATE('2024-06-19'),
    TO_DATE('2024-07-01'), TO_DATE('2024-07-20'), TO_DATE('2024-08-07'),
    TO_DATE('2024-08-15'), TO_DATE('2024-10-14'), TO_DATE('2024-11-01'),
    TO_DATE('2024-11-11'), TO_DATE('2024-12-08'), TO_DATE('2024-12-25'),
    TO_DATE('2025-01-01'), TO_DATE('2025-01-13'), TO_DATE('2025-03-24'),
    TO_DATE('2025-04-17'), TO_DATE('2025-04-18'), TO_DATE('2025-05-01'),
    TO_DATE('2025-06-02'), TO_DATE('2025-06-23'), TO_DATE('2025-06-30'),
    TO_DATE('2025-07-20'), TO_DATE('2025-08-07'), TO_DATE('2025-08-18'),
    TO_DATE('2025-10-13'), TO_DATE('2025-11-03'), TO_DATE('2025-11-17'),
    TO_DATE('2025-12-08'), TO_DATE('2025-12-25'),
    TO_DATE('2026-01-01'), TO_DATE('2026-01-12'), TO_DATE('2026-03-23'),
    TO_DATE('2026-04-02'), TO_DATE('2026-04-03'), TO_DATE('2026-05-01'),
    TO_DATE('2026-06-08'), TO_DATE('2026-06-15'), TO_DATE('2026-06-29'),
    TO_DATE('2026-07-20'), TO_DATE('2026-08-07'), TO_DATE('2026-08-17'),
    TO_DATE('2026-10-12'), TO_DATE('2026-11-02'), TO_DATE('2026-11-16'),
    TO_DATE('2026-12-08'), TO_DATE('2026-12-25')
  )) AS festivo_date
)
SELECT
  d.business_date,
  YEAR(d.business_date)        AS year,
  QUARTER(d.business_date)     AS quarter,
  MONTH(d.business_date)       AS month,
  DAYOFMONTH(d.business_date)  AS day_of_month,
  DAYOFWEEK(d.business_date)   AS day_of_week,
  DATE_FORMAT(d.business_date, 'MMMM') AS month_name,
  DATE_FORMAT(d.business_date, 'EEEE') AS day_name,
  CASE WHEN DAYOFWEEK(d.business_date) IN (1, 7) THEN TRUE ELSE FALSE END AS is_weekend,
  CASE WHEN f.festivo_date IS NOT NULL THEN TRUE ELSE FALSE END AS is_festivo_col
FROM date_range d
LEFT JOIN festivos f ON d.business_date = f.festivo_date;

-- COMMAND ----------

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT business_date) AS distintos,
  SUM(CASE WHEN is_festivo_col THEN 1 ELSE 0 END) AS festivos
FROM motoshop.silver.dim_tiempo;
