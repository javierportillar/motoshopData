# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Detección de schema drift
# MAGIC
# MAGIC Compara el esquema entre 2 ingest_dates para detectar cambios
# MAGIC inesperados en columnas o tipos. Cumple verificación V7.

# COMMAND ----------

dbutils.widgets.text("ingest_date_a", "2026-05-28")
dbutils.widgets.text("ingest_date_b", "2026-05-28")

ingest_date_a = dbutils.widgets.get("ingest_date_a")
ingest_date_b = dbutils.widgets.get("ingest_date_b")

CATALOG = "motoshop"
SCHEMA = "bronze"

TABLES = [
    "bodegas", "sucursales", "formapago", "subproduct",
    "productos", "preciosxpro", "terceros", "auxinventario",
    "facventas", "detfventas", "compras", "detcompras",
]

# COMMAND ----------

def get_schema(table, ingest_date):
    """Obtiene el esquema de una tabla para una fecha de ingesta específica."""
    try:
        df = spark.table(f"{CATALOG}.{SCHEMA}.{table}").filter(f"ingest_date = '{ingest_date}'")
        return [(f.name, str(f.dataType), f.nullable) for f in df.schema.fields]
    except Exception:
        return []

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Comparar esquemas

# COMMAND ----------

drift = []
stable = []

for table in TABLES:
    schema_a = get_schema(table, ingest_date_a)
    schema_b = get_schema(table, ingest_date_b)
    
    if not schema_a:
        drift.append((table, "no existe en fecha A"))
        continue
    if not schema_b:
        drift.append((table, "no existe en fecha B"))
        continue
    
    set_a = set(schema_a)
    set_b = set(schema_b)
    
    if set_a == set_b:
        stable.append(table)
    else:
        diff = set_a.symmetric_difference(set_b)
        drift.append((table, diff))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Resultados

# COMMAND ----------

print(f"Esquema A: {ingest_date_a}")
print(f"Esquema B: {ingest_date_b}")
print(f"\nTablas estables: {len(stable)}/{len(TABLES)}")
for t in stable:
    print(f"  OK {t}")

if drift:
    print(f"\nDrift detectado: {len(drift)} tabla(s)")
    for t, diff in drift:
        print(f"  DRIFT {t}: {diff}")
else:
    print("\nSin drift detectado")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Veredicto V7

# COMMAND ----------

if len(stable) == len(TABLES):
    print(f"VEREDICTO: OK — las {len(TABLES)} tablas tienen esquema estable entre {ingest_date_a} y {ingest_date_b}")
elif drift:
    print(f"VEREDICTO: FAIL — drift detectado en {len(drift)} tabla(s)")
else:
    print(f"VEREDICTO: WARN — solo {len(stable)} tablas comparadas")
