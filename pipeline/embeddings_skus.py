"""Pipeline de embeddings — wrapper que llama a motoshop_api.embeddings.

Reutiliza la lógica del API para evitar duplicación.
Corre: python -m pipeline.embeddings_skus [--mode full]
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Ensure API package is importable (adjacent to pipeline/ in repo root)
_API_PATH = os.path.join(os.path.dirname(__file__), "..", "motoshop-app", "api", "src")
if _API_PATH not in sys.path:
    sys.path.insert(0, os.path.abspath(_API_PATH))


def generate_embeddings(con, mode: str = "delta") -> int:
    """Genera embeddings reutilizando la lógica del API.

    Args:
        con: duckdb.DuckDBPyConnection (read-write).
        mode: "delta" (solo embeddings faltantes) | "full" (todos).

    Returns:
        Número de SKUs procesados.
    """
    from motoshop_api.embeddings import (
        EMBEDDING_DIM,
        _build_embedding_text,
        _get_embed_model,
    )

    # Crear columna si no existe
    col_exists = False
    try:
        con.execute("SELECT embedding FROM motoshop_silver_dim_producto LIMIT 0")
        col_exists = True
    except Exception:
        pass

    if not col_exists:
        logger.info("Adding embedding column (FLOAT[%d]) to dim_producto", EMBEDDING_DIM)
        con.execute(f"ALTER TABLE motoshop_silver_dim_producto ADD COLUMN embedding FLOAT[{EMBEDDING_DIM}]")

    if mode == "full":
        con.execute("UPDATE motoshop_silver_dim_producto SET embedding = NULL")
        rows = con.execute(
            "SELECT cod_producto, nombre_producto, cod_grupo, descripcion "
            "FROM motoshop_silver_dim_producto"
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT cod_producto, nombre_producto, cod_grupo, descripcion "
            "FROM motoshop_silver_dim_producto WHERE embedding IS NULL"
        ).fetchall()

    columns = ["cod_producto", "nombre_producto", "cod_grupo", "descripcion"]
    products = [dict(zip(columns, r)) for r in rows]

    if not products:
        logger.info("No products to embed (mode=%s)", mode)
        return 0

    logger.info("Generating embeddings for %d products (mode=%s)", len(products), mode)
    model = _get_embed_model()
    texts = [_build_embedding_text(p) for p in products]
    embeddings = list(model.embed(texts, batch_size=256))

    for p, emb in zip(products, embeddings):
        emb_str = str(emb.tolist()).replace("[", "").replace("]", "")
        con.execute(
            f"UPDATE motoshop_silver_dim_producto "
            f"SET embedding = CAST([{emb_str}] AS FLOAT[{EMBEDDING_DIM}]) "
            f"WHERE cod_producto = ?",
            [p["cod_producto"]],
        )

    logger.info("Embeddings complete: %d products", len(products))
    return len(products)


if __name__ == "__main__":
    import duckdb

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("full", "delta") else "delta"

    db_path = os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb")
    con = duckdb.connect(db_path)
    try:
        count = generate_embeddings(con, mode=mode)
        print(f"Done: {count} embeddings generated (mode={mode})")
    finally:
        con.close()
