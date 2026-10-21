"""Task 1.4 tests: idempotency convention for document saves (WF-8s1, WF-8s2).

Contract:
- Same UUIDv4 Idempotency-Key replays the stored response: identical payload,
  contadores NOT advanced again, exactly one document/journal row.
- A new key under the same payload reserves a new number and creates a new
  document (this is what makes retries safe but edits fresh).
"""

from __future__ import annotations

import pytest

from motoshop_api.erp.engine import save_document, ErpSaveRequest
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from tests.test_erp_journal import UOW_ENGINE


TENANT = "motoshop"
EMPRESA = "E01"
KEY_A = "c1a55f9e-6c2c-4ab0-8ec7-b4d7db3e0a11"
KEY_B = "c1a55f9e-6c2c-4ab0-8ec7-b4d7db3e0a12"


def _numbering_factory():
    state = {"next": 700, "calls": 0}

    def numbering(req):
        state["calls"] += 1
        n = state["next"]
        state["next"] += 1
        return n

    return state, numbering


def _request(key, save_fn=None, numbering=None):
    if save_fn is None:

        def save_fn(conn, number):
            return {"numfven": number, "pref": "FA"}

    return ErpSaveRequest(
        codclas="FV",
        pref="FA",
        doc_type="invoice",
        tenant=TENANT,
        empresa=EMPRESA,
        actor="cajero1",
        request_id="req-1",
        idempotency_key=key,
        save_fn=save_fn,
        numbering_fn=numbering,
        engine=UOW_ENGINE,
    )


# ─── WF-8s1 replay does not double-charge ──────────────────────


def test_replay_same_key_returns_stored_response_without_new_number():
    journal = FakeJournalRepo()
    idem = FakeIdempotencyRepo()
    state, numbering = _numbering_factory()

    first = save_document(_request(KEY_A, numbering=numbering), journal, idem)
    first_counter = state["calls"]
    second = save_document(_request(KEY_A, numbering=numbering), journal, idem)

    assert first == second == {"numfven": 700, "pref": "FA"}
    assert state["calls"] == first_counter == 1  # contadores advanced once
    committed = [e for e in journal.entries if e["status"] == "COMMITTED"]
    assert len(committed) == 1  # exactly one document


def test_replay_short_circuits_before_phi1_journal():
    journal = FakeJournalRepo()
    idem = FakeIdempotencyRepo()
    state, numbering = _numbering_factory()

    save_document(_request(KEY_A, numbering=numbering), journal, idem)
    journal.entries.clear()
    save_document(_request(KEY_A, numbering=numbering), journal, idem)

    assert journal.entries == []  # no new journal row on replay


# ─── WF-8s2 different key means a new document ─────────────────


def test_new_key_reserves_new_number_and_new_document():
    journal = FakeJournalRepo()
    idem = FakeIdempotencyRepo()
    state, numbering = _numbering_factory()

    first = save_document(_request(KEY_A, numbering=numbering), journal, idem)
    second = save_document(_request(KEY_B, numbering=numbering), journal, idem)

    assert first["numfven"] == 700
    assert second["numfven"] == 701
    assert state["calls"] == 2
    committed = [e for e in journal.entries if e["status"] == "COMMITTED"]
    assert len(committed) == 2


# ─── Repo contract ─────────────────────────────────────────────


def test_fake_idempotency_store_roundtrip():
    idem = FakeIdempotencyRepo()
    assert idem.get(KEY_A) is None
    idem.store(KEY_A, doc_type="invoice", tenant="motoshop", actor="c1",
               request_id="req-1", response={"numfven": 700})
    assert idem.get(KEY_A) == {"numfven": 700}
    # upsert per key: re-store replaces, get returns the latest snapshot
    idem.store(KEY_A, doc_type="invoice", tenant="motoshop", actor="c1",
               request_id="req-2", response={"numfven": 700, "warnings": []})
    assert idem.get(KEY_A) == {"numfven": 700, "warnings": []}
