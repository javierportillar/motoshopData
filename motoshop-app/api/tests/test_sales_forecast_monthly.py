"""Monthly forecast contract and calendar comparison regression tests."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi import HTTPException

from motoshop_api.auth.module_access import authorize_modules, route_modules
from motoshop_api.auth.users import User
from motoshop_api.main import app
from motoshop_api.metrics.repo_duckdb import (
    DuckDBMetricsRepo,
    _calibrate_forecast_confidence,
    close_all_shared_connections,
)


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
    assert result["backtest_accuracy"]["sample_months"] == 3
    assert result["current_month"]["confidence"] == result["backtest_accuracy"]["confidence"]


def test_monthly_forecast_endpoint_has_a_response_model() -> None:
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/metrics/sales-forecast-monthly"
    )

    assert route.response_model is not None
    assert route.response_model.__name__ == "SalesForecastMonthlyResponse"


def test_forecast_confidence_uses_backtest_error_not_only_sales_day_count() -> None:
    masvital = _calibrate_forecast_confidence([
        {"actual_amount": 12_600_000, "error_pct": 100.0},
        {"actual_amount": 17_700_000, "error_pct": 75.5},
        {"actual_amount": 17_500_000, "error_pct": 40.4},
    ])
    motoshop = _calibrate_forecast_confidence([
        {"actual_amount": 1_000, "error_pct": error}
        for error in (-13.9, -26.4, -18.5, -12.8, 0.9, -1.7)
    ])

    assert masvital["confidence"] == "low"
    assert masvital["sample_months"] == 3
    assert masvital["median_absolute_error_pct"] == 75.5
    assert motoshop["confidence"] == "high"
    assert motoshop["sample_months"] == 6


def test_forecast_confidence_stays_low_until_four_valid_backtest_months() -> None:
    result = _calibrate_forecast_confidence([
        {"actual_amount": 1_000, "error_pct": error}
        for error in (8.0, 10.0, 12.0)
    ])

    assert result["confidence"] == "low"
    assert result["sample_months"] == 3
    assert result["median_absolute_error_pct"] == 10.0


def test_four_backtest_months_with_moderate_error_have_medium_confidence() -> None:
    result = _calibrate_forecast_confidence([
        {"actual_amount": 1_000, "error_pct": error}
        for error in (20.0, 25.0, 25.0, 30.0)
    ])

    assert result["confidence"] == "medium"
    assert result["sample_months"] == 4
    assert result["median_absolute_error_pct"] == 25.0


def test_monthly_projection_route_is_available_from_analysis_or_forecast_module() -> None:
    modules = route_modules("GET", "/api/metrics/sales-forecast-monthly")
    assert modules == ("analisis", "forecast")

    analysis_user = User(
        username="analyst", hashed_password="x", email="a@example.test",
        role="analista", allowed_modules=["analisis"], source="supabase",
    )
    forecast_user = User(
        username="forecaster", hashed_password="x", email="f@example.test",
        role="analista", allowed_modules=["forecast"], source="supabase",
    )
    restricted_user = User(
        username="sales", hashed_password="x", email="s@example.test",
        role="vendedor", allowed_modules=["ventas-summary"], source="supabase",
    )

    assert authorize_modules(analysis_user, modules) is analysis_user
    assert authorize_modules(forecast_user, modules) is forecast_user
    with pytest.raises(HTTPException) as error:
        authorize_modules(restricted_user, modules)
    assert error.value.status_code == 403
