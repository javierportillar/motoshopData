"""Coincidencia por valor (S7 · 7.1): la regla, sola y explicable.

Es la pregunta más simple de la conciliación y la que la UI del POS necesita
para **prellenar** la captura del pago: «¿hay un ingreso por este importe?».
La respuesta vive aquí, en una **función pura**: sin base de datos, sin
navegador, sin red. Por eso se prueba offline y por eso el worker del nodo y
el endpoint de candidatos comparten **la misma regla**.

Reglas (spec `erp-bank-reconciliation`):

- sólo los movimientos **positivos** son candidatos: un egreso con el mismo
  importe no es un pago recibido;
- el importe se compara con `Decimal` **exacto**: nunca `float`, nunca
  tolerancia (ADR-0008-07);
- un movimiento **fuera de la ventana** no es candidato;
- un candidato ⇒ coincidencia única; dos o más ⇒ **ambigua**: se listan todos
  y **no se elige ninguno** (la elección es del operador en el POS);
- cero ⇒ lista vacía (no es un error).

El `id` del candidato es el identificador de **dominio** del movimiento
(`uuid5` de `tenant:id_externo`): es el mismo id con el que la API apunta a la
fila, así que la UI puede llevar el candidato al conciliador sin ambigüedad.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from motoshop_api.erp.bankreconciliation.schemas import BankMovementOut
from motoshop_api.erp.bankreconciliation.store import id_dominio_movimiento

__all__ = [
    "Candidato",
    "MovimientoCoincidible",
    "MovimientoRaspado",
    "ValueMatch",
    "desde_movimiento_persistido",
    "desde_movimiento_raspado",
    "match_by_value",
]

#: La ventana de consulta: dos cotas. Acepta día o instante (la ventana del
#: nodo es un instante; el día es su parte de fecha).
Ventana = tuple[datetime.date | datetime.datetime, datetime.date | datetime.datetime]


@dataclass(frozen=True)
class MovimientoCoincidible:
    """La forma mínima de un movimiento para la coincidencia por valor.

    Normaliza las dos formas que hay en el sistema (la leída del portal y la
    persistida) para que la regla viva en un solo sitio:

    - `id_externo` + `tenant`: identifican el movimiento en el dominio (el
      `id` que ve la API);
    - `valor`: importe exacto (`Decimal`);
    - `es_candidato_pago`: si el movimiento es un **ingreso**. En la forma
      persistida se deduce del signo; en la leída del portal lo dice el
      scraper.
    """

    id_externo: str
    tenant: str
    valor: Decimal
    pagador_nombre: str
    referencia: str
    fecha: datetime.date
    es_candidato_pago: bool

    @property
    def id(self) -> str:
        """Identificador de dominio del movimiento (`uuid5` de `tenant:id_externo`)."""
        return id_dominio_movimiento(self.tenant, self.id_externo)


@dataclass(frozen=True)
class Candidato:
    """Movimiento que puede ser el pago que se está capturando.

    - `id`: identificador de **dominio** del movimiento (el que usa la API);
    - `valor`: importe exacto (`Decimal`);
    - `pagador_nombre`: pagador (vacío si la fila no es `PAGO QR`);
    - `referencia`: referencia **sanificada** (sin el sufijo `" null"`);
    - `fecha`: día del movimiento.
    """

    id: str
    valor: Decimal
    pagador_nombre: str
    referencia: str
    fecha: datetime.date


@dataclass(frozen=True)
class ValueMatch:
    """Resultado de la coincidencia por valor.

    - `ambiguo`: `True` cuando hay dos o más candidatos (la elección es del
      operador, nunca del sistema);
    - `candidatos`: **todos** los candidatos de la ventana (en el caso
      ambiguo, todos; nunca uno elegido);
    - `ventana`: la ventana aplicada (normalizada a días).
    """

    ambiguo: bool
    candidatos: list[Candidato]
    ventana: tuple[datetime.date, datetime.date]

    @property
    def seleccionado(self) -> Candidato | None:
        """El candidato único, o `None` si no hay ninguno o hay más de uno."""
        return self.candidatos[0] if len(self.candidatos) == 1 else None


class MovimientoRaspado(Protocol):
    """Lo mínimo de un movimiento leído del portal que usa el matching.

    Es un `Protocol` (y no la clase del scraper) para que este módulo siga
    siendo puro: no arrastra el navegador ni la bóveda de credenciales.
    """

    id_externo: str
    fecha: datetime.date
    valor: Decimal
    pagador_nombre: str
    referencia: str
    es_candidato_pago: bool


def desde_movimiento_raspado(
    movimiento: MovimientoRaspado,
    tenant: str,
) -> MovimientoCoincidible:
    """Movimiento leído del portal → forma normalizada del matching."""
    return MovimientoCoincidible(
        id_externo=movimiento.id_externo,
        tenant=tenant,
        valor=movimiento.valor,
        pagador_nombre=movimiento.pagador_nombre,
        referencia=movimiento.referencia,
        fecha=movimiento.fecha,
        es_candidato_pago=movimiento.es_candidato_pago,
    )


def desde_movimiento_persistido(movimiento: BankMovementOut) -> MovimientoCoincidible:
    """Movimiento persistido → forma normalizada del matching.

    La fila persistida no trae la bandera de "candidato de pago": se deduce
    del **signo** del importe (un ingreso es un importe positivo).
    """
    return MovimientoCoincidible(
        id_externo=movimiento.id_externo,
        tenant=movimiento.tenant,
        valor=movimiento.valor,
        pagador_nombre=movimiento.pagador_nombre,
        referencia=movimiento.referencia,
        fecha=movimiento.fecha_movimiento,
        es_candidato_pago=movimiento.valor > 0,
    )


def match_by_value(
    valor: Decimal,
    movimientos: Sequence[MovimientoCoincidible],
    ventana: Ventana,
) -> ValueMatch:
    """Candidatos con **el mismo importe** dentro de la ventana.

    Args:
        valor: importe que se está cobrando (`Decimal` exacto).
        movimientos: movimientos a considerar (los de cualquier signo).
        ventana: cota inferior y superior de la consulta.

    Returns:
        La coincidencia: `ambiguo` cuando hay dos o más candidatos (y en ese
        caso **no** se elige ninguno), la lista de candidatos y la ventana
        aplicada.
    """
    inicio, fin = _a_dia(ventana[0]), _a_dia(ventana[1])
    candidatos = [
        Candidato(
            id=movimiento.id,
            valor=movimiento.valor,
            pagador_nombre=movimiento.pagador_nombre,
            referencia=movimiento.referencia,
            fecha=movimiento.fecha,
        )
        for movimiento in movimientos
        if movimiento.es_candidato_pago
        and movimiento.valor > 0
        and movimiento.valor == valor
        and inicio <= movimiento.fecha <= fin
    ]
    return ValueMatch(
        ambiguo=len(candidatos) > 1,
        candidatos=candidatos,
        ventana=(inicio, fin),
    )


def _a_dia(cota: datetime.date | datetime.datetime) -> datetime.date:
    """Una cota de la ventana (día o instante) → su día."""
    if isinstance(cota, datetime.datetime):
        return cota.date()
    return cota
