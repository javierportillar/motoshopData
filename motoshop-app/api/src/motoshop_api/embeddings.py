"""Embeddings vía Hugging Face Inference API (HTTP, 0 modelos en RAM).

Pipeline local (en Mac del PO):
    pipeline/embeddings_skus.py  →  sentence-transformers  →  DuckDB embeddings

Runtime (en Render, sin ML):
    _get_query_embedding()  →  httpx POST a HF Inference API  →  vector[384]
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
# NOTA: api-inference.huggingface.co ya no existe (NXDOMAIN).
# El endpoint correcto es router.huggingface.co/hf-inference/models/{model_id}
HF_MODEL_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


def _get_query_embedding(text: str) -> list[float]:
    """Embedding de UNA query via Hugging Face Inference API.

    Requiere HF_API_TOKEN en entorno (free tier, ~1000 req/mes).
    """
    token = os.environ.get("HF_API_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    logger.info("hf_api_call: token_set=%s model=%s", bool(token), HF_MODEL_URL.split("/")[-1])

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                HF_MODEL_URL,
                json={"inputs": text, "options": {"wait_for_model": True}},
                headers=headers,
            )
    except Exception as exc:
        logger.error("hf_api_connection_failed: %s", exc)
        raise RuntimeError(f"HuggingFace API connection failed: {exc}") from exc

    if resp.status_code != 200:
        logger.warning("hf_api_error: status=%s body=%s", resp.status_code, resp.text[:200])
        raise RuntimeError(f"HuggingFace API returned {resp.status_code}")

    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"HuggingFace API error: {data['error']}")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Unexpected HF API response: {type(data).__name__}")

    embedding = data[0]  # primer (y único) elemento = vector[384]
    if not isinstance(embedding, list) or len(embedding) != EMBEDDING_DIM:
        raise RuntimeError(f"Unexpected embedding dim: got {len(embedding)} expected {EMBEDDING_DIM}")

    return embedding


def ensure_embeddings(db_path: str) -> int:
    """No-op — los embeddings se generan en pipeline local (Mac)."""
    return 0
