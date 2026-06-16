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
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.products.schemas import (
    MovementItem,
    ProductOut,
    ProductPage,
    ProductMovementsResponse,
    SemanticMatch,
    SemanticSearchResponse,
)

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
def search_semantic(
    request: Request,
    q: str = Query(..., min_length=2, description="Búsqueda en lenguaje natural"),
    limit: int = Query(default=10, ge=1, le=50),
    _user: User = Depends(get_current_user),
) -> SemanticSearchResponse:
    """Búsqueda semántica de productos — DuckDB embeddings o fallback MySQL."""
    from motoshop_api.config import settings as _settings

    db_path = _settings.duckdb_path
    _ensure_duckdb_file(db_path)

    # 1. Intentar DuckDB embeddings con score híbrido
    try:
        if os.path.exists(db_path):
            from motoshop_api.embeddings import _get_query_embedding
            from motoshop_api.synonyms import split_keywords as _split_keywords
            from motoshop_api.synonyms import expand_keyword_terms as _expand

            query_emb = _get_query_embedding(q)
            emb_str = str(query_emb).replace("[", "").replace("]", "")
            dim = len(query_emb)

            # Armar keyword conditions con términos expandidos
            keywords = _split_keywords(q)
            safe_first = keywords[0].replace("'", "''") if len(keywords) >= 1 else q.split()[0].replace("'", "''")
            safe_second = keywords[1].replace("'", "''") if len(keywords) >= 2 else ""

            # Expandir a términos relacionados (ej: manija → manigueta, clutch)
            first_terms = _expand(keywords[0]) if len(keywords) >= 1 else [safe_first]
            second_terms = _expand(keywords[1]) if len(keywords) >= 2 else []

            # Construir LIKEs para cada término expandido
            first_likes = " OR ".join(
                f"UPPER(nombre_producto) LIKE UPPER('%{t.replace(chr(39), chr(39)+chr(39))}%')"
                for t in first_terms
            )
            if second_terms:
                second_likes = " OR ".join(
                    f"UPPER(nombre_producto) LIKE UPPER('%{t.replace(chr(39), chr(39)+chr(39))}%')"
                    for t in second_terms
                )
                keyword_case = f" CASE WHEN {first_likes} THEN 1.0 ELSE 0.0 END + CASE WHEN {second_likes} THEN 0.5 ELSE 0.0 END"
            else:
                keyword_case = f" CASE WHEN {first_likes} THEN 1.0 ELSE 0.0 END"

            con = duckdb.connect(db_path, read_only=True)
            rows = con.execute(f"""
                WITH semantic AS (
                    SELECT cod_producto, nombre_producto AS nomprod,
                           array_cosine_similarity(
                               embedding, CAST([{emb_str}] AS FLOAT[{dim}])
                           )::DOUBLE AS semantic_score
                    FROM silver_dim_producto
                    WHERE embedding IS NOT NULL
                ),
                keyword AS (
                    SELECT cod_producto,
                           {keyword_case} AS keyword_score
                    FROM silver_dim_producto
                )
                SELECT s.cod_producto, s.nomprod,
                       ROUND(0.3 * s.semantic_score + 0.7 * k.keyword_score, 4) AS score,
                       ROUND(s.semantic_score, 4) AS sem,
                       ROUND(k.keyword_score, 4) AS kw
                FROM semantic s
                LEFT JOIN keyword k ON s.cod_producto = k.cod_producto
                ORDER BY score DESC
                LIMIT ?
            """, [limit]).fetchall()
            con.close()

            if rows:
                return SemanticSearchResponse(
                    query=q,
                    results=[SemanticMatch(codprod=str(r[0]), nomprod=str(r[1]), score=float(r[2])) for r in rows],
                    total=len(rows),
                )
    except Exception as exc:
        logger.warning("duckdb_semantic_failed: %s", exc)

    # 2. Fallback: MySQL LIKE search
    try:
        repo = get_products_repo()
        matches = [
            SemanticMatch(codprod=str(r.get("codprod","")), nomprod=str(r.get("nomprod","")), score=0.0)
            for r in repo.search(query=q, limit=limit, offset=0)
        ]
        return SemanticSearchResponse(query=q, results=matches, total=len(matches))
    except Exception as exc:
        logger.error("mysql_semantic_fallback_failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Semantic search no disponible (DuckDB offline, MySQL offline).",
        )


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


@router.get("/products/{sku}/movements", response_model=ProductMovementsResponse)
@limiter.limit("60/minute")
async def get_product_movements(
    request: Request,
    sku: str,
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> ProductMovementsResponse:
    """Retorna historial de ventas y compras de un SKU desde DuckDB.

    Requiere autenticación y que el tenant tenga datos en DuckDB.
    """
    from motoshop_api.metrics.repo_duckdb import _make_db_path, _bootstrap_duckdb_from_r2

    _p = _make_db_path(tenant)
    _bootstrap_duckdb_from_r2(_p, tenant)
    if not _p.exists():
        raise HTTPException(status_code=503, detail="DuckDB no disponible para este tenant")

    try:
        con = duckdb.connect(str(_p), read_only=True)
    except Exception as exc:
        logger.error("duckdb_connect_failed: %s", exc)
        raise HTTPException(status_code=503, detail="No se pudo conectar a DuckDB")

    try:
        # ── Ventas (últimos 50 docs) ──
        ventas_raw = con.execute("""
            SELECT
                CAST(business_date AS VARCHAR) AS fecha,
                num_documento AS documento,
                ROUND(SUM(cantidad), 2) AS cantidad,
                ROUND(AVG(valor_unitario), 2) AS valor_unitario,
                ROUND(SUM(total_detalle), 2) AS total
            FROM silver_fact_ventas_detalle
            WHERE cod_producto = ?
            GROUP BY business_date, num_documento
            ORDER BY business_date DESC
            LIMIT 50
        """, [sku]).fetchall()

        # ── Compras (últimos 50 docs) ──
        compras_raw = con.execute("""
            SELECT
                CAST(business_date AS VARCHAR) AS fecha,
                num_documento AS documento,
                ROUND(SUM(cantidad), 2) AS cantidad,
                ROUND(AVG(valor_unitario), 2) AS valor_unitario,
                ROUND(SUM(total_detalle), 2) AS total
            FROM silver_fact_compras_detalle
            WHERE cod_producto = ?
            GROUP BY business_date, num_documento
            ORDER BY business_date DESC
            LIMIT 50
        """, [sku]).fetchall()

        # ── Totales ALL-TIME (compras + ventas, sin límite) ──
        totales_raw = con.execute("""
            SELECT
                COALESCE((SELECT SUM(cantidad) FROM silver_fact_compras_detalle WHERE cod_producto = ?), 0) AS total_compras_all,
                COALESCE((SELECT SUM(cantidad) FROM silver_fact_ventas_detalle WHERE cod_producto = ?), 0) AS total_ventas_all
        """, [sku, sku]).fetchone()
        total_compras_all = float(totales_raw[0] or 0) if totales_raw else 0.0
        total_ventas_all = float(totales_raw[1] or 0) if totales_raw else 0.0
        stock_calculado = total_compras_all - total_ventas_all

        # ── Último costo unitario (compra) ──
        ultimo_costo = con.execute("""
            SELECT costo_producto FROM silver_fact_compras_detalle
            WHERE cod_producto = ? AND costo_producto > 0
            ORDER BY business_date DESC
            LIMIT 1
        """, [sku]).fetchone()

        # ── Último precio de venta ──
        ultimo_precio = con.execute("""
            SELECT valor_unitario FROM silver_fact_ventas_detalle
            WHERE cod_producto = ?
            ORDER BY business_date DESC
            LIMIT 1
        """, [sku]).fetchone()

        # ── Nombre producto ──
        nombre = None
        nombre_raw = con.execute("""
            SELECT nom_producto FROM gold_mart_inventario_actual
            WHERE cod_producto = ? AND nom_producto IS NOT NULL AND nom_producto != ''
            LIMIT 1
        """, [sku]).fetchone()
        if nombre_raw:
            nombre = str(nombre_raw[0])
        else:
            nombre_raw2 = con.execute("""
                SELECT nombre_detalle FROM silver_fact_ventas_detalle
                WHERE cod_producto = ? AND nombre_detalle IS NOT NULL
                LIMIT 1
            """, [sku]).fetchone()
            if nombre_raw2:
                nombre = str(nombre_raw2[0])

    except Exception as exc:
        con.close()
        logger.error("duckdb_movements_query_failed: %s", exc)
        raise HTTPException(status_code=500, detail="Error al consultar movimientos")
    finally:
        con.close()

    def _to_movements(rows: list, tipo: str) -> list:
        return [
            MovementItem(
                tipo=tipo,
                fecha=str(r[0]),
                documento=str(r[1]),
                cantidad=float(r[2] or 0),
                valor_unitario=float(r[3] or 0),
                total=float(r[4] or 0),
            )
            for r in rows
        ]

    ventas = _to_movements(ventas_raw, "venta")
    compras = _to_movements(compras_raw, "compra")

    # total_* es ALL-TIME (sin límite), la lista detallada muestra solo los últimos 50
    ultimo_costo_val = float(ultimo_costo[0]) if ultimo_costo else None
    ultimo_precio_val = float(ultimo_precio[0]) if ultimo_precio else None

    return ProductMovementsResponse(
        sku=sku,
        nom_producto=nombre,
        ventas=ventas,
        compras=compras,
        stock_actual=round(stock_calculado, 2),
        total_ventas=round(total_ventas_all, 2),
        total_compras=round(total_compras_all, 2),
        ultimo_costo_unitario=ultimo_costo_val,
        ultimo_precio_venta=ultimo_precio_val,
    )
