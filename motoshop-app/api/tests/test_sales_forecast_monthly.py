"""Monthly forecast contract and calendar comparison regression tests."""

from __future__ import annotations

from pathlib import Path

import duckdb

from motoshop_api.main import app
from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo, close_all_shared_connections


def _forecast_repo(path: Path) -> DuckDBMetricsRepo:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas (
                business_date DATE,
                total_factura DOUBLE,
                estado_documento VARCHAR
            );
            INSERT INTO silver_fact_ventas VALUES
                ('2025-07-10', 111, 'B'),
                ('2025-08-10', 222, 'B'),
                ('2025-08-11', 999, 'A'),
                ('2026-04-10', 900, 'B'),
                ('2026-05-10', 1000, 'B'),
                ('2026-06-10', 1100, 'B'),
                ('2026-07-18', 200, 'B')
            """
        )
    finally:
        connection.close()
    close_all_shared_connections()
    return DuckDBMetricsRepo(db_path=path, tenant="forecast-test")


def test_next_month_compares_with_that_month_last_year(tmp_path: Path) -> None:
    result = _forecast_repo(tmp_path / "forecast.duckdb").get_sales_forecast_monthly()

    assert result["next_month"]["month"] == "2026-08"
    assert result["next_month"]["last_year_same_month"] == 222
    previous = next(item for item in result["history"] if item["month"] == "2026-06")
    assert "projected_amount" in previous
    assert previous["projected_amount"] >= 0


def test_monthly_forecast_endpoint_has_a_response_model() -> None:
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/metrics/sales-forecast-monthly"
    )

    assert route.response_model is not None
    assert route.response_model.__name__ == "SalesForecastMonthlyResponse"
