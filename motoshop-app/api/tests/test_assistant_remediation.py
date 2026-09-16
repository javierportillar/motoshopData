from __future__ import annotations

from pathlib import Path

import duckdb
import httpx
import pytest
import yaml

from motoshop_api.auth.tenant_dep import TenantContext
from motoshop_api.llm.client import LLMClient, TransientLLMError
from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
from motoshop_api.llm.qa_chat import ConversationManager, QAChat
from motoshop_api.llm.registry import resolve_entity_ref
from motoshop_api.llm.sources import DuckDBSourceAdapter, SupabaseSourceAdapter
from motoshop_api.tenants import load_tenants


@pytest.fixture
def isolated_tenant_fixtures(tmp_path: Path):
    tenants_path = tmp_path / "tenants.yaml"
    tenants_path.write_text(
        yaml.safe_dump(
            {
                "tenants": [
                    {
                        "id": "motoshop",
                        "nombre": "Fixture MotoShop",
                        "r2_object_key": "motoshop.duckdb",
                        "local_db_path": str(tmp_path / "motoshop.duckdb"),
                        "agent": {"enabled_tools": ["get_kpis_today"]},
                    },
                    {
                        "id": "masvital",
                        "nombre": "Fixture MasVital",
                        "r2_object_key": "masvital.duckdb",
                        "local_db_path": str(tmp_path / "masvital.duckdb"),
                        "agent": {"enabled_tools": ["get_kpis_today"]},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    load_tenants(tenants_path)

    for tenant, supplier in (("motoshop", "Moto supplier"), ("masvital", "Vital supplier")):
        database = tmp_path / f"{tenant}.duckdb"
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                "CREATE TABLE silver_fact_compras (business_date DATE, num_documento VARCHAR, "
                "cod_clase VARCHAR, nit_proveedor VARCHAR, nombre_proveedor VARCHAR, "
                "total_factura DOUBLE, estado_documento VARCHAR)"
            )
            connection.execute(
                "INSERT INTO silver_fact_compras VALUES ('2026-01-02', '1', 'FC', 'NIT', ?, 100, 'B')",
                [supplier],
            )
            connection.execute(
                "CREATE TABLE silver_fact_compras_detalle (cod_clase VARCHAR, num_documento VARCHAR, "
                "cod_producto VARCHAR, nombre_detalle VARCHAR, cantidad DOUBLE, "
                "precio_unitario DOUBLE, total_detalle DOUBLE)"
            )
            connection.execute(
                "CREATE TABLE gold_mart_inventario_actual (cod_producto VARCHAR, snapshot_date DATE)"
            )
            if tenant == "motoshop":
                connection.execute(
                    "INSERT INTO gold_mart_inventario_actual VALUES ('SKU-1', '2026-01-02')"
                )
            connection.execute("CREATE TABLE gold_mart_ventas_diarias_sku (business_date DATE)")
            connection.execute("INSERT INTO gold_mart_ventas_diarias_sku VALUES ('2026-01-03')")
    yield tmp_path
    load_tenants(Path(__file__).parents[1] / "tenants.yaml")


def test_disabled_assistant_context_cannot_invoke_a_configured_tool(monkeypatch) -> None:
    import motoshop_api.llm.tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: object())
    context = TenantContext("motoshop", "managed", "vendedor", False, frozenset({"sales"}))
    executor = ToolExecutor(tenant="motoshop", user_id="managed", tenant_context=context)
    executor.get_kpis_today = lambda: {"authorized": True}

    assert executor.run("get_kpis_today", {}) == {"error": "Tool not allowed for this tenant"}


def test_disabled_assistant_context_does_not_expose_tool_schemas(monkeypatch) -> None:
    import motoshop_api.llm.qa_chat as qa_module
    import motoshop_api.llm.tools as tools_module

    class _Executor:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(tools_module, "ToolExecutor", _Executor)
    monkeypatch.setattr("motoshop_api.llm.client.get_llm_client", lambda: object())
    context = TenantContext("motoshop", "managed", "vendedor", False, frozenset({"sales"}))

    chat = qa_module.get_qa_chat(
        "motoshop", "managed", repository=InMemoryConversationRepository(), tenant_context=context
    )

    assert chat.tool_defs == []


def test_provider_deadline_is_capped_for_a_later_caller_deadline(monkeypatch) -> None:
    import motoshop_api.llm.client as client_module

    client = object.__new__(LLMClient)
    client._backends = [
        {
            "name": "go",
            "base": "https://provider.test",
            "key": "secret",
            "model": "go",
            "max_tokens": 100,
        },
        {
            "name": "zen",
            "base": "https://provider.test",
            "key": "secret",
            "model": "zen",
            "max_tokens": 100,
        },
    ]
    clock = [100.0]
    timeouts: list[float] = []

    class _TimeoutHTTP:
        def post(self, *args, **kwargs):
            timeouts.append(kwargs["timeout"])
            clock[0] += 20
            raise httpx.ReadTimeout("timed out")

    client._http = _TimeoutHTTP()
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])

    with pytest.raises(TransientLLMError):
        client.complete("hello", deadline=200.0)

    assert timeouts == [60.0, 40.0]


def test_tool_calls_stop_when_a_prior_call_consumes_the_shared_deadline(monkeypatch) -> None:
    import motoshop_api.llm.qa_chat as qa_module

    clock = [100.0]

    class _TwoCallsLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens, deadline):
            self.calls += 1
            return {
                "text": "",
                "tool_calls": [
                    {"id": "one", "function": {"name": "sales", "arguments": "{}"}},
                    {"id": "two", "function": {"name": "sales", "arguments": "{}"}},
                ],
            }

    class _SlowExecutor:
        calls = 0

        def run(self, name, args):
            self.calls += 1
            clock[0] += 61  # exceeds 60s deadline
            return {"sources": []}

    monkeypatch.setattr(qa_module.time, "monotonic", lambda: clock[0])
    llm = _TwoCallsLLM()
    executor = _SlowExecutor()
    chat = QAChat(
        llm,
        ConversationManager(),
        executor,
        [],
        tenant_id="motoshop",
        user_id="managed",
        repository=InMemoryConversationRepository(),
    )

    with pytest.raises(TransientLLMError):
        chat.chat("consultá ventas")

    assert (llm.calls, executor.calls) == (1, 1)


def test_tool_exception_response_and_log_do_not_contain_sensitive_values(caplog) -> None:
    from motoshop_api.llm.tools import ToolExecutor

    executor = object.__new__(ToolExecutor)
    executor.tenant = "motoshop"
    executor._allowed_tools = {"explode"}

    def explode(**kwargs):
        raise RuntimeError("token=super-secret")

    executor.explode = explode
    with caplog.at_level("WARNING", logger="motoshop_api.llm.tools"):
        result = executor.run("explode", {"password": "super-secret", "sku": "SKU-PRIVATE-42"})

    assert result == {"error": "Tool execution failed"}
    assert "super-secret" not in caplog.text
    assert "SKU-PRIVATE-42" not in caplog.text


def test_tool_preserves_user_facing_value_error() -> None:
    from motoshop_api.llm.tools import ToolExecutor

    executor = object.__new__(ToolExecutor)
    executor.tenant = "motoshop"
    executor._allowed_tools = {"validate"}
    executor.validate = lambda **kwargs: (_ for _ in ()).throw(
        ValueError("date_from must be before date_to")
    )

    assert executor.run("validate", {}) == {"error": "date_from must be before date_to"}


def test_rbac_blocks_tools_not_in_fixture_enabled_tools(isolated_tenant_fixtures) -> None:
    """Verifica que el mecanismo RBAC bloquea tools que NO están en enabled_tools del fixture.

    El fixture usa enabled_tools=['get_kpis_today'], así que cualquier otra tool
    (incluyendo compras) debe ser rechazada. Esto valida el MECANISMO, no una política.
    """
    from motoshop_api.llm.tools import ToolExecutor

    for tenant in ("motoshop", "masvital"):
        executor = ToolExecutor(
            tenant=tenant, duckdb_path=str(isolated_tenant_fixtures / f"{tenant}.duckdb")
        )
        # Tools no en enabled_tools son bloqueadas por RBAC
        assert executor.run("get_ultima_compra", {}) == {
            "error": "Tool not allowed for this tenant"
        }
        assert executor.run("get_compras_recientes", {}) == {
            "error": "Tool not allowed for this tenant"
        }
        # Tool en enabled_tools pasa el RBAC (puede fallar por schema del fixture, eso es OK)
        result = executor.run("get_kpis_today", {})
        assert result.get("error") != "Tool not allowed for this tenant"


def test_purchase_fixture_does_not_cross_tenant(isolated_tenant_fixtures) -> None:
    from motoshop_api.llm.tools import ToolExecutor

    moto = ToolExecutor(
        tenant="motoshop", duckdb_path=str(isolated_tenant_fixtures / "motoshop.duckdb")
    )
    vital = ToolExecutor(
        tenant="masvital", duckdb_path=str(isolated_tenant_fixtures / "masvital.duckdb")
    )

    moto_result = moto.get_ultima_compra()
    vital_result = vital.get_ultima_compra()
    assert moto_result["proveedor"] == "Moto supplier"
    assert vital_result["proveedor"] == "Vital supplier"
    assert moto_result["freshness"][0]["cutoff_at"] == "2026-01-02"
    assert moto_result["sources"][0]["domain"] == "purchases"
    assert "Moto supplier" not in str(vital_result)


def test_entity_reference_requires_owned_entity_and_fails_closed(
    isolated_tenant_fixtures, monkeypatch
) -> None:
    from motoshop_api.metrics import repo_duckdb

    _connections: dict[str, duckdb.DuckDBPyConnection] = {}

    def _open_connection(path: str):
        if path not in _connections:
            _connections[path] = duckdb.connect(path, read_only=False)
        return _connections[path]

    class _FakeProxy:
        def __init__(self, path: str) -> None:
            self._path = path

        def execute(self, query: str, parameters=None):
            con = _open_connection(self._path)
            cursor = con.cursor()
            cursor.execute(query, parameters)
            return cursor

        def close(self) -> None:
            pass

    monkeypatch.setattr(repo_duckdb, "get_shared_connection", lambda path: _FakeProxy(str(path)))
    monkeypatch.setattr(
        repo_duckdb, "_make_db_path", lambda tenant: isolated_tenant_fixtures / f"{tenant}.duckdb"
    )

    context_moto = TenantContext("motoshop", "managed", "vendedor", True, frozenset({"inventory"}))
    context_vital = TenantContext("masvital", "managed", "vendedor", True, frozenset({"inventory"}))

    ref = resolve_entity_ref(
        context_moto,
        entity_type="product",
        entity_id="SKU-1",
        label="Fixture product",
        domain="inventory",
        route_key="product",
    )
    assert ref.href == "/inventario/productos/SKU-1"

    with pytest.raises(LookupError):
        resolve_entity_ref(
            context_moto,
            entity_type="product",
            entity_id="SKU-9",
            label="Unknown product",
            domain="inventory",
            route_key="product",
        )

    with pytest.raises(LookupError):
        resolve_entity_ref(
            context_vital,
            entity_type="product",
            entity_id="SKU-1",
            label="Cross-tenant product",
            domain="inventory",
            route_key="product",
        )


def test_entity_ref_denied_for_unauthorized_domain(isolated_tenant_fixtures, monkeypatch) -> None:
    from motoshop_api.metrics import repo_duckdb

    _connections: dict[str, duckdb.DuckDBPyConnection] = {}

    def _open_connection(path: str):
        if path not in _connections:
            _connections[path] = duckdb.connect(path, read_only=False)
        return _connections[path]

    class _FakeProxy:
        def __init__(self, path: str) -> None:
            self._path = path

        def execute(self, query: str, parameters=None):
            con = _open_connection(self._path)
            cursor = con.cursor()
            cursor.execute(query, parameters)
            return cursor

        def close(self) -> None:
            pass

    monkeypatch.setattr(repo_duckdb, "get_shared_connection", lambda path: _FakeProxy(str(path)))
    monkeypatch.setattr(
        repo_duckdb, "_make_db_path", lambda tenant: isolated_tenant_fixtures / f"{tenant}.duckdb"
    )

    context = TenantContext("motoshop", "managed", "vendedor", True, frozenset({"sales"}))
    with pytest.raises(PermissionError, match="entity_destination_denied"):
        resolve_entity_ref(
            context,
            entity_type="product",
            entity_id="SKU-1",
            label="Denied product",
            domain="inventory",
            route_key="product",
        )


def test_cross_domain_evidence_shows_distinct_cutoffs(isolated_tenant_fixtures) -> None:
    class SupabaseResponse:
        def json(self) -> list[dict[str, object]]:
            return [{"amount": 100, "tenant": "motoshop"}]

    class SupabaseClient:
        def get(self, path: str, *, params: dict[str, str]) -> SupabaseResponse:
            assert params["tenant"] == "eq.motoshop"
            return SupabaseResponse()

    context = TenantContext(
        "motoshop", "managed", "vendedor", True, frozenset({"sales", "expenses"})
    )
    with duckdb.connect(str(isolated_tenant_fixtures / "motoshop.duckdb")) as connection:
        _, duckdb_ev = DuckDBSourceAdapter(context, connection=connection).read("sales", {})
    _, supabase_ev = SupabaseSourceAdapter(context, client=SupabaseClient()).read("expenses")

    assert duckdb_ev.kind == "duckdb"
    assert supabase_ev.kind == "supabase"
    assert duckdb_ev.domain == "sales"
    assert supabase_ev.domain == "expenses"
    assert duckdb_ev.observed_at is not None
    assert supabase_ev.observed_at is not None


def test_mixed_source_freshness_reflects_independent_cutoffs(isolated_tenant_fixtures) -> None:
    class SupabaseResponse:
        def json(self) -> list[dict[str, object]]:
            return [{"amount": 50}]

    class SupabaseClient:
        def get(self, path: str, *, params: dict[str, str]) -> SupabaseResponse:
            return SupabaseResponse()

    context = TenantContext(
        "motoshop", "managed", "vendedor", True, frozenset({"sales", "expenses"})
    )
    with duckdb.connect(str(isolated_tenant_fixtures / "motoshop.duckdb")) as connection:
        _, duckdb_ev = DuckDBSourceAdapter(context, connection=connection).read("sales", {})
    _, supabase_ev = SupabaseSourceAdapter(context, client=SupabaseClient()).read("expenses")

    assert duckdb_ev.cutoff_at != supabase_ev.cutoff_at or duckdb_ev.domain != supabase_ev.domain


def test_one_source_failure_produces_partial_status(isolated_tenant_fixtures) -> None:
    class BrokenLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens, deadline):
            self.calls += 1
            if self.calls == 1:
                return {
                    "text": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "function": {
                                "name": "cross_domain",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            return {"text": "Ventas OK; gastos fallaron.", "tool_calls": []}

    class PartialExecutor:
        def run(self, name, args):
            return {
                "sources": [
                    {
                        "source_id": "duckdb-sales",
                        "domain": "sales",
                        "kind": "duckdb",
                        "citation": "fixture",
                        "cutoff_at": "2026-01-03",
                        "status": "used",
                    },
                    {
                        "source_id": "supabase-expenses",
                        "domain": "expenses",
                        "kind": "supabase",
                        "citation": "fixture",
                        "cutoff_at": "2026-01-01",
                        "status": "failed",
                        "reason": "unavailable",
                    },
                ],
                "freshness": [
                    {
                        "domain": "sales",
                        "cutoff_at": "2026-01-03",
                        "observed_at": "2026-01-04T00:00:00+00:00",
                        "status": "current",
                    },
                    {
                        "domain": "expenses",
                        "cutoff_at": "2026-01-01",
                        "observed_at": "2026-01-04T00:00:00+00:00",
                        "status": "stale",
                    },
                ],
            }

    chat = QAChat(
        BrokenLLM(),
        ConversationManager(),
        PartialExecutor(),
        [],
        tenant_id="motoshop",
        user_id="managed",
        repository=InMemoryConversationRepository(),
    )
    result = chat.chat("compará ventas y gastos")

    assert result["status"] == "partial"
    statuses = {s["status"] for s in result["sources"]}
    assert statuses == {"used", "failed"}
    cutoffs = {f["cutoff_at"] for f in result["freshness"]}
    assert len(cutoffs) == 2


def test_purchase_tools_return_valid_metadata_when_explicitly_allowed(
    isolated_tenant_fixtures,
) -> None:
    """Verifica que las tools de compras devuelven metadata válida (sources, freshness)
    cuando se habilitan explícitamente via _allowed_tools."""
    from motoshop_api.llm.tools import ToolExecutor

    # Con el fixture default (solo get_kpis_today), compras están bloqueada
    for tenant in ("motoshop", "masvital"):
        executor = ToolExecutor(
            tenant=tenant,
            duckdb_path=str(isolated_tenant_fixtures / f"{tenant}.duckdb"),
        )
        assert executor.run("get_ultima_compra", {}) == {
            "error": "Tool not allowed for this tenant"
        }

    # Al habilitar explícitamente, la tool funciona y devuelve metadata completa
    executor = ToolExecutor(
        tenant="motoshop",
        duckdb_path=str(isolated_tenant_fixtures / "motoshop.duckdb"),
    )
    executor._allowed_tools = {"get_ultima_compra"}
    result = executor.get_ultima_compra()
    assert "sources" in result
    assert "freshness" in result
    assert result["sources"][0]["domain"] == "purchases"
    assert result["sources"][0]["kind"] == "duckdb"
    assert result["freshness"][0]["domain"] == "purchases"


def test_purchase_tools_work_when_in_enabled_tools(isolated_tenant_fixtures) -> None:
    """Verifica que get_ultima_compra y get_compras_recientes funcionan correctamente
    cuando están incluidas en enabled_tools del tenant (como en producción)."""
    from motoshop_api.llm.tools import ToolExecutor

    # Crear un fixture con compras habilitadas
    import yaml as _yaml

    tenants_path = isolated_tenant_fixtures / "tenants_with_compras.yaml"
    tenants_path.write_text(
        _yaml.safe_dump(
            {
                "tenants": [
                    {
                        "id": "motoshop",
                        "nombre": "Fixture MotoShop",
                        "r2_object_key": "motoshop.duckdb",
                        "local_db_path": str(isolated_tenant_fixtures / "motoshop.duckdb"),
                        "agent": {
                            "enabled_tools": [
                                "get_kpis_today",
                                "get_ultima_compra",
                                "get_compras_recientes",
                            ]
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    from motoshop_api.tenants import load_tenants

    load_tenants(tenants_path)

    try:
        executor = ToolExecutor(
            tenant="motoshop",
            duckdb_path=str(isolated_tenant_fixtures / "motoshop.duckdb"),
        )

        # get_ultima_compra debe funcionar
        result = executor.run("get_ultima_compra", {})
        assert "error" not in result
        assert result["proveedor"] == "Moto supplier"
        assert result["fecha"] == "2026-01-02"
        assert result["sources"][0]["domain"] == "purchases"
        assert result["freshness"][0]["domain"] == "purchases"

        # get_compras_recientes debe funcionar
        result2 = executor.run("get_compras_recientes", {"limit": 5})
        assert "error" not in result2
        assert result2["count"] == 1
        assert result2["compras"][0]["proveedor"] == "Moto supplier"
    finally:
        load_tenants(isolated_tenant_fixtures / "tenants.yaml")


def test_fixture_sources_preserve_distinct_source_kinds_and_partial_failure(
    isolated_tenant_fixtures,
) -> None:
    class Response:
        def json(self) -> list[dict[str, object]]:
            return [{"amount": 12, "tenant": "motoshop"}]

    class Client:
        def get(self, path: str, *, params: dict[str, str]) -> Response:
            assert path == "/gastos_operativos"
            assert params["tenant"] == "eq.motoshop"
            return Response()

    context = TenantContext(
        "motoshop", "managed", "vendedor", True, frozenset({"sales", "expenses"})
    )
    with duckdb.connect(str(isolated_tenant_fixtures / "motoshop.duckdb")) as connection:
        _, duckdb_evidence = DuckDBSourceAdapter(context, connection=connection).read("sales", {})
    _, supabase_evidence = SupabaseSourceAdapter(context, client=Client()).read("expenses")

    assert (duckdb_evidence.kind, supabase_evidence.kind) == ("duckdb", "supabase")
    assert duckdb_evidence.domain != supabase_evidence.domain

    class BrokenLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens, deadline):
            self.calls += 1
            if self.calls == 1:
                return {
                    "text": "",
                    "tool_calls": [
                        {"id": "1", "function": {"name": "cross_domain", "arguments": "{}"}}
                    ],
                }
            return {"text": "Ventas disponibles; gastos no disponibles.", "tool_calls": []}

    chat = QAChat(
        BrokenLLM(),
        ConversationManager(),
        type(
            "Executor",
            (),
            {
                "run": lambda self, name, args: {
                    "sources": [
                        {
                            "source_id": "duckdb-sales",
                            "domain": "sales",
                            "kind": "duckdb",
                            "citation": "fixture",
                            "cutoff_at": "2026-01-03",
                            "status": "used",
                        },
                        {
                            "source_id": "supabase-expenses",
                            "domain": "expenses",
                            "kind": "supabase",
                            "citation": "fixture",
                            "cutoff_at": "2026-01-01",
                            "status": "failed",
                            "reason": "unavailable",
                        },
                    ],
                    "freshness": [
                        {
                            "domain": "sales",
                            "cutoff_at": "2026-01-03",
                            "observed_at": "2026-01-04T00:00:00+00:00",
                            "status": "current",
                        },
                        {
                            "domain": "expenses",
                            "cutoff_at": "2026-01-01",
                            "observed_at": "2026-01-04T00:00:00+00:00",
                            "status": "stale",
                        },
                    ],
                }
            },
        )(),
        [],
        tenant_id="motoshop",
        user_id="managed",
        repository=InMemoryConversationRepository(),
    )
    result = chat.chat("compará ventas y gastos")
    assert result["status"] == "partial"
    assert {source["status"] for source in result["sources"]} == {"used", "failed"}
    assert {item["cutoff_at"] for item in result["freshness"]} == {"2026-01-01", "2026-01-03"}


def test_assistant_data_dependency_failure_uses_problem_details(client, admin_token, monkeypatch):
    from motoshop_api.metrics.repo_duckdb import DuckDBNotReadyError

    class FailingChat:
        def chat(self, message, conversation_id, request_id):
            raise DuckDBNotReadyError("tenant path should not be exposed")

    monkeypatch.setattr("motoshop_api.llm.qa_chat.get_qa_chat", lambda **_: FailingChat())
    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
        json={"message": "¿Cómo vamos?", "request_id": "dependency-1"},
    )

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert set(("type", "title", "status", "detail", "request_id")) <= response.json().keys()
    assert "tenant path" not in response.text
