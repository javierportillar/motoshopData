"""Repositorio de stock — lee productos + bodegas (sin auxinventario, no tiene stock real)."""

from __future__ import annotations

from sqlalchemy import Engine, select

from motoshop_api.db.tables import productos, bodegas


class StockRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_stock_by_sku(self, sku: str) -> dict:
        stmt = select(productos).where(productos.c.codprod == sku)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
            if not row:
                return {"sku": sku, "total": 0, "by_bodega": []}

            bodegas_stmt = select(bodegas)
            bodegas_rows = conn.execute(bodegas_stmt).mappings().all()

        return {
            "sku": sku,
            "nomprod": row.get("nomprod", ""),
            "total": 0,
            "by_bodega": [
                {"codbod": b["codbod"], "nombod": b["nombod"], "cantidad": 0}
                for b in bodegas_rows
            ],
        }


class FakeStockRepo:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    def get_stock_by_sku(self, sku: str) -> dict:
        return self._data.get(sku, {"sku": sku, "total": 0, "by_bodega": []})
