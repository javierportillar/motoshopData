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

import dataclasses
import datetime
import logging
import os
import time
import traceback
from collections.abc import Callable, Mapping
from typing import Any

from motoshop_api.erp.bankreconciliation.jobs import (
    EstadoJob,
    VerificationJob,
    VerificationJobStore,
)
from motoshop_api.erp.bankreconciliation.matching import normalizar_nombre
from motoshop_api.erp.bankreconciliation.node_config import (
    CODIGO_PORTAL_NO_DISPONIBLE,
    FIN_DEL_DIA,
    INICIO_DEL_DIA,
    NodeConfig,
)
from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn
from motoshop_api.erp.bankreconciliation.scraper import (
    BankScrapeError,
    BankScraper,
    ScrapedMovement,
    ScrapeResult,
    SessionSlotError,
)
from motoshop_api.erp.bankreconciliation.store import BankStore, get_bank_store
from motoshop_api.erp.bankreconciliation.value_match import (
    Candidato,
    ValueMatch,
    desde_movimiento_raspado,
    match_by_value,
)

#: Variable de entorno con el identificador del nodo (el que corrió el job).
ENV_NODO = "BANK_NODE_ID"

#: Límites de las columnas de `app_bank_movements` (los mismos que el
#: sincronizador `scripts/bank_sync.py`): el texto que exceda el límite de la
#: base se recorta aquí.
LIMITE_DESCRIPCION = 255
LIMITE_REFERENCIA = 64
LIMITE_PAGADOR = 128
LIMITE_CUENTA = 64

#: Un solo reintento cuando el portal no responde: el segundo intento casi
#: siempre entra (medido en produccion) y el operador no tiene que volver a
#: apretar el boton. El reintento espera el turno de sesion del nodo.
REINTENTOS_PORTAL = 1
ESPERA_REINTENTO_SEG = 35.0


def _pedir_codigo_en_consola(prompt: str) -> str:
    """Pide el código de un solo uso **en la consola del nodo**.

    El código no se guarda en disco, no va en el log y no viaja en el
    resultado del job: sólo de la terminal al formulario del navegador.
    """
    return input(prompt)


def _estado_del_job(coincidencia: ValueMatch) -> EstadoJob:
    """El veredicto del matching, expresado en estados del job.

    - 0 candidatos ⇒ `sin_coincidencia`;
    - 1 candidato ⇒ `resuelto`;
    - 2 o más ⇒ `ambiguo`: el worker **no elige** (la elección es del
      operador en el POS).

    La regla (qué es un candidato) no vive aquí: vive en
    `value_match.match_by_value`, que es la **misma** que usa el endpoint de
    candidatos.
    """
    if not coincidencia.candidatos:
        return EstadoJob.SIN_COINCIDENCIA
    if coincidencia.ambiguo:
        return EstadoJob.AMBIGUO
    return EstadoJob.RESUELTO


#: NIT comodin de "consumidor final": no identifica a ningun cliente.
NIT_COMODIN = "222222222"


def _candidato_con_senales(
    candidato: Candidato,
    modo: str,
    solicitud: dict[str, Any],
    datos_factura: dict[str, str],
) -> dict[str, Any]:
    """Candidato en JSON con los datos del cliente y la senal del nombre."""
    datos: dict[str, Any] = _candidato_json(candidato)
    if modo == "pago":
        if solicitud.get("nitter"):
            datos["nitter"] = str(solicitud["nitter"])
        if solicitud.get("nombre_esperado"):
            datos["cliente_nombre"] = str(solicitud["nombre_esperado"])
    else:
        if datos_factura.get("nitter"):
            datos["nitter"] = datos_factura["nitter"]
        if datos_factura.get("cliente_nombre"):
            datos["cliente_nombre"] = datos_factura["cliente_nombre"]
    # El NIT comodin del consumidor final no identifica a nadie: mostrarlo en
    # el chulo del POS es peor que no mostrarlo (el operador lo lee como si
    # fuera el NIT del cliente).
    nit = str(datos.get("nitter") or "").strip()
    if nit == NIT_COMODIN or normalizar_nombre(str(datos.get("cliente_nombre") or "")) == (
        "CONSUMIDOR FINAL"
    ):
        datos.pop("nitter", None)
        # Etiqueta estable para el chulo: el operador lee "Cliente: CONSUMIDOR
        # FINAL" en vez de un nombre recortado del catalogo legacy.
        datos["cliente_nombre"] = "CONSUMIDOR FINAL"
    esperado = solicitud.get("nombre_esperado")
    if esperado:
        # Senal, no decision: con dos importes iguales el job sigue ambiguo.
        datos["coincide_nombre"] = normalizar_nombre(esperado) in normalizar_nombre(
            candidato.pagador_nombre
        )
    return datos


def _candidato_json(candidato: Candidato) -> dict[str, str]:
    """Candidato → JSON del resultado del job (el front lo usa para el prellenado)."""
    return {
        "id": candidato.id,
        "valor": str(candidato.valor),
        "pagador_nombre": candidato.pagador_nombre,
        "referencia": candidato.referencia,
        "fecha": candidato.fecha.isoformat(),
    }


def _variantes_numfven(factura_id: str) -> list[str]:
    """Formas en que la factura puede estar escrita en `facventas.numfven`.

    El POS manda `FVP-3600` y el catalogo legacy guarda `3600`: se prueba tal
    cual y sin el prefijo alfabetico. Nunca se inventa un numero.
    """
    limpio = factura_id.strip()
    solo_digitos = "".join(ch for ch in limpio if ch.isdigit())
    variantes = [limpio]
    if solo_digitos and solo_digitos != limpio:
        variantes.append(solo_digitos)
    return variantes


def _factura_erp(factura_id: str) -> dict[str, str] | None:
    """NIT y nombre del cliente de la factura, desde el ERP.

    El NIT **no** viene del banco: en los pagos por QR la referencia es el
    mismo convenio para todos los movimientos, asi que derivarlo de ahi daria
    un NIT falso.

    Lee `facventas` y su `terceros`: es una lectura, no escribe nada. El SQL va
    sin prefijo de base a proposito: las tablas viven en la base del tenant
    (`MYSQL_DATABASE`) y `db/tables.py` fija el esquema de MotoShop.
    """
    from sqlalchemy import text

    from motoshop_api.db.engine import get_engine

    consulta = text(
        "SELECT f.nitter AS nitter, t.nomter AS nomter, "
        "t.razsoc AS razsoc, t.nomcom AS nomcom "
        "FROM facventas f LEFT JOIN terceros t ON f.nitter = t.nitter "
        "WHERE f.numfven = :numfven LIMIT 1"
    )
    with get_engine().connect() as conexion:
        for numfven in _variantes_numfven(factura_id):
            fila = conexion.execute(consulta, {"numfven": numfven}).mappings().first()
            if fila:
                break
        else:
            return None
    nitter = "".join((fila["nitter"] or "").split())
    # El catalogo legacy tiene espacios dobles ("CONSUMIDOR  FINAL"): se colapsan.
    nombre = ""
    for columna in ("razsoc", "nomcom", "nomter"):
        nombre = " ".join((fila[columna] or "").split())
        if nombre:
            break
    return {"nitter": nitter, "cliente_nombre": nombre}


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
        esperar: Callable[[float], None] | None = None,
        facturas: Callable[[str], Mapping[str, str] | None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._jobs = jobs
        self._config = config
        self._store = store if store is not None else get_bank_store()
        self._session_factory = session_factory
        self._vault = vault
        self._reloj = reloj or (lambda: datetime.datetime.now())
        self._esperar = esperar or time.sleep
        self._facturas = facturas or _factura_erp
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
        # Claim atómico `en_cola → ejecutando`: el despacho levanta un hilo
        # por petición y el doble clic llega con dos hilos para el mismo job.
        # El que pierde el claim muere acá sin tocar estados: si marcara
        # `fallido`, enmascararía el resultado del hilo que sí está raspando.
        if not self._jobs.reclamar_ejecucion(job.tenant, job.job_id, nodo=self._nodo):
            return
        try:
            resultado = self._raspar(job)
        except BankScrapeError as exc:
            # Sólo el código estable: el mensaje del portal puede traer datos
            # de la sesión y no puede viajar al job.
            self._log.warning("Job de verificación fallido: %s", exc.codigo)
            if os.environ.get("BANK_LOG_CAUSA", "").strip() == "1":
                # Diagnostico local (apagado por defecto): el detalle queda solo
                # en el log del nodo, nunca en el job ni en la API.
                self._log.warning("Causa del fallo %s: %s", job.job_id, exc)
                self._log.warning(
                    "Traza del fallo %s:\n%s", job.job_id, traceback.format_exc()
                )
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
        coincidencia = match_by_value(
            job.valor,
            [
                desde_movimiento_raspado(movimiento, resultado.tenant)
                for movimiento in resultado.movimientos
            ],
            resultado.ventana,
        )
        self._actualizar(
            job,
            _estado_del_job(coincidencia),
            resultado=self._resultado_json(job, resultado, coincidencia),
        )

    # --- implementación ---

    def _raspar(self, job: VerificationJob) -> ScrapeResult:
        """Raspa con un solo reintento si el portal no responde.

        El portal detras de Imperva corta un click con timeout de 30 s cada
        tanto (medido: 3 de 11 corridas en el nodo). El segundo intento entra,
        asi que se reintenta una vez: el operador no tiene que volver a
        apretar el boton. El reintento respeta el turno de sesion del nodo.
        """
        config = self._config_de(job)
        intento = 0
        while True:
            intento += 1
            try:
                return self._scraper.scrape(config)
            except BankScrapeError as exc:
                reintentable = (
                    exc.codigo == CODIGO_PORTAL_NO_DISPONIBLE
                    and intento <= REINTENTOS_PORTAL
                    and self._hay_tiempo_para_reintentar(job)
                )
                if not reintentable:
                    raise
                self._log.warning(
                    "El portal no respondio (job %s); reintento %d/%d en %.0f s",
                    job.job_id,
                    intento,
                    REINTENTOS_PORTAL,
                    ESPERA_REINTENTO_SEG,
                )
                self._esperar(ESPERA_REINTENTO_SEG)

    def _config_de(self, job: VerificationJob) -> NodeConfig:
        """Configuración del nodo con la ventana del job, si el job pide una.

        Sin `fecha` en la solicitud se usa la ventana del nodo (el día en
        curso): el comportamiento histórico no cambia. Con `fecha` la ventana
        pasa a ser ese día completo **para este job**, sin tocar la config del
        proceso ni la de los demás jobs: dos verificaciones simultáneas de días
        distintos no se pisan.

        Una `fecha` ilegible no tumba el job: se cae a la ventana del nodo, que
        es lo que el operador hubiera obtenido sin pedir nada.
        """
        bruto = (job.solicitud or {}).get("fecha")
        if not bruto:
            return self._config
        try:
            dia = datetime.date.fromisoformat(str(bruto))
        except ValueError:
            self._log.warning(
                "Fecha de ventana ilegible en el job %s: se usa la del nodo", job.job_id
            )
            return self._config
        return dataclasses.replace(
            self._config,
            window_start=datetime.datetime.combine(dia, INICIO_DEL_DIA),
            window_end=datetime.datetime.combine(dia, FIN_DEL_DIA),
        )

    def _hay_tiempo_para_reintentar(self, job: VerificationJob) -> bool:
        """True si el job sigue vivo despues de esperar el turno de sesion."""
        expira = getattr(job, "expira_en", None)
        if expira is None:
            return True
        return self._reloj() + datetime.timedelta(seconds=ESPERA_REINTENTO_SEG) < expira
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
        job: VerificationJob,
        resultado: ScrapeResult,
        coincidencia: ValueMatch,
    ) -> dict[str, Any]:
        """Lo que se persiste en `resultado_json`: ventana, nodo e ingesta.

        El resultado sirve a los dos modos del contrato:

        - **factura**: al candidato se le suman `nitter` y `cliente_nombre` de
          la factura del ERP (es el modo histórico).
        - **pago**: no hay factura; se devuelven los `nitter`/`cliente_nombre`
          que mandó el POS (si los mandó) y el pagador que publicó el banco.

        `nombre_esperado` agrega una **señal** por candidato
        (`coincide_nombre`), nunca una decisión: con dos importes iguales el
        job sigue siendo `ambiguo` aunque uno de los nombres coincida.
        """
        inicio, fin = resultado.ventana
        solicitud = job.solicitud or {}
        modo = solicitud.get("modo", "factura")
        datos_factura: dict[str, str] = {}
        if modo == "factura" and job.factura_id:
            datos_factura = self._datos_factura(job.factura_id)

        detalle = [
            _candidato_con_senales(candidato, modo, solicitud, datos_factura)
            for candidato in coincidencia.candidatos
        ]
        # Orden estable: primero los que coinciden por nombre. Es presentación:
        # la decisión sale del conteo de candidatos, no de este orden.
        detalle.sort(key=lambda item: not item.get("coincide_nombre", False))

        candidato_json = detalle[0] if len(detalle) == 1 else None
        payload: dict[str, Any] = {
            "ventana": {"desde": inicio.isoformat(), "hasta": fin.isoformat()},
            "nodo": self._nodo,
            "ingesta_at": resultado.leido_en.isoformat(),
            "cuenta": resultado.cuenta,
            "paginas": resultado.paginas,
            "movimientos": len(resultado.movimientos),
            "candidatos": len(coincidencia.candidatos),
            "candidato": candidato_json,
        }
        if len(detalle) > 1:
            # Sólo cuando es ambiguo: la lista completa para que el operador
            # elija. `candidatos` (el número) se conserva como estaba.
            payload["candidatos_detalle"] = detalle
        return payload

    def _datos_factura(self, factura_id: str) -> dict[str, str]:
        """Datos del cliente de la factura; si el ERP falla, el job no se cae."""
        try:
            return dict(self._facturas(factura_id) or {})
        except Exception:  # noqa: BLE001 - el resultado del banco vale por si solo
            self._log.warning("No pude leer la factura %s para el resultado del job", factura_id)
            return {}

