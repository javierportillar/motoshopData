# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · dim_bodega — SCD Type 1 desde bronze.bodegas
# MAGIC
# MAGIC Snapshot del estado actual de bodegas.
# MAGIC **Esquema real:** 5 columnas — `codbod`, `nombod`, `telbod`, `ubibod`, `resbod`.
# MAGIC
# MAGIC **DT-F2-2:** SCD Type 1. **DT-F2-5:** `dim_bodega`.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.dim_bodega"

# COMMAND ----------

from pyspark.sql.functions import col, trim, current_date

df_bronze = spark.table(f"{BRONZE}.bodegas")
print(f"Filas bronze.bodegas: {df_bronze.count()}")
print("Columnas:", df_bronze.columns)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transformación
# MAGIC
# MAGIC Nota: `sucursales` tiene 0 filas en la BD actual.
# MAGIC Solo 1 bodega principal.

# COMMAND ----------

df_silver = (
    df_bronze
    .select(
        trim(col("codbod")).alias("cod_bodega"),
        trim(col("nombod")).alias("nombre_bodega"),
        trim(col("telbod")).alias("telefono"),
        trim(col("ubibod")).alias("ubicacion"),
        trim(col("resbod")).alias("responsable"),
        current_date().alias("snapshot_date"),
    )
    .where(col("cod_bodega").isNotNull())
    .dropDuplicates(["cod_bodega"])
)

print(f"Filas dimension bodega: {df_silver.count()}")

# COMMAND ----------

# Validación PK
pk_count = df_silver.count()
pk_distinct = df_silver.select("cod_bodega").distinct().count()
assert pk_count == pk_distinct, (
    f"❌ Duplicados en dim_bodega: {pk_count} vs {pk_distinct}"
)
print(f"✅ PK única: {pk_count}")

# COMMAND ----------

# Escritura
df_silver.write.format("delta").mode("overwrite").saveAsTable(TARGET)
final_count = spark.table(TARGET).count()
print(f"✅ dim_bodega: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
