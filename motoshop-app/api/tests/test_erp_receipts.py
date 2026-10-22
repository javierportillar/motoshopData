"""Task 4.1 tests: receipts against open CxC + ``Graba_Fpago`` duality.

Scenarios (spec erp-collections-cash):
- CC-1s1: a full receipt closes the balance to 0 and the journal COMMITTED.
- CC-1s2: a partial receipt leaves the remaining balance (300 000 → 200 000).
- CC-1s3: an over-payment is rejected 422 with the available balance in the
  detail and NOTHING persists (no payment row, no journal entry).
- CC-1s4: an annulled target (``estfven='A'``) is rejected 409.
- CC-2s1: a standard S01 receipt row carries ``soldeb=40000.0`` / ``solcre=0``.
- CC-2s2: a note-type payment document (tipclas in the solcre set) carries
  ``solcre`` with ``soldeb=0``.

The open balance is the LIVE truth ``SUM(detcuentas.valdeb − valhab)`` on the
cartera accounts (canonical ``13050501`` + legacy alias ``1305``) of the
target document — the receipt's own credit row lands on that document, so the
balance always reflects what was collected. The account set itself is
covered in ``tests/test_erp_cash_cartera.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from motoshop_api.erp.cash.repo import (
    AnnulledDocumentError,
    FakeReceiptsRepo,
    ReceiptOverpaymentError,
    open_balance,
    payment_duality,
)
from motoshop_api.erp.cash.schemas import ReceiptCreate
from motoshop_api.erp.cash.store import FakeCashStore
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError

_BODY = {
    "nitter": "222222222222",
    "numfven": 100,
    "prefven": "FVP",
    "codpag": "01",
    "valor": "150000",
    "fecha": "2025-02-10",
    "codcaj": "01",
    "tipclas": "S01",
    "concepto": "ABONO CARTERA",
}


def _store(balance: str = "150000", *, estfven: str = "B") -> FakeCashStore:
    store = FakeCashStore()
    store.facventas.append(
        {
            "numfven": 100,
            "prefven": "FVP",
            "nitter": "222222222222",
            "estfven": estfven,
            "codclas": "S15",
            "totfven": Decimal(balance),
        }
    )
    store.detcuentas.append(
        {
            "numnum": "100",
            "codclas": "S15",
            "prenum": "FVP",
            "codcue": "1305",
            "valdeb": Decimal(balance),
            "valhab": Decimal("0"),
            "nitter": "222222222222",
            "estcue": "B",
        }
    )
    return store


def _repo(store: FakeCashStore, journal: FakeJournalRepo | None = None):
    journal = journal or FakeJournalRepo()
    repo = FakeReceiptsRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )
    return repo, journal


def _create(repo, body=None, **kwargs):
    payload = {**_BODY, **(body or {})}
    return repo.create(
        ReceiptCreate(**payload),
        tenant="motoshop",
        empresa="E01",
        actor=kwargs.get("actor", "ger1"),
        request_id=kwargs.get("request_id", "r1"),
        idempotency_key=kwargs.get("idempotency_key"),
    )


# ─── CC-1s1: full payment closes the balance ─────────────────────


def test_cc1s1_full_receipt_closes_the_balance_and_commits_the_journal():
    store = _store("150000")
    repo, journal = _repo(store)

    response = _create(repo)

    assert response["saldo_anterior"] == "150000"
    assert response["saldo_actual"] == "0"
    assert response["numero"] == 101  # contadores S01 seeded at 101
    assert response["pref"] == "RC"
    assert [entry["status"] for entry in journal.entries] == ["COMMITTED"]
    assert open_balance(store, 100) == Decimal("0")
    assert len(store.detapago) == 1
    assert store.detapago[0]["numnum"] == "101"
    assert store.detapago[0]["codclas"] == "S01"
    assert store.detapago[0]["estado"] == "B"
    assert store.detapago[0]["valpag"] == Decimal("150000")


def test_cc1s1_receipt_causation_credits_cartera_and_debits_cash():
    store = _store("150000")
    repo, _journal = _repo(store)

    _create(repo)

    cartera = [r for r in store.detcuentas if r["codcue"] == "1305"]
    assert len(cartera) == 1  # the invoice debit (written before the fix)
    assert cartera[0]["valdeb"] == Decimal("150000")
    assert cartera[0]["valhab"] == Decimal("0")

    # the receipt credit lands on the CANONICAL cartera account
    credit = [r for r in store.detcuentas if r["codcue"] == "13050501"]
    assert len(credit) == 1
    assert credit[0]["numnum"] == "100"  # lands on the collected invoice
    assert credit[0]["valhab"] == Decimal("150000")
    assert credit[0]["valdeb"] == Decimal("0")

    cash = [r for r in store.detcuentas if r["codcue"] == "1105"]
    assert len(cash) == 1
    assert cash[0]["valdeb"] == Decimal("150000")
    assert cash[0]["valhab"] == Decimal("0")

    # the causación of the receipt itself balances (the invoice's own debit
    # is not part of the receipt's causación)
    receipt_entries = [r for r in store.detcuentas if "RECIBO" in r.get("detcue", "")]
    assert len(receipt_entries) == 2
    assert sum(r["valdeb"] for r in receipt_entries) == sum(
        r["valhab"] for r in receipt_entries
    )


# ─── CC-1s2: partial payment leaves the balance open ─────────────


def test_cc1s2_partial_receipt_leaves_the_open_balance():
    store = _store("300000")
    repo, _journal = _repo(store)

    response = _create(repo, {"valor": "100000"})

    assert response["saldo_anterior"] == "300000"
    assert response["saldo_actual"] == "200000"
    assert open_balance(store, 100) == Decimal("200000")
    assert len(store.detapago) == 1
    assert store.detapago[0]["valpag"] == Decimal("100000")


# ─── CC-1s3: over-payment rejected ──────────────────────────────


def test_cc1s3_overpayment_is_422_with_the_available_balance_and_persists_nothing():
    store = _store("50000")
    repo, journal = _repo(store)

    with pytest.raises(ReceiptOverpaymentError) as excinfo:
        _create(repo, {"valor": "60000"})

    detail = excinfo.value.detail()
    assert detail["saldo_disponible"] == "50000"
    assert "50000" in detail["fields"]["valor"]
    assert store.detapago == []
    assert journal.entries == []  # nothing was even journalled


def test_cc1s3_non_positive_amount_is_rejected_with_the_aggregate_shape():
    store = _store("150000")
    repo, journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        _create(repo, {"valor": "0"})

    assert "valor" in excinfo.value.detail()["fields"]
    assert store.detapago == []
    assert journal.entries == []


def test_cc1s3_unknown_target_document_is_rejected():
    store = _store("150000")
    repo, _journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        _create(repo, {"numfven": 999})

    assert "numfven" in excinfo.value.detail()["fields"]


# ─── CC-1s4: annulled target rejected ───────────────────────────


def test_cc1s4_annulled_target_is_409_and_persists_nothing():
    store = _store("150000", estfven="A")
    repo, journal = _repo(store)

    with pytest.raises(AnnulledDocumentError) as excinfo:
        _create(repo)

    assert excinfo.value.detail()["code"] == "document_annulled"
    assert store.detapago == []
    assert journal.entries == []


# ─── CC-2: formapago duality (Graba_Fpago) ──────────────────────


def test_cc2s1_standard_receipt_row_carries_soldeb_only():
    store = _store("150000")
    repo, _journal = _repo(store)

    _create(repo, {"valor": "40000"})

    row = store.detapago[0]
    assert row["soldeb"] == Decimal("40000.0")
    assert row["solcre"] == Decimal("0")


def test_cc2s2_note_type_payment_document_carries_solcre_only():
    store = _store("150000")
    repo, _journal = _repo(store)

    _create(repo, {"valor": "40000", "tipclas": "S14"})

    row = store.detapago[0]
    assert row["solcre"] == Decimal("40000.0")
    assert row["soldeb"] == Decimal("0")


def test_cc2_duality_helper_maps_the_legacy_tipclas_sets():
    assert payment_duality("S01", Decimal("10")) == (Decimal("10"), Decimal("0"))
    assert payment_duality("S02", Decimal("10")) == (Decimal("10"), Decimal("0"))
    assert payment_duality("S14", Decimal("10")) == (Decimal("0"), Decimal("10"))
    assert payment_duality("S21", Decimal("10")) == (Decimal("0"), Decimal("10"))


def test_cc2_unknown_payment_class_is_rejected():
    store = _store("150000")
    repo, _journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        _create(repo, {"tipclas": "S99"})

    assert "tipclas" in excinfo.value.detail()["fields"]


# ─── idempotent replay (WF-8s1 contract reused) ──────────────────


def test_receipt_replay_under_the_same_key_does_not_write_twice():
    store = _store("150000")
    repo, journal = _repo(store)

    first = _create(repo, idempotency_key="8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6")
    second = _create(repo, idempotency_key="8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6")

    assert first == second
    assert len(store.detapago) == 1
    assert len([e for e in journal.entries if e["status"] == "COMMITTED"]) == 1
