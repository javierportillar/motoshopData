"""Router de productos: GET /products?q=..."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.products.repo import ProductsRepo
from motoshop_api.products.schemas import ProductOut, ProductPage

router = APIRouter(tags=["products"])

limiter = Limiter(key_func=get_remote_address)


def get_products_repo() -> ProductsRepo:
    from motoshop_api.db.engine import get_engine

    return ProductsRepo(get_engine())


@router.get("/products", response_model=ProductPage)
@limiter.limit("60/minute")
async def list_products(
    request: Request,
    q: str | None = Query(None, description="Búsqueda por nombre o código"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(get_current_user),
    repo: ProductsRepo = Depends(get_products_repo),
) -> ProductPage:
    """Lista productos con paginación. Requiere autenticación."""
    items = repo.search(query=q, limit=limit, offset=offset)
    total = repo.count(query=q)
    return ProductPage(
        items=[ProductOut(**i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{sku}", response_model=ProductOut)
@limiter.limit("60/minute")
async def get_product(
    request: Request,
    sku: str,
    _user: User = Depends(get_current_user),
    repo: ProductsRepo = Depends(get_products_repo),
) -> ProductOut:
    """Retorna detalle de un producto por SKU exacto. Requiere autenticación."""
    row = repo.get_by_sku(sku)
    if row is None:
        raise HTTPException(status_code=404, detail=f"SKU '{sku}' no encontrado")
    return ProductOut(**row)
