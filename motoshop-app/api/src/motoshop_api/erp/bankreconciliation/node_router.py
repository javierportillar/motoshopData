"""Plano de control del nodo (F0/F1): cola por cuenta, candado y heartbeat.

Este módulo es el **plano de control**: no raspa nunca. Sólo registra nodos,
entrega jobs de la cola y custodia el candado por cuenta. El scrape sigue en
la PC del cliente, en un proceso aparte (`infra/node_agent.py`).

Tres piezas y una regla de oro:

1. **Modo de despacho** (`BANK_DISPATCH_MODE`). `local` (default) deja todo
   como está hoy: el POST crea el job y un hilo dentro de la API lo corre.
   `queue` cambia *sólo* el despacho: el POST escribe la fila `en_cola` y
   devuelve 202 sin hilos dentro de la API; el agente del nodo la reclama.
   La regresión de `local` es explícita y está probada: es la red de
   seguridad (si el agente falla se cambia una variable y vuelve a andar).

2. **Candado por cuenta** (`app_bank_account_locks`, PK `tenant`). El banco
   permite dos cuentas abiertas a la vez pero no la misma cuenta en dos
   dispositivos. Adquirir es un `INSERT ... ON DUPLICATE KEY UPDATE` atómico:
   gana el que llega con el candado vencido o el que ya lo tenía. TTL 60 s,
   renovación cada 20 s mientras raspa. Sin preempción: si está vivo, no se
   arrebata. El que no lo tiene **no toca el portal**: ni login, ni ping.

3. **Dos relojes**. `expira_en` es la espera en cola (`BANK_JOB_QUEUE_TTL`,
   900 s): vencer ahí es `expirado` con motivo `sin_nodo`, nunca `fallido`.
   `actualizado_en` mientras el job está `ejecutando` es el reloj de
   ejecución (`BANK_JOB_EXEC_TTL`, 180 s): un `ejecutando` vencido se rescata
   a `en_cola` con `intentos + 1`, y al segundo intento queda `fallido`.

Un job que vuelve por "Tienes otra sesión abierta" no es un fallo: es un
conflicto de sesión. Vuelve a `en_cola` con el código
`sesion_cerrada_por_otro_dispositivo` y otro nodo (o el mismo, más tarde) lo
retoma.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

__all__ = [
    "CODIGO_EJECUCION_VENCIDA",
    "CODIGO_SESION_CERRADA",
    "CODIGO_SIN_NODO",
    "ENV_MODO_DESPACHO",
    "ENV_TOKEN_NODO",
    "EXEC_TTL_SEGUNDOS",
    "LOCK_TTL_SEGUNDOS",
    "MODO_LOCAL",
    "MODO_QUEUE",
    "NodoStore",
    "QUEUE_TTL_SEGUNDOS",
    "configurar_modo_despacho",
    "modo_despacho",
    "router",
    "start_sweeper",
]

log = logging.getLogger(__name__)

# --- Configuración (variables de entorno, sin tocar `config.py`) ------------

#: `local` (default) | `queue`. Es la única perilla que cambia el despacho.
ENV_MODO_DESPACHO = "BANK_DISPATCH_MODE"
MODO_LOCAL = "local"
MODO_QUEUE = "queue"

#: Secreto compartido entre la API y el agente del nodo (`X-Node-Token`).
ENV_TOKEN_NODO = "BANK_NODE_TOKEN"

#: Candado por cuenta: TTL y renovación mientras se raspa.
LOCK_TTL_SEGUNDOS = 60
LOCK_RENOVAR_SEGUNDOS = 20

#: Un nodo sin latir por más de esto se considera caído (failover).
HEARTBEAT_CAIDO_SEGUNDOS = 90

#: Espera máxima en cola: vencer acá es `expirado`/`sin_nodo`, nunca `fallido`.
QUEUE_TTL_SEGUNDOS = 900

#: Ejecución máxima: pasado esto el claim rescata el job a `en_cola`.
EXEC_TTL_SEGUNDOS = 180

#: Intentos de ejecución antes de darlo por `fallido`.
INTENTOS_MAX = 2

#: Barrido del plano de control (rescate + vencidos de cola).
BARRIDO_SEGUNDOS = 15

#: Códigos estables (viajan al job; nunca el mensaje crudo del portal).
CODIGO_SIN_NODO = "sin_nodo"
CODIGO_EJECUCION_VENCIDA = "ejecucion_vencida"
CODIGO_SESION_CERRADA = "sesion_cerrada_por_otro_dispositivo"

#: Estados que el agente puede publicar.
ESTADOS_PUBLICABLES = frozenset(
    {"resuelto", "sin_coincidencia", "ambiguo", "fallido", "expirado", "en_cola"}
)


def _entero_env(nombre: str, default: int) -> int:
    """Entero de entorno; si viene mal, el default (nunca rompe el arranque)."""
    try:
        return int(os.environ.get(nombre, "").strip() or default)
    except ValueError:
        return default


def modo_despacho() -> str:
    """Modo efectivo de despacho (`local` si el valor no se reconoce)."""
    valor = os.environ.get(ENV_MODO_DESPACHO, "").strip().lower()
    return MODO_QUEUE if valor == MODO_QUEUE else MODO_LOCAL


def _ahora() -> datetime:
    """UTC naive: la misma convención que `jobs.py` (MySQL 5.0 sin zona)."""
    return datetime.now(UTC).replace(tzinfo=None)


# --- SQL -------------------------------------------------------------------

_SQL_HEARTBEAT = """
INSERT INTO app_bank_nodes
  (node_id, tenants, slots_libres, slots_ocupados, version, latida_en, visto_en)
VALUES
  (:node_id, :tenants, :slots_libres, :slots_ocupados, :version, :now, :now)
ON DUPLICATE KEY UPDATE
  tenants = VALUES(tenants),
  slots_libres = VALUES(slots_libres),
  slots_ocupados = VALUES(slots_ocupados),
  version = VALUES(version),
  latida_en = VALUES(latida_en)
"""

#: Adquisición atómica del candado. El `IF` se evalúa contra la fila actual y
#: `node_id` se actualiza al final para que las condiciones vean el valor viejo.
_SQL_LOCK = """
INSERT INTO app_bank_account_locks (tenant, node_id, latida_en, vence_en)
VALUES (:tenant, :node_id, :now, :vence)
ON DUPLICATE KEY UPDATE
  latida_en = IF(vence_en < :now OR node_id = :node_id, VALUES(latida_en), latida_en),
  vence_en  = IF(vence_en < :now OR node_id = :node_id, VALUES(vence_en), vence_en),
  node_id   = IF(vence_en < :now OR node_id = :node_id, VALUES(node_id), node_id)
"""

_SQL_LOCK_LEER = """
SELECT node_id, latida_en, vence_en FROM app_bank_account_locks WHERE tenant = :tenant
"""

_SQL_LOCK_RENOVAR = """
UPDATE app_bank_account_locks
SET latida_en = :now, vence_en = :vence
WHERE tenant = :tenant AND node_id = :node_id
"""

_SQL_LOCK_LIBERAR = """
DELETE FROM app_bank_account_locks WHERE tenant = :tenant AND node_id = :node_id
"""

_SQL_COLA_CANDIDATO = """
SELECT job_id FROM app_bank_verification_jobs
WHERE tenant = :tenant AND estado = 'en_cola' AND expira_en > :now
ORDER BY creado_en ASC
LIMIT 1
"""

#: Claim atómico. `expira_en` se estira al reloj de ejecución: la cola ya
#: terminó cuando el job se toma.
_SQL_CLAIM = """
UPDATE app_bank_verification_jobs
SET estado = 'ejecutando',
    nodo = :node_id,
    actualizado_en = :now,
    expira_en = :vence_ejecucion
WHERE tenant = :tenant
  AND job_id = :job_id
  AND estado = 'en_cola'
  AND expira_en > :now
"""

#: Rescate del `ejecutando` vencido. El orden importa: `intentos` se
#: incrementa primero y las expresiones siguientes ya ven el valor nuevo.
_SQL_RESCATE = """
UPDATE app_bank_verification_jobs
SET intentos = intentos + 1,
    estado = IF(intentos >= :max_intentos, 'fallido', 'en_cola'),
    error_codigo = :codigo,
    nodo = IF(intentos >= :max_intentos, nodo, NULL),
    actualizado_en = :now
WHERE estado = 'ejecutando'
  AND actualizado_en <= :limite
"""

#: Cola vencida: `expirado` con motivo `sin_nodo`, nunca `fallido`.
_SQL_EXPIRAR_COLA = """
UPDATE app_bank_verification_jobs
SET estado = 'expirado', error_codigo = :codigo, actualizado_en = :now
WHERE estado = 'en_cola'
  AND creado_en <= :limite
"""

_SQL_PUBLICAR = """
UPDATE app_bank_verification_jobs
SET estado = :estado,
    resultado_json = :resultado_json,
    error_codigo = :error_codigo,
    nodo = :nodo,
    actualizado_en = :now,
    expira_en = :expira_en
WHERE tenant = :tenant AND job_id = :job_id AND estado = 'ejecutando' AND nodo = :node_id
"""

_SQL_NODOS = """
SELECT node_id, tenants, slots_libres, slots_ocupados, version, latida_en
FROM app_bank_nodes
WHERE latida_en > :limite
"""


class NodoStore:
    """Persistencia del plano de control (tablas `app_bank_*`)."""

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    def _motor(self) -> Any:
        if self._engine is not None:
            return self._engine
        from motoshop_api.db.engine import get_writer_engine

        return get_writer_engine()

    # --- nodos ---

    def heartbeat(
        self,
        node_id: str,
        tenants: list[str],
        *,
        slots_libres: int,
        slots_ocupados: int,
        version: str | None = None,
        ahora: datetime | None = None,
    ) -> None:
        from sqlalchemy import text

        with self._motor().connect() as conn:
            conn.execute(
                text(_SQL_HEARTBEAT),
                {
                    "node_id": node_id,
                    "tenants": ",".join(tenants),
                    "slots_libres": slots_libres,
                    "slots_ocupados": slots_ocupados,
                    "version": version,
                    "now": ahora or _ahora(),
                },
            )
            conn.commit()

    def nodos_en_linea(self, ahora: datetime | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text

        instante = ahora or _ahora()
        limite = instante - timedelta(seconds=HEARTBEAT_CAIDO_SEGUNDOS)
        with self._motor().connect() as conn:
            filas = conn.execute(text(_SQL_NODOS), {"limite": limite}).mappings().all()
        return [
            {
                "node_id": fila["node_id"],
                "tenants": [t for t in (fila["tenants"] or "").split(",") if t],
                "slots_libres": fila["slots_libres"],
                "slots_ocupados": fila["slots_ocupados"],
                "version": fila["version"],
                "latida_en": fila["latida_en"],
            }
            for fila in filas
        ]

    def tenants_en_linea(self, ahora: datetime | None = None) -> dict[str, list[str]]:
        """Tenant → nodos que lo atienden y están latiendo."""
        mapa: dict[str, list[str]] = {}
        for nodo in self.nodos_en_linea(ahora):
            for tenant in nodo["tenants"]:
                mapa.setdefault(tenant, []).append(nodo["node_id"])
        return mapa

    # --- candado por cuenta ---

    def adquirir_lock(
        self, tenant: str, node_id: str, *, ahora: datetime | None = None
    ) -> bool:
        """Toma el candado del tenant si está libre o vencido (o si es mío)."""
        from sqlalchemy import text

        instante = ahora or _ahora()
        with self._motor().connect() as conn:
            conn.execute(
                text(_SQL_LOCK),
                {
                    "tenant": tenant,
                    "node_id": node_id,
                    "now": instante,
                    "vence": instante + timedelta(seconds=LOCK_TTL_SEGUNDOS),
                },
            )
            conn.commit()
            fila = conn.execute(text(_SQL_LOCK_LEER), {"tenant": tenant}).mappings().first()
        return fila is not None and fila["node_id"] == node_id

    def renovar_lock(
        self, tenant: str, node_id: str, *, ahora: datetime | None = None
    ) -> bool:
        from sqlalchemy import text

        instante = ahora or _ahora()
        with self._motor().connect() as conn:
            resultado = conn.execute(
                text(_SQL_LOCK_RENOVAR),
                {
                    "tenant": tenant,
                    "node_id": node_id,
                    "now": instante,
                    "vence": instante + timedelta(seconds=LOCK_TTL_SEGUNDOS),
                },
            )
            conn.commit()
            return bool(resultado.rowcount)

    def liberar_lock(self, tenant: str, node_id: str) -> None:
        from sqlalchemy import text

        with self._motor().connect() as conn:
            conn.execute(
                text(_SQL_LOCK_LIBERAR), {"tenant": tenant, "node_id": node_id}
            )
            conn.commit()

    def lock_de(self, tenant: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        with self._motor().connect() as conn:
            fila = conn.execute(text(_SQL_LOCK_LEER), {"tenant": tenant}).mappings().first()
        if fila is None:
            return None
        return {
            "tenant": tenant,
            "node_id": fila["node_id"],
            "latida_en": fila["latida_en"],
            "vence_en": fila["vence_en"],
        }

    # --- cola ---

    def claim(
        self,
        tenant: str,
        node_id: str,
        *,
        ahora: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Toma el job más viejo de la cola del tenant (o `None`).

        El candado del tenant tiene que estar en mano del nodo: quien llama ya
        lo verificó. Dos nodos con el candado vencido no pueden reclamar el
        mismo job: el `UPDATE` condicionado a `estado = 'en_cola'` decide por
        `rowcount`.
        """
        from sqlalchemy import text

        instante = ahora or _ahora()
        with self._motor().connect() as conn:
            fila = conn.execute(
                text(_SQL_COLA_CANDIDATO), {"tenant": tenant, "now": instante}
            ).mappings().first()
            if fila is None:
                return None
            job_id = fila["job_id"]
            resultado = conn.execute(
                text(_SQL_CLAIM),
                {
                    "tenant": tenant,
                    "job_id": job_id,
                    "node_id": node_id,
                    "now": instante,
                    "vence_ejecucion": instante + timedelta(seconds=EXEC_TTL_SEGUNDOS),
                },
            )
            conn.commit()
            if not resultado.rowcount:
                return None
            vuelta = conn.execute(
                text(
                    "SELECT job_id, tenant, factura_id, valor, estado, creado_en, "
                    "expira_en, nodo, intentos FROM app_bank_verification_jobs "
                    "WHERE tenant = :tenant AND job_id = :job_id"
                ),
                {"tenant": tenant, "job_id": job_id},
            ).mappings().first()
        if vuelta is None:
            return None
        return {
            "job_id": vuelta["job_id"],
            "tenant": vuelta["tenant"],
            "factura_id": vuelta["factura_id"],
            "valor": str(vuelta["valor"]),
            "estado": vuelta["estado"],
            "creado_en": vuelta["creado_en"],
            "expira_en": vuelta["expira_en"],
            "nodo": vuelta["nodo"],
            "intentos": int(vuelta.get("intentos") or 0),
            "lock_segundos": LOCK_TTL_SEGUNDOS,
        }

    def publicar(
        self,
        tenant: str,
        node_id: str,
        job_id: str,
        estado: str,
        *,
        resultado: dict[str, Any] | None = None,
        error_codigo: str | None = None,
        ahora: datetime | None = None,
    ) -> bool:
        """Publica el resultado del job (sólo si lo ejecutaba este nodo).

        Un `en_cola` acá significa "conflicto de sesión": el job vuelve a la
        cola con el motivo, sin dueño, y se le renueva la espera.
        """
        if estado not in ESTADOS_PUBLICABLES:
            raise ValueError(f"estado no publicable: {estado}")
        from sqlalchemy import text

        instante = ahora or _ahora()
        vuelve_a_cola = estado == "en_cola"
        with self._motor().connect() as conn:
            resultado_ejecucion = conn.execute(
                text(_SQL_PUBLICAR),
                {
                    "tenant": tenant,
                    "job_id": job_id,
                    "node_id": node_id,
                    "estado": estado,
                    "resultado_json": None if resultado is None else _json(resultado),
                    "error_codigo": error_codigo,
                    "nodo": None if vuelve_a_cola else node_id,
                    "now": instante,
                    "expira_en": instante + timedelta(seconds=QUEUE_TTL_SEGUNDOS),
                },
            )
            conn.commit()
            return bool(resultado_ejecucion.rowcount)

    # --- barrido ---

    def rescatar_vencidos(self, *, ahora: datetime | None = None) -> int:
        """`ejecutando` pasado el reloj de ejecución → `en_cola` / `fallido`."""
        from sqlalchemy import text

        instante = ahora or _ahora()
        limite = instante - timedelta(seconds=_entero_env("BANK_JOB_EXEC_TTL", EXEC_TTL_SEGUNDOS))
        with self._motor().connect() as conn:
            resultado = conn.execute(
                text(_SQL_RESCATE),
                {
                    "limite": limite,
                    "max_intentos": INTENTOS_MAX,
                    "codigo": CODIGO_EJECUCION_VENCIDA,
                    "now": instante,
                },
            )
            conn.commit()
            return int(resultado.rowcount or 0)

    def expirar_cola(self, *, ahora: datetime | None = None) -> int:
        """`en_cola` sin nodo pasado el TTL de cola → `expirado`/`sin_nodo`."""
        from sqlalchemy import text

        instante = ahora or _ahora()
        limite = instante - timedelta(
            seconds=_entero_env("BANK_JOB_QUEUE_TTL", QUEUE_TTL_SEGUNDOS)
        )
        with self._motor().connect() as conn:
            resultado = conn.execute(
                text(_SQL_EXPIRAR_COLA), {"limite": limite, "codigo": CODIGO_SIN_NODO, "now": instante}
            )
            conn.commit()
            return int(resultado.rowcount or 0)


def _json(datos: dict[str, Any]) -> str:
    import json

    return json.dumps(datos, default=str)


# --- API del plano de control ----------------------------------------------

router = APIRouter(tags=["bank-node"])


class HeartbeatIn(BaseModel):
    """Latido del agente: quién es, qué atiende y cuántos slots le quedan."""

    node_id: str = Field(min_length=1, max_length=64)
    tenants: list[str] = Field(default_factory=list)
    slots_libres: int = Field(default=1, ge=0)
    slots_ocupados: int = Field(default=0, ge=0)
    version: str | None = Field(default=None, max_length=32)


class ClaimIn(BaseModel):
    """Pedido de trabajo: el agente declara sus tenants y espera un job."""

    node_id: str = Field(min_length=1, max_length=64)
    tenants: list[str] = Field(min_length=1)


class LockIn(BaseModel):
    """Renovación o liberación del candado de una cuenta."""

    node_id: str = Field(min_length=1, max_length=64)
    tenant: str = Field(min_length=1, max_length=32)


class ResultadoIn(BaseModel):
    """Resultado del scrape, tal como lo publica el agente."""

    node_id: str = Field(min_length=1, max_length=64)
    estado: str = Field(min_length=1, max_length=32)
    resultado: dict[str, Any] | None = None
    error_codigo: str | None = Field(default=None, max_length=64)


def exigir_token(x_node_token: str | None = Header(default=None)) -> None:
    """Autentica al agente con el secreto compartido (falla cerrado)."""
    esperado = os.environ.get(ENV_TOKEN_NODO, "").strip()
    if not esperado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BANK_NODE_TOKEN no configurado: el plano de control queda cerrado",
        )
    if not x_node_token or not secrets.compare_digest(x_node_token, esperado):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token de nodo inválido")


def get_nodo_store() -> NodoStore:
    """Store real del plano de control (tests inyectan uno con engine falso)."""
    return NodoStore()


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatIn,
    tienda: NodoStore = Depends(get_nodo_store),
    _: None = Depends(exigir_token),
) -> dict[str, Any]:
    """Registra el latido y devuelve el mapa de tenants en línea."""
    tienda.heartbeat(
        body.node_id,
        body.tenants,
        slots_libres=body.slots_libres,
        slots_ocupados=body.slots_ocupados,
        version=body.version,
    )
    return {"ok": True, "tenants_en_linea": tienda.tenants_en_linea()}


@router.post("/claim")
def claim(
    body: ClaimIn,
    tienda: NodoStore = Depends(get_nodo_store),
    _: None = Depends(exigir_token),
) -> dict[str, Any]:
    """Entrega el próximo job del nodo, tomando el candado de la cuenta.

    Sin candado no hay job: el nodo que no lo consigue **no toca el portal**.
    El agente reintenta a los 5 s (lo decide él, no la API).
    """
    for tenant in body.tenants:
        if not tienda.adquirir_lock(tenant, body.node_id):
            continue
        job = tienda.claim(tenant, body.node_id)
        if job is not None:
            return {"job": job}
        # Sin trabajo: se suelta el candado para no bloquear a otro nodo.
        tienda.liberar_lock(tenant, body.node_id)
    return {"job": None}


@router.post("/lock/renew")
def renovar_lock(
    body: LockIn,
    tienda: NodoStore = Depends(get_nodo_store),
    _: None = Depends(exigir_token),
) -> dict[str, Any]:
    """Renueva el TTL del candado (cada 20 s mientras raspa)."""
    if not tienda.renovar_lock(body.tenant, body.node_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="candado perdido: el nodo ya no es dueño de la cuenta",
        )
    return {"ok": True}


@router.post("/lock/release")
def liberar_lock(
    body: LockIn,
    tienda: NodoStore = Depends(get_nodo_store),
    _: None = Depends(exigir_token),
) -> dict[str, Any]:
    """Suelta el candado al terminar (con o sin resultado)."""
    tienda.liberar_lock(body.tenant, body.node_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/result")
def publicar_resultado(
    job_id: str,
    body: ResultadoIn,
    tenant: str,
    tienda: NodoStore = Depends(get_nodo_store),
    _: None = Depends(exigir_token),
) -> dict[str, Any]:
    """Publica el resultado. Sólo lo puede hacer el nodo que ejecutaba el job."""
    try:
        aplicado = tienda.publicar(
            tenant,
            body.node_id,
            job_id,
            body.estado,
            resultado=body.resultado,
            error_codigo=body.error_codigo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if not aplicado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="el job ya no está ejecutando por este nodo",
        )
    return {"ok": True}


@router.get("/status")
def status_plano(
    tienda: NodoStore = Depends(get_nodo_store),
    _: None = Depends(exigir_token),
) -> dict[str, Any]:
    """Estado del plano de control: nodos en línea y dueños de cada cuenta."""
    return {"tenants_en_linea": tienda.tenants_en_linea()}


# --- Barrido y modo de despacho -------------------------------------------


class _Sweeper:
    """Hilo de barrido del plano de control (cada 15 s)."""

    def __init__(self, store: NodoStore | None = None) -> None:
        self._store = store or NodoStore()
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._correr, name="bank-sweeper", daemon=True)

    def start(self) -> "_Sweeper":
        self._hilo.start()
        return self

    def stop(self) -> None:
        self._parar.set()
        if self._hilo.is_alive():
            self._hilo.join(timeout=5)

    def _correr(self) -> None:
        en_cola = modo_despacho() == MODO_QUEUE
        while not self._parar.wait(BARRIDO_SEGUNDOS):
            try:
                rescatados = self._store.rescatar_vencidos()
                expirados = self._store.expirar_cola() if en_cola else 0
                if rescatados or expirados:
                    log.warning(
                        "plano de control: %d ejecutando rescatados, %d en cola expirados",
                        rescatados,
                        expirados,
                    )
            except Exception:  # noqa: BLE001 - el barrido no puede tumbar la API
                log.exception("fallo el barrido del plano de control")


_SWEEPER: _Sweeper | None = None


def start_sweeper() -> _Sweeper | None:
    """Arranca el barrido una sola vez por proceso (no en tests)."""
    global _SWEEPER
    from motoshop_api.config import settings

    if settings.env == "test":
        return None
    if _SWEEPER is None:
        _SWEEPER = _Sweeper().start()
    return _SWEEPER


def configurar_modo_despacho(app: Any) -> None:
    """Aplica `BANK_DISPATCH_MODE` sobre el despacho del POST de verificaciones.

    `local` (default): no toca nada, el despacho de `router.py` sigue igual.
    `queue`: reemplaza la dependencia `get_despachador` por un no-op, así el
    POST sólo escribe la fila `en_cola` y devuelve 202 sin hilos dentro de la
    API. No se edita `router.py`: se usa el mecanismo de override de FastAPI.
    """
    if modo_despacho() != MODO_QUEUE:
        log.info("bank dispatch mode=local (sin cola: el hilo corre en la API)")
        return
    from motoshop_api.erp.bankreconciliation.router import get_despachador

    def _sin_despacho(_job: Any) -> None:
        """En modo cola el job espera: lo toma el agente del nodo."""
        return None

    app.dependency_overrides[get_despachador] = lambda: _sin_despacho
    log.info("bank dispatch mode=queue (el POST sólo encola; raspa el agente)")
