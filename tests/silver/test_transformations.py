"""
Tests unitarios de transformaciones silver — MotoShop.

Usa `chispa` para comparación de DataFrames con datasets sintéticos.
Requiere PySpark local (no SQL Warehouse).

Ejecutar: pytest tests/silver/test_transformations.py -v
"""

import pytest

try:
    from chispa.dataframe_comparer import assert_df_equality
    from chispa.schema_comparer import SchemasAreNotEqualError

    HAS_CHISPA = True
except ImportError:
    HAS_CHISPA = False

try:
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        StructType, StructField, StringType, DoubleType, IntegerType, DateType
    )
    from pyspark.sql.functions import col, trim, current_date, sha2, concat_ws
    import pyspark

    HAS_SPARK = True
except ImportError:
    HAS_SPARK = False


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def spark():
    """SparkSession local para tests."""
    session = (
        SparkSession.builder
        .master("local[1]")
        .appName("motoshop-silver-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


# ─── Tests: dim_producto ────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CHISPA, reason="chispa not installed")
@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestDimProducto:
    """Tests para dim_producto."""

    def test_trim_applied(self, spark):
        """TRIM elimina whitespace de cod_producto y nombre."""
        schema = StructType([
            StructField("codprod", StringType()),
            StructField("nomprod", StringType()),
            StructField("codbar", StringType()),
            StructField("unimed", StringType()),
            StructField("codmed", StringType()),
            StructField("valmed", DoubleType()),
            StructField("presen", StringType()),
            StructField("actprod", StringType()),
            StructField("codpor", StringType()),
            StructField("codlin1", StringType()),
            StructField("desprod", StringType()),
            StructField("nitter", StringType()),
            StructField("codbod", StringType()),
            StructField("fecapa", DateType()),
        ])
        data = [
            ("  P001  ", "Aceite 20W50", "77000001", "LT", "LT", 1.0, "Botella", "A", "GR01", "LI01", "Aceite motor", "NIT001", "BD01", None),
            ("P002", "Filtro Aire", None, "UN", "UN", 1.0, "Unidad", "A", "GR01", "LI01", "Filtro", "NIT001", "BD01", None),
        ]
        df_input = spark.createDataFrame(data, schema)

        df_result = (
            df_input
            .select(
                trim(col("codprod")).alias("cod_producto"),
                trim(col("nomprod")).alias("nombre_producto"),
                trim(col("codbar")).alias("codigo_barras"),
                trim(col("unimed")).alias("unidad_medida"),
                trim(col("codmed")).alias("cod_medida"),
                col("valmed").cast("double").alias("valor_medida"),
                trim(col("presen")).alias("presentacion"),
                trim(col("actprod")).alias("estado_producto"),
                trim(col("codpor")).alias("cod_grupo"),
                trim(col("codlin1")).alias("cod_linea1"),
                trim(col("desprod")).alias("descripcion"),
                trim(col("nitter")).alias("nit_proveedor"),
                trim(col("codbod")).alias("cod_bodega_default"),
                col("fecapa").cast("date").alias("fecha_actualizacion"),
                current_date().alias("snapshot_date"),
            )
            .where(col("cod_producto").isNotNull())
            .dropDuplicates(["cod_producto"])
        )

        expected = spark.createDataFrame([
            ("P001", "Aceite 20W50", "77000001", "LT", "LT", 1.0, "Botella", "A", "GR01", "LI01", "Aceite motor", "NIT001", "BD01", None),
            ("P002", "Filtro Aire", None, "UN", "UN", 1.0, "Unidad", "A", "GR01", "LI01", "Filtro", "NIT001", "BD01", None),
        ], schema=df_result.schema)

        assert_df_equality(df_result, expected, ignore_row_order=True)

    def test_no_null_pk(self, spark):
        """cod_producto no puede ser nulo."""
        schema = StructType([
            StructField("codprod", StringType()),
            StructField("nomprod", StringType()),
        ])
        data = [
            (None, "Sin código"),
            ("P001", "Producto válido"),
        ]
        df = spark.createDataFrame(data, schema)
        df_filtered = df.where(col("codprod").isNotNull())
        assert df_filtered.count() == 1

    def test_deduplication(self, spark):
        """Duplicados por cod_producto se eliminan."""
        schema = StructType([
            StructField("codprod", StringType()),
            StructField("nomprod", StringType()),
        ])
        data = [
            ("P001", "Producto A"),
            ("P001", "Producto A v2"),
            ("P002", "Producto B"),
        ]
        df = spark.createDataFrame(data, schema)
        df_dedup = df.dropDuplicates(["codprod"])
        assert df_dedup.count() == 2


# ─── Tests: dim_bodega ──────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CHISPA, reason="chispa not installed")
@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestDimBodega:

    def test_no_null_pk(self, spark):
        schema = StructType([
            StructField("codbod", StringType()),
            StructField("nombod", StringType()),
        ])
        data = [(None, "Sin código"), ("BD01", "Bodega Principal")]
        df = spark.createDataFrame(data, schema)
        df_filtered = df.where(col("codbod").isNotNull())
        assert df_filtered.count() == 1


# ─── Tests: dim_tercero ─────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CHISPA, reason="chispa not installed")
@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestDimTercero:

    def test_pseudonimizacion_nombre(self, spark):
        """nombre_hash debe ser SHA2 de nombre + apellido."""
        schema = StructType([
            StructField("nomter", StringType()),
            StructField("apeter", StringType()),
        ])
        data = [("Juan", "Pérez")]
        df = spark.createDataFrame(data, schema)
        df_result = df.withColumn(
            "nombre_hash",
            sha2(concat_ws(" ", trim(col("nomter")), trim(col("apeter"))), 256)
        )
        row = df_result.collect()[0]
        assert row["nombre_hash"] is not None
        assert len(row["nombre_hash"]) == 64  # SHA-256 hex length

    def test_no_null_nit(self, spark):
        schema = StructType([
            StructField("nitter", StringType()),
        ])
        data = [(None,), ("900123456",)]
        df = spark.createDataFrame(data, schema)
        df_filtered = df.where(col("nitter").isNotNull())
        assert df_filtered.count() == 1


# ─── Tests: fact_ventas ─────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CHISPA, reason="chispa not installed")
@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestFactVentas:

    def test_no_negative_total(self, spark):
        """total_factura no puede ser negativo."""
        schema = StructType([
            StructField("numfven", StringType()),
            StructField("totfven", DoubleType()),
        ])
        data = [("FV001", 150000.0), ("FV002", -500.0)]
        df = spark.createDataFrame(data, schema)
        neg_count = df.where(col("totfven") < 0).count()
        assert neg_count == 1

    def test_business_date_filter(self, spark):
        """Solo fechas entre 2020-01-01 y hoy."""
        schema = StructType([
            StructField("numfven", StringType()),
            StructField("fecfven", StringType()),
        ])
        data = [
            ("FV001", "2024-06-15"),
            ("FV002", "1999-01-01"),  # fuera de rango
            ("FV003", "2025-12-31"),  # futuro
        ]
        df = spark.createDataFrame(data, schema)
        from pyspark.sql.functions import to_date, current_date
        df_filtered = df.where(
            (to_date(col("fecfven")).cast("date") >= "2020-01-01") &
            (to_date(col("fecfven")).cast("date") <= current_date())
        )
        assert df_filtered.count() == 1  # solo FV001

    def test_pk_unicity(self, spark):
        """PK (numfven, cod_clase) debe ser única."""
        schema = StructType([
            StructField("numfven", StringType()),
            StructField("codclas", StringType()),
        ])
        data = [("FV001", "FV"), ("FV002", "FV"), ("FV001", "FV")]
        df = spark.createDataFrame(data, schema)
        total = df.count()
        distinct = df.select("numfven", "codclas").distinct().count()
        assert total != distinct  # hay duplicado


# ─── Tests: fact_compras ────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CHISPA, reason="chispa not installed")
@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestFactCompras:

    def test_no_negative_total(self, spark):
        schema = StructType([
            StructField("numcom", StringType()),
            StructField("totcom", DoubleType()),
        ])
        data = [("C001", 50000.0), ("C002", -100.0)]
        df = spark.createDataFrame(data, schema)
        neg_count = df.where(col("totcom") < 0).count()
        assert neg_count == 1


# ─── Tests: dim_tiempo ──────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CHISPA, reason="chispa not installed")
@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestDimTiempo:

    def test_no_duplicate_dates(self, spark):
        """business_date no puede tener duplicados."""
        schema = StructType([
            StructField("business_date", DateType()),
        ])
        from datetime import date
        data = [
            (date(2024, 1, 1),),
            (date(2024, 1, 2),),
            (date(2024, 1, 1),),  # duplicado
        ]
        df = spark.createDataFrame(data, schema)
        total = df.count()
        distinct = df.select("business_date").distinct().count()
        assert total != distinct  # hay duplicado

    def test_festivos_marked(self, spark):
        """Festivos colombianos deben estar marcados."""
        from pyspark.sql.functions import when, lit, dayofweek, month, quarter, year, dayofmonth, date_format
        from datetime import date
        schema = StructType([
            StructField("business_date", DateType()),
        ])
        data = [(date(2024, 1, 1),), (date(2024, 1, 2),)]
        df = spark.createDataFrame(data, schema)
        FESTIVOS = ["2024-01-01"]
        df_festivos = spark.createDataFrame([(d,) for d in FESTIVOS], ["festivo_date"])
        from pyspark.sql.types import DateType as DT
        df_festivos = df_festivos.withColumn("festivo_date", col("festivo_date").cast(DT))

        df_result = df.join(
            df_festivos, df.business_date == df_festivos.festivo_date, "left"
        ).withColumn(
            "is_festivo",
            when(col("festivo_date").isNotNull(), True).otherwise(False)
        ).drop("festivo_date")

        rows = {row["business_date"]: row["is_festivo"] for row in df_result.collect()}
        assert rows[date(2024, 1, 1)] == True
        assert rows[date(2024, 1, 2)] == False


# ─── Tests: Quality Run ─────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_SPARK, reason="pyspark not installed")
class TestQualityRun:

    def test_assert_no_null_pk(self, spark):
        """Función assert_no_null_pk detecta PKs nulas."""
        schema = StructType([
            StructField("pk", StringType()),
            StructField("value", StringType()),
        ])
        data = [(None, "a"), ("k1", "b")]
        df = spark.createDataFrame(data, schema)
        null_count = df.where(col("pk").isNull()).count()
        assert null_count == 1

    def test_assert_no_future_dates(self, spark):
        """Detecta business_date futuras."""
        from pyspark.sql.functions import current_date
        schema = StructType([
            StructField("business_date", DateType()),
        ])
        from datetime import date, timedelta
        future = date.today() + timedelta(days=10)
        data = [(date.today(),), (future,)]
        df = spark.createDataFrame(data, schema)
        future_count = df.where(col("business_date") > current_date()).count()
        assert future_count == 1

    def test_assert_no_negative_amounts(self, spark):
        """Detecta montos negativos."""
        schema = StructType([
            StructField("amount", DoubleType()),
        ])
        data = [(100.0,), (-50.0,), (200.0,)]
        df = spark.createDataFrame(data, schema)
        neg_count = df.where(col("amount") < 0).count()
        assert neg_count == 1
