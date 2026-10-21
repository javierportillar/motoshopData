"""Idempotency convention repo for document saves (F8-002 / F5-001 pattern).

Document-saving write endpoints accept a UUIDv4 ``Idempotency-Key``. The
first successful save stores the response snapshot under the key; repeats
short-circuit at φ0 and replay the stored response without reserving a new
document number or duplicating rows (spec WF-8s1/WF-8s2).
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class IdempotencyRepo(Protocol):
    """Contract shared by FakeIdempotencyRepo and RealIdempotencyRepo."""

    def get(self, idempotency_key: str) -> dict | None: ...

    def store(
        self,
        idempotency_key: str,
        *,
        doc_type: str,
        tenant: str,
        actor: str,
        request_id: str,
        response: dict,
    ) -> None: ...


# ─── Fake (memoria para tests) ────────────────────────────────


class FakeIdempotencyRepo:
    """In-memory store keyed by the UUIDv4 idempotency key."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._meta: dict[str, dict] = {}

    def get(self, idempotency_key: str) -> dict | None:
        row = self._rows.get(idempotency_key)
        return dict(row) if row is not None else None

    def store(
        self,
        idempotency_key: str,
        *,
        doc_type: str,
        tenant: str,
        actor: str,
        request_id: str,
        response: dict,
    ) -> None:
        self._rows[idempotency_key] = dict(response)
        self._meta[idempotency_key] = {
            "doc_type": doc_type,
            "tenant": tenant,
            "actor": actor,
            "request_id": request_id,
        }

    def _clear(self) -> None:
        self._rows.clear()
        self._meta.clear()


# ─── Real (MySQL InnoDB via the app_writer engine) ────────────


class RealIdempotencyRepo:
    """app_idempotency CRUD with the unique-key upsert convention."""

    def __init__(self) -> None:
        from motoshop_api.db.engine import get_writer_engine

        self._engine = get_writer_engine()

    def get(self, idempotency_key: str) -> dict | None:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT response_json FROM app_idempotency "
                    "WHERE idempotency_key = :key"
                ),
                {"key": idempotency_key},
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return json.loads(row[0])

    def store(
        self,
        idempotency_key: str,
        *,
        doc_type: str,
        tenant: str,
        actor: str,
        request_id: str,
        response: dict,
    ) -> None:
        from sqlalchemy import insert
        from sqlalchemy.exc import IntegrityError

        from motoshop_api.erp.models import app_idempotency

        payload = json.dumps(response, default=str)
        try:
            with self._engine.connect() as conn:
                conn.execute(
                    insert(app_idempotency).values(
                        idempotency_key=idempotency_key,
                        doc_type=doc_type,
                        tenant=tenant,
                        actor=actor,
                        request_id=request_id,
                        response_json=payload,
                    )
                )
                conn.commit()
        except IntegrityError:
            # Unique-key collision: an earlier request already stored a
            # response under this key. Never overwrite it — the φ0 replay is
            # the authoritative snapshot (do-not-double-charge contract).
            logger.info(
                "idempotency_key_already_stored key=%s (keeping original response)",
                idempotency_key,
            )


# ─── Factory ──────────────────────────────────────────────────


def get_idempotency_repo() -> IdempotencyRepo:
    """Real in prod/dev, Fake under tests (settings.env == 'test')."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealIdempotencyRepo()
    return FakeIdempotencyRepo()
