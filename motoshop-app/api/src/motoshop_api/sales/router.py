"""Router de ventas: GET /sales/recent"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.sales.repo import SalesRepo
from motoshop_api.sales.schemas import SaleOut, SalesPage

router = APIRouter(tags=["sales"])

limiter = Limiter(key_func=get_remote_address)


def get_sales_repo() -> SalesRepo:
    from motoshop_api.db.engine import get_engine
    return SalesRepo(get_engine())


@router.get("/sales/recent", response_model=SalesPage)
@limiter.limit("60/minute")
async def list_recent_sales(
    request: Request,
    since: str | None = Query(None, description="Fecha ISO 8601 UTC mínima"),
    limit: int = Query(50, ge=1, le=200),
    _user: User = Depends(get_current_user),
    repo: SalesRepo = Depends(get_sales_repo),
) -> SalesPage:
    """Lista ventas recientes (solo activas). Requiere autenticación."""
    items = repo.get_recent(since=since, limit=limit)
    return SalesPage(
        items=[SaleOut(**i) for i in items],
        total=len(items),
        limit=limit,
    )
