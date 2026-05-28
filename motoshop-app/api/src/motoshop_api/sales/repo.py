"""Repositorio de ventas — lee facventas (solo activas)."""

from __future__ import annotations

from sqlalchemy import Engine, select, func

from motoshop_api.db.tables import facventas


class SalesRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_recent(self, since: str | None = None, limit: int = 50) -> list[dict]:
        """Retorna las N ventas más recientes (estdoc='A')."""
        stmt = (
            select(facventas)
            .where(facventas.c.estdoc == "A")
            .order_by(facventas.c.fecdoc.desc())
            .limit(limit)
        )
        if since:
            stmt = stmt.where(facventas.c.fecdoc >= since)

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
            return [dict(r) for r in rows]


class FakeSalesRepo:
    def __init__(self, items: list[dict] | None = None) -> None:
        self._items = items or []

    def get_recent(self, since: str | None = None, limit: int = 50) -> list[dict]:
        result = self._items
        if since:
            result = [i for i in result if i.get("fecdoc", "") >= since]
        return result[:limit]
