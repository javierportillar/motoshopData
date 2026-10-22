"""Worker del nodo (S6 · 6.2): corre **un** job de verificación a la vez.

El worker vive **en el proceso del nodo local** (el mismo que la API del
tenant): no hay cola ni broker. Toma el turno de sesión del scraper —el lock
por perfil y el intervalo mínimo de 30 s—, lee los movimientos de la cuenta
del tenant y **reporta** lo que encontró.

Máquina de estados:

    en_cola → ejecutando → (esperando_otp) → resuelto | sin_coincidencia |
                                              ambiguo | fallido

Reglas que no se negocian: **nunca postea un pago** (sólo lee; el operador
confirma en el POS), **ningún fallo deja movimientos parciales** (la ingesta
es posterior al scrape) y **ningún secreto sale de aquí** (al job sólo viaja
el código estable del fallo, nunca el mensaje crudo del portal).
"""

from __future__ import annotations

import datetime
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from motoshop_api.erp.bankreconciliation.jobs import (
    EstadoJob,
    VerificationJob,
    VerificationJobStore,
)
from motoshop_api.erp.bankreconciliation.node_config import NodeConfig
from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn
from motoshop_api.erp.bankreconciliation.scraper import (
    BankScrapeError,
    BankScraper,
    ScrapedMovement,
    ScrapeResult,
    SessionSlotError,
)
from motoshop_api.erp.bankreconciliation.store import BankStore, get_bank_store

#: Variable de entorno con el identificador del nodo (el que corrió el job).
ENV_NODO = "BANK_NODE_ID"

#: Límites de las columnas de `app_bank_movements` (los mismos que el
#: sincronizador `scripts/bank_sync.py`): el texto que exceda el límite de la
#: base se recorta aquí.
LIMITE_DESCRIPCION = 255
LIMITE_REFERENCIA = 64
LIMITE_PAGADOR = 128
LIMITE_CUENTA = 64


def _pedir_codigo_en_consola(prompt: str) -> str:
    """Pide el código de un solo uso **en la consola del nodo**.

    El código no se guarda en disco, no va en el log y no viaja en el
    resultado del job: sólo de la terminal al formulario del navegador.
    """
    return input(prompt)


@dataclass(frozen=True)
class Candidato:
    """Movimiento que puede ser el pago que se está verificando."""

    id_externo: str
    valor: Decimal
    pagador_nombre: str
    referencia: str
    fecha: datetime.date

    def a_dict(self) -> dict[str, str]:
        """Forma JSON del candidato (el front la usa para el prellenado)."""
        return {
            "id": self.id_externo,
            "valor": str(self.valor),
            "pagador_nombre": self.pagador_nombre,
            "referencia": self.referencia,
            "fecha": self.fecha.isoformat(),
        }


@dataclass(frozen=True)
class ResultadoClasificacion:
    """Veredicto del worker sobre los movimientos leídos."""

    estado: EstadoJob
    candidatos: tuple[Candidato, ...]


def clasificar_por_valor(
    valor: Decimal,
    movimientos: Sequence[ScrapedMovement],
) -> ResultadoClasificacion:
    """Clasifica el job según los movimientos con el **mismo importe**.

    - 0 candidatos ⇒ `sin_coincidencia`;
    - 1 candidato ⇒ `resuelto`;
    - 2 o más ⇒ `ambiguo`: el worker **no elige** (la elección es del
      operador en el POS).

    Sólo cuentan los ingresos (`es_candidato_pago`): un egreso con el mismo
    importe no es un pago.

    Nota: el matching completo por valor (ventana, puntaje, referencia) es de
    la slice S7 (`value_match.py`); aquí sólo está el criterio mínimo que
    decide el estado del job.
    """
    iguales = [
        movimiento
        for movimiento in movimientos
        if movimiento.es_candidato_pago and movimiento.valor == valor
    ]
    candidatos = tuple(
        Candidato(
            id_externo=movimiento.id_externo,
            valor=movimiento.valor,
            pagador_nombre=movimiento.pagador_nombre,
            referencia=movimiento.referencia,
            fecha=movimiento.fecha,
        )
        for movimiento in iguales
    )
    if not candidatos:
        return ResultadoClasificacion(EstadoJob.SIN_COINCIDENCIA, ())
    if len(candidatos) > 1:
        return ResultadoClasificacion(EstadoJob.AMBIGUO, candidatos)
    return ResultadoClasificacion(EstadoJob.RESUELTO, candidatos)


def _a_ingesta(movimiento: ScrapedMovement) -> BankMovementIn:
    """Movimiento del portal → fila de entrada de la ingesta.

    `referencia_norm` es la referencia ya saneada (sin el sufijo `" null"`):
    la normalización sin ceros a la izquierda es del matching (S7/S9).
    """
    return BankMovementIn(
        id_externo=movimiento.id_externo,
        fecha_movimiento=movimiento.fecha,
        valor=movimiento.valor,
        descripcion=movimiento.descripcion[:LIMITE_DESCRIPCION],
        referencia=movimiento.referencia[:LIMITE_REFERENCIA],
        referencia_norm=movimiento.referencia[:LIMITE_REFERENCIA],
        pagador_nombre=movimiento.pagador_nombre[:LIMITE_PAGADOR],
        cuenta_origen=movimiento.cuenta_origen[:LIMITE_CUENTA],
    )


class BankVerificationWorker:
    """Corre un job de verificación en el nodo local.

    Args:
        jobs: store de jobs (escribe el estado en cada transición).
        config: configuración del nodo (tenant, ventana, perfil).
        store: store de movimientos (destino de la ingesta). Por defecto, el
            de producción.
        scraper_factory: fábrica del scraper. Recibe la función que pide el
            código de un solo uso (para poder marcar `esperando_otp` antes de
            la pregunta) y devuelve el scraper. Por defecto, el `BankScraper`
            de producción.
        session_factory: sesión del portal (sólo si no hay `scraper_factory`).
        vault: bóveda de credenciales del tenant.
        nodo: identificador del nodo. Por defecto, `BANK_NODE_ID` o el tenant.
        pedir_codigo: cómo se pide el código OTP (por defecto, `input()` en
            la consola del nodo).
        reloj: reloj inyectable (las pruebas lo fijan).
        logger: logger del nodo.
    """

    def __init__(
        self,
        *,
        jobs: VerificationJobStore,
        config: NodeConfig,
        store: BankStore | None = None,
        scraper_factory: Callable[[Callable[[str], str]], Any] | None = None,
        session_factory: Callable[[NodeConfig], Any] | None = None,
        vault: Any | None = None,
        nodo: str | None = None,
        pedir_codigo: Callable[[str], str] | None = None,
        reloj: Callable[[], datetime.datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._jobs = jobs
        self._config = config
        self._store = store if store is not None else get_bank_store()
        self._session_factory = session_factory
        self._vault = vault
        self._reloj = reloj or (lambda: datetime.datetime.now())
        self._log = logger or logging.getLogger(__name__)
        self._nodo = nodo or os.environ.get(ENV_NODO) or config.tenant
        self._pedir_codigo = pedir_codigo or _pedir_codigo_en_consola
        self._job_actual: VerificationJob | None = None
        fabrica = scraper_factory or self._scraper_por_defecto
        self._scraper = fabrica(self._preguntar_otp)

    # --- API pública ---

    def run_once(self, job: VerificationJob) -> None:
        """Ejecuta un job de punta a punta: raspa, ingiere y clasifica.

        Nunca propaga el fallo del portal: el job queda `fallido` con el
        código estable del error, que es lo que el front muestra.

        Args:
            job: job a ejecutar (debe estar en `en_cola`).
        """
        self._job_actual = job
        self._actualizar(job, EstadoJob.EJECUTANDO)
        try:
            resultado = self._scraper.scrape(self._config)
        except BankScrapeError as exc:
            # Sólo el código estable: el mensaje del portal puede traer datos
            # de la sesión y no puede viajar al job.
            self._log.warning("Job de verificación fallido: %s", exc.codigo)
            self._actualizar(job, EstadoJob.FALLIDO, error_codigo=exc.codigo)
            return
        except SessionSlotError as exc:
            # Otra corrida en curso o intervalo mínimo: el nodo no entra.
            self._log.warning("Job de verificación sin turno de sesión: %s", exc.motivo)
            self._actualizar(job, EstadoJob.FALLIDO, error_codigo=exc.motivo)
            return
        finally:
            self._job_actual = None

        # La ingesta ocurre DESPUÉS del scrape completo: un fallo del portal
        # deja cero movimientos (nada de filas parciales).
        self._ingerir(resultado)
        clasificacion = clasificar_por_valor(job.valor, resultado.movimientos)
        self._actualizar(
            job,
            clasificacion.estado,
            resultado=self._resultado_json(resultado, clasificacion),
        )

    # --- implementación ---

    def _scraper_por_defecto(self, pedir_codigo: Callable[[str], str]) -> Any:
        """Scraper de producción (Playwright) con la pregunta del OTP marcada."""
        return BankScraper(
            session_factory=self._session_factory,
            vault=self._vault,
            pedir_codigo=pedir_codigo,
            reloj=self._reloj,
        )

    def _preguntar_otp(self, prompt: str) -> str:
        """Marca `esperando_otp` y pide el código en la consola del nodo."""
        job = self._job_actual
        if job is not None:
            self._actualizar(job, EstadoJob.ESPERANDO_OTP)
        return self._pedir_codigo(prompt)

    def _actualizar(
        self,
        job: VerificationJob,
        estado: EstadoJob,
        resultado: dict[str, Any] | None = None,
        error_codigo: str | None = None,
    ) -> None:
        self._jobs.update_job(
            job.tenant,
            job.job_id,
            estado,
            resultado=resultado,
            error_codigo=error_codigo,
            # El nodo que corre el job queda en la fila (columna `nodo`).
            nodo=self._nodo,
        )

    def _ingerir(self, resultado: ScrapeResult) -> None:
        """Ingesta idempotente de los movimientos leídos."""
        movimientos = [_a_ingesta(movimiento) for movimiento in resultado.movimientos]
        if not movimientos:
            return
        self._store.upsert_movements(resultado.tenant, resultado.tenant, movimientos)

    def _resultado_json(
        self,
        resultado: ScrapeResult,
        clasificacion: ResultadoClasificacion,
    ) -> dict[str, Any]:
        """Lo que se persiste en `resultado_json`: ventana, nodo e ingesta."""
        inicio, fin = resultado.ventana
        candidato = (
            clasificacion.candidatos[0].a_dict() if len(clasificacion.candidatos) == 1 else None
        )
        return {
            "ventana": {"desde": inicio.isoformat(), "hasta": fin.isoformat()},
            "nodo": self._nodo,
            "ingesta_at": resultado.leido_en.isoformat(),
            "cuenta": resultado.cuenta,
            "paginas": resultado.paginas,
            "movimientos": len(resultado.movimientos),
            "candidatos": len(clasificacion.candidatos),
            "candidato": candidato,
        }
