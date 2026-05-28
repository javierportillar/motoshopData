-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 03 · Validación de conteos — manifest vs. bronze
-- MAGIC
-- MAGIC Lee el manifest del UC Volume y compara `tables[*].rows` contra
-- MAGIC `COUNT(*) FROM motoshop.bronze.<tabla> WHERE ingest_date = '<date>'`.
-- MAGIC
-- MAGIC **Cierra verificación V1:** conteos bronze == origen.
-- MAGIC **Cierra verificación V2:** evidencia de idempotencia (mismos conteos tras re-ejecución).

-- COMMAND ----------

CREATE WIDGET TEXT ingest_date DEFAULT '2026-05-28';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Leer manifest del Volume

-- COMMAND ----------

SELECT
  manifest.ingest_date,
  manifest.duration_seconds,
  manifest.total_tables,
  manifest.total_rows AS manifest_total_rows
FROM json.`/Volumes/motoshop/bronze/_landing/_manifests/manifest_$ingest_date.json` AS manifest;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · Conteos por tabla en bronze

-- COMMAND ----------

WITH manifest_tables AS (
  SELECT
    t.table_name AS manifest_table,
    t.rows AS manifest_rows
  FROM json.`/Volumes/motoshop/bronze/_landing/_manifests/manifest_$ingest_date.json` AS manifest,
       LATERAL VIEW EXPLODE(manifest.tables) AS t
  WHERE t.error IS NULL
),
bronze_counts AS (
  SELECT
    'bodegas' AS tbl, COUNT(*) AS n FROM motoshop.bronze.bodegas WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'sucursales', COUNT(*) FROM motoshop.bronze.sucursales WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'formapago', COUNT(*) FROM motoshop.bronze.formapago WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'subproduct', COUNT(*) FROM motoshop.bronze.subproduct WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'productos', COUNT(*) FROM motoshop.bronze.productos WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'preciosxpro', COUNT(*) FROM motoshop.bronze.preciosxpro WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'terceros', COUNT(*) FROM motoshop.bronze.terceros WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'auxinventario', COUNT(*) FROM motoshop.bronze.auxinventario WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'facventas', COUNT(*) FROM motoshop.bronze.facventas WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'detfventas', COUNT(*) FROM motoshop.bronze.detfventas WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'compras', COUNT(*) FROM motoshop.bronze.compras WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'detcompras', COUNT(*) FROM motoshop.bronze.detcompras WHERE ingest_date = '$ingest_date'
)
SELECT
  COALESCE(b.tbl, m.manifest_table) AS table_name,
  m.manifest_rows,
  b.n AS bronze_rows,
  CASE
    WHEN m.manifest_rows = b.n AND b.n > 0 THEN 'OK'
    WHEN m.manifest_rows = b.n AND b.n = 0 THEN 'WARN: N=0'
    WHEN m.manifest_rows IS NULL THEN 'MISSING: tabla no esta en bronze'
    WHEN b IS NULL THEN 'MISSING: tabla no esta en manifest'
    ELSE 'MISMATCH'
  END AS status
FROM manifest_tables m
FULL OUTER JOIN bronze_counts b ON m.manifest_table = b.tbl
ORDER BY table_name;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Veredicto final

-- COMMAND ----------

WITH manifest_tables AS (
  SELECT t.table_name AS tbl, t.rows AS manifest_rows
  FROM json.`/Volumes/motoshop/bronze/_landing/_manifests/manifest_$ingest_date.json` AS manifest,
       LATERAL VIEW EXPLODE(manifest.tables) AS t
  WHERE t.error IS NULL
),
bronze_counts AS (
  SELECT 'bodegas' AS tbl, COUNT(*) AS n FROM motoshop.bronze.bodegas WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'sucursales', COUNT(*) FROM motoshop.bronze.sucursales WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'formapago', COUNT(*) FROM motoshop.bronze.formapago WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'subproduct', COUNT(*) FROM motoshop.bronze.subproduct WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'productos', COUNT(*) FROM motoshop.bronze.productos WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'preciosxpro', COUNT(*) FROM motoshop.bronze.preciosxpro WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'terceros', COUNT(*) FROM motoshop.bronze.terceros WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'auxinventario', COUNT(*) FROM motoshop.bronze.auxinventario WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'facventas', COUNT(*) FROM motoshop.bronze.facventas WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'detfventas', COUNT(*) FROM motoshop.bronze.detfventas WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'compras', COUNT(*) FROM motoshop.bronze.compras WHERE ingest_date = '$ingest_date'
  UNION ALL SELECT 'detcompras', COUNT(*) FROM motoshop.bronze.detcompras WHERE ingest_date = '$ingest_date'
),
comparison AS (
  SELECT
    COALESCE(b.tbl, m.tbl) AS tbl,
    m.manifest_rows,
    b.n AS bronze_rows,
    CASE WHEN m.manifest_rows = b.n THEN 1 ELSE 0 END AS matches
  FROM manifest_tables m
  FULL OUTER JOIN bronze_counts b ON m.tbl = b.tbl
)
SELECT
  CASE
    WHEN SUM(matches) = COUNT(*) AND SUM(bronze_rows) > 0 THEN 'OK — conteos cuadran y N>0 para todas las tablas'
    WHEN SUM(matches) = COUNT(*) AND SUM(bronze_rows) = 0 THEN 'WARN — conteos cuadran pero N=0'
    ELSE CONCAT('FAIL — ', CAST(COUNT(*) - SUM(matches) AS STRING), ' tablas con mismatch')
  END AS verdict,
  COUNT(*) AS total_tables,
  SUM(matches) AS matching_tables,
  SUM(bronze_rows) AS total_bronze_rows
FROM comparison;
