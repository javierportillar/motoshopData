-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 01 · Smoke Test — Ingesta Bronze (versión SQL)
-- MAGIC
-- MAGIC **Objetivo:** verificación crítica **#3 de Fase 0** — ejecutable en
-- MAGIC el SQL Warehouse de Databricks Free Edition (no requiere compute
-- MAGIC Python). La versión PySpark equivalente vive en
-- MAGIC `01_ingest_smoke_test.py` y se usará cuando se disponga de
-- MAGIC serverless compute para notebooks.
-- MAGIC
-- MAGIC **Pre-requisitos:**
-- MAGIC 1. UC Volume `motoshop.bronze._landing` creado (ver `infra/setup_uc_volume.md`).
-- MAGIC 2. `infra/dump_to_cloud.py` ejecutado al menos una vez para la tabla bajo prueba.
-- MAGIC    Para validar la verificación crítica **con N > 0**, usar una tabla
-- MAGIC    pequeña pero **con datos** (recomendado: `bodegas` o `formapago`).
-- MAGIC
-- MAGIC **Parámetros (widgets):**
-- MAGIC - `table_name` — nombre de la tabla bronze a materializar.
-- MAGIC - `ingest_date` — fecha de ingesta (YYYY-MM-DD) que el dump usó como partición.

-- COMMAND ----------

-- Crear los widgets (se ejecuta solo la primera vez)
CREATE WIDGET TEXT table_name DEFAULT 'bodegas';
CREATE WIDGET TEXT ingest_date DEFAULT '2026-05-28';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Configuración

-- COMMAND ----------

SELECT
  'motoshop' AS catalog,
  'bronze' AS schema,
  '$table_name' AS table,
  '$ingest_date' AS ingest_date,
  '/Volumes/motoshop/bronze/_landing/$table_name/ingest_date=$ingest_date/' AS source_path,
  'motoshop.bronze.$table_name' AS target_table;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · Conteo en el origen (Parquet del Volume)

-- COMMAND ----------

SELECT COUNT(*) AS source_rows
FROM parquet.`/Volumes/motoshop/bronze/_landing/$table_name/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Muestra de filas (5 primeras)
-- MAGIC
-- MAGIC Esto satisface el "muestre los datos" de la verificación crítica #3.

-- COMMAND ----------

SELECT *
FROM parquet.`/Volumes/motoshop/bronze/_landing/$table_name/ingest_date=$ingest_date/`
LIMIT 5;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Escritura a Bronze (Delta + partición por ingest_date)
-- MAGIC
-- MAGIC `CREATE OR REPLACE TABLE` es válido en Databricks Delta y reemplaza
-- MAGIC la tabla completa. Para producción usar el patrón idempotente con
-- MAGIC `INSERT ... REPLACE WHERE` que aparece en `02_ingest_bookmarked.sql`
-- MAGIC (a entregar en F1).

-- COMMAND ----------

CREATE OR REPLACE TABLE motoshop.bronze.$table_name
USING DELTA
PARTITIONED BY (ingest_date)
AS
SELECT
  *,
  '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/$table_name/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5 · Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS bronze_rows
FROM motoshop.bronze.$table_name
WHERE ingest_date = '$ingest_date';

-- COMMAND ----------

-- Cuadre estricto: bronze == origen.
-- Si las cifras no cuadran, hay bug. La regla de oro #3 lo exige.
WITH
  src AS (
    SELECT COUNT(*) AS n
    FROM parquet.`/Volumes/motoshop/bronze/_landing/$table_name/ingest_date=$ingest_date/`
  ),
  brz AS (
    SELECT COUNT(*) AS n
    FROM motoshop.bronze.$table_name
    WHERE ingest_date = '$ingest_date'
  )
SELECT
  src.n AS source_rows,
  brz.n AS bronze_rows,
  CASE
    WHEN src.n = brz.n AND src.n > 0 THEN '✅ OK — conteos cuadran y N > 0 (verif. #3 cumplida)'
    WHEN src.n = brz.n AND src.n = 0 THEN '⚠️ Conteos cuadran pero N = 0; no demuestra movimiento de datos. Reintentar con una tabla con datos.'
    ELSE '❌ Conteos no cuadran — bug. Revisar el dump o el path.'
  END AS verdict
FROM src, brz;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 6 · Linaje
-- MAGIC
-- MAGIC `DESCRIBE HISTORY` muestra todas las operaciones sobre la tabla Delta.
-- MAGIC Copiar la salida de esta celda + la celda 5 al archivo de evidencia:
-- MAGIC `notebooks/bronze/_runs/smoke_test_YYYY-MM-DD.md`.

-- COMMAND ----------

DESCRIBE HISTORY motoshop.bronze.$table_name LIMIT 5;
