"""Repositorio de stock — lee auxinventario para cantidades.

Nota de diseño: auxinventario es una tabla de movimientos/auxiliar de inventario.
No todas las tablas de productos tienen registros en auxinventario.
Cuando un producto no tiene registros, se retorna total=0.
La columna codbod está vacía en la BD actual, por lo que no se puede
desglosar por bodega. Se retorna una lista vacía de by_bodega.

Cache: TTLCache(maxsize=200, ttl=300) — stock visible puede estar hasta
5 min desactualizado. Trade-off aceptable para operación de tienda.
No thread-safe, pero FastAPI+SQLAlchemy sync no tiene race condition real.
"""

from __future__ import annotations

from cachetools import TTLCache
from sqlalchemy import Engine, func, select

from motoshop_api.db.tables import auxinventario, productos

# Cache en memoria. 200 SKUs distintos × 5 min TTL.
_stock_cache: TTLCache[str, dict] = TTLCache(maxsize=200, ttl=300)


class StockRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_stock_by_sku(self, sku: str) -> dict:
        cached = _stock_cache.get(sku)
        if cached is not None:
            return cached

        prod_stmt = select(productos).where(productos.c.codprod == sku)
        with self._engine.connect() as conn:
            prod_row = conn.execute(prod_stmt).mappings().first()
            if not prod_row:
                result = {"sku": sku, "nomprod": None, "total": 0, "by_bodega": []}
                _stock_cache[sku] = result
                return result

            nomprod = prod_row.get("nomprod", "")

            try:
                stock_stmt = (
                    select(
                        auxinventario.c.codprod,
                        func.coalesce(auxinventario.c.codbod, "SIN_BODEGA").label("codbod"),
                        func.sum(auxinventario.c.valor3).label("cantidad"),
                    )
                    .where(auxinventario.c.codprod == sku)
                    .group_by(auxinventario.c.codprod, auxinventario.c.codbod)
                )
                stock_rows = conn.execute(stock_stmt).mappings().all()

                if not stock_rows:
                    result = {"sku": sku, "nomprod": nomprod, "total": 0, "by_bodega": []}
                    _stock_cache[sku] = result
                    return result

                total = sum(float(r["cantidad"] or 0) for r in stock_rows)
                by_bodega = [
                    {
                        "codbod": r["codbod"],
                        "nombod": r["codbod"],
                        "cantidad": float(r["cantidad"] or 0),
                    }
                    for r in stock_rows
                ]

                result = {"sku": sku, "nomprod": nomprod, "total": total, "by_bodega": by_bodega}
                _stock_cache[sku] = result
                return result
            except Exception:
                return {"sku": sku, "nomprod": nomprod, "total": 0, "by_bodega": []}


def clear_stock_cache() -> None:
    _stock_cache.clear()


class FakeStockRepo:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    def get_stock_by_sku(self, sku: str) -> dict:
        return self._data.get(sku, {"sku": sku, "nomprod": None, "total": 0, "by_bodega": []})
