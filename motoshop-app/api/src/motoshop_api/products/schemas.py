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


class SemanticMatch(BaseModel):
    codprod: str
    nomprod: str
    score: float  # cosine similarity (0 = unrelated, 1 = identical)


class SemanticSearchResponse(BaseModel):
    query: str
    results: list[SemanticMatch]
    total: int


class MovementItem(BaseModel):
    """Un movimiento de entrada (compra) o salida (venta) de un producto."""

    tipo: str  # "venta" | "compra"
    fecha: str
    documento: str
    cantidad: float
    valor_unitario: float
    total: float


class ProductMovementsResponse(BaseModel):
    sku: str
    nom_producto: str | None = None
    ventas: list[MovementItem]
    compras: list[MovementItem]
    stock_actual: float = 0
    total_ventas: float = 0  # suma de UNIDADES vendidas, no documentos
    total_compras: float = 0  # suma de UNIDADES compradas, no documentos
    ultimo_costo_unitario: float | None = None
    ultimo_precio_venta: float | None = None
