"""Task 4.3 tests: egresos (comprobantes) with concept causación — CC-3.

Scenario (spec erp-collections-cash):
- CC-3s1: an egress of 90 000 with an approved expense concept posts
  ``detcuentas`` with a 90 000 DEBIT on the concept's expense account and a
  90 000 CREDIT on the cash account; debits equal credits and the document
  total (``totegr``) is computed server-side.

The movement endpoints (in/out) inherit the shared period lock of task 4.2 —
a movement dated inside a closed period is rejected 409 with no ledger row.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from motoshop_api.erp.cash.repo import (
    EGRESS_CODCON,
    MOVEMENT_ENTRADA,
    MOVEMENT_SALIDA,
    FakeCashMovementsRepo,
)
from motoshop_api.erp.cash.schemas import CashMovementCreate, EgressCreate
from motoshop_api.erp.cash.store import FakeCashStore
from motoshop_api.erp.guards import PeriodLockedError
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError

_EGRESS = {
    "codcon": "G001",
    "valor": "90000",
    "fecha": "2025-02-10",
    "codpag": "01",
    "codcaj": "01",
    "concepto": "COMPRA DE REPUESTOS",
}
_MOVEMENT = {
    "tipo": MOVEMENT_SALIDA,
    "codcon": "G001",
    "valor": "90000",
    "fecha": "2025-02-10",
    "codpag": "01",
    "codcaj": "01",
    "concepto": "COMPRA DE REPUESTOS",
}


def _store() -> FakeCashStore:
    store = FakeCashStore()
    store.concepingegr["G001"] = {
        "codcon": "G001",
        "nomcon": "GASTOS GENERALES",
        "valcon": Decimal("0"),
        "tipcon": "EGRESO",
        "debcre": "D",
        "codcue": "5110",
        "descon": "GASTOS GENERALES",
        "codpor": "",
    }
    store.concepingegr["I001"] = {
        "codcon": "I001",
        "nomcon": "OTROS INGRESOS",
        "valcon": Decimal("0"),
        "tipcon": "INGRESO",
        "debcre": "C",
        "codcue": "4135",
        "descon": "OTROS INGRESOS",
        "codpor": "",
    }
    return store


def _repo(store: FakeCashStore, journal: FakeJournalRepo | None = None):
    journal = journal or FakeJournalRepo()
    return (
        FakeCashMovementsRepo(
            store=store, journal=journal, idempotency=FakeIdempotencyRepo()
        ),
        journal,
    )


# ─── CC-3s1: egress with an expense concept balances ────────────


def test_cc3s1_egress_debits_the_expense_account_and_credits_cash():
    store = _store()
    repo, journal = _repo(store)

    response = repo.create_egress(
        EgressCreate(**_EGRESS),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=None,
    )

    assert response["numero"] == 201  # contadores S02 seeded at 201
    assert response["pref"] == "CE"
    assert response["codclas"] == EGRESS_CODCON
    assert response["totegr"] == "90000"  # server-side total

    # the comprobantes header
    assert len(store.comprobantes) == 1
    header = store.comprobantes[0]
    assert header["numegr"] == "201"
    assert header["codclas"] == EGRESS_CODCON
    assert header["preegr"] == "CE"
    assert header["totegr"] == Decimal("90000")
    assert header["subegr"] == Decimal("90000")
    assert header["codcos"] == "G001"
    assert header["estegr"] == "B"

    # the causación: 90 000 debit to the expense account, 90 000 credit to cash
    expense = [r for r in store.detcuentas if r["codcue"] == "5110"]
    assert len(expense) == 1
    assert expense[0]["valdeb"] == Decimal("90000")
    assert expense[0]["valhab"] == Decimal("0")

    cash = [r for r in store.detcuentas if r["codcue"] == "1105"]
    assert len(cash) == 1
    assert cash[0]["valdeb"] == Decimal("0")
    assert cash[0]["valhab"] == Decimal("90000")

    total_debit = sum(r["valdeb"] for r in store.detcuentas)
    total_credit = sum(r["valhab"] for r in store.detcuentas)
    assert total_debit == total_credit

    assert [entry["status"] for entry in journal.entries] == ["COMMITTED"]


def test_cc3s1_egress_keeps_the_payment_duality_and_the_cash_row():
    store = _store()
    repo, _journal = _repo(store)

    repo.create_egress(
        EgressCreate(**_EGRESS),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=None,
    )

    assert len(store.detapago) == 1
    row = store.detapago[0]
    assert row["valpag"] == Decimal("90000")
    assert row["soldeb"] == Decimal("90000")
    assert row["solcre"] == Decimal("0")
    assert row["estado"] == "B"


def test_cc3_ingress_mirrors_the_egress_and_uses_its_own_document_class():
    store = _store()
    repo, _journal = _repo(store)

    response = repo.create_movement(
        CashMovementCreate(**{**_MOVEMENT, "tipo": MOVEMENT_ENTRADA, "codcon": "I001"}),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=None,
    )

    assert response["pref"] == "CI"
    assert response["codclas"] == "S03"

    income = [r for r in store.detcuentas if r["codcue"] == "4135"]
    assert len(income) == 1
    assert income[0]["valhab"] == Decimal("90000")
    cash = [r for r in store.detcuentas if r["codcue"] == "1105"]
    assert cash[0]["valdeb"] == Decimal("90000")
    assert cash[0]["valhab"] == Decimal("0")


# ─── validation ──────────────────────────────────────────────────


def test_cc3_unknown_concept_is_422_and_persists_nothing():
    store = _store()
    repo, journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        repo.create_egress(
            EgressCreate(**{**_EGRESS, "codcon": "NOPE"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    assert "codcon" in excinfo.value.detail()["fields"]
    assert store.comprobantes == []
    assert store.detcuentas == []
    assert journal.entries == []


def test_cc3_non_positive_value_is_422():
    store = _store()
    repo, _journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        repo.create_egress(
            EgressCreate(**{**_EGRESS, "valor": "0"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    assert "valor" in excinfo.value.detail()["fields"]


def test_cc3_unknown_movement_type_is_422():
    store = _store()
    repo, _journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        repo.create_movement(
            CashMovementCreate(**{**_MOVEMENT, "tipo": "VUELO"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    assert "tipo" in excinfo.value.detail()["fields"]


# ─── the shared period lock applies to the movements too (CC-6) ──


def test_cc6_movement_inside_a_closed_period_is_rejected_and_writes_nothing():
    store = _store()
    store.cierresper.append(
        {
            "codcie": 1,
            "fecdes": date(2025, 1, 1),
            "fechas": date(2025, 1, 31),
            "tipcie": "P",
            "numaju": "",
            "codclas": "",
        }
    )
    repo, journal = _repo(store)

    with pytest.raises(PeriodLockedError):
        repo.create_egress(
            EgressCreate(**{**_EGRESS, "fecha": "2025-01-15"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    assert store.comprobantes == []
    assert store.detcuentas == []
    assert journal.entries == []


# ─── idempotent replay ───────────────────────────────────────────


def test_egress_replay_does_not_write_twice():
    store = _store()
    repo, journal = _repo(store)
    key = "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"

    first = repo.create_egress(
        EgressCreate(**_EGRESS),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=key,
    )
    second = repo.create_egress(
        EgressCreate(**_EGRESS),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=key,
    )

    assert first == second
    assert len(store.comprobantes) == 1
    assert len(store.detapago) == 1
    assert len([e for e in journal.entries if e["status"] == "COMMITTED"]) == 1
