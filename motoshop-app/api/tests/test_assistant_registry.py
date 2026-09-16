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
        def fetchone(self):
            return (1,)

        def close(self):
            pass

    class Connection:
        def execute(self, sql, params):
            assert "gold_mart_inventario_actual" in sql
            assert params == ["SKU-1"]
            return Cursor()

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
    assert ref.href == "/inventario/productos/SKU-1"
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
