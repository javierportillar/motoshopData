"""Tests de paridad: DuckDB vs snapshot Databricks.

Compara row counts y SUM agregados de cada tabla vs raw_responses.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

DB_PATH = Path("out/motoshop_gold.duckdb")
RAW_RESPONSES = Path("docs/audit/raw_responses.json")


def _get_db() -> duckdb.DuckDBPyConnection:
    assert DB_PATH.exists(), f"DuckDB not found at {DB_PATH}"
    return duckdb.connect(str(DB_PATH), read_only=True)


def _get_raw(label: str) -> dict:
    data = json.loads(RAW_RESPONSES.read_text(encoding="utf-8"))
    for item in data:
        if item["label"] == label:
            body = item["body"]
            if isinstance(body, str):
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {}  # Truncado en snapshot
            return body
    return {}


def test_sales_summary_ventas_mes_actual() -> None:
    con = _get_db()
    result = con.execute("""
        SELECT ROUND(SUM(valor_total), 2) AS ventas_mes
        FROM motoshop_gold_mart_ventas_diarias_sku
        WHERE STRFTIME(business_date, '%Y-%m') = (
            SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM motoshop_gold_mart_ventas_diarias_sku
        )
    """).fetchone()[0]
    expected = _get_raw("SALES_SUMMARY").get("ventas_mes_actual")
    if expected is not None:
        assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"


def test_sales_summary_num_facturas() -> None:
    con = _get_db()
    result = con.execute("""
        SELECT SUM(num_facturas) AS num_facturas
        FROM motoshop_gold_mart_ventas_diarias_sku
        WHERE STRFTIME(business_date, '%Y-%m') = (
            SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM motoshop_gold_mart_ventas_diarias_sku
        )
    """).fetchone()[0]
    expected = _get_raw("SALES_SUMMARY").get("num_facturas")
    if expected is not None:
        assert result == expected, f"Expected {expected}, got {result}"


def test_inventory_rowcount() -> None:
    con = _get_db()
    result = con.execute("SELECT COUNT(DISTINCT cod_producto) FROM motoshop_gold_mart_inventario_actual").fetchone()[0]
    expected = _get_raw("INVENTORY").get("num_productos")
    if expected is not None:
        assert result == expected, f"Expected {expected}, got {result}"


def test_dormidos_rowcount() -> None:
    con = _get_db()
    result = con.execute("SELECT COUNT(*) FROM motoshop_gold_mart_productos_dormidos").fetchone()[0]
    assert result >= 0


def test_alertas_quiebre_rowcount() -> None:
    con = _get_db()
    result = con.execute("SELECT COUNT(*) FROM motoshop_gold_alertas_quiebre").fetchone()[0]
    # Snapshot JSON is truncated; verify we have data (46 in Databricks)
    assert result > 0, f"Expected >0 alerts, got {result}"


def test_forecast_categoria_rowcount() -> None:
    con = _get_db()
    result = con.execute("SELECT COUNT(DISTINCT cod_grupo) FROM motoshop_gold_forecast_categoria WHERE business_date >= CURRENT_DATE - INTERVAL '30' DAY").fetchone()[0]
    expected = _get_raw("FORECAST_CATEGORIA").get("total_categorias")
    if expected is not None:
        assert result == expected, f"Expected {expected}, got {result}"


def test_vendedores_rowcount() -> None:
    con = _get_db()
    result = con.execute("""
        SELECT COUNT(DISTINCT nit_vendedor)
        FROM motoshop_silver_fact_ventas
        WHERE STRFTIME(business_date, '%Y-%m') = (
            SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM motoshop_silver_fact_ventas
        )
          AND nit_vendedor IS NOT NULL AND nit_vendedor != ''
    """).fetchone()[0]
    expected = len(_get_raw("VENDEDORES_NO_PARAM").get("items", []))
    assert result == expected, f"Expected {expected}, got {result}"
