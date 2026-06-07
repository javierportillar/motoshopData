"""Router de productos: GET /products?q=..."""

from __future__ import annotations

import logging
import os

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

# ── Embedding model cache (HuggingFace, local, gratis) ──────────────────
_embed_model = None
EMBEDDING_DIM = 384


def _get_embed_model():
    """Lazy singleton — carga paraphrase-multilingual-MiniLM-L12-v2 una sola vez."""
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            logger.info("Loading embedding model: %s", model_name)
            _embed_model = SentenceTransformer(model_name)
            logger.info("Embedding model loaded — dim=%d", _embed_model.get_sentence_embedding_dimension())
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Semantic search not available: sentence-transformers not installed",
            )
        except Exception as exc:
            logger.error("Failed to load embedding model: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"Semantic search not available: failed to load embedding model",
            )
    return _embed_model


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
    """Búsqueda semántica de productos vía HuggingFace embeddings + DuckDB cosine similarity.

    Modelo: paraphrase-multilingual-MiniLM-L12-v2 (384d, multilingüe, local y gratis).
    Ejemplo: "aceite sintético 4 tiempos" → encuentra "MOBIL SUPER MOTO 4T 20W50".
    """
    from motoshop_api.config import settings

    db_path = settings.duckdb_path or "/tmp/motoshop_gold.duckdb"
    if not os.path.exists(db_path):
        raise HTTPException(
            status_code=503,
            detail=f"DuckDB not found at {db_path}. Run embeddings pipeline first.",
        )

    # 1. Generar embedding de la query con HuggingFace (local)
    try:
        model = _get_embed_model()
        query_emb = model.encode([q], show_progress_bar=False)[0].tolist()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to generate query embedding") from exc

    # 2. Cosine similarity en DuckDB
    emb_str = str(query_emb).replace("[", "").replace("]", "")
    query_dim = len(query_emb)

    try:
        con = duckdb.connect(db_path, read_only=True)
        rows = con.execute(f"""
            SELECT
                cod_producto,
                nombre_producto AS nomprod,
                ROUND(array_cosine_similarity(
                    embedding,
                    CAST([{emb_str}] AS FLOAT[{query_dim}])
                )::DOUBLE, 4) AS score
            FROM motoshop_silver_dim_producto
            WHERE embedding IS NOT NULL
            ORDER BY score DESC
            LIMIT ?
        """, [limit]).fetchall()
        con.close()
    except Exception as exc:
        logger.error("DuckDB semantic query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Semantic search query failed") from exc

    results = [
        SemanticMatch(codprod=str(r[0]), nomprod=str(r[1]), score=float(r[2]))
        for r in rows
    ]

    return SemanticSearchResponse(query=q, results=results, total=len(results))


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
