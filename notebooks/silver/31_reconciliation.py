# Databricks notebook source
# MAGIC %md
# MAGIC # 31 · Reconciliation — Silver vs Bronze (proxy sgHermes)
# MAGIC
# MAGIC V3: Compara totales de silver con bronze como proxy de sgHermes.
# MAGIC Tolerancia: < 0.5% diferencia.
# MAGIC
# MAGIC **Nota:** bronze es la fuente más cercana a sgHermes (snapshot 1:1).
# MAGIC La reconciliación compara `SUM(total)` entre silver y bronze para el mes pasado.

# COMMAND ----------

CATALOG = "motoshop"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"

# COMMAND ----------

from pyspark.sql.functions import col, sum as spark_sum, abs as spark_abs, when, month, year, current_date
from datetime import date, timedelta

today = date.today().isoformat()
# Mes pasado
first_of_this_month = date.today().replace(day=1)
last_month_end = first_of_this_month - timedelta(days=1)
last_month_start = last_month_end.replace(day=1)

print(f"Período de reconciliación: {last_month_start} a {last_month_end}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Reconciliación fact_ventas

# COMMAND ----------

print("=" * 50)
print("  V3 · Reconciliación Silver vs Bronze — fact_ventas")
print("=" * 50)

try:
    # Bronze: sumar totfven del mes pasado (proxy sgHermes)
    df_bronzeventas = spark.table(f"{BRONZE}.facventas").where(
        (col("estfven") == "A") &
        (col("fecfven").cast("date") >= last_month_start) &
        (col("fecfven").cast("date") <= last_month_end)
    )
    bronze_total = df_bronzeventas.agg(spark_sum("totfven")).collect()[0][0] or 0
    bronze_count = df_bronzeventas.count()

    # Silver: sumar total_factura del mes pasado
    df_silverventas = spark.table(f"{SILVER}.fact_ventas").where(
        (col("business_date") >= last_month_start) &
        (col("business_date") <= last_month_end)
    )
    silver_total = df_silverventas.agg(spark_sum("total_factura")).collect()[0][0] or 0
    silver_count = df_silverventas.count()

    # Comparación
    diff_abs = abs(bronze_total - silver_total)
    diff_pct = (diff_abs / bronze_total * 100) if bronze_total > 0 else 0

    print(f"\n  Bronze (proxy sgHermes): {bronze_count} facturas, ${bronze_total:,.2f}")
    print(f"  Silver:                 {silver_count} facturas, ${silver_total:,.2f}")
    print(f"  Diferencia:             ${diff_abs:,.2f} ({diff_pct:.2f}%)")

    status_ventas = "PASS" if diff_pct < 0.5 else "FAIL"
    icon = "✅" if status_ventas == "PASS" else "❌"
    print(f"  {icon} Veredicto: {status_ventas}")

except Exception as e:
    print(f"  ⚠️ Error: {str(e)[:100]}")
    status_ventas = "ERROR"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Reconciliación fact_compras

# COMMAND ----------

print("\n" + "=" * 50)
print("  V3 · Reconciliación Silver vs Bronze — fact_compras")
print("=" * 50)

try:
    df_bronzecomp = spark.table(f"{BRONZE}.compras").where(
        (col("estcom") == "A") &
        (col("feccom").cast("date") >= last_month_start) &
        (col("feccom").cast("date") <= last_month_end)
    )
    bronze_total_comp = df_bronzecomp.agg(spark_sum("totcom")).collect()[0][0] or 0
    bronze_count_comp = df_bronzecomp.count()

    df_silvercomp = spark.table(f"{SILVER}.fact_compras").where(
        (col("business_date") >= last_month_start) &
        (col("business_date") <= last_month_end)
    )
    silver_total_comp = df_silvercomp.agg(spark_sum("total_compra")).collect()[0][0] or 0
    silver_count_comp = df_silvercomp.count()

    diff_abs_comp = abs(bronze_total_comp - silver_total_comp)
    diff_pct_comp = (diff_abs_comp / bronze_total_comp * 100) if bronze_total_comp > 0 else 0

    print(f"\n  Bronze: {bronze_count_comp} compras, ${bronze_total_comp:,.2f}")
    print(f"  Silver: {silver_count_comp} compras, ${silver_total_comp:,.2f}")
    print(f"  Diferencia: ${diff_abs_comp:,.2f} ({diff_pct_comp:.2f}%)")

    status_compras = "PASS" if diff_pct_comp < 0.5 else "FAIL"
    icon = "✅" if status_compras == "PASS" else "❌"
    print(f"  {icon} Veredicto: {status_compras}")

except Exception as e:
    print(f"  ⚠️ Error: {str(e)[:100]}")
    status_compras = "ERROR"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Top SKUs mes pasado

# COMMAND ----------

print("\n" + "=" * 50)
print("  Top 10 SKUs por ventas (mes pasado)")
print("=" * 50)

try:
    df_detalle = spark.table(f"{SILVER}.fact_ventas_detalle").where(
        (col("business_date") >= last_month_start) &
        (col("business_date") <= last_month_end)
    )
    top_skus = (
        df_detalle
        .groupBy("cod_producto")
        .agg(spark_sum("total_detalle").alias("total_ventas"))
        .orderBy(col("total_ventas").desc())
        .limit(10)
    )
    display(top_skus)
except Exception as e:
    print(f"  ⚠️ No disponible: {str(e)[:60]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Resumen final

# COMMAND ----------

print(f"\n{'='*50}")
print(f"  RESUMEN RECONCILIACIÓN — {today}")
print(f"  Período: {last_month_start} a {last_month_end}")
print(f"{'='*50}")
print(f"  V3 fact_ventas:   {status_ventas}")
print(f"  V3 fact_compras:  {status_compras}")

overall = "PASS" if (status_ventas == "PASS" and status_compras == "PASS") else "FAIL"
icon = "✅" if overall == "PASS" else "❌"
print(f"\n  {icon} VEREDICTO GENERAL: {overall}")

if overall == "FAIL":
    print("\n  ⚠️ Acción requerida: investigar diferencias > 0.5%")
    print("  Causas comunes: documentos anulados, redondeo, timezone")
