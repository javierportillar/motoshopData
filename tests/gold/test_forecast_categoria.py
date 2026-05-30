"""
Tests unitarios de forecasting por categoría — MotoShop F6-B.

Usa sqlparse para validar estructura SQL en notebooks Databricks.
Tests locales sin PySpark.

Ejecutar: pytest tests/gold/test_forecast_categoria.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlparse

GOLD_DIR = Path("notebooks/gold")

# ── Helpers ──────────────────────────────────────────────────────────────────


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


def _get_select_statements(path: Path) -> list[sqlparse.sql.Statement]:
    """Extrae statements SELECT del notebook (para validación)."""
    sql = _extract_sql(path)
    parsed = sqlparse.parse(sql)
    result = []
    for stmt in parsed:
        if stmt.get_type() == "SELECT":
            result.append(stmt)
    return result


def _get_create_columns(path: Path) -> dict[str, str]:
    """Extrae columnas del CREATE TABLE como dict {nombre: tipo}."""
    creates = _get_create_statements(path)
    if not creates:
        return {}

    create_sql = creates[0].value
    paren = create_sql.index("(")
    col_block = create_sql[paren:]

    cols: dict[str, str] = {}
    for line in col_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(")") or stripped.startswith("("):
            continue
        if stripped.upper().startswith("USING") or stripped.upper().startswith(
            "PARTITIONED"
        ):
            continue
        parts = stripped.split(None, 1)
        if len(parts) >= 2:
            name = parts[0].strip().strip(",")
            dtype = parts[1].strip().strip(",")
            cols[name] = dtype
    return cols


# ── Datos de referencia ──────────────────────────────────────────────────────

FORECAST_CATEGORIA_COLS = {
    "cod_grupo": "STRING",
    "business_date": "DATE",
    "demanda_real": "DOUBLE",
    "demanda_predicha_baseline": "DOUBLE",
    "metodo_baseline": "STRING",
}


# ── Tests 24_forecast_categoria.py ───────────────────────────────────────────


class TestForecastCategoria:
    """Validación del notebook 24 (forecast por categoría)."""

    NOTEBOOK = GOLD_DIR / "24_forecast_categoria.py"

    def test_notebook_exists(self):
        assert self.NOTEBOOK.exists(), f"No existe: {self.NOTEBOOK}"

    def test_has_create_table(self):
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1, "Debe tener al menos un CREATE TABLE"

    def test_create_table_has_partitioned_by(self):
        create_sql = _get_create_statements(self.NOTEBOOK)[0].value.upper()
        assert "PARTITIONED BY" in create_sql, (
            "CREATE TABLE debe tener PARTITIONED BY"
        )

    def test_create_table_has_required_columns(self):
        cols = _get_create_columns(self.NOTEBOOK)
        for col_name, col_type in FORECAST_CATEGORIA_COLS.items():
            assert col_name in cols, f"Falta columna: {col_name}"
            assert col_type in cols[col_name].upper(), (
                f"Columna {col_name} debe ser {col_type}, got {cols[col_name]}"
            )

    def test_has_creat_or_replace_temp_view(self):
        """Debe usar CREATE OR REPLACE TEMPORARY VIEW (patrón F4-B)."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "CREATE OR REPLACE TEMPORARY VIEW" in sql, (
            "Debe usar CREATE OR REPLACE TEMPORARY VIEW para evitar CTE "
            "dentro de INSERT"
        )

    def test_has_insert_overwrite_from_view(self):
        """INSERT OVERWRITE debe leer de la temporary view."""
        inserts = _get_insert_statements(self.NOTEBOOK)
        assert len(inserts) >= 1, "Debe tener al menos un INSERT"

        insert_sql = inserts[0].value.upper()
        # Verificar que selecciona desde una vista
        assert "SELECT" in insert_sql, "INSERT debe tener SELECT"

        # Verificar que particiona por business_date
        assert "PARTITION" in insert_sql, (
            "INSERT debe particionar por business_date"
        )

    def test_insert_overwrite_targets_forecast_categoria(self):
        """INSERT debe targetear gold.forecast_categoria."""
        inserts = _get_insert_statements(self.NOTEBOOK)
        insert_sql = inserts[0].value.upper()
        assert "FORECAST_CATEGORIA" in insert_sql, (
            "INSERT debe targetear gold.forecast_categoria"
        )

    def test_join_with_dim_producto(self):
        """Debe hacer JOIN con dim_producto para obtener cod_grupo."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "DIM_PRODUCTO" in sql, "Debe referenciar dim_producto"
        assert "COD_GRUPO" in sql, "Debe usar cod_grupo para la agregación"

    def test_joins_mart_ventas_diarias_sku(self):
        """Debe leer de mart_ventas_diarias_sku como fuente de ventas."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "MART_VENTAS_DIARIAS_SKU" in sql, (
            "Debe leer de mart_ventas_diarias_sku"
        )

    def test_has_coalesce_for_sin_grupo(self):
        """Debe manejar SKUs sin cod_grupo con COALESCE."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "COALESCE" in sql, "Debe usar COALESCE para valores NULL"
        assert "SIN_GRUPO" in sql, "Debe agrupar SKUs sin grupo como 'SIN_GRUPO'"

    def test_has_wape_calculation(self):
        """Debe tener cálculo de WAPE como validación."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "WAPE" in sql or "SUM(ABS" in sql, (
            "Debe tener cálculo de WAPE en las validaciones"
        )

    def test_has_validation_selects(self):
        """Debe tener suficientes SELECTs de validación."""
        selects = _get_select_statements(self.NOTEBOOK)
        # DDL (1) + demanda_categoria view (1) + baseline view (1) + INSERT (1)
        # + 5 validaciones = al menos 5 SELECTs puros de validación
        assert len(selects) >= 5, (
            f"Debe tener al menos 5 SELECTs de validación, tiene {len(selects)}"
        )

    def test_has_coverage_by_category(self):
        """Debe validar cobertura de categorías con ≥ 90 días."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "90" in sql, (
            "Debe tener filtro de elegibilidad (≥90 días)"
        )

    def test_has_wape_by_category(self):
        """Debe tener WAPE por categoría individual."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "GROUP BY" in sql and "WAPE_PCT" in sql.upper(), (
            "Debe tener WAPE agrupado por categoría"
        )

    def test_baseline_uses_moving_average(self):
        """Baseline debe usar media móvil 7/14/28 días."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "AVG(" in sql, "Debe usar AVG para media móvil"
        assert "ROWS BETWEEN" in sql, (
            "Debe usar ROWS BETWEEN para ventana móvil"
        )

    def test_eval_script_exists(self):
        """Debe existir el script de evaluación con Prophet."""
        eval_script = GOLD_DIR / "eval_forecast_categoria.py"
        assert eval_script.exists(), (
            f"No existe script de evaluación: {eval_script}"
        )

    def test_eval_script_has_wape_function(self):
        """El script de evaluación debe tener función WAPE."""
        eval_script = GOLD_DIR / "eval_forecast_categoria.py"
        content = eval_script.read_text()
        assert "def wape(" in content, "Debe tener función wape()"
        assert "def main()" in content, "Debe tener función main()"
        assert "Prophet" in content, "Debe usar Prophet para ML"
