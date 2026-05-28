"""Schemas de stock."""

from __future__ import annotations

from pydantic import BaseModel


class BodegaStock(BaseModel):
    codbod: str
    nombod: str | None = None
    cantidad: float


class StockResponse(BaseModel):
    sku: str
    total: float
    by_bodega: list[BodegaStock]
