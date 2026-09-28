from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


@pytest.fixture
def sales_database(tmp_path: Path) -> Path:
    path = tmp_path / "sales-ranking.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas (
                business_date DATE, num_documento VARCHAR, cod_clase VARCHAR,
                estado_documento VARCHAR
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas_detalle (
                business_date DATE, num_documento VARCHAR, cod_clase VARCHAR,
                cod_producto VARCHAR, nombre_detalle VARCHAR, cantidad DOUBLE,
                total_detalle DOUBLE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR, nombre_producto VARCHAR, cod_medida VARCHAR,
                presentacion VARCHAR, snapshot_date DATE, fecha_actualizacion DATE
            )
            """
        )
        connection.executemany(
            "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("SKU-A", "Kombucha Maracuyá", "UND", "UNIDAD", "2026-09-26", "2026-09-26"),
                ("SKU-B", "Kombucha Lulo", "UND", "UNIDAD", "2026-09-26", "2026-09-26"),
                ("SKU-GRAM", "Café molido", "GR", "GRAMO", "2026-09-26", "2026-09-26"),
                ("SKU-NOUNIT", "Producto sin medida", None, None, "2026-09-26", "2026-09-26"),
                ("SKU-VAL", "Agua de Coco", "UND", "UNIDAD", "2026-09-26", "2026-09-26"),
                ("SKU-CANCEL", "Producto cancelado", "UND", "UNIDAD", "2026-09-26", "2026-09-26"),
                ("SKU-DUP", "Producto duplicado", "UND", "UNIDAD", "2026-09-26", "2026-09-26"),
            ],
        )
        connection.executemany(
            "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
            [
                ("2026-08-10", "AUG-1", "FV", "B"),
                ("2026-08-20", "AUG-2", "FV", "B"),
                ("2026-09-25", "SEP-DUP", "FV", "B"),
                ("2026-09-25", "SEP-DUP", "FV", "B"),
                ("2026-09-27", "SEP-LATEST-DUP", "FV", "B"),
                ("2026-09-27", "SEP-LATEST-DUP", "FV", "B"),
                ("2026-09-28", "", "FV", "B"),
                ("2026-09-26", "SEP-1", "FV", "B"),
                ("2026-09-26", "SEP-CANCEL", "FV", "A"),
            ],
        )
        connection.executemany(
            "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-08-10", "AUG-1", "FV", "SKU-A", "Kombucha Maracuyá", 5, 37500),
                ("2026-08-10", "AUG-1", "FV", "SKU-B", "Kombucha Lulo", 5, 37500),
                ("2026-08-10", "AUG-1", "FV", "SKU-GRAM", "Café molido", 300, 600),
                ("2026-08-10", "AUG-1", "FV", "SKU-NOUNIT", "Producto sin medida", 50, 100),
                ("2026-08-10", "AUG-1", "FV", "SKU-VAL", "Agua de Coco", 2, 57800),
                ("2026-08-20", "AUG-2", "FV", "SKU-A", "Kombucha Maracuyá", 0, 0),
                ("2026-09-25", "SEP-DUP", "FV", "SKU-DUP", "Producto duplicado", 10000, 1000000),
                ("2026-09-26", "SEP-1", "FV", "SKU-A", "Kombucha Maracuyá", 5, 37500),
                ("2026-09-26", "SEP-1", "FV", "SKU-B", "Kombucha Lulo", 5, 37500),
                ("2026-09-26", "SEP-1", "FV", "SKU-GRAM", "Café molido", 300, 600),
                ("2026-09-26", "SEP-1", "FV", "SKU-NOUNIT", "Producto sin medida", 50, 100),
                ("2026-09-26", "SEP-1", "FV", "SKU-VAL", "Agua de Coco", 2, 57800),
                (
                    "2026-09-26", "SEP-CANCEL", "FV", "SKU-CANCEL",
                    "Producto cancelado", 99999, 999999,
                ),
            ],
        )
    return path


def test_sales_ranking_is_month_specific_uses_units_and_keeps_ties(
    sales_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(sales_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(sales_database), tenant="motoshop")

    result = executor.get_top_productos_periodo(
        periods=[
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
            {"date_from": "2026-08-01", "date_to": "2026-08-31"},
        ],
        metric="units",
        limit=1,
    )

    winners = [
        {
            unit_group: sorted(
                product["sku"] for product in period["productos"]
                if product["unidad_grupo"] == unit_group
            )
            for unit_group in {product["unidad_grupo"] for product in period["productos"]}
        }
        for period in result["period_results"]
    ]
    assert [period["label"] for period in result["period_results"]] == [
        "septiembre 2026", "agosto 2026",
    ]
    assert winners == [
        {
            "GR": ["SKU-GRAM"], "UND": ["SKU-A", "SKU-B"],
            "UNKNOWN:SKU-NOUNIT": ["SKU-NOUNIT"],
        },
        {
            "GR": ["SKU-GRAM"], "UND": ["SKU-A", "SKU-B"],
            "UNKNOWN:SKU-NOUNIT": ["SKU-NOUNIT"],
        },
    ]
    assert result["status"] == "partial"
    assert result["sources"][0]["cutoff_at"] == "2026-09-26"
    assert result["period_results"][0]["status"] == "partial"
    assert result["period_results"][0]["available_through"] == "2026-09-26"
    assert result["period_results"][1]["status"] == "complete"
    assert "el resto del período no está verificado" in result["respuesta_fallback"]
    assert "unidades por medida" in result["respuesta_fallback"]
    assert "medidas distintas no se comparan" in result["respuesta_fallback"]
    assert "medida no informada · SKU SKU-NOUNIT" in result["respuesta_fallback"]
    assert "SKU-DUP" not in {product["sku"] for product in result["productos"]}
    assert "SKU-CANCEL" not in {product["sku"] for product in result["productos"]}
    connection.close()


def test_revenue_rank_and_exact_empty_day_do_not_fall_back_to_latest_day(
    sales_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(sales_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(sales_database), tenant="motoshop")

    highest_revenue = executor.get_top_productos_periodo(
        periods=[{"date_from": "2026-09-26", "date_to": "2026-09-26"}],
        metric="revenue",
        limit=1,
    )
    yesterday = executor.get_top_productos_periodo(
        periods=[{"date_from": "2026-09-25", "date_to": "2026-09-25"}],
        metric="units",
        limit=1,
    )
    mid_august = executor.get_top_productos_periodo(
        periods=[{"date_from": "2026-08-01", "date_to": "2026-08-15"}],
        metric="units",
        limit=1,
    )
    after_cutoff = executor.get_top_productos_periodo(
        periods=[{"date_from": "2026-09-27", "date_to": "2026-09-27"}],
        metric="units",
        limit=1,
    )

    assert [product["sku"] for product in highest_revenue["productos"]] == ["SKU-VAL"]
    assert highest_revenue["metric"] == "revenue"
    assert yesterday["status"] == "empty"
    assert yesterday["productos"] == []
    assert "no reemplacé el rango" in yesterday["respuesta_fallback"]
    assert {product["sku"] for product in mid_august["productos"]} == {
        "SKU-A", "SKU-B", "SKU-GRAM", "SKU-NOUNIT",
    }
    assert mid_august["period_results"][0]["date_to"].isoformat() == "2026-08-15"
    assert after_cutoff["status"] == "partial"
    assert after_cutoff["period_results"][0]["status"] == "unavailable"
    assert "No puedo verificar este período" in after_cutoff["respuesta_fallback"]
    assert "No encontré ventas entre 2026-09-27" not in after_cutoff["respuesta_fallback"]
    connection.close()


def test_qa_directly_routes_sales_ranking_and_returns_catalog_verified_product_links(
    sales_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.auth.tenant_dep import TenantContext
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
    from motoshop_api.llm.qa_chat import ConversationManager, QAChat
    from motoshop_api.llm.tools import TOOL_DEFINITIONS, ToolExecutor
    from motoshop_api.metrics import repo_duckdb

    connection = duckdb.connect(str(sales_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda _tenant: sales_database)
    monkeypatch.setattr(
        repo_duckdb,
        "get_shared_connection",
        lambda _path: duckdb.connect(str(sales_database), read_only=True),
    )
    context = TenantContext(
        "motoshop", "seller", "vendedor", True, frozenset({"sales", "inventory"})
    )
    executor = ToolExecutor(
        duckdb_path=str(sales_database), tenant="motoshop", tenant_context=context
    )
    assert executor.get_data_freshness()["por_tabla"]["silver_fact_ventas"] == "2026-09-26"

    class _NoProvider:
        def complete_with_tools(self, *args, **kwargs):
            raise AssertionError("The exact month ranking must not invoke the model")

    chat = QAChat(
        _NoProvider(),
        ConversationManager(),
        executor,
        [
            definition for definition in TOOL_DEFINITIONS
            if definition["function"]["name"] == "get_top_productos_periodo"
        ],
        tenant_id="motoshop",
        user_id="seller",
        repository=InMemoryConversationRepository(),
        tenant_context=context,
    )

    response = chat.chat("¿Cuál es el producto más vendido de septiembre y agosto?")
    assert executor.get_data_freshness()["por_tabla"]["silver_fact_ventas"] == "2026-09-26"
    today_response = chat.chat("¿Cuál es el producto más vendido hoy?")

    assert response["status"] == "partial"
    assert response["tools_used"] == ["get_top_productos_periodo"]
    assert {ref["entity_id"] for ref in response["entity_refs"]} == {
        "SKU-A", "SKU-B", "SKU-GRAM", "SKU-NOUNIT",
    }
    assert {ref["href"] for ref in response["entity_refs"]} == {
        "/dashboards/productos/SKU-A", "/dashboards/productos/SKU-B",
        "/dashboards/productos/SKU-GRAM", "/dashboards/productos/SKU-NOUNIT",
    }
    assert "### Septiembre 2026" in response["text"]
    assert "### Agosto 2026" in response["text"]
    assert "### 26/09/2026" in today_response["text"]
    assert "No encontré ventas" not in today_response["text"]
    connection.close()


@pytest.mark.parametrize(
    ("periods", "metric", "limit"),
    [
        ([{"date_from": "2026-09-26", "date_to": "2026-09-25"}], "units", 1),
        ([{"date_from": "2025-01-01", "date_to": "2026-01-02"}], "units", 1),
        ([{"date_from": "2026-08-01", "date_to": "2026-08-31"}] * 7, "units", 1),
        ([{"date_from": "2026-08-01", "date_to": "2026-08-31"}], "profit", 1),
        ([{"date_from": "2026-08-01", "date_to": "2026-08-31"}], "units", 21),
    ],
)
def test_sales_query_plan_rejects_invalid_ranges_and_metrics(
    sales_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    periods: list[dict[str, str]],
    metric: str,
    limit: int,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(sales_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(sales_database), tenant="motoshop")
    with pytest.raises(ValueError):
        executor.get_top_productos_periodo(periods=periods, metric=metric, limit=limit)
    connection.close()


def test_sales_rank_source_failure_is_not_replaced_with_latest_gold_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(":memory:")
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=":memory:", tenant="motoshop")

    result = executor.get_top_productos_periodo(
        periods=[{"date_from": "2026-09-25", "date_to": "2026-09-25"}],
        metric="units",
        limit=1,
    )

    assert result["status"] == "unavailable"
    assert result["productos"] == []
    assert "no pude verificar" in result["respuesta_fallback"].casefold()
    assert result["sources"][0]["status"] == "failed"
    connection.close()


def test_sales_ranking_caps_ties_and_global_results_without_claiming_later_month_is_empty(
    sales_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with duckdb.connect(str(sales_database)) as writer:
        tie_catalog = [
            (
                f"SKU-TIE-{index:02d}", f"Tie product {index}", "UND", "UNIDAD",
                "2026-09-26", "2026-09-26",
            )
            for index in range(30)
        ]
        unknown_catalog = [
            (
                f"SKU-UNKNOWN-{index:03d}", f"Unknown measure {index}", None, None,
                "2026-09-26", "2026-09-26",
            )
            for index in range(101)
        ]
        writer.executemany(
            "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?)",
            tie_catalog + unknown_catalog,
        )
        writer.executemany(
            "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "2026-09-26", "SEP-1", "FV", sku, name, 5, 37500,
                )
                for sku, name, *_ in tie_catalog
            ]
            + [
                (
                    "2026-09-26", "SEP-1", "FV", sku, name, 1, 100,
                )
                for sku, name, *_ in unknown_catalog
            ],
        )

    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(sales_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(sales_database), tenant="motoshop")

    result = executor.get_top_productos_periodo(
        periods=[
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
            {"date_from": "2026-08-01", "date_to": "2026-08-31"},
        ],
        metric="units",
        limit=1,
    )

    assert result["status"] == "partial"
    assert result["ranking_truncated"] is True
    assert result["ranking_result_count"] > result["ranking_tie_capped_count"] > 100
    assert len(result["productos"]) == 100
    assert result["period_results"][1]["productos"] == []
    assert "No puedo confirmar si hubo ventas en este período" in result["respuesta_fallback"]
    assert "No encontré ventas entre 2026-08-01" not in result["respuesta_fallback"]
    assert "Algunos empates superan 25 productos" in result["respuesta_fallback"]

    fully_covered = executor.get_top_productos_periodo(
        periods=[{"date_from": "2026-09-26", "date_to": "2026-09-26"}],
        metric="units",
        limit=1,
    )

    assert fully_covered["period_results"][0]["status"] == "complete"
    assert fully_covered["ranking_truncated"] is True
    assert fully_covered["status"] == "partial"
    connection.close()
