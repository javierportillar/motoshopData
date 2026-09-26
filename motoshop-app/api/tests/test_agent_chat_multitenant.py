from pathlib import Path
from uuid import uuid4

import pytest

from motoshop_api import tenants


@pytest.fixture(autouse=True)
def load_test_tenants():
    tenants.load_tenants(Path(__file__).parents[1] / "tenants.yaml")


def test_agent_prompt_is_tenant_specific():
    from motoshop_api.llm.qa_chat import build_qa_system

    moto = build_qa_system("motoshop")
    vital = build_qa_system("masvital")
    assert "MotoShop" in moto and "MasVital" not in moto
    assert "MasVital" in vital and "MotoShop" not in vital


def test_agent_prompt_restricts_generate_report_to_explicit_file_requests():
    """Una pregunta de datos ('cuáles son los productos bajos en stock?') NO debe
    disparar la generación de archivos: generate_report solo ante pedido explícito."""
    from motoshop_api.llm.qa_chat import build_qa_system

    prompt = build_qa_system("motoshop")
    assert "SOLO para cuando el usuario pida EXPLÍCITAMENTE" in prompt
    assert "NUNCA generes un archivo si el usuario no lo pidió" in prompt
    assert "respondé SIEMPRE en el chat" in prompt


def test_generate_report_tool_description_demands_explicit_file_request():
    """La spec de la tool también debe desincentivar el uso para preguntas de datos."""
    from motoshop_api.llm.tools import TOOL_DEFINITIONS

    spec = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "generate_report")
    description = spec["function"]["description"]
    assert "SOLO cuando el usuario pida EXPLÍCITAMENTE" in description
    assert "NO la uses para responder preguntas de datos" in description


def test_chat_tool_catalog_is_scoped_to_tenant(monkeypatch):
    import motoshop_api.llm.qa_chat as qa_module
    from motoshop_api.llm.conversations.repository import InMemoryConversationRepository

    class FakeExecutor:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr("motoshop_api.llm.tools.ToolExecutor", FakeExecutor)
    monkeypatch.setattr("motoshop_api.llm.client.get_llm_client", lambda: object())
    monkeypatch.setattr(qa_module, "get_tenant_config", tenants.get_tenant_config)
    # Repository defaults are not touched; only inspect the generated catalog.
    chat = qa_module.get_qa_chat("masvital", "ana", repository=InMemoryConversationRepository())
    assert {item["function"]["name"] for item in chat.tool_defs} == {
        "get_kpis_today",
        "get_kpis_month",
        "get_top_skus",
        "get_dormidos",
        "get_inventory_value",
        "get_data_freshness",
        "search_business_knowledge",
        "get_ultima_compra",
        "get_compras_recientes",
        "buscar_compras_por_proveedor",
        "get_producto_detalle",
        "get_detalle_compra",
        "search_products",
        "analizar_compras_periodo",
        "evaluar_compra_planeada",
        "get_top_clientes",
        "get_inventario_por_bodega",
        "get_drift_alerts",
        "generate_report",
    }

    moto = qa_module.get_qa_chat("motoshop", "ana", repository=InMemoryConversationRepository())
    moto_names = {item["function"]["name"] for item in moto.tool_defs}
    assert "get_ultima_compra" in moto_names
    assert "get_compras_recientes" in moto_names
    assert "search_products" in moto_names
    assert "analizar_compras_periodo" in moto_names
    assert "evaluar_compra_planeada" in moto_names
    assert "get_top_clientes" in moto_names
    assert "get_inventario_por_bodega" in moto_names
    assert "get_abc_xyz_distribution" in moto_names
    assert "get_cohortes_clientes" in moto_names
    assert "get_drift_alerts" in moto_names


def test_tool_executor_does_not_inherit_global_duckdb(monkeypatch):
    import motoshop_api.metrics.repo_duckdb as repo_duckdb
    from motoshop_api.llm.tools import ToolExecutor

    seen = {}
    monkeypatch.setenv("DUCKDB_PATH", "/tmp/wrong-global.duckdb")
    monkeypatch.setattr(
        repo_duckdb, "_make_db_path", lambda tenant: Path(f"/tmp/{tenant}-gold.duckdb")
    )
    import motoshop_api.llm.tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "get_shared_connection",
        lambda path: seen.setdefault("path", path) or object(),
    )
    executor = ToolExecutor(tenant="masvital")
    assert seen["path"] == "/tmp/masvital-gold.duckdb"
    assert executor.run("close", {}) == {"error": "Tool not allowed for this tenant"}


def test_conversations_are_isolated_by_tenant_and_user():
    from motoshop_api.llm.conversations.repository import InMemoryConversationRepository

    repo = InMemoryConversationRepository()
    first = repo.create_conversation("motoshop", "ana")
    repo.create_conversation("masvital", "ana")
    repo.append_turn("motoshop", "ana", first["id"], "hola", "respuesta")
    assert len(repo.list_messages("motoshop", "ana", first["id"])) == 2
    assert repo.get_conversation("motoshop", "otra", first["id"]) is None


def test_qa_chat_persists_turn_and_returns_sources():
    from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
    from motoshop_api.llm.qa_chat import ConversationManager, QAChat

    class FakeLLM:
        def complete_with_tools(self, messages, tools, *, max_tokens):
            return {"text": "Respuesta real", "tool_calls": [], "model": "test", "backend": "fake"}

    class FakeExecutor:
        def run(self, name, args):
            return {"sources": [{"source": "manual.md"}]}

    repo = InMemoryConversationRepository()
    chat = QAChat(
        FakeLLM(),
        ConversationManager(),
        FakeExecutor(),
        [],
        tenant_id="masvital",
        user_id="ana",
        repository=repo,
    )
    result = chat.chat("¿Cómo estamos?")
    assert result["conversation_id"]
    assert result["turn_count"] == 1
    assert len(repo.list_conversations("masvital", "ana")) == 1


def test_qa_chat_reuses_persisted_response_for_same_request_id():
    from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
    from motoshop_api.llm.qa_chat import ConversationManager, QAChat

    class FakeLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens):
            self.calls += 1
            return {"text": "respuesta", "tool_calls": []}

    class FakeExecutor:
        def run(self, name, args):
            return {}

    llm = FakeLLM()
    repo = InMemoryConversationRepository()
    chat = QAChat(
        llm,
        ConversationManager(),
        FakeExecutor(),
        [],
        tenant_id="motoshop",
        user_id="ana",
        repository=repo,
    )
    first = chat.chat("hola", request_id="same-request")
    second = chat.chat("hola", first["conversation_id"], request_id="same-request")
    assert second["text"] == first["text"]
    assert llm.calls == 1


def test_hybrid_retriever_degrades_without_supabase(monkeypatch):
    from motoshop_api.llm.retrieval import HybridRetriever

    monkeypatch.setattr("motoshop_api.llm.retrieval.settings.supabase_url", "")
    monkeypatch.setattr("motoshop_api.llm.retrieval.settings.supabase_service_key", "")
    result = HybridRetriever().search("motoshop", "política de devoluciones")
    assert result["status"] == "unavailable"
    assert result["results"] == []


def test_sqlite_conversations_survive_repository_restart(tmp_path):
    from motoshop_api.llm.conversations.repository import SQLiteConversationRepository

    path = tmp_path / "chat.sqlite3"
    first = SQLiteConversationRepository(str(path))
    conversation = first.create_conversation("motoshop", "ana")
    first.append_turn(
        "motoshop", "ana", conversation["id"], "hola", "respuesta", request_id="request-1"
    )
    first.append_turn(
        "motoshop", "ana", conversation["id"], "hola", "respuesta", request_id="request-1"
    )

    restarted = SQLiteConversationRepository(str(path))
    messages = restarted.list_messages("motoshop", "ana", conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert restarted.get_conversation("masvital", "ana", conversation["id"]) is None


def test_supabase_append_turn_inserts_user_and_assistant_separately():
    from motoshop_api.llm.conversations.repository import SupabaseConversationRepository

    conversation_id = str(uuid4())
    calls = []
    repo = object.__new__(SupabaseConversationRepository)

    def fake_request(method, table, **kwargs):
        calls.append((method, table, kwargs))
        if method == "GET":
            return [{"id": conversation_id, "message_count": 0, "title": "Nueva conversación"}]
        return []

    repo._request = fake_request
    repo.append_turn(
        "motoshop",
        "ana",
        conversation_id,
        "hola",
        "respuesta",
        request_id="request-1",
    )

    message_calls = [call for call in calls if call[:2] == ("POST", "agent_messages")]
    # Each message is inserted individually (PostgREST batch requires same keys)
    assert len(message_calls) == 2
    assert message_calls[0][2]["json"]["role"] == "user"
    assert message_calls[1][2]["json"]["role"] == "assistant"
    assert message_calls[0][2]["json"]["created_at"] < message_calls[1][2]["json"]["created_at"]

    update_call = next(call for call in calls if call[:2] == ("PATCH", "agent_conversations"))
    assert update_call[2]["json"]["message_count"] == 2
    assert update_call[2]["json"]["title"] == "hola"


def test_chat_http_endpoint_forwards_authenticated_tenant_and_user(
    client, admin_token, monkeypatch
):
    captured = {}

    class FakeChat:
        def chat(self, message, conversation_id, request_id):
            return {
                "text": "ok",
                "conversation_id": "conversation-1",
                "turn_count": 1,
                "tools_used": [],
                "sources": [],
                "data_as_of": None,
            }

    def fake_factory(**kwargs):
        context = kwargs["tenant_context"]
        captured.update(tenant=context.tenant_id, user_id=context.user_id)
        return FakeChat()

    monkeypatch.setattr("motoshop_api.llm.qa_chat.get_qa_chat", fake_factory)
    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "masvital"},
        json={"message": "¿Cómo vamos?", "request_id": "request-1"},
    )
    assert response.status_code == 200
    assert captured == {"tenant": "masvital", "user_id": "admin"}


def test_chat_passes_authenticated_capability_context_to_executor(client, monkeypatch):
    from motoshop_api.auth.deps import get_current_user
    from motoshop_api.auth.users import User
    from motoshop_api.main import app

    captured = {}

    class FakeChat:
        def chat(self, message, conversation_id, request_id):
            return {"text": "ok", "conversation_id": "c1", "turn_count": 1, "tools_used": []}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return FakeChat()

    restricted = User(
        username="sales-only",
        hashed_password="hash",
        email="sales-only@test.com",
        role="vendedor",
        tenants_allowed=["motoshop"],
        allowed_modules=["chat-ia", "ventas-summary"],
        source="supabase",
    )
    app.dependency_overrides[get_current_user] = lambda: restricted
    monkeypatch.setattr("motoshop_api.llm.qa_chat.get_qa_chat", fake_factory)
    try:
        client.post(
            "/api/llm/qa/chat",
            headers={"X-Tenant": "motoshop"},
            json={"message": "¿Cómo van las ventas?"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    context = captured["tenant_context"]
    assert context.user_id == "sales-only"
    assert context.tenant_id == "motoshop"
    assert context.allowed_domains == frozenset({"sales", "purchases"})


def test_assistant_rejection_paths_use_problem_details(client, admin_token):
    invalid = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Request-ID": "validation-1"},
        json={"message": "x" * 501},
    )
    assert invalid.status_code == 422
    assert invalid.headers["content-type"] == "application/problem+json"
    assert set(("type", "title", "status", "detail", "request_id")) <= invalid.json().keys()

    unauthenticated = client.post("/api/llm/qa/chat", json={"message": "hola"})
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["content-type"] == "application/problem+json"

    missing_conversation = client.get(
        "/api/llm/chat/conversations/not-found/messages",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
    )
    assert missing_conversation.status_code == 404
    assert missing_conversation.headers["content-type"] == "application/problem+json"


def test_chat_http_endpoint_maps_provider_outage_to_503(client, admin_token, monkeypatch):
    from motoshop_api.llm.client import TransientLLMError

    class FailingChat:
        def chat(self, message, conversation_id, request_id):
            raise TransientLLMError("provider timeout")

    monkeypatch.setattr("motoshop_api.llm.qa_chat.get_qa_chat", lambda **_: FailingChat())
    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
        json={"message": "¿Cómo vamos?"},
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.headers["content-type"] == "application/problem+json"


def test_chat_http_endpoint_maps_provider_rejection_to_502(client, admin_token, monkeypatch):
    from motoshop_api.llm.client import PermanentLLMError

    class FailingChat:
        def chat(self, message, conversation_id, request_id):
            raise PermanentLLMError("provider rejected")

    monkeypatch.setattr("motoshop_api.llm.qa_chat.get_qa_chat", lambda **_: FailingChat())
    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
        json={"message": "¿Cómo vamos?", "request_id": "problem-1"},
    )
    assert (
        response.status_code,
        response.headers["content-type"],
        response.json()["request_id"],
    ) == (502, "application/problem+json", "problem-1")


def _chat_with_tool_result(tool_result, tool_name="sales"):
    from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
    from motoshop_api.llm.qa_chat import ConversationManager, QAChat

    class FakeLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens):
            self.calls += 1
            return (
                {
                    "text": "",
                    "tool_calls": [
                        {"id": "call", "function": {"name": tool_name, "arguments": "{}"}}
                    ],
                }
                if self.calls == 1
                else {"text": "No hay ventas en el alcance consultado.", "tool_calls": []}
            )

    class FakeExecutor:
        calls = 0

        def run(self, name, args):
            self.calls += 1
            return tool_result

    chat = QAChat(
        FakeLLM(),
        ConversationManager(),
        FakeExecutor(),
        [],
        tenant_id="motoshop",
        user_id="ana",
        repository=InMemoryConversationRepository(),
    )
    return chat, chat.executor


def test_qa_chat_returns_governed_envelope_with_per_source_freshness():
    chat, _ = _chat_with_tool_result(
        {
            "sources": [
                {
                    "source_id": "duckdb-sales",
                    "domain": "sales",
                    "kind": "duckdb",
                    "citation": "sales snapshot",
                    "cutoff_at": "2026-09-13",
                    "observed_at": "2026-09-15T10:00:00+00:00",
                    "status": "used",
                }
            ],
            "freshness": [
                {
                    "domain": "sales",
                    "cutoff_at": "2026-09-13",
                    "observed_at": "2026-09-15T10:00:00+00:00",
                    "status": "current",
                }
            ],
            "entity_refs": [
                {
                    "entity_type": "product",
                    "entity_id": "SKU-1",
                    "label": "Filtro",
                    "domain": "inventory",
                    "route_key": "product",
                },
                {"href": "https://evil.example/file"},
            ],
        }
    )
    result = chat.chat("¿Cómo están las ventas?")

    assert set(result) == {
        "status",
        "tenant_id",
        "text",
        "conversation_id",
        "turn_count",
        "tools_used",
        "sources",
        "freshness",
        "entity_refs",
        "attachments",
    }
    assert result["status"] == "complete"
    assert result["tenant_id"] == "motoshop"
    assert result["sources"][0]["cutoff_at"] == result["freshness"][0]["cutoff_at"] == "2026-09-13"
    assert result["entity_refs"] == []


def test_qa_chat_marks_empty_and_does_not_invent_values():
    chat, _ = _chat_with_tool_result({"status": "empty", "sources": [], "freshness": []})
    result = chat.chat("¿Qué ventas hubo en un período sin registros?")
    assert result["status"] == "empty"
    assert "0" not in result["text"]
    assert result["sources"] == []


def test_qa_chat_requires_explicit_file_intent_and_reuses_duplicate_envelope():
    chat, executor = _chat_with_tool_result(
        {"status": "success", "download_url": "/api/reports/download/rep_bad"},
        tool_name="generate_report",
    )
    result = chat.chat("Dame un reporte de stock", request_id="duplicate-1")

    assert (result["status"], result["attachments"], executor.calls) == (
        "needs_clarification",
        [],
        0,
    )

    duplicate = chat.chat("Dame un reporte de stock", result["conversation_id"], "duplicate-1")
    assert duplicate == result
