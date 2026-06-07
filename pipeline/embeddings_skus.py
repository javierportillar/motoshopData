"""Pipeline de embeddings para búsqueda semántica de productos.

Genera embeddings OpenAI text-embedding-3-small (1536-dim) para cada SKU
en motoshop_silver_dim_producto y los guarda en columna `embedding`.

Modos:
- full:   regenera todos los embeddings (útil si cambia el modelo)
- delta:  solo SKUs sin embedding (modo por defecto)

Costo: ~$0.01 one-time para 4,829 SKUs. Delta recurrente < $0.01/mes.

Requiere: OPENAI_API_KEY en entorno.

Usage desde run_all.py:
    from pipeline.embeddings_skus import generate_embeddings
    generate_embeddings(con, mode="delta")
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BATCH_SIZE = 100  # OpenAI rate limit: 3,000 RPM tier 1
_RETRY_BACKOFF = [1, 2, 4, 8]  # exponential backoff seconds


def _get_openai_client():
    """Lazy import + auth. Raises si no hay API key."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Set it in your environment or .env file. "
            "Get one at https://platform.openai.com/api-keys"
        )
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def _add_embedding_column(con) -> None:
    """Añade columna embedding FLOAT[1536] si no existe."""
    try:
        con.execute("SELECT embedding FROM motoshop_silver_dim_producto LIMIT 0")
    except Exception:
        logger.info("Adding embedding column (FLOAT[%d]) to dim_producto", EMBEDDING_DIM)
        con.execute(
            f"ALTER TABLE motoshop_silver_dim_producto ADD COLUMN embedding FLOAT[{EMBEDDING_DIM}]"
        )


def _build_embedding_text(row: dict) -> str:
    """Construye texto de embedding combinando nombre + grupo + línea."""
    parts = [row["nombre_producto"]]
    if row.get("cod_grupo") and row["cod_grupo"] != "SIN_GRUPO":
        parts.append(f"categoría {row['cod_grupo']}")
    if row.get("descripcion"):
        parts.append(row["descripcion"])
    return " | ".join(parts)


def _batch_embed(texts: list[str], client) -> list[list[float]]:
    """Genera embeddings en batch con retry."""
    for attempt, delay in enumerate([0] + _RETRY_BACKOFF):
        try:
            if delay > 0:
                time.sleep(delay)
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as exc:
            if attempt >= len(_RETRY_BACKOFF):
                raise
            logger.warning("OpenAI batch error (attempt %d): %s", attempt + 1, exc)
            time.sleep(delay)
    raise RuntimeError("Unreachable")


def generate_embeddings(con, mode: str = "delta") -> int:
    """Genera embeddings para dim_producto.

    Args:
        con: duckdb.DuckDBPyConnection (read-write).
        mode: "delta" (solo SKUs sin embedding) | "full" (todos).

    Returns:
        Número de SKUs procesados.
    """
    from duckdb import DuckDBPyConnection

    con: DuckDBPyConnection

    _add_embedding_column(con)

    if mode == "delta":
        rows = con.execute(
            "SELECT cod_producto, nombre_producto, cod_grupo, descripcion "
            "FROM motoshop_silver_dim_producto "
            "WHERE embedding IS NULL"
        ).fetchall()
    else:
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

    client = _get_openai_client()

    processed = 0
    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i : i + BATCH_SIZE]
        texts = [_build_embedding_text(p) for p in batch]
        embeddings = _batch_embed(texts, client)

        for p, emb in zip(batch, embeddings):
            # DuckDB expects array literal as string: [1.0,2.0,...]
            emb_str = str(emb).replace("[", "").replace("]", "")
            con.execute(
                f"UPDATE motoshop_silver_dim_producto "
                f"SET embedding = CAST([{emb_str}] AS FLOAT[{EMBEDDING_DIM}]) "
                f"WHERE cod_producto = ?",
                [p["cod_producto"]],
            )

        processed += len(batch)
        logger.info(
            "Embeddings: %d/%d (%.0f%%)",
            processed, len(products), processed / len(products) * 100,
        )

    logger.info("Embeddings complete: %d products", processed)
    return processed


if __name__ == "__main__":
    import duckdb
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    db_path = os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb")
    con = duckdb.connect(db_path)
    try:
        count = generate_embeddings(con, mode="delta")
        print(f"Done: {count} embeddings generated")
    finally:
        con.close()
