# Databricks notebook source
# MAGIC %md
# MAGIC # 12 · fact_compras — desde bronze.compras
# MAGIC
# MAGIC Patrón idempotente DT-F2-1. `business_date` se deriva de `feccom` (ADR-0013).
# MAGIC Solo documentos activos (`estcom = 'A'`).
# MAGIC **Esquema real:** 51 columnas en bronze.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.fact_compras"

# COMMAND ----------

dbutils.widgets.text("business_date", "")
business_date = dbutils.widgets.get("business_date")

# COMMAND ----------

from pyspark.sql.functions import col, current_date

df_bronze = spark.table(f"{BRONZE}.compras")
print(f"Filas bronze.compras: {df_bronze.count()}")

# COMMAND ----------

df_silver = (
    df_bronze
    .where(col("estcom") == "A")  # Solo activos
    .select(
        col("numcom").alias("num_documento"),
        col("codclas").alias("cod_clase"),
        col("precom").alias("prefijo"),
        col("feccom").cast("timestamp").alias("fecha_documento_ts"),
        col("feccom").cast("date").alias("business_date"),
        col("nitter").alias("nit_proveedor"),
        col("procom").alias("nombre_proveedor"),
        col("codsuc").alias("cod_sucursal"),
        col("codpag").alias("cod_formapago"),
        col("subcom").cast("double").alias("subtotal"),
        col("totdct").cast("double").alias("total_descuentos"),
        col("totiva").cast("double").alias("total_iva"),
        col("totipo").cast("double").alias("total_impuesto"),
        col("retfte").cast("double").alias("retencion_fuente"),
        col("retiva").cast("double").alias("retencion_iva"),
        col("retica").cast("double").alias("retencion_ica"),
        col("totcom").cast("double").alias("total_compra"),
        col("obscom").alias("observaciones"),
        col("estcom").alias("estado_documento"),
        col("codemp").alias("cod_empresa"),
        col("empcod").alias("cod_empresa_alt"),
        col("nitvend").alias("nit_vendedor"),
        current_date().alias("ingest_date_silver"),
    )
    .where(
        (col("business_date").isNotNull()) &
        (col("business_date") >= "2020-01-01") &
        (col("business_date") <= current_date())
    )
    .dropDuplicates(["num_documento", "cod_clase", "business_date"])
)

print(f"Filas fact_compras: {df_silver.count()}")

# COMMAND ----------

# Escritura idempotente
if business_date:
    df_silver = df_silver.where(col("business_date") == business_date)

spark.sql(f"CREATE TABLE IF NOT EXISTS {TARGET} (dummy INT) USING delta")

(
    df_silver.write
    .format("delta")
    .mode("overwrite")
    .partitionBy("business_date")
    .option("replaceWhere", f"business_date = '{business_date}'" if business_date else None)
    .saveAsTable(TARGET)
)

# COMMAND ----------

final_count = spark.table(TARGET).count()
print(f"✅ fact_compras: {final_count} filas en silver")

if final_count > 0:
    pk = spark.table(TARGET).select("num_documento", "cod_clase", "business_date").count()
    pk_d = spark.table(TARGET).select("num_documento", "cod_clase", "business_date").distinct().count()
    assert pk == pk_d, f"❌ Duplicados: {pk} vs {pk_d}"
    print(f"✅ PK única: {pk}")

display(spark.table(TARGET).limit(10))
