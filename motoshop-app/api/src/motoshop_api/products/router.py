"""Router de productos: GET /products?q=..."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.products.repo import ProductsRepo
from motoshop_api.products.schemas import ProductOut, ProductPage, SemanticMatch, SemanticSearchResponse

router = APIRouter(tags=["products"])
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

# ── Embedding model cache — HuggingFace Inference API (sin modelo local) ──
EMBEDDING_DIM = 384


def _get_query_embedding(query: str) -> list[float]:
    """Genera embedding de query vía HF Inference API (HTTP, 0 RAM)."""
    from motoshop_api.embeddings import _get_query_embedding as _hf
    return _hf(query)


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


# ── Semantic search (BEFORE /{sku} to avoid route conflict) ─────────────


@router.get("/products/search-semantic", response_model=SemanticSearchResponse)
@limiter.limit("30/minute")
async def search_semantic(
    request: Request,
    q: str = Query(..., min_length=2, description="Búsqueda en lenguaje natural"),
    limit: int = Query(default=10, ge=1, le=50),
    _user: User = Depends(get_current_user),
) -> SemanticSearchResponse:
    """Búsqueda semántica de productos."""
    # Debug temporal: siempre responde
    return SemanticSearchResponse(query=q, results=[SemanticMatch(codprod="TEST", nomprod="Prueba", score=1.0)], total=1)


def _ensure_duckdb_file(db_path: str) -> None:
    """Intenta descargar DuckDB de R2 si no existe localmente."""
    if os.path.exists(db_path):
        return
    _p = Path(db_path)
    _p.parent.mkdir(parents=True, exist_ok=True)
    try:
        from motoshop_api.metrics.repo_duckdb import _bootstrap_duckdb_from_r2
        _bootstrap_duckdb_from_r2(_p)
    except Exception:
        pass
    if not os.path.exists(db_path) and os.path.exists("out/motoshop_gold.duckdb"):
        os.environ["DUCKDB_PATH"] = os.path.abspath("out/motoshop_gold.duckdb")


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
