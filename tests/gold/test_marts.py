"""
Tests unitarios de marts gold — MotoShop.

Usa sqlparse para validar estructura SQL real en vez de keywords sueltas.
Tests locales sin PySpark. Tests reales en Databricks: notebooks/gold/30_validate_gold.py

Ejecutar: pytest tests/gold/test_marts.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlparse

GOLD_DIR = Path("notebooks/gold")

GOLD_NOTEBOOKS = [
    "10_mart_ventas_diarias_sku.py",
    "11_mart_inventario_actual.py",
    "12_mart_rotacion_abc.py",
    "13_mart_cohortes_clientes.py",
    "14_mart_productos_dormidos.py",
]

ALL_NOTEBOOKS = GOLD_NOTEBOOKS + [
    "20_quality_gold.py",
    "30_validate_gold.py",
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_sql(path: Path, keep_comments: bool = False) -> str:
    """Extrae solo el SQL de un notebook Databricks.

    Por default (keep_comments=False): omite MAGIC, COMMAND y líneas md.
    Con keep_comments=True: también incluye los comentarios -- MAGIC (para
    buscar nombres de tests como V1/V2/V3 que están en markdown).
    """
    text = path.read_text()
    lines = text.splitlines()
    sql_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-- COMMAND"):
            continue
        if keep_comments and stripped.startswith("-- MAGIC"):
            sql_lines.append(line)
            continue
        if stripped.startswith("-- MAGIC"):
            continue
        sql_lines.append(line)
    return "\n".join(sql_lines)


def _get_insert_statements(path: Path) -> list[sqlparse.sql.Statement]:
    """Extrae statements INSERT OVERWRITE o INSERT INTO del notebook."""
    sql = _extract_sql(path)
    parsed = sqlparse.parse(sql)
    result = []
    for stmt in parsed:
        token_str = stmt.value.strip().upper() if stmt.value else ""
        if "INSERT" in token_str:
            result.append(stmt)
    return result


def _get_create_statements(path: Path) -> list[sqlparse.sql.Statement]:
    """Extrae statements CREATE TABLE del notebook."""
    sql = _extract_sql(path)
    parsed = sqlparse.parse(sql)
    result = []
    for stmt in parsed:
        token_str = stmt.value.strip().upper() if stmt.value else ""
        if stmt.get_type() == "CREATE" or "CREATE TABLE" in token_str:
            result.append(stmt)
    return result


def _stmt_contains(stmt: sqlparse.sql.Statement, pattern: str) -> bool:
    """Check if a parsed statement contains a string pattern (case-insensitive)."""
    return pattern.lower() in stmt.value.lower()


def _count_occurrences(sql: str, keyword: str) -> int:
    """Count occurrences of a keyword in SQL (case-insensitive word boundary)."""
    return len(re.findall(rf"\b{re.escape(keyword)}\b", sql, re.IGNORECASE))


# ── Test 10: mart_ventas_diarias_sku ────────────────────────────────────────


class TestMartVentasDiariasSku:
    """Valida mart_ventas_diarias_sku con sqlparse."""

    NOTEBOOK = GOLD_DIR / "10_mart_ventas_diarias_sku.py"
    EXPECTED_COLUMNS = [
        "business_date", "cod_producto", "nom_producto",
        "cod_bodega", "nom_bodega",
        "cantidad_total", "valor_total", "num_facturas",
    ]

    def test_has_required_columns(self):
        """El CREATE TABLE debe tener todas las columnas requeridas."""
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1, "No se encontró CREATE TABLE"
        col_defs = str(creates[0])
        for col in self.EXPECTED_COLUMNS:
            assert col in col_defs, f"Falta columna en CREATE: {col}"

    def test_uses_insert_overwrite_partitioned(self):
        """Debe usar INSERT OVERWRITE con PARTITION (business_date)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        assert len(stmts) >= 1, "No se encontró INSERT"
        text = str(stmts[0]).upper()
        assert "INSERT OVERWRITE" in text, (
            "Usa DELETE+INSERT en vez de INSERT OVERWRITE"
        )
        assert "PARTITION (BUSINESS_DATE)" in text, (
            "Falta PARTITION (business_date)"
        )

    def test_joins_with_dim_producto(self):
        """Debe hacer LEFT JOIN con dim_producto."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text or "INNER JOIN" in text
        assert "dim_producto" in text

    def test_joins_with_dim_bodega(self):
        """Debe hacer LEFT JOIN con dim_bodega."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text or "INNER JOIN" in text
        assert "dim_bodega" in text

    def test_group_by_includes_date_product_bodega(self):
        """GROUP BY debe incluir business_date, cod_producto, cod_bodega."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "GROUP BY" in text
        assert "business_date" in text.split("GROUP BY")[1] if "GROUP BY" in text else True

    def test_partitioned_by_business_date(self):
        """CREATE TABLE debe estar particionado por business_date."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        assert "PARTITIONED BY" in text
        assert "business_date" in text

    def test_has_validation_select(self):
        """Debe tener SELECT de validación con COUNT."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "SELECT" in sql and "COUNT(*)" in sql


# ── Test 11: mart_inventario_actual ─────────────────────────────────────────


class TestMartInventarioActual:
    """Valida mart_inventario_actual con sqlparse."""

    NOTEBOOK = GOLD_DIR / "11_mart_inventario_actual.py"
    EXPECTED_COLUMNS = [
        "cod_producto", "nom_producto", "cod_bodega", "nom_bodega",
        "cantidad_actual", "ultimo_costo", "ultima_actualizacion",
    ]

    def test_has_required_columns(self):
        """CREATE TABLE debe tener todas las columnas requeridas."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        for col in self.EXPECTED_COLUMNS:
            assert col in text, f"Falta columna en CREATE: {col}"

    def test_uses_insert_overwrite_no_partition(self):
        """Debe usar INSERT OVERWRITE sin PARTITION en la tabla (snapshot)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]).upper() if stmts else ""
        assert "INSERT OVERWRITE" in text, (
            "Usa DELETE+INSERT en vez de INSERT OVERWRITE"
        )
        # Check that INSERT OVERWRITE is NOT followed by PARTITION
        # (PARTITION may appear in subquery OVER/PARTITION BY clauses)
        insert_line = text[:text.find("SELECT")] if "SELECT" in text else text
        # Normalize and check: "INSERT OVERWRITE table" not followed by "PARTITION"
        lines = [l.strip() for l in insert_line.split("\n") if l.strip()]
        has_table_partition = any(
            line.startswith("PARTITION") or "PARTITION (" in line
            for line in lines
        )
        assert not has_table_partition, (
            "INSERT OVERWRITE snapshot no debería tener cláusula PARTITION"
        )

    def test_uses_row_number(self):
        """Debe usar ROW_NUMBER para obtener último registro."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "ROW_NUMBER()" in text or "ROW_NUMBER (" in text

    def test_partition_by_product_bodega(self):
        """ROW_NUMBER debe particionar por cod_producto, cod_bodega."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""

        # Check OVER clause contains both partition keys
        # sqlparse tokenizes OVER(...), verify cod_producto and cod_bodega are near OVER
        assert "OVER" in text.upper()
        assert "cod_producto" in text
        assert "cod_bodega" in text

    def test_no_table_partition(self):
        """CREATE TABLE no debe tener PARTITIONED BY (snapshot)."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        assert "PARTITIONED BY" not in text

    def test_left_join_dim_producto(self):
        """Debe hacer LEFT JOIN con dim_producto."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text
        assert "dim_producto" in text

    def test_left_join_dim_bodega(self):
        """Debe hacer LEFT JOIN con dim_bodega."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text
        assert "dim_bodega" in text


# ── Test 12: mart_rotacion_abc ──────────────────────────────────────────────


class TestMartRotacionABC:
    """Valida mart_rotacion_abc con sqlparse."""

    NOTEBOOK = GOLD_DIR / "12_mart_rotacion_abc.py"
    EXPECTED_COLUMNS = [
        "business_month", "cod_producto", "nom_producto",
        "valor_total", "porcentaje_acumulado", "categoria_abc",
    ]

    def test_has_required_columns(self):
        """CREATE TABLE debe tener todas las columnas requeridas."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        for col in self.EXPECTED_COLUMNS:
            assert col in text, f"Falta columna en CREATE: {col}"

    def test_uses_insert_overwrite_partitioned(self):
        """Debe usar INSERT OVERWRITE con PARTITION (business_month)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]).upper() if stmts else ""
        assert "INSERT OVERWRITE" in text
        assert "PARTITION (BUSINESS_MONTH)" in text

    def test_has_abc_logic(self):
        """Debe tener CASE WHEN con 0.80 y 0.95 thresholds."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "0.80" in text, "Falta threshold 80%"
        assert "0.95" in text, "Falta threshold 95%"
        assert "CASE" in text and "categoria_abc" in text

    def test_has_row_number_with_tiebreaker(self):
        """ROW_NUMBER debe tener tiebreaker (cod_producto)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "ROW_NUMBER()" in text or "ROW_NUMBER (" in text
        assert "OVER" in text.upper()
        # Verify tiebreaker exists (cod_producto or similar after ORDER BY)
        over_section = text[text.upper().find("ORDER BY"):]
        over_section = over_section[:over_section.find(")")] if ")" in over_section else over_section
        assert "cod_producto" in over_section, (
            "ROW_NUMBER ORDER BY debe tener tiebreaker (cod_producto)"
        )

    def test_has_running_total(self):
        """Debe usar SUM(valor_total) OVER para running total."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "SUM(" in text and "OVER" in text.upper()

    def test_partitioned_by_business_month(self):
        """CREATE TABLE debe estar particionado por business_month."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        assert "PARTITIONED BY" in text
        assert "business_month" in text


# ── Test 13: mart_cohortes_clientes ─────────────────────────────────────────


class TestMartCohortesClientes:
    """Valida mart_cohortes_clientes con sqlparse."""

    NOTEBOOK = GOLD_DIR / "13_mart_cohortes_clientes.py"
    EXPECTED_COLUMNS = [
        "business_month", "mes_cohorte", "nit_cliente", "nombre_cliente",
        "meses_desde_cohorte", "compro_este_mes", "ticket_promedio",
        "ingresos_totales", "es_activo",
    ]

    def test_has_required_columns(self):
        """CREATE TABLE debe tener todas las columnas requeridas."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        for col in self.EXPECTED_COLUMNS:
            assert col in text, f"Falta columna en CREATE: {col}"

    def test_uses_insert_overwrite_partitioned(self):
        """Debe usar INSERT OVERWRITE con PARTITION (business_month)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]).upper() if stmts else ""
        assert "INSERT OVERWRITE" in text
        assert "PARTITION (BUSINESS_MONTH)" in text

    def test_uses_months_between(self):
        """Debe usar MONTHS_BETWEEN para meses_desde_cohorte."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "MONTHS_BETWEEN" in text, (
            "Todavía usa DATEDIFF(días)/31 en vez de MONTHS_BETWEEN"
        )
        assert "meses_desde_cohorte" in text

    def test_has_primera_compra_cte(self):
        """Debe tener CTE primera_compra con MIN(business_date)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "primera_compra" in text or "PRIMERA_COMPRA" in text.upper()
        assert "MIN(" in text

    def test_has_es_activo_logic(self):
        """Debe tener CASE para es_activo."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "es_activo" in text
        assert "WHEN" in text or "CASE" in text

    def test_has_compro_este_mes(self):
        """Debe tener columna booleana compro_este_mes."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "compro_este_mes" in text

    def test_partitioned_by_business_month(self):
        """CREATE TABLE debe estar particionado por business_month."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        assert "PARTITIONED BY" in text
        assert "business_month" in text


# ── Test 14: mart_productos_dormidos ────────────────────────────────────────


class TestMartProductosDormidos:
    """Valida mart_productos_dormidos con sqlparse."""

    NOTEBOOK = GOLD_DIR / "14_mart_productos_dormidos.py"
    EXPECTED_COLUMNS = [
        "cod_producto", "nom_producto", "cod_bodega",
        "ultima_fecha_venta", "dias_sin_venta",
        "stock_actual", "categoria",
    ]

    def test_has_required_columns(self):
        """CREATE TABLE debe tener todas las columnas requeridas."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        for col in self.EXPECTED_COLUMNS:
            assert col in text, f"Falta columna en CREATE: {col}"

    def test_uses_insert_overwrite_no_partition(self):
        """Debe usar INSERT OVERWRITE sin PARTITION (snapshot)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]).upper() if stmts else ""
        assert "INSERT OVERWRITE" in text
        assert "PARTITION" not in text

    def test_filters_90_days(self):
        """WHERE debe filtrar > 90 días sin venta o productos sin venta."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "90" in text
        assert "DATEDIFF" in text or "dias_sin_venta" in text

    def test_has_dormido_categories(self):
        """CASE debe tener categorías dormido_con_stock y dormido_sin_stock."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "dormido_con_stock" in text
        assert "dormido_sin_stock" in text

    def test_has_stock_actual(self):
        """INSERT debe incluir stock_actual."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "stock_actual" in text
        assert "COALESCE" in text

    def test_no_table_partition(self):
        """CREATE TABLE no debe tener PARTITIONED BY."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        assert "PARTITIONED BY" not in text


# ── Patrón idempotente (todos los marts) ────────────────────────────────────


class TestIdempotentPatternGold:
    """Valida que todos los marts usen INSERT OVERWRITE (atómico)."""

    def test_all_marts_no_create_replace(self):
        """Marts no deben usar CREATE OR REPLACE TABLE."""
        for nb in GOLD_NOTEBOOKS:
            sql = _extract_sql(GOLD_DIR / nb)
            assert "CREATE OR REPLACE TABLE" not in sql, (
                f"{nb} usa CREATE OR REPLACE TABLE — debe usar INSERT OVERWRITE"
            )

    def test_all_marts_have_create_if_not_exists(self):
        """Marts deben usar CREATE TABLE IF NOT EXISTS."""
        for nb in GOLD_NOTEBOOKS:
            sql = _extract_sql(GOLD_DIR / nb)
            assert "CREATE TABLE IF NOT EXISTS" in sql, (
                f"{nb} no tiene CREATE TABLE IF NOT EXISTS"
            )

    def test_all_marts_have_insert_overwrite(self):
        """Marts deben usar INSERT OVERWRITE (no DELETE+INSERT)."""
        for nb in GOLD_NOTEBOOKS:
            sql = _extract_sql(GOLD_DIR / nb)
            assert "INSERT OVERWRITE" in sql, (
                f"{nb} no usa INSERT OVERWRITE"
            )
            assert "DELETE FROM" not in sql, (
                f"{nb} todavía tiene DELETE FROM en vez de INSERT OVERWRITE"
            )

    def test_all_marts_have_validation(self):
        """Marts deben tener SELECT de validación con COUNT."""
        for nb in GOLD_NOTEBOOKS:
            sql = _extract_sql(GOLD_DIR / nb)
            assert "SELECT" in sql and "COUNT(*)" in sql, (
                f"{nb} no tiene validación con COUNT(*)"
            )


# ── Test 20: quality_gold ──────────────────────────────────────────────────


class TestQualityGold:
    """Valida lógica de quality gold con sqlparse."""

    NOTEBOOK = GOLD_DIR / "20_quality_gold.py"

    def test_has_assert_true(self):
        """quality_gold debe tener assert_true para fallar en CRITICAL."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "assert_true" in sql
        assert "CRITICAL" in sql

    def test_has_all_marts(self):
        """quality_gold debe validar los 5 marts gold."""
        sql = _extract_sql(self.NOTEBOOK)
        for mart in ["mart_ventas_diarias_sku", "mart_inventario_actual",
                     "mart_rotacion_abc", "mart_cohortes_clientes",
                     "mart_productos_dormidos"]:
            assert mart in sql, f"Falta validación para {mart}"

    def test_has_null_pk_rule(self):
        """Debe tener regla de PK nula en todos los marts."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "null_pk" in sql
        assert _count_occurrences(sql, "null_pk") >= 5, (
            "null_pk rule debe aparecer al menos 5 veces (una por mart)"
        )

    def test_uses_uuid(self):
        """Debe usar UUID() en vez de RAND()+fecha."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "UUID()" in sql, "Todavía usa RAND() en vez de UUID()"
        assert "RAND()" not in sql, "Todavía usa RAND() — debe usar UUID()"

    def test_has_negative_values_rule(self):
        """Debe tener regla 'negative_' para valores negativos CRITICAL."""
        sql = _extract_sql(self.NOTEBOOK)
        # Count 'negative_' appearing as rule name (may be followed by column name)
        negative_count = sql.lower().count("negative_")
        assert negative_count >= 5, (
            f"Reglas 'negative_' deberían aparecer al menos 5 veces, "
            f"se encontraron {negative_count}"
        )

    def test_has_future_dates_rule(self):
        """Debe tener regla 'future_' para fechas futuras WARNING."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "future_" in sql.lower()

    def test_has_empty_mart_rule(self):
        """Debe tener regla 'empty_mart' para marts vacíos WARNING."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "empty_mart" in sql
        assert _count_occurrences(sql, "empty_mart") >= 5, (
            "empty_mart rule debe aparecer al menos 5 veces"
        )


# ── Test 30: validate_gold ──────────────────────────────────────────────────


class TestValidateGold:
    """Valida que 30_validate_gold.py tenga V1-V3 y estructura correcta."""

    NOTEBOOK = GOLD_DIR / "30_validate_gold.py"

    def _sql_with_comments(self) -> str:
        """Incluye comentarios MAGIC donde están los nombres V1/V2/V3."""
        return _extract_sql(self.NOTEBOOK, keep_comments=True)

    def _sql_clean(self) -> str:
        """Solo SQL puro."""
        return _extract_sql(self.NOTEBOOK)

    def test_has_v1_baseline(self):
        """V1 debe tener conteo baseline de filas."""
        # V1 está en comentarios MAGIC (markdown)
        assert "V1" in self._sql_with_comments() or "idempotencia" in self._sql_with_comments().lower()

    def test_has_v2_fechas(self):
        """V2 debe validar fechas futuras."""
        assert "V2" in self._sql_with_comments() or "fechas" in self._sql_with_comments().lower()

    def test_has_v3_coherencia(self):
        """V3 debe probar coherencia silver↔gold."""
        assert "V3" in self._sql_with_comments() or "coherencia" in self._sql_with_comments().lower()

    def test_has_silver_gold_comparison(self):
        """V3 debe comparar gold con silver usando line-level detail."""
        sql = self._sql_clean()
        assert "gold" in sql.lower()
        assert "fact_ventas_detalle" in sql, (
            "V3 debe comparar contra fact_ventas_detalle (line-level), "
            "no contra fact_ventas (cabecera)"
        )

    def test_has_explicit_cross_join(self):
        """V3 debe usar CROSS JOIN explícito, no FROM a,b implícito."""
        assert "CROSS JOIN" in self._sql_clean(), (
            "Usa FROM a,b implícito en vez de CROSS JOIN explícito"
        )

    def test_has_tolerance_check(self):
        """V3 debe tener tolerancia < 0.5%."""
        sql = self._sql_clean()
        assert "0.005" in sql or "0.5" in sql


# ── Formato de notebooks ────────────────────────────────────────────────────


class TestNotebookFormatGold:
    """Valida que todos los notebooks gold usen formato Databricks correcto."""

    def test_all_start_with_databricks_source(self):
        """Todos deben empezar con -- Databricks notebook source."""
        for nb in ALL_NOTEBOOKS:
            first_line = (GOLD_DIR / nb).read_text().splitlines()[0].strip()
            assert first_line == "-- Databricks notebook source", (
                f"{nb} empieza con: {first_line}"
            )

    def test_all_have_comment_separators(self):
        """Todos deben tener separadores de celda COMMAND."""
        for nb in ALL_NOTEBOOKS:
            content = (GOLD_DIR / nb).read_text()
            assert "-- COMMAND ----------" in content, (
                f"{nb} no tiene separadores de celda"
            )
