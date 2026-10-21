"""app_doc_journal repository: write-ahead intent per document (ADR-0008-03).

The journal MUST be the first write of any document save (φ1), using a
single autocommitted InnoDB insert, so a crash can be detected and healed.

Protocol + Fake (tests) + Real (MySQL via the writer engine, matching the
app_writes pattern for single-row app_* writes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)

from sqlalchemy import insert, update

from motoshop_api.erp.models import app_doc_journal

JOURNAL_STATUSES = ("PENDING", "COMMITTED", "FAILED", "ANNULLED")


@dataclass(frozen=True)
class JournalEntry:
    """Journal envelope (per spec: codclas, pref, docnum, status, tenant, actor, empresa)."""

    id: int | None
    codclas: str
    pref: str
    docnum: int | None
    status: str
    tenant: str
    empresa: str
    actor: str
    request_id: str
    idempotency_key: str | None
    error_msg: str | None
    created_at: datetime | None
    doc_type: str = ""


class JournalRepo(Protocol):
    """Contract shared by FakeJournalRepo and RealJournalRepo."""

    def open_pending(
        self,
        codclas: str,
        pref: str,
        doc_type: str,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> JournalEntry: ...

    def record_number(self, entry_id: int, docnum: int) -> None: ...

    def mark_committed(self, entry_id: int, docnum: int) -> None: ...

    def mark_failed(self, entry_id: int, error_msg: str) -> None: ...

    def mark_annulled(self, entry_id: int, docnum: int) -> None: ...

    def list_document_entries(self, codclas: str, docnum: int) -> list[JournalEntry]: ...

    def list_stale_pending(
        self, stale_after: timedelta, now: datetime
    ) -> list[JournalEntry]: ...


# ─── Fake (memoria para tests) ────────────────────────────────


class FakeJournalRepo:
    """In-memory journal, listed call order preserved."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self._next_id = 1

    def open_pending(
        self,
        codclas: str,
        pref: str,
        doc_type: str,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> JournalEntry:
        record = {
            "id": self._next_id,
            "codclas": codclas,
            "pref": pref,
            "docnum": None,
            "status": "PENDING",
            "doc_type": doc_type,
            "tenant": tenant,
            "empresa": empresa,
            "actor": actor,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "error_msg": None,
            "created_at": datetime.now(UTC),
        }
        self._next_id += 1
        self.entries.append(record)
        return _row_to_entry(record)

    def record_number(self, entry_id: int, docnum: int) -> None:
        self.entries[entry_id - 1]["docnum"] = docnum

    def mark_committed(self, entry_id: int, docnum: int) -> None:
        record = self.entries[entry_id - 1]
        record["status"] = "COMMITTED"
        record["docnum"] = docnum

    def mark_failed(self, entry_id: int, error_msg: str) -> None:
        record = self.entries[entry_id - 1]
        record["status"] = "FAILED"
        record["error_msg"] = error_msg[:500]

    def mark_annulled(self, entry_id: int, docnum: int) -> None:
        record = self.entries[entry_id - 1]
        record["status"] = "ANNULLED"
        record["docnum"] = docnum

    def list_document_entries(self, codclas: str, docnum: int) -> list[JournalEntry]:
        return [
            _row_to_entry(record)
            for record in self.entries
            if record["codclas"] == codclas and record["docnum"] == docnum
        ]

    def list_stale_pending(
        self, stale_after: timedelta, now: datetime
    ) -> list[JournalEntry]:
        out = []
        for record in self.entries:
            if record["status"] != "PENDING":
                continue
            created = record["created_at"]
            age = now - created
            if age >= stale_after:
                out.append(_row_to_entry(record))
        return out


def _row_to_entry(record: dict) -> JournalEntry:
    return JournalEntry(
        id=record["id"],
        codclas=record["codclas"],
        pref=record.get("pref", ""),
        docnum=record.get("docnum"),
        status=record["status"],
        tenant=record["tenant"],
        empresa=record.get("empresa", ""),
        actor=record["actor"],
        request_id=record.get("request_id", ""),
        idempotency_key=record.get("idempotency_key"),
        error_msg=record.get("error_msg"),
        created_at=record.get("created_at"),
        doc_type=record.get("doc_type", ""),
    )


# ─── Real (MySQL InnoDB via the app_writer engine) ────────────


class RealJournalRepo:
    """Single-row autocommitted inserts against app_doc_journal."""

    def __init__(self) -> None:
        from motoshop_api.db.engine import get_writer_engine

        self._engine = get_writer_engine()

    def open_pending(
        self,
        codclas: str,
        pref: str,
        doc_type: str,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> JournalEntry:
        with self._engine.connect() as conn:
            result = conn.execute(
                insert(app_doc_journal).values(
                    codclas=codclas,
                    pref=pref,
                    status="PENDING",
                    doc_type=doc_type,
                    tenant=tenant,
                    empresa=empresa,
                    actor=actor,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                )
            )
            conn.commit()
            new_id = int(result.inserted_primary_key[0])
        return JournalEntry(
            id=new_id, codclas=codclas, pref=pref, docnum=None, status="PENDING",
            tenant=tenant, empresa=empresa, actor=actor, request_id=request_id,
            idempotency_key=idempotency_key, error_msg=None, created_at=None,
            doc_type=doc_type,
        )

    def record_number(self, entry_id: int, docnum: int) -> None:
        self._update(entry_id, status=None, docnum=docnum)

    def mark_committed(self, entry_id: int, docnum: int) -> None:
        self._update(entry_id, status="COMMITTED", docnum=docnum)

    def mark_failed(self, entry_id: int, error_msg: str) -> None:
        self._update(entry_id, status="FAILED", error_msg=error_msg[:500], docnum=None)

    def mark_annulled(self, entry_id: int, docnum: int) -> None:
        self._update(entry_id, status="ANNULLED", docnum=docnum)

    def list_document_entries(self, codclas: str, docnum: int) -> list[JournalEntry]:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, codclas, pref, docnum, status, tenant, empresa, actor, "
                    "request_id, idempotency_key, error_msg, created_at, doc_type "
                    "FROM app_doc_journal WHERE codclas = :c AND docnum = :n "
                    "ORDER BY id"
                ),
                {"c": str(codclas), "n": docnum},
            ).fetchall()
        return [
            JournalEntry(
                id=r[0], codclas=r[1], pref=r[2] or "", docnum=r[3], status=r[4],
                tenant=r[5], empresa=r[6] or "", actor=r[7], request_id=r[8] or "",
                idempotency_key=r[9], error_msg=r[10], created_at=r[11],
                doc_type=r[12] or "",
            )
            for r in rows
        ]

    def list_stale_pending(
        self, stale_after: timedelta, now: datetime
    ) -> list[JournalEntry]:
        horizon = now - stale_after
        from sqlalchemy import text

        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, codclas, pref, docnum, status, tenant, empresa, actor, "
                    "request_id, idempotency_key, error_msg, created_at "
                    "FROM app_doc_journal WHERE status = 'PENDING' "
                    "AND created_at <= :horizon ORDER BY id LIMIT 100"
                ),
                {"horizon": horizon.replace(tzinfo=None)},
            ).fetchall()
        entries = [
            JournalEntry(
                id=r[0], codclas=r[1], pref=r[2] or "", docnum=r[3], status=r[4],
                tenant=r[5], empresa=r[6] or "", actor=r[7], request_id=r[8] or "",
                idempotency_key=r[9], error_msg=r[10], created_at=r[11],
            )
            for r in rows
        ]
        return entries

    def _update(
        self,
        entry_id: int,
        status: str | None,
        docnum: int | None,
        error_msg: str | None = None,
    ) -> None:
        values: dict = {}
        if status is not None:
            values["status"] = status
        if docnum is not None:
            values["docnum"] = docnum
        if error_msg is not None:
            values["error_msg"] = error_msg
        with self._engine.connect() as conn:
            if not values:
                conn.execute(
                    update(app_doc_journal)
                    .where(app_doc_journal.c.id == entry_id)
                    .values(updated_at=datetime.now(UTC).replace(tzinfo=None))
                )
            else:
                values["updated_at"] = datetime.now(UTC).replace(tzinfo=None)
                conn.execute(
                    update(app_doc_journal)
                    .where(app_doc_journal.c.id == entry_id)
                    .values(**values)
                )
            conn.commit()


# ─── Factory ──────────────────────────────────────────────────


def get_journal_repo() -> JournalRepo:
    """Real in prod/dev, Fake under tests (settings.env == 'test')."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealJournalRepo()
    return FakeJournalRepo()
