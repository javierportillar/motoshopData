# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · dim_producto — SCD Type 1 desde bronze.productos
# MAGIC
# MAGIC Snapshot del estado actual del catálogo de productos.
# MAGIC Aplica TRIM a campos de texto y tipado formal.
# MAGIC
# MAGIC **DT-F2-2:** SCD Type 1 (snapshot del estado actual).
# MAGIC **DT-F2-5:** Naming `dim_producto` en esquema `silver`.
# MAGIC **Esquema real:** 77 columnas en bronze (ver `full_schema_survey_2026-05-29.md`).

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.dim_producto"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Leer último snapshot de bronze.productos

# COMMAND ----------

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, trim, current_date

df_bronze: DataFrame = spark.table(f"{BRONZE}.productos")
print(f"Filas bronze.productos: {df_bronze.count()}")
print("Columnas:", df_bronze.columns)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Transformación: SCD1 + TRIM + tipados
# MAGIC
# MAGIC Seleccionamos las columnas más relevantes para F2-F4.
# MAGIC Las 77 columnas completas permanecen en bronze para auditoría.

# COMMAND ----------

df_silver = (
    df_bronze
    .select(
        trim(col("codprod")).alias("cod_producto"),
        trim(col("nomprod")).alias("nombre_producto"),
        trim(col("codbar")).alias("codigo_barras"),
        trim(col("unimed")).alias("unidad_medida"),
        trim(col("codmed")).alias("cod_medida"),
        col("valmed").cast("double").alias("valor_medida"),
        trim(col("presen")).alias("presentacion"),
        trim(col("codcla")).alias("cod_clase"),
        trim(col("codsubcla")).alias("cod_subclase"),
        col("stockmin").cast("double").alias("stock_minimo"),
        col("stockmax").cast("double").alias("stock_maximo"),
        col("exiprod").cast("double").alias("existencia"),
        col("cosprod").cast("double").alias("costo_producto"),
        col("cosulc").cast("double").alias("costo_ultima_compra"),
        col("pvsini").cast("double").alias("precio_venta_sin_iva"),
        col("pvconi").cast("double").alias("precio_venta_con_iva"),
        trim(col("actprod")).alias("estado_producto"),
        trim(col("codpor")).alias("cod_grupo"),
        trim(col("codlin1")).alias("cod_linea1"),
        trim(col("desprod")).alias("descripcion"),
        trim(col("nitter")).alias("nit_proveedor"),
        trim(col("codbod")).alias("cod_bodega_default"),
        col("fecapa").cast("date").alias("fecha_actualizacion"),
        current_date().alias("snapshot_date"),
    )
    .where(col("cod_producto").isNotNull())
    .dropDuplicates(["cod_producto"])
)

print(f"Filas dimension producto: {df_silver.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Validación: clave única no nula

# COMMAND ----------

pk_count = df_silver.count()
pk_distinct = df_silver.select("cod_producto").distinct().count()
assert pk_count == pk_distinct, (
    f"❌ Duplicados en dim_producto: {pk_count} filas vs {pk_distinct} únicas"
)
print(f"✅ PK única: {pk_count} filas, {pk_distinct} únicas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Escritura a silver (SCD1: sobrescribe completo)

# COMMAND ----------

df_silver.write.format("delta").mode("overwrite").saveAsTable(TARGET)
print(f"✅ Escritura {TARGET} completada")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Verificación final

# COMMAND ----------

final_count = spark.table(TARGET).count()
print(f"dim_producto: {final_count} filas en silver")
display(spark.table(TARGET).limit(10))
