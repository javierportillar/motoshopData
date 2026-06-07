"""Embeddings vía HuggingFace InferenceClient (HTTP, 0 modelos en RAM).

Usa huggingface_hub.InferenceClient que maneja correctamente el
feature-extraction pipeline (evita el problema de sentence-similarity
del router.huggingface.co).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_client = None


def _get_client():
    global _client
    if _client is None:
        from huggingface_hub import InferenceClient
        token = os.environ.get("HF_API_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        logger.info("init_hf_client: token_set=%s", bool(token))
        _client = InferenceClient(
            model=EMBEDDING_MODEL,
            token=token,
        )
    return _client


def _get_query_embedding(text: str) -> list[float]:
    """Genera embedding de query via HuggingFace InferenceClient.

    Expande la query con sinónimos antes de llamar a feature_extraction
    para mejorar la calidad de los resultados semánticos.
    """
    from motoshop_api.synonyms import expand_query

    client = _get_client()
    expanded = expand_query(text)
    if expanded != text:
        logger.info("query_expanded: %s → %s", text[:60], expanded[:120])

    result = client.feature_extraction(expanded)
    # feature_extraction devuelve ndarray de shape (384,) o (1, 384)
    if hasattr(result, 'tolist'):
        result = result.tolist()
    # result es [float, ...] o [[float, ...]]
    if isinstance(result, list) and len(result) > 0:
        if isinstance(result[0], list):
            embedding = result[0]
        else:
            embedding = result
    else:
        raise RuntimeError(f"Unexpected feature_extraction response: {type(result)}")

    if len(embedding) != EMBEDDING_DIM:
        logger.warning("unexpected_embedding_dim: got=%d expected=%d", len(embedding), EMBEDDING_DIM)

    return embedding


def ensure_embeddings(db_path: str) -> int:
    """No-op — los embeddings se generan en pipeline local (Mac)."""
    return 0
