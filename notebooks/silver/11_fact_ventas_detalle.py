# Databricks notebook source
# MAGIC %md
# MAGIC # 11 · fact_ventas_detalle — desde bronze.detfventas
# MAGIC
# MAGIC Detalle de facturas de venta. JOIN con `fact_ventas` para heredar `business_date`.
# MAGIC **Esquema real:** 38 columnas en bronze.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.fact_ventas_detalle"

# COMMAND ----------

dbutils.widgets.text("business_date", "")
business_date = dbutils.widgets.get("business_date")

# COMMAND ----------

from pyspark.sql.functions import col, current_date

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Leer bronze.detfventas

# COMMAND ----------

df_bronze = spark.table(f"{BRONZE}.detfventas")
print(f"Filas bronze.detfventas: {df_bronze.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · JOIN con fact_ventas para heredar business_date

# COMMAND ----------

# business_date viene de facventas vía numfven + codclas
# Si fact_ventas aún no existe, usamosfecfven de detfventas no existe directamente,
# así que necesitamos el header.
try:
    df_header = spark.table(f"{SILVER}.fact_ventas").select(
        col("num_documento").alias("numfven"),
        col("cod_clase").alias("codclas"),
        col("business_date"),
    )
    has_header = True
except Exception:
    has_header = False
    print("⚠️ fact_ventas no existe aún — se usa business_date = CURRENT_DATE como fallback")

if has_header:
    df_joined = (
        df_bronze
        .join(df_header, on=["numfven", "codclas"], how="inner")
    )
else:
    from pyspark.sql.functions import current_date as cur_date
    df_joined = df_bronze.withColumn("business_date", cur_date())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Transformación

# COMMAND ----------

df_silver = (
    df_joined
    .select(
        col("numfven").alias("num_documento"),
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

print(f"Filas fact_ventas_detalle: {df_silver.count()}")

# COMMAND ----------

# Escritura
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
print(f"✅ fact_ventas_detalle: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
