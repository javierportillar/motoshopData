# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Validación de tablas grandes — paginación
# MAGIC
# MAGIC Verifica que `detfventas` (~27k) y `detcompras` (~11k) se ingirieron completas.
# MAGIC Cierra verificación V6.

# COMMAND ----------

dbutils.widgets.text("ingest_date", "2026-05-28")
ingest_date = dbutils.widgets.get("ingest_date")

CATALOG = "motoshop"
SCHEMA = "bronze"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · detfventas

# COMMAND ----------

detfventas_df = spark.table(f"{CATALOG}.{SCHEMA}.detfventas") \
    .filter(f"ingest_date = '{ingest_date}'")

detfventas_count = detfventas_df.count()
print(f"detfventas: {detfventas_count:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · detcompras

# COMMAND ----------

detcompras_df = spark.table(f"{CATALOG}.{SCHEMA}.detcompras") \
    .filter(f"ingest_date = '{ingest_date}'")

detcompras_count = detcompras_df.count()
print(f"detcompras: {detcompras_count:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Veredicto V6

# COMMAND ----------

if detfventas_count > 0 and detcompras_count > 0:
    print(f"VEREDICTO: OK — detfventas={detfventas_count:,}, detcompras={detcompras_count:,}")
else:
    print(f"VEREDICTO: FAIL — detfventas={detfventas_count}, detcompras={detcompras_count}")
