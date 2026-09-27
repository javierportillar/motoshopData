from __future__ import annotations

import pytest

from motoshop_api.auth.tenant_dep import TenantContext
from motoshop_api.llm.catalog import get_query_spec
from motoshop_api.llm.registry import GovernedRegistry, resolve_entity_ref
from motoshop_api.llm.sources import DuckDBSourceAdapter, SourceUnavailable, SupabaseSourceAdapter


def _context(*domains: str) -> TenantContext:
    return TenantContext("motoshop", "ana", "vendedor", True, frozenset(domains or ("sales",)))


def test_registry_allowlist_and_disabled_domain() -> None:
    registry = GovernedRegistry(_context("sales", "inventory"))
    assert "purchase_plans" not in registry.names() and registry.get("sales") is not None
    with pytest.raises(PermissionError):
        registry.require("expenses")


def test_entity_ref_is_server_resolved_and_tenant_authorized(monkeypatch) -> None:
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def close(self):
            pass

    class Connection:
        def execute(self, sql, params):
            assert "FROM silver_dim_producto" in sql
            if "COUNT(DISTINCT cod_producto)" in sql:
                return Cursor([(params[0], 1)])
            if "COALESCE(existencia, 0) DESC" in sql:
                assert "snapshot_date = (SELECT MAX(snapshot_date)" in sql
            return Cursor([(params[0], f"Canonical {params[0]}")])

    class FakeProxy:
        def __init__(self):
            self._conn = Connection()

        def execute(self, query, parameters=None):
            return self._conn.execute(query, parameters)

        def close(self):
            pass

    from motoshop_api.metrics import repo_duckdb

    shared_proxy = FakeProxy()
    monkeypatch.setattr(repo_duckdb, "get_shared_connection", lambda _path: shared_proxy)
    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda tenant: f"/fake/{tenant}.duckdb")

    ref = resolve_entity_ref(
        _context("inventory"),
        entity_type="product",
        entity_id="SKU-1",
        label="Filtro",
        domain="inventory",
        route_key="product",
    )
    assert ref.href == "/dashboards/productos/SKU-1"
    assert ref.label == "Canonical SKU-1"
    encoded_ref = resolve_entity_ref(
        _context("inventory"),
        entity_type="product",
        entity_id="SKU/1",
        label="Untrusted name",
        domain="inventory",
        route_key="product",
    )
    assert encoded_ref.href == "/dashboards/productos/SKU%2F1"
    assert encoded_ref.label == "Canonical SKU/1"
    masvital_ref = resolve_entity_ref(
        TenantContext("masvital", "ana", "vendedor", True, frozenset({"inventory"})),
        entity_type="product",
        entity_id="SKU-1",
        label="Untrusted name",
        domain="inventory",
        route_key="product",
    )
    assert masvital_ref.href == "/dashboards/productos/SKU-1"
    assert masvital_ref.label == "Canonical SKU-1"
    with pytest.raises(PermissionError):
        resolve_entity_ref(
            _context("sales"),
            entity_type="product",
            entity_id="SKU-1",
            label="Filtro",
            domain="inventory",
            route_key="product",
        )
    with pytest.raises(ValueError):
        resolve_entity_ref(
            _context("inventory"),
            entity_type="product",
            entity_id="https://x",
            label="Filtro",
            domain="inventory",
            route_key="product",
        )


def test_duckdb_adapter_binds_tenant_and_limits_rows() -> None:
    class Cursor:
        description = [("total",)]

        def execute(self, sql: str, params: list[object]) -> Cursor:
            self.called = (sql, params)
            return self

        def fetchmany(self, size: int) -> list[tuple[int]]:
            self.size = size
            return [(4,)]

        def close(self) -> None:
            pass

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    rows, evidence = DuckDBSourceAdapter(_context("sales"), connection=Connection()).read(
        "sales", {}
    )
    assert rows == [{"total": 4}] and evidence.status == "used"
    assert "?" in get_query_spec("sales").sql


def test_product_reference_marks_duplicate_catalog_names_as_ambiguous(monkeypatch) -> None:
    from motoshop_api.metrics import repo_duckdb

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def close(self):
            pass

    class Connection:
        def execute(self, sql, params):
            if "COUNT(DISTINCT cod_producto)" in sql:
                return Cursor([(params[0], 2)])
            return Cursor([("SKU-1", "Shared product name")])

    monkeypatch.setattr(repo_duckdb, "get_shared_connection", lambda _path: Connection())
    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda _tenant: "/fake/motoshop.duckdb")

    ref = resolve_entity_ref(
        _context("inventory"),
        entity_type="product",
        entity_id="SKU-1",
        label="Untrusted input label",
        domain="inventory",
        route_key="product",
    )

    assert ref.label == "Shared product name"
    assert ref.label_is_unique is False


def test_numeric_product_mentions_require_name_context_to_avoid_linking_amounts() -> None:
    from motoshop_api.llm.contracts import EntityRef
    from motoshop_api.llm.registry import product_ref_mentioned

    ref = EntityRef(
        entity_type="product",
        entity_id="123456",
        label="Product alpha",
        domain="inventory",
        href="/dashboards/productos/123456",
    )

    assert not product_ref_mentioned("La factura sumó $123456 COP.", ref)
    assert not product_ref_mentioned(
        "Total: $123456 [nota](/dashboards/productos/Product-alpha)", ref
    )
    assert product_ref_mentioned("123456 Product alpha: stock bajo.", ref)


def test_historical_product_link_resolution_degrades_if_duckdb_is_unavailable(monkeypatch) -> None:
    from motoshop_api.llm.registry import resolve_product_refs_in_text

    from motoshop_api.metrics import repo_duckdb

    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda _tenant: "/offline/catalog.duckdb")

    def unavailable(_path):
        raise OSError("DuckDB snapshot unavailable")

    monkeypatch.setattr(repo_duckdb, "get_shared_connection", unavailable)
    context = TenantContext("motoshop", "ana", "vendedor", True, frozenset({"inventory"}))

    assert resolve_product_refs_in_text(context, "BONNAT001 SALSAS MRS TASTE") == []


@pytest.mark.parametrize(("limit", "expected_count"), [(3, 3), (30, 30), (500, 50), (0, 0)])
def test_historical_product_link_resolution_caps_total_candidate_queries(
    monkeypatch, limit: int, expected_count: int
) -> None:
    from motoshop_api.llm import registry

    context = TenantContext("motoshop", "ana", "vendedor", True, frozenset({"inventory"}))
    calls = []

    def capture_resolution(_context, codes, *, batch_size):
        calls.append((codes, batch_size))
        return []

    monkeypatch.setattr(registry, "resolve_product_refs", capture_resolution)
    text = " ".join(f"SKU-{index:03}" for index in range(80))

    assert registry.resolve_product_refs_in_text(context, text, limit=limit) == []
    assert len(calls) == (1 if expected_count else 0)
    if expected_count:
        assert len(calls[0][0]) == expected_count
        assert calls[0][1] == 50


def test_sources_reject_failures_and_untrusted_supabase_filters() -> None:
    class Broken:
        def cursor(self) -> None:
            raise OSError("credentials=secret")

    with pytest.raises(SourceUnavailable, match="disponible"):
        DuckDBSourceAdapter(_context("sales"), connection=Broken()).read("sales", {})

    class Response:
        def json(self) -> list[dict[str, object]]:
            return [{"token": "secret"}]

    class Client:
        def get(self, path: str, *, params: dict[str, str]) -> Response:
            return Response()

    adapter = SupabaseSourceAdapter(_context("expenses"), client=Client())
    rows, _ = adapter.read("expenses", {"mes": "eq.2026-09"})
    assert rows == [{"token": "[REDACTED]"}]
    with pytest.raises(ValueError):
        adapter.read("expenses", {"mes": "eq.2026-09),or=(tenant.eq.other"})
