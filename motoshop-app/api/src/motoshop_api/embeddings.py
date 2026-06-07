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

    No carga modelos en RAM. Usa urllib.request (stdlib, sin pip extra).
    """
    import json as _json
    import urllib.request as _req
    import urllib.error as _err

    body = _json.dumps({"inputs": text, "options": {"wait_for_model": True}}).encode()
    try:
        resp = _req.urlopen(
            _HF_MODEL_URL,
            data=body,
            timeout=60,
        )
        data = _json.loads(resp.read().decode())
    except _err.HTTPError as e:
        body = e.read().decode()
        logger.warning("hf_api_http_error: status=%s body=%s", e.code, body[:200])
        raise RuntimeError(f"HuggingFace API returned {e.code}: {body[:100]}")
    except OSError as e:
        raise RuntimeError(f"HuggingFace API connection failed: {e}")

    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"HuggingFace API error: {data['error']}")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Unexpected HF API response: {type(data).__name__}")

    embedding = data[0]
    if not isinstance(embedding, list) or len(embedding) != EMBEDDING_DIM:
        raise RuntimeError(f"Unexpected embedding dim: got {len(embedding)} expected {EMBEDDING_DIM}")

    return embedding


def ensure_embeddings(db_path: str) -> int:
    """No-op en producción. Los embeddings se generan en el pipeline local."""
    return 0
