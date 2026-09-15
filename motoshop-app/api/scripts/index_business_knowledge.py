#!/usr/bin/env python3
"""Index Markdown/TXT documents per tenant into Supabase pgvector + FTS.

Usage:
  python scripts/index_business_knowledge.py --tenant motoshop --source-dir docs/knowledge
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import httpx

from motoshop_api.config import settings

EMBEDDING_DIMENSIONS = 1536


def chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []
    step = max(size - overlap, 1)
    return [normalized[index : index + size] for index in range(0, len(normalized), step)]


def embed(client: httpx.Client, content: str) -> list[float] | None:
    if not settings.embedding_api_base or not settings.embedding_api_key:
        return None
    response = client.post(
        f"{settings.embedding_api_base.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        json={"model": settings.embedding_model, "input": content},
    )
    response.raise_for_status()
    vector = response.json()["data"][0]["embedding"]
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            f"El modelo devolvió {len(vector)} dimensiones; se requieren {EMBEDDING_DIMENSIONS}"
        )
    return vector


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, choices=("motoshop", "masvital"))
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.source_dir.is_dir():
        raise SystemExit(f"No existe el directorio: {args.source_dir}")
    if not settings.supabase_url or not settings.supabase_service_key:
        raise SystemExit("SUPABASE_URL y SUPABASE_SERVICE_KEY son obligatorios")

    base = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_key
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30) as client:
        for path in sorted(args.source_dir.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            raw = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(raw.encode()).hexdigest()
            source = path.relative_to(args.source_dir).as_posix()
            existing = client.get(
                f"{base}/rest/v1/rag_documents",
                headers=headers,
                params={
                    "tenant_id": f"eq.{args.tenant}",
                    "source": f"eq.{source}",
                    "select": "id,checksum",
                },
            )
            existing.raise_for_status()
            existing_rows = existing.json()
            if existing_rows and existing_rows[0]["checksum"] == checksum:
                continue

            # Build every embedding before replacing the active document chunks.
            # A provider failure therefore leaves the previous index untouched.
            prepared: list[dict[str, Any]] = []
            for index, content in enumerate(chunks(raw)):
                prepared.append(
                    {
                        "tenant_id": args.tenant,
                        "content": content,
                        "chunk_index": index,
                        "embedding": embed(client, content),
                        "metadata": {"section": path.stem},
                    }
                )

            if existing_rows:
                document_id = existing_rows[0]["id"]
                updated = client.patch(
                    f"{base}/rest/v1/rag_documents",
                    headers=headers,
                    params={"id": f"eq.{document_id}", "tenant_id": f"eq.{args.tenant}"},
                    json={"title": path.stem, "checksum": checksum},
                )
                updated.raise_for_status()
                deleted = client.delete(
                    f"{base}/rest/v1/rag_chunks",
                    headers=headers,
                    params={"document_id": f"eq.{document_id}", "tenant_id": f"eq.{args.tenant}"},
                )
                deleted.raise_for_status()
            else:
                document = client.post(
                    f"{base}/rest/v1/rag_documents",
                    headers={**headers, "Prefer": "return=representation"},
                    json={
                        "tenant_id": args.tenant,
                        "source": source,
                        "title": path.stem,
                        "checksum": checksum,
                    },
                )
                document.raise_for_status()
                document_id = document.json()[0]["id"]

            for row in prepared:
                row["document_id"] = document_id
            for offset in range(0, len(prepared), 100):
                inserted = client.post(
                    f"{base}/rest/v1/rag_chunks",
                    headers=headers,
                    json=prepared[offset : offset + 100],
                )
                inserted.raise_for_status()
            print(f"indexed {source} ({len(prepared)} chunks)")


if __name__ == "__main__":
    main()
