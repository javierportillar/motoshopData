"""ERP save engine: the fixed φ0..φ4 sequence (ADR-0008-03).

    φ0  Idempotency precheck (playback short-circuits before numbering)
    φ1  journal INSERT PENDING (InnoDB, autocommit)       ← first write
    φ2  numbering hook (reserved number recorded on the journal row)
    φ3  unit: legacy document rows inside `erp_write_uow` (fixed order)
    φ4  journal PENDING → COMMITTED; response stored for idempotent replay

Failure paths:
- φ3 raises → journal FAILED(error), compensating cleanup runs *after* the
  failed unit in a fresh autocommitted unit (MyISAM rows cannot roll back),
  and `ErpSaveFailed` (retryable 503 contract) is raised to the caller.
- Orphan PENDING rows are healed by `heal_stale_pending` (watchdog +
  on-startup; the number is released for reuse, spec WF-5s2).

This module owns the *sequence*; concrete documents (numbering, legacy
inserts, cleanup) are injected as callables per slice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from motoshop_api.erp.uow import erp_write_uow

logger = logging.getLogger(__name__)


class ErpSaveFailed(Exception):
    """Retryable document-save failure (maps to 503 at the router layer)."""

    def __init__(self, message: str, docnum: int | None = None, retryable: bool = True):
        super().__init__(message)
        self.docnum = docnum
        self.retryable = retryable


@dataclass(frozen=True)
class ErpSaveRequest:
    """Envelope of one document save (journal + idempotency + unit hooks)."""

    codclas: str
    pref: str
    doc_type: str
    tenant: str
    empresa: str
    actor: str
    request_id: str
    idempotency_key: str
    save_fn: Callable[[object, int], Any]           # (conn, reserved number) → response
    numbering_fn: Callable[["ErpSaveRequest"], int]  # φ2 hook: reserve the number
    cleanup_fn: Callable[[int], None] | None = None  # φ3 failure compensation
    engine: object | None = None                     # UoW engine override (tests)


def save_document(request: ErpSaveRequest, journal: Any, idempotency: Any = None) -> Any:
    """Run the φ0..φ4 sequence; return the save_fn response.

    `journal` is a JournalRepo (Fake or Real). `idempotency`, when provided,
    is an IdempotencyRepo and φ0 replays the stored response for a repeated
    key (spec WF-8s1: no new number, no second document).
    """
    # φ0 idempotency precheck
    if idempotency is not None:
        stored = idempotency.get(request.idempotency_key)
        if stored is not None:
            return stored

    # φ1 journal-first: PENDING before numbering or any legacy insert
    entry = journal.open_pending(
        codclas=request.codclas,
        pref=request.pref,
        doc_type=request.doc_type,
        tenant=request.tenant,
        empresa=request.empresa,
        actor=request.actor,
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
    )

    # φ2 numbering hook (slice 3 plugs the contadores LOCK TABLES engine in)
    number = request.numbering_fn(request)
    journal.record_number(entry.id, number)

    # φ3 unit: legacy writes inside one transaction
    try:
        with erp_write_uow(request.engine) as conn:
            response = request.save_fn(conn, number)
    except Exception as exc:
        detail = f"φ3 unit failed: {type(exc).__name__}: {exc}"
        logger.warning(
            "erp_save_failed codclas=%s pref=%s number=%s error=%s",
            request.codclas, request.pref, number, detail,
        )
        journal.mark_failed(entry.id, detail)
        if request.cleanup_fn is not None:
            request.cleanup_fn(number)
        raise ErpSaveFailed(detail, docnum=number, retryable=True) from exc

    # φ4 journal COMMITTED with the final number; store for replay
    journal.mark_committed(entry.id, number)
    if idempotency is not None:
        idempotency.store(
            request.idempotency_key,
            doc_type=request.doc_type,
            tenant=request.tenant,
            actor=request.actor,
            request_id=request.request_id,
            response=response,
        )
    return response


def heal_stale_pending(
    journal: Any,
    release_fn: Callable[[int], None],
    stale_after: timedelta,
    has_legacy_rows: Callable[[int], bool],
    now: datetime | None = None,
) -> list[str]:
    """Watchdog heal: stale PENDING rows with zero legacy rows → FAILED + released.

    Returns the healed document keys ("codclas/pref/docnum REASON"). Rows that
    DO have legacy rows are NOT auto-failed here: they need the nightly
    consistency check (doc totals vs detcuentas, exiprod audit) and are only
    listed by the caller.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    healed: list[str] = []
    for entry in journal.list_stale_pending(stale_after=stale_after, now=now):
        if entry.docnum is not None and has_legacy_rows(entry.docnum):
            logger.info(
                "heal_skip has_legacy_rows codclas=%s pref=%s number=%s",
                entry.codclas, entry.pref, entry.docnum,
            )
            continue
        journal.mark_failed(
            entry.id, "watchdog: orphan PENDING beyond threshold, number released"
        )
        if entry.docnum is not None:
            release_fn(entry.docnum)
        healed.append(f"{entry.codclas}/{entry.pref}/{entry.docnum} ORPHAN")
    return healed
