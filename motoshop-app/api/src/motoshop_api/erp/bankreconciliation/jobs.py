"""Jobs de verificación bancaria (S6 · 6.1) — `app_bank_verification_jobs`.

El scrape del portal tarda 10–40 s, así que no cabe en un request HTTP: el
verificador pide un **job** y el nodo local lo corre. El job tiene dos
identidades, y esa distinción es deliberada:

- `id`: identificador de **dominio** — `uuid5(NAMESPACE_DOMINIO,
  f"{tenant}:{factura_id}:{valor}")`. Estable y determinista: pedir dos veces
  la verificación de la misma factura por el mismo importe devuelve **el
  mismo job** (la idempotencia es de la tabla: el `id` es la PK).
- `job_id`: identificador **público** — un `uuid4` único por job. Es el que
  viaja en la URL y el que el front sondea; nunca es adivinable.

El importe es `Decimal` con **dos decimales** (nunca float) y se normaliza
antes de calcular el id: `458200` y `458200.00` son el mismo job.

Los estados son los del contrato: `en_cola`, `ejecutando`, `esperando_otp`,
`resuelto`, `sin_coincidencia`, `ambiguo`, `fallido`, `expirado`. Las
transiciones las gobierna el worker (`worker.py`), no el store: el store sólo
escribe el estado que le pidan.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any, Protocol

from motoshop_api.erp.bankreconciliation.store import NAMESPACE_DOMINIO

#: Vida máxima del job (segundos). El diseño D2 da 120 s de scrape y 300 s
#: esperando el código de un solo uso: 300 s es el techo.
TTL_SEGUNDOS = 300

#: Dos decimales exactos (`DECIMAL(18,2)`).
_PRECISION_VALOR = Decimal("0.01")


class EstadoJob(StrEnum):
    """Estados del job de verificación (el contrato de la UI los conoce)."""

    EN_COLA = "en_cola"
    EJECUTANDO = "ejecutando"
    ESPERANDO_OTP = "esperando_otp"
    RESUELTO = "resuelto"
    SIN_COINCIDENCIA = "sin_coincidencia"
    AMBIGUO = "ambiguo"
    FALLIDO = "fallido"
    EXPIRADO = "expirado"


#: Todos los estados del contrato, como texto.
ESTADOS_DEL_JOB = frozenset(estado.value for estado in EstadoJob)

#: Estados en los que el job ya no vuelve a moverse.
ESTADOS_TERMINALES = frozenset(
    {
        EstadoJob.RESUELTO,
        EstadoJob.SIN_COINCIDENCIA,
        EstadoJob.AMBIGUO,
        EstadoJob.FALLIDO,
        EstadoJob.EXPIRADO,
    }
)


@dataclass(frozen=True)
class VerificationJob:
    """Un job de verificación persistido.

    `id` es el identificador de dominio (la PK), `job_id` el público (el que
    viaja en la URL), `tenant` el dueño (los tenants nunca se cruzan), `valor`
    el importe a verificar (`Decimal` de dos decimales) y `error_codigo` el
    código estable del fallo (nunca el mensaje crudo del portal).
    """

    id: str
    job_id: str
    tenant: str
    factura_id: str
    valor: Decimal
    estado: EstadoJob
    creado_en: datetime
    actualizado_en: datetime
    expira_en: datetime
    nodo: str | None = None
    resultado: dict[str, Any] | None = None
    error_codigo: str | None = None


class VerificationJobStore(Protocol):
    """Contrato de persistencia de los jobs (doble falso y real)."""

    def create_job(self, tenant: str, factura_id: str, valor: Decimal) -> VerificationJob: ...

    def get_job(self, tenant: str, job_id: str) -> VerificationJob | None: ...

    def update_job(
        self,
        tenant: str,
        job_id: str,
        estado: EstadoJob | str,
        resultado: dict[str, Any] | None = None,
        error_codigo: str | None = None,
        nodo: str | None = None,
    ) -> bool: ...

    def expire_stale_jobs(self, now: datetime) -> int: ...

    def reclamar_ejecucion(
        self, tenant: str, job_id: str, *, nodo: str | None = None
    ) -> bool: ...


def id_dominio_job(tenant: str, factura_id: str, valor: Decimal) -> str:
    """Identificador de dominio del job: `uuid5` de `tenant:factura_id:valor`.

    Es estable entre procesos y distinto entre tenants: el mismo job se
    reconoce sin guardar nada más.
    """
    return str(uuid.uuid5(NAMESPACE_DOMINIO, f"{tenant}:{factura_id}:{valor}"))


def _valor_normalizado(valor: Decimal) -> Decimal:
    """Importe a dos decimales exactos (la forma canónica del id de dominio)."""
    return valor.quantize(_PRECISION_VALOR, rounding=ROUND_HALF_UP)


def _ahora() -> datetime:
    """Instante actual en UTC naive (MySQL 5.0 no guarda zona horaria)."""
    return datetime.now(UTC).replace(tzinfo=None)


class FakeVerificationJobStore:
    """Doble en memoria: mismas restricciones que la tabla real.

    Reproduce la PK de dominio (un job por `tenant:factura_id:valor`), el
    `job_id` público único, el filtro por tenant de todas las lecturas y la
    expiración por TTL.
    """

    def __init__(
        self,
        *,
        reloj: Callable[[], datetime] | None = None,
        ttl_segundos: int = TTL_SEGUNDOS,
    ) -> None:
        self.jobs: dict[str, VerificationJob] = {}
        self._reloj = reloj or _ahora
        self._ttl = ttl_segundos

    def create_job(self, tenant: str, factura_id: str, valor: Decimal) -> VerificationJob:
        importe = _valor_normalizado(valor)
        id_dominio = id_dominio_job(tenant, factura_id, importe)
        existente = self.jobs.get(id_dominio)
        # La idempotencia protege la verificación EN CURSO (no se raspa dos
        # veces lo mismo). Un job terminado no bloquea el reintento: si el
        # portal falló o el OTP caducó, el operador tiene que poder pedirlo de
        # nuevo para la misma factura y el mismo importe.
        if existente is not None and existente.estado not in ESTADOS_TERMINALES:
            return existente
        ahora = self._reloj()
        job = VerificationJob(
            id=id_dominio,
            job_id=str(uuid.uuid4()),
            tenant=tenant,
            factura_id=factura_id,
            valor=importe,
            estado=EstadoJob.EN_COLA,
            creado_en=ahora,
            actualizado_en=ahora,
            expira_en=ahora + timedelta(seconds=self._ttl),
        )
        self.jobs[id_dominio] = job
        return job

    def get_job(self, tenant: str, job_id: str) -> VerificationJob | None:
        return self._buscar(tenant, job_id)

    def update_job(
        self,
        tenant: str,
        job_id: str,
        estado: EstadoJob | str,
        resultado: dict[str, Any] | None = None,
        error_codigo: str | None = None,
        nodo: str | None = None,
    ) -> bool:
        job = self._buscar(tenant, job_id)
        if job is None:
            return False
        cambios: dict[str, Any] = {
            "estado": EstadoJob(estado),
            "actualizado_en": self._reloj(),
        }
        # Un `None` no toca la fila (mismo contrato que `move_to_state`).
        if resultado is not None:
            cambios["resultado"] = resultado
        if error_codigo is not None:
            cambios["error_codigo"] = error_codigo
        if nodo is not None:
            cambios["nodo"] = nodo
        actualizado = replace(job, **cambios)
        self.jobs[actualizado.id] = actualizado
        return True

    def reclamar_ejecucion(
        self, tenant: str, job_id: str, *, nodo: str | None = None
    ) -> bool:
        """Toma el job sólo si sigue `en_cola` (claim atómico del worker).

        El despacho levanta un hilo por petición y el doble clic llega con dos
        hilos para el mismo `job`: el primero reclama y raspa, el segundo
        entra acá, no reclama y muere **sin tocar estados** (un `fallido`
        espurio del segundo hilo enmascaraba el resultado del primero).
        """
        job = self._buscar(tenant, job_id)
        if job is None or job.estado is not EstadoJob.EN_COLA:
            return False
        cambios: dict[str, Any] = {
            "estado": EstadoJob.EJECUTANDO,
            "actualizado_en": self._reloj(),
        }
        if nodo is not None:
            cambios["nodo"] = nodo
        self.jobs[job.id] = replace(job, **cambios)
        return True

    def expire_stale_jobs(self, now: datetime) -> int:
        """Pasa a `expirado` los jobs vencidos que siguen en curso."""
        expirados = 0
        for id_dominio, job in list(self.jobs.items()):
            if job.estado in ESTADOS_TERMINALES:
                continue
            if job.expira_en > now:
                continue
            self.jobs[id_dominio] = replace(job, estado=EstadoJob.EXPIRADO, actualizado_en=now)
            expirados += 1
        return expirados

    def _buscar(self, tenant: str, job_id: str) -> VerificationJob | None:
        """Job del tenant con ese `job_id` (público) o ese id de dominio."""
        for job in self.jobs.values():
            if job.tenant != tenant:
                continue
            if job.job_id == job_id or job.id == job_id:
                return job
        return None


# --- El store real ---


_SQL_SELECT = """
SELECT id, job_id, tenant, factura_id, valor, estado, nodo, resultado_json,
       error_codigo, creado_en, actualizado_en, expira_en
FROM app_bank_verification_jobs
WHERE tenant = :tenant
"""

_SQL_INSERT = """
INSERT INTO app_bank_verification_jobs
  (id, job_id, tenant, factura_id, valor, estado, nodo, resultado_json,
   error_codigo, creado_en, actualizado_en, expira_en)
VALUES
  (:id, :job_id, :tenant, :factura_id, :valor, :estado, :nodo, :resultado_json,
   :error_codigo, :creado_en, :actualizado_en, :expira_en)
ON DUPLICATE KEY UPDATE id = VALUES(id)
"""

#: Revive el job de dominio cuando el anterior ya terminó: es el reintento del
#: operador (portal caído, OTP caducado), no una verificación nueva en paralelo.
#: El `job_id` público cambia: quien sondee el intento viejo ve el estado viejo.
_SQL_REVIVIR = """
UPDATE app_bank_verification_jobs
SET job_id = :job_id,
    estado = 'en_cola',
    nodo = NULL,
    resultado_json = NULL,
    error_codigo = NULL,
    creado_en = :creado_en,
    actualizado_en = :actualizado_en,
    expira_en = :expira_en
WHERE tenant = :tenant
  AND id = :id
  AND estado IN ('resuelto', 'sin_coincidencia', 'ambiguo', 'fallido', 'expirado')
"""

_SQL_EXPIRAR = """UPDATE app_bank_verification_jobs
SET estado = 'expirado', actualizado_en = :now
WHERE estado NOT IN ('resuelto', 'sin_coincidencia', 'ambiguo', 'fallido', 'expirado')
  AND expira_en <= :now
"""

#: Claim atómico: sólo un hilo de los varios que el despacho puede levantar
#: para el mismo job (doble clic) logra el paso `en_cola → ejecutando`.
_SQL_RECLAMAR = """UPDATE app_bank_verification_jobs
SET estado = 'ejecutando', nodo = :nodo, actualizado_en = :now
WHERE tenant = :tenant
  AND (job_id = :job_id OR id = :job_id)
  AND estado = 'en_cola'
  AND expira_en > :now
"""


class RealVerificationJobStore:
    """Store real sobre `app_bank_verification_jobs` (InnoDB, motor de escritura)."""

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    def _motor(self) -> Any:
        if self._engine is not None:
            return self._engine
        from motoshop_api.db.engine import get_writer_engine

        return get_writer_engine()

    def create_job(self, tenant: str, factura_id: str, valor: Decimal) -> VerificationJob:
        from sqlalchemy import text

        importe = _valor_normalizado(valor)
        id_dominio = id_dominio_job(tenant, factura_id, importe)
        ahora = _ahora()
        params = {
            "id": id_dominio,
            "job_id": str(uuid.uuid4()),
            "tenant": tenant,
            "factura_id": factura_id,
            "valor": str(importe),
            "estado": EstadoJob.EN_COLA.value,
            "nodo": None,
            "resultado_json": None,
            "error_codigo": None,
            "creado_en": ahora,
            "actualizado_en": ahora,
            "expira_en": ahora + timedelta(seconds=TTL_SEGUNDOS),
        }
        with self._motor().connect() as conn:
            # La idempotencia es de la tabla y protege el job EN CURSO: si ya
            # existe (otra corrida, otra petición), la fila gana y se devuelve
            # tal cual. Si la fila ya terminó, `_SQL_REVIVIR` la devuelve a
            # `en_cola` con un `job_id` público nuevo: es un reintento.
            conn.execute(text(_SQL_INSERT), params)
            conn.execute(text(_SQL_REVIVIR), params)
            conn.commit()
            row = conn.execute(
                text(_SQL_SELECT + " AND id = :id LIMIT 1"),
                {"tenant": tenant, "id": id_dominio},
            ).fetchone()
        return _a_job(row)

    def get_job(self, tenant: str, job_id: str) -> VerificationJob | None:
        from sqlalchemy import text

        sql = _SQL_SELECT + " AND (job_id = :job_id OR id = :job_id) LIMIT 1"
        with self._motor().connect() as conn:
            row = conn.execute(text(sql), {"tenant": tenant, "job_id": job_id}).fetchone()
        return _a_job(row) if row is not None else None

    def update_job(
        self,
        tenant: str,
        job_id: str,
        estado: EstadoJob | str,
        resultado: dict[str, Any] | None = None,
        error_codigo: str | None = None,
        nodo: str | None = None,
    ) -> bool:
        from sqlalchemy import text

        valores: dict[str, Any] = {
            "estado": EstadoJob(estado).value,
            "actualizado_en": _ahora(),
        }
        if resultado is not None:
            valores["resultado_json"] = json.dumps(resultado, default=str)
        if error_codigo is not None:
            valores["error_codigo"] = error_codigo
        if nodo is not None:
            valores["nodo"] = nodo
        sets = ", ".join(f"{columna} = :{columna}" for columna in valores)
        sql = (
            f"UPDATE app_bank_verification_jobs SET {sets} "
            "WHERE tenant = :tenant AND (job_id = :job_id OR id = :job_id)"
        )
        with self._motor().connect() as conn:
            resultado_ejecucion = conn.execute(
                text(sql),
                {**valores, "tenant": tenant, "job_id": job_id},
            )
            conn.commit()
            impacted = resultado_ejecucion.rowcount
        return bool(impacted)

    def reclamar_ejecucion(
        self, tenant: str, job_id: str, *, nodo: str | None = None
    ) -> bool:
        """Claim atómico `en_cola → ejecutando` (`rowcount` decide el ganador)."""
        from sqlalchemy import text

        with self._motor().connect() as conn:
            resultado_ejecucion = conn.execute(
                text(_SQL_RECLAMAR),
                {"tenant": tenant, "job_id": job_id, "nodo": nodo, "now": _ahora()},
            )
            conn.commit()
            impacted = resultado_ejecucion.rowcount
        return bool(impacted)

    def expire_stale_jobs(self, now: datetime) -> int:
        from sqlalchemy import text

        with self._motor().connect() as conn:
            resultado_ejecucion = conn.execute(text(_SQL_EXPIRAR), {"now": now})
            conn.commit()
            expirados = resultado_ejecucion.rowcount
        return int(expirados or 0)


def _a_job(row: Any) -> VerificationJob:
    """Fila de MySQL → modelo de lectura (el importe vuelve a `Decimal`)."""
    datos = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    resultado = datos.get("resultado_json")
    if isinstance(resultado, str):
        resultado = json.loads(resultado) if resultado else None
    return VerificationJob(
        id=str(datos["id"]),
        job_id=str(datos["job_id"]),
        tenant=str(datos["tenant"]),
        factura_id=str(datos["factura_id"]),
        valor=Decimal(str(datos["valor"])),
        estado=EstadoJob(datos["estado"]),
        creado_en=datos["creado_en"],
        actualizado_en=datos["actualizado_en"],
        expira_en=datos["expira_en"],
        nodo=datos.get("nodo"),
        resultado=resultado,
        error_codigo=datos.get("error_codigo"),
    )


#: Store falso compartido: el job vive entre peticiones (el front sondea).
_STORE_FALSO: FakeVerificationJobStore | None = None


def get_verification_job_store() -> VerificationJobStore:
    """Real en prod/dev, doble falso bajo pruebas (`settings.env == 'test'`)."""
    global _STORE_FALSO
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealVerificationJobStore()
    if _STORE_FALSO is None:
        _STORE_FALSO = FakeVerificationJobStore()
    return _STORE_FALSO
