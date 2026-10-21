"""Router `/api/erp/invoices` (task 3.3) — POS sale endpoint.

Guard order (same as the other ERP routers): route matrix (mounted
dependency) → tenant enablement (WF-3) → ERP write role (WF-1) → business
validation inside the repo.

The endpoint owns NOTHING but the transport: the client never sends
``totdet`` nor the header totals, the server recomputes them (ADR-0008-07)
and rejects a mismatching client snapshot with 422 naming the field.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from motoshop_api.app_writes.repo import AuditRepo, FakeAuditRepo, get_audit_repo
from motoshop_api.auth.users import User
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import (
    PeriodLockedError,
    require_erp_tenant,
    require_erp_write,
)
from motoshop_api.erp.invoicing.repo import (
    FakeInvoicesRepo,
    RealInvoicesRepo,
    get_invoices_repo,
)
from motoshop_api.erp.invoicing.schemas import InvoiceCreate
from motoshop_api.erp.masters.validators import (
    InactiveMasterError,
    LegacyValidationError,
)
from motoshop_api.tenants import Tenant

logger = structlog.get_logger("motoshop.erp.invoicing")

router = APIRouter(prefix="/erp", tags=["erp-sales"])

HTTP_422 = status.HTTP_422_UNPROCESSABLE_CONTENT

#: F5-001 convention: UUID v4 for Idempotency-Key.
UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_idempotency_key(key: str) -> str:
    if not UUID_V4_RE.match(key):
        raise HTTPException(
            status_code=HTTP_422,
            detail="Idempotency-Key debe ser un UUID v4 válido",
        )
    return key


def _jsonify(value):
    """Recursively JSON-legible payload: Decimal → str (never float)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def _save_or_http_error(save):
    """Map the repo exceptions to the frozen HTTP contracts."""
    try:
        return save()
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except InactiveMasterError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except PeriodLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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


@router.post("/invoices", status_code=201)
def create_invoice(
    body: InvoiceCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_write),
    repo: FakeInvoicesRepo | RealInvoicesRepo = Depends(get_invoices_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Create a POS sale invoice (SI-*): server-side formuleo + journaled save."""
    _validate_idempotency_key(idempotency_key)
    request_id = x_request_id or str(uuid.uuid4())
    response = _save_or_http_error(
        lambda: repo.create(
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    )
    try:
        audit.log(
            user_id=user.username,
            user_role=user.role,
            action="create",
            target_type="factura_venta",
            target_id=str(response["numfven"]),
            request_id=request_id,
            payload={"before": None, "after": _jsonify(response)},
        )
    except Exception:  # pragma: no cover - audit must never break the sale
        logger.warning("erp.invoicing.audit_failed", request_id=request_id)
    return _jsonify(response)


@router.get("/invoices/{numfven}/receipt")
def get_invoice_receipt(
    numfven: int,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_write),
    repo: FakeInvoicesRepo | RealInvoicesRepo = Depends(get_invoices_repo),
) -> dict:
    """Assemble the printable receipt of a saved invoice (task 3.7).

    The receipt carries the DIAN QR slot: with the placeholder until the
    document is accepted (``estfele``), with the official catalogue URL
    (``https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=<CUFE>``)
    once the CUFE is known.
    """
    receipt = repo.receipt(numfven)
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La factura {numfven} no existe",
        )
    return _jsonify(receipt)
