"""Tests de conciliación y aplicación (S9.2).

El repo no adivina: puntúa, deja el movimiento listo y espera la confirmación
humana. Estos tests verifican qué documento se genera, con qué fecha, que el
periodo cerrado no deja escritura parcial y que el reintento no duplica.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from motoshop_api.erp.bankreconciliation.matching import FacturaCandidata
from motoshop_api.erp.bankreconciliation.repo import (
    BankReconciliationRepo,
    CodpagNoConfirmadoError,
    EstadoConciliacion,
    MovimientoNoEncontradoError,
    clave_idempotencia,
)
from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn, EstadoMovimiento
from motoshop_api.erp.bankreconciliation.store import FakeBankStore, id_dominio_movimiento
from motoshop_api.erp.guards import PeriodLockedError

#: `find_movement`/`apply` usan el id de dominio, no el id del portal.
MOV_ID = id_dominio_movimiento("motoshop", "mov-1")


class DocumentoFake:
    """Registra los documentos creados, como el ledger de ``erp.cash``."""

    def __init__(self, *, periodo_cerrado: bool = False) -> None:
        self.creados: list[dict[str, Any]] = []
        self.periodo_cerrado = periodo_cerrado

    def create(
        self,
        body: object,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        if self.periodo_cerrado:
            # El guard de periodos corta ANTES de escribir: cero filas.
            raise PeriodLockedError("El periodo está cerrado")
        cuerpo = body.model_dump() if hasattr(body, "model_dump") else dict(body)
        documento = {
            "numero": f"{len(self.creados) + 1:04d}",
            "prefijo": "S01",
            "tenant": tenant,
            "empresa": empresa,
            "actor": actor,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            **cuerpo,
        }
        self.creados.append(documento)
        return documento


def preparar(
    *,
    valor: str = "100000.00",
    fecha: date = date(2026, 10, 20),
    referencia: str = "0092055984",
    pagador: str = "DISTRIBUIDORA EL SOL",
    descripcion: str = "PAGO QR NIT 900123456",
) -> tuple[FakeBankStore, FacturaCandidata, BankReconciliationRepo]:
    store = FakeBankStore()
    store.upsert_movements(
        "motoshop",
        "01",
        [
            BankMovementIn(
                id_externo="mov-1",
                fecha_movimiento=fecha,
                valor=Decimal(valor),
                descripcion=descripcion,
                referencia=referencia,
                referencia_norm=referencia,
                pagador_nombre=pagador,
            )
        ],
    )
    factura = FacturaCandidata(
        factura_id="F-1",
        tenant="motoshop",
        numfven=100,
        prefven="FVP",
        nitter="900123456",
        cliente_nombre="DISTRIBUIDORA EL SOL",
        saldo=Decimal("150000.00"),
        referencia=referencia,
    )
    repo = BankReconciliationRepo(
        movements=store,
        facturas=lambda _tenant, _empresa: [factura],
        receipts=DocumentoFake(),
        consignments=DocumentoFake(),
        codpag_transferencia={"motoshop": "F07"},
    )
    return store, factura, repo


def test_movimiento_con_score_80_queda_listo_sin_generar_documento() -> None:
    store, _factura, repo = preparar()
    movimiento = store.find_movement("motoshop", MOV_ID)
    assert movimiento is not None

    resultado = repo.reconcile("motoshop", "01", movimiento)

    assert resultado.estado == EstadoConciliacion.LISTO_PARA_APLICAR
    assert resultado.factura_sugerida == "F-1"
    assert repo.receipts.creados == []  # type: ignore[attr-defined]
    assert repo.consignments.creados == []  # type: ignore[attr-defined]
    assert store.find_movement("motoshop", MOV_ID).estado == EstadoMovimiento.PENDIENTE


def test_confirmacion_del_operador_genera_el_recibo_con_la_fecha_del_movimiento() -> None:
    store, _factura, repo = preparar(fecha=date(2026, 10, 20))

    repo.apply("motoshop", "01", MOV_ID, "F-1")

    creados = repo.receipts.creados  # type: ignore[attr-defined]
    assert len(creados) == 1
    assert creados[0]["fecha"] == date(2026, 10, 20)
    assert creados[0]["numfven"] == 100
    assert creados[0]["nitter"] == "900123456"


def test_movimiento_sin_match_aterriza_como_consignacion_bancaria() -> None:
    store, _factura, repo = preparar()

    repo.apply("motoshop", "01", MOV_ID, None)

    assert repo.receipts.creados == []  # type: ignore[attr-defined]
    assert len(repo.consignments.creados) == 1  # type: ignore[attr-defined]
    assert store.find_movement("motoshop", MOV_ID).estado == EstadoMovimiento.APLICADO


def test_dos_facturas_con_el_mismo_score_maximo_queda_ambigua_y_no_se_aplica() -> None:
    store, factura, repo = preparar()
    gemela = FacturaCandidata(
        factura_id="F-2",
        tenant="motoshop",
        numfven=101,
        prefven="FVP",
        nitter="900123456",
        cliente_nombre="DISTRIBUIDORA EL SOL",
        saldo=Decimal("150000.00"),
        referencia=factura.referencia,
    )
    repo.facturas = lambda _tenant, _empresa: [factura, gemela]
    movimiento = store.find_movement("motoshop", MOV_ID)

    resultado = repo.reconcile("motoshop", "01", movimiento)

    assert resultado.estado == EstadoConciliacion.AMBIGUA
    assert {c.factura_id for c in resultado.candidaturas} >= {"F-1", "F-2"}
    assert store.find_movement("motoshop", MOV_ID).estado == EstadoMovimiento.PENDIENTE


def test_sobrepago_no_se_aplica() -> None:
    store, factura, repo = preparar(valor="120000.00")
    factura_chica = FacturaCandidata(
        factura_id=factura.factura_id,
        tenant=factura.tenant,
        numfven=factura.numfven,
        prefven=factura.prefven,
        nitter=factura.nitter,
        cliente_nombre=factura.cliente_nombre,
        saldo=Decimal("100000.00"),
        referencia=factura.referencia,
    )
    repo.facturas = lambda _tenant, _empresa: [factura_chica]
    movimiento = store.find_movement("motoshop", MOV_ID)

    resultado = repo.reconcile("motoshop", "01", movimiento)

    assert resultado.estado == EstadoConciliacion.SOBREPAGO
    assert store.find_movement("motoshop", MOV_ID).estado == EstadoMovimiento.PENDIENTE


def test_periodo_cerrado_responde_409_y_el_movimiento_queda_pendiente_y_reintentable() -> None:
    store, _factura, repo = preparar()
    repo.receipts = DocumentoFake(periodo_cerrado=True)  # type: ignore[assignment]

    with pytest.raises(PeriodLockedError):
        repo.apply("motoshop", "01", MOV_ID, "F-1")

    # Cero filas de ledger y el movimiento intacto.
    assert repo.receipts.creados == []  # type: ignore[attr-defined]
    assert store.find_movement("motoshop", MOV_ID).estado == EstadoMovimiento.PENDIENTE


def test_reintento_tras_reabrir_el_periodo_aplica_con_la_fecha_del_movimiento() -> None:
    store, _factura, repo = preparar(fecha=date(2026, 10, 20))
    repo.receipts = DocumentoFake(periodo_cerrado=True)  # type: ignore[assignment]
    with pytest.raises(PeriodLockedError):
        repo.apply("motoshop", "01", MOV_ID, "F-1")

    # Se reabre el periodo: el mismo movimiento se aplica ahora.
    repo.receipts = DocumentoFake()  # type: ignore[assignment]
    repo.apply("motoshop", "01", MOV_ID, "F-1")

    assert repo.receipts.creados[0]["fecha"] == date(2026, 10, 20)  # type: ignore[attr-defined]


def test_reejecucion_de_la_conciliacion_no_genera_un_segundo_documento() -> None:
    store, _factura, repo = preparar()

    repo.apply("motoshop", "01", MOV_ID, "F-1")
    resultado = repo.apply("motoshop", "01", MOV_ID, "F-1")

    assert len(repo.receipts.creados) == 1  # type: ignore[attr-defined]
    assert resultado["replay"] is True
    assert store.find_movement("motoshop", MOV_ID).estado == EstadoMovimiento.APLICADO


def test_el_documento_generado_usa_el_codpag_de_transferencia_bancaria() -> None:
    store, _factura, repo = preparar()
    movimiento = store.find_movement("motoshop", MOV_ID)
    assert movimiento is not None
    resultado = repo.reconcile("motoshop", "01", movimiento)
    assert resultado.estado == EstadoConciliacion.LISTO_PARA_APLICAR

    repo.apply("motoshop", "01", MOV_ID, "F-1")

    assert repo.receipts.creados[0]["codpag"] == "F07"  # type: ignore[attr-defined]

    # Fail-closed: sin el codpag confirmado no se postea ni se aplica.
    sin_codpag = BankReconciliationRepo(
        movements=store,
        facturas=repo.facturas,
        receipts=DocumentoFake(),
        consignments=DocumentoFake(),
        codpag_transferencia=None,
    )
    store2 = FakeBankStore()
    store2.upsert_movements(
        "motoshop",
        "01",
        [
            BankMovementIn(
                id_externo="mov-2",
                fecha_movimiento=date(2026, 10, 21),
                valor=Decimal("100000.00"),
                referencia="0092055984",
                referencia_norm="0092055984",
                pagador_nombre="DISTRIBUIDORA EL SOL",
            )
        ],
    )
    sin_codpag.movements = store2
    id_mov2 = id_dominio_movimiento("motoshop", "mov-2")
    with pytest.raises(CodpagNoConfirmadoError):
        sin_codpag.apply("motoshop", "01", id_mov2, "F-1")
    movimiento2 = store2.find_movement("motoshop", id_mov2)
    assert movimiento2 is not None
    assert movimiento2.estado == EstadoMovimiento.PENDIENTE


def test_movimiento_de_otro_tenant_no_se_encuentra() -> None:
    _store, _factura, repo = preparar()

    with pytest.raises(MovimientoNoEncontradoError):
        repo.apply("masvital", "01", MOV_ID, "F-1")


def test_la_clave_de_idempotencia_es_estable_por_movimiento() -> None:
    assert clave_idempotencia("motoshop", "mov-1") == clave_idempotencia("motoshop", "mov-1")
    assert clave_idempotencia("motoshop", "mov-1") != clave_idempotencia("masvital", "mov-1")


def test_cada_tenant_usa_su_propio_codpag_de_transferencia() -> None:
    """El catálogo de formas de pago es de cada empresa, no del proceso."""
    store, _factura, _repo = preparar()
    store.upsert_movements(
        "masvital",
        "01",
        [
            BankMovementIn(
                id_externo="mov-mv",
                fecha_movimiento=date(2026, 10, 21),
                valor=Decimal("100000.00"),
                referencia="0092055984",
                referencia_norm="0092055984",
                pagador_nombre="DISTRIBUIDORA EL SOL",
            )
        ],
    )
    repo = BankReconciliationRepo(
        movements=store,
        facturas=lambda _tenant, _empresa: [
            FacturaCandidata(
                factura_id="F-9",
                tenant="masvital",
                numfven=900,
                prefven="MV",
                nitter="900123456",
                cliente_nombre="DISTRIBUIDORA EL SOL",
                saldo=Decimal("150000.00"),
                referencia="0092055984",
            )
        ],
        receipts=DocumentoFake(),
        consignments=DocumentoFake(),
        codpag_transferencia={"motoshop": "F07", "masvital": "F09"},
    )

    repo.apply("masvital", "01", id_dominio_movimiento("masvital", "mov-mv"), "F-9")

    assert repo.receipts.creados[0]["codpag"] == "F09"  # type: ignore[attr-defined]


def test_tenant_sin_codpag_propio_usa_el_global_de_compatibilidad() -> None:
    """Con una sola empresa por proceso, el global sigue sirviendo."""
    store, _factura, _repo = preparar()
    repo = BankReconciliationRepo(
        movements=store,
        facturas=lambda _tenant, _empresa: [],
        receipts=DocumentoFake(),
        consignments=DocumentoFake(),
        codpag_transferencia={"masvital": "F09"},
        codpag_comun="F07",
    )

    repo.apply("motoshop", "01", MOV_ID, None)

    assert repo.consignments.creados[0]["codpag"] == "F07"  # type: ignore[attr-defined]
