# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · dim_tercero — SCD Type 1 desde bronze.terceros
# MAGIC
# MAGIC Snapshot de terceros (clientes/proveedores).
# MAGIC **Esquema real:** 64 columnas en bronze. Seleccionamos las más relevantes.
# MAGIC **PII:** `nomter`, `razsoc` contienen nombre completo — pseudonimizar si datasets se comparten.
# MAGIC
# MAGIC **DT-F2-2:** SCD Type 1. **DT-F2-5:** `dim_tercero`.
# MAGIC **R-F2A-2:** Pseudonimización de PII (Habeas Data Col).

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.dim_tercero"

# COMMAND ----------

from pyspark.sql.functions import col, trim, current_date, sha2, concat_ws

df_bronze = spark.table(f"{BRONZE}.terceros")
print(f"Filas bronze.terceros: {df_bronze.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transformación + pseudonimización de nombre

# COMMAND ----------

df_silver = (
    df_bronze
    .select(
        trim(col("nitter")).alias("nit_tercero"),
        trim(col("tipnit")).alias("tipo_nit"),
        trim(col("digter")).alias("digito_verificador"),
        trim(col("perjur")).alias("persona_juridica"),
        trim(col("razsoc")).alias("razon_social"),
        trim(col("apeter")).alias("apellido1"),
        trim(col("apeter2")).alias("apellido2"),
        trim(col("nomter")).alias("nombre1"),
        trim(col("nomter2")).alias("nombre2"),
        trim(col("nomcom")).alias("nombre_completo"),
        # Pseudonimización: hash del nombre completo para datasets compartidos
        sha2(
            concat_ws(" ", trim(col("nomter")), trim(col("apeter"))),
            256
        ).alias("nombre_hash"),
        trim(col("dirter")).alias("direccion"),
        trim(col("telter")).alias("telefono"),
        trim(col("movter")).alias("movil"),
        trim(col("corele")).alias("email"),
        trim(col("codciu")).alias("cod_ciudad"),
        trim(col("cliter")).alias("clase_cliente"),
        trim(col("proter")).alias("clase_proveedor"),
        trim(col("empter")).alias("clase_empleado"),
        trim(col("venter")).alias("clase_vendedor"),
        col("fecnac").cast("date").alias("fecha_nacimiento"),
        col("feccrea").cast("date").alias("fecha_creacion"),
        trim(col("obster")).alias("observaciones"),
        current_date().alias("snapshot_date"),
    )
    .where(col("nit_tercero").isNotNull())
    .dropDuplicates(["nit_tercero"])
)

print(f"Filas dimension tercero: {df_silver.count()}")

# COMMAND ----------

# Validación PK
pk_count = df_silver.count()
pk_distinct = df_silver.select("nit_tercero").distinct().count()
assert pk_count == pk_distinct, (
    f"❌ Duplicados en dim_tercero: {pk_count} vs {pk_distinct}"
)
print(f"✅ PK única: {pk_count}")

# COMMAND ----------

# Escritura
df_silver.write.format("delta").mode("overwrite").saveAsTable(TARGET)
final_count = spark.table(TARGET).count()
print(f"✅ dim_tercero: {final_count} filas en silver")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Nota de PII
# MAGIC
# MAGIC `nombre1`, `nombre2`, `nombre_completo` contienen el nombre real del tercero.
# MAGIC `nombre_hash` es seguro para agregados y joins en datasets compartidos.
# MAGIC En la PWA, exponer solo `nombre_completo` al usuario autenticado.

# COMMAND ----------

display(spark.table(TARGET).limit(5))
