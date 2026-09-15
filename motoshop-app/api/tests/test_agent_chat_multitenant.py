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
    }


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


def test_supabase_append_turn_uses_role_scoped_idempotency():
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

    message_call = next(call for call in calls if call[:2] == ("POST", "agent_messages"))
    payload = message_call[2]
    assert payload["params"]["on_conflict"] == "conversation_id,request_id,role"
    assert [row["role"] for row in payload["json"]] == ["user", "assistant"]
    assert payload["json"][0]["created_at"] < payload["json"][1]["created_at"]

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

    def fake_factory(tenant, user_id):
        captured.update(tenant=tenant, user_id=user_id)
        return FakeChat()

    monkeypatch.setattr("motoshop_api.llm.qa_chat.get_qa_chat", fake_factory)
    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "masvital"},
        json={"message": "¿Cómo vamos?", "request_id": "request-1"},
    )
    assert response.status_code == 200
    assert captured == {"tenant": "masvital", "user_id": "admin"}


def test_chat_http_endpoint_maps_provider_outage_to_503(client, admin_token, monkeypatch):
    from motoshop_api.llm.client import TransientLLMError

    class FailingChat:
        def chat(self, message, conversation_id, request_id):
            raise TransientLLMError("provider timeout")

    monkeypatch.setattr(
        "motoshop_api.llm.qa_chat.get_qa_chat", lambda tenant, user_id: FailingChat()
    )
    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
        json={"message": "¿Cómo vamos?"},
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
