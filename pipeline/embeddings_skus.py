"""Pipeline de embeddings para motoshop_silver_dim_producto.

Se corre en la Mac del PO, NO en Render, NO en Windows.

Uso:
    python -m pipeline.embeddings_skus          # delta (solo faltantes)
    python -m pipeline.embeddings_skus --full   # regenerar todos

Modelo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384d, español).

Post-condición: subir out/motoshop_gold.duckdb a R2:
    python scripts/upload_duckdb_to_r2.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Dependencias LOCALES (instaladas en la Mac, NO en pyproject.toml) ──
# pip install sentence-transformers  (solo en la Mac del PO)
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    _msg = "ERROR: sentence-transformers no instalado.\n  pip install sentence-transformers\n  (Solo necesario en Mac para generar embeddings. NO va en pyproject.toml.)"
    if __name__ == "__main__":
        sys.exit(_msg)
    else:
        # Cuando se importa desde run_all.py, sys.exit() levanta SystemExit
        # que NO es caught por except Exception. Usar raise en su lugar.
        raise ImportError(_msg)

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 256

_model = None


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Model loaded — dim=%d", _model.get_sentence_embedding_dimension())
    return _model


def _build_embedding_text(row: dict) -> str:
    """Texto descriptivo para embedding usando diccionario de sinónimos."""
    import sys, os
    _api_src = os.path.join(os.path.dirname(__file__), "..", "motoshop-app", "api", "src")
    if _api_src not in sys.path:
        sys.path.insert(0, os.path.abspath(_api_src))
    from motoshop_api.synonyms import enrich_sku_text

    nombre = str(row.get("nombre_producto", ""))
    grupo = row.get("cod_grupo")
    categoria = grupo if grupo and str(grupo) != "SIN_GRUPO" else None
    return enrich_sku_text(nombre, categoria)


def _add_column(con) -> None:
    try:
        con.execute("SELECT embedding FROM motoshop_silver_dim_producto LIMIT 0")
    except Exception:
        logger.info("Adding embedding column FLOAT[%d]", EMBEDDING_DIM)
        con.execute(f"ALTER TABLE motoshop_silver_dim_producto ADD COLUMN embedding FLOAT[{EMBEDDING_DIM}]")


def generate_embeddings(db_path: str | Path, mode: str = "delta") -> int:
    """Genera embeddings y escribe en DuckDB.

    Args:
        db_path: Ruta al archivo DuckDB.
        mode: "delta" | "full"

    Returns:
        Cantidad de SKUs embedidos.
    """
    import duckdb

    con = duckdb.connect(str(db_path))
    _add_column(con)

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
        con.close()
        return 0

    logger.info("Embedding %d products (mode=%s)", len(products), mode)
    model = _get_model()
    texts = [_build_embedding_text(p) for p in products]
    embeddings = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=True)

    for p, emb in zip(products, embeddings):
        emb_str = str(emb.tolist()).replace("[", "").replace("]", "")
        con.execute(
            f"UPDATE motoshop_silver_dim_producto "
            f"SET embedding = CAST([{emb_str}] AS FLOAT[{EMBEDDING_DIM}]) "
            f"WHERE cod_producto = ?",
            [p["cod_producto"]],
        )

    con.close()
    logger.info("Done: %d products", len(products))
    return len(products)


# ── Pipeline observability (MySQL logging, no-op si MySQL no accesible) ──
_PIPELINE_RUN_ID: int | None = None
_PIPELINE_START: float | None = None


def _try_start_run(pipeline_name: str, triggered_by: str = "manual") -> int | None:
    """Crea app_pipeline_runs si MySQL está disponible. Returns run_id o None."""
    try:
        import pymysql
        conn = pymysql.connect(host="localhost", port=3306, user="root",
                                database="motoshop2024", charset="utf8")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_pipeline_runs (pipeline_name, started_at, status, triggered_by) "
            "VALUES (%s, NOW(), 'running', %s)",
            (pipeline_name, triggered_by),
        )
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        logger.info("Pipeline run #%d logged to MySQL", run_id)
        return run_id
    except Exception as exc:
        logger.info("MySQL logging skipped: %s", exc)
        return None


def _try_finish_run(run_id: int | None, status: str, dur_s: float, err: str | None = None) -> None:
    if run_id is None:
        return
    try:
        import pymysql
        conn = pymysql.connect(host="localhost", port=3306, user="root",
                                database="motoshop2024", charset="utf8")
        cur = conn.cursor()
        if err:
            cur.execute(
                "UPDATE app_pipeline_runs SET finished_at=NOW(), status=%s, duration_seconds=%s, error_message=%s "
                "WHERE id=%s",
                (status, dur_s, err, run_id),
            )
        else:
            cur.execute(
                "UPDATE app_pipeline_runs SET finished_at=NOW(), status=%s, duration_seconds=%s "
                "WHERE id=%s",
                (status, dur_s, run_id),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    mode = "full" if "--full" in sys.argv else "delta"
    db_path = os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb")
    _PIPELINE_RUN_ID = _try_start_run("embeddings_skus", "manual")
    _PIPELINE_START = __import__("time").time()
    try:
        count = generate_embeddings(db_path, mode=mode)
        dur = __import__("time").time() - _PIPELINE_START
        _try_finish_run(_PIPELINE_RUN_ID, "success", dur)
        print(f"\n✅ {count} embeddings generados en {db_path} (mode={mode})")
        print(f"   → python scripts/upload_duckdb_to_r2.py  para subir a R2")
    except Exception as exc:
        dur = __import__("time").time() - _PIPELINE_START if _PIPELINE_START else 0
        _try_finish_run(_PIPELINE_RUN_ID, "failed", dur, str(exc))
        raise
