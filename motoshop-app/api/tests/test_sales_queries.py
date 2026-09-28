from __future__ import annotations

import pytest

from motoshop_api.llm.sales_queries import parse_sales_product_ranking_request


@pytest.mark.parametrize(
    ("month_name", "month_number", "last_day"),
    [
        ("enero", "01", "31"), ("febrero", "02", "28"), ("marzo", "03", "31"),
        ("abril", "04", "30"), ("mayo", "05", "31"), ("junio", "06", "30"),
        ("julio", "07", "31"), ("agosto", "08", "31"), ("septiembre", "09", "30"),
        ("octubre", "10", "31"), ("noviembre", "11", "30"), ("diciembre", "12", "31"),
    ],
)
def test_product_rank_accepts_any_calendar_month(
    month_name: str, month_number: str, last_day: str
) -> None:
    request = parse_sales_product_ranking_request(
        f"¿Cuál fue el producto más vendido del mes de {month_name} 2025?",
        sales_cutoff="2026-09-26",
    )

    assert request is not None
    assert request.metric == "units"
    assert [(period.date_from, period.date_to) for period in request.periods] == [
        (f"2025-{month_number}-01", f"2025-{month_number}-{last_day}")
    ]


def test_product_rank_months_are_independent_and_keep_user_order() -> None:
    request = parse_sales_product_ranking_request(
        "¿Cuál es el producto más vendido de septiembre y agosto?",
        sales_cutoff="2026-09-26",
    )

    assert request is not None
    assert [(period.date_from, period.date_to) for period in request.periods] == [
        ("2026-09-01", "2026-09-30"),
        ("2026-08-01", "2026-08-31"),
    ]


def test_today_yesterday_and_day_25_resolve_against_sales_cutoff() -> None:
    today = parse_sales_product_ranking_request(
        "¿Cuál fue el producto más vendido el día de hoy?",
        sales_cutoff="2026-09-26",
    )
    yesterday = parse_sales_product_ranking_request(
        "¿Y del día de ayer?",
        sales_cutoff="2026-09-26",
        inherited_limit=1,
        inherited_metric="units",
    )
    explicit = parse_sales_product_ranking_request(
        "Necesito el producto más vendido el día 25",
        sales_cutoff="2026-09-26",
    )

    assert today is not None and (today.periods[0].date_from, today.periods[0].date_to) == (
        "2026-09-26", "2026-09-26"
    )
    assert yesterday is not None
    assert (yesterday.periods[0].date_from, yesterday.periods[0].date_to) == (
        "2026-09-25", "2026-09-25"
    )
    assert explicit is not None and explicit.periods[0].date_from == "2026-09-25"


def test_sales_total_followup_does_not_inherit_a_product_ranking() -> None:
    unrelated_sales_question = parse_sales_product_ranking_request(
        "¿Cuántas ventas hubo ayer?",
        sales_cutoff="2026-09-26",
        inherited_limit=1,
        inherited_metric="units",
    )
    ranking_ellipsis = parse_sales_product_ranking_request(
        "¿Y del día de ayer?",
        sales_cutoff="2026-09-26",
        inherited_limit=1,
        inherited_metric="units",
    )
    product_count = parse_sales_product_ranking_request(
        "¿Cuántos productos se vendieron ayer?",
        sales_cutoff="2026-09-26",
        inherited_limit=1,
        inherited_metric="units",
    )

    assert unrelated_sales_question is None
    assert product_count is None
    assert ranking_ellipsis is not None
    assert (ranking_ellipsis.periods[0].date_from, ranking_ellipsis.periods[0].date_to) == (
        "2026-09-25", "2026-09-25"
    )


@pytest.mark.parametrize("date_text", ["2026-09-10", "10/09/2026", "10-09-2026"])
def test_numeric_date_only_is_a_valid_ranking_followup(date_text: str) -> None:
    request = parse_sales_product_ranking_request(
        date_text,
        sales_cutoff="2026-09-26",
        inherited_limit=1,
        inherited_metric="units",
    )

    assert request is not None
    assert (request.periods[0].date_from, request.periods[0].date_to) == (
        "2026-09-10", "2026-09-10"
    )


def test_product_rank_defaults_to_units_and_accepts_explicit_revenue() -> None:
    units = parse_sales_product_ranking_request(
        "¿Cuál producto se vendió más en agosto 2026?",
        sales_cutoff="2026-09-26",
    )
    revenue = parse_sales_product_ranking_request(
        "Top 3 productos por valor facturado en agosto 2026",
        sales_cutoff="2026-09-26",
    )

    assert units is not None and units.metric == "units"
    assert revenue is not None and revenue.metric == "revenue" and revenue.limit == 3


def test_custom_date_range_is_one_period_not_two_exact_day_rankings() -> None:
    request = parse_sales_product_ranking_request(
        "Top 3 productos por unidades desde 2026-08-01 hasta 2026-08-15",
        sales_cutoff="2026-09-26",
    )

    assert request is not None
    assert [(period.date_from, period.date_to) for period in request.periods] == [
        ("2026-08-01", "2026-08-15")
    ]


def test_purchase_audit_and_nonranking_questions_do_not_become_sales_rankings() -> None:
    assert parse_sales_product_ranking_request(
        "Analiza productos comprados en agosto según rotación",
        sales_cutoff="2026-09-26",
    ) is None
    assert parse_sales_product_ranking_request(
        "¿Cuánto vendimos en agosto?",
        sales_cutoff="2026-09-26",
    ) is None
