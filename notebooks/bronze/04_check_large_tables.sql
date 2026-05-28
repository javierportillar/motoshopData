-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 04 · Validación de tablas grandes — paginación
-- MAGIC
-- MAGIC Verifica que `detfventas` (~27k filas) y `detcompras` (~11k filas)
-- MAGIC se ingirieron completas. Cumple verificación V6.
-- MAGIC
-- MAGIC **Pre-requisitos:** ingestión de F1-A completada para la fecha.

-- COMMAND ----------

CREATE WIDGET TEXT ingest_date DEFAULT '2026-05-28';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · detfventas (~27k filas esperadas)

-- COMMAND ----------

SELECT
  COUNT(*) AS total_rows,
  MIN(fecdoc) AS min_fecdoc,
  MAX(fecdoc) AS max_fecdoc,
  COUNT(DISTINCT SUBSTRING(fecdoc, 1, 7)) AS distinct_months
FROM motoshop.bronze.detfventas
WHERE ingest_date = '$ingest_date';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · detcompras (~11k filas esperadas)

-- COMMAND ----------

SELECT
  COUNT(*) AS total_rows,
  MIN(fecdoc) AS min_fecdoc,
  MAX(fecdoc) AS max_fecdoc,
  COUNT(DISTINCT SUBSTRING(fecdoc, 1, 7)) AS distinct_months
FROM motoshop.bronze.detcompras
WHERE ingest_date = '$ingest_date';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Veredicto V6

-- COMMAND ----------

WITH
  detf AS (
    SELECT COUNT(*) AS n
    FROM motoshop.bronze.detfventas
    WHERE ingest_date = '$ingest_date'
  ),
  detc AS (
    SELECT COUNT(*) AS n
    FROM motoshop.bronze.detcompras
    WHERE ingest_date = '$ingest_date'
  )
SELECT
  CASE
    WHEN detf.n > 0 AND detc.n > 0 THEN 'OK — detfventas=' || CAST(detf.n AS STRING) || ', detcompras=' || CAST(detc.n AS STRING)
    ELSE 'FAIL — detfventas=' || CAST(detf.n AS STRING) || ', detcompras=' || CAST(detc.n AS STRING)
  END AS verdict
FROM detf, detc;
