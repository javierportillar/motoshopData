# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Ingesta Bronze — las 12 tablas core
# MAGIC
# MAGIC Patrón canónico idempotente (DT-6): `INSERT ... REPLACE WHERE`.
# MAGIC Lee Parquet del UC Volume y escribe a Bronze particionado por `ingest_date`.
# MAGIC
# MAGIC **Auto-detecta la última partición disponible** en el Volume.
# MAGIC Si el job pasa `ingest_date` como widget, usa ese. Si no, busca la
# MAGIC partición más reciente en el Volume. Esto permite:
# MAGIC   - Ejecuciones horarias (9 AM-6 PM): toman la última data disponible
# MAGIC   - Ejecución nocturna (02:30): funciona igual si hay data del día anterior
# MAGIC   - Backfill manual: pasar `ingest_date=YYYY-MM-DD` explícitamente
# MAGIC
# MAGIC **Pre-requisitos:**
# MAGIC 1. `dump_to_cloud.py --tables-core` ejecutado (sube Parquet + manifest al Volume).
# MAGIC 2. UC Volume `motoshop.bronze._landing` con datos de la fecha.

# COMMAND ----------

from pyspark.sql.functions import lit, max as spark_max

CATALOG = "motoshop"
SCHEMA = "bronze"
VOLUME = f"/Volumes/{CATALOG}/{SCHEMA}/_landing"

# Widget opcional — si no se pasa, se auto-detecta la última partición
dbutils.widgets.text("ingest_date", "")
ingest_date = dbutils.widgets.get("ingest_date")

if not ingest_date:
    # Auto-detect: buscar la última partición disponible en el Volume
    try:
        ref_path = f"{VOLUME}/bodegas"
        ref_df = spark.read.parquet(ref_path)
        latest_row = ref_df.select(spark_max("ingest_date")).collect()[0][0]
        if latest_row:
            ingest_date = str(latest_row)
            print(f"Auto-detect: última partición disponible → {ingest_date}")
    except Exception as e:
        print(f"WARN: auto-detect falló ({e}), usando fallback")

if not ingest_date:
    # Fallback final: ayer
    from datetime import datetime, timedelta, timezone
    ingest_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fallback: {ingest_date}")

print(f"ingest_date: {ingest_date}")

# ─── Skip si esta fecha ya fue procesada ────────────────────────────────
# En Databricks Free evitamos trabajo al pedo: si ya existe la partición
# en bodegas, es porque esta fecha ya se ingirió → SKIP.
ref_table = f"{CATALOG}.{SCHEMA}.bodegas"
try:
    existing_parts = spark.sql(f"SHOW PARTITIONS {ref_table}")
    dates_done = set()
    for row in existing_parts.collect():
        spec = row[0]  # "ingest_date=2026-05-29"
        if "=" in spec:
            dates_done.add(spec.split("=", 1)[1])

    if ingest_date in dates_done:
        print(f"\n⏭️  SKIP: ingest_date={ingest_date} ya existe en la tabla bronze.")
        print(f"    No hay datos nuevos que procesar. Finalizando.")
        # Terminar el notebook temprano
        dbutils.notebook.exit(f"SKIP: {ingest_date} ya procesado")
except Exception as e:
    # Si SHOW PARTITIONS falla (tabla nueva, sin particiones), seguimos normal
    print(f"WARN: no se pudo verificar particiones ({e}), igual se procesa.")

# COMMAND ----------

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
