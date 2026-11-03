"""El repositorio de ventas tiene que leer las VÁLIDAS, no las anuladas.

Convención legacy de Hermes (blueprint §3): ``facventas.estfven`` vale
**B = válida** y **A = anulada**; la anulación marca ``'A'`` al anular. El
repositorio filtraba por ``'A'`` y devolvía exactamente lo contrario.
"""

from __future__ import annotations

from sqlalchemy.dialects import mysql

from motoshop_api.sales.repo import ESTADO_VALIDA, _stmt_validas


def _sql(limit: int = 10) -> str:
    return str(
        _stmt_validas(limit).compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_el_estado_valido_es_b() -> None:
    assert ESTADO_VALIDA == "B"


def test_la_consulta_filtra_por_validas() -> None:
    sql = _sql()
    assert "estfven = 'B'" in sql
    assert "estfven = 'A'" not in sql


def test_la_consulta_ordena_y_limita() -> None:
    sql = _sql(7)
    assert "ORDER BY" in sql and "fecfven DESC" in sql
    assert "LIMIT 7" in sql
