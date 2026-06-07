"""Embeddings vía HuggingFace Inference API (sin modelo local).

Para generación batch de 6K productos → pipeline/embeddings_skus.py (usa fastembed local).
Para query en tiempo real → HTTP POST a HuggingFace Inference API (gratis, ~200ms, 0 RAM).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_HF_MODEL_URL = (
    "https://api-inference.huggingface.co/pipeline/feature-extraction/"
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


def _get_query_embedding(text: str) -> list[float]:
    """Genera embedding para UNA query vía HuggingFace Inference API.

    No carga modelos en RAM. Hace HTTP POST al API gratuita de HuggingFace.
    Útil para buscar productos en tiempo real usando embeddings ya almacenados.
    """
    import requests as _req

    resp = _req.post(
        _HF_MODEL_URL,
        json={"inputs": text, "options": {"wait_for_model": True}},
        timeout=30,
    )
    if resp.status_code != 200:
        logger.warning("hf_api_error: status=%s body=%s", resp.status_code, resp.text[:200])
        raise RuntimeError(f"HuggingFace API returned {resp.status_code}")

    data = resp.json()
    # La API devuelve [[float, ...]] o {error: ...}
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"HuggingFace API error: {data['error']}")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Unexpected HF API response shape: {type(data).__name__}")

    embedding = data[0]  # primer (y único) elemento = embedding vec
    if not isinstance(embedding, list) or len(embedding) != EMBEDDING_DIM:
        raise RuntimeError(f"Unexpected embedding dim: got {len(embedding)} expected {EMBEDDING_DIM}")

    return embedding


def ensure_embeddings(db_path: str) -> int:
    """No-op en producción. Los embeddings se generan en el pipeline local."""
    return 0
