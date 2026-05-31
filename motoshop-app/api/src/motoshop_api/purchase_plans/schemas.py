"""Schemas para purchase_plans CRUD."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PurchasePlanItem(BaseModel):
    sku: str
    nombre: str
    cantidad: int
    costo_unitario: float | None = None


class PurchasePlanCreate(BaseModel):
    plan_name: str = Field(min_length=1, max_length=255)
    items: list[PurchasePlanItem] = Field(min_length=1)
    total_skus: int
    total_value: float


class PurchasePlanResponse(BaseModel):
    id: int
    created_by: str
    created_at: datetime
    plan_name: str
    total_skus: int
    total_value: float
    items: Any  # JSON
    status: str  # draft | approved | sent | received


class PurchasePlanListResponse(BaseModel):
    items: list[PurchasePlanResponse]
    total: int


class PurchasePlanStatusUpdate(BaseModel):
    status: str = Field(pattern="^(approved|sent|received)$")
