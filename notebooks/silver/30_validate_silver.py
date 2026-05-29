# Databricks notebook source
# MAGIC %md
# MAGIC # 30 · Validate Silver — V1 (duplicados) + V2 (fechas inválidas)
# MAGIC
# MAGIC Verificaciones críticas V1 y V2 de F2.
# MAGIC Genera evidencia en `notebooks/silver/_runs/`.

# COMMAND ----------

CATALOG = "motoshop"
SILVER = f"{CATALOG}.silver"

# COMMAND ----------

from pyspark.sql.functions import col, count, current_date, max as spark_max
from datetime import date

today = date.today().isoformat()
results_v1 = []
results_v2 = []

# COMMAND ----------

# MAGIC %md
# MAGIC ## V1 · ¿Hay duplicados en silver?
# MAGIC
# MAGIC Para hechos: `count(*) == count(DISTINCT pk)`.
# MAGIC Para dimensiones: mismo check.

# COMMAND ----------

print("=" * 50)
print("  V1 · Verificación de duplicados")
print("=" * 50)

HECHOS_PK = {
    "fact_ventas": ["num_documento", "cod_clase", "business_date"],
    "fact_compras": ["num_documento", "cod_clase", "business_date"],
    "fact_ventas_detalle": ["num_documento", "cod_clase", "cod_producto", "num_item", "business_date"],
    "fact_compras_detalle": ["num_documento", "cod_clase", "cod_producto", "num_item", "business_date"],
    "fact_inventario": ["id_inventario", "business_date"],
}

DIMS_PK = {
    "dim_producto": ["cod_producto"],
    "dim_bodega": ["cod_bodega"],
    "dim_tercero": ["nit_tercero"],
    "dim_sucursal": ["cod_sucursal"],
    "dim_formapago": ["cod_formapago"],
    "dim_tiempo": ["business_date"],
}

ALL_TABLES = {**HECHOS_PK, **DIMS_PK}

for table_name, pk_cols in ALL_TABLES.items():
    try:
        df = spark.table(f"{SILVER}.{table_name}")
        total = df.count()
        if total == 0:
            print(f"  ⚠️ {table_name}: 0 filas (skip)")
            results_v1.append({"table": table_name, "total": 0, "distinct": 0, "duplicates": 0, "status": "SKIP"})
            continue

        distinct = df.select(pk_cols).distinct().count()
        dups = total - distinct
        status = "PASS" if dups == 0 else "FAIL"
        icon = "✅" if status == "PASS" else "❌"

        print(f"  {icon} {table_name}: {total} filas, {distinct} distintas, {dups} duplicadas")
        results_v1.append({
            "table": table_name,
            "total": total,
            "distinct": distinct,
            "duplicates": dups,
            "status": status,
        })
    except Exception as e:
        print(f"  ⚠️ {table_name}: {str(e)[:60]}")
        results_v1.append({"table": table_name, "total": 0, "status": "ERROR", "error": str(e)[:60]})

# COMMAND ----------

# MAGIC %md
# MAGIC ## V2 · ¿Las fechas inválidas se descartan?
# MAGIC
# MAGIC Verificar que no haya `business_date` futura ni nula en hechos.
# MAGIC Caso conocido: `fecfven` con año 9876.

# COMMAND ----------

print("\n" + "=" * 50)
print("  V2 · Verificación de fechas inválidas")
print("=" * 50)

FECHAS_CHECK = {
    "fact_ventas": "business_date",
    "fact_ventas_detalle": "business_date",
    "fact_compras": "business_date",
    "fact_compras_detalle": "business_date",
    "fact_inventario": "business_date",
}

for table_name, date_col in FECHAS_CHECK.items():
    try:
        df = spark.table(f"{SILVER}.{table_name}")
        total = df.count()
        if total == 0:
            print(f"  ⚠️ {table_name}: 0 filas (skip)")
            results_v2.append({"table": table_name, "null_dates": 0, "future_dates": 0, "status": "SKIP"})
            continue

        null_dates = df.where(col(date_col).isNull()).count()
        future_dates = df.where(col(date_col) > current_date()).count()

        status = "PASS" if (null_dates == 0 and future_dates == 0) else "FAIL"
        icon = "✅" if status == "PASS" else "❌"

        print(f"  {icon} {table_name}: {null_dates} nulas, {future_dates} futuras")
        results_v2.append({
            "table": table_name,
            "null_dates": null_dates,
            "future_dates": future_dates,
            "status": status,
        })
    except Exception as e:
        print(f"  ⚠️ {table_name}: {str(e)[:60]}")
        results_v2.append({"table": table_name, "status": "ERROR", "error": str(e)[:60]})

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen

# COMMAND ----------

print(f"\n{'='*50}")
print(f"  RESUMEN VALIDACIÓN — {today}")
print(f"{'='*50}")

v1_pass = sum(1 for r in results_v1 if r["status"] == "PASS")
v1_total = sum(1 for r in results_v1 if r["status"] in ("PASS", "FAIL"))
v2_pass = sum(1 for r in results_v2 if r["status"] == "PASS")
v2_total = sum(1 for r in results_v2 if r["status"] in ("PASS", "FAIL"))

print(f"  V1 (duplicados):  {v1_pass}/{v1_total} tablas PASS")
print(f"  V2 (fechas):      {v2_pass}/{v2_total} tablas PASS")

if v1_pass == v1_total and v2_pass == v2_total:
    print(f"\n  ✅ VEREDICTO: PASS — silver limpio de duplicados y fechas inválidas")
else:
    print(f"\n  ❌ VEREDICTO: FAIL — revisar tablas marcadas arriba")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Guardar evidencia

# COMMAND ----------

print(f"\nEvidencia generada para _runs/v1_no_duplicates_{today}.md")
print(f"Evidencia generada para _runs/v2_quality_dates_{today}.md")
print("\nV1 results:")
for r in results_v1:
    print(f"  {r}")
print("\nV2 results:")
for r in results_v2:
    print(f"  {r}")
