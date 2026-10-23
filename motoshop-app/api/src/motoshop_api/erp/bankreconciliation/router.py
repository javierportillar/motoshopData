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

Además, `GET /api/erp/bank/candidates` (S7) devuelve los **candidatos por
importe** del tenant activo: es la lectura que la UI del POS usa para
prellenar la captura del pago. La regla de coincidencia vive en
`value_match.py` (función pura); aquí sólo se leen los movimientos del tenant
y se traduce el resultado a JSON.
"""

from __future__ import annotations

import datetime
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from motoshop_api.erp.bankreconciliation.schemas import BankMoney, BankMovementOut, EstadoMovimiento
from motoshop_api.erp.bankreconciliation.store import BankStore, get_bank_store
from motoshop_api.erp.bankreconciliation.value_match import (
    Candidato,
    desde_movimiento_persistido,
    match_by_value,
)
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
    """Qué se quiere verificar, en uno de los dos modos del contrato.

    - ``modo="factura"`` (por defecto si viene ``factura_id``): el operador
      está cobrando una factura concreta; el importe y el NIT salen de la
      factura del ERP. Es el comportamiento histórico.
    - ``modo="pago"`` (sin ``factura_id``): el POS todavía no tiene factura
      (el modal de cobro se abre ANTES de crear la venta). Manda el importe y,
      si los tiene, el NIT y el nombre del cliente.

    ``extra="forbid"``: un campo desconocido es un error del cliente, no algo
    que se ignore en silencio.
    """

    model_config = ConfigDict(extra="forbid")

    modo: Literal["factura", "pago"] | None = None
    factura_id: str | None = Field(default=None, min_length=1, max_length=64)
    valor: BankMoney
    nitter: str | None = Field(default=None, min_length=1, max_length=32)
    nombre_esperado: str | None = Field(default=None, min_length=2, max_length=120)

    @model_validator(mode="after")
    def _normalizar_modo(self) -> VerificacionCreate:
        """Deriva el modo y rechaza combinaciones incoherentes."""
        modo = self.modo or ("factura" if self.factura_id else "pago")
        if modo == "factura":
            if not self.factura_id:
                raise ValueError("modo 'factura' exige factura_id")
            if self.nitter or self.nombre_esperado:
                raise ValueError(
                    "modo 'factura' toma el NIT de la factura: no envíes "
                    "nitter ni nombre_esperado"
                )
        else:
            if self.factura_id:
                raise ValueError("modo 'pago' no admite factura_id")
        self.modo = modo
        return self

    @property
    def solicitud(self) -> dict[str, str] | None:
        """Lo que el worker necesita para armar el resultado (modo pago)."""
        if self.modo != "pago":
            return None
        datos = {"modo": "pago"}
        if self.nitter:
            datos["nitter"] = self.nitter.strip()
        if self.nombre_esperado:
            datos["nombre_esperado"] = self.nombre_esperado.strip()
        return datos


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

    La idempotencia protege la verificación **en curso**: pedir dos veces la
    verificación de la misma factura por el mismo importe, mientras corre,
    devuelve el **mismo** `job_id`. Si el intento anterior terminó (`fallido`,
    `expirado`, `resuelto`…), el pedido es un **reintento**: se reusa la fila
    del job pero con un `job_id` público nuevo y el error viejo limpio, así el
    operador puede volver a probar cuando el portal falló o el OTP caducó.
    """
    _exigir_nodo_capaz(config, tenant)
    # En modo "pago" no hay factura: la clave de idempotencia queda en el
    # importe (`tenant::valor`), que es exactamente lo que distingue un doble
    # clic de una verificación nueva. El NIT y el nombre viajan en `solicitud`.
    job = jobs.create_job(
        tenant.id,
        body.factura_id or "",
        body.valor,
        solicitud=body.solicitud,
    )
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


@router.get("/bank/candidates")
def listar_candidatos(
    valor: Annotated[Decimal, Query(max_digits=18, decimal_places=2)],
    desde: datetime.date | None = Query(default=None),
    hasta: datetime.date | None = Query(default=None),
    tenant: Tenant = Depends(require_erp_tenant),
    store: BankStore = Depends(get_bank_store),
) -> dict:
    """Candidatos con el mismo importe dentro de la ventana de consulta.

    Es una **lectura**: sólo se ven los movimientos del tenant activo y la
    regla de coincidencia es la de `value_match.match_by_value` (la misma que
    usa el worker del nodo).

    - `valor` es obligatorio y debe ser un decimal válido de dos decimales
      (si no, la API responde **422**);
    - `desde`/`hasta` acotan la ventana; por defecto es **el día en curso**;
    - sin coincidencia la respuesta es **200** con `candidatos` vacío: no es
      un error;
    - `ambiguo` es `True` cuando hay dos o más candidatos: se listan todos y
      **no** se elige ninguno (la elección es del operador).

    Respuesta **200**:

        {
          "ambiguo": false,
          "ventana": {"desde": "2026-10-21", "hasta": "2026-10-21"},
          "candidatos": [
            {"id": "<uuid5>", "valor": "458200.00", "pagadorNombre": "...",
             "referencia": "0092055984", "fecha": "2026-10-21"}
          ],
          "ultimaIngestaAt": "2026-10-21T12:00:00"
        }

    El importe viaja como **texto** (`"458200.00"`): nunca como `float`.
    """
    hoy = datetime.date.today()
    inicio = desde or hoy
    fin = hasta or hoy
    if inicio > fin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La ventana de consulta está invertida: 'desde' es posterior a 'hasta'.",
        )

    movimientos = store.list_movimientos(tenant.id)
    coincidencia = match_by_value(
        valor,
        [desde_movimiento_persistido(movimiento) for movimiento in movimientos],
        (inicio, fin),
    )
    return {
        "ambiguo": coincidencia.ambiguo,
        "ventana": {"desde": inicio.isoformat(), "hasta": fin.isoformat()},
        "candidatos": [_candidato_json(candidato) for candidato in coincidencia.candidatos],
        "ultimaIngestaAt": _ultima_ingesta(movimientos),
    }


def _candidato_json(candidato: Candidato) -> dict[str, str]:
    """Candidato → JSON de la API (el importe viaja como texto: nunca `float`)."""
    return {
        "id": candidato.id,
        "valor": str(candidato.valor),
        "pagadorNombre": candidato.pagador_nombre,
        "referencia": candidato.referencia,
        "fecha": candidato.fecha.isoformat(),
    }


def _ultima_ingesta(movimientos: Sequence[BankMovementOut]) -> str | None:
    """Instante de la última ingesta del tenant (`None` si nunca ingirió)."""
    instantes = [movimiento.scraped_at for movimiento in movimientos if movimiento.scraped_at]
    if not instantes:
        return None
    return max(instantes).isoformat()


# ── S9: movimientos, sync-status y aplicación ─────────────────────────────

from motoshop_api.erp.bankreconciliation.repo import (  # noqa: E402
    BankReconciliationRepo,
    CodpagNoConfirmadoError,
    FacturaNoEncontradaError,
    MovimientoNoEncontradoError,
)
from motoshop_api.erp.cash.repo import (  # noqa: E402
    get_consignment_repo,
    get_receipts_repo,
)
from motoshop_api.erp.guards import PeriodLockedError  # noqa: E402


class FacturasNoConfiguradasError(Exception):
    """El nodo no tiene cableado el proveedor de facturas abiertas.

    Fail-closed a propósito: devolver una lista vacía haría que todo
    movimiento sin match terminara como consignación, sin que nadie lo note.
    """

    codigo = "facturas_no_configuradas"


def get_facturas_provider() -> Callable[[str, str], Sequence[object]]:
    """Facturas abiertas del tenant.

    Todavía no hay proveedor real cableado (depende del esquema de cartera del
    tenant). Hasta entonces la conciliación responde 503 en vez de adivinar.
    """
    raise FacturasNoConfiguradasError("No hay proveedor de facturas abiertas cableado")


def get_reconciliation_repo(
    store: BankStore = Depends(get_bank_store),
    facturas: Callable[[str, str], Sequence[object]] = Depends(get_facturas_provider),
    receipts: object = Depends(get_receipts_repo),
    consignments: object = Depends(get_consignment_repo),
) -> BankReconciliationRepo:
    """Repo de conciliación con los caminos de caja reales.

    El ``codpag`` es **fail-closed** (Q5): sin la variable de entorno
    confirmada, ``apply`` no postea nada. Recibo por transferencia y
    consignación bancaria usan códigos distintos y no se cruzan.
    """
    return BankReconciliationRepo(
        movements=store,
        facturas=facturas,  # type: ignore[arg-type]
        receipts=receipts,  # type: ignore[arg-type]
        consignments=consignments,  # type: ignore[arg-type]
        codpag_transferencia=_codpags("BANK_CODPAG_TRANSFERENCIA_"),
        codpag_consignacion=_codpags("BANK_CODPAG_CONSIGNACION_"),
        codpag_comun=_codpag_comun("BANK_CODPAG_TRANSFERENCIA"),
        codpag_comun_consignacion=_codpag_comun("BANK_CODPAG_CONSIGNACION"),
    )


def _codpags(prefijo: str) -> dict[str, str]:
    """Códigos por tenant declarados en el entorno para ese prefijo."""
    return codpags_por_tenant(prefijo=prefijo)[0]


def _codpag_comun(variable: str) -> str | None:
    """Código global de compatibilidad (una sola empresa por proceso)."""
    return codpags_por_tenant(variable=variable)[1]


def codpags_por_tenant(
    env: Mapping[str, str] | None = None,
    *,
    prefijo: str = "BANK_CODPAG_TRANSFERENCIA_",
    variable: str = "BANK_CODPAG_TRANSFERENCIA",
) -> tuple[dict[str, str], str | None]:
    """`codpag` **por tenant** para una forma de pago, desde el entorno.

    Una sola API sirve a varias empresas y cada una tiene su catálogo de
    formas de pago: el código de MotoShop no necesariamente existe en
    MasVital. Se resuelven **dos** códigos distintos —recibo por
    transferencia y consignación bancaria— porque también son filas distintas
    del catálogo legacy. Se acepta el específico
    (`BANK_CODPAG_TRANSFERENCIA_<TENANT>` / `BANK_CODPAG_CONSIGNACION_<TENANT>`)
    y, como compatibilidad, uno global.

    Sin código para un tenant el resultado es fail-closed: `apply` responde
    **409** `codpag_no_confirmado` en vez de adivinar.
    """
    valores = os.environ if env is None else env
    comun = (valores.get(variable) or "").strip() or None
    por_tenant: dict[str, str] = {}
    for clave, valor in valores.items():
        if not clave.startswith(prefijo):
            continue
        tenant = clave[len(prefijo) :].strip().lower()
        codigo = (valor or "").strip()
        if tenant and codigo:
            por_tenant[tenant] = codigo
    return por_tenant, comun


def _movimiento_json(movimiento: BankMovementOut) -> dict[str, object]:
    return {
        "id": movimiento.id,
        "fecha": movimiento.fecha_movimiento.isoformat(),
        "valor": str(movimiento.valor),
        "descripcion": movimiento.descripcion,
        "referencia": movimiento.referencia,
        "pagadorNombre": movimiento.pagador_nombre,
        "estado": movimiento.estado.value,
        "reciboNumero": movimiento.recibo_numero,
        "confianza": movimiento.confianza,
        "razones": movimiento.razones,
    }


@router.get("/bank/movements")
def listar_movimientos(
    estado: Annotated[EstadoMovimiento | None, Query()] = None,
    desde: datetime.date | None = Query(default=None),
    hasta: datetime.date | None = Query(default=None),
    tenant: Tenant = Depends(require_erp_tenant),
    store: BankStore = Depends(get_bank_store),
) -> dict:
    """Movimientos del tenant activo, filtrables por estado y rango de fechas.

    Sólo se ven los movimientos propios: el tenant sale del request, nunca de
    un parámetro.
    """
    movimientos = store.list_movimientos(tenant.id, estado=estado, desde=desde, hasta=hasta)
    return {"movimientos": [_movimiento_json(m) for m in movimientos]}


@router.get("/bank/sync-status")
def sync_status(
    tenant: Tenant = Depends(require_erp_tenant),
    store: BankStore = Depends(get_bank_store),
    config: NodeConfig | None = Depends(get_node_config),
) -> dict:
    """Última ingesta, nodo y ventana de consulta del tenant activo."""
    movimientos = store.list_movimientos(tenant.id)
    return {
        "ultimaIngestaAt": _ultima_ingesta(movimientos),
        "nodo": (config.account_label or config.tenant) if config is not None else None,
        "scraperHabilitado": bool(config and config.scraper_enabled),
        "ventana": (
            {
                "desde": config.window_start.isoformat(),
                "hasta": config.window_end.isoformat(),
            }
            if config is not None
            else None
        ),
    }


@router.post("/bank/reconciliation/{movimiento_id}/apply")
def aplicar_movimiento(
    movimiento_id: str,
    factura_id: Annotated[str | None, Query()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_collections_write),
    repo: BankReconciliationRepo = Depends(get_reconciliation_repo),
) -> dict:
    """Confirma la aplicación de un movimiento (confirmación humana).

    ``factura_id`` presente ⇒ recibo S01; ausente ⇒ consignación bancaria.
    Con el mismo ``Idempotency-Key`` (o el mismo movimiento) no se duplica el
    documento. Periodo cerrado ⇒ **409** y el movimiento queda pendiente.
    """
    try:
        return repo.apply(
            tenant.id,
            tenant.erp.empresa,
            movimiento_id,
            factura_id,
            idempotency_key=idempotency_key,
        )
    except MovimientoNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_codigo": exc.codigo, "message": "El movimiento no existe."},
        ) from exc
    except FacturaNoEncontradaError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_codigo": exc.codigo, "message": "La factura no está abierta."},
        ) from exc
    except CodpagNoConfirmadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_codigo": exc.codigo, "message": str(exc)},
        ) from exc
    except PeriodLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_codigo": "periodo_cerrado",
                "message": "El periodo está cerrado; el movimiento queda pendiente.",
            },
        ) from exc
    except FacturasNoConfiguradasError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_codigo": exc.codigo, "message": str(exc)},
        ) from exc
