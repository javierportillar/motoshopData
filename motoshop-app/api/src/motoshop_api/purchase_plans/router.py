"""Router CRUD para purchase_plans."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.users import User
from motoshop_api.purchase_plans.repo import (
    PurchasePlansRepoProtocol,
    get_purchase_plans_repo,
)
from motoshop_api.purchase_plans.schemas import (
    PurchasePlanCreate,
    PurchasePlanListResponse,
    PurchasePlanResponse,
    PurchasePlanStatusUpdate,
)

router = APIRouter(prefix="/purchase-plans", tags=["purchase-plans"])


@router.post("", response_model=PurchasePlanResponse, status_code=201)
def create_plan(
    body: PurchasePlanCreate,
    request: Request,
    repo: PurchasePlansRepoProtocol = Depends(get_purchase_plans_repo),
    user: User = Depends(get_current_user),
) -> PurchasePlanResponse:
    """Crear un plan de compras (draft)."""
    return repo.create(created_by=user.username, data=body)


@router.get("", response_model=PurchasePlanListResponse)
def list_plans(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    repo: PurchasePlansRepoProtocol = Depends(get_purchase_plans_repo),
) -> PurchasePlanListResponse:
    """Listar planes de compras (todos si admin, propios si vendedor)."""
    created_by = None if user.role == "admin" else user.username
    return repo.list(created_by=created_by, limit=limit, offset=offset)


@router.get("/{plan_id}", response_model=PurchasePlanResponse)
def get_plan(
    plan_id: int,
    request: Request,
    repo: PurchasePlansRepoProtocol = Depends(get_purchase_plans_repo),
    user: User = Depends(get_current_user),
) -> PurchasePlanResponse:
    """Obtener un plan por ID. Solo el creador o admin pueden verlo."""
    plan = repo.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    if user.role != "admin" and plan.created_by != user.username:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este plan")
    return plan


@router.patch("/{plan_id}/status", response_model=PurchasePlanResponse)
def update_plan_status(
    plan_id: int,
    body: PurchasePlanStatusUpdate,
    request: Request,
    repo: PurchasePlansRepoProtocol = Depends(get_purchase_plans_repo),
    user: User = Depends(require_role("admin", "gerente")),
) -> PurchasePlanResponse:
    """Actualizar status de un plan (approved, sent, received).
    Solo admin/gerente pueden cambiar status, y solo de sus propios planes
    (o cualquier plan si son admin).
    """
    plan = repo.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    if user.role != "admin" and plan.created_by != user.username:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar este plan")
    return repo.update_status(plan_id, body)
