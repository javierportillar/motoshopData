"""Schemas de ventas."""

from __future__ import annotations

from pydantic import BaseModel


class SaleOut(BaseModel):
    numnum: str
    fecdoc: str | None = None
    nitter: str | None = None
    estdoc: str | None = None
    valtotal: str | None = None


class SalesPage(BaseModel):
    items: list[SaleOut]
    total: int
    limit: int
