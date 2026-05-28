# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Ingesta Bronze — las 12 tablas core
# MAGIC
# MAGIC Patrón canónico idempotente (DT-6): `INSERT ... REPLACE WHERE`.
# MAGIC Lee Parquet del UC Volume y escribe a Bronze particionado por `ingest_date`.
# MAGIC
# MAGIC **Pre-requisitos:**
# MAGIC 1. `dump_to_cloud.py --tables-core` ejecutado (sube Parquet + manifest al Volume).
# MAGIC 2. UC Volume `motoshop.bronze._landing` con datos de la fecha.

# COMMAND ----------

dbutils.widgets.text("ingest_date", "2026-05-28")
ingest_date = dbutils.widgets.get("ingest_date")
print(f"ingest_date: {ingest_date}")

# COMMAND ----------

from pyspark.sql.functions import lit

CATALOG = "motoshop"
SCHEMA = "bronze"
VOLUME = f"/Volumes/{CATALOG}/{SCHEMA}/_landing"

TABLES = [
    "bodegas", "sucursales", "formapago", "subproduct",
    "productos", "preciosxpro", "terceros", "auxinventario",
    "facventas", "detfventas", "compras", "detcompras",
]

results = []

for table in TABLES:
    path = f"{VOLUME}/{table}/ingest_date={ingest_date}/"
    target = f"{CATALOG}.{SCHEMA}.{table}"
    
    try:
        df = spark.read.parquet(path)
        df = df.withColumn("ingest_date", lit(ingest_date))
        row_count = df.count()
        
        df.write.format("delta") \
            .partitionBy("ingest_date") \
            .mode("overwrite") \
            .option("replaceWhere", f"ingest_date = '{ingest_date}'") \
            .saveAsTable(target)
        
        print(f"OK {table}: {row_count} rows")
        results.append({"table": table, "rows": row_count, "status": "OK"})
    except Exception as e:
        print(f"FAIL {table}: {str(e)[:100]}")
        results.append({"table": table, "rows": 0, "status": f"FAIL: {str(e)[:80]}"})

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen

# COMMAND ----------

print(f"\n{'='*50}")
print(f"  RESUMEN INGESTA BRONZE")
print(f"  Fecha: {ingest_date}")
print(f"{'='*50}")

ok_count = sum(1 for r in results if r["status"] == "OK")
total_rows = sum(r["rows"] for r in results)
print(f"  Tablas OK: {ok_count}/{len(TABLES)}")
print(f"  Total filas: {total_rows:,}")

for r in results:
    icon = "OK" if r["status"] == "OK" else "FAIL"
    print(f"  {icon} {r['table']}: {r['rows']:,} rows")

if ok_count == len(TABLES):
    print(f"\n  VEREDICTO: OK — las {len(TABLES)} tablas se ingerieron correctamente")
else:
    fail_count = len(TABLES) - ok_count
    print(f"\n  VEREDICTO: FAIL — {fail_count} tablas fallaron")
