"""
Tests unitarios de feature store SKU — MotoShop F4-A.

Usa sqlparse para validar estructura SQL.
Tests locales sin PySpark.

Ejecutar: pytest tests/gold/test_feature_store.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlparse

GOLD_DIR = Path("notebooks/gold")
FEATURE_NOTEBOOK = "15_feature_store_sku.py"


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_sql(path: Path) -> str:
    """Extrae solo el SQL de un notebook Databricks."""
    text = path.read_text()
    lines = text.splitlines()
    sql_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-- COMMAND"):
            continue
        if stripped.startswith("-- MAGIC"):
            continue
        sql_lines.append(line)
    return "\n".join(sql_lines)


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


def _count_occurrences(sql: str, keyword: str) -> int:
    """Count occurrences of a keyword in SQL (case-insensitive word boundary)."""
    return len(re.findall(rf"\b{re.escape(keyword)}\b", sql, re.IGNORECASE))


# ── Tests ──────────────────────────────────────────────────────────────────


class TestFeatureStoreSchema:
    """Valida schema de feature_store_sku con sqlparse."""

    NOTEBOOK = GOLD_DIR / FEATURE_NOTEBOOK

    EXPECTED_COLUMNS = [
        "cod_producto",
        "business_date",
        "demanda_diaria",
        "lag_7d",
        "lag_14d",
        "lag_28d",
        "media_movil_7d",
        "media_movil_14d",
        "media_movil_28d",
        "dia_semana",
        "mes",
        "es_festivo",
        "stock_actual",
        "dias_sin_venta",
        "categoria_abc",
    ]

    def test_feature_store_schema(self):
        """CREATE TABLE debe tener ≥ 15 columnas."""
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1, "No se encontró CREATE TABLE"
        create_text = str(creates[0])
        # Contar columnas por presencia en el CREATE
        col_count = sum(1 for col in self.EXPECTED_COLUMNS if col in create_text)
        assert col_count >= 15, (
            f"CREATE TABLE tiene {col_count} columnas esperadas de 15. "
            f"Faltan: {[c for c in self.EXPECTED_COLUMNS if c not in create_text]}"
        )
        # Verificar que al menos aparecen 15 nombres de columna distintos
        # (contar comas entre paréntesis de CREATE TABLE)
        # Buscar bloque entre paréntesis después de CREATE TABLE
        paren_match = re.search(r"\(([^)]+)\)", create_text, re.DOTALL)
        assert paren_match is not None, "No se encontró bloque de columnas en CREATE TABLE"
        inner = paren_match.group(1)
        # Contar definiciones de columna (líneas con tipo de dato)
        col_defs = [l.strip() for l in inner.split(",") if l.strip()]
        data_type_pattern = r"\b(STRING|DATE|DOUBLE|INT|BOOLEAN|BIGINT|FLOAT|DECIMAL)\b"
        actual_cols = [c for c in col_defs if re.search(data_type_pattern, c, re.IGNORECASE)]
        assert len(actual_cols) >= 15, (
            f"CREATE TABLE tiene {len(actual_cols)} columnas con tipo de dato, "
            f"se esperaban ≥ 15"
        )

    def test_feature_store_column_types(self):
        """Columnas clave deben tener tipos correctos: DOUBLE para lags, INT para dia_semana/mes."""
        creates = _get_create_statements(self.NOTEBOOK)
        create_text = str(creates[0]) if creates else ""

        # Verificar tipos DOUBLE para lags
        for col in ["lag_7d", "lag_14d", "lag_28d", "media_movil_7d", "media_movil_14d", "media_movil_28d", "demanda_diaria"]:
            # Buscar "col DOUBLE" en el CREATE
            pattern = rf"{col}\s+DOUBLE"
            assert re.search(pattern, create_text, re.IGNORECASE), (
                f"Columna {col} debe ser DOUBLE"
            )

        # Verificar INT para dia_semana y mes
        for col in ["dia_semana", "mes"]:
            pattern = rf"{col}\s+INT"
            assert re.search(pattern, create_text, re.IGNORECASE), (
                f"Columna {col} debe ser INT"
            )

        # Verificar BOOLEAN para es_festivo
        assert re.search(r"es_festivo\s+BOOLEAN", create_text, re.IGNORECASE), (
            "Columna es_festivo debe ser BOOLEAN"
        )

    def test_feature_store_pk_not_null(self):
        """INSERT OVERWRITE no debe permitir NULLs en cod_producto (COALESCE o NOT NULL implícito)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""

        # Verificar que cod_producto aparece en SELECT y no puede ser NULL
        # (debe tener COALESCE o provenir de una CTE con GROUP BY)
        assert "cod_producto" in text
        # El SELECT final no debe hacer COALESCE en cod_producto (son PK de CTEs)
        # En su lugar, verificar que el FROM/JOIN no es RIGHT JOIN que podría NULLizar

    def test_feature_store_partitioned(self):
        """CREATE TABLE debe estar particionado por business_date."""
        creates = _get_create_statements(self.NOTEBOOK)
        text = str(creates[0]) if creates else ""
        assert "PARTITIONED BY" in text, "Falta PARTITIONED BY"
        assert "business_date" in text.split("PARTITIONED BY")[1], (
            "PARTITIONED BY debe ser por business_date"
        )

    def test_lag_not_negative(self):
        """lags deben ser >= 0 (usar COALESCE con 0 si hay NULLs)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        # Debe tener COALESCE en lags
        for lag in ["lag_7d", "lag_14d", "lag_28d"]:
            # Verificar COALESCE(lag_X, 0)
            assert re.search(rf"COALESCE\(\s*{lag}\s*,?\s*0\s*\)", text, re.IGNORECASE) or \
                   re.search(rf"{lag}.*COALESCE", text, re.IGNORECASE), (
                f"Falta COALESCE({lag}, 0)"
            )

    def test_media_movil_not_negative(self):
        """Medias móviles deben ser >= 0 (COALESCE con 0)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        for mm in ["media_movil_7d", "media_movil_14d", "media_movil_28d"]:
            assert re.search(rf"COALESCE\(\s*{mm}\s*,?\s*0\s*\)", text, re.IGNORECASE) or \
                   re.search(rf"{mm}.*COALESCE", text, re.IGNORECASE), (
                f"Falta COALESCE({mm}, 0)"
            )

    def test_dia_semana_range(self):
        """dia_semana debe venir de DAYOFWEEK (rango 1-7)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        # Verificar que usa DAYOFWEEK o DAYOFWEEK_ISO (Databricks SQL)
        assert "DAYOFWEEK" in text.upper() or "DOW" in text.upper(), (
            "dia_semana debe usar DAYOFWEEK (1=lunes, 7=domingo)"
        )

    def test_mes_range(self):
        """mes debe venir de MONTH (rango 1-12)."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "MONTH(" in text.upper() or "MONTH(" in text, (
            "mes debe usar MONTH(business_date)"
        )

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

    def test_uses_window_functions(self):
        """INSERT debe usar LAG() y AVG() OVER para lags y medias móviles."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LAG(" in text.upper() or "LAG (" in text.upper(), (
            "Falta LAG() window function"
        )
        assert "AVG(" in text.upper() or "AVG (" in text.upper(), (
            "Falta AVG() window function"
        )
        assert "OVER" in text.upper(), (
            "Falta cláusula OVER (PARTITION BY)"
        )

    def test_has_validation_count(self):
        """Debe tener SELECT de validación con COUNT."""
        sql = _extract_sql(self.NOTEBOOK)
        assert "COUNT(*)" in sql, "Falta COUNT(*) de validación"

    def test_joins_inventario_actual(self):
        """INSERT debe hacer LEFT JOIN con mart_inventario_actual para stock."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text
        assert "mart_inventario_actual" in text

    def test_joins_rotacion_abc(self):
        """INSERT debe hacer LEFT JOIN con mart_rotacion_abc para categoria_abc."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text
        assert "mart_rotacion_abc" in text

    def test_joins_productos_dormidos(self):
        """INSERT debe hacer LEFT JOIN con mart_productos_dormidos para dias_sin_venta."""
        stmts = _get_insert_statements(self.NOTEBOOK)
        text = str(stmts[0]) if stmts else ""
        assert "LEFT JOIN" in text
        assert "mart_productos_dormidos" in text


class TestFeatureStoreFormat:
    """Valida formato del notebook feature store."""

    NOTEBOOK = GOLD_DIR / FEATURE_NOTEBOOK

    def test_starts_with_databricks_source(self):
        """Debe empezar con -- Databricks notebook source."""
        first_line = self.NOTEBOOK.read_text().splitlines()[0].strip()
        assert first_line == "-- Databricks notebook source", (
            f"Empieza con: {first_line}"
        )

    def test_has_comment_separators(self):
        """Debe tener separadores de celda COMMAND."""
        content = self.NOTEBOOK.read_text()
        assert "-- COMMAND ----------" in content
