from __future__ import annotations

import pytest

from motoshop_api.llm.contracts import (
    AssistantEnvelope,
    AssistantRequest,
    Attachment,
    Freshness,
    SourceEvidence,
    problem_response,
    redact_sensitive,
)


def test_envelope_has_exact_fields_and_empty_arrays() -> None:
    result = AssistantEnvelope(status="complete", tenant_id="motoshop", text="ok",
                               conversation_id="c", turn_count=1, tools_used=[])
    assert set(result.model_dump()) == {
        "status", "tenant_id", "text", "conversation_id", "turn_count", "tools_used",
        "sources", "freshness", "entity_refs", "attachments",
    }
    assert result.sources == result.freshness == result.entity_refs == result.attachments == []
    with pytest.raises(ValueError):
        AssistantEnvelope(status="complete", tenant_id="m", text="x", conversation_id="c",
                          turn_count=0, tools_used=[], extra="denied")


def test_typed_contracts_enforce_bounds_and_server_routes() -> None:
    assert AssistantRequest(message=" ventas ", request_id="r").message == "ventas"
    with pytest.raises(ValueError):
        AssistantRequest(message="   ")
    with pytest.raises(ValueError):
        AssistantRequest(message="x" * 501)
    source = SourceEvidence(source_id="s", domain="sales", kind="duckdb", citation="daily",
                            status="used")
    assert source.domain == Freshness(domain="sales", status="unknown").domain
    with pytest.raises(ValueError):
        Attachment(format="pdf", filename="r.pdf", download_url="https://evil", state="available",
                   expires_at=None, date_from=None, date_to=None, period_label=None)


def test_problem_response_and_redaction_are_safe() -> None:
    response = problem_response(403, "assistant-disabled", "Assistant disabled", "req-1")
    assert response.media_type == "application/problem+json" and response.status_code == 403
    assert b'"request_id":"req-1"' in response.body
    assert redact_sensitive({"token": "secret", "nested": {"password": "pw", "amount": 4}}) == {
        "token": "[REDACTED]", "nested": {"password": "[REDACTED]", "amount": 4}
    }
