"""Task 1.3 tests: app_doc_journal repo + φ-sequence save engine skeleton.

Contract (WF-5s1, WF-4s2, WF-5s2 — erp-write-foundation spec / ADR-0008-03):
- φ1 journal PENDING row exists BEFORE any legacy insert (journal-first).
- Success flips COMMITTED with the final number (φ4).
- φ3 failure → journal FAILED(error) + compensating cleanup + retryable error.
- Orphan PENDING rows older than the watchdog threshold are healed: marked
  FAILED and the reserved number released, only when no legacy rows exist.

Tests run hermetically against the Fake twin + fake numbering hook; the
InnoDB/real-MySQL contract is exercised at the local checkpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from motoshop_api.erp.engine import (
    ErpSaveRequest,
    ErpSaveFailed,
    heal_stale_pending,
    save_document,
)
from motoshop_api.erp.journal import FakeJournalRepo


class FakeUowEngine:
    """Hermetic UoW engine: never touches MySQL."""

    def __init__(self):
        self.connections: list = []

    def connect(self):
        conn = FakeUowConn()
        self.connections.append(conn)
        return conn

    def dispose(self):
        pass


class FakeUowConn:
    def __init__(self):
        self.executed: list[str] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, statement, params=None):
        self.executed.append(str(statement))
        return f"executed:{statement}"

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


UOW_ENGINE = FakeUowEngine()


TENANT = "motoshop"
EMPRESA = "E01"
ACTOR = "cajero1"
KEY = "0d9e3e56-2f5c-4cdd-8f0a-4b1a0b5e5f01"


def _request(save_fn, numbering=None, cleanup_fn=None):
    if numbering is None:
        state = {"next": 501}

        def _numbering(req):
            n = state["next"]
            state["next"] += 1
            return n

        numbering = _numbering
    return ErpSaveRequest(
        codclas="FV",
        pref="FA",
        doc_type="invoice",
        tenant=TENANT,
        empresa=EMPRESA,
        actor=ACTOR,
        request_id="req-1",
        idempotency_key=KEY,
        save_fn=save_fn,
        numbering_fn=numbering,
        cleanup_fn=cleanup_fn,
        engine=UOW_ENGINE,
    )


# ─── WF-5s1 journal leads the save ─────────────────────────────


def test_journal_row_pending_before_first_legacy_insert():
    journal = FakeJournalRepo()
    seen: dict = {}

    def save_fn(conn, number):
        # observation point: the legacy write sees the journal already PENDING
        seen["status"] = journal.entries[0]["status"]
        seen["entry_count"] = len(journal.entries)
        return {"numfven": number}

    save_document(_request(save_fn), journal=journal)
    assert seen["status"] == "PENDING"
    assert seen["entry_count"] == 1
    entry = journal.entries[0]
    assert entry["status"] == "COMMITTED"
    assert entry["docnum"] == 501


def test_save_returns_result_from_save_fn():
    journal = FakeJournalRepo()

    def save_fn(conn, number):
        return {"numfven": number, "total": "31350.90"}

    result = save_document(_request(save_fn), journal=journal)
    assert result == {"numfven": 501, "total": "31350.90"}
    assert journal.entries[0]["status"] == "COMMITTED"


# ─── WF-4s2 failure path ───────────────────────────────────────


def test_failure_mid_save_marks_failed_and_runs_cleanup():
    journal = FakeJournalRepo()
    cleanup_calls: list[int] = []

    def save_fn(conn, number):
        raise RuntimeError("insert detapago failed")

    with pytest.raises(ErpSaveFailed):
        save_document(
            _request(save_fn, cleanup_fn=cleanup_calls.append), journal=journal
        )
    entry = journal.entries[0]
    assert entry["status"] == "FAILED"
    assert "detapago" in entry["error_msg"]
    assert cleanup_calls == [501]


def test_failure_error_is_retryable():
    journal = FakeJournalRepo()

    def save_fn(conn, number):
        raise ValueError("boom")

    with pytest.raises(ErpSaveFailed) as exc:
        save_document(_request(save_fn), journal=journal)
    assert exc.value.retryable is True
    assert exc.value.docnum == 501


# ─── WF-5s2 orphan heal ────────────────────────────────────────


def test_heal_marks_stale_pending_failed_and_releases_number():
    journal = FakeJournalRepo()
    journal.entries.append(
        {
            "id": 1,
            "codclas": "FV",
            "pref": "FA",
            "docnum": 502,
            "status": "PENDING",
            "tenant": TENANT,
            "empresa": EMPRESA,
            "actor": ACTOR,
            "request_id": "req-orph",
            "error_msg": None,
            "created_at": datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        }
    )
    released: list[int] = []
    now = datetime(2026, 10, 20, 10, 20, tzinfo=timezone.utc)

    healed = heal_stale_pending(
        journal,
        release_fn=released.append,
        stale_after=timedelta(minutes=15),
        has_legacy_rows=lambda number: False,
        now=now,
    )
    assert healed == ["FV/FA/502 ORPHAN"]
    assert journal.entries[0]["status"] == "FAILED"
    assert "watchdog" in journal.entries[0]["error_msg"]
    assert released == [502]


def test_heal_ignores_recent_pending_and_failed_rows():
    journal = FakeJournalRepo()
    recent = datetime(2026, 10, 20, 10, 19, tzinfo=timezone.utc)
    journal.entries.append(
        {
            "id": 1, "codclas": "FV", "pref": "FA", "docnum": 503,
            "status": "PENDING", "tenant": TENANT, "empresa": EMPRESA,
            "actor": ACTOR, "request_id": "req-ok", "error_msg": None,
            "created_at": recent,
        }
    )
    journal.entries.append(
        {
            "id": 2, "codclas": "FV", "pref": "FA", "docnum": 504,
            "status": "FAILED", "tenant": TENANT, "empresa": EMPRESA,
            "actor": ACTOR, "request_id": "req-x", "error_msg": None,
            "created_at": datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
        }
    )
    now = datetime(2026, 10, 20, 10, 20, tzinfo=timezone.utc)
    healed = heal_stale_pending(
        journal,
        release_fn=lambda n: pytest.fail("must not release recent/failed rows"),
        stale_after=timedelta(minutes=15),
        has_legacy_rows=lambda number: False,
        now=now,
    )
    assert healed == []


# ─── Journal repo contract ─────────────────────────────────────


def test_fake_journal_repo_lifecycle_fifo():
    journal = FakeJournalRepo()

    def save_fn(conn, number):
        return {"numfven": number}

    entry = save_document(_request(save_fn), journal=journal)
    assert entry is not None
    stale = journal.list_stale_pending(
        stale_after=timedelta(minutes=1),
        now=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    # committed rows are never stale candidates
    assert stale == []
