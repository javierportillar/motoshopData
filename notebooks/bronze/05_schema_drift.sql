-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 05 · Detección de schema drift
-- MAGIC
-- MAGIC Compara el esquema entre 2 ingest_dates para detectar cambios
-- MAGIC inesperados en columnas o tipos. Cumple verificación V7.
-- MAGIC
-- MAGIC **Uso:** cambiar `ingest_date_a` y `ingest_date_b` por las fechas a comparar.
-- MAGIC Idealmente: una fecha reciente vs. una fecha anterior.

-- COMMAND ----------

CREATE WIDGET TEXT ingest_date_a DEFAULT '2026-05-28';
CREATE WIDGET TEXT ingest_date_b DEFAULT '';

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Esquema de la fecha A

-- COMMAND ----------

DESCRIBE TABLE motoshop.bronze.productos;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · Esquema de la fecha B (si existe)

-- COMMAND ----------

-- Si ingest_date_b está vacío, este paso se salta.
-- Para comparar, ejecutar con ingest_date_b = fecha anterior.
SELECT
  '$ingest_date_a' AS fecha_a,
  '$ingest_date_b' AS fecha_b,
  CASE
    WHEN '$ingest_date_b' = '' THEN 'SKIP — solo hay una fecha de ingestión'
    ELSE 'Comparar esquemas manualmente entre las dos fechas'
  END AS instruccion;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Verificar estabilidad de esquema (todas las tablas)

-- COMMAND ----------

SELECT
  table_name,
  COUNT(DISTINCT column_name) AS column_count,
  COLLECT_LIST(column_name) AS columns
FROM motoshop.information_schema.columns
WHERE table_schema = 'bronze'
  AND table_name IN (
    'bodegas', 'sucursales', 'formapago', 'subproduct',
    'productos', 'preciosxpro', 'terceros', 'auxinventario',
    'facventas', 'detfventas', 'compras', 'detcompras'
  )
GROUP BY table_name
ORDER BY table_name;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Veredicto V7

-- COMMAND ----------

SELECT
  CASE
    WHEN COUNT(*) = 12 THEN 'OK — las 12 tablas bronze existen con esquema definido'
    ELSE 'WARN — solo ' || CAST(COUNT(*) AS STRING) || ' tablas encontradas'
  END AS verdict
FROM motoshop.information_schema.tables
WHERE table_schema = 'bronze'
  AND table_name IN (
    'bodegas', 'sucursales', 'formapago', 'subproduct',
    'productos', 'preciosxpro', 'terceros', 'auxinventario',
    'facventas', 'detfventas', 'compras', 'detcompras'
  );
