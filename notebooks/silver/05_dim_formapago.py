# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · dim_formapago — SCD Type 1 desde bronze.formapago
# MAGIC
# MAGIC **Esquema real:** 26 columnas. Seleccionamos las más relevantes.
# MAGIC **DT-F2-2:** SCD Type 1. **DT-F2-5:** `dim_formapago`.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.dim_formapago"

# COMMAND ----------

from pyspark.sql.functions import col, trim, current_date

df_bronze = spark.table(f"{BRONZE}.formapago")
print(f"Filas bronze.formapago: {df_bronze.count()}")

# COMMAND ----------

df_silver = (
    df_bronze
    .select(
        trim(col("codpag")).alias("cod_formapago"),
        trim(col("forpag")).alias("nombre_formapago"),
        col("afepag").cast("int").alias("afecta_pago"),
        col("tippag").cast("int").alias("tipo_pago"),
        trim(col("codcaj")).alias("cod_caja"),
        trim(col("codban")).alias("cod_banco"),
        trim(col("codcue")).alias("cod_cuenta"),
        trim(col("facven")).alias("factura_venta"),
        trim(col("venpos")).alias("venta_pos"),
        trim(col("compra")).alias("es_compra"),
        trim(col("financ")).alias("es_financiacion"),
        trim(col("empsino")).alias("empresa_sino"),
        current_date().alias("snapshot_date"),
    )
    .where(col("cod_formapago").isNotNull())
    .dropDuplicates(["cod_formapago"])
)

print(f"Filas dimension formapago: {df_silver.count()}")

# COMMAND ----------

# Validación PK
pk_count = df_silver.count()
pk_distinct = df_silver.select("cod_formapago").distinct().count()
assert pk_count == pk_distinct, (
    f"❌ Duplicados en dim_formapago: {pk_count} vs {pk_distinct}"
)
print(f"✅ PK única: {pk_count}")

# COMMAND ----------

df_silver.write.format("delta").mode("overwrite").saveAsTable(TARGET)
final_count = spark.table(TARGET).count()
print(f"✅ dim_formapago: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
