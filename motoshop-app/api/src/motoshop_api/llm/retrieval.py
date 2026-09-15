"""Recuperación híbrida tenant-scoped para conocimiento no estructurado.

Los datos transaccionales siguen viniendo de tools DuckDB. Este módulo sólo
consulta chunks documentales indexados en Supabase (pgvector + FTS).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import httpx

from motoshop_api.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def __init__(self) -> None:
        self.base = (
            settings.embedding_api_base or os.environ.get("EMBEDDING_API_BASE", "")
        ).rstrip("/")
        self.key = settings.embedding_api_key or os.environ.get("EMBEDDING_API_KEY", "")
        self.model = settings.embedding_model or os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-3-small"
        )
        self._http = httpx.Client(timeout=httpx.Timeout(15.0))

    def embed(self, text: str) -> list[float] | None:
        if not self.base or not self.key:
            return None
        try:
            response = self._http.post(
                f"{self.base}/embeddings",
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            vector = data.get("data", [{}])[0].get("embedding")
            return vector if isinstance(vector, list) else None
        except Exception:
            logger.warning("embedding_request_failed", exc_info=True)
            return None


class HybridRetriever:
    def __init__(self) -> None:
        self._embedding = EmbeddingClient()
        self._http = httpx.Client(timeout=httpx.Timeout(8.0))

    @property
    def available(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_key)

    def _headers(self) -> dict[str, str]:
        key = settings.supabase_service_key
        return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _rpc(self, name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._http.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/{name}",
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def search(self, tenant_id: str, query: str, limit: int = 5) -> dict[str, Any]:
        if not query.strip() or not self.available:
            return {"results": [], "sources": [], "status": "unavailable"}
        limit = max(1, min(limit, 20))
        rows: list[dict[str, Any]] = []
        vector = self._embedding.embed(query)
        try:
            if vector:
                rows.extend(
                    self._rpc(
                        "match_rag_chunks",
                        {
                            "p_tenant_id": tenant_id,
                            "p_query_embedding": vector,
                            "p_match_count": limit,
                        },
                    )
                )
            rows.extend(
                self._rpc(
                    "search_rag_chunks",
                    {
                        "p_tenant_id": tenant_id,
                        "p_query": query,
                        "p_match_count": limit,
                    },
                )
            )
        except Exception:
            logger.warning("rag_retrieval_failed tenant=%s", tenant_id, exc_info=True)
            return {"results": [], "sources": [], "status": "unavailable"}

        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("id") or hashlib.sha1(str(row).encode()).hexdigest())
            item = {
                "id": key,
                "content": str(row.get("content") or ""),
                "source": str(
                    row.get("source") or row.get("document_title") or "Documento interno"
                ),
                "section": row.get("section") or row.get("metadata", {}).get("section"),
                "score": float(row.get("similarity") or row.get("rank") or row.get("score") or 0),
            }
            previous = merged.get(key)
            if previous is None or item["score"] > previous["score"]:
                merged[key] = item
        result = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:limit]
        return {
            "results": result,
            "sources": [
                {"source": item["source"], "section": item["section"], "score": item["score"]}
                for item in result
            ],
            "status": "ok",
        }


_retriever: HybridRetriever | None = None


def get_hybrid_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
