"""POS sale adapter: the web POS screen -> the transactional ERP engine.

The POS screen (``frontfambus/app/(authenticated)/pos``) posts its own
payload to ``POST /api/pos/sales``. That endpoint did not exist on the
backend, so every sale was silently queued as "offline" and never reached
the legacy ledger.

This module is the bridge: it maps the POS payload onto the SAME contract
the POS screen already uses (legacy field names: ``candet``, ``valuni``,
``dctpes``, ``ivapes``, ``ipopes``) and delegates to the invoicing engine,
so the sale lands in ``sgHermes`` exactly like the desktop does:

    facventas (header) + detfventas (lines) + detapago (payments)
    + contadores (numbering, LOCK TABLES) + app_doc_journal (write-ahead)

The analytics side needs no change: the ETL reads the legacy tables, so
the dashboards pick the sale up on the next run.

Payment mapping (legacy ``formapago``):

    EFECTIVO     -> F01   (caja, tippag=1)
    DATAFONO     -> F03   (tarjeta debito, tippag=2)
    TRANSFERENCIA-> F07   (transferencia banco, tippag=2)
    CREDITO      -> F10   (cuentas x cobrar, tippag=4)
"""

from __future__ import annotations

import datetime
import logging
import re
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import PeriodLockedError, require_erp_tenant
from motoshop_api.erp.invoicing.repo import (
    FakeInvoicesRepo,
    RealInvoicesRepo,
    get_invoices_repo,
)
from motoshop_api.erp.invoicing.schemas import (
    InvoiceCreate,
    InvoiceLineIn,
    InvoicePaymentIn,
)
from motoshop_api.erp.masters.validators import (
    InactiveMasterError,
    LegacyValidationError,
)
from motoshop_api.erp.models import ProductSearchResult
from motoshop_api.erp.repo import ERPRepository, get_erp_repo
from motoshop_api.tenants import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pos", tags=["erp-pos-legacy"])

HTTP_422 = status.HTTP_422_UNPROCESSABLE_CONTENT
HTTP_409 = status.HTTP_409_CONFLICT

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

#: The POS payment method -> the legacy ``formapago.codpag``.
PAYMENT_FORM_BY_METHOD = {
    "EFECTIVO": "F01",
    "EFECTIVO ": "F01",
    "CASH": "F01",
    "DATAFONO": "F03",
    "TARJETA": "F03",
    "CARD": "F03",
    "TRANSFERENCIA": "F07",
    "TRANSFER": "F07",
    "CREDITO": "F10",
    "CREDIT": "F10",
}

#: The consumer final NIT used when the POS does not capture a client.
DEFAULT_CLIENT_NIT = "222222222222"


class PosSaleItem(BaseModel):
    """One line of the POS cart (the legacy field names)."""

    model_config = ConfigDict(extra="ignore")

    product: dict[str, Any] = Field(default_factory=dict)
    candet: Decimal = Field(default=Decimal("1"), gt=0)
    valuni: Decimal = Field(default=Decimal("0"), ge=0)
    dctpes: Decimal = Field(default=Decimal("0"), ge=0)
    ivapes: Decimal = Field(default=Decimal("0"), ge=0)
    ipopes: Decimal = Field(default=Decimal("0"), ge=0)
    dctpor: Decimal = Field(default=Decimal("0"), ge=0)
    ivapor: Decimal = Field(default=Decimal("0"), ge=0)
    ipopor: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class PosSalePayment(BaseModel):
    """One payment of the POS sale."""

    model_config = ConfigDict(extra="ignore")

    method: str = "EFECTIVO"
    amount: Decimal = Field(default=Decimal("0"))
    reference: str | None = None
    bank: str | None = None


class PosSaleCustomer(BaseModel):
    """The POS customer (``customer.nit`` is the legacy ``nitter``)."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    nit: str | None = None
    name: str | None = None


class PosSaleCreate(BaseModel):
    """The payload the POS screen posts to ``/api/pos/sales``."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    documentType: str | None = None
    documentNumber: str | None = None
    customer: PosSaleCustomer = Field(default_factory=PosSaleCustomer)
    items: list[PosSaleItem] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    payments: list[PosSalePayment] = Field(default_factory=list)
    sessionId: str | None = None
    cashier: str | None = None
    notes: str | None = None
    tenant: str | None = None


def _sku_of(item: PosSaleItem) -> str:
    product = item.product or {}
    for key in ("sku", "codprod", "product_id", "id"):
        value = product.get(key)
        if value:
            return str(value)
    return str(item.product.get("sku") or "")


def _name_of(item: PosSaleItem) -> str:
    product = item.product or {}
    return str(product.get("name") or item.notes or "")


def _unit_of(item: PosSaleItem) -> str:
    product = item.product or {}
    unit = str(product.get("unit") or "UND").strip()
    return unit[:3] or "UND"


def _form_of(method: str) -> str:
    key = str(method or "EFECTIVO").strip().upper()
    return PAYMENT_FORM_BY_METHOD.get(key, "F01")


def _to_invoice(
    sale: PosSaleCreate, *, nitvend: str, codcaj: str
) -> InvoiceCreate:
    """Map the POS payload onto the invoice contract."""
    lines = [
        InvoiceLineIn(
            codprod=_sku_of(item),
            nomdet=_name_of(item),
            candet=item.candet,
            valuni=item.valuni,
            dctpes=item.dctpes,
            ivapes=item.ivapes,
            ipopes=item.ipopes,
            dctpor=item.dctpor,
            ivapor=item.ivapor,
            ipopor=item.ipopor,
            codmed=_unit_of(item),
        )
        for item in sale.items
    ]
    payments = [
        InvoicePaymentIn(
            codpag=_form_of(payment.method),
            amount=payment.amount,
            referencia=payment.reference,
        )
        for payment in sale.payments
        if payment.amount > 0
    ]
    client_nit = (sale.customer.nit or sale.customer.id or "").strip()
    if client_nit.upper().startswith("CF-"):
        client_nit = client_nit[3:]
    return InvoiceCreate(
        nitter=client_nit or DEFAULT_CLIENT_NIT,
        nomclien=(sale.customer.name or "").strip()[:120] or None,
        nitvend=nitvend,
        codcaj=codcaj,
        obsfven=sale.notes,
        lines=lines,
        payments=payments,
        client_totals=None,
    )


def _resolve_seller(repo: Any) -> str:
    """The seller NIT: the company's own NIT (``terceros.emppro = 'SI'``)."""
    store = getattr(repo, "store", None)
    resolver = getattr(store, "company_nit", None)
    if callable(resolver):
        nit = resolver()
        if nit:
            return str(nit)
    return DEFAULT_CLIENT_NIT


@router.post("/sales", status_code=201)
def create_pos_sale(
    sale: PosSaleCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
    repo: FakeInvoicesRepo | RealInvoicesRepo = Depends(get_invoices_repo),
) -> dict:
    """Create a POS sale in the legacy ledger (the transactional engine).

    The POS screen sends its own idempotency id in ``X-Idempotency-Key``;
    both header names are accepted.
    """
    key = idempotency_key or x_idempotency_key or sale.id
    if key and not UUID_V4_RE.match(key):
        # The POS ids are UUIDs, but the screen may use another shape: the
        # engine only needs a stable, non-empty key for the replay.
        key = key or None
    if not sale.items:
        raise HTTPException(
            status_code=HTTP_422,
            detail={"message": "La venta no tiene líneas", "fields": {"items": "vacío"}},
        )
    invoice = _to_invoice(
        sale,
        nitvend=_resolve_seller(repo),
        codcaj=str(getattr(tenant.erp, "caja", "01") or "01"),
    )
    try:
        response = repo.create(
            invoice,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=sale.cashier or user.username,
            request_id=sale.id or "pos",
            idempotency_key=key,
        )
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except InactiveMasterError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except PeriodLockedError as exc:
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except ErpSaveFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": str(exc),
                "code": "erp_save_failed",
                "docnum": exc.docnum,
                "retryable": exc.retryable,
            },
        ) from exc
    return {
        "success": True,
        "numfven": response["numfven"],
        "prefven": response["prefven"],
        "totals": response["totals"],
        "documentNumber": f"{response['prefven']}{response['numfven']}",
    }


@router.get("/sales")
def list_pos_sales(
    fecha: datetime.date = Query(...),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
) -> dict:
    """Ventas creadas **por la web/POS** en ese día, con su detalle.

    Se identifican por el journal de escritura (`app_doc_journal`): el motor de
    facturación anota cada documento que crea, y SgHermes no escribe ahí. Es la
    única forma de distinguir lo que se vendió por el POS de lo que se facturó a
    mano en el escritorio.

    Los importes viajan como **texto** (nunca `float`), igual que el resto de la
    API del ERP.
    """
    from sqlalchemy import text

    from motoshop_api.db.engine import get_engine

    sql_docs = text(
        """
        SELECT f.numfven, f.codclas, f.prefven, f.fecfven, f.nitter, f.clifven,
               f.nitvend, f.codcaj, f.codpag, f.totfven, f.estfven,
               j.actor, j.status, j.idempotency_key
        FROM app_doc_journal j
        JOIN facventas f
          ON f.codclas = j.codclas AND f.numfven = CAST(j.docnum AS CHAR)
        WHERE j.tenant = :tenant
          AND j.status IN ('COMMITTED', 'ANNULLED')
          AND DATE(f.fecfven) = :fecha
        ORDER BY f.fecfven DESC, f.numfven DESC
        LIMIT :limite
        """
    )
    with get_engine().connect() as conn:
        docs = [dict(r._mapping) for r in conn.execute(sql_docs, {
            "tenant": tenant.id, "fecha": fecha.isoformat(), "limite": limit,
        })]

    if not docs:
        return {"fecha": fecha.isoformat(), "ventas": []}

    numeros = [str(d["numfven"]) for d in docs]
    classes = sorted({d["codclas"] for d in docs})
    sql_lineas = text(
        """
        SELECT numfven, codclas, numite, codprod, nomdet, candet, valuni, totdet,
               codbod, codmed
        FROM detfventas
        WHERE codclas IN :clases AND numfven IN :numeros
        ORDER BY numfven, numite
        """
    ).bindparams(bindparam("clases", expanding=True), bindparam("numeros", expanding=True))
    sql_pagos = text(
        """
        SELECT numnum, codclas, codpag, valpag, estado
        FROM detapago
        WHERE codclas IN :clases AND numnum IN :numeros
        """
    ).bindparams(bindparam("clases", expanding=True), bindparam("numeros", expanding=True))

    with get_engine().connect() as conn:
        lineas = [
            dict(r._mapping)
            for r in conn.execute(sql_lineas, {"clases": classes, "numeros": numeros})
        ]
        pagos = [
            dict(r._mapping)
            for r in conn.execute(sql_pagos, {"clases": classes, "numeros": numeros})
        ]

    por_doc_lineas: dict[str, list[dict]] = {}
    for fila in lineas:
        por_doc_lineas.setdefault(str(fila["numfven"]), []).append({
            "numite": fila["numite"],
            "codprod": fila["codprod"],
            "nomdet": fila["nomdet"],
            "candet": str(fila["candet"]),
            "valuni": str(fila["valuni"]),
            "totdet": str(fila["totdet"]),
            "codbod": fila["codbod"],
            "codmed": fila["codmed"],
        })
    por_doc_pagos: dict[str, list[dict]] = {}
    for fila in pagos:
        por_doc_pagos.setdefault(str(fila["numnum"]), []).append({
            "codpag": fila["codpag"],
            "valpag": str(fila["valpag"]),
            "estado": fila["estado"],
        })

    ventas = []
    for doc in docs:
        numero = str(doc["numfven"])
        fec = doc["fecfven"]
        ventas.append({
            "numfven": numero,
            "codclase": doc["codclas"],
            "prefijo": doc["prefven"],
            "documento": f"{doc['prefven']}{numero}",
            "fecha": fec.date().isoformat() if hasattr(fec, "date") else str(fec)[:10],
            "hora": fec.strftime("%H:%M") if hasattr(fec, "strftime") else "",
            "cliente": doc["clifven"],
            "nitter": doc["nitter"],
            "vendedor": doc["nitvend"],
            "caja": doc["codcaj"],
            "formapago": doc["codpag"],
            "total": str(doc["totfven"]),
            "estado": doc["estfven"],
            "cajero": doc["actor"],
            "anulada": str(doc["status"]) == "ANNULLED",
            "lineas": por_doc_lineas.get(numero, []),
            "pagos": por_doc_pagos.get(numero, []),
        })
    return {"fecha": fecha.isoformat(), "ventas": ventas}


@router.get("/products", response_model=list[ProductSearchResult])
async def list_pos_products(
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
    repo: ERPRepository = Depends(get_erp_repo),
) -> list[ProductSearchResult]:
    """Search products for the Web POS counter in active tenant."""
    return repo.search_products(tenant_id=tenant.id, q=q, limit=limit)

