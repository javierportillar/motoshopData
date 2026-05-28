"""Repositorio de stock — lee auxinventario + bodegas."""

from __future__ import annotations

from sqlalchemy import Engine, Float, cast, select, func

from motoshop_api.db.tables import auxinventario, bodegas


class StockRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_stock_by_sku(self, sku: str) -> dict:
        """Retorna stock total y desglose por bodega para un SKU."""
        stmt = (
            select(
                auxinventario.c.codbod,
                bodegas.c.nombod,
                func.SUM(cast(auxinventario.c.canactu, Float)).label("cantidad"),
            )
            .join(bodegas, auxinventario.c.codbod == bodegas.c.codbod)
            .where(auxinventario.c.codprod == sku)
            .group_by(auxinventario.c.codbod, bodegas.c.nombod)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        by_bodega = [
            {"codbod": r["codbod"], "nombod": r["nombod"], "cantidad": float(r["cantidad"] or 0)}
            for r in rows
        ]
        total = sum(b["cantidad"] for b in by_bodega)

        return {
            "sku": sku,
            "total": total,
            "by_bodega": by_bodega,
        }


class FakeStockRepo:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    def get_stock_by_sku(self, sku: str) -> dict:
        return self._data.get(sku, {"sku": sku, "total": 0, "by_bodega": []})
