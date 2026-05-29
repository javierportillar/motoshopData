# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · dim_sucursal — SCD Type 1 desde bronze.sucursales
# MAGIC
# MAGIC **Esquema real:** 26 columnas. Seleccionamos las más relevantes.
# MAGIC **Nota:** sucursales tiene 0 filas en la BD actual (solo se usa `bodegas`).
# MAGIC
# MAGIC **DT-F2-2:** SCD Type 1. **DT-F2-5:** `dim_sucursal`.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.dim_sucursal"

# COMMAND ----------

from pyspark.sql.functions import col, trim, current_date

df_bronze = spark.table(f"{BRONZE}.sucursales")
print(f"Filas bronze.sucursales: {df_bronze.count()}")

# COMMAND ----------

df_silver = (
    df_bronze
    .select(
        trim(col("codsuc")).alias("cod_sucursal"),
        trim(col("nitter")).alias("nit_tercero"),
        trim(col("nomsuc")).alias("nombre_sucursal"),
        trim(col("dirsuc")).alias("direccion"),
        trim(col("telsuc")).alias("telefono"),
        trim(col("movsuc")).alias("movil"),
        trim(col("nomrut")).alias("nombre_ruta"),
        trim(col("nomzon")).alias("nombre_zona"),
        trim(col("inasuc")).alias("inactiva"),
        trim(col("codciu")).alias("cod_ciudad"),
        trim(col("codest")).alias("cod_establecimiento"),
        trim(col("codcat")).alias("cod_categoria"),
        trim(col("corele")).alias("email"),
        trim(col("tiposuc")).alias("tipo_sucursal"),
        current_date().alias("snapshot_date"),
    )
    .where(col("cod_sucursal").isNotNull())
    .dropDuplicates(["cod_sucursal"])
)

print(f"Filas dimension sucursal: {df_silver.count()}")

# COMMAND ----------

# Validación PK
pk_count = df_silver.count()
pk_distinct = df_silver.select("cod_sucursal").distinct().count()
assert pk_count == pk_distinct, (
    f"❌ Duplicados en dim_sucursal: {pk_count} vs {pk_distinct}"
)
print(f"✅ PK única: {pk_count}")

# COMMAND ----------

df_silver.write.format("delta").mode("overwrite").saveAsTable(TARGET)
final_count = spark.table(TARGET).count()
print(f"✅ dim_sucursal: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
