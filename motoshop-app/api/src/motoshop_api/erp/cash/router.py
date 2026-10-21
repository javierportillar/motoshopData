"""Router `/api/erp/{receipts,cash/*,bank/consignments}` — slice 4.

Guard order (same contract as the masters router):
route matrix (WF-2) → tenant enablement (WF-3) → collections role (WF-1s3:
admin/gerente only — a matrix grant can never widen the population) →
business validation inside the repo.

Error contract:
- ``LegacyValidationError`` → 422 aggregate body (``fields`` + ``message``)
- ``AnnulledDocumentError`` / ``PeriodLockedError`` → 409 with a reason code
- ``InactiveMasterError`` → the FROZEN 422 master-state shape (verbatim)
- ``ErpSaveFailed`` → retryable 503 (the handler is mounted in main.py)

Every write is journaled PENDING → COMMITTED and answers the same
``Idempotency-Key`` with the stored response (WF-8s1).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from motoshop_api.app_writes.repo import AuditRepo, FakeAuditRepo, get_audit_repo
from motoshop_api.auth.users import User
from motoshop_api.erp.cash.repo import (
    AnnulledDocumentError,
    FakeCashMovementsRepo,
    FakeReceiptsRepo,
    RealCashMovementsRepo,
    RealReceiptsRepo,
    get_cash_movements_repo,
    get_receipts_repo,
)
from motoshop_api.erp.cash.schemas import CashMovementCreate, EgressCreate, ReceiptCreate
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import (
    PeriodLockedError,
    require_erp_collections_write,
    require_erp_tenant,
)
from motoshop_api.erp.masters.validators import InactiveMasterError, LegacyValidationError
from motoshop_api.tenants import Tenant

logger = structlog.get_logger("motoshop.erp.cash")

router = APIRouter(prefix="/erp", tags=["erp-cash"])

HTTP_422 = status.HTTP_422_UNPROCESSABLE_CONTENT
HTTP_503 = status.HTTP_503_SERVICE_UNAVAILABLE

# F5-001 convention: UUID v4 for Idempotency-Key (same contract as app_writes).
UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_idempotency_key(key: str) -> str:
    if not UUID_V4_RE.match(key):
        raise HTTPException(
            status_code=HTTP_422, detail="Idempotency-Key debe ser un UUID v4 válido"
        )
    return key


def _jsonify(value):
    """Recursively JSON-legible payload: Decimal → str (never float, ADR-0008-07)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def _log_audit(
    audit: AuditRepo | FakeAuditRepo,
    user: User,
    action: str,
    target_type: str,
    target_id: str,
    request_id: str,
    payload: dict | None = None,
    status_value: str = "success",
    error_msg: str | None = None,
) -> None:
    """Append the app_audit_log row; audit failures never break the write."""
    try:
        audit.log(
            user_id=user.username,
            user_role=user.role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            payload=_jsonify(payload),
            status=status_value,
            error_msg=error_msg,
        )
    except Exception:
        logger.warning("audit log failed (best-effort)", exc_info=True)


def _conflict(exc: Exception) -> HTTPException:
    """409 for the cash-specific conflicts (annulled target / locked period)."""
    detail = exc.detail() if hasattr(exc, "detail") else {"message": str(exc)}
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_jsonify(detail))


def _save_or_http_error(save):
    """Map the repo error contract onto the HTTP contract."""
    try:
        return save()
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except InactiveMasterError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except (AnnulledDocumentError, PeriodLockedError) as exc:
        raise _conflict(exc) from exc
    except ErpSaveFailed as exc:
        raise HTTPException(
            status_code=HTTP_503, detail=str(exc), headers={"Retry-After": "5"}
        ) from exc


@router.post("/receipts", status_code=201)
def create_receipt(
    body: ReceiptCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_collections_write),
    repo: FakeReceiptsRepo | RealReceiptsRepo = Depends(get_receipts_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Post a cash receipt (S01) against an open CxC balance (CC-1/CC-2/CC-6)."""
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
    _log_audit(
        audit,
        user,
        "create",
        "recibo_caja",
        str(response["numero"]),
        request_id,
        payload={"before": None, "after": response},
    )
    return response


@router.post("/cash/movements", status_code=201)
def create_cash_movement(
    body: CashMovementCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_collections_write),
    repo: FakeCashMovementsRepo | RealCashMovementsRepo = Depends(
        get_cash_movements_repo
    ),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Cash movement in/out through a ``concepingegr`` concept (CC-3/CC-6)."""
    _validate_idempotency_key(idempotency_key)
    request_id = x_request_id or str(uuid.uuid4())
    response = _save_or_http_error(
        lambda: repo.create_movement(
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    )
    _log_audit(
        audit,
        user,
        "create",
        "comprobante_caja",
        str(response["numero"]),
        request_id,
        payload={"before": None, "after": response},
    )
    return response


@router.post("/cash/egresos", status_code=201)
def create_egress(
    body: EgressCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_collections_write),
    repo: FakeCashMovementsRepo | RealCashMovementsRepo = Depends(
        get_cash_movements_repo
    ),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Post a comprobante de egreso (S02) with a server-side total (CC-3)."""
    _validate_idempotency_key(idempotency_key)
    request_id = x_request_id or str(uuid.uuid4())
    response = _save_or_http_error(
        lambda: repo.create_egress(
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    )
    _log_audit(
        audit,
        user,
        "create",
        "comprobante_egreso",
        str(response["numero"]),
        request_id,
        payload={"before": None, "after": response},
    )
    return response
