"""Pydantic models for DIAN electronic invoicing (Slice 6, spec erp-dian-einvoicing)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DianStatusEnum(str, Enum):
    """Lifecycle status of a document in the DIAN electronic invoicing pipeline."""

    PENDING = "PENDING"
    SENDING = "SENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DianDocOut(BaseModel):
    """Public representation of an electronic document transmitted to DIAN."""

    model_config = ConfigDict(from_attributes=True)

    sale_id: str = Field(description="Unique sale identifier in the ERP")
    doc_number: str = Field(description="Invoice or document consecutive number, e.g. POS-0001 or FV-1001")
    cufe: str | None = Field(default=None, description="Código Único de Factura Electrónica (SHA-384 hex 96 chars)")
    qr_url: str | None = Field(default=None, description="Official DIAN verification QR URL")
    status: DianStatusEnum = Field(default=DianStatusEnum.PENDING, description="Current transmission status")
    sent_at: datetime | None = Field(default=None, description="Timestamp of the most recent transmission attempt")
    accepted_at: datetime | None = Field(default=None, description="Timestamp when DIAN officially accepted the document")
    error_message: str | None = Field(default=None, description="Error message if rejected or failed")
    retry_count: int = Field(default=0, ge=0, description="Number of transmission attempts performed")
    track_id: str | None = Field(default=None, description="Provider track ID / transaction UUID")
    estfele: int | None = Field(default=None, description="Numeric DIAN status parity (1=Accepted, 2=Accepted with warning, 3=Rejected, 0=Failed)")


class DianQueueListOut(BaseModel):
    """Paginated or filtered list of documents in the DIAN queue with summary metrics."""

    model_config = ConfigDict(from_attributes=True)

    documents: list[DianDocOut] = Field(default_factory=list, description="List of queued documents")
    total: int = Field(ge=0, description="Total queued documents for tenant")
    accepted: int = Field(ge=0, description="Count of accepted documents")
    pending: int = Field(ge=0, description="Count of pending documents")
    failed: int = Field(ge=0, description="Count of permanently failed documents")
    rejected: int = Field(default=0, ge=0, description="Count of rejected documents")


class DianRetryIn(BaseModel):
    """Payload to trigger a manual retry for a failed DIAN document."""

    sale_id: str = Field(description="Sale ID to retry")
    force: bool = Field(default=False, description="Whether to reset retry count and bypass backoff delays")
