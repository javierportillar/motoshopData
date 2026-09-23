from __future__ import annotations

from datetime import date

import httpx
import pytest
import duckdb

from motoshop_api.llm.client import LLMClient, PermanentLLMError, TransientLLMError
from motoshop_api.llm.contracts import AssistantRequest
from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
from motoshop_api.llm.qa_chat import ConversationManager, QAChat


class _AnsweringLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete_with_tools(self, messages, tools, *, max_tokens):
        self.calls += 1
        return {"text": "Respuesta de prueba", "tool_calls": []}


class _ToolLoopLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete_with_tools(self, messages, tools, *, max_tokens):
        self.calls += 1
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": str(self.calls),
                    "function": {"name": "sales", "arguments": "{}"},
                }
            ],
        }


class _Executor:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, name, args):
        self.calls += 1
        return {"sources": []}


def _chat(llm, repository=None, executor=None) -> QAChat:
    return QAChat(
        llm,
        ConversationManager(),
        executor or _Executor(),
        [],
        tenant_id="motoshop",
        user_id="ana",
        repository=repository or InMemoryConversationRepository(),
    )


def test_assistant_request_accepts_500_characters_and_rejects_501() -> None:
    accepted = AssistantRequest(message="x" * 500)

    assert len(accepted.message) == 500
    with pytest.raises(ValueError):
        AssistantRequest(message="x" * 501)
    with pytest.raises(ValueError):
        AssistantRequest(message="")


def test_chat_does_not_call_provider_after_20_turns() -> None:
    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "ana")
    for index in range(20):
        repository.append_turn(
            "motoshop",
            "ana",
            conversation["id"],
            f"question-{index}",
            "answer",
            request_id=f"request-{index}",
        )
    llm = _AnsweringLLM()

    result = _chat(llm, repository).chat("one more", conversation["id"])

    assert result["status"] == "needs_clarification"
    assert result["turn_count"] == 20
    assert llm.calls == 0


def test_chat_allows_the_twentieth_turn() -> None:
    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "ana")
    for index in range(19):
        repository.append_turn(
            "motoshop",
            "ana",
            conversation["id"],
            f"question-{index}",
            "answer",
            request_id=f"request-{index}",
        )
    llm = _AnsweringLLM()

    result = _chat(llm, repository).chat("last allowed turn", conversation["id"])

    assert result["status"] == "complete"
    assert result["turn_count"] == 20
    assert llm.calls == 1


def test_chat_stops_after_five_tool_iterations() -> None:
    llm = _ToolLoopLLM()
    executor = _Executor()

    result = _chat(llm, executor=executor).chat("consultá ventas")

    assert llm.calls == 8
    assert executor.calls == 8
    assert result["turn_count"] == 1
    assert "respuesta concreta" in result["text"]


def test_provider_timeout_is_transient() -> None:
    client = object.__new__(LLMClient)
    client._backends = [
        {
            "name": "go",
            "base": "https://provider.test",
            "key": "secret",
            "model": "test",
            "max_tokens": 100,
        }
    ]

    class _TimeoutHTTP:
        def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    client._http = _TimeoutHTTP()

    with pytest.raises(TransientLLMError):
        client.complete("hello")


def test_provider_rejection_is_permanent() -> None:
    client = object.__new__(LLMClient)
    client._backends = [
        {
            "name": "go",
            "base": "https://provider.test",
            "key": "secret",
            "model": "test",
            "max_tokens": 100,
        }
    ]

    class _RejectedHTTP:
        def post(self, *args, **kwargs):
            return httpx.Response(400, request=httpx.Request("POST", "https://provider.test"))

    client._http = _RejectedHTTP()

    with pytest.raises(PermanentLLMError):
        client.complete("hello")


def test_provider_retries_share_one_absolute_deadline(monkeypatch) -> None:
    import motoshop_api.llm.client as client_module

    client = object.__new__(LLMClient)
    client._backends = [
        {"name": "go", "base": "https://provider.test", "key": "secret", "model": "go", "max_tokens": 100},  # noqa: E501
        {"name": "zen", "base": "https://provider.test", "key": "secret", "model": "zen", "max_tokens": 100},  # noqa: E501
    ]
    clock = [100.0]
    timeouts = []

    class _RetryingHTTP:
        def post(self, *args, **kwargs):
            timeouts.append(kwargs["timeout"])
            clock[0] += 20
            raise httpx.ReadTimeout("timed out")

    client._http = _RetryingHTTP()
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])

    with pytest.raises(TransientLLMError):
        client.complete("hello", deadline=130.0)

    assert timeouts == [30.0, 10.0]


def test_tool_iterations_stop_when_the_shared_deadline_is_consumed(monkeypatch) -> None:
    import motoshop_api.llm.qa_chat as qa_module

    clock = [100.0]

    class _LoopingLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens, deadline):
            self.calls += 1
            clock[0] += 19
            return {
                "text": "",
                "tool_calls": [{"id": str(self.calls), "function": {"name": "sales", "arguments": "{}"}}],  # noqa: E501
            }

    class _SlowExecutor(_Executor):
        def run(self, name, args):
            result = super().run(name, args)
            clock[0] += 12
            return result

    monkeypatch.setattr(qa_module.time, "monotonic", lambda: clock[0])
    llm = _LoopingLLM()
    with pytest.raises(TransientLLMError):
        _chat(llm, executor=_SlowExecutor()).chat("consultá ventas")

    assert llm.calls == 2
    assert clock[0] == 162.0


def test_tool_result_with_date_is_serialized_before_next_llm_call() -> None:
    class _DateLLM:
        calls = 0

        def complete_with_tools(self, messages, tools, *, max_tokens, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "text": "",
                    "tool_calls": [{
                        "id": "product-1",
                        "function": {"name": "product", "arguments": "{}"},
                    }],
                }
            assert '"ultima_compra": "2026-09-13"' in messages[-1]["content"]
            return {"text": "Ficha procesada", "tool_calls": []}

    class _DateExecutor(_Executor):
        def run(self, name, args):
            return {"ultima_compra": date(2026, 9, 13)}

    result = _chat(_DateLLM(), executor=_DateExecutor()).chat("consultá el producto")

    assert result["text"] == "Ficha procesada"


def test_search_products_matches_reordered_words_and_reports_ambiguity() -> None:
    from motoshop_api.llm.tools import ToolExecutor

    executor = object.__new__(ToolExecutor)
    executor._con = duckdb.connect(":memory:")
    executor._con.execute(
        """
        CREATE TABLE silver_dim_producto (
            cod_producto VARCHAR,
            nombre_producto VARCHAR,
            precio_venta_sin_iva DOUBLE,
            costo_ultima_compra DOUBLE,
            existencia DOUBLE,
            nit_proveedor VARCHAR,
            estado_producto VARCHAR,
            cod_grupo VARCHAR
        )
        """
    )
    executor._con.executemany(
        "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("171751", "KIT CAJA CADENA - DR 150 DORADA CASSARELLA", 142100, 85278, 3, "N1", "A", "G1"),
            ("175712", "KIT CAJA CADENA - DR 150 DORADA GAVIRIA", 130000, 78000, 2, "N2", "A", "G1"),
            ("SKU-OTHER", "FILTRO DE ACEITE", 10000, 5000, 4, "N3", "A", "G2"),
        ],
    )

    result = executor.search_products("cadena dr 150")

    assert result["ambiguo"] is True
    assert result["total"] == 2
    assert {item["codigo"] for item in result["productos"]} == {"171751", "175712"}


def test_tool_errors_do_not_log_raw_arguments_or_values(caplog) -> None:
    from motoshop_api.llm.tools import ToolExecutor

    executor = object.__new__(ToolExecutor)
    executor.tenant = "motoshop"
    executor._allowed_tools = {"explode"}

    def explode(**kwargs):
        raise ValueError("provider secret should not be logged")

    executor.explode = explode
    with caplog.at_level("WARNING", logger="motoshop_api.llm.tools"):
        result = executor.run(
            "explode", {"password": "super-secret", "sku": "SKU-PRIVATE-42"}
        )

    assert result == {"error": "provider secret should not be logged"}
    assert "super-secret" not in caplog.text
    assert "SKU-PRIVATE-42" not in caplog.text
    assert "ValueError" in caplog.text


def test_tool_executor_filters_invocations_by_authenticated_domains(monkeypatch) -> None:
    from pathlib import Path

    import motoshop_api.llm.tools as tools_module
    from motoshop_api.auth.tenant_dep import TenantContext
    from motoshop_api.llm.tools import ToolExecutor

    monkeypatch.setattr(tools_module, "get_shared_connection", lambda path: object())
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb._make_db_path",
        lambda tenant: Path(f"/tmp/{tenant}.duckdb"),
    )
    context = TenantContext(
        "motoshop", "sales-only", "vendedor", True, frozenset({"sales"})
    )
    executor = ToolExecutor(tenant="motoshop", user_id="sales-only", tenant_context=context)
    executor.get_kpis_today = lambda: {"authorized": True}

    assert executor.run("get_kpis_today", {}) == {"authorized": True}
    assert executor.run("get_inventory_value", {}) == {
        "error": "Tool not allowed for this tenant"
    }


def test_duplicate_request_without_conversation_reuses_persisted_response() -> None:
    repository = InMemoryConversationRepository()
    llm = _AnsweringLLM()
    chat = _chat(llm, repository)

    first = chat.chat("hola", request_id="request-once")
    duplicate = chat.chat("hola", request_id="request-once")

    assert duplicate == first
    assert llm.calls == 1
    assert len(repository.list_conversations("motoshop", "ana")) == 1


def test_sqlite_duplicate_request_without_conversation_reuses_persisted_response(tmp_path) -> None:
    from motoshop_api.llm.conversations.repository import SQLiteConversationRepository

    repository = SQLiteConversationRepository(str(tmp_path / "assistant.sqlite3"))
    llm = _AnsweringLLM()
    chat = _chat(llm, repository)

    first = chat.chat("hola", request_id="request-once")
    duplicate = chat.chat("hola", request_id="request-once")

    assert duplicate == first
    assert llm.calls == 1
    assert len(repository.list_conversations("motoshop", "ana")) == 1
