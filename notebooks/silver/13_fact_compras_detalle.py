# Databricks notebook source
# MAGIC %md
# MAGIC # 13 · fact_compras_detalle — desde bronze.detcompras
# MAGIC
# MAGIC Detalle de compras. JOIN con `fact_compras` para heredar `business_date`.
# MAGIC **Esquema real:** 37 columnas en bronze.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.fact_compras_detalle"

# COMMAND ----------

dbutils.widgets.text("business_date", "")
business_date = dbutils.widgets.get("business_date")

# COMMAND ----------

from pyspark.sql.functions import col, current_date

df_bronze = spark.table(f"{BRONZE}.detcompras")
print(f"Filas bronze.detcompras: {df_bronze.count()}")

# COMMAND ----------

# JOIN con fact_compras para business_date
try:
    df_header = spark.table(f"{SILVER}.fact_compras").select(
        col("num_documento").alias("numcom"),
        col("cod_clase").alias("codclas"),
        col("business_date"),
    )
    has_header = True
except Exception:
    has_header = False
    print("⚠️ fact_compras no existe aún — fallback a CURRENT_DATE")

if has_header:
    df_joined = df_bronze.join(df_header, on=["numcom", "codclas"], how="inner")
else:
    df_joined = df_bronze.withColumn("business_date", current_date())

# COMMAND ----------

df_silver = (
    df_joined
    .select(
        col("numcom").alias("num_documento"),
        col("codclas").alias("cod_clase"),
        col("codprod").alias("cod_producto"),
        col("nomdet").alias("nombre_detalle"),
        col("candet").cast("double").alias("cantidad"),
        col("valuni").cast("double").alias("valor_unitario"),
        col("dctpor").cast("double").alias("descuento_porcentaje"),
        col("dctpes").cast("double").alias("descuento_valor"),
        col("ivapor").cast("double").alias("iva_porcentaje"),
        col("ivapes").cast("double").alias("iva_valor"),
        col("ipopor").cast("double").alias("ipo_porcentaje"),
        col("ipopes").cast("double").alias("ipo_valor"),
        col("totdet").cast("double").alias("total_detalle"),
        col("cosprod").cast("double").alias("costo_producto"),
        col("numite").cast("int").alias("num_item"),
        col("codbod").alias("cod_bodega"),
        col("codcos").alias("cod_centro_costo"),
        col("business_date"),
    )
    .where(col("business_date").isNotNull())
)

print(f"Filas fact_compras_detalle: {df_silver.count()}")

# COMMAND ----------

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
print(f"✅ fact_compras_detalle: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
