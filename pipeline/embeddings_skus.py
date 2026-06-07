"""Pipeline de embeddings para búsqueda semántica de productos.

Genera embeddings con fastembed (ONNX nativo, sin PyTorch) para cada SKU
en motoshop_silver_dim_producto y los guarda en columna `embedding`.

Modelo: intfloat/multilingual-e5-small (118MB, 384d, multilingüe).
¡Gratuito, local, sin API key, sin GPU!

Modos:
- full:   regenera todos los embeddings
- delta:  solo SKUs sin embedding (modo por defecto)

Usage desde run_all.py:
    from pipeline.embeddings_skus import generate_embeddings
    generate_embeddings(con, mode="delta")
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 256

# Lazy singleton
_model = None


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = TextEmbedding(model_name=EMBEDDING_MODEL)
        logger.info("Model loaded — dim=%d", EMBEDDING_DIM)
    return _model


def _add_embedding_column(con) -> None:
    """Añade columna embedding FLOAT[384] si no existe."""
    try:
        con.execute("SELECT embedding FROM motoshop_silver_dim_producto LIMIT 0")
    except Exception:
        logger.info("Adding embedding column (FLOAT[%d]) to dim_producto", EMBEDDING_DIM)
        con.execute(
            f"ALTER TABLE motoshop_silver_dim_producto ADD COLUMN embedding FLOAT[{EMBEDDING_DIM}]"
        )


def _build_embedding_text(row: dict) -> str:
    """Construye texto de embedding combinando nombre + grupo."""
    parts = [row["nombre_producto"]]
    if row.get("cod_grupo") and row["cod_grupo"] != "SIN_GRUPO":
        parts.append(f"categoría {row['cod_grupo']}")
    if row.get("descripcion"):
        parts.append(row["descripcion"])
    return " | ".join(parts)


def generate_embeddings(con, mode: str = "delta") -> int:
    """Genera embeddings para dim_producto usando fastembed (ONNX).

    Args:
        con: duckdb.DuckDBPyConnection (read-write).
        mode: "delta" (solo SKUs sin embedding) | "full" (todos).

    Returns:
        Número de SKUs procesados.
    """
    _add_embedding_column(con)

    if mode == "delta":
        rows = con.execute(
            "SELECT cod_producto, nombre_producto, cod_grupo, descripcion "
            "FROM motoshop_silver_dim_producto "
            "WHERE embedding IS NULL"
        ).fetchall()
    else:
        # full: null existing embeddings first
        con.execute("UPDATE motoshop_silver_dim_producto SET embedding = NULL")
        rows = con.execute(
            "SELECT cod_producto, nombre_producto, cod_grupo, descripcion "
            "FROM motoshop_silver_dim_producto"
        ).fetchall()

    columns = ["cod_producto", "nombre_producto", "cod_grupo", "descripcion"]
    products = [dict(zip(columns, r)) for r in rows]

    if not products:
        logger.info("No products to embed (mode=%s)", mode)
        return 0

    logger.info("Generating embeddings for %d products (mode=%s)", len(products), mode)
    model = _get_model()
    texts = [_build_embedding_text(p) for p in products]

    # fastembed devuelve generator de numpy arrays
    embeddings = list(model.embed(texts, batch_size=BATCH_SIZE))

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
    from fastembed import TextEmbedding

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    db_path = os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb")
    con = duckdb.connect(db_path)
    try:
        count = generate_embeddings(con, mode="full")
        print(f"Done: {count} embeddings generated")
    finally:
        con.close()
