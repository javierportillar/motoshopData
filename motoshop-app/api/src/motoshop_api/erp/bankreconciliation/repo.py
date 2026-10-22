"""Conciliación y aplicación de movimientos bancarios (S9.2).

Dos operaciones, con responsabilidades separadas:

- ``reconcile``: puntúa las facturas abiertas y decide el estado. **No escribe
  nada.** Un movimiento con puntaje suficiente y candidata única queda *listo
  para aplicar*, nunca aplicado.
- ``apply``: la confirmación del operador. Recién ahí se genera el documento,
  y siempre por los caminos de caja existentes (recibo S01 o consignación
  bancaria). No hay camino contable paralelo.

Invariantes:

- **Fecha**: el documento lleva la fecha del movimiento, no la de hoy. Un pago
  del viernes no puede caer contablemente el lunes.
- **Periodo cerrado**: el error del guard de periodos sube tal cual y el
  movimiento queda ``PENDIENTE`` (reintentable al reabrir).
- **Idempotencia**: la clave es ``uuid5(tenant:id_externo)``; reejecutar no
  genera un segundo documento.
- **Fail-closed**: sin el ``codpag`` real de transferencia confirmado no se
  postea nada y el movimiento queda pendiente.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from motoshop_api.erp.bankreconciliation.matching import (
    UMBRAL_LISTO_PARA_APLICAR,
    Candidatura,
    FacturaCandidata,
    es_sobrepago,
    score_candidates,
)
from motoshop_api.erp.bankreconciliation.schemas import BankMovementOut, EstadoMovimiento
from motoshop_api.erp.bankreconciliation.store import NAMESPACE_DOMINIO
from motoshop_api.erp.cash.schemas import ConsignmentCreate, ReceiptCreate

#: Actor con el que quedan auditados los documentos que genera la conciliación.
ACTOR_CONCILIACION = "scraper:bancos"

#: La referencia del recibo se recorta a 20 caracteres (legado ``numpag``).
LARGO_REFERENCIA = 20


class EstadoConciliacion(StrEnum):
    """Qué hacer con un movimiento recién puntuado."""

    LISTO_PARA_APLICAR = "listo_para_aplicar"
    AMBIGUA = "ambigua"
    SOBREPAGO = "sobrepago"
    SIN_MATCH = "sin_match"


@dataclass(frozen=True, slots=True)
class ResultadoConciliacion:
    """Resultado de puntuar un movimiento (todavía sin escribir nada)."""

    movimiento_id: str
    estado: EstadoConciliacion
    candidaturas: tuple[Candidatura, ...]
    factura_sugerida: str | None = None


class CodpagNoConfirmadoError(Exception):
    """No hay ``formapago.codpag`` confirmado para la transferencia bancaria.

    Fail-closed: sin ese dato no se postea, porque el documento quedaría con
    una forma de pago equivocada y habría que anularlo a mano.
    """

    codigo = "codpag_no_confirmado"


class MovimientoNoEncontradoError(Exception):
    """El movimiento no existe o es de otro tenant."""

    codigo = "movimiento_no_encontrado"


class FacturaNoEncontradaError(Exception):
    """La factura indicada por el operador no está abierta en este tenant."""

    codigo = "factura_no_encontrada"


class DocumentoRepo(Protocol):
    """Contrato común de recibos y consignaciones de ``erp.cash``."""

    def create(
        self,
        body: object,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


#: Provee las facturas abiertas del tenant (el repo real consulta cartera).
FacturasProvider = Callable[[str, str], Sequence[FacturaCandidata]]


def clave_idempotencia(tenant: str, id_externo: str) -> str:
    """Clave estable por movimiento: el reintento no duplica el documento."""
    return str(uuid.uuid5(NAMESPACE_DOMINIO, f"{tenant}:{id_externo}"))


class BankReconciliationRepo:
    """Puntúa movimientos y los aplica por los caminos de caja existentes."""

    def __init__(
        self,
        *,
        movements: object,
        facturas: FacturasProvider,
        receipts: DocumentoRepo,
        consignments: DocumentoRepo,
        codpag_transferencia: Mapping[str, str] | None = None,
        codpag_consignacion: Mapping[str, str] | None = None,
        codpag_comun: str | None = None,
        codpag_comun_consignacion: str | None = None,
    ) -> None:
        # El `codpag` vive en el catálogo de formas de pago de CADA empresa:
        # una sola API sirve a varios tenants y comparten el proceso, así que
        # una cadena global postearía con el código de otra empresa.
        self.movements = movements
        self.facturas = facturas
        self.receipts = receipts
        self.consignments = consignments
        self.codpag_transferencia: Mapping[str, str] = dict(codpag_transferencia or {})
        # El recibo de una factura y la consignación bancaria son formas de pago
        # DISTINTAS en el catálogo legacy (`TRANSFERENCIA BANCO` vs
        # `CONSIGNACION BANCO`): usar una sola para los dos caminos cambia el
        # asiento y la cuenta de contrapartida.
        self.codpag_consignacion: Mapping[str, str] = dict(codpag_consignacion or {})
        self.codpag_comun = codpag_comun
        # El global de consignación es aparte: caer al código de transferencia
        # postearía la forma de pago equivocada, así que no se cruzan.
        self.codpag_comun_consignacion = codpag_comun_consignacion

    # ── Lectura / decisión ───────────────────────────────────────────────

    def reconcile(
        self,
        tenant: str,
        empresa: str,
        movimiento: BankMovementOut,
    ) -> ResultadoConciliacion:
        """Decide el estado del movimiento. No escribe nada."""
        candidatas = list(self.facturas(tenant, empresa))
        puntuadas = score_candidates(movimiento, candidatas)

        if not puntuadas:
            return ResultadoConciliacion(
                movimiento_id=movimiento.id,
                estado=EstadoConciliacion.SIN_MATCH,
                candidaturas=(),
            )

        maximo = puntuadas[0].score
        empatadas = [c for c in puntuadas if c.score == maximo]

        if maximo >= UMBRAL_LISTO_PARA_APLICAR and es_sobrepago(movimiento, candidatas, puntuadas):
            return ResultadoConciliacion(
                movimiento_id=movimiento.id,
                estado=EstadoConciliacion.SOBREPAGO,
                candidaturas=tuple(puntuadas),
            )

        if maximo >= UMBRAL_LISTO_PARA_APLICAR and len(empatadas) > 1:
            return ResultadoConciliacion(
                movimiento_id=movimiento.id,
                estado=EstadoConciliacion.AMBIGUA,
                candidaturas=tuple(puntuadas),
            )

        if maximo >= UMBRAL_LISTO_PARA_APLICAR:
            return ResultadoConciliacion(
                movimiento_id=movimiento.id,
                estado=EstadoConciliacion.LISTO_PARA_APLICAR,
                candidaturas=tuple(puntuadas),
                factura_sugerida=empatadas[0].factura_id,
            )

        # Hay señales, pero ninguna alcanza para proponerle una factura al
        # operador: se resuelve a mano.
        return ResultadoConciliacion(
            movimiento_id=movimiento.id,
            estado=EstadoConciliacion.SIN_MATCH,
            candidaturas=tuple(puntuadas),
        )

    # ── Aplicación (confirmación del operador) ───────────────────────────

    def apply(
        self,
        tenant: str,
        empresa: str,
        movimiento_id: str,
        factura_id: str | None,
        *,
        idempotency_key: str | None = None,
        actor: str = ACTOR_CONCILIACION,
    ) -> dict:
        """Genera el documento y marca el movimiento como aplicado.

        ``factura_id=None`` significa "aplicar como consignación" (no hay
        factura que cobrar). Con factura, se postea un recibo S01.
        """
        movimiento = self._buscar_movimiento(tenant, movimiento_id)

        # Replay: si ya está aplicado, devolver el documento existente sin
        # volver a postear (idempotencia por estado, además de por clave).
        if movimiento.estado == EstadoMovimiento.APLICADO and movimiento.recibo_numero:
            return {
                "movimiento_id": movimiento.id,
                "documento": movimiento.recibo_numero,
                "prefijo": movimiento.recibo_pref,
                "replay": True,
            }

        if factura_id is None:
            codpag = (
                self.codpag_consignacion.get(tenant)
                or self.codpag_comun_consignacion
            )
            faltante = "consignación bancaria"
        else:
            codpag = self.codpag_transferencia.get(tenant) or self.codpag_comun
            faltante = "transferencia bancaria"
        if not codpag:
            # Fail-closed: sin la forma de pago real confirmada no se adivina.
            raise CodpagNoConfirmadoError(
                f"Falta el codpag de {faltante} confirmado; el movimiento queda pendiente."
            )

        clave = idempotency_key or clave_idempotencia(tenant, movimiento.id_externo)
        request_id = f"bank-reconcile-{movimiento.id[:8]}"

        if factura_id is None:
            documento = self.consignments.create(
                ConsignmentCreate(
                    codpag=codpag,
                    valor=movimiento.valor,
                    fecha=movimiento.fecha_movimiento,
                    detalle=(movimiento.descripcion or "")[:300] or None,
                ),
                tenant=tenant,
                empresa=empresa,
                actor=actor,
                request_id=request_id,
                idempotency_key=clave,
            )
            numero = str(documento.get("numero") or documento.get("numcon") or "")
            prefijo = str(documento.get("prefijo") or documento.get("precon") or "CC")
        else:
            factura = self._buscar_factura(tenant, empresa, factura_id)
            documento = self.receipts.create(
                ReceiptCreate(
                    nitter=factura.nitter,
                    numfven=factura.numfven,
                    prefven=factura.prefven,
                    codpag=codpag,
                    valor=movimiento.valor,
                    fecha=movimiento.fecha_movimiento,
                    referencia=(movimiento.referencia or "")[:LARGO_REFERENCIA] or None,
                    concepto="Conciliación bancaria",
                ),
                tenant=tenant,
                empresa=empresa,
                actor=actor,
                request_id=request_id,
                idempotency_key=clave,
            )
            numero = str(documento.get("numero") or documento.get("numrec") or "")
            prefijo = str(documento.get("prefijo") or documento.get("prefijo_doc") or "S01")

        # Sólo se marca aplicado con el documento ya creado: si el guard de
        # periodos lanzó, no se llega acá y el movimiento sigue PENDIENTE.
        self.movements.move_to_state(
            tenant,
            movimiento.id,
            EstadoMovimiento.APLICADO,
            recibo_numero=numero or None,
            recibo_pref=prefijo or None,
            confianza=movimiento.confianza,
            razones=movimiento.razones,
        )

        return {
            "movimiento_id": movimiento.id,
            "documento": numero,
            "prefijo": prefijo,
            "replay": False,
            "documento_completo": documento,
        }

    # ── Internos ─────────────────────────────────────────────────────────

    def _buscar_movimiento(self, tenant: str, movimiento_id: str) -> BankMovementOut:
        movimiento = self.movements.find_movement(tenant, movimiento_id)
        if movimiento is None:
            # Misma respuesta para "no existe" y "es de otro tenant": no se
            # revela la existencia de movimientos ajenos.
            raise MovimientoNoEncontradoError(movimiento_id)
        return movimiento

    def _buscar_factura(self, tenant: str, empresa: str, factura_id: str) -> FacturaCandidata:
        for factura in self.facturas(tenant, empresa):
            if factura.factura_id == factura_id:
                return factura
        raise FacturaNoEncontradaError(factura_id)
