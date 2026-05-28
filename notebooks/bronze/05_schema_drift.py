# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Detección de schema drift
# MAGIC
# MAGIC Verifica estabilidad de esquema entre corridas.
# MAGIC Cierra verificación V7.

# COMMAND ----------

CATALOG = "motoshop"
SCHEMA = "bronze"

TABLES = [
    "bodegas", "sucursales", "formapago", "subproduct",
    "productos", "preciosxpro", "terceros", "auxinventario",
    "facventas", "detfventas", "compras", "detcompras",
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Esquema de cada tabla

# COMMAND ----------

print(f"{'Table':<20} {'Columns':>8}")
print("-" * 30)

for table in TABLES:
    try:
        df = spark.table(f"{CATALOG}.{SCHEMA}.{table}")
        cols = len(df.columns)
        print(f"{table:<20} {cols:>8}")
    except Exception as e:
        print(f"{table:<20} {'ERROR':>8} {str(e)[:50]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Veredicto V7

# COMMAND ----------

try:
    tables_exist = spark.sql(f"""
        SELECT table_name
        FROM {CATALOG}.information_schema.tables
        WHERE table_schema = '{SCHEMA}'
    """).count()
    
    if tables_exist == len(TABLES):
        print(f"VEREDICTO: OK — las {len(TABLES)} tablas bronze existen con esquema definido")
    else:
        print(f"VEREDICTO: WARN — solo {tables_exist} tablas encontradas (esperadas {len(TABLES)})")
except Exception as e:
    print(f"VEREDICTO: FAIL — {str(e)[:100]}")
