"""Router `/api/erp/{terceros,productos}` (tasks 2.2–2.4) — masters writes.

Guard order per spec: route matrix (WF-2, mounted dependency) → tenant
enablement (WF-3) → masters write role (MW-5) → business validation inside
the repo. Masters writes journal PENDING → COMMITTED through the slice-1
φ-sequence (doc_types "tercero"/"producto") and append one `app_audit_log`
row per successful create/edit with before/after snapshots (MW-4 —
`motanudoc` is NEVER touched: its contract is reserved for annulment).
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from motoshop_api.app_writes.repo import AuditRepo, FakeAuditRepo, get_audit_repo
from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import require_erp_masters_write, require_erp_tenant
from motoshop_api.erp.masters.repo import (
    FakeProductosRepo,
    FakeTercerosRepo,
    RealProductosRepo,
    RealTercerosRepo,
    get_productos_repo,
    get_terceros_repo,
)
from motoshop_api.erp.masters.schemas import (
    ProductCreate,
    ProductUpdate,
    TerceroCreate,
    TerceroUpdate,
)
from motoshop_api.erp.masters.validators import (
    DuplicateMasterError,
    LegacyValidationError,
)
from motoshop_api.tenants import Tenant

logger = structlog.get_logger("motoshop.erp.masters")

router = APIRouter(prefix="/erp", tags=["erp-masters"])

HTTP_422 = status.HTTP_422_UNPROCESSABLE_CONTENT

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


@router.post("/terceros", status_code=201)
def create_tercero(
    body: TerceroCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_masters_write),
    repo: FakeTercerosRepo | RealTercerosRepo = Depends(get_terceros_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Create a third party (+ `tercecorreo` rows) inside one journaled UoW."""
    _validate_idempotency_key(idempotency_key)
    request_id = x_request_id or str(uuid.uuid4())
    try:
        response = repo.create(
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except DuplicateMasterError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=exc.detail()
        ) from exc
    except ErpSaveFailed:
        raise  # retryable 503 contract — the handler is mounted via main.py
    _log_audit(
        audit, user, "create", "tercero", response["nitter"], request_id,
        payload={"before": None, "after": response},
    )
    return response


@router.patch("/terceros/{id}")
def update_tercero(
    id: str,
    body: TerceroUpdate,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_masters_write),
    repo: FakeTercerosRepo | RealTercerosRepo = Depends(get_terceros_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Edit a third party; identity fields are immutable (MW-1 parity)."""
    request_id = x_request_id or str(uuid.uuid4())
    before = repo.get(id)
    if before is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tercero '{id}' no encontrado",
        )
    try:
        response = repo.update(
            id,
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
        )
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except DuplicateMasterError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=exc.detail()
        ) from exc
    _log_audit(
        audit, user, "update", "tercero", id, request_id,
        payload={"before": before, "after": response},
    )
    return response


@router.get("/terceros")
def list_terceros(
    search: str = "",
    limit: int = 50,
    offset: int = 0,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
    repo: FakeTercerosRepo | RealTercerosRepo = Depends(get_terceros_repo),
) -> list[dict]:
    """List third parties (MW-5: reads are open to all tenant roles)."""
    return repo.list(search=search, limit=limit, offset=offset)


@router.get("/terceros/{id}")
def get_tercero(
    id: str,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
    repo: FakeTercerosRepo | RealTercerosRepo = Depends(get_terceros_repo),
) -> dict:
    """Read one third party with its emails."""
    row = repo.get(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tercero '{id}' no encontrado",
        )
    return row


# ════════════════════════ Productos (tasks 2.3 / 2.4) ═══════════════════


@router.post("/productos", status_code=201)
def create_producto(
    body: ProductCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_masters_write),
    repo: FakeProductosRepo | RealProductosRepo = Depends(get_productos_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Create a product with units, barcodes and list prices in one UoW."""
    _validate_idempotency_key(idempotency_key)
    request_id = x_request_id or str(uuid.uuid4())
    try:
        response = repo.create(
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except DuplicateMasterError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=exc.detail()
        ) from exc
    except ErpSaveFailed:
        raise  # retryable 503 contract — the handler is mounted via main.py
    _log_audit(
        audit, user, "create", "producto", response["codprod"], request_id,
        payload={"before": None, "after": response},
    )
    return response


@router.patch("/productos/{id}")
def update_producto(
    id: str,
    body: ProductUpdate,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_masters_write),
    repo: FakeProductosRepo | RealProductosRepo = Depends(get_productos_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Edit a product; price edits recompute the IVA pair + `porutil` (MW-2)."""
    request_id = x_request_id or str(uuid.uuid4())
    before = repo.get(id)
    if before is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto '{id}' no encontrado",
        )
    try:
        response = repo.update(
            id,
            body,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id=request_id,
        )
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except DuplicateMasterError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=exc.detail()
        ) from exc
    except ErpSaveFailed:
        raise  # retryable 503 contract — the handler is mounted via main.py
    _log_audit(
        audit, user, "update", "producto", id, request_id,
        payload={"before": before, "after": response},
    )
    return response


@router.get("/productos")
def list_productos(
    search: str = "",
    limit: int = 50,
    offset: int = 0,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
    repo: FakeProductosRepo | RealProductosRepo = Depends(get_productos_repo),
) -> list[dict]:
    """List products (MW-5: reads are open to all tenant roles)."""
    return repo.list(search=search, limit=limit, offset=offset)


@router.get("/productos/{id}")
def get_producto(
    id: str,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(get_current_user),
    repo: FakeProductosRepo | RealProductosRepo = Depends(get_productos_repo),
) -> dict:
    """Read one product with its units, barcodes and price levels."""
    row = repo.get(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto '{id}' no encontrado",
        )
    return row
