"""Coincidencia por valor (S7 · 7.1): la regla, sola y explicable.

El matching por valor es una **función pura**: no toca la base de datos, ni el
navegador, ni la red. Por eso se prueba aquí, offline, con filas del portal ya
interpretadas por el parser.

Se verifica lo que la spec `erp-bank-reconciliation` exige:

- un importe que aparece **dentro** de la ventana devuelve ese candidato;
- un importe que no aparece devuelve **ningún** candidato (no es un error);
- un movimiento con el mismo valor **fuera** de la ventana (el de ayer) no es
  candidato;
- dos movimientos con el mismo valor dan una coincidencia **ambigua**: se
  listan los dos y **no se elige ninguno**;
- el candidato expone el **pagador** (lo que va detrás de `PAGO QR`) y la
  **referencia saneada** (sin el sufijo `" null"` del portal);
- una fila que no es `PAGO QR` expone el pagador **vacío**.

Los importes se comparan con `Decimal` **exacto**: nunca `float`, nunca
tolerancia (ADR-0008-07).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from motoshop_api.erp.bankreconciliation.parser import parse_movement_row
from motoshop_api.erp.bankreconciliation.store import id_dominio_movimiento
from motoshop_api.erp.bankreconciliation.value_match import (
    MovimientoCoincidible,
    match_by_value,
)

TENANT = "motoshop"
VALOR = Decimal("458200.00")

#: La ventana de consulta del día (el default de la spec).
VENTANA = (datetime.date(2026, 10, 21), datetime.date(2026, 10, 21))

#: Fila real del portal: `PAGO QR <pagador>` con referencia sufijo `" null"`.
FILA_PAGO_QR = [
    "21 oct 2026",
    "PAGO QR CRISTOPHER BENAMIDES P",
    "0092055984 null",
    "$ 458.200,00",
]

#: Fila real del portal que **no** es un pago QR: no trae pagador.
FILA_SIN_PAGO_QR = [
    "21 oct 2026",
    "CONSIGNACION CORRESPONSAL CB",
    "0092055984",
    "$ 458.200,00",
]


def _movimiento(celdas: list[str], *, id_externo: str = "m1") -> MovimientoCoincidible:
    """Fila del portal → movimiento normalizado para el matching.

    El parser deja el importe exacto, el pagador (sólo en `PAGO QR`) y la
    referencia **sanificada** (sin el sufijo `" null"`).
    """
    fila = parse_movement_row(celdas)
    return MovimientoCoincidible(
        id_externo=id_externo,
        tenant=TENANT,
        valor=fila.valor,
        pagador_nombre=fila.pagador_nombre,
        referencia=fila.referencia,
        fecha=fila.fecha,
        es_candidato_pago=fila.es_candidato_pago,
    )


def test_valor_igual_dentro_de_la_ventana_devuelve_el_candidato() -> None:
    """El importe buscado devuelve **ese** movimiento como único candidato."""
    movimiento = _movimiento(FILA_PAGO_QR)

    resultado = match_by_value(VALOR, [movimiento], VENTANA)

    assert resultado.ambiguo is False
    assert len(resultado.candidatos) == 1
    candidato = resultado.candidatos[0]
    assert candidato.valor == Decimal("458200.00")
    assert candidato.fecha == datetime.date(2026, 10, 21)
    # El id es el identificador de dominio: el mismo que usa la API.
    assert candidato.id == id_dominio_movimiento(TENANT, "m1")
    # Con un solo candidato, la coincidencia es una selección (no ambigua).
    assert resultado.seleccionado is candidato


def test_sin_coincidencias_en_la_ventana_no_devuelve_candidatos() -> None:
    """Un importe que no aparece devuelve lista vacía (y no es ambiguo)."""
    movimiento = _movimiento(FILA_PAGO_QR)

    resultado = match_by_value(Decimal("999999.00"), [movimiento], VENTANA)

    assert resultado.candidatos == []
    assert resultado.ambiguo is False
    assert resultado.seleccionado is None


def test_mismo_valor_de_ayer_no_es_candidato() -> None:
    """Un movimiento con el mismo valor **fuera** de la ventana no es candidato."""
    ayer = _movimiento(
        [
            "20 oct 2026",
            "PAGO QR CRISTOPHER BENAMIDES P",
            "0092055984",
            "$ 458.200,00",
        ],
        id_externo="m2",
    )

    resultado = match_by_value(VALOR, [ayer], VENTANA)

    assert resultado.candidatos == []
    assert resultado.ambiguo is False


def test_dos_movimientos_con_el_mismo_valor_reporta_ambiguedad_y_lista_ambos_sin_elegir() -> (
    None
):
    """Dos movimientos del mismo importe: la coincidencia es ambigua y no elige."""
    primero = _movimiento(FILA_PAGO_QR, id_externo="m1")
    segundo = _movimiento(FILA_PAGO_QR, id_externo="m2")

    resultado = match_by_value(VALOR, [primero, segundo], VENTANA)

    assert resultado.ambiguo is True
    assert len(resultado.candidatos) == 2
    # La elección es del operador en el POS: aquí no se elige ninguno.
    assert resultado.seleccionado is None
    assert {candidato.id for candidato in resultado.candidatos} == {
        id_dominio_movimiento(TENANT, "m1"),
        id_dominio_movimiento(TENANT, "m2"),
    }


def test_candidato_expone_pagador_y_referencia_saneada() -> None:
    """El candidato expone el pagador y la referencia sin el sufijo `" null"`."""
    movimiento = _movimiento(FILA_PAGO_QR)

    resultado = match_by_value(VALOR, [movimiento], VENTANA)

    candidato = resultado.candidatos[0]
    assert candidato.pagador_nombre == "CRISTOPHER BENAMIDES P"
    assert candidato.referencia == "0092055984"


def test_fila_no_pago_qr_expone_pagador_vacio() -> None:
    """Una fila que no es `PAGO QR` expone el pagador vacío (no inventa uno)."""
    movimiento = _movimiento(FILA_SIN_PAGO_QR)

    resultado = match_by_value(VALOR, [movimiento], VENTANA)

    candidato = resultado.candidatos[0]
    assert candidato.pagador_nombre == ""
    assert candidato.referencia == "0092055984"
