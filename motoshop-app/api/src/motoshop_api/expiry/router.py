"""REST endpoints for manual MasVital lot and expiry tracking."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.expiry.repo import ExpiryLotsRepo, get_expiry_lots_repo
from motoshop_api.expiry.schemas import (
    ExpiryAlertItem,
    ExpiryAlertListResponse,
    ExpiryLotListResponse,
    ExpiryLotResponse,
    LotAdjustmentCreate,
    LotUpdate,
    MutationLotResponse,
    ReceiptCreate,
)

router = APIRouter(prefix="/expiry", tags=["expiry-lots"])


def _require_masvital(tenant: str) -> str:
    """Enforce the product boundary at the API layer as well as the database."""
    if tenant != "masvital":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La gestión de caducidad no está habilitada para este tenant.",
        )
    return tenant


def get_masvital_tenant(tenant: str = Depends(get_tenant)) -> str:
    """Resolve an authorized tenant, then restrict this module to MasVital."""
    return _require_masvital(tenant)


@router.get("/lots", response_model=ExpiryLotListResponse)
def list_lots(
    product_sku: str | None = Query(default=None, min_length=1, max_length=128),
    expires_before: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_masvital_tenant),
    repo: ExpiryLotsRepo = Depends(get_expiry_lots_repo),
) -> ExpiryLotListResponse:
    """List manually entered MasVital lots, always scoped to the authorized tenant."""
    items, total = repo.list_lots(
        tenant=tenant,
        product_sku=product_sku.strip() if product_sku else None,
        expires_before=expires_before,
        limit=limit,
        offset=offset,
    )
    return ExpiryLotListResponse(
        items=[ExpiryLotResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts", response_model=ExpiryAlertListResponse)
def list_expiry_alerts(
    days: int = Query(default=90, ge=0, le=730),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_masvital_tenant),
    repo: ExpiryLotsRepo = Depends(get_expiry_lots_repo),
) -> ExpiryAlertListResponse:
    """List non-empty lots expiring in the requested horizon; no FEFO allocation occurs."""
    today = date.today()
    items = repo.list_alerts(tenant=tenant, expires_before=today + timedelta(days=days))
    return ExpiryAlertListResponse(
        items=[
            ExpiryAlertItem.model_validate(
                {**item, "days_until_expiry": (date.fromisoformat(item["expires_on"]) - today).days}
            )
            for item in items
        ],
        horizon_days=days,
    )


@router.post("/receipts", response_model=MutationLotResponse, status_code=status.HTTP_201_CREATED)
def create_receipt(
    payload: ReceiptCreate,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_masvital_tenant),
    repo: ExpiryLotsRepo = Depends(get_expiry_lots_repo),
) -> Response:
    """Record one manual receipt with an explicit lot and expiry date (MasVital only)."""
    result = repo.create_receipt(
        tenant=tenant,
        actor=user.username,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    body = MutationLotResponse(
        lot=ExpiryLotResponse.model_validate(result["lot"]),
        replayed=bool(result.get("replayed")),
    )
    return Response(
        content=body.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK if body.replayed else status.HTTP_201_CREATED,
    )


@router.patch("/lots/{lot_id}", response_model=MutationLotResponse)
def update_lot(
    lot_id: UUID,
    payload: LotUpdate,
    _user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_masvital_tenant),
    repo: ExpiryLotsRepo = Depends(get_expiry_lots_repo),
) -> MutationLotResponse:
    """Edit a lot's metadata (product, invoice, dates, quantity, notes).

    This corrects the caducidad record itself; it never touches the system
    inventory (ETL/DuckDB). Restricted to MasVital and privileged roles.
    """
    result = repo.update_lot(tenant=tenant, lot_id=lot_id, payload=payload)
    return MutationLotResponse(
        lot=ExpiryLotResponse.model_validate(result["lot"]),
        replayed=False,
    )


@router.post(
    "/lots/{lot_id}/adjustments",
    response_model=MutationLotResponse,
    status_code=status.HTTP_201_CREATED,
)
def adjust_lot(
    lot_id: UUID,
    payload: LotAdjustmentCreate,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_masvital_tenant),
    repo: ExpiryLotsRepo = Depends(get_expiry_lots_repo),
) -> Response:
    """Apply a privileged manual quantity correction; DB rejects a negative remainder."""
    result = repo.adjust_lot(
        tenant=tenant,
        lot_id=lot_id,
        actor=user.username,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    body = MutationLotResponse(
        lot=ExpiryLotResponse.model_validate(result["lot"]),
        replayed=bool(result.get("replayed")),
    )
    return Response(
        content=body.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK if body.replayed else status.HTTP_201_CREATED,
    )
