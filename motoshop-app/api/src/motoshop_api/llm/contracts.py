"""Typed contracts and safety helpers for the governed assistant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["complete", "partial", "empty", "needs_clarification", "unavailable"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
class AssistantRequest(_Contract):
    message: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = None
    request_id: str | None = Field(default=None, max_length=80)

    @field_validator("message", mode="before")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value
class SourceEvidence(_Contract):
    source_id: str
    domain: str
    kind: Literal["duckdb", "supabase", "document"]
    citation: str
    cutoff_at: str | None = None
    observed_at: str | None = None
    status: Literal["used", "failed"]
class Freshness(_Contract):
    domain: str
    cutoff_at: str | None = None
    observed_at: str | None = None
    status: Literal["current", "stale", "unknown"]
class EntityRef(_Contract):
    entity_type: str
    entity_id: str
    label: str
    domain: str
    href: str
class Attachment(_Contract):
    type: Literal["report"] = "report"
    format: Literal["excel", "pdf", "word"]
    filename: str
    download_url: str
    state: Literal["available", "expired"]
    expires_at: str | None
    date_from: str | None
    date_to: str | None
    period_label: str | None

    @field_validator("download_url")
    @classmethod
    def server_route(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("download_url must be a server-issued route")
        return value
class AssistantEnvelope(_Contract):
    status: Status
    tenant_id: str
    text: str
    conversation_id: str
    turn_count: int = Field(ge=0)
    tools_used: list[str]
    sources: list[SourceEvidence] = Field(default_factory=list)
    freshness: list[Freshness] = Field(default_factory=list)
    entity_refs: list[EntityRef] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
def problem_response(status: int, error_type: str, detail: str, request_id: str) -> JSONResponse:
    """Return RFC 7807-compatible JSON without provider details."""
    titles = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 422: "Unprocessable Entity",
              502: "Bad Gateway", 503: "Service Unavailable"}
    return JSONResponse(status_code=status, media_type="application/problem+json", content={
        "type": error_type, "title": titles.get(status, "Request Error"), "status": status,
        "detail": detail, "request_id": request_id,
    })
_SENSITIVE = {"password", "passwd", "token", "secret", "credential", "authorization", "api_key"}


def redact_sensitive(value: Any) -> Any:
    """Recursively redact credential-shaped mapping fields."""
    if isinstance(value, Mapping):
        return {key: "[REDACTED]" if _sensitive(str(key)) else redact_sensitive(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value
def _sensitive(key: str) -> bool:
    key = key.lower()
    return key in _SENSITIVE or any(key.endswith(f"_{suffix}") for suffix in _SENSITIVE)
