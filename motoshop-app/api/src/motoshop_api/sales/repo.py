"""Repositorio de ventas — lee facventas (sólo las válidas).

Convención legacy de Hermes (``docs/hermes/hermes_reverse_engineering_blueprint.md``):
``facventas.estfven`` vale **B = válida** (7.291 filas) y **A = anulada** (16).
El mismo criterio usa la anulación, que marca ``estfven='A'`` al anular
(``erp/annulment/repo.py``). Este repositorio filtraba por ``'A'``: devolvía las
anuladas y escondía las ventas reales.
"""

from __future__ import annotations

from sqlalchemy import Engine, select

from motoshop_api.db.tables import facventas

#: ``facventas.estfven`` de un documento válido (``A`` = anulada).
ESTADO_VALIDA = "B"


def _stmt_validas(limit: int):
    """Consulta base: sólo documentos válidos, del más nuevo al más viejo."""
    return (
        select(facventas)
        .where(facventas.c.estfven == ESTADO_VALIDA)
        .order_by(facventas.c.fecfven.desc())
        .limit(limit)
    )


class SalesRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_recent(self, since: str | None = None, limit: int = 50) -> list[dict]:
        stmt = _stmt_validas(limit)
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
