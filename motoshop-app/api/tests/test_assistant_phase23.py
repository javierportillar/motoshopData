from __future__ import annotations

import httpx
import pytest

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

    assert llm.calls == 5
    assert executor.calls == 5
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
