"""Schemas de productos."""

from __future__ import annotations

from pydantic import BaseModel


class ProductOut(BaseModel):
    codprod: str
    nomprod: str | None = None
    codbar: str | None = None


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int
