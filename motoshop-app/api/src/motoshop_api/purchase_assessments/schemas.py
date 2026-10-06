"""Authenticated purchase-assessment response contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel


class PurchaseAssessmentResponse(BaseModel):
    id: str
    business_date: date
    cod_clase: str
    num_documento: str
    nit_proveedor: str | None = None
    nombre_proveedor: str | None = None
    content_fingerprint: str
    assessment_fingerprint: str
    status: Literal["pending", "processing", "completed", "fallback", "failed"]
    attempt_count: int
    last_error_code: str | None = None
    next_retry_at: datetime | None = None
    deterministic_metrics: dict[str, Any]
    markdown: str | None = None
    source_cutoffs: dict[str, str | None]
    generation_mode: Literal["llm", "deterministic_fallback"] | None = None
    provider: str | None = None
    model: str | None = None
    analyzer_revision: str
    prompt_revision: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class PurchaseAssessmentListResponse(BaseModel):
    items: list[PurchaseAssessmentResponse]
    date_from: date
    date_to: date
    limit: int
