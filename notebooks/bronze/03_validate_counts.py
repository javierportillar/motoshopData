# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Validación de conteos — manifest vs. bronze
# MAGIC
# MAGIC Lee el manifest del UC Volume y compara con conteos en bronze.
# MAGIC Cierra verificación V1.

# COMMAND ----------

import json
from pyspark.sql.functions import col, lit, sum as spark_sum, when, count

dbutils.widgets.text("ingest_date", "2026-05-28")
ingest_date = dbutils.widgets.get("ingest_date")

CATALOG = "motoshop"
SCHEMA = "bronze"
VOLUME = f"/Volumes/{CATALOG}/{SCHEMA}/_landing"

TABLES = [
    "bodegas", "sucursales", "formapago", "subproduct",
    "productos", "preciosxpro", "terceros", "auxinventario",
    "facventas", "detfventas", "compras", "detcompras",
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Leer manifest

# COMMAND ----------

manifest_path = f"{VOLUME}/_manifests/manifest_{ingest_date}.json"

# El manifest es JSON anidado (no NDJSON), leer todas las lineas y unirlas
lines = spark.read.text(manifest_path).toPandas()["value"].tolist()
manifest_text = "".join(lines)
manifest_data = json.loads(manifest_text)

manifest_date = manifest_data.get('ingest_date', ingest_date)
print(f"Manifest: {manifest_date}")
print(f"Duracion: {manifest_data.get('duration_seconds', '?')}s")
print(f"Tablas en manifest: {len(manifest_data.get('tables', []))}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Conteos por tabla

# COMMAND ----------

# Extraer conteos del manifest
manifest_tables = {}
for t in manifest_data.get("tables", []):
    if t.get("error") is None:
        manifest_tables[t["table"]] = t["rows"]

print("Manifest tables:", manifest_tables)

# COMMAND ----------

# Contar filas en bronze
bronze_counts = {}
for table in TABLES:
    try:
        n = spark.table(f"{CATALOG}.{SCHEMA}.{table}") \
                 .filter(f"ingest_date = '{ingest_date}'").count()
        bronze_counts[table] = n
    except Exception:
        bronze_counts[table] = 0

print("Bronze counts:", bronze_counts)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Comparación

# COMMAND ----------

print(f"\n{'Table':<20} {'Manifest':>10} {'Bronze':>10} {'Status':>10}")
print("-" * 55)

mismatches = 0
total_manifest = 0
total_bronze = 0

for table in sorted(TABLES):
    m = manifest_tables.get(table, 0)
    b = bronze_counts.get(table, 0)
    total_manifest += m
    total_bronze += b

    if m == b and b > 0:
        status = "OK"
    elif m == b and b == 0:
        status = "WARN_N0"
    else:
        status = "MISMATCH"
        mismatches += 1

    print(f"{table:<20} {m:>10} {b:>10} {status:>10}")

print("-" * 55)
print(f"{'TOTAL':<20} {total_manifest:>10} {total_bronze:>10}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Veredicto

# COMMAND ----------

if mismatches == 0 and total_bronze > 0:
    print("VEREDICTO: OK — conteos cuadran y N>0 para todas las tablas")
elif mismatches == 0 and total_bronze == 0:
    print("VEREDICTO: WARN — conteos cuadran pero N=0")
else:
    print(f"VEREDICTO: FAIL — {mismatches} tablas con mismatch")
