"""Regression tests for movement dates and DuckDB snapshot replacement."""

from __future__ import annotations

from pathlib import Path

import duckdb

from motoshop_api.metrics.repo_duckdb import (
    DuckDBMetricsRepo,
    close_all_shared_connections,
)


def _create_sales_db(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas (
                num_documento VARCHAR,
                cod_clase VARCHAR,
                business_date DATE,
                total_factura DOUBLE,
                estado_documento VARCHAR
            )
            """
        )
        connection.execute(
            """
            INSERT INTO silver_fact_ventas VALUES
                ('V17', 'FV', '2026-07-17', 100.0, 'B'),
                ('V18', 'FV', '2026-07-18', 200.0, 'B'),
                ('A19', 'FV', '2026-07-19', 999.0, 'A')
            """
        )
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas_detalle (
                num_documento VARCHAR,
                cod_clase VARCHAR,
                business_date DATE,
                cod_producto VARCHAR,
                cantidad DOUBLE,
                total_detalle DOUBLE
            );
            INSERT INTO silver_fact_ventas_detalle VALUES
                ('V17', 'FV', '2026-07-17', 'A', 1, 100),
                ('V18', 'FV', '2026-07-18', 'B', 1, 200),
                ('A19', 'FV', '2026-07-19', 'C', 1, 999);
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR,
                nombre_producto VARCHAR
            );
            INSERT INTO silver_dim_producto VALUES
                ('A', 'Item A'), ('B', 'Item B'), ('C', 'Canceled item');
            """
        )
        connection.execute(
            """
            CREATE TABLE gold_mart_ventas_diarias_sku (
                business_date DATE,
                cod_producto VARCHAR,
                nom_producto VARCHAR,
                cantidad_total DOUBLE,
                valor_total DOUBLE,
                num_facturas INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO gold_mart_ventas_diarias_sku VALUES
                ('2026-07-17', 'A', 'Item A', 1, 100, 1),
                ('2026-07-18', 'B', 'Item B', 1, 200, 1)
            """
        )
    finally:
        connection.close()


def _repo(path: Path) -> DuckDBMetricsRepo:
    close_all_shared_connections()
    return DuckDBMetricsRepo(db_path=path, tenant="test-sales")


def test_explicit_day_without_sales_does_not_fall_back(tmp_path: Path) -> None:
    db_path = tmp_path / "sales.duckdb"
    _create_sales_db(db_path)

    response = _repo(db_path).get_sales_daily("2026-07-19")

    assert response.date == "2026-07-19"
    assert response.total_ventas == 0
    assert response.total_facturas == 0
    assert response.productos_vendidos == []


def test_summary_and_daily_calendar_share_business_cutoff(tmp_path: Path) -> None:
    db_path = tmp_path / "sales.duckdb"
    _create_sales_db(db_path)
    repo = _repo(db_path)

    summary = repo.get_sales_summary_v2()
    calendar = repo.get_sales_daily_month("2026-07")

    assert summary["as_of_business_date"] == "2026-07-18"
    assert calendar["as_of_business_date"] == "2026-07-18"
    assert [day["date"] for day in calendar["days"]] == ["2026-07-17", "2026-07-18"]


def test_empty_sales_dataset_has_null_business_cutoff(tmp_path: Path) -> None:
    db_path = tmp_path / "empty-sales.duckdb"
    _create_sales_db(db_path)
    connection = duckdb.connect(str(db_path))
    try:
        connection.execute("DELETE FROM silver_fact_ventas")
    finally:
        connection.close()
    repo = _repo(db_path)

    summary = repo.get_sales_summary_v2()
    calendar = repo.get_sales_daily_month("2026-07")

    assert summary["business_month"] is None
    assert summary["max_sales_date"] is None
    assert summary["as_of_business_date"] is None
    assert calendar["as_of_business_date"] is None
