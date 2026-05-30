"""Schemas Pydantic para app_writes: alert action request/response."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AlertActionRequest(BaseModel):
    """Body de POST /alerts/{alert_id}/action.

    Validación condicional por action_type:
    - ordered → quantity requerido, supplier opcional
    - dismissed → reason requerido
    - postponed → postponed_to requerido
    """

    action_type: Literal["ordered", "dismissed", "postponed"]
    quantity: Decimal | None = Field(default=None, ge=0)
    supplier: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=500)
    postponed_to: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "AlertActionRequest":
        if self.action_type == "ordered" and self.quantity is None:
            raise ValueError("quantity es requerido cuando action_type='ordered'")
        if self.action_type == "dismissed" and not self.reason:
            raise ValueError("reason es requerido cuando action_type='dismissed'")
        if self.action_type == "postponed" and self.postponed_to is None:
            raise ValueError("postponed_to es requerido cuando action_type='postponed'")
        return self


class AlertActionResponse(BaseModel):
    """Respuesta de POST /alerts/{alert_id}/action (201 creado / 200 replay)."""

    id: int
    alert_id: str
    sku: str
    action_type: str
    user_id: str
    created_at: datetime


class AlertActionItem(BaseModel):
    """Item individual en la lista de acciones del usuario."""

    id: int
    alert_id: str
    sku: str
    action_type: str
    quantity: Decimal | None = None
    supplier: str | None = None
    reason: str | None = None
    postponed_to: date | None = None
    notes: str | None = None
    created_at: datetime


class AlertActionListResponse(BaseModel):
    """Respuesta paginada de GET /alerts/actions/me."""

    items: list[AlertActionItem]
    total: int
    limit: int
    offset: int


class IdempotencyKey(str):
    """UUID v4 usado como idempotency-key.

    Se valida con regex en el router antes de usar.
    """

    @classmethod
    def generate(cls) -> str:
        return str(uuid.uuid4())
