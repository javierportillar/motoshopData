"""Pydantic schemas for manual MasVital expiry-lot tracking."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _LotBase(BaseModel):
    """Fields exposed for an inventory lot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant: str
    product_sku: str
    # Product catalog enrichment is intentionally optional; lot persistence stores SKU only.
    product_name: str | None = None
    purchase_order_ref: str
    lot_code: str
    expires_on: date
    received_on: date
    received_quantity: Decimal
    remaining_quantity: Decimal
    supplier: str | None = None
    notes: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class ExpiryLotResponse(_LotBase):
    """Single lot response."""


class ExpiryLotListResponse(BaseModel):
    """Offset-paginated lot list."""

    items: list[ExpiryLotResponse]
    total: int
    limit: int
    offset: int


class ExpiryAlertItem(ExpiryLotResponse):
    """Lot with calculated expiration horizon."""

    days_until_expiry: int


class ExpiryAlertListResponse(BaseModel):
    """Lots that expire within the requested horizon."""

    items: list[ExpiryAlertItem]
    horizon_days: int


class ReceiptCreate(BaseModel):
    """Manual receipt that establishes a lot and expiry date."""

    product_sku: str = Field(min_length=1, max_length=128)
    purchase_order_ref: str = Field(min_length=1, max_length=128)
    lot_code: str = Field(min_length=1, max_length=128)
    expires_on: date
    received_on: date | None = None
    received_quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    supplier: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("product_sku", "purchase_order_ref", "lot_code")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("supplier", "notes")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class LotAdjustmentCreate(BaseModel):
    """Manual quantity adjustment for an existing lot."""

    quantity_delta: Decimal = Field(max_digits=14, decimal_places=3)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value

    @field_validator("quantity_delta")
    @classmethod
    def reject_zero_delta(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("quantity_delta must not be zero")
        return value


class MutationLotResponse(BaseModel):
    """Lot mutation response; replayed signals idempotent retry."""

    lot: ExpiryLotResponse
    replayed: bool
