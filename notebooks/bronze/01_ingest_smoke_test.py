# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Smoke Test — Ingesta Bronze (`sucursales`)
# MAGIC
# MAGIC **Objetivo:** verificación crítica **#3 de Fase 0** — *"La conectividad
# MAGIC Databricks → MySQL local funciona end-to-end. Un notebook que lea una
# MAGIC tabla (aunque sea con 10 filas) y muestre los datos."*
# MAGIC
# MAGIC **Cómo lo cumplimos** (P1 · Opción A, ver
# MAGIC [ADR-0005](../docs/decisions/0005-databricks-mysql-connectivity.md) y
# MAGIC [ADR-0010](../docs/decisions/0010-compute-databricks-free.md)):
# MAGIC
# MAGIC 1. El script local `infra/dump_to_cloud.py` extrae `sucursales` de
# MAGIC    MySQL y sube `part-0.parquet` al **UC Volume**
# MAGIC    `/Volumes/motoshop/bronze/_landing/sucursales/ingest_date=YYYY-MM-DD/`.
# MAGIC 2. Este notebook lee ese Parquet **del volume** y lo materializa como
# MAGIC    `motoshop.bronze.sucursales` particionado por `ingest_date`.
# MAGIC 3. Comparamos COUNT(*) en Delta vs. filas del Parquet de origen — debe
# MAGIC    coincidir 1:1.
# MAGIC
# MAGIC **Pre-requisitos antes de ejecutar:**
# MAGIC - Volume `motoshop.bronze._landing` creado en Unity Catalog.
# MAGIC - `dump_to_cloud.py` ejecutado al menos una vez para `--tables sucursales`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Configuración

# COMMAND ----------

from datetime import date

from pyspark.sql.functions import lit

CATALOG = "motoshop"
SCHEMA = "bronze"
TABLE = "sucursales"

# Permite parametrizar la fecha al ejecutar el notebook desde un Workflow.
try:
    dbutils.widgets.text("ingest_date", date.today().isoformat())
    INGEST_DATE = dbutils.widgets.get("ingest_date")
except Exception:
    INGEST_DATE = date.today().isoformat()

VOLUME_BASE = f"/Volumes/{CATALOG}/{SCHEMA}/_landing"
SOURCE_PATH = f"{VOLUME_BASE}/{TABLE}/ingest_date={INGEST_DATE}"
TARGET_TABLE = f"{CATALOG}.{SCHEMA}.{TABLE}"

print(f"Catálogo · esquema · tabla:  {TARGET_TABLE}")
print(f"Origen (UC Volume):          {SOURCE_PATH}")
print(f"ingest_date:                 {INGEST_DATE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Lectura del Parquet del Volume

# COMMAND ----------

# Lectura sin esquema impuesto — bronze refleja lo que vino del origen.
# `dump_to_cloud.py` materializa todo como string para tolerar tipos MyISAM;
# el casteo formal sucede en silver.
df_raw = spark.read.parquet(SOURCE_PATH)
# Apuntamos directamente a la partición; añadimos ingest_date como columna
# para que la escritura particionada quede consistente.
df = df_raw.withColumn("ingest_date", lit(INGEST_DATE))

source_count = df.count()
print(f"Filas leídas del Parquet: {source_count}")
print("\nEsquema observado:")
df.printSchema()

print("\nPrimeras 5 filas (muestra para el ojo humano):")
df.show(5, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Escritura a Bronze (Delta + partición por ingest_date)

# COMMAND ----------

# Si la tabla no existe, se crea; si ya existe, se sobrescribe SOLO la partición de hoy.
# Esto preserva ingestas anteriores y hace la ingesta idempotente para la misma fecha.
(
    df.write
      .mode("overwrite")
      .partitionBy("ingest_date")
      .option("replaceWhere", f"ingest_date = '{INGEST_DATE}'")
      .format("delta")
      .saveAsTable(TARGET_TABLE)
)
print(f"✅ Escritura en {TARGET_TABLE} (partición ingest_date={INGEST_DATE})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Validación

# COMMAND ----------

bronze_count = spark.sql(
    f"SELECT COUNT(*) AS n FROM {TARGET_TABLE} WHERE ingest_date = '{INGEST_DATE}'"
).collect()[0]["n"]

print(f"Filas en bronze (partición {INGEST_DATE}): {bronze_count}")
print(f"Filas en parquet de origen               : {source_count}")

assert bronze_count == source_count, (
    f"❌ Diferencia de conteos. Bronze={bronze_count}, Origen={source_count}. "
    "Esto rompe la regla de oro: cualquier cifra mostrada debe cuadrar con sgHermes."
)

print("\n✅ Smoke test OK · verificación crítica #3 de F0 cumplida")
print(f"   Tabla: {TARGET_TABLE}")
print(f"   ingest_date: {INGEST_DATE}")
print(f"   Filas: {bronze_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Captura para SEGUIMIENTO.md
# MAGIC
# MAGIC Guardar la salida de las celdas 2, 3 y 4 en `notebooks/bronze/_runs/smoke_test_YYYY-MM-DD.txt`
# MAGIC (o capturar pantalla y enlazar). Sirve de evidencia para cerrar la verificación crítica #3.

# COMMAND ----------

# Información del run para auditoría
display(spark.sql(f"DESCRIBE HISTORY {TARGET_TABLE} LIMIT 5"))
