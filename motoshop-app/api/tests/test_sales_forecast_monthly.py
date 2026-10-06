"""Monthly forecast contract and calendar comparison regression tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
from fastapi import HTTPException

from motoshop_api.auth.module_access import authorize_modules, route_modules
from motoshop_api.auth.users import User
from motoshop_api.main import app
from motoshop_api.metrics.repo_duckdb import (
    DuckDBMetricsRepo,
    _allocate_stock_adjusted_demand,
    _calibrate_forecast_confidence,
    close_all_shared_connections,
)
from motoshop_api.metrics.schemas import SalesForecastMonthlyResponse


def _forecast_repo(
    path: Path,
    tenant: str = "forecast-test",
    *,
    with_product_snapshot: bool = True,
    inventory_units: float = 8,
    with_unpurchased_snapshot_sku: bool = False,
    with_unknown_stock_sku: bool = False,
    with_duplicate_purchase_lines: bool = False,
    with_explicit_service_indicator: bool = False,
    with_calendar_patterns: bool = False,
) -> DuckDBMetricsRepo:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas (
                business_date DATE,
                total_factura DOUBLE,
                estado_documento VARCHAR,
                num_documento VARCHAR,
                cod_clase VARCHAR
            );
            INSERT INTO silver_fact_ventas VALUES
                ('2025-07-10', 111, 'B', 'S-2025-07', 'FV'),
                ('2025-08-10', 222, 'B', 'S-2025-08', 'FV'),
                ('2025-08-11', 999, 'A', 'S-CANCELED', 'FV'),
                ('2026-04-10', 900, 'B', 'S-2026-04', 'FV'),
                ('2026-05-10', 1000, 'B', 'S-2026-05', 'FV'),
                ('2026-06-10', 1100, 'B', 'S-2026-06', 'FV'),
                ('2026-07-18', 200, 'B', 'S-2026-07', 'FV'),
                ('2026-07-19', 400, 'B', 'S-DUP-HEADER', 'FV'),
                ('2026-07-19', 400, 'B', 'S-DUP-HEADER', 'FV'),
                ('2026-07-20', 999, 'A', 'S-CANCELED-LATE', 'FV');
            CREATE TABLE silver_fact_ventas_detalle (
                business_date DATE, cod_clase VARCHAR, num_documento VARCHAR,
                cod_producto VARCHAR, cantidad DOUBLE, total_detalle DOUBLE,
                valor_unitario DOUBLE
            );
            CREATE TABLE silver_fact_compras (
                business_date DATE, cod_clase VARCHAR, num_documento VARCHAR,
                estado_documento VARCHAR
            );
            CREATE TABLE silver_fact_compras_detalle (
                business_date DATE, cod_clase VARCHAR, num_documento VARCHAR,
                cod_producto VARCHAR, cantidad DOUBLE
            );
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR, nombre_producto VARCHAR,
                existencia DOUBLE, snapshot_date DATE
            );
            INSERT INTO silver_fact_ventas_detalle VALUES
                ('2026-04-10', 'FV', 'S-2026-04', 'SKU-1', 10, 900, 90),
                ('2026-04-10', 'FV', 'S-2026-04', 'SKU-1', 10, 900, 90),
                ('2026-05-10', 'FV', 'S-2026-05', 'SKU-1', 10, 1000, 100),
                ('2026-06-10', 'FV', 'S-2026-06', 'SKU-1', 10, 0, 110),
                ('2026-07-18', 'FV', 'S-2026-07', 'SKU-1', 2, 200, 100),
                ('2026-07-19', 'FV', 'S-DUP-HEADER', 'SKU-1', 100, 10000, 100),
                ('2026-07-20', 'FV', 'S-CANCELED-LATE', 'SKU-1', 100, 10000, 100);
            INSERT INTO silver_fact_compras VALUES
                ('2026-03-01', 'FC', 'P-1', 'B'),
                ('2026-07-19', 'FC', 'P-DUP-HEADER', 'B'),
                ('2026-07-19', 'FC', 'P-DUP-HEADER', 'B'),
                ('2026-07-20', 'FC', 'P-CANCELED-LATE', 'A');
            INSERT INTO silver_fact_compras_detalle VALUES
                ('2026-03-01', 'FC', 'P-1', 'SKU-1', 40),
                ('2026-07-19', 'FC', 'P-DUP-HEADER', 'SKU-1', 100),
                ('2026-07-20', 'FC', 'P-CANCELED-LATE', 'SKU-1', 100);
            """
        )
        if with_explicit_service_indicator:
            connection.execute(
                "ALTER TABLE silver_dim_producto ADD COLUMN es_servicio BOOLEAN"
            )
        if with_product_snapshot:
            connection.execute(
                "INSERT INTO silver_dim_producto "
                "(cod_producto, nombre_producto, existencia, snapshot_date) "
                "VALUES (?, ?, ?, ?)",
                ["SKU-1", "Test item", inventory_units, date(2026, 7, 19)],
            )
        if with_unpurchased_snapshot_sku:
            connection.execute(
                "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?, ?)",
                [date(2026, 4, 11), 9000, "B", "S-SNAPSHOT-ONLY", "FV"],
            )
            connection.execute(
                "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [date(2026, 4, 11), "FV", "S-SNAPSHOT-ONLY", "SNAPSHOT-ONLY", 90, 9000, 100],
            )
            if with_product_snapshot:
                connection.execute(
                    "INSERT INTO silver_dim_producto "
                    "(cod_producto, nombre_producto, existencia, snapshot_date) "
                    "VALUES (?, ?, ?, ?)",
                    ["SNAPSHOT-ONLY", "Snapshot-controlled item", 1, date(2026, 7, 19)],
                )
        if with_explicit_service_indicator:
            connection.execute(
                "UPDATE silver_dim_producto SET es_servicio = TRUE "
                "WHERE cod_producto = 'SKU-1'"
            )
        if with_unknown_stock_sku:
            connection.execute(
                "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?, ?)",
                [date(2026, 4, 12), 9000, "B", "S-UNKNOWN-STOCK", "FV"],
            )
            connection.execute(
                "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [date(2026, 4, 12), "FV", "S-UNKNOWN-STOCK", "UNKNOWN-STOCK", 90, 9000, 100],
            )
        if with_duplicate_purchase_lines:
            connection.execute(
                "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?)",
                [date(2026, 7, 19), "FC", "P-DUP-LINES", "B"],
            )
            connection.execute(
                "INSERT INTO silver_fact_compras_detalle VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)",
                [date(2026, 7, 19), "FC", "P-DUP-LINES", "SKU-1", 5,
                 date(2026, 7, 19), "FC", "P-DUP-LINES", "SKU-1", 5],
            )
        if with_calendar_patterns:
            pattern_start = date(2026, 4, 2)
            pattern_end = date(2026, 6, 30)
            weekday_amounts = (180, 240, 310, 390, 520, 90, 0)
            pattern_headers = []
            cursor = pattern_start
            while cursor <= pattern_end:
                amount = weekday_amounts[cursor.weekday()]
                if amount:
                    month_week_bonus = 120 if cursor.day <= 7 else 0
                    pattern_headers.append((
                        cursor,
                        amount + month_week_bonus,
                        "B",
                        f"CAL-{cursor.isoformat()}",
                        "FV",
                    ))
                cursor += timedelta(days=1)
            connection.executemany(
                "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?, ?)",
                pattern_headers,
            )
    finally:
        connection.close()
    close_all_shared_connections()
    return DuckDBMetricsRepo(db_path=path, tenant=tenant)


def test_next_month_compares_with_that_month_last_year(tmp_path: Path) -> None:
    result = _forecast_repo(tmp_path / "forecast.duckdb").get_sales_forecast_monthly(
        as_of_date=date(2026, 7, 20)
    )
    SalesForecastMonthlyResponse(**result)

    assert result["next_month"]["month"] == "2026-08"
    assert result["next_month"]["last_year_same_month"] == 222
    previous = next(item for item in result["history"] if item["month"] == "2026-06")
    assert "projected_amount" in previous
    assert previous["projected_amount"] >= 0
    assert result["backtest_accuracy"]["sample_months"] == 3
    assert result["current_month"]["confidence"] == result["backtest_accuracy"]["confidence"]
    assert result["current_month"]["observed_amount"] == 200
    assert result["stock_adjusted"]["no_future_replenishment"] is True
    assert result["business_timezone"] == "America/Bogota"
    assert result["model_version"] == "weekday_week_of_month_v1_stock_scenario"
    assert result["daily_pattern"]["method"] == "flat_daily_fallback"

    current_days = [
        item for item in result["daily_series"] if item["date"].strftime("%Y-%m") == "2026-07"
    ]
    next_days = [
        item for item in result["daily_series"] if item["date"].strftime("%Y-%m") == "2026-08"
    ]
    assert round(sum(
        (item["actual_amount"] or 0) + (item["base_projected_amount"] or 0)
        for item in current_days
    ), 2) == (
        result["current_month"]["projected_amount"]
    )
    assert round(sum(
        (item["actual_amount"] or 0) + (item["base_projected_amount"] or 0)
        for item in next_days
    ), 2) == (
        result["next_month"]["projected_amount"]
    )
    assert round(sum(
        (item["actual_amount"] or 0) + (item["stock_adjusted_projected_amount"] or 0)
        for item in current_days
    ), 2) == (
        result["stock_adjusted"]["current_month"]["projected_amount"]
    )
    assert round(sum(
        (item["actual_amount"] or 0) + (item["stock_adjusted_projected_amount"] or 0)
        for item in next_days
    ), 2) == (
        result["stock_adjusted"]["next_month"]["projected_amount"]
    )
    observed_days = [item for item in current_days if item["actual_amount"] is not None]
    assert observed_days
    assert all(item["base_projected_amount"] is None for item in observed_days)
    assert all(item["stock_adjusted_projected_amount"] is None for item in observed_days)
    assert all(item["actual_amount"] is None for item in next_days)


def test_daily_forecast_varies_by_weekday_and_reconciles_to_monthly_total(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "weekday-calendar-forecast.duckdb",
        tenant="masvital",
        inventory_units=1_000,
        with_calendar_patterns=True,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    current_forecast_days = [
        item
        for item in result["daily_series"]
        if item["date"].strftime("%Y-%m") == "2026-07"
        and item["base_projected_amount"] is not None
    ]
    daily_amounts = [item["base_projected_amount"] for item in current_forecast_days]
    stock_daily_amounts = [
        item["stock_adjusted_projected_amount"] for item in current_forecast_days
    ]

    assert result["daily_pattern"]["method"] == "weekday_week_of_month"
    assert result["daily_pattern"]["days_with_sales"] >= 28
    assert "día de semana" in result["daily_pattern"]["note"]
    assert len({round(amount, 2) for amount in daily_amounts}) > 1
    assert len({round(amount, 2) for amount in stock_daily_amounts}) > 1
    assert round(sum(daily_amounts), 2) == round(
        result["current_month"]["projected_amount"]
        - result["current_month"]["observed_amount"],
        2,
    )
    assert round(sum(stock_daily_amounts), 2) == round(
        result["stock_adjusted"]["current_month"]["projected_amount"]
        - result["stock_adjusted"]["current_month"]["observed_amount"],
        2,
    )


def test_daily_sales_month_uses_the_same_valid_invoice_headers_as_the_forecast(
    tmp_path: Path,
) -> None:
    repo = _forecast_repo(tmp_path / "daily-forecast-parity.duckdb")

    daily = repo.get_sales_daily_month("2026-07")

    assert daily["days"] == [{
        "date": "2026-07-18",
        "day": 18,
        "sales": 200.0,
        "invoices": 1,
        "avg_ticket": 200.0,
        "accumulated": 200.0,
    }]


def test_old_sales_cutoff_does_not_move_calendar_horizon_backwards(tmp_path: Path) -> None:
    result = _forecast_repo(tmp_path / "stale-forecast.duckdb").get_sales_forecast_monthly(
        as_of_date=date(2026, 10, 5)
    )

    assert result["current_month"]["month"] == "2026-10"
    assert result["next_month"]["month"] == "2026-11"
    assert result["current_month"]["observed_amount"] == 0
    assert result["current_month"]["days_observed"] == 0
    assert result["current_month"]["projected_amount"] > 0
    assert result["source_cutoffs"]["sales_date"] == date(2026, 7, 18)
    assert result["staleness"]["sales_is_stale"] is True
    october_days = [
        item for item in result["daily_series"] if item["date"].strftime("%Y-%m") == "2026-10"
    ]
    assert all(item["actual_amount"] is None for item in october_days)
    assert round(sum(
        (item["actual_amount"] or 0) + (item["base_projected_amount"] or 0)
        for item in october_days
    ), 2) == (
        result["current_month"]["projected_amount"]
    )


def test_masvital_stock_scenario_uses_latest_inventory_snapshot_and_carries_stock(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "masvital-forecast.duckdb", tenant="masvital"
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    assert result["stock_adjusted"]["inventory_source"] == (
        "silver_dim_producto.existencia (último snapshot)"
    )
    assert result["source_cutoffs"]["inventory_date"] == date(2026, 7, 19)
    assert result["source_cutoffs"]["sales_date"] == date(2026, 7, 18)
    assert result["source_cutoffs"]["purchases_date"] == date(2026, 3, 1)
    # Eight units are available at the latest snapshot; both months together
    # cannot realize more than those eight units at the historical unit revenue.
    projected_future_revenue = (
        result["stock_adjusted"]["current_month"]["projected_amount"]
        - result["stock_adjusted"]["current_month"]["observed_amount"]
        + result["stock_adjusted"]["next_month"]["projected_amount"]
    )
    assert projected_future_revenue <= 8 * 100
    assert round(
        result["stock_adjusted"]["current_month"]["projected_amount"]
        - result["stock_adjusted"]["current_month"]["observed_amount"],
        2,
    ) == 433.33


def test_masvital_sku_without_inventory_snapshot_is_flagged_as_insufficient(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "masvital-no-stock.duckdb",
        tenant="masvital",
        with_product_snapshot=False,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    assert result["stock_adjusted"]["insufficient_evidence_skus"] == 1
    assert result["stock_adjusted"]["current_month"]["projected_amount"] == 200
    assert result["stock_adjusted"]["inventory_source"].endswith("sin snapshot disponible)")


def test_masvital_snapshot_caps_sku_without_purchases_and_unknown_stock_is_not_a_service(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "masvital-snapshot-only.duckdb",
        tenant="masvital",
        with_unpurchased_snapshot_sku=True,
        with_unknown_stock_sku=True,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    stock = result["stock_adjusted"]
    future_revenue = (
        stock["current_month"]["projected_amount"]
        - stock["current_month"]["observed_amount"]
        + stock["next_month"]["projected_amount"]
    )
    # SKU-1 realizes eight snapshot units ($600); SNAPSHOT-ONLY realizes its
    # one snapshot unit ($100); UNKNOWN-STOCK has no evidence and realizes $0.
    assert future_revenue == 700
    assert stock["inventory_controlled_skus"] == 2
    assert stock["uncapped_service_skus"] == 0
    assert stock["insufficient_evidence_skus"] == 1


def test_unknown_motoshop_stock_is_not_classified_as_an_uncapped_service(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "motoshop-unknown-stock.duckdb",
        tenant="motoshop",
        with_unknown_stock_sku=True,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    stock = result["stock_adjusted"]
    assert stock["uncapped_service_skus"] == 0
    assert stock["insufficient_evidence_skus"] == 1
    assert stock["current_month"]["projected_amount"] == 200
    assert stock["next_month"]["projected_amount"] == 0


def test_only_an_explicit_service_indicator_allows_uncapped_revenue(tmp_path: Path) -> None:
    result = _forecast_repo(
        tmp_path / "explicit-service-indicator.duckdb",
        tenant="motoshop",
        with_explicit_service_indicator=True,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    stock = result["stock_adjusted"]
    assert stock["uncapped_service_skus"] == 1
    assert stock["insufficient_evidence_skus"] == 0
    assert round((
        stock["current_month"]["projected_amount"]
        - stock["current_month"]["observed_amount"]
        + stock["next_month"]["projected_amount"]
    ), 2) == 1466.66


def test_duplicate_looking_purchase_and_sales_lines_under_valid_headers_are_counted(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "duplicate-forecast-lines.duckdb",
        tenant="motoshop",
        with_duplicate_purchase_lines=True,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    stock = result["stock_adjusted"]
    future_revenue = (
        stock["current_month"]["projected_amount"]
        - stock["current_month"]["observed_amount"]
        + stock["next_month"]["projected_amount"]
    )
    # The two identical April sales rows and two identical purchase rows each
    # belong to a unique valid header: 50 purchased - 42 sold = 8 units at $75.
    assert future_revenue == 600


def test_stock_adjusted_revenue_reconciles_to_header_totals_when_unconstrained(
    tmp_path: Path,
) -> None:
    result = _forecast_repo(
        tmp_path / "header-reconciliation.duckdb",
        tenant="masvital",
        inventory_units=10_000,
    ).get_sales_forecast_monthly(as_of_date=date(2026, 7, 20))

    # The April header is $900 while its two details sum to $1,800; the June
    # line total is zero and falls back to its $1,100 unit-value amount. With
    # ample stock, header-prorated SKU revenue must match the header baseline.
    assert result["current_month"]["projected_amount"] == 633.33
    assert result["next_month"]["projected_amount"] == 1033.33
    assert result["stock_adjusted"]["current_month"]["projected_amount"] == 633.33
    assert result["stock_adjusted"]["next_month"]["projected_amount"] == 1033.33


def test_stock_scenario_caps_inventory_and_carries_only_unspent_units() -> None:
    demand = [
        {"sku": "stocked", "units_90d": 90, "revenue_90d": 900, "is_service": False},
        {"sku": "service", "units_90d": 90, "revenue_90d": 1800, "is_service": True},
        {"sku": "unknown", "units_90d": 90, "revenue_90d": 900, "is_service": False},
    ]

    current = _allocate_stock_adjusted_demand(
        demand, 30, {"stocked": 2, "service": None, "unknown": None}
    )
    following = _allocate_stock_adjusted_demand(demand, 31, current["remaining_stock"])

    assert current["realized"]["stocked"]["projected_units"] <= 2
    assert current["realized"]["service"]["projected_units"] == 30
    assert current["realized"]["unknown"]["projected_units"] == 0
    assert current["realized"]["unknown"]["insufficient_evidence"] is True
    assert (
        current["realized"]["stocked"]["projected_units"]
        + following["realized"]["stocked"]["projected_units"]
        <= 2
    )


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
