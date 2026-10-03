from __future__ import annotations

import duckdb
import pytest

from motoshop_api.llm import tools as tools_module
from motoshop_api.llm.tools import ToolExecutor


def test_catalog_tool_reuses_catalog_metrics_and_projects_only_answer_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = duckdb.connect(":memory:")
    captured: dict[str, object] = {}

    class FakeMetricsRepo:
        def __init__(self, db_path: str, tenant: str) -> None:
            captured["db_path"] = db_path
            captured["tenant"] = tenant

        def get_product_analytics(self, **kwargs: object) -> dict:
            captured["query"] = kwargs
            return {
                "window_days": 180,
                "page": 1,
                "page_size": 50,
                "total": 51,
                "items": [{
                    "cod_producto": "SKU-A",
                    "nombre": "A product",
                    "cantidad_actual": 0,
                    "unidades_win": 14,
                    "velocidad_mensual": 2.33,
                    "dias_stock": None,
                    "abc": "A",
                    "estado": "agotado",
                    "accion": "reabastecer",
                    "rank_rev": 1,
                    "valor_inventario": 0,
                    "costo_unit": 99,
                }],
            }

    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb.DuckDBMetricsRepo", FakeMetricsRepo
    )
    executor = ToolExecutor(duckdb_path=":memory:", tenant="masvital")
    executor.get_data_freshness = lambda: {
        "por_tabla": {
            "silver_fact_ventas": "2026-10-02",
            "silver_fact_compras": "2026-09-29",
            "silver_dim_producto": "2026-10-02",
        }
    }

    result = executor.get_productos_catalogo()

    assert captured["tenant"] == "masvital"
    assert captured["query"] == {
        "window_days": 180,
        "page": 1,
        "page_size": 50,
        "abc": "A",
        "sort": "revenue_win",
        "order": "desc",
        "q": None,
        "estado": None,
        "preset": None,
        "rotacion": None,
    }
    assert result["status"] == "complete"
    assert result["total"] == 51
    assert result["has_more"] is True
    assert result["next_page"] == 2
    assert result["productos"] == [{
        "cod_producto": "SKU-A",
        "nombre": "A product",
        "abc": "A",
        "stock_actual": 0.0,
        "unidades_win": 14.0,
        "velocidad_mensual": 2.33,
        "dias_stock": None,
        "estado": "agotado",
        "accion": "reabastecer",
        "rank_rev": 1,
    }]
    assert "valor_inventario" not in result["productos"][0]
    assert "costo_unit" not in result["productos"][0]
    connection.close()


def test_catalog_tool_passes_and_validates_requested_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = duckdb.connect(":memory:")
    captured: dict[str, object] = {}

    class FakeMetricsRepo:
        def __init__(self, db_path: str, tenant: str) -> None:
            pass

        def get_product_analytics(self, **kwargs: object) -> dict:
            captured["query"] = kwargs
            return {"total": 0, "items": [], "data_freshness": {}}

    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb.DuckDBMetricsRepo", FakeMetricsRepo
    )
    executor = ToolExecutor(duckdb_path=":memory:", tenant="motoshop")
    executor.get_data_freshness = lambda: {
        "sales_cutoff": "2026-10-02",
        "inventory_snapshot": "2026-10-02",
    }

    result = executor.get_productos_catalogo(estado="agotado,sin_stock")

    assert captured["query"]["estado"] == "agotado,sin_stock"
    assert "estado agotados o sin stock" in result["respuesta_fallback"]
    with pytest.raises(ValueError, match="estado"):
        executor.get_productos_catalogo(estado="agotado; DROP TABLE productos")
    connection.close()


@pytest.mark.parametrize(
    ("page", "page_size", "window_days", "abc"),
    [(0, 50, 180, "A"), (1, 51, 180, "A"), (1, 50, 29, "A"), (1, 50, 180, "D")],
)
def test_catalog_tool_rejects_invalid_filters_and_unbounded_pagination(
    monkeypatch: pytest.MonkeyPatch,
    page: int,
    page_size: int,
    window_days: int,
    abc: str,
) -> None:
    connection = duckdb.connect(":memory:")
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=":memory:", tenant="motoshop")

    with pytest.raises(ValueError):
        executor.get_productos_catalogo(
            abc=abc, window_days=window_days, page=page, page_size=page_size
        )
    connection.close()


def test_catalog_tool_preserves_repository_source_cutoffs_and_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = duckdb.connect(":memory:")

    class FakeMetricsRepo:
        def __init__(self, db_path: str, tenant: str) -> None:
            self.tenant = tenant

        def get_product_analytics(self, **_kwargs: object) -> dict:
            return {
                "window_days": 180,
                "page": 1,
                "page_size": 50,
                "total": 1,
                "items": [{
                    "cod_producto": "SKU-A",
                    "nombre": "A product",
                    "cantidad_actual": 5,
                    "unidades_win": 14,
                    "velocidad_mensual": 2.33,
                    "dias_stock": 64,
                    "abc": "A",
                    "estado": "saludable",
                    "accion": "ok",
                    "rank_rev": 1,
                }],
                "data_freshness": {
                    "sales_cutoff": "2026-10-02",
                    "purchase_cutoff": "2026-09-29",
                    "inventory_snapshot": "2026-10-02",
                    "snapshot_generation": 7,
                    "stock_source": "catalog_snapshot",
                },
            }

    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb.DuckDBMetricsRepo", FakeMetricsRepo
    )
    executor = ToolExecutor(duckdb_path=":memory:", tenant="masvital")
    executor.get_data_freshness = lambda: pytest.fail(
        "Use the catalog result's matching snapshot metadata instead of refetching it"
    )

    result = executor.get_productos_catalogo()

    assert result["status"] == "complete"
    assert result["data_freshness"] == {
        "sales_cutoff": "2026-10-02",
        "purchase_cutoff": "2026-09-29",
        "inventory_snapshot": "2026-10-02",
        "snapshot_generation": 7,
        "stock_source": "catalog_snapshot",
    }
    assert "ventas 2026-10-02" in result["respuesta_fallback"]
    connection.close()


@pytest.mark.parametrize(
    ("stock_source", "inventory_snapshot", "purchase_cutoff", "expected_status"),
    [
        ("purchases_minus_sales_estimate", None, "2026-09-29", "empty"),
        ("catalog_snapshot", None, "2026-09-29", "unavailable"),
    ],
)
def test_catalog_tool_checks_cutoffs_for_the_actual_stock_source(
    monkeypatch: pytest.MonkeyPatch,
    stock_source: str,
    inventory_snapshot: str | None,
    purchase_cutoff: str,
    expected_status: str,
) -> None:
    connection = duckdb.connect(":memory:")

    class FakeMetricsRepo:
        def __init__(self, db_path: str, tenant: str) -> None:
            pass

        def get_product_analytics(self, **_kwargs: object) -> dict:
            return {
                "total": 0,
                "items": [],
                "data_freshness": {
                    "sales_cutoff": "2026-10-02",
                    "purchase_cutoff": purchase_cutoff,
                    "inventory_snapshot": inventory_snapshot,
                    "snapshot_generation": 3,
                    "stock_source": stock_source,
                },
            }

    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb.DuckDBMetricsRepo", FakeMetricsRepo
    )
    result = ToolExecutor(duckdb_path=":memory:", tenant="motoshop").get_productos_catalogo()

    assert result["status"] == expected_status
    connection.close()
