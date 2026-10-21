"""Task 2.1 tests: terceros repo + legacy validity parity (erp-masters-write).

Scenarios (erp-masters-write):
- MW-1s1: create with one email → `terceros` + `tercecorreo` rows, journal
  PENDING → COMMITTED (masters writes journal per design ADR-0008-03).
- MW-1s2: duplicate `nitter` → 409 with the field identified; zero table
  writes AND zero journal rows (validation happens before φ1).
- MW-1s3: verification-digit checksum failure → 422 with the offending field
  named (aggregate), record set unchanged.
- φ3 failure semantics for masters: injected save failure → journal FAILED,
  legacy rows compensated, ErpSaveFailed (retryable) to the caller.
- Idempotent replay for masters (F5-001 / WF-8 convention at φ0).

The Fake twins mirror the legacy contract: single transaction = one staged
batch applied on commit; a simulated failure between inserts mimics MyISAM
roles landing before the compensating path (engine φ3 → cleanup_fn).
"""

from __future__ import annotations

import pytest

from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.repo import (
    FakeMastersStore,
    FakeTercerosRepo,
    get_terceros_repo,
)
from motoshop_api.erp.masters.schemas import TerceroCreate, TerceroUpdate
from motoshop_api.erp.masters.validators import (
    DuplicateMasterError,
    LegacyValidationError,
    nit_verification_digit,
)

_IDEM_KEY = "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"


def _body(**overrides) -> TerceroCreate:
    values = {
        "nitter": "900123456",
        "tipnit": "N",
        "digter": "8",
        "perjur": "S",
        "apeter": "Garcés",
        "nomter": "Andrés",
        "dirter": "Cra 5 #20-10",
        "telter": "3012345678",
        "emails": ["aj@example.com"],
    }
    values.update(overrides)
    return TerceroCreate(**values)


def _repo(store: FakeMastersStore, journal: FakeJournalRepo | None = None):
    return FakeTercerosRepo(
        store=store,
        journal=journal or FakeJournalRepo(),
        idempotency=FakeIdempotencyRepo(),
    )


def _save_kwargs() -> dict:
    return {
        "tenant": "motoshop",
        "empresa": "E01",
        "actor": "gerente1",
        "request_id": "r-1",
        "idempotency_key": _IDEM_KEY,
    }


# ─── MW-1s3 helpers: the documented verification-digit rules ────


def test_verification_digit_mod11_parity():
    """CheckSum DV = 11 − (Σ digit×weight mod 11), 0/1 remainder maps to 0/1."""
    assert nit_verification_digit("900123456") == "8"
    assert nit_verification_digit("4") == "1"  # Σ=12 → rem 1 → DV 1
    assert nit_verification_digit("0") == "0"  # Σ=0 → rem 0 → DV 0


# ─── MW-1s1: create happy path ─────────────────────────────────


def test_create_tercero_writes_terceros_and_tercecorreo_committed():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    repo = _repo(store, journal)

    response = repo.create(_body(), **_save_kwargs())

    assert store.terceros["900123456"]["nomcom"] == "Andrés Garcés"
    assert store.terceros["900123456"]["tipnit"] == "N"
    assert store.terceros["900123456"]["cupblo"] == "R"
    emails = [e for e in store.tercecorreo if e["nitter"] == "900123456"]
    assert emails == [{"nitter": "900123456", "corele": "aj@example.com"}]
    assert response["nitter"] == "900123456"
    assert response["emails"] == ["aj@example.com"]
    # Masters writes journal PENDING → COMMITTED (no contadores numbering)
    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry["status"] == "COMMITTED"
    assert entry["doc_type"] == "tercero"
    assert entry["tenant"] == "motoshop"
    assert entry["empresa"] == "E01"
    assert entry["actor"] == "gerente1"


def test_create_tercero_accepts_razsoc_juridica_and_dv_zero():
    """Triangulation: juridical person + NIT whose DV remainder is 0."""
    nit = "0" * 9  # Σ digits × weights = 0 → DV '0'
    store = FakeMastersStore()
    repo = _repo(store)
    body = _body(
        nitter=nit, digter="0", perjur="S", razsoc="Distribuidora Andina SA",
        nomcom=None, apeter=None, nomter=None,
    )
    repo.create(body, **_save_kwargs())
    assert store.terceros[nit]["nomcom"] == "Distribuidora Andina SA"


# ─── MW-1s2: duplicate identification ──────────────────────────


def test_duplicate_nitter_rejected_field_identified_zero_writes():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    store.terceros["900123456"] = {"nitter": "900123456", "nomcom": "Existente"}
    repo = _repo(store, journal)

    with pytest.raises(DuplicateMasterError) as exc:
        repo.create(_body(), **_save_kwargs())

    assert exc.value.field == "nitter"
    # Zero rows AND zero journal rows: the reject happens before φ1
    assert store.tercecorreo == []
    assert journal.entries == []


# ─── MW-1s3: verification checksum failure ─────────────────────


def test_verification_digit_checksum_failure_422_aggregate():
    store = FakeMastersStore()
    repo = _repo(store)
    body = _body(digter="7")  # expected DV for 900123456 is "8"

    with pytest.raises(LegacyValidationError) as exc:
        repo.create(body, **_save_kwargs())

    assert "digter" in exc.value.fields
    assert "8" in exc.value.fields["digter"]  # names the expected digit
    assert store.terceros == {}


def test_missing_required_fields_aggregate_not_first_fail():
    """Legacy parity: all offending required fields listed at once."""
    store = FakeMastersStore()
    repo = _repo(store)
    body = _body(dirter="", telter="", apeter="", nomter="")

    with pytest.raises(LegacyValidationError) as exc:
        repo.create(body, **_save_kwargs())

    assert set(exc.value.fields) >= {"dirter", "telter", "nomter"}


# ─── φ3 failure semantics (journal FAILED + compensation) ──────


def test_save_failure_marks_journal_failed_and_compensates_rows():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    store.fail_table = "tercecorreo"  # simulated insert failure mid-save
    repo = _repo(store, journal)

    with pytest.raises(ErpSaveFailed) as exc:
        repo.create(_body(), **_save_kwargs())

    assert exc.value.retryable is True
    # MyISAM-style partial row was compensated: record set back to zero
    assert store.terceros == {}
    assert store.tercecorreo == []
    assert [e["status"] for e in journal.entries] == ["FAILED"]


# ─── Idempotent replay (F5-001 at φ0) ──────────────────────────


def test_idempotent_replay_returns_stored_response_without_new_rows():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    repo = _repo(store, journal)
    first = repo.create(_body(), **_save_kwargs())

    replay = repo.create(_body(emails=[]), **_save_kwargs())

    assert replay == first
    assert len(store.tercecorreo) == 1  # no second email row
    assert len(journal.entries) == 1


# ─── Edit path: partial update keeps identity ──────────────────


def test_edit_tercero_updates_fields_and_replaces_emails():
    store = FakeMastersStore()
    repo = _repo(store)
    created = repo.create(_body(), **_save_kwargs())
    update = TerceroUpdate(
        dirter="Av Siempre Viva 742", telter="3199998888", emails=["nuevo@example.com"]
    )

    updated = repo.update("900123456", update, tenant="motoshop", empresa="E01",
                          actor="gerente1", request_id="r-2")

    assert store.terceros["900123456"]["dirter"] == "Av Siempre Viva 742"
    assert store.terceros["900123456"]["telter"] == "3199998888"
    assert store.terceros["900123456"]["nomter"] == "Andrés"  # untouched fields kept
    emails = [e for e in store.tercecorreo if e["nitter"] == "900123456"]
    assert emails == [{"nitter": "900123456", "corele": "nuevo@example.com"}]
    assert updated["emails"] == ["nuevo@example.com"]
    assert created["nitter"] == "900123456"


def test_get_returns_none_for_missing_tercero():
    repo = _repo(FakeMastersStore())
    assert repo.get("000000000") is None


# ─── Factory wiring ────────────────────────────────────────────


def test_get_terceros_repo_returns_fake_under_test_env():
    assert isinstance(get_terceros_repo(), FakeTercerosRepo)
