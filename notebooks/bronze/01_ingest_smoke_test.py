# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Smoke Test — Ingesta Bronze
# MAGIC
# MAGIC **Objetivo:** Validar que la conectividad Databricks → MySQL funciona y que podemos escribir en el catálogo `motoshop.bronze`.
# MAGIC
# MAGIC **Estrategia (P1 · Opción A):** self-hosted dump → cloud storage. Este notebook lee desde cloud storage donde el script local deja los dumps.
# MAGIC
# MAGIC **Verificación crítica #3 de F0:** ¿La conectividad Databricks → MySQL local funciona end-to-end?

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuración

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.functions import lit
from datetime import datetime, date

CATALOG = "motoshop"
BRONZE  = "bronze"
TABLE   = "sucursales"
INGEST_DATE = date.today().isoformat()

print(f"Catálogo: {CATALOG}")
print(f"Esquema:  {BRONZE}")
print(f"Tabla:    {TABLE}")
print(f"Fecha:    {INGEST_DATE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Ruta de datos
# MAGIC
# MAGIC Los dumps llegan a cloud storage desde el script `infra/backup_mysql.ps1` (o .sh).
# MAGIC Ajustar la ruta según el cloud storage que se use (S3, ADLS, GCS).
# MAGIC
# MAGIC Formato esperado: `parquet` particionado por `ingest_date`.

# COMMAND ----------

# Ruta temporal — ajustar cuando se defina el cloud storage
CLOUD_PATH = "dbfs:/mnt/motoshop/bronze"

# Para el smoke test, creamos datos sintéticos pequeños
# (reemplazar con lectura real cuando el dump pipeline esté listo)
data = [
    (1, "001", "Casa Matriz", "Calle 1 #2-3", "Activa"),
    (2, "002", "Sucursal Norte", "Carrera 4 #5-6", "Activa"),
    (3, "003", "Sucursal Sur", "Avenida 7 #8-9", "Inactiva"),
]

columns = ["id_sucursal", "codbod", "nombod", "direccion", "estado"]
df = spark.createDataFrame(data, columns)
df = df.withColumn("ingest_date", lit(INGEST_DATE))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Escribir a Bronze

# COMMAND ----------

target_table = f"{CATALOG}.{BRONZE}.{TABLE}"
print(f"Escribiendo a: {target_table}")

df.write \
    .mode("overwrite") \
    .partitionBy("ingest_date") \
    .format("delta") \
    .saveAsTable(target_table)

print("✅ Escritura completada")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Validación

# COMMAND ----------

result = spark.sql(f"SELECT COUNT(*) AS total FROM {target_table} WHERE ingest_date = '{INGEST_DATE}'")
result.show()

count = result.collect()[0]["total"]
expected = len(data)
assert count == expected, f"❌ Esperado {expected}, obtenido {count}"
print(f"✅ Validación exitosa: {count} filas en bronze.{TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Limpieza (opcional)
# MAGIC
# MAGIC Descomentar si se quiere eliminar la tabla de prueba después del smoke test.

# COMMAND ----------

# spark.sql(f"DROP TABLE IF EXISTS {target_table}")
# print(f"Tabla {target_table} eliminada")
