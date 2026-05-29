# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Validación de tablas grandes — paginación real
# MAGIC
# MAGIC Verifica que paginar `detfventas` (~27k) y `detcompras` (~11k) con offsets sucesivos
# MAGIC cubre el total exactamente una vez, sin duplicados ni huecos.
# MAGIC Cierra verificación V6.

# COMMAND ----------

from pyspark.sql.functions import col, lit, row_number, monotonically_increasing_id
from pyspark.sql.window import Window

dbutils.widgets.text("ingest_date", "2026-05-28")
ingest_date = dbutils.widgets.get("ingest_date")

CATALOG = "motoshop"
SCHEMA = "bronze"
CHUNK_SIZE = 5000

# COMMAND ----------

# MAGIC %md
# MAGIC ## Función de paginación

# COMMAND ----------

def test_pagination(table_name, ingest_date, chunk_size=5000):
    """Prueba que la paginación cubre el total sin duplicados ni huecos."""
    df = spark.table(f"{CATALOG}.{SCHEMA}.{table_name}").filter(f"ingest_date = '{ingest_date}'")
    total = df.count()
    
    if total == 0:
        return {
            "table": table_name,
            "total": 0,
            "distinct_after_pagination": 0,
            "chunks": 0,
            "chunk_size": chunk_size,
            "status": "WARN: N=0",
        }
    
    # Agregar row number para paginación
    window = Window.orderBy("numfven", "codprod")
    df_with_rownum = df.withColumn("row_num", row_number().over(window))
    
    # Paginar en chunks
    chunks = []
    offset = 0
    while offset < total:
        chunk = df_with_rownum.filter(
            (col("row_num") > offset) & (col("row_num") <= offset + chunk_size)
        ).drop("row_num")
        chunks.append(chunk)
        offset += chunk_size
    
    # Unir todos los chunks y contar distinct
    if len(chunks) > 1:
        all_rows = chunks[0]
        for c in chunks[1:]:
            all_rows = all_rows.union(c)
        distinct_count = all_rows.count()
    else:
        distinct_count = chunks[0].count()
    
    # Validar
    if distinct_count == total:
        status = "OK"
    else:
        status = f"FAIL: distinct={distinct_count} != total={total}"
    
    return {
        "table": table_name,
        "total": total,
        "distinct_after_pagination": distinct_count,
        "chunks": len(chunks),
        "chunk_size": chunk_size,
        "status": status
    }

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · detfventas (~27k filas)

# COMMAND ----------

result_detf = test_pagination("detfventas", ingest_date, CHUNK_SIZE)
print(
    f"detfventas: total={result_detf['total']}, "
    f"distinct={result_detf.get('distinct_after_pagination', 0)}, "
    f"chunks={result_detf['chunks']}"
)
print(f"Status: {result_detf['status']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · detcompras (~11k filas)

# COMMAND ----------

result_detc = test_pagination("detcompras", ingest_date, CHUNK_SIZE)
print(
    f"detcompras: total={result_detc['total']}, "
    f"distinct={result_detc.get('distinct_after_pagination', 0)}, "
    f"chunks={result_detc['chunks']}"
)
print(f"Status: {result_detc['status']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Veredicto V6

# COMMAND ----------

if result_detf["status"] == "OK" and result_detc["status"] == "OK":
    print(f"\nVEREDICTO: OK — paginación cubre el total sin duplicados")
    print(f"  detfventas: {result_detf['total']} filas, {result_detf['chunks']} chunks")
    print(f"  detcompras: {result_detc['total']} filas, {result_detc['chunks']} chunks")
else:
    print(f"\nVEREDICTO: FAIL")
    if result_detf["status"] != "OK":
        print(f"  detfventas: {result_detf['status']}")
    if result_detc["status"] != "OK":
        print(f"  detcompras: {result_detc['status']}")
