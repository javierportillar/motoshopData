"""Agente del nodo de verificacion bancaria (F0/F1).

Vive en la PC del cliente y es el **unico** que raspa. Habla con el plano de
control por HTTP (`/api/erp/bank/node/*`): late, toma el candado de la cuenta,
reclama el job mas viejo de la cola, renueva el candado mientras raspa y
publica el resultado. Nunca escribe estados de job por su cuenta: el estado lo
decide la API, que es la que manda.

Por que un proceso aparte y no el hilo de la API:

- el scrape abre un Chrome real y tarda 40-160 s; colgarlo del request o de un
  hilo del API deja el proceso del API a merced de Playwright;
- el plano de control nunca raspa, asi que la nube no necesita credenciales ni
  navegador;
- el agente se puede reiniciar solo (tarea programada o `pythonw`) sin tocar la
  API ni el POS.

Reglas que respeta, iguales a las del worker local:

- **un solo job por cuenta a la vez**: lo garantiza el candado del plano de
  control, no este proceso;
- **nunca postea un pago**: solo lee;
- **ningun fallo deja movimientos parciales**: la ingesta va despues del scrape;
- **ningun secreto sale de la PC**: al job solo viaja el codigo estable.

Uso:

    python infra/node_agent.py                  # bucle normal
    python infra/node_agent.py --una-vez        # reclama y ejecuta un job
    python infra/node_agent.py --estado         # heartbeat + estado y sale

Variables de entorno (todas con default sensato salvo el token):

    BANK_API_URL           base de la API (default http://127.0.0.1:8000)
    BANK_NODE_TOKEN        secreto compartido con el plano de control (obligatorio)
    BANK_NODE_ID           identificador del nodo (default: nombre de la PC)
    BANK_NODE_TENANTS      tenants que atiende, separados por coma (default: el del nodo)
    BANK_NODE_CONCURRENCY  scrapes simultaneos (default 1)
    BANK_NODE_POLL_SEG     cada cuanto pedir trabajo (default 5)
    BANK_NODE_HEARTBEAT_SEG cada cuanto latir (default 30)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger("node_agent")

#: Version del agente: viaja en el heartbeat para saber que corre cada PC.
VERSION_AGENTE = "1.0.0"

#: Cada cuanto se renueva el candado mientras se raspa (TTL del lado API: 60 s).
RENOVAR_SEGUNDOS = 20

#: Timeout de las llamadas al plano de control (el claim puede tardar un poco).
TIMEOUT_HTTP = 20.0

#: Nombres de entorno.
ENV_API_URL = "BANK_API_URL"
ENV_TOKEN = "BANK_NODE_TOKEN"
ENV_NODE_ID = "BANK_NODE_ID"
ENV_TENANTS = "BANK_NODE_TENANTS"
ENV_CONCURRENCY = "BANK_NODE_CONCURRENCY"
ENV_POLL = "BANK_NODE_POLL_SEG"
ENV_HEARTBEAT = "BANK_NODE_HEARTBEAT_SEG"


# --- Plano de control (HTTP, stdlib: sin dependencias en la PC del cliente) --


class ErrorPlanoDeControl(RuntimeError):
    """Fallo de comunicacion con el plano de control."""

    def __init__(self, mensaje: str, *, status: int | None = None) -> None:
        super().__init__(mensaje)
        self.status = status


class PlanoDeControl:
    """Cliente HTTP del plano de control (heartbeat, claim, lock, resultado)."""

    def __init__(self, base_url: str, token: str, *, timeout: float = TIMEOUT_HTTP) -> None:
        self._base = base_url.rstrip("/") + "/api/erp/bank/node"
        self._token = token
        self._timeout = timeout

    def _llamar(self, ruta: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        datos = None if payload is None else json.dumps(payload).encode("utf-8")
        pedido = urllib.request.Request(
            self._base + ruta,
            data=datos,
            method="POST" if datos is not None else "GET",
            headers={
                "Content-Type": "application/json",
                "X-Node-Token": self._token,
            },
        )
        try:
            with urllib.request.urlopen(pedido, timeout=self._timeout) as respuesta:
                crudo = respuesta.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", errors="replace")[:200]
            raise ErrorPlanoDeControl(
                f"{ruta}: HTTP {exc.code} {detalle}", status=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            raise ErrorPlanoDeControl(f"{ruta}: sin conexion ({exc.reason})") from exc
        return json.loads(crudo) if crudo else {}

    def heartbeat(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return self._llamar("/heartbeat", cuerpo)

    def claim(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return self._llamar("/claim", cuerpo)

    def renovar(self, node_id: str, tenant: str) -> None:
        self._llamar("/lock/renew", {"node_id": node_id, "tenant": tenant})

    def liberar(self, node_id: str, tenant: str) -> None:
        self._llamar("/lock/release", {"node_id": node_id, "tenant": tenant})

    def publicar(
        self,
        tenant: str,
        job_id: str,
        *,
        node_id: str,
        estado: str,
        resultado: dict[str, Any] | None = None,
        error_codigo: str | None = None,
    ) -> None:
        self._llamar(
            f"/jobs/{job_id}/result?tenant={tenant}",
            {
                "node_id": node_id,
                "estado": estado,
                "resultado": resultado,
                "error_codigo": error_codigo,
            },
        )

    def estado(self) -> dict[str, Any]:
        return self._llamar("/status")


# --- Worker que publica por HTTP -------------------------------------------


def _worker_http(publicar: Any) -> Any:
    """Construye el worker reutilizando el scrape y el matching del worker real.

    Se importa aca adentro (y no arriba) para que `--estado` no cargue
    Playwright ni la base: el agente tiene que poder reportar salud aunque el
    navegador o el ERP esten rotos.
    """
    from motoshop_api.erp.bankreconciliation.jobs import EstadoJob
    from motoshop_api.erp.bankreconciliation.matching import normalizar_nombre  # noqa: F401
    from motoshop_api.erp.bankreconciliation.node_config import load_node_config
    from motoshop_api.erp.bankreconciliation.scraper import (
        BankScrapeError,
        CODIGO_SESION_CERRADA,
        SessionSlotError,
    )
    from motoshop_api.erp.bankreconciliation.value_match import (
        desde_movimiento_raspado,
        match_by_value,
    )
    from motoshop_api.erp.bankreconciliation.worker import (
        BankVerificationWorker,
        _estado_del_job,
    )

    class _JobsNoop:
        """El agente no toca la tabla de jobs: los estados los pone la API."""

        def __getattr__(self, nombre: str) -> Any:  # noqa: D401
            def _no(*_args: Any, **_kw: Any) -> Any:
                raise RuntimeError(f"el agente no usa jobs.{nombre}()")

            return _no

    class WorkerHTTP(BankVerificationWorker):
        """Ejecuta el job reclamado y publica cada transicion por HTTP."""

        def __init__(self, *, publicar_cb: Any, **kwargs: Any) -> None:
            self._publicar_cb = publicar_cb
            super().__init__(**kwargs)

        def ejecutar(self, job: Any) -> None:
            """Como `run_once`, pero el claim ya lo hizo el plano de control."""
            self._job_actual = job
            try:
                resultado = self._raspar(job)
            except BankScrapeError as exc:
                if exc.codigo == CODIGO_SESION_CERRADA:
                    # Conflicto de sesion, no un fallo: vuelve a la cola.
                    self._log.warning(
                        "La cuenta se abrio en otro dispositivo: el job %s vuelve a la cola",
                        job.job_id,
                    )
                    self._actualizar(job, EstadoJob.EN_COLA, error_codigo=exc.codigo)
                    return
                self._log.warning("Job %s fallido: %s", job.job_id, exc.codigo)
                self._actualizar(job, EstadoJob.FALLIDO, error_codigo=exc.codigo)
                return
            except SessionSlotError as exc:
                self._log.warning("Job %s sin turno de sesion: %s", job.job_id, exc.motivo)
                self._actualizar(job, EstadoJob.FALLIDO, error_codigo=exc.motivo)
                return
            finally:
                self._job_actual = None

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

        def _actualizar(
            self,
            job: Any,
            estado: Any,
            resultado: dict[str, Any] | None = None,
            error_codigo: str | None = None,
        ) -> None:
            self._publicar_cb(job, estado, resultado, error_codigo)

    return WorkerHTTP, _JobsNoop, load_node_config


def _job_desde_claim(datos: dict[str, Any]) -> Any:
    """Reconstruye el job de dominio desde la respuesta del claim."""
    from motoshop_api.erp.bankreconciliation.jobs import EstadoJob, VerificationJob

    def _fecha(valor: Any) -> datetime:
        if isinstance(valor, datetime):
            return valor
        return datetime.fromisoformat(str(valor))

    return VerificationJob(
        id=str(datos.get("id") or datos["job_id"]),
        job_id=str(datos["job_id"]),
        tenant=str(datos["tenant"]),
        factura_id=str(datos.get("factura_id") or ""),
        valor=Decimal(str(datos["valor"])),
        estado=EstadoJob.EJECUTANDO,
        creado_en=_fecha(datos["creado_en"]),
        actualizado_en=_fecha(datos.get("actualizado_en") or datos["creado_en"]),
        expira_en=_fecha(datos["expira_en"]),
        nodo=datos.get("nodo"),
        solicitud=datos.get("solicitud"),
    )


# --- Agente ----------------------------------------------------------------


class AgenteNodo:
    """Bucle del agente: late, reclama, raspa y publica."""

    def __init__(
        self,
        plano: PlanoDeControl,
        *,
        node_id: str,
        tenants: list[str],
        concurrencia: int = 1,
        poll_segundos: float = 5.0,
        heartbeat_segundos: float = 30.0,
    ) -> None:
        self._plano = plano
        self._node_id = node_id
        self._tenants = tenants
        self._concurrencia = max(1, int(concurrencia))
        self._poll = poll_segundos
        self._heartbeat = heartbeat_segundos
        self._activos: dict[str, int] = {tenant: 0 for tenant in tenants}
        self._parar = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._candado = threading.Lock()

    # --- estado ---

    @property
    def ocupados(self) -> int:
        with self._candado:
            return sum(self._activos.values())

    def _libres(self) -> int:
        return max(0, self._concurrencia - self.ocupados)

    def _latir(self) -> None:
        """Manda el heartbeat (una vez; el bucle lo repite)."""
        with self._candado:
            ocupados = sum(self._activos.values())
        cuerpo = {
            "node_id": self._node_id,
            "tenants": self._tenants,
            "slots_libres": max(0, self._concurrencia - ocupados),
            "slots_ocupados": ocupados,
            "version": VERSION_AGENTE,
        }
        try:
            respuesta = self._plano.heartbeat(cuerpo)
            en_linea = respuesta.get("tenants_en_linea") or {}
            logger.debug("heartbeat ok (%s tenants en linea)", len(en_linea))
        except ErrorPlanoDeControl as exc:
            logger.warning("heartbeat fallo: %s", exc)

    def _bucle_heartbeat(self) -> None:
        while not self._parar.wait(self._heartbeat):
            self._latir()

    # --- ejecucion de un job ---

    def _correr_job(self, datos: dict[str, Any]) -> None:
        tenant = str(datos["tenant"])
        job_id = str(datos["job_id"])
        with self._candado:
            self._activos[tenant] = self._activos.get(tenant, 0) + 1
        parar_renovacion = threading.Event()

        def _renovar() -> None:
            while not parar_renovacion.wait(RENOVAR_SEGUNDOS):
                try:
                    self._plano.renovar(self._node_id, tenant)
                except ErrorPlanoDeControl as exc:
                    logger.warning("no pude renovar el candado de %s: %s", tenant, exc)
                    return

        renovador = threading.Thread(target=_renovar, name=f"renovar-{tenant}", daemon=True)
        renovador.start()
        try:
            logger.info("job %s de %s: raspando", job_id, tenant)
            worker = self._armar_worker()
            worker.ejecutar(_job_desde_claim(datos))
        except ErrorPlanoDeControl as exc:
            logger.error("job %s: no pude publicar el resultado: %s", job_id, exc)
        except Exception:  # noqa: BLE001 - un job roto no puede tumbar el agente
            logger.exception("job %s: fallo inesperado del agente", job_id)
        finally:
            parar_renovacion.set()
            with self._candado:
                self._activos[tenant] = max(0, self._activos.get(tenant, 1) - 1)
            try:
                self._plano.liberar(self._node_id, tenant)
            except ErrorPlanoDeControl as exc:
                logger.warning("no pude liberar el candado de %s: %s", tenant, exc)
            logger.info("job %s de %s: terminado", job_id, tenant)

    def _armar_worker(self) -> Any:
        WorkerHTTP, JobsNoop, cargar = _worker_http(None)

        def _publicar(job: Any, estado: Any, resultado: Any, error_codigo: Any) -> None:
            self._plano.publicar(
                job.tenant,
                job.job_id,
                node_id=self._node_id,
                estado=getattr(estado, "value", estado),
                resultado=resultado,
                error_codigo=error_codigo,
            )

        config = cargar()
        return WorkerHTTP(
            publicar_cb=_publicar,
            jobs=JobsNoop(),
            config=config,
            nodo=self._node_id,
            pedir_codigo=self._pedir_otp,
        )

    def _pedir_otp(self, prompt: str) -> str:
        """Pide el codigo de un solo uso en la consola del nodo.

        Sin consola (arranque oculto) no hay forma de pedirlo: se devuelve
        vacio y el portal rechaza el codigo, que es un fallo explicito y no un
        cuelgue. El dia que el banco pida OTP en cada corrida hay que mandar el
        pedido al operador (fuera de este alcance).
        """
        try:
            return input(prompt)
        except (EOFError, OSError) as exc:
            logger.error("el portal pidio un codigo y no hay consola: %s", exc)
            return ""

    # --- bucles ---

    def latir_una_vez(self) -> None:
        self._latir()

    def reclamar_uno(self) -> dict[str, Any] | None:
        """Pide un job por tenant, respetando los slots libres."""
        for tenant in self._tenants:
            with self._candado:
                if self._activos.get(tenant, 0) >= 1 and self._concurrencia == 1:
                    continue
            if self._libres() <= 0:
                return None
            try:
                respuesta = self._plano.claim({"node_id": self._node_id, "tenants": [tenant]})
            except ErrorPlanoDeControl as exc:
                logger.warning("claim fallo: %s", exc)
                return None
            job = respuesta.get("job")
            if job:
                return job
        return None

    def ejecutar_una_vez(self) -> bool:
        """Reclama y ejecuta un job. Devuelve True si habia trabajo."""
        job = self.reclamar_uno()
        if not job:
            return False
        self._correr_job(job)
        return True

    def correr(self) -> None:
        """Bucle principal: heartbeat en un hilo y polling de trabajos."""
        logger.info(
            "agente %s: tenants=%s concurrencia=%d poll=%.0fs",
            self._node_id,
            ",".join(self._tenants),
            self._concurrencia,
            self._poll,
        )
        self._latir()
        hilo_latido = threading.Thread(target=self._bucle_heartbeat, name="heartbeat", daemon=True)
        hilo_latido.start()
        self._hilos.append(hilo_latido)
        try:
            while not self._parar.is_set():
                if self._libres() <= 0:
                    self._parar.wait(self._poll)
                    continue
                job = self.reclamar_uno()
                if job is None:
                    self._parar.wait(self._poll)
                    continue
                hilo = threading.Thread(target=self._correr_job, args=(job,), daemon=True)
                hilo.start()
                self._hilos.append(hilo)
        except KeyboardInterrupt:
            logger.info("agente detenido por el operador")
        finally:
            self.detener()

    def detener(self) -> None:
        self._parar.set()
        for hilo in self._hilos:
            hilo.join(timeout=5)


# --- CLI -------------------------------------------------------------------


def _entero(valor: str | None, default: int) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return default


def _configurar_log(destino: str | None = None) -> None:
    manejadores: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    ruta = Path(destino or (Path(__file__).resolve().parent / "logs" / "node_agent.log"))
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        manejadores.append(logging.FileHandler(ruta, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=manejadores,
    )


def _tenants_por_defecto() -> list[str]:
    """Tenants del nodo: los del entorno o, si no, el del `node_config`."""
    crudo = os.environ.get(ENV_TENANTS, "").strip()
    if crudo:
        return [t.strip() for t in crudo.split(",") if t.strip()]
    from motoshop_api.erp.bankreconciliation.node_config import load_node_config

    return [load_node_config().tenant]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente del nodo de verificacion bancaria")
    parser.add_argument("--una-vez", action="store_true", help="reclama y ejecuta un job y sale")
    parser.add_argument("--estado", action="store_true", help="heartbeat + estado y sale")
    parser.add_argument("--tenants", default=None, help="tenants separados por coma")
    parser.add_argument("--log", default=None, help="ruta del log")
    args = parser.parse_args(argv)

    _configurar_log(args.log)

    token = os.environ.get(ENV_TOKEN, "").strip()
    if not token:
        logger.error("falta %s: el plano de control no acepta nodos sin token", ENV_TOKEN)
        return 2
    base = os.environ.get(ENV_API_URL, "http://127.0.0.1:8000").strip()
    node_id = os.environ.get(ENV_NODE_ID, "").strip() or socket.gethostname().upper()
    if args.tenants:
        tenants = [t.strip() for t in args.tenants.split(",") if t.strip()]
    else:
        try:
            tenants = _tenants_por_defecto()
        except Exception as exc:  # noqa: BLE001 - sin config no hay tenants
            logger.error("no pude resolver los tenants del nodo: %s", exc)
            return 2
    if not tenants:
        logger.error("el nodo no tiene tenants configurados")
        return 2

    plano = PlanoDeControl(base, token)
    agente = AgenteNodo(
        plano,
        node_id=node_id,
        tenants=tenants,
        concurrencia=_entero(os.environ.get(ENV_CONCURRENCY), 1),
        poll_segundos=float(_entero(os.environ.get(ENV_POLL), 5)),
        heartbeat_segundos=float(_entero(os.environ.get(ENV_HEARTBEAT), 30)),
    )

    if args.estado:
        agente.latir_una_vez()
        try:
            print(json.dumps(plano.estado(), indent=2, default=str))
        except ErrorPlanoDeControl as exc:
            logger.error("no pude leer el estado: %s", exc)
            return 1
        return 0

    if args.una_vez:
        agente.latir_una_vez()
        hizo = agente.ejecutar_una_vez()
        logger.info("una-vez: %s", "ejecute un job" if hizo else "no habia trabajo")
        return 0

    agente.correr()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
