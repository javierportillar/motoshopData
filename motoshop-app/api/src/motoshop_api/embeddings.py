"""Generación de embeddings para búsqueda semántica (fastembed ONNX).

Usa fastembed (sin PyTorch, ONNX runtime nativo).
Modelo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384d, multilingüe).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 256

_model = None


def _get_embed_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = TextEmbedding(model_name=EMBEDDING_MODEL)
        logger.info("Model loaded — dim=%d", EMBEDDING_DIM)
    return _model


def _build_embedding_text(product_row: dict) -> str:
    """Construye texto descriptivo para embedding."""
    parts = [str(product_row.get("nombre_producto", ""))]
    grupo = product_row.get("cod_grupo")
    if grupo and str(grupo) != "SIN_GRUPO":
        parts.append(f"categoría {grupo}")
    desc = product_row.get("descripcion")
    if desc:
        parts.append(str(desc))
    return " | ".join(parts)


def ensure_embeddings(db_path: str) -> int:
    """Genera embeddings faltantes en la tabla motoshop_silver_dim_producto.

    Args:
        db_path: Ruta al archivo DuckDB.

    Returns:
        Número de productos embedidos (0 si ya estaban todos).
    """
    import duckdb

    con = duckdb.connect(db_path)

    # Crear columna si no existe
    col_exists = False
    try:
        con.execute("SELECT embedding FROM motoshop_silver_dim_producto LIMIT 0")
        col_exists = True
    except Exception:
        pass

    if not col_exists:
        logger.info("Adding embedding column (FLOAT[%d]) to dim_producto", EMBEDDING_DIM)
        con.execute(
            f"ALTER TABLE motoshop_silver_dim_producto ADD COLUMN embedding FLOAT[{EMBEDDING_DIM}]"
        )

    # Contar productos sin embedding
    missing = con.execute(
        "SELECT cod_producto, nombre_producto, cod_grupo, descripcion "
        "FROM motoshop_silver_dim_producto WHERE embedding IS NULL"
    ).fetchall()

    if not missing:
        con.close()
        return 0

    columns = ["cod_producto", "nombre_producto", "cod_grupo", "descripcion"]
    products = [dict(zip(columns, r)) for r in missing]
    logger.info("Generating embeddings for %d products", len(products))

    model = _get_embed_model()
    texts = [_build_embedding_text(p) for p in products]
    embeddings = list(model.embed(texts, batch_size=BATCH_SIZE))

    for p, emb in zip(products, embeddings):
        emb_str = str(emb.tolist()).replace("[", "").replace("]", "")
        con.execute(
            f"UPDATE motoshop_silver_dim_producto "
            f"SET embedding = CAST([{emb_str}] AS FLOAT[{EMBEDDING_DIM}]) "
            f"WHERE cod_producto = ?",
            [p["cod_producto"]],
        )

    con.close()
    logger.info("Embedded %d products", len(products))
    return len(products)
