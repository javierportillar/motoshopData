# Databricks notebook source
# MAGIC %md
# MAGIC # 14 · fact_inventario — desde bronze.auxinventario
# MAGIC
# MAGIC Auxiliar de inventario. `business_date` se deriva de `docfec` (ADR-0013).
# MAGIC **Esquema real:** 35 columnas en bronze.
# MAGIC **Nota:** `valor3` parece ser la cantidad/campo de stock.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.fact_inventario"

# COMMAND ----------

dbutils.widgets.text("business_date", "")
business_date = dbutils.widgets.get("business_date")

# COMMAND ----------

from pyspark.sql.functions import col, current_date, monotonically_increasing_id

df_bronze = spark.table(f"{BRONZE}.auxinventario")
print(f"Filas bronze.auxinventario: {df_bronze.count()}")

# COMMAND ----------

df_silver = (
    df_bronze
    .select(
        monotonically_increasing_id().alias("id_inventario"),
        col("codlis").alias("cod_lista"),
        col("nomlis").alias("nombre_lista"),
        col("codlin1").alias("cod_linea1"),
        col("nomlin").alias("nombre_linea"),
        col("codlin2").alias("cod_linea2"),
        col("nomlin2").alias("nombre_linea2"),
        col("codbod").alias("cod_bodega"),
        col("nombod").alias("nombre_bodega"),
        col("nitter").alias("nit_tercero"),
        col("nomter").alias("nombre_tercero"),
        col("numdoc").alias("num_documento"),
        col("nomdoc").alias("nombre_documento"),
        col("codprod").alias("cod_producto"),
        col("sernum").alias("num_serie"),
        col("nomprod").alias("nombre_producto"),
        col("unimed").alias("unidad_medida"),
        col("valor1").cast("double").alias("valor_costo"),
        col("valor2").cast("double").alias("valor_venta"),
        col("valor3").cast("double").alias("cantidad"),
        col("valor4").cast("double").alias("valor4"),
        col("valor5").cast("double").alias("valor5"),
        col("docfec").cast("date").alias("business_date"),
        col("docnum").alias("num_doc_referencia"),
        col("nomsub").alias("nombre_sub"),
        col("multiplo").cast("double").alias("multiplo"),
        col("codcos").alias("cod_centro_costo"),
        col("nomcos").alias("nombre_centro_costo"),
    )
    .where(
        (col("business_date").isNotNull()) &
        (col("business_date") >= "2020-01-01") &
        (col("business_date") <= current_date())
    )
)

print(f"Filas fact_inventario: {df_silver.count()}")

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
print(f"✅ fact_inventario: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
