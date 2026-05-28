"""Repositorio de ventas — lee facventas (solo activas)."""

from __future__ import annotations

from sqlalchemy import Engine, select

from motoshop_api.db.tables import facventas


class SalesRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_recent(self, since: str | None = None, limit: int = 50) -> list[dict]:
        stmt = (
            select(facventas)
            .where(facventas.c.estfven == "A")
            .order_by(facventas.c.fecfven.desc())
            .limit(limit)
        )
        if since:
            stmt = stmt.where(facventas.c.fecfven >= since)

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
            return [dict(r) for r in rows]


class FakeSalesRepo:
    def __init__(self, items: list[dict] | None = None) -> None:
        self._items = items or []

    def get_recent(self, since: str | None = None, limit: int = 50) -> list[dict]:
        result = self._items
        if since:
            result = [i for i in result if i.get("fecfven", "") >= since]
        return result[:limit]
