"""Embeddings vía fastembed (ONNX local, sin PyTorch, cero HTTP).

Pipeline (en Mac):
    pipeline/embeddings_skus.py → sentence-transformers → DuckDB

Query en Render (en caliente):
    _get_query_embedding() → fastembed lazy singleton → vector[384]
    Sin llamadas HTTP externas. Modelo ~130MB en RAM.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_model = None


def _get_query_embedding(text: str) -> list[float]:
    """Genera el embedding de UNA query usando fastembed (ONNX local).

    El modelo se carga lazy: primera llamada descarga ~130MB desde HuggingFace,
    después queda cachead en memoria para todas las queries siguientes.
    """
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = TextEmbedding(model_name=EMBEDDING_MODEL)
        logger.info("Model loaded — dim=%d", EMBEDDING_DIM)

    # fastembed devuelve generator → list → [0]
    embedding = list(_model.embed([text]))[0].tolist()
    return embedding


def ensure_embeddings(db_path: str) -> int:
    """No-op — los embeddings se generan en pipeline local (Mac)."""
    return 0
