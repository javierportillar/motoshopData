"""Tests del parser puro de los movimientos del portal Bancolombia (slice S5).

El parser no toca el disco ni la red: recibe las **celdas** de una fila de la
tabla "Tus movimientos" y devuelve un movimiento tipado. Todos los importes son
`Decimal` exactos (nunca `float`) y las fechas son `datetime.date`.

Las columnas del portal, en el orden en que las renderiza la tabla, son:

    Fecha | Descripción | Referencia | Valor

Los datos que aparecen en los tests son los reales del portal (capturas del
operador): referencias como `0092055984 null` o `0000000000`, descripciones
como `PAGO QR LIZETH STEPHANIA PORTI` e importes en formato colombiano
(`$ 458.200,00`, `- $ 7.590,00`).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from motoshop_api.erp.bankreconciliation.parser import (
    FormatoDeMovimientoInvalido,
    MovementDirection,
    parse_colombian_amount,
    parse_movement_row,
    sanitize_reference,
)

#: Fila real del portal: Fecha | Descripción | Referencia | Valor.
FILA_PAGO_QR = [
    "10/02/2025",
    "PAGO QR LIZETH STEPHANIA PORTI",
    "0092055984 null",
    "$ 458.200,00",
]

#: Las descripciones reales que devuelve el portal, con el pagador esperado.
DESCRIPCIONES_REALES = [
    ("PAGO QR LIZETH STEPHANIA PORTI", "LIZETH STEPHANIA PORTI"),
    ("PAGO QR CRISTOPHER BENAMIDES P", "CRISTOPHER BENAMIDES P"),
    ("PAGO QR MARIA LUISA ZAMORA PAN", "MARIA LUISA ZAMORA PAN"),
    ("PAGO QR SHANON ALEJAN", "SHANON ALEJAN"),
    ("COMISION TRASLADO OTROS BANCOS", ""),
    ("COMPRA INTL APPLE.COM/BILL", ""),
    ("CONSIGNACION CORRESPONSAL CB", ""),
    ("PAGO PSE ASOPAGOS", ""),
    ("TRASLADO VIRTUAL OTROS BANCOS", ""),
    ("ABONO INTERESES AHORROS", ""),
    ("IVA COMIS TRASLADO OTROS BCOS", ""),
]


def test_parse_colombian_amount_con_separadores() -> None:
    """`$ 458.200,00` son 458200.00 exactos."""
    assert parse_colombian_amount("$ 458.200,00") == Decimal("458200.00")


def test_parse_colombian_amount_negativo_con_signo() -> None:
    """El signo va adelante: `- $ 7.590,00` es un egreso de 7590.00."""
    assert parse_colombian_amount("- $ 7.590,00") == Decimal("-7590.00")


def test_importe_no_sufre_redondeo_de_float() -> None:
    """`1.005,50` no puede pasar por `float` (que daría 1005.4999999...)."""
    valor = parse_colombian_amount(" $ 1.005,50 ")

    assert valor == Decimal("1005.50")
    assert str(valor) == "1005.50"
    assert valor.as_tuple().exponent == -2
    assert valor != Decimal("1005.4999999")


def test_parse_movement_row_pago_qr_extrae_pagador_y_referencia() -> None:
    """El pagador y la referencia viven en columnas distintas."""
    movimiento = parse_movement_row(
        ["PAGO QR LIZETH STEPHANIA PORTI", "0092055984 null", "$ 458.200,00", "10/02/2025"]
    )

    assert movimiento.pagador_nombre == "LIZETH STEPHANIA PORTI"
    assert movimiento.referencia == "0092055984"
    assert movimiento.valor == Decimal("458200.00")
    assert movimiento.fecha == datetime.date(2025, 2, 10)
    assert movimiento.referencia_utilizable is True
    assert movimiento.direccion == MovementDirection.INGRESO


def test_parse_movement_row_referencia_de_solo_ceros_queda_no_utilizable() -> None:
    """`0000000000` no sirve para conciliar: no es utilizable."""
    movimiento = parse_movement_row(
        ["12/02/2025", "COMPRA INTL APPLE.COM/BILL", "0000000000", "- $ 45.000,00"]
    )

    assert movimiento.referencia == "0000000000"
    assert movimiento.referencia_utilizable is False


def test_parse_movement_row_descripcion_no_pagadora_deja_pagador_vacio() -> None:
    """Una descripción que no es "PAGO QR" deja el pagador vacío, sin excepción."""
    movimiento = parse_movement_row(
        ["10/02/2025", "ABONO INTERESES AHORROS", "760321133", "$ 1.200,00"]
    )

    assert movimiento.pagador_nombre == ""
    assert movimiento.descripcion == "ABONO INTERESES AHORROS"


def test_movimiento_negativo_es_egreso_y_no_candidato_de_pago() -> None:
    """Un egreso nunca es candidato de pago."""
    movimiento = parse_movement_row(
        ["11/02/2025", "COMISION TRASLADO OTROS BANCOS", "0000000000", "- $ 7.590,00"]
    )

    assert movimiento.direccion == MovementDirection.EGRESO
    assert movimiento.direccion == "egreso"
    assert movimiento.es_candidato_pago is False


def test_movimiento_positivo_es_ingreso() -> None:
    """Un valor positivo es un ingreso."""
    movimiento = parse_movement_row(
        ["12/02/2025", "CONSIGNACION CORRESPONSAL CB", "760321133", "$ 458.200,00"]
    )

    assert movimiento.direccion == MovementDirection.INGRESO
    assert movimiento.direccion == "ingreso"
    assert movimiento.es_candidato_pago is True


def test_sanitize_reference_quita_el_sufijo_null() -> None:
    """El portal añade `" null"` cuando la referencia no existe."""
    assert sanitize_reference("0092055984 null") == "0092055984"


# --- Casos límite -----------------------------------------------------------


def test_parse_colombian_amount_ignora_los_espacios_sobrantes() -> None:
    """Los espacios del HTML no cambian el importe."""
    assert parse_colombian_amount("  $ 458.200,00  ") == Decimal("458200.00")
    assert parse_colombian_amount("$1.234.567,89") == Decimal("1234567.89")


def test_parse_colombian_amount_tolera_el_espacio_duro_del_html() -> None:
    """El portal a veces pega un espacio duro (no separable) en el importe."""
    assert parse_colombian_amount("$ 1\u00a0005,50") == Decimal("1005.50")


def test_parse_colombian_amount_rechaza_un_importe_ilegible() -> None:
    """Un importe que no es un número es un error explícito, no un cero."""
    with pytest.raises(FormatoDeMovimientoInvalido):
        parse_colombian_amount("no hay importe")


def test_referencia_vacia_no_es_utilizable() -> None:
    """Sin referencia no hay conciliación posible."""
    movimiento = parse_movement_row(["12/02/2025", "ABONO INTERESES AHORROS", "", "$ 1.200,00"])

    assert movimiento.referencia == ""
    assert movimiento.referencia_utilizable is False


def test_el_pagador_solo_se_extrae_de_un_pago_qr() -> None:
    """`PAGO PSE` es un pago del banco, no un pagador con nombre."""
    movimiento = parse_movement_row(
        ["15/02/2025", "PAGO PSE ASOPAGOS", "760321133", "$ 320.000,00"]
    )

    assert movimiento.pagador_nombre == ""


def test_descripcion_que_solo_contiene_pago_qr_no_extrae_pagador() -> None:
    """El pagador sale sólo si la descripción EMPIEZA con "PAGO QR"."""
    movimiento = parse_movement_row(
        ["15/02/2025", "ABONO INTERESES AHORROS (PAGO QR)", "760321133", "$ 320.000,00"]
    )

    assert movimiento.pagador_nombre == ""


def test_sanitize_reference_no_quita_el_sufijo_null_si_no_es_final() -> None:
    """El sufijo "null" sólo se quita cuando está al final de la referencia."""
    assert sanitize_reference("0092055 null 984") == "0092055 null 984"


def test_sanitize_reference_quita_el_sufijo_null_sin_espacio() -> None:
    """El portal también pega el "null" sin espacio."""
    assert sanitize_reference("0092055984null") == "0092055984"


def test_sanitize_reference_normaliza_los_espacios() -> None:
    """La referencia se devuelve limpia y sin espacios redundantes."""
    assert sanitize_reference("  0092055984  ") == "0092055984"
    assert sanitize_reference("null") == ""


def test_parse_movement_row_acepta_el_orden_de_columnas_del_portal() -> None:
    """El orden real del portal es Fecha | Descripción | Referencia | Valor."""
    movimiento = parse_movement_row(FILA_PAGO_QR)

    assert movimiento.pagador_nombre == "LIZETH STEPHANIA PORTI"
    assert movimiento.referencia == "0092055984"
    assert movimiento.valor == Decimal("458200.00")
    assert movimiento.fecha == datetime.date(2025, 2, 10)


def test_parse_movement_row_rechaza_una_fila_sin_importe() -> None:
    """Una fila sin importe no es un movimiento: hay que avisar."""
    with pytest.raises(FormatoDeMovimientoInvalido):
        parse_movement_row(["10/02/2025", "PAGO QR ALGO"])


def test_movimiento_con_valor_cero_no_es_candidato_de_pago() -> None:
    """Un importe de cero no es dinero que entrada: no se concilia."""
    movimiento = parse_movement_row(
        ["12/02/2025", "ABONO INTERESES AHORROS", "760321133", "$ 0,00"]
    )

    assert movimiento.valor == Decimal("0.00")
    assert movimiento.es_candidato_pago is False


@pytest.mark.parametrize(("descripcion", "pagador"), DESCRIPCIONES_REALES)
def test_las_descripciones_reales_del_portal_se_clasifican_bien(
    descripcion: str, pagador: str
) -> None:
    """Cada descripción real del portal produce el pagador que corresponde."""
    movimiento = parse_movement_row(
        ["12/02/2025", descripcion, "0092055984 null", "$ 458.200,00"]
    )

    assert movimiento.pagador_nombre == pagador
    assert movimiento.descripcion == descripcion
