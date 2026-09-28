from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from motoshop_api.llm.purchase_queries import (
    parse_purchase_period_request,
    parse_purchase_ranking_request,
)


@pytest.mark.parametrize(
    ("month_name", "month_number", "last_day"),
    [
        ("enero", "01", "31"), ("febrero", "02", "28"), ("marzo", "03", "31"),
        ("abril", "04", "30"), ("mayo", "05", "31"), ("junio", "06", "30"),
        ("julio", "07", "31"), ("agosto", "08", "31"), ("septiembre", "09", "30"),
        ("octubre", "10", "31"), ("noviembre", "11", "30"), ("diciembre", "12", "31"),
    ],
)
def test_purchase_ranking_resolves_any_named_calendar_month(
    month_name: str, month_number: str, last_day: str
) -> None:
    request = parse_purchase_ranking_request(
        f"Top 3 compras más grandes de {month_name} 2025",
        purchase_cutoff="2026-09-26",
    )

    assert request is not None
    assert [(period.date_from, period.date_to) for period in request.periods] == [
        (f"2025-{month_number}-01", f"2025-{month_number}-{last_day}")
    ]


def test_supplier_filter_survives_top_purchase_query_parsing() -> None:
    request = parse_purchase_ranking_request(
        "¿Cuál es la compra más grande hecha hacia MILIS en agosto?",
        purchase_cutoff="2026-09-26",
    )

    assert request is not None
    assert request.supplier_query == "milis"
    assert request.tool_arguments()["supplier_query"] == "milis"


@pytest.mark.parametrize("requested_count", ["30", "100"])
def test_purchase_ranking_cap_is_reported_when_request_exceeds_tool_limit(
    requested_count: str,
) -> None:
    request = parse_purchase_ranking_request(
        f"Top {requested_count} compras más grandes de agosto 2026",
        purchase_cutoff="2026-09-26",
    )

    assert request is not None
    assert request.limit == 20
    assert request.limit_capped is True
    assert request.tool_arguments()["limit_capped"] is True


def test_month_purchase_questions_select_summary_or_full_invoice_list() -> None:
    listing = parse_purchase_period_request(
        "¿Cuáles son las compras realizadas el mes de agosto?",
        purchase_cutoff="2026-09-26",
    )
    summary = parse_purchase_period_request(
        "¿El mes de agosto tiene compras?",
        purchase_cutoff="2026-09-26",
    )

    assert listing is not None and listing.view == "list" and listing.limit == 50
    assert listing.periods[0].date_from == "2026-08-01"
    assert summary is not None and summary.view == "summary"


def test_detail_followup_inherits_period_but_not_a_guessed_supplier() -> None:
    previous = parse_purchase_period_request(
        "¿Cuáles son las compras realizadas el mes de agosto?",
        purchase_cutoff="2026-09-26",
    )
    assert previous is not None
    detail = parse_purchase_period_request(
        "Detalla esas compras, dime el proveedor y el total",
        purchase_cutoff="2026-09-26",
        inherited_periods=previous.periods,
    )

    assert detail is not None and detail.view == "list"
    assert detail.periods == previous.periods
    assert detail.supplier_query is None


def test_purchase_audit_does_not_become_invoice_list_or_top() -> None:
    message = "Analiza las compras de agosto según rotación y ventas"

    assert parse_purchase_period_request(message, purchase_cutoff="2026-09-26") is None
    assert parse_purchase_ranking_request(message, purchase_cutoff="2026-09-26") is None


@pytest.fixture
def purchase_query_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, duckdb.DuckDBPyConnection]:
    path = tmp_path / "purchase-periods.duckdb"
    with duckdb.connect(str(path)) as writer:
        writer.execute(
            """
            CREATE TABLE silver_fact_compras (
                business_date DATE, num_documento VARCHAR, cod_clase VARCHAR,
                nit_proveedor VARCHAR, nombre_proveedor VARCHAR, total_factura DOUBLE,
                estado_documento VARCHAR
            )
            """
        )
        writer.executemany(
            "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-08-15", "AUG-1", "FC", "900111111-1", "Supplier A", 500, "B"),
                ("2026-09-10", "SEP-1", "FC", "900111111-1", "Supplier A", 1000, "B"),
                ("2026-09-12", "DUP", "FC", "900111111-1", "Supplier A", 2000, "B"),
                ("2026-09-12", "DUP", "FC", "900111111-1", "Supplier A", 2000, "B"),
                ("2026-09-13", "", "FC", "900111111-1", "Supplier A", 3000, "B"),
                ("2026-09-14", "CANCEL", "FC", "900111111-1", "Supplier A", 4000, "A"),
            ],
        )

    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(path))
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(path), tenant="motoshop")
    yield executor, connection
    connection.close()


def test_purchase_period_reports_partial_and_unavailable_ranges_without_claiming_no_purchases(
    purchase_query_executor: tuple[object, duckdb.DuckDBPyConnection],
) -> None:
    executor, _connection = purchase_query_executor

    freshness = executor.get_data_freshness()
    partial_month = executor.get_top_compras_periodos(
        periods=[{"date_from": "2026-09-01", "date_to": "2026-09-30"}],
        limit=3,
    )
    summary = executor.get_compras_periodo(
        periods=[{"date_from": "2026-09-01", "date_to": "2026-09-30"}],
        view="summary",
    )
    capped_top = executor.get_top_compras_periodos(
        periods=[{"date_from": "2026-08-01", "date_to": "2026-08-31"}],
        limit=20,
        limit_capped=True,
    )
    after_cutoff = executor.get_compras_periodo(
        periods=[{"date_from": "2026-10-01", "date_to": "2026-10-31"}],
        view="summary",
    )

    assert freshness["por_tabla"]["silver_fact_compras"] == "2026-09-10"
    assert partial_month["status"] == "partial"
    assert partial_month["period_results"][0]["status"] == "partial"
    assert partial_month["period_results"][0]["available_through"] == "2026-09-10"
    assert [purchase["num_documento"] for purchase in partial_month["compras"]] == ["SEP-1"]
    assert "el resto del período no está verificado" in partial_month["respuesta_fallback"]
    assert summary["status"] == "partial"
    assert "los días posteriores no están verificados" in summary["respuesta_fallback"]
    assert capped_top["limit_capped"] is True
    assert "superaba el límite permitido" in capped_top["respuesta_fallback"]
    assert after_cutoff["status"] == "partial"
    assert after_cutoff["period_results"][0]["status"] == "unavailable"
    assert "no puedo verificar este período" in after_cutoff["respuesta_fallback"].casefold()
    assert "no encontré compras válidas" not in after_cutoff["respuesta_fallback"].casefold()


def test_purchase_queries_without_a_valid_cutoff_return_unavailable_not_empty(
    purchase_query_executor: tuple[object, duckdb.DuckDBPyConnection],
) -> None:
    executor, connection = purchase_query_executor
    connection.execute("DELETE FROM silver_fact_compras WHERE estado_documento != 'A'")

    result = executor.get_top_compras_periodos(
        periods=[{"date_from": "2026-08-01", "date_to": "2026-08-31"}],
        limit=1,
    )

    assert result["status"] == "unavailable"
    assert result["period_results"][0]["status"] == "unavailable"
    assert "No puedo verificar este período" in result["respuesta_fallback"]
