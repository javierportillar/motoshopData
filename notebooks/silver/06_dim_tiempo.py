# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · dim_tiempo — Calendario con festivos COL
# MAGIC
# MAGIC Genera una dimensión de tiempo con business_date, año, trimestre,
# MAGIC mes, día de la semana, y festivos colombianos.
# MAGIC
# MAGIC **DT-F2-5:** `dim_tiempo`. Rango: MIN(business_date) en fact_ventas hasta CURRENT_DATE + 365.

# COMMAND ----------

CATALOG = "motoshop"
SILVER = f"{CATALOG}.silver"
TARGET = f"{SILVER}.dim_tiempo"

# COMMAND ----------

from pyspark.sql.functions import (
    col, date_range, lit, dayofweek, month, quarter, year,
    dayofmonth, date_format, when, current_date, explode, sequence
)
from pyspark.sql.types import DateType

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Determinar rango de fechas

# COMMAND ----------

try:
    fact_ventas_exists = spark.sql(
        f"SHOW TABLES IN {CATALOG}.silver LIKE 'fact_ventas'"
    ).count() > 0
except Exception:
    fact_ventas_exists = False

if fact_ventas_exists:
    min_date = spark.sql(
        f"SELECT MIN(business_date) FROM {SILVER}.fact_ventas"
    ).collect()[0][0]
    if min_date is None:
        min_date = "2020-01-01"
else:
    min_date = "2020-01-01"

print(f"Fecha mínima: {min_date}")

# COMMAND ----------

df_dates = spark.sql(f"""
    SELECT explode(sequence(
        TO_DATE('{min_date}'),
        DATE_ADD(CURRENT_DATE(), 365),
        INTERVAL 1 DAY
    )) AS business_date
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Derivar columnas de calendario

# COMMAND ----------

df_silver = (
    df_dates
    .withColumn("year", year(col("business_date")))
    .withColumn("quarter", quarter(col("business_date")))
    .withColumn("month", month(col("business_date")))
    .withColumn("day_of_month", dayofmonth(col("business_date")))
    .withColumn("day_of_week", dayofweek(col("business_date")))
    .withColumn("month_name", date_format(col("business_date"), "MMMM"))
    .withColumn("day_name", date_format(col("business_date"), "EEEE"))
    .withColumn("is_weekend", when(col("day_of_week").isin(1, 7), True).otherwise(False))
    .withColumn("is_festivo_col", lit(False))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Festivos Colombia (lista estática 2024-2026)

# COMMAND ----------

FESTIVOS = [
    # 2024
    "2024-01-01", "2024-01-08", "2024-03-25", "2024-03-28", "2024-03-29",
    "2024-05-01", "2024-05-13", "2024-06-03", "2024-06-19", "2024-07-01",
    "2024-07-20", "2024-08-07", "2024-08-15", "2024-10-14", "2024-11-01",
    "2024-11-11", "2024-12-08", "2024-12-25",
    # 2025
    "2025-01-01", "2025-01-13", "2025-03-24", "2025-04-17", "2025-04-18",
    "2025-05-01", "2025-06-02", "2025-06-23", "2025-06-30", "2025-07-20",
    "2025-08-07", "2025-08-18", "2025-10-13", "2025-11-03", "2025-11-17",
    "2025-12-08", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03",
    "2026-05-01", "2026-06-08", "2026-06-15", "2026-06-29", "2026-07-20",
    "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02", "2026-11-16",
    "2026-12-08", "2026-12-25",
]

df_festivos = spark.createDataFrame(
    [(d,) for d in FESTIVOS], ["festivo_date"]
).withColumn("festivo_date", col("festivo_date").cast(DateType()))

df_silver = df_silver.join(
    df_festivos,
    df_silver.business_date == df_festivos.festivo_date,
    "left"
).withColumn(
    "is_festivo_col",
    when(col("festivo_date").isNotNull(), True).otherwise(False)
).drop("festivo_date")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Validación

# COMMAND ----------

total_days = df_silver.count()
distinct_dates = df_silver.select("business_date").distinct().count()
assert total_days == distinct_dates, (
    f"❌ Duplicados en dim_tiempo: {total_days} vs {distinct_dates}"
)
print(f"✅ dim_tiempo: {total_days} fechas, todas únicas")

festivos_count = df_silver.where(col("is_festivo_col") == True).count()
print(f"   Festivos marcados: {festivos_count}")

# COMMAND ----------

# Escritura
df_silver.write.format("delta").mode("overwrite").saveAsTable(TARGET)
final_count = spark.table(TARGET).count()
print(f"✅ dim_tiempo: {final_count} filas en silver")
display(spark.table(TARGET).where(col("is_festivo_col") == True).limit(10))
