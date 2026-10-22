"""Router `/api/erp/bank/verificaciones` — slice S6 (job asíncrono).

El scrape del portal tarda 10–40 s: no cabe en un request HTTP (la nube es
serverless y sin navegador). Por eso la verificación es un **job**:

- `POST /api/erp/bank/verificaciones` → **202** con `{job_id, estado,
  expira_en}`. El job se crea y se despacha al worker **del nodo local** (el
  mismo proceso: no hay cola ni broker).
- `GET /api/erp/bank/verificaciones/{job_id}` → **200** con `{job_id, estado,
  resultado?, error?, expira_en}`. El front lo sondea cada ~2 s.

Errores (el cuerpo es `{"detail": {...}}`):

- **503 `scraper_no_habilitado`**: este nodo no raspa (la nube). El front
  deshabilita el botón y conserva el pegado manual del POS.
- **503 `tenant_no_servido`**: este nodo sirve a otro tenant. Los tenants
  nunca se cruzan.
- **404 `job_no_encontrado`**: el job no existe **o** es de otro tenant (la
  respuesta es la misma: no se revela la existencia de jobs ajenos).

Guardas: `POST` exige `require_erp_tenant` **+** `require_erp_collections_write`
(crear un job es una escritura de cobranzas); `GET` exige `require_erp_tenant`
y el módulo `erp-cash` (es el sondeo del POS).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from motoshop_api.auth.users import User
from motoshop_api.erp.bankreconciliation.jobs import (
    VerificationJob,
    VerificationJobStore,
    get_verification_job_store,
)
from motoshop_api.erp.bankreconciliation.node_config import (
    NodeConfig,
    NodeConfigError,
    load_node_config,
)
from motoshop_api.erp.bankreconciliation.schemas import BankMoney
from motoshop_api.erp.bankreconciliation.store import BankStore, get_bank_store
from motoshop_api.erp.bankreconciliation.worker import BankVerificationWorker
from motoshop_api.erp.guards import require_erp_collections_write, require_erp_tenant
from motoshop_api.tenants import Tenant

router = APIRouter(prefix="/erp", tags=["erp-cash"])

#: Este nodo no raspa (la nube): el front conserva el pegado manual.
CODIGO_SCRAPER_NO_HABILITADO = "scraper_no_habilitado"
#: Este nodo sirve a otro tenant: los tenants nunca se cruzan.
CODIGO_TENANT_NO_SERVIDO = "tenant_no_servido"
#: El job no existe (o es de otro tenant: la respuesta es la misma).
CODIGO_JOB_NO_ENCONTRADO = "job_no_encontrado"


class VerificacionCreate(BaseModel):
    """Qué se quiere verificar: la factura y el importe capturado."""

    model_config = ConfigDict(extra="forbid")

    factura_id: str = Field(min_length=1, max_length=64)
    valor: BankMoney


def get_node_config() -> NodeConfig | None:
    """Configuración del nodo (del entorno). `None` si no se puede leer.

    Un nodo con la configuración rota **no raspa**: mejor un 503 explícito
    que un 500 en el botón del POS.
    """
    try:
        return load_node_config()
    except NodeConfigError:
        return None


def get_despachador(
    jobs: VerificationJobStore = Depends(get_verification_job_store),
    store: BankStore = Depends(get_bank_store),
    config: NodeConfig | None = Depends(get_node_config),
) -> Callable[[VerificationJob], None]:
    """Despachador por defecto: el worker corre en un hilo del mismo proceso.

    El nodo local es el que raspa, y el scrape no cabe en el request (por eso
    la respuesta es 202). El hilo es *demonio*: si el proceso muere, el job
    caduca por TTL y el front lo ve como `expirado`.
    """

    def despachar(job: VerificationJob) -> None:
        if config is None:
            # Inaccesible: el handler ya rechazó a un nodo sin scraper.
            return
        worker = BankVerificationWorker(jobs=jobs, store=store, config=config)
        threading.Thread(
            target=worker.run_once,
            args=(job,),
            name="banco-verificacion",
            daemon=True,
        ).start()

    return despachar


def _exigir_nodo_capaz(config: NodeConfig | None, tenant: Tenant) -> None:
    """503 si este nodo no puede servir la verificación de este tenant."""
    if config is None or not config.scraper_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_codigo": CODIGO_SCRAPER_NO_HABILITADO,
                "message": (
                    "Este nodo no tiene el scraper del banco habilitado: "
                    "la verificación se hace desde el nodo local del tenant."
                ),
            },
        )
    if config.tenant != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_codigo": CODIGO_TENANT_NO_SERVIDO,
                "message": (
                    f"Este nodo sirve al tenant '{config.tenant}', no al "
                    f"'{tenant.id}': la verificación no se cruza entre tenants."
                ),
            },
        )


@router.post("/bank/verificaciones", status_code=202)
def crear_verificacion(
    body: VerificacionCreate,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_collections_write),
    jobs: VerificationJobStore = Depends(get_verification_job_store),
    config: NodeConfig | None = Depends(get_node_config),
    despachar: Callable[[VerificationJob], None] = Depends(get_despachador),
) -> dict:
    """Crea el job de verificación y lo despacha al worker del nodo.

    La idempotencia es del job: pedir dos veces la verificación de la misma
    factura por el mismo importe devuelve el **mismo** `job_id`.
    """
    _exigir_nodo_capaz(config, tenant)
    job = jobs.create_job(tenant.id, body.factura_id, body.valor)
    despachar(job)
    return {
        "job_id": job.job_id,
        "estado": job.estado.value,
        "expira_en": job.expira_en.isoformat(),
    }


@router.get("/bank/verificaciones/{job_id}")
def leer_verificacion(
    job_id: str,
    tenant: Tenant = Depends(require_erp_tenant),
    jobs: VerificationJobStore = Depends(get_verification_job_store),
) -> dict:
    """Estado del job: lo sondea el front hasta que llega a un estado final."""
    job = jobs.get_job(tenant.id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_codigo": CODIGO_JOB_NO_ENCONTRADO,
                "message": "No existe la verificación solicitada.",
            },
        )
    respuesta: dict = {
        "job_id": job.job_id,
        "estado": job.estado.value,
        "expira_en": job.expira_en.isoformat(),
    }
    if job.resultado is not None:
        respuesta["resultado"] = job.resultado
    if job.error_codigo is not None:
        respuesta["error"] = job.error_codigo
    return respuesta
