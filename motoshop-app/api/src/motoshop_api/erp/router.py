"""FastAPI Router for POS & ERP operations under /api/erp."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.erp.models import (
    CashMovementIn,
    CashMovementOut,
    CashSessionCloseIn,
    CashSessionOpenIn,
    CashSessionOut,
    ProductSearchResult,
    SaleCreateIn,
    SaleOut,
    SaleVoidIn,
)
from motoshop_api.erp.repo import ERPRepository, get_erp_repo

router = APIRouter(tags=["erp-pos"])

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_uuid_v4(key: str) -> str:
    """Validates that key matches UUID v4 specification."""
    if not UUID_V4_RE.match(key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key must be a valid UUID v4",
        )
    return key


# ─── Sales Endpoints ─────────────────────────────────────────────

@router.post("/pos/sales", response_model=SaleOut)
async def create_sale(
    sale_in: SaleCreateIn,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    cashier: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> SaleOut:
    """Creates a new sale with required Idempotency-Key header.

    Returns HTTP 201 on first issue, or HTTP 200 on idempotent replay.
    Raises HTTP 422 if the same key is reused with a different payload.
    """
    _validate_uuid_v4(idempotency_key)
    sale, is_new = repo.create_sale(
        tenant_id=tenant_id,
        sale_in=sale_in,
        cashier_user_id=cashier.username,
        idempotency_key=idempotency_key,
    )
    if is_new:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK

    return sale


@router.get("/pos/sales/{id}", response_model=SaleOut)
async def get_sale(
    id: str,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> SaleOut:
    """Retrieves a sale by ID or invoice number within active tenant."""
    sale = repo.get_sale(tenant_id=tenant_id, sale_id=id)
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sale '{id}' not found",
        )
    return sale


@router.get("/pos/sales", response_model=list[SaleOut])
async def list_sales(
    status: Literal["issued", "voided"] | None = None,
    doc_type: Literal["POS", "FV", "RM"] | None = None,
    branch_id: str | None = None,
    session_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> list[SaleOut]:
    """Lists sales with pagination and filtering within active tenant."""
    return repo.list_sales(
        tenant_id=tenant_id,
        status=status,
        doc_type=doc_type,
        branch_id=branch_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )


@router.post("/pos/sales/{id}/void", response_model=SaleOut)
async def void_sale(
    id: str,
    payload: SaleVoidIn,
    cashier: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> SaleOut:
    """Voids an issued sale with mandatory reason and user auditing."""
    return repo.void_sale(
        tenant_id=tenant_id,
        sale_id=id,
        reason=payload.reason,
        voided_by=cashier.username,
    )


# ─── Cash Sessions Endpoints ─────────────────────────────────────

@router.get("/pos/sessions/current", response_model=CashSessionOut)
async def get_current_session(
    cashier: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> CashSessionOut:
    """Retrieves the active open cash session for current cashier in tenant."""
    session = repo.get_active_session_for_user(
        tenant_id=tenant_id,
        cashier_user_id=cashier.username,
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active cash session found for cashier '{cashier.username}'",
        )
    return session


@router.post(
    "/pos/sessions/open",
    response_model=CashSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def open_session(
    payload: CashSessionOpenIn,
    cashier: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> CashSessionOut:
    """Opens a new cash register session for the active tenant."""
    return repo.open_session(
        tenant_id=tenant_id,
        branch_id=payload.branch_id,
        cashier_user_id=cashier.username,
        cashier_name=cashier.email or cashier.username,
        opening_float=payload.opening_float,
    )


@router.post("/pos/sessions/{id}/close", response_model=CashSessionOut)
async def close_session(
    id: str,
    payload: CashSessionCloseIn,
    cashier: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> CashSessionOut:
    """Closes a cash session and computes cash variance."""
    return repo.close_session(
        tenant_id=tenant_id,
        session_id=id,
        actual_cash=payload.actual_cash,
        closed_by=cashier.username,
        denominations=payload.denominations,
        notes=payload.notes,
    )


@router.post(
    "/pos/sessions/{id}/movements",
    response_model=CashMovementOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_cash_movement(
    id: str,
    payload: CashMovementIn,
    cashier: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> CashMovementOut:
    """Records an IN or OUT manual cash movement for the tenant session."""
    return repo.add_movement(
        tenant_id=tenant_id,
        session_id=id,
        type=payload.type,
        amount=payload.amount,
        reason=payload.reason,
        performed_by=cashier.username,
    )


# ─── Product Catalog Endpoints ───────────────────────────────────

@router.get("/catalog/products/search", response_model=list[ProductSearchResult])
async def search_products(
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> list[ProductSearchResult]:
    """Search products by name, SKU, or barcode in active tenant."""
    return repo.search_products(tenant_id=tenant_id, q=q, limit=limit)


# Frontend compatibility alias
@router.get("/pos/products", response_model=list[ProductSearchResult], include_in_schema=False)
async def search_products_alias(
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
) -> list[ProductSearchResult]:
    return repo.search_products(tenant_id=tenant_id, q=q, limit=limit)
