"""
Tests unitarios de marts gold — MotoShop.

Tests locales sin PySpark (validación de lógica y patrones similar a silver).
Tests reales en Databricks: notebooks/gold/30_validate_gold.py

Para lógica real (ABC, dormidos, cohortes) los tests verifican:
- Notebooks usan patrón correcto
- SQL queries contienen las transformaciones esperadas

Ejecutar: pytest tests/gold/test_marts.py -v
"""

import pytest


GOLD_NOTEBOOKS = [
    "10_mart_ventas_diarias_sku.py",
    "11_mart_inventario_actual.py",
    "12_mart_rotacion_abc.py",
    "13_mart_cohortes_clientes.py",
    "14_mart_productos_dormidos.py",
]

GOLD_DIR = "notebooks/gold"


class TestMartVentasDiariasSku:
    """Valida mart_ventas_diarias_sku."""

    EXPECTED_COLUMNS = [
        "business_date", "cod_producto", "nom_producto",
        "cod_bodega", "nom_bodega",
        "cantidad_total", "valor_total", "num_facturas",
    ]

    def test_has_required_columns(self):
        """El mart debe tener todas las columnas requeridas."""
        with open(f"{GOLD_DIR}/10_mart_ventas_diarias_sku.py") as f:
            content = f.read()
        for col in self.EXPECTED_COLUMNS:
            assert col in content, f"Falta columna: {col}"

    def test_has_delete_by_date(self):
        """Debe tener DELETE por rango de business_date."""
        with open(f"{GOLD_DIR}/10_mart_ventas_diarias_sku.py") as f:
            content = f.read()
        assert "DELETE FROM" in content
        assert "business_date" in content
        assert "2020-01-01" in content

    def test_joins_with_dim_producto(self):
        """Debe hacer JOIN con dim_producto para nombres."""
        with open(f"{GOLD_DIR}/10_mart_ventas_diarias_sku.py") as f:
            content = f.read()
        assert "dim_producto" in content

    def test_joins_with_dim_bodega(self):
        """Debe hacer JOIN con dim_bodega para nombres."""
        with open(f"{GOLD_DIR}/10_mart_ventas_diarias_sku.py") as f:
            content = f.read()
        assert "dim_bodega" in content

    def test_group_by_business_date(self):
        """Debe agrupar por business_date."""
        with open(f"{GOLD_DIR}/10_mart_ventas_diarias_sku.py") as f:
            content = f.read()
        assert "GROUP BY" in content

    def test_partitioned_by_business_date(self):
        """Debe estar particionado por business_date."""
        with open(f"{GOLD_DIR}/10_mart_ventas_diarias_sku.py") as f:
            content = f.read()
        assert "PARTITIONED BY (business_date)" in content


class TestMartInventarioActual:
    """Valida mart_inventario_actual."""

    EXPECTED_COLUMNS = [
        "cod_producto", "nom_producto", "cod_bodega", "nom_bodega",
        "cantidad_actual", "costo_promedio", "ultima_actualizacion",
    ]

    def test_has_required_columns(self):
        """El mart debe tener todas las columnas requeridas."""
        with open(f"{GOLD_DIR}/11_mart_inventario_actual.py") as f:
            content = f.read()
        for col in self.EXPECTED_COLUMNS:
            assert col in content, f"Falta columna: {col}"

    def test_uses_row_number(self):
        """Debe usar ROW_NUMBER para obtener último registro."""
        with open(f"{GOLD_DIR}/11_mart_inventario_actual.py") as f:
            content = f.read()
        assert "ROW_NUMBER()" in content

    def test_partition_by_product_bodega(self):
        """ROW_NUMBER debe particionar por cod_producto, cod_bodega."""
        with open(f"{GOLD_DIR}/11_mart_inventario_actual.py") as f:
            content = f.read()
        assert "PARTITION BY cod_producto, cod_bodega" in content or \
               "PARTITION BY cod_producto, cod_bodega" in content.replace("'", "")

    def test_no_partition(self):
        """No debe tener partición (snapshot)."""
        with open(f"{GOLD_DIR}/11_mart_inventario_actual.py") as f:
            content = f.read()
        assert "PARTITIONED BY" not in content


class TestMartRotacionABC:
    """Valida mart_rotacion_abc — la lógica más compleja."""

    EXPECTED_COLUMNS = [
        "business_month", "cod_producto", "nom_producto",
        "valor_total", "porcentaje_acumulado", "categoria_abc",
    ]

    def test_has_required_columns(self):
        """El mart debe tener todas las columnas requeridas."""
        with open(f"{GOLD_DIR}/12_mart_rotacion_abc.py") as f:
            content = f.read()
        for col in self.EXPECTED_COLUMNS:
            assert col in content, f"Falta columna: {col}"

    def test_has_abc_threshold_80(self):
        """Debe tener el threshold 80% para categoría A."""
        with open(f"{GOLD_DIR}/12_mart_rotacion_abc.py") as f:
            content = f.read()
        assert "0.80" in content or "80" in content

    def test_has_abc_threshold_95(self):
        """Debe tener el threshold 95% para categoría B."""
        with open(f"{GOLD_DIR}/12_mart_rotacion_abc.py") as f:
            content = f.read()
        assert "0.95" in content or "95" in content

    def test_has_categoria_abc_logic(self):
        """Debe tener CASE para asignar A/B/C."""
        with open(f"{GOLD_DIR}/12_mart_rotacion_abc.py") as f:
            content = f.read()
        assert "CASE" in content and "categoria_abc" in content

    def test_uses_running_total(self):
        """Debe usar SUM() OVER para running total acumulado."""
        with open(f"{GOLD_DIR}/12_mart_rotacion_abc.py") as f:
            content = f.read()
        assert "SUM(" in content and "OVER" in content

    def test_partitioned_by_business_month(self):
        """Debe estar particionado por business_month."""
        with open(f"{GOLD_DIR}/12_mart_rotacion_abc.py") as f:
            content = f.read()
        assert "PARTITIONED BY (business_month)" in content


class TestMartCohortesClientes:
    """Valida mart_cohortes_clientes."""

    EXPECTED_COLUMNS = [
        "business_month", "mes_cohorte", "nit_cliente", "nombre_cliente",
        "meses_desde_cohorte", "compro_este_mes", "ticket_promedio",
        "ingresos_totales", "es_activo",
    ]

    def test_has_required_columns(self):
        """El mart debe tener todas las columnas requeridas."""
        with open(f"{GOLD_DIR}/13_mart_cohortes_clientes.py") as f:
            content = f.read()
        for col in self.EXPECTED_COLUMNS:
            assert col in content, f"Falta columna: {col}"

    def test_has_mes_cohorte_calculation(self):
        """Debe calcular mes_cohorte como MIN de business_date por cliente."""
        with open(f"{GOLD_DIR}/13_mart_cohortes_clientes.py") as f:
            content = f.read()
        assert "MIN(" in content and "mes_cohorte" in content

    def test_has_meses_desde_cohorte(self):
        """Debe calcular meses desde cohorte."""
        with open(f"{GOLD_DIR}/13_mart_cohortes_clientes.py") as f:
            content = f.read()
        assert "meses_desde_cohorte" in content

    def test_has_compro_este_mes_bool(self):
        """Debe tener columna booleana compro_este_mes."""
        with open(f"{GOLD_DIR}/13_mart_cohortes_clientes.py") as f:
            content = f.read()
        assert "compro_este_mes" in content

    def test_partitioned_by_business_month(self):
        """Debe estar particionado por business_month."""
        with open(f"{GOLD_DIR}/13_mart_cohortes_clientes.py") as f:
            content = f.read()
        assert "PARTITIONED BY (business_month)" in content


class TestMartProductosDormidos:
    """Valida mart_productos_dormidos."""

    EXPECTED_COLUMNS = [
        "cod_producto", "nom_producto", "cod_bodega",
        "ultima_fecha_venta", "dias_sin_venta",
        "stock_actual", "categoria",
    ]

    def test_has_required_columns(self):
        """El mart debe tener todas las columnas requeridas."""
        with open(f"{GOLD_DIR}/14_mart_productos_dormidos.py") as f:
            content = f.read()
        for col in self.EXPECTED_COLUMNS:
            assert col in content, f"Falta columna: {col}"

    def test_filters_90_days(self):
        """Debe filtrar productos con > 90 días sin venta."""
        with open(f"{GOLD_DIR}/14_mart_productos_dormidos.py") as f:
            content = f.read()
        assert "90" in content

    def test_has_dormido_categories(self):
        """Debe tener categorías dormido_con_stock y dormido_sin_stock."""
        with open(f"{GOLD_DIR}/14_mart_productos_dormidos.py") as f:
            content = f.read()
        assert "dormido_con_stock" in content
        assert "dormido_sin_stock" in content

    def test_has_stock_actual(self):
        """Debe tener columna stock_actual."""
        with open(f"{GOLD_DIR}/14_mart_productos_dormidos.py") as f:
            content = f.read()
        assert "stock_actual" in content

    def test_no_partition(self):
        """No debe tener partición (snapshot)."""
        with open(f"{GOLD_DIR}/14_mart_productos_dormidos.py") as f:
            content = f.read()
        assert "PARTITIONED BY" not in content


class TestIdempotentPatternGold:
    """Valida que todos los marts usen patrón idempotente DELETE+INSERT."""

    def test_all_marts_no_create_replace(self):
        """Marts no deben usar CREATE OR REPLACE TABLE."""
        for nb in GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "CREATE OR REPLACE TABLE" not in content, (
                f"{nb} usa CREATE OR REPLACE TABLE — debe usar DELETE+INSERT"
            )

    def test_all_marts_have_create_if_not_exists(self):
        """Marts deben usar CREATE TABLE IF NOT EXISTS."""
        for nb in GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "CREATE TABLE IF NOT EXISTS" in content, (
                f"{nb} no tiene CREATE TABLE IF NOT EXISTS"
            )

    def test_all_marts_have_delete(self):
        """Marts deben tener DELETE para idempotencia."""
        for nb in GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "DELETE FROM" in content, (
                f"{nb} no tiene DELETE FROM"
            )

    def test_all_marts_have_insert_into(self):
        """Marts deben tener INSERT INTO."""
        for nb in GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "INSERT INTO" in content, (
                f"{nb} no tiene INSERT INTO"
            )

    def test_all_marts_have_validation(self):
        """Marts deben tener SELECT de validación."""
        for nb in GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "SELECT" in content and "COUNT" in content, (
                f"{nb} no tiene validación con COUNT"
            )


class TestQualityGold:
    """Valida lógica de quality gold."""

    def test_has_assert_true(self):
        """quality_gold debe tener assert_true para fallar en CRITICAL."""
        with open(f"{GOLD_DIR}/20_quality_gold.py") as f:
            content = f.read()
        assert "assert_true" in content
        assert "CRITICAL" in content

    def test_has_all_marts(self):
        """quality_gold debe validar los 5 marts."""
        with open(f"{GOLD_DIR}/20_quality_gold.py") as f:
            content = f.read()
        assert "mart_ventas_diarias_sku" in content
        assert "mart_inventario_actual" in content
        assert "mart_rotacion_abc" in content
        assert "mart_cohortes_clientes" in content
        assert "mart_productos_dormidos" in content

    def test_has_null_pk_rule(self):
        """Debe tener regla de PK nula CRITICAL."""
        with open(f"{GOLD_DIR}/20_quality_gold.py") as f:
            content = f.read()
        assert "null_pk" in content and "CRITICAL" in content

    def test_has_negative_values_rule(self):
        """Debe tener regla de valores negativos CRITICAL."""
        with open(f"{GOLD_DIR}/20_quality_gold.py") as f:
            content = f.read()
        assert "negative" in content.lower()

    def test_has_future_dates_rule(self):
        """Debe tener regla de fechas futuras WARNING."""
        with open(f"{GOLD_DIR}/20_quality_gold.py") as f:
            content = f.read()
        assert "future" in content.lower()

    def test_has_empty_mart_rule(self):
        """Debe tener regla de mart vacío WARNING."""
        with open(f"{GOLD_DIR}/20_quality_gold.py") as f:
            content = f.read()
        assert "empty_mart" in content


class TestValidateGold:
    """Valida que 30_validate_gold.py tenga los 3 tests."""

    def test_has_v1_idempotencia(self):
        """V1 debe probar idempotencia."""
        with open(f"{GOLD_DIR}/30_validate_gold.py") as f:
            content = f.read()
        assert "V1" in content or "idempotencia" in content.lower()

    def test_has_v2_fechas(self):
        """V2 debe validar fechas."""
        with open(f"{GOLD_DIR}/30_validate_gold.py") as f:
            content = f.read()
        assert "V2" in content or "fechas" in content.lower()

    def test_has_v3_coherencia(self):
        """V3 debe probar coherencia silver↔gold."""
        with open(f"{GOLD_DIR}/30_validate_gold.py") as f:
            content = f.read()
        assert "V3" in content or "coherencia" in content.lower()

    def test_has_silver_gold_comparison(self):
        """V3 debe comparar SUM(valor_total) con silver.fact_ventas."""
        with open(f"{GOLD_DIR}/30_validate_gold.py") as f:
            content = f.read()
        assert "silver" in content.lower() and "gold" in content.lower()

    def test_has_tolerance_check(self):
        """V3 debe tener tolerancia < 0.5%."""
        with open(f"{GOLD_DIR}/30_validate_gold.py") as f:
            content = f.read()
        assert "0.005" in content or "0.5" in content


class TestNotebookFormatGold:
    """Valida que todos los notebooks gold usen formato SQL correcto."""

    ALL_GOLD_NOTEBOOKS = GOLD_NOTEBOOKS + [
        "20_quality_gold.py",
        "30_validate_gold.py",
    ]

    def test_all_start_with_databricks_source(self):
        """Todos deben empezar con -- Databricks notebook source."""
        for nb in self.ALL_GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                first_line = f.readline().strip()
            assert first_line == "-- Databricks notebook source", (
                f"{nb} empieza con: {first_line}"
            )

    def test_all_have_magic_md(self):
        """Todos deben tener al menos un markdown."""
        for nb in self.ALL_GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "-- MAGIC %md" in content, (
                f"{nb} no tiene celdas markdown"
            )

    def test_all_have_comment_separators(self):
        """Todos deben tener separadores de celda."""
        for nb in self.ALL_GOLD_NOTEBOOKS:
            with open(f"{GOLD_DIR}/{nb}") as f:
                content = f.read()
            assert "-- COMMAND ----------" in content, (
                f"{nb} no tiene separadores de celda"
            )
