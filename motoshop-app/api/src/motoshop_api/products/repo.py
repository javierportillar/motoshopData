"""Repositorio de productos — acceso a MySQL vía SQLAlchemy core."""

from __future__ import annotations

from sqlalchemy import Engine, select, func

from motoshop_api.db.tables import productos


class ProductsRepo:
    """Repositorio de lectura de productos."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(self, query: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        """Busca productos por nombre/código con paginación."""
        stmt = select(productos)
        if query:
            search = f"%{query}%"
            stmt = stmt.where(
                productos.c.nomprod.ilike(search) | productos.c.codprod.ilike(search)
            )
        stmt = stmt.limit(limit).offset(offset)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
            return [dict(r) for r in rows]

    def count(self, query: str | None = None) -> int:
        """Cuenta productos que coinciden con la búsqueda."""
        stmt = select(func.count()).select_from(productos)
        if query:
            search = f"%{query}%"
            stmt = stmt.where(
                productos.c.nomprod.ilike(search) | productos.c.codprod.ilike(search)
            )
        with self._engine.connect() as conn:
            return conn.execute(stmt).scalar() or 0

    def get_by_sku(self, sku: str) -> dict | None:
        """Retorna un producto por código exacto."""
        stmt = select(productos).where(productos.c.codprod == sku)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
            return dict(row) if row else None


class FakeProductsRepo:
    """Repo fake para tests unitarios."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self._items = items or []

    def search(self, query: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        result = self._items
        if query:
            q = query.lower()
            result = [i for i in result if q in i.get("nomprod", "").lower() or q in i.get("codprod", "").lower()]
        return result[offset : offset + limit]

    def count(self, query: str | None = None) -> int:
        result = self._items
        if query:
            q = query.lower()
            result = [i for i in result if q in i.get("nomprod", "").lower() or q in i.get("codprod", "").lower()]
        return len(result)

    def get_by_sku(self, sku: str) -> dict | None:
        for i in self._items:
            if i.get("codprod") == sku:
                return i
        return None
