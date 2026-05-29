"""Router de stock: GET /products/{sku}/stock"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.stock.repo import StockRepo
from motoshop_api.stock.schemas import StockResponse

router = APIRouter(tags=["stock"])

limiter = Limiter(key_func=get_remote_address)


def get_stock_repo() -> StockRepo:
    from motoshop_api.db.engine import get_engine

    return StockRepo(get_engine())


@router.get("/products/{sku}/stock", response_model=StockResponse)
@limiter.limit("60/minute")
async def get_stock(
    request: Request,
    sku: str,
    _user: User = Depends(get_current_user),
    repo: StockRepo = Depends(get_stock_repo),
) -> StockResponse:
    """Retorna stock de un SKU. Requiere autenticación."""
    result = repo.get_stock_by_sku(sku)
    if result["nomprod"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU '{sku}' no encontrado",
        )
    return StockResponse(**result)
