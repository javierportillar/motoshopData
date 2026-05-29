# Databricks notebook source
# MAGIC %md
# MAGIC # 10 · fact_ventas — desde bronze.facventas
# MAGIC
# MAGIC Patrón idempotente `INSERT INTO ... REPLACE WHERE business_date = '...'` (DT-F2-1).
# MAGIC `business_date` se deriva de `fecfven` (ADR-0013 opción C).
# MAGIC Solo documentos activos (`estfven = 'A'`).
# MAGIC
# MAGIC **Esquema real:** 65 columnas en bronze. Seleccionamos las más relevantes.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.fact_ventas"

# COMMAND ----------

dbutils.widgets.text("business_date", "")
business_date = dbutils.widgets.get("business_date")
print(f"business_date: {business_date}")

# COMMAND ----------

from pyspark.sql.functions import col, lit, trim, current_date

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Leer y transformar

# COMMAND ----------

df_bronze = spark.table(f"{BRONZE}.facventas")
print(f"Filas bronze.facventas: {df_bronze.count()}")

# COMMAND ----------

df_silver = (
    df_bronze
    .where(col("estfven") == "A")  # Solo activos
    .select(
        trim(col("numfven")).alias("num_documento"),
        trim(col("codclas")).alias("cod_clase"),
        trim(col("prefven")).alias("prefijo"),
        col("fecfven").cast("timestamp").alias("fecha_documento_ts"),
        col("fecfven").cast("date").alias("business_date"),
        trim(col("nitter")).alias("nit_cliente"),
        trim(col("clifven")).alias("nombre_cliente"),
        trim(col("nitvend")).alias("nit_vendedor"),
        trim(col("venfven")).alias("nombre_vendedor"),
        trim(col("codpag")).alias("cod_formapago"),
        col("diasfven").cast("int").alias("dias_formapago"),
        col("subfven").cast("double").alias("subtotal"),
        col("totdct").cast("double").alias("total_descuentos"),
        col("totiva").cast("double").alias("total_iva"),
        col("totipo").cast("double").alias("total_impuesto"),
        col("retfte").cast("double").alias("retencion_fuente"),
        col("retiva").cast("double").alias("retencion_iva"),
        col("retica").cast("double").alias("retencion_ica"),
        col("totfven").cast("double").alias("total_factura"),
        trim(col("obsfven")).alias("observaciones"),
        trim(col("estfven")).alias("estado_documento"),
        trim(col("codsuc")).alias("cod_sucursal"),
        trim(col("codemp")).alias("cod_empresa"),
        trim(col("empcod")).alias("cod_empresa_alt"),
        trim(col("codres")).alias("cod_resolucion"),
        current_date().alias("ingest_date_silver"),
    )
    .where(
        (col("business_date").isNotNull()) &
        (col("business_date") >= "2020-01-01") &
        (col("business_date") <= current_date())
    )
    .dropDuplicates(["num_documento", "cod_clase", "business_date"])
)

print(f"Filas fact_ventas transformadas: {df_silver.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Escritura idempotente (DT-F2-1)

# COMMAND ----------

if business_date:
    df_silver = df_silver.where(col("business_date") == business_date)

# Crear tabla si no existe, luego INSERT REPLACE WHERE
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

# MAGIC %md
# MAGIC ## 3 · Validación

# COMMAND ----------

final_count = spark.table(TARGET).count()
print(f"✅ fact_ventas: {final_count} filas en silver")

# Verificar PK única
if final_count > 0:
    pk_count = spark.table(TARGET).select(
        "num_documento", "cod_clase", "business_date"
    ).count()
    pk_distinct = spark.table(TARGET).select(
        "num_documento", "cod_clase", "business_date"
    ).distinct().count()
    assert pk_count == pk_distinct, (
        f"❌ Duplicados en fact_ventas: {pk_count} vs {pk_distinct}"
    )
    print(f"✅ PK única: {pk_count}")

# COMMAND ----------

display(spark.table(TARGET).limit(10))
