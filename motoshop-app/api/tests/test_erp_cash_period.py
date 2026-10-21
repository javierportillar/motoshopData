"""Task 4.2 tests: period lock (``Hay_Cie_Eli``) at creation — CC-6.

Scenario (spec erp-collections-cash):
- CC-6: a cash document dated inside a closed accounting period
  (``cierresper`` rows of type P/M/A) is rejected at creation time with 409
  and NO ledger row is written.

The guard is shared: slice 5 (annulment) will consume the same
``hay_cie_eli`` truth, so the rules are pinned here — the closure types
(P/M/A), the date range and the optional ``codclas``/``numaju`` scope.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from motoshop_api.erp.cash.repo import FakeReceiptsRepo
from motoshop_api.erp.cash.schemas import ReceiptCreate
from motoshop_api.erp.cash.store import FakeCashStore
from motoshop_api.erp.guards import PeriodLockedError, hay_cie_eli
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo

_BODY = {
    "nitter": "222222222222",
    "numfven": 100,
    "prefven": "FVP",
    "codpag": "01",
    "valor": "150000",
    "fecha": "2025-02-10",
    "codcaj": "01",
    "tipclas": "S01",
}


def _store(balance: str = "150000") -> FakeCashStore:
    store = FakeCashStore()
    store.facventas.append(
        {
            "numfven": 100,
            "prefven": "FVP",
            "nitter": "222222222222",
            "estfven": "B",
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


def _closure(tipcie: str = "P") -> dict:
    return {
        "codcie": 1,
        "fecdes": date(2025, 1, 1),
        "fechas": date(2025, 1, 31),
        "tipcie": tipcie,
        "numaju": "",
        "codclas": "",
    }


# ─── CC-6: backdated receipt into a closed period is rejected ────


def test_cc6_receipt_dated_inside_a_closed_period_is_rejected_and_writes_nothing():
    store = _store()
    store.cierresper.append(_closure("P"))
    journal = FakeJournalRepo()
    repo = FakeReceiptsRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )

    with pytest.raises(PeriodLockedError) as excinfo:
        repo.create(
            ReceiptCreate(**{**_BODY, "fecha": "2025-01-15"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    detail = excinfo.value.detail()
    assert detail["code"] == "period_locked"
    assert detail["period"]["tipcie"] == "P"
    assert store.detapago == []  # no ledger row
    assert store.detcuentas == store.detcuentas[:1]  # only the seeded invoice row
    assert journal.entries == []  # nothing was even journalled


@pytest.mark.parametrize("tipcie", ["P", "M", "A"])
def test_cc6_every_closure_type_p_m_a_locks_the_period(tipcie: str):
    store = _store()
    store.cierresper.append(_closure(tipcie))
    journal = FakeJournalRepo()
    repo = FakeReceiptsRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )

    with pytest.raises(PeriodLockedError):
        repo.create(
            ReceiptCreate(**{**_BODY, "fecha": "2025-01-15"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )
    assert store.detapago == []


def test_cc6_receipt_outside_the_closed_period_is_accepted():
    store = _store()
    store.cierresper.append(_closure("P"))
    journal = FakeJournalRepo()
    repo = FakeReceiptsRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )

    response = repo.create(
        ReceiptCreate(**_BODY),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=None,
    )

    assert response["saldo_actual"] == "0"
    assert len(store.detapago) == 1
    assert [entry["status"] for entry in journal.entries] == ["COMMITTED"]


# ─── the shared guard itself (consumed by slice 5) ───────────────


def test_guard_ignores_a_closure_of_another_type():
    periods = [{**_closure("P"), "tipcie": "X"}]
    assert hay_cie_eli(periods, fecha=date(2025, 1, 15), codclas="S01") is None


def test_guard_ignores_a_closure_scoped_to_another_document_class():
    periods = [{**_closure("P"), "codclas": "S15"}]
    assert hay_cie_eli(periods, fecha=date(2025, 1, 15), codclas="S01") is None
    assert hay_cie_eli(periods, fecha=date(2025, 1, 15), codclas="S15") is not None


def test_guard_ignores_a_date_outside_the_closed_range():
    periods = [_closure("P")]
    assert hay_cie_eli(periods, fecha=date(2024, 12, 31), codclas="S01") is None
    assert hay_cie_eli(periods, fecha=date(2025, 2, 1), codclas="S01") is None


def test_guard_accepts_iso_string_dates():
    periods = [
        {"fecdes": "2025-01-01", "fechas": "2025-01-31", "tipcie": "P"},
    ]
    assert hay_cie_eli(periods, fecha="2025-01-15", codclas="S01") is not None
    assert hay_cie_eli(periods, fecha="2025-03-15", codclas="S01") is None
