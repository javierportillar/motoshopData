from pathlib import Path

import pytest

from motoshop_api import tenants
from motoshop_api.llm.conversations.repository import (
    InMemoryConversationRepository,
    SQLiteConversationRepository,
)
from motoshop_api.llm.qa_chat import ConversationManager, QAChat


@pytest.fixture(autouse=True)
def load_test_tenants():
    tenants.load_tenants(Path(__file__).parents[1] / "tenants.yaml")


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete_with_tools(self, messages, tools, *, max_tokens):
        self.calls += 1
        if self.calls == 1:
            return {
                "text": "",
                "tool_calls": [
                    {
                        "id": "sales-call",
                        "function": {"name": "sales", "arguments": "{}"},
                    }
                ],
            }
        return {"text": "Ventas disponibles.", "tool_calls": []}


class _FakeExecutor:
    def __init__(self, with_attachment: bool = False) -> None:
        self.with_attachment = with_attachment

    def run(self, name, args):
        result = {
            "sources": [
                {
                    "source_id": "sales-snapshot",
                    "domain": "sales",
                    "kind": "duckdb",
                    "citation": "Ventas del corte",
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
                }
            ],
        }
        if self.with_attachment:
            result.update(
                {
                    "format": "pdf",
                    "filename": "ventas.pdf",
                    "download_url": "/api/reports/download/rep_integration",
                    "expires_at": "2099-09-15T10:00:00+00:00",
                    "date_from": "2026-09-01",
                    "date_to": "2026-09-13",
                    "period_label": "Septiembre 2026",
                }
            )
        return result


def _chat(repository, executor=None) -> QAChat:
    return QAChat(
        _FakeLLM(),
        ConversationManager(),
        executor or _FakeExecutor(),
        [],
        tenant_id="motoshop",
        user_id="admin",
        repository=repository,
    )


def test_chat_envelope_round_trips_through_history_and_remains_tenant_scoped(
    client, admin_token, monkeypatch
):
    repository = InMemoryConversationRepository()
    monkeypatch.setattr(
        "motoshop_api.llm.qa_chat.get_qa_chat",
        lambda **_: _chat(repository),
    )
    monkeypatch.setattr(
        "motoshop_api.llm.conversations.repository.get_conversation_repository",
        lambda: repository,
    )

    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
        json={"message": "¿Cómo están las ventas?", "request_id": "integration-1"},
    )

    assert response.status_code == 200
    reply = response.json()
    assert reply["tenant_id"] == "motoshop"
    assert reply["sources"][0]["cutoff_at"] == "2026-09-13"
    assert reply["entity_refs"] == []

    history = client.get(
        f"/api/llm/chat/conversations/{reply['conversation_id']}/messages",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
    )

    assert history.status_code == 200
    assistant = history.json()[-1]
    assert assistant["tenant_id"] == "motoshop"
    assert assistant["status"] == "complete"
    assert assistant["sources"] == reply["sources"]
    assert assistant["freshness"] == reply["freshness"]
    assert assistant["entity_refs"] == reply["entity_refs"]
    assert assistant["attachments"] == []

    cross_tenant = client.get(
        f"/api/llm/chat/conversations/{reply['conversation_id']}/messages",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "masvital"},
    )
    assert cross_tenant.status_code == 404


def test_old_assistant_history_backfills_catalog_verified_product_refs_read_only(
    client, admin_token, monkeypatch
):
    from motoshop_api.llm.contracts import EntityRef

    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "admin")
    repository.append_turn(
        "motoshop",
        "admin",
        conversation["id"],
        "¿Qué revisar?",
        "BONNAT001 SALSAS MRS TASTE requiere revisión.",
    )
    repository.append_turn(
        "motoshop",
        "admin",
        conversation["id"],
        "¿Dónde veo el producto?",
        "Detalle anterior: BONNAT001 SALSAS MRS TASTE.",
        entity_refs=[{
            "entity_type": "product",
            "entity_id": "BONNAT001",
            "label": "SALSAS MRS TASTE",
            "domain": "inventory",
            "href": "/inventario/productos/BONNAT001",
        }],
    )
    monkeypatch.setattr(
        "motoshop_api.llm.conversations.repository.get_conversation_repository",
        lambda: repository,
    )
    monkeypatch.setattr(
        "motoshop_api.llm.registry.resolve_product_refs_in_text",
        lambda context, text, *, limit=30: [
            EntityRef(
                entity_type="product",
                entity_id="BONNAT001",
                label="SALSAS MRS TASTE",
                domain="inventory",
                href="/dashboards/productos/BONNAT001",
            )
        ],
    )

    response = client.get(
        f"/api/llm/chat/conversations/{conversation['id']}/messages",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
    )

    assert response.status_code == 200, response.text
    assistant_messages = [row for row in response.json() if row["role"] == "assistant"]
    expected_ref = {
        "entity_type": "product",
        "entity_id": "BONNAT001",
        "label": "SALSAS MRS TASTE",
        "label_is_unique": True,
        "domain": "inventory",
        "href": "/dashboards/productos/BONNAT001",
    }
    assert [row["entity_refs"] for row in assistant_messages] == [[expected_ref], [expected_ref]]
    stored_assistant_messages = [
        row for row in repository.list_messages("motoshop", "admin", conversation["id"])
        if row["role"] == "assistant"
    ]
    assert stored_assistant_messages[0]["entity_refs"] == []
    assert stored_assistant_messages[1]["entity_refs"][0]["href"] == "/inventario/productos/BONNAT001"


def test_history_reference_filter_requires_entity_domain_and_current_capability() -> None:
    from motoshop_api.auth.tenant_dep import TenantContext
    from motoshop_api.llm.router import _entity_ref_allowed

    sales_only = TenantContext("motoshop", "sales", "vendedor", True, frozenset({"sales"}))
    inventory_only = TenantContext(
        "motoshop", "inventory", "vendedor", True, frozenset({"inventory"})
    )

    assert not _entity_ref_allowed({
        "entity_type": "product", "entity_id": "SKU-1", "domain": "sales",
    }, sales_only)
    assert not _entity_ref_allowed({
        "entity_type": "product", "entity_id": "SKU-1", "domain": "inventory",
    }, sales_only)
    assert _entity_ref_allowed({
        "entity_type": "product", "entity_id": "SKU-1", "domain": "inventory",
    }, inventory_only)
def test_explicit_report_attachment_round_trips_in_sqlite_history(
    client, admin_token, monkeypatch, tmp_path
):
    repository = SQLiteConversationRepository(str(tmp_path / "assistant.sqlite3"))
    monkeypatch.setattr(
        "motoshop_api.llm.qa_chat.get_qa_chat",
        lambda **_: _chat(repository, _FakeExecutor(with_attachment=True)),
    )
    monkeypatch.setattr(
        "motoshop_api.llm.conversations.repository.get_conversation_repository",
        lambda: repository,
    )

    response = client.post(
        "/api/llm/qa/chat",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
        json={"message": "Exportame las ventas en PDF", "request_id": "integration-report"},
    )

    assert response.status_code == 200
    reply = response.json()
    assert reply["attachments"][0]["download_url"] == "/api/reports/download/rep_integration"

    history = client.get(
        f"/api/llm/chat/conversations/{reply['conversation_id']}/messages",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
    )

    assert history.status_code == 200
    assert history.json()[-1]["attachments"] == reply["attachments"]
