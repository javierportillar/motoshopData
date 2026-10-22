"""Tests del matching explicable (S9.1).

El puntaje es una suma de señales ponderadas; cada test aísla una señal para
probar el peso exacto sin que las demás lo contaminen.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from motoshop_api.erp.bankreconciliation.matching import (
    Candidatura,
    FacturaCandidata,
    es_sobrepago,
    normalizar_nombre,
    normalizar_referencia,
    score_candidates,
)


@dataclass
class Movimiento:
    """Movimiento del banco mínimo para el matching."""

    tenant: str = "motoshop"
    valor: Decimal = Decimal("100000.00")
    descripcion: str = ""
    referencia: str = ""
    referencia_norm: str = ""
    pagador_nombre: str = ""


def factura(
    *,
    factura_id: str = "F-1",
    tenant: str = "motoshop",
    nitter: str = "111111111",
    nombre: str = "Cliente Generico",
    saldo: Decimal = Decimal("100000.00"),
    referencia: str | None = None,
) -> FacturaCandidata:
    return FacturaCandidata(
        factura_id=factura_id,
        tenant=tenant,
        numfven=100,
        prefven="FVP",
        nitter=nitter,
        cliente_nombre=nombre,
        saldo=saldo,
        referencia=referencia,
    )


def test_normalizar_referencia_quita_sufijo_null_y_ceros_a_la_izquierda() -> None:
    assert normalizar_referencia("0092055984 null") == "92055984"
    assert normalizar_referencia("92055984") == "92055984"
    assert normalizar_referencia(None) == ""


def test_normalizar_nombre_quita_tildes_signos_y_sufijos_societarios() -> None:
    assert normalizar_nombre("Distribuidora El Sol S.A.S.") == "DISTRIBUIDORA EL SOL"
    assert normalizar_nombre("DISTRIBUIDORA EL SOL LTDA") == "DISTRIBUIDORA EL SOL"
    assert normalizar_nombre("José Pérez & Cía.") == "JOSE PEREZ CIA"


def test_match_por_referencia_exacta_encabeza_con_100() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="PAGO QR CRISTOPHER",
        referencia="0092055984 null",
        referencia_norm="0092055984",
        pagador_nombre="CRISTOPHER BENAMIDES P",
    )
    candidatas = [
        factura(
            factura_id="F-REF",
            nitter="999999999",
            nombre="OTRO CLIENTE DISTINTO",
            saldo=Decimal("50000.00"),
            referencia="92055984",
        )
    ]

    resultado = score_candidates(movimiento, candidatas)

    assert [(c.factura_id, c.score) for c in resultado] == [("F-REF", 100)]
    assert "referencia_exacta" in resultado[0].razones


def test_match_por_nit_del_pagador_alcanza_80() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="PAGO QR NIT 900.123.456-7",
        referencia="11111111",
        referencia_norm="11111111",
        pagador_nombre="PAGADOR SIN RELACION",
    )
    candidatas = [
        factura(
            factura_id="F-NIT",
            nitter="900123456",
            nombre="EMPRESA DISTINTA",
            saldo=Decimal("50000.00"),
            referencia="88888888",
        )
    ]

    resultado = score_candidates(movimiento, candidatas)

    assert resultado[0].score == 80
    assert resultado[0].razones == ("nit_pagador",)


def test_match_por_nombre_normalizado_alcanza_60() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="TRANSFERENCIA",
        referencia="11111111",
        referencia_norm="11111111",
        pagador_nombre="DISTRIBUIDORA EL SOL",
    )
    candidatas = [
        factura(
            factura_id="F-NOMBRE",
            nitter="900999999",
            nombre="Distribuidora El Sol S.A.S.",
            saldo=Decimal("50000.00"),
            referencia="88888888",
        )
    ]

    resultado = score_candidates(movimiento, candidatas)

    assert resultado[0].score == 60
    assert resultado[0].razones == ("nombre_normalizado",)


def test_match_por_importe_exacto_alcanza_40_y_por_importe_parcial_20() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="TRANSFERENCIA",
        referencia="11111111",
        referencia_norm="11111111",
        pagador_nombre="PAGADOR SIN RELACION",
    )
    exacta = factura(
        factura_id="F-EXACTA",
        nitter="900999999",
        nombre="OTRA EMPRESA",
        saldo=Decimal("100000.00"),
        referencia="88888888",
    )
    parcial = factura(
        factura_id="F-PARCIAL",
        nitter="900888888",
        nombre="TERCERA EMPRESA",
        saldo=Decimal("150000.00"),
        referencia="77777777",
    )

    resultado = {c.factura_id: c for c in score_candidates(movimiento, [exacta, parcial])}

    assert resultado["F-EXACTA"].score == 40
    assert resultado["F-EXACTA"].razones == ("importe_exacto",)
    assert resultado["F-PARCIAL"].score == 20
    assert resultado["F-PARCIAL"].razones == ("importe_parcial",)


def test_cada_candidatura_expone_las_senales_que_coincidieron() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="PAGO QR NIT 900123456",
        referencia="0092055984 null",
        referencia_norm="0092055984",
        pagador_nombre="DISTRIBUIDORA EL SOL",
    )
    candidatas = [
        factura(
            factura_id="F-TOTAL",
            nitter="900123456",
            nombre="Distribuidora El Sol S.A.S.",
            saldo=Decimal("100000.00"),
            referencia="92055984",
        )
    ]

    resultado = score_candidates(movimiento, candidatas)

    assert resultado[0].score == 100 + 80 + 60 + 40
    assert set(resultado[0].razones) == {
        "referencia_exacta",
        "nit_pagador",
        "nombre_normalizado",
        "importe_exacto",
    }


def test_dos_facturas_con_el_mismo_score_maximo_produce_ambigüedad() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="TRANSFERENCIA",
        referencia="11111111",
        referencia_norm="11111111",
        pagador_nombre="PAGADOR SIN RELACION",
    )
    candidatas = [
        factura(
            factura_id="F-A", nitter="900111111", nombre="EMPRESA A", saldo=Decimal("100000.00")
        ),
        factura(
            factura_id="F-B", nitter="900222222", nombre="EMPRESA B", saldo=Decimal("100000.00")
        ),
    ]

    resultado = score_candidates(movimiento, candidatas)

    assert [c.score for c in resultado] == [40, 40]
    maximo = resultado[0].score
    assert sum(1 for c in resultado if c.score == maximo) == 2


def test_sobrepago_cuando_el_valor_excede_el_saldo() -> None:
    movimiento = Movimiento(
        valor=Decimal("60000.00"),
        descripcion="PAGO QR NIT 900123456",
        referencia="11111111",
        referencia_norm="11111111",
        pagador_nombre="PAGADOR SIN RELACION",
    )
    candidatas = [
        factura(
            factura_id="F-CHICA",
            nitter="900123456",
            nombre="EMPRESA DISTINTA",
            saldo=Decimal("50000.00"),
        )
    ]

    resultado = score_candidates(movimiento, candidatas)

    assert resultado[0].score == 80
    assert es_sobrepago(movimiento, candidatas, resultado) is True


def test_factura_de_otro_tenant_no_es_candidata() -> None:
    movimiento = Movimiento(
        valor=Decimal("100000.00"),
        descripcion="PAGO QR NIT 900123456",
        referencia="11111111",
        referencia_norm="11111111",
        pagador_nombre="DISTRIBUIDORA EL SOL",
    )
    candidatas = [
        factura(
            factura_id="F-PROPIA",
            tenant="motoshop",
            nitter="900123456",
            nombre="DISTRIBUIDORA EL SOL",
            saldo=Decimal("100000.00"),
        ),
        factura(
            factura_id="F-AJENA",
            tenant="masvital",
            nitter="900123456",
            nombre="DISTRIBUIDORA EL SOL",
            saldo=Decimal("100000.00"),
        ),
    ]

    resultado: list[Candidatura] = score_candidates(movimiento, candidatas)

    assert [c.factura_id for c in resultado] == ["F-PROPIA"]
