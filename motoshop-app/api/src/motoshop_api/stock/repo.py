"""Repositorio de stock — lee auxinventario para cantidades.

Nota de diseño: auxinventario es una tabla de movimientos/auxiliar de inventario.
No todas las tablas de productos tienen registros en auxinventario.
Cuando un producto no tiene registros, se retorna total=0.
La columna codbod está vacía en la BD actual, por lo que no se puede
desglosar por bodega. Se retorna una lista vacía de by_bodega.

Limitación documentada: F1-FIX1 (R2).
"""

from __future__ import annotations

from sqlalchemy import Engine, select, func

from motoshop_api.db.tables import productos, bodegas, auxinventario


class StockRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_stock_by_sku(self, sku: str) -> dict:
        # 1. Verificar que el producto existe
        prod_stmt = select(productos).where(productos.c.codprod == sku)
        with self._engine.connect() as conn:
            prod_row = conn.execute(prod_stmt).mappings().first()
            if not prod_row:
                return {"sku": sku, "nomprod": None, "total": 0, "by_bodega": []}

            nomprod = prod_row.get("nomprod", "")

            # 2. Buscar registros en auxinventario para este producto
            # auxinventario tiene 'valor3' como columna de cantidad
            # codbod puede estar vacío en la BD actual
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
                    return {"sku": sku, "nomprod": nomprod, "total": 0, "by_bodega": []}

                total = sum(float(r["cantidad"] or 0) for r in stock_rows)
                by_bodega = [
                    {"codbod": r["codbod"], "nombod": r["codbod"], "cantidad": float(r["cantidad"] or 0)}
                    for r in stock_rows
                ]

                return {"sku": sku, "nomprod": nomprod, "total": total, "by_bodega": by_bodega}
            except Exception:
                return {"sku": sku, "nomprod": nomprod, "total": 0, "by_bodega": []}


class FakeStockRepo:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    def get_stock_by_sku(self, sku: str) -> dict:
        return self._data.get(sku, {"sku": sku, "nomprod": None, "total": 0, "by_bodega": []})
