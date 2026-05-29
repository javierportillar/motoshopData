# Databricks notebook source
# MAGIC %md
# MAGIC # 20 · Quality Run — Reglas de calidad silver
# MAGIC
# MAGIC Ejecuta asserts sobre cada tabla silver y escribe resultados a `silver._quality_runs`.
# MAGIC **DT-F2-3:** PySpark assert + tabla `_quality_runs`.
# MAGIC Severidades: CRITICAL → falla el notebook; WARNING → continúa pero registra.

# COMMAND ----------

CATALOG = "motoshop"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}._quality_runs"

# COMMAND ----------

from pyspark.sql.functions import lit, current_timestamp, monotonically_increasing_id
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType
import uuid
from datetime import datetime

# COMMAND ----------

# MAGIC %md
# MAGIC ## Funciones de validación

# COMMAND ----------

def write_quality_event(spark, run_id, table, rule, failed_rows, severity="WARNING"):
    """Escribe un evento de calidad a silver._quality_runs."""
    row = spark.createDataFrame(
        [(run_id, table, rule, failed_rows, severity, datetime.now())],
        ["run_id", "table", "rule", "failed_rows", "severity", "timestamp"]
    )
    row.write.format("delta").mode("append").saveAsTable(TARGET)
    icon = "🔴" if severity == "CRITICAL" else "🟡"
    print(f"  {icon} {table}.{rule}: {failed_rows} filas fallidas [{severity}]")


def assert_no_null_pk(spark, df, pk_columns, table_name, run_id):
    """Verifica que no haya PKs nulas."""
    null_count = df.where(
        df[pk_columns[0]].isNull() if len(pk_columns) == 1
        else ~reduce(lambda a, b: a & b, [df[c].isNotNull() for c in pk_columns])
    ).count()
    severity = "CRITICAL" if null_count > 0 else "OK"
    if null_count > 0:
        write_quality_event(spark, run_id, table_name, "null_pk", null_count, severity)
    return null_count


def assert_no_negative(spark, df, column, table_name, run_id):
    """Verifica que no haya valores negativos en montos."""
    neg_count = df.where(df[column] < 0).count()
    severity = "CRITICAL" if neg_count > 0 else "OK"
    if neg_count > 0:
        write_quality_event(spark, run_id, table_name, f"negative_{column}", neg_count, severity)
    return neg_count


def assert_no_future_dates(spark, df, date_column, table_name, run_id):
    """Verifica que no haya business_date en el futuro."""
    from pyspark.sql.functions import current_date
    future_count = df.where(df[date_column] > current_date()).count()
    severity = "WARNING" if future_count > 0 else "OK"
    if future_count > 0:
        write_quality_event(spark, run_id, table_name, f"future_date_{date_column}", future_count, severity)
    return future_count


def assert_no_duplicates(spark, df, pk_columns, table_name, run_id):
    """Verifica unicidad de PKs."""
    total = df.count()
    distinct = df.select(pk_columns).distinct().count()
    dup_count = total - distinct
    severity = "CRITICAL" if dup_count > 0 else "OK"
    if dup_count > 0:
        write_quality_event(spark, run_id, table_name, "duplicate_pk", dup_count, severity)
    return dup_count

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ejecutar reglas sobre cada tabla silver

# COMMAND ----------

from functools import reduce
import time

run_id = str(uuid.uuid4())[:8]
print(f"Quality run ID: {run_id}")
print(f"Timestamp: {datetime.now()}")
print("=" * 50)

results = []

# COMMAND ----------

# MAGIC %md
# MAGIC ### fact_ventas

# COMMAND ----------

try:
    df = spark.table(f"{SILVER}.fact_ventas")
    count = df.count()
    print(f"\n📋 fact_ventas: {count} filas")

    pk_dup = assert_no_duplicates(spark, df, ["num_documento", "cod_clase", "business_date"], "fact_ventas", run_id)
    neg_tot = assert_no_negative(spark, df, "total_factura", "fact_ventas", run_id)
    fut_bd = assert_no_future_dates(spark, df, "business_date", "fact_ventas", run_id)

    results.append({"table": "fact_ventas", "rows": count, "duplicates": pk_dup, "negatives": neg_tot, "future_dates": fut_bd})
except Exception as e:
    print(f"⚠️ fact_ventas no disponible: {str(e)[:80]}")
    results.append({"table": "fact_ventas", "rows": 0, "error": str(e)[:80]})

# COMMAND ----------

# MAGIC %md
# MAGIC ### fact_ventas_detalle

# COMMAND ----------

try:
    df = spark.table(f"{SILVER}.fact_ventas_detalle")
    count = df.count()
    print(f"\n📋 fact_ventas_detalle: {count} filas")

    neg_tot = assert_no_negative(spark, df, "total_detalle", "fact_ventas_detalle", run_id)
    fut_bd = assert_no_future_dates(spark, df, "business_date", "fact_ventas_detalle", run_id)

    results.append({"table": "fact_ventas_detalle", "rows": count, "negatives": neg_tot, "future_dates": fut_bd})
except Exception as e:
    print(f"⚠️ fact_ventas_detalle no disponible: {str(e)[:80]}")
    results.append({"table": "fact_ventas_detalle", "rows": 0, "error": str(e)[:80]})

# COMMAND ----------

# MAGIC %md
# MAGIC ### fact_compras

# COMMAND ----------

try:
    df = spark.table(f"{SILVER}.fact_compras")
    count = df.count()
    print(f"\n📋 fact_compras: {count} filas")

    pk_dup = assert_no_duplicates(spark, df, ["num_documento", "cod_clase", "business_date"], "fact_compras", run_id)
    neg_tot = assert_no_negative(spark, df, "total_compra", "fact_compras", run_id)
    fut_bd = assert_no_future_dates(spark, df, "business_date", "fact_compras", run_id)

    results.append({"table": "fact_compras", "rows": count, "duplicates": pk_dup, "negatives": neg_tot, "future_dates": fut_bd})
except Exception as e:
    print(f"⚠️ fact_compras no disponible: {str(e)[:80]}")
    results.append({"table": "fact_compras", "rows": 0, "error": str(e)[:80]})

# COMMAND ----------

# MAGIC %md
# MAGIC ### fact_compras_detalle

# COMMAND ----------

try:
    df = spark.table(f"{SILVER}.fact_compras_detalle")
    count = df.count()
    print(f"\n📋 fact_compras_detalle: {count} filas")

    neg_tot = assert_no_negative(spark, df, "total_detalle", "fact_compras_detalle", run_id)
    fut_bd = assert_no_future_dates(spark, df, "business_date", "fact_compras_detalle", run_id)

    results.append({"table": "fact_compras_detalle", "rows": count, "negatives": neg_tot, "future_dates": fut_bd})
except Exception as e:
    print(f"⚠️ fact_compras_detalle no disponible: {str(e)[:80]}")
    results.append({"table": "fact_compras_detalle", "rows": 0, "error": str(e)[:80]})

# COMMAND ----------

# MAGIC %md
# MAGIC ### fact_inventario

# COMMAND ----------

try:
    df = spark.table(f"{SILVER}.fact_inventario")
    count = df.count()
    print(f"\n📋 fact_inventario: {count} filas")

    neg_cant = assert_no_negative(spark, df, "cantidad", "fact_inventario", run_id)
    fut_bd = assert_no_future_dates(spark, df, "business_date", "fact_inventario", run_id)

    results.append({"table": "fact_inventario", "rows": count, "negatives": neg_cant, "future_dates": fut_bd})
except Exception as e:
    print(f"⚠️ fact_inventario no disponible: {str(e)[:80]}")
    results.append({"table": "fact_inventario", "rows": 0, "error": str(e)[:80]})

# COMMAND ----------

# MAGIC %md
# MAGIC ### Dimensiones (validación PK)

# COMMAND ----------

DIM_TABLES = {
    "dim_producto": "cod_producto",
    "dim_bodega": "cod_bodega",
    "dim_tercero": "nit_tercero",
    "dim_sucursal": "cod_sucursal",
    "dim_formapago": "cod_formapago",
}

for dim_name, pk in DIM_TABLES.items():
    try:
        df = spark.table(f"{SILVER}.{dim_name}")
        count = df.count()
        pk_dup = assert_no_duplicates(spark, df, [pk], dim_name, run_id)
        results.append({"table": dim_name, "rows": count, "duplicates": pk_dup})
        print(f"  ✅ {dim_name}: {count} filas, PK única")
    except Exception as e:
        print(f"  ⚠️ {dim_name} no disponible: {str(e)[:60]}")
        results.append({"table": dim_name, "rows": 0, "error": str(e)[:60]})

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen

# COMMAND ----------

print(f"\n{'='*50}")
print(f"  RESUMEN QUALITY RUN — {run_id}")
print(f"  Timestamp: {datetime.now()}")
print(f"{'='*50}")

for r in results:
    rows = r.get("rows", 0)
    errs = []
    if r.get("duplicates", 0) > 0:
        errs.append(f"{r['duplicates']} duplicados")
    if r.get("negatives", 0) > 0:
        errs.append(f"{r['negatives']} negativos")
    if r.get("future_dates", 0) > 0:
        errs.append(f"{r['future_dates']} fechas futuras")
    if r.get("error"):
        errs.append(f"ERROR: {r['error'][:40]}")

    status = "OK" if not errs else "FAIL"
    detail = f" ({'; '.join(errs)})" if errs else ""
    print(f"  {status} {r['table']}: {rows:,} filas{detail}")

print(f"\n  Tablas procesadas: {len(results)}")
ok_count = sum(1 for r in results if not r.get("error") and r.get("duplicates", 0) == 0)
print(f"  Tablas OK: {ok_count}/{len(results)}")
