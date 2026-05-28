-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 02 · Ingesta Bronze — las 12 tablas core
-- MAGIC
-- MAGIC Patrón canónico idempotente (DT-6): `INSERT INTO ... REPLACE WHERE`.
-- MAGIC Cada tabla: `CREATE TABLE IF NOT EXISTS` (primera vez) + `INSERT REPLACE WHERE ingest_date`.
-- MAGIC
-- MAGIC **Pre-requisitos:**
-- MAGIC 1. `dump_to_cloud.py --tables-core` ejecutado (sube Parquet + manifest al Volume).
-- MAGIC 2. UC Volume `motoshop.bronze._landing` con datos de la fecha.
-- MAGIC
-- MAGIC **Uso:** ejecutar cada celda separadamente para cada tabla, o parametrizar con widgets.

-- COMMAND ----------

CREATE WIDGET TEXT ingest_date DEFAULT '2026-05-28';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Tablas core (las 12 de PLAN.md §7)

-- COMMAND ----------

-- Celda maestra: ejecutar una vez por tabla.
-- Cambiar `$table_name` por el nombre de cada tabla.

-- TABLA: bodegas
CREATE TABLE IF NOT EXISTS motoshop.bronze.bodegas
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/bodegas/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.bodegas
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/bodegas/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: sucursales
CREATE TABLE IF NOT EXISTS motoshop.bronze.sucursales
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/sucursales/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.sucursales
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/sucursales/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: formapago
CREATE TABLE IF NOT EXISTS motoshop.bronze.formapago
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/formapago/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.formapago
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/formapago/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: subproduct
CREATE TABLE IF NOT EXISTS motoshop.bronze.subproduct
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/subproduct/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.subproduct
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/subproduct/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: productos
CREATE TABLE IF NOT EXISTS motoshop.bronze.productos
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/productos/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.productos
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/productos/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: preciosxpro
CREATE TABLE IF NOT EXISTS motoshop.bronze.preciosxpro
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/preciosxpro/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.preciosxpro
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/preciosxpro/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: terceros
CREATE TABLE IF NOT EXISTS motoshop.bronze.terceros
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/terceros/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.terceros
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/terceros/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: auxinventario
CREATE TABLE IF NOT EXISTS motoshop.bronze.auxinventario
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/auxinventario/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.auxinventario
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/auxinventario/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: facventas
CREATE TABLE IF NOT EXISTS motoshop.bronze.facventas
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/facventas/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.facventas
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/facventas/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: detfventas
CREATE TABLE IF NOT EXISTS motoshop.bronze.detfventas
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/detfventas/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.detfventas
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/detfventas/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: compras
CREATE TABLE IF NOT EXISTS motoshop.bronze.compras
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/compras/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.compras
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/compras/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- TABLA: detcompras
CREATE TABLE IF NOT EXISTS motoshop.bronze.detcompras
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/detcompras/ingest_date=$ingest_date/`
WHERE 1=0;

INSERT INTO motoshop.bronze.detcompras
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/detcompras/ingest_date=$ingest_date/`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Resumen de ingesta

-- COMMAND ----------

SELECT
  table_name,
  COUNT(*) AS rows_current_date
FROM motoshop.information_schema.tables t
JOIN (
  VALUES
    ('bodegas'), ('sucursales'), ('formapago'), ('subproduct'),
    ('productos'), ('preciosxpro'), ('terceros'), ('auxinventario'),
    ('facventas'), ('detfventas'), ('compras'), ('detcompras')
) AS expected(name)
ON t.table_name = expected.name
WHERE t.table_schema = 'bronze'
GROUP BY t.table_name
ORDER BY t.table_name;
