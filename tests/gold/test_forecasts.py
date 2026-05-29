"""
Tests unitarios de forecast + classifier — MotoShop F4-B.

Usa sqlparse para validar estructura SQL en notebooks Databricks.
Tests locales sin PySpark.

Ejecutar: pytest tests/gold/test_forecasts.py -v
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
        if stripped.upper().startswith("USING") or stripped.upper().startswith("PARTITIONED"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) >= 2:
            name = parts[0].strip().strip(",")
            dtype = parts[1].strip().strip(",")
            cols[name] = dtype
    return cols


# ── Datos de referencia ──────────────────────────────────────────────────────

FORECAST_DEMANDA_COLS = {
    "sku": "STRING",
    "forecast_date": "DATE",
    "horizon": "INT",
    "predicted_qty": "DOUBLE",
    "confidence_lower": "DOUBLE",
    "confidence_upper": "DOUBLE",
    "model_version": "STRING",
    "mape": "DOUBLE",
    "smape": "DOUBLE",
    "business_date": "DATE",
}

ALERTAS_QUIEBRE_COLS = {
    "sku": "STRING",
    "nom_producto": "STRING",
    "stock_actual": "DOUBLE",
    "demanda_predicha": "DOUBLE",
    "dias_hasta_quiebre": "DOUBLE",
    "urgencia": "STRING",
    "business_date": "DATE",
}

BASELINE_COLS = {
    "cod_producto": "STRING",
    "business_date": "DATE",
    "demanda_real": "DOUBLE",
    "demanda_predicha": "DOUBLE",
    "metodo": "STRING",
}


# ── Tests 16_forecast_baseline_sku.py ────────────────────────────────────────


class TestForecastBaseline:
    """Validación del notebook 16 (baseline naive estacional)."""

    NOTEBOOK = GOLD_DIR / "16_forecast_baseline_sku.py"

    def test_notebook_exists(self):
        assert self.NOTEBOOK.exists(), f"No existe: {self.NOTEBOOK}"

    def test_has_create_table(self):
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1, "Debe tener al menos un CREATE TABLE"

    def test_create_table_has_partitioned_by(self):
        create_sql = _get_create_statements(self.NOTEBOOK)[0].value.upper()
        assert "PARTITIONED BY" in create_sql, "CREATE TABLE debe tener PARTITIONED BY"

    def test_create_table_has_required_columns(self):
        cols = _get_create_columns(self.NOTEBOOK)
        for col_name, col_type in BASELINE_COLS.items():
            assert col_name in cols, f"Falta columna: {col_name}"
            assert col_type in cols[col_name].upper(), (
                f"Columna {col_name} debe ser {col_type}, got {cols[col_name]}"
            )

    def test_has_creat_or_replace_temp_view(self):
        """F4-B fix: debe usar CREATE OR REPLACE TEMPORARY VIEW (no WITH dentro de INSERT)."""
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "CREATE OR REPLACE TEMPORARY VIEW" in sql, (
            "Debe usar CREATE OR REPLACE TEMPORARY VIEW para evitar CTE dentro de INSERT"
        )

    def test_insert_overwrite_from_view(self):
        """INSERT OVERWRITE debe leer de la temporary view, no tener WITH anidado."""
        inserts = _get_insert_statements(self.NOTEBOOK)
        assert len(inserts) >= 1, "Debe tener al menos un INSERT"
        insert_sql = inserts[0].value.upper()
        assert "SELECT * FROM" in insert_sql or "SELECT *  FROM" in insert_sql, (
            "INSERT debe leer de la temporary view con SELECT * FROM"
        )
        # Verificar que NO hay WITH dentro del INSERT
        assert "WITH" not in insert_sql.split("INSERT")[-1].split("SELECT")[0] if "WITH" in insert_sql else True, (
            "El INSERT no debe contener WITH (debe leer de la view)"
        )

    def test_has_validation_selects(self):
        selects = _get_select_statements(self.NOTEBOOK)
        assert len(selects) >= 3, "Debe tener al menos 3 SELECTs de validación"


# ── Tests 22_classifier_stockout.py ──────────────────────────────────────────


class TestClassifierStockout:
    """Validación del notebook 22 (classifier stockout DDL)."""

    NOTEBOOK = GOLD_DIR / "22_classifier_stockout.py"

    def test_notebook_exists(self):
        assert self.NOTEBOOK.exists(), f"No existe: {self.NOTEBOOK}"

    def test_has_create_table(self):
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1, "Debe tener CREATE TABLE"

    def test_create_table_has_partitioned_by(self):
        create_sql = _get_create_statements(self.NOTEBOOK)[0].value.upper()
        assert "PARTITIONED BY" in create_sql

    def test_create_table_has_required_columns(self):
        cols = _get_create_columns(self.NOTEBOOK)
        for col_name, col_type in ALERTAS_QUIEBRE_COLS.items():
            assert col_name in cols, f"Falta columna: {col_name}"
            assert col_type in cols[col_name].upper(), (
                f"Columna {col_name} debe ser {col_type}, got {cols[col_name]}"
            )

    def test_has_describe(self):
        sql = _extract_sql(self.NOTEBOOK).upper()
        assert "DESCRIBE" in sql, "Debe tener DESCRIBE para validar esquema"

    def test_has_validation_selects(self):
        selects = _get_select_statements(self.NOTEBOOK)
        assert len(selects) >= 2, "Debe tener al menos 2 SELECTs de validación"


# ── Tests 24_forecast_demanda_sku_ddl.sql ────────────────────────────────────


class TestForecastDemandaDDL:
    """Validación del DDL 24 (forecast_demanda_sku)."""

    NOTEBOOK = GOLD_DIR / "24_forecast_demanda_sku_ddl.sql"

    def test_notebook_exists(self):
        assert self.NOTEBOOK.exists(), f"No existe: {self.NOTEBOOK}"

    def test_has_create_table(self):
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1

    def test_create_table_has_partitioned_by(self):
        create_sql = _get_create_statements(self.NOTEBOOK)[0].value.upper()
        assert "PARTITIONED BY" in create_sql

    def test_create_table_has_required_columns(self):
        cols = _get_create_columns(self.NOTEBOOK)
        for col_name, col_type in FORECAST_DEMANDA_COLS.items():
            assert col_name in cols, f"Falta columna: {col_name}"
            assert col_type in cols[col_name].upper(), (
                f"Columna {col_name} debe ser {col_type}, got {cols[col_name]}"
            )

    def test_has_validation_selects(self):
        selects = _get_select_statements(self.NOTEBOOK)
        assert len(selects) >= 1


# ── Tests 25_alertas_quiebre_ddl.sql ─────────────────────────────────────────


class TestAlertasQuiebreDDL:
    """Validación del DDL 25 (alertas_quiebre)."""

    NOTEBOOK = GOLD_DIR / "25_alertas_quiebre_ddl.sql"

    def test_notebook_exists(self):
        assert self.NOTEBOOK.exists(), f"No existe: {self.NOTEBOOK}"

    def test_has_create_table(self):
        creates = _get_create_statements(self.NOTEBOOK)
        assert len(creates) >= 1

    def test_create_table_has_partitioned_by(self):
        create_sql = _get_create_statements(self.NOTEBOOK)[0].value.upper()
        assert "PARTITIONED BY" in create_sql

    def test_create_table_has_required_columns(self):
        cols = _get_create_columns(self.NOTEBOOK)
        for col_name, col_type in ALERTAS_QUIEBRE_COLS.items():
            assert col_name in cols, f"Falta columna: {col_name}"
            assert col_type in cols[col_name].upper(), (
                f"Columna {col_name} debe ser {col_type}, got {cols[col_name]}"
            )

    def test_has_validation_selects(self):
        selects = _get_select_statements(self.NOTEBOOK)
        assert len(selects) >= 1


# ── Tests unitarios run_classifier_stockout.py ────────────────────────────────


class TestClassifierUrgencyLogic:
    """Tests de la lógica de clasificación de urgencia (sin Databricks)."""

    def test_urgency_alta_when_dias_le_7(self):
        """dias_hasta_quiebre ≤ 7 debe dar urgencia 'alta' (si pred_quiebre=1)."""
        assert self._classify(stock=10, media_movil=5, dias=7) == "alta"
        assert self._classify(stock=10, media_movil=5, dias=3) == "alta"
        assert self._classify(stock=10, media_movil=5, dias=1) == "alta"

    def test_urgency_media_when_dias_le_14(self):
        """7 < dias_hasta_quiebre ≤ 14 debe dar urgencia 'media'."""
        assert self._classify(stock=20, media_movil=2, dias=10) == "media"
        assert self._classify(stock=20, media_movil=2, dias=14) == "media"

    def test_urgency_baja_when_dias_gt_14(self):
        """dias_hasta_quiebre > 14 debe dar urgencia 'baja'."""
        assert self._classify(stock=30, media_movil=1, dias=20) == "baja"
        assert self._classify(stock=30, media_movil=1, dias=30) == "baja"

    def test_no_negative_days(self):
        """dias_hasta_quiebre nunca debe ser negativo."""
        # Cuando media_movil_7d > 0 pero stock=0
        dias = self._calc_dias(stock=0, media_movil=10)
        assert dias >= 0, f"dias debe ser >= 0, got {dias}"
        # Cuando stock=0 y media_movil=0 (división por cero segura)
        dias = self._calc_dias(stock=0, media_movil=0)
        assert dias >= 0, f"dias debe ser >= 0, got {dias}"
        # Caso normal
        dias = self._calc_dias(stock=15, media_movil=3)
        assert dias == 5, f"dias debe ser 5, got {dias}"

    def test_pred_quiebre_0_es_baja(self):
        """Si pred_quiebre=0, urgencia siempre 'baja'."""
        assert self._classify(pred_quiebre=0, stock=100, media_movil=10, dias=30) == "baja"
        # Incluso si días hasta quiebre son pocos, si no hay quiebre predicho → baja
        assert self._classify(pred_quiebre=0, stock=5, media_movil=10, dias=1) == "baja"

    def test_dias_calculo_consistente(self):
        """dias_hasta_quiebre = stock_actual / media_movil_7d (rounded)."""
        assert self._calc_dias(stock=45, media_movil=5) == 9
        assert self._calc_dias(stock=10, media_movil=3) == 3  # 10/3 = 3.33 → 3
        assert self._calc_dias(stock=7, media_movil=2) == 4   # 7/2 = 3.5 → 4

    # ── Helpers de test (replican lógica del classifier) ─────────

    @staticmethod
    def _calc_dias(stock: float, media_movil: float) -> int:
        """Replica el cálculo de dias_hasta_quiebre del classifier."""
        if media_movil <= 0:
            return 999
        return max(0, round(stock / media_movil))

    @classmethod
    def _classify(cls, stock=10, media_movil=5, dias=None, pred_quiebre=1) -> str:
        """Replica la lógica de clasificación de urgencia del classifier."""
        if pred_quiebre == 0:
            return "baja"
        if dias is None:
            dias = cls._calc_dias(stock, media_movil)
        if dias <= 7:
            return "alta"
        elif dias <= 14:
            return "media"
        else:
            return "baja"
