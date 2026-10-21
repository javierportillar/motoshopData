"""Task 4.4 tests: arqueo de caja (cajaarqueo + detcajarq) — CC-4.

Scenarios (spec erp-collections-cash):
- CC-4s1: bills (tiparq 1) summing 300 000 + coins (tiparq 2) summing 12 500
  post a header with ``salcaj = 312500.0`` and the rows keep their tiparq
  classes.
- CC-4s2: a declared ``salcaj`` that does not match the denomination sum is
  a 422 that NAMES the difference — nothing persists.

The server owns the total: when the client omits ``salcaj`` the header
carries the computed sum.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from motoshop_api.erp.cash.repo import ARQUEO_CODCON, FakeArqueoRepo
from motoshop_api.erp.cash.schemas import ArqueoCreate
from motoshop_api.erp.cash.store import FakeCashStore
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError

_ROWS = [
    {"denarq": "100000", "cantden": 3, "tiparq": 1, "tipdet": "BILLETE 100000"},
    {"denarq": "5000", "cantden": 2, "tiparq": 2, "tipdet": "MONEDA 5000"},
    {"denarq": "2500", "cantden": 1, "tiparq": 2, "tipdet": "MONEDA 2500"},
]
_BODY = {
    "fecha": "2025-02-10",
    "codcaj": "01",
    "codcue": "1105",
    "nitter": "222222222222",
    "rows": _ROWS,
}


def _repo(store: FakeCashStore, journal: FakeJournalRepo | None = None):
    journal = journal or FakeJournalRepo()
    return (
        FakeArqueoRepo(store=store, journal=journal, idempotency=FakeIdempotencyRepo()),
        journal,
    )


# ─── CC-4s1: the header equals the denomination sum ──────────────


def test_cc4s1_arqueo_header_reads_the_denomination_sum():
    store = FakeCashStore()
    repo, journal = _repo(store)

    response = repo.create(
        ArqueoCreate(**_BODY),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=None,
    )

    assert response["salcaj"] == "312500"
    assert response["numero"] == 401  # contadores S38 seeded at 401
    assert response["pref"] == "ARQ"
    assert response["codclas"] == ARQUEO_CODCON

    assert len(store.cajaarqueo) == 1
    header = store.cajaarqueo[0]
    assert header["salcaj"] == Decimal("312500")
    assert header["estarq"] == "B"
    assert header["numarq"] == "401"
    assert header["codcue"] == "1105"

    # the rows keep their classes: 3 denominations, 1 class-1 and 2 class-2
    assert len(store.detcajarq) == 3
    classes = sorted(row["tiparq"] for row in store.detcajarq)
    assert classes == ["1", "2", "2"]
    total = sum(row["denarq"] * row["cantden"] for row in store.detcajarq)
    assert total == Decimal("312500")

    assert [entry["status"] for entry in journal.entries] == ["COMMITTED"]


def test_cc4s1_declared_total_matching_the_sum_is_accepted():
    store = FakeCashStore()
    repo, _journal = _repo(store)

    response = repo.create(
        ArqueoCreate(**{**_BODY, "salcaj": "312500"}),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=None,
    )

    assert response["salcaj"] == "312500"
    assert store.cajaarqueo[0]["salcaj"] == Decimal("312500")


# ─── CC-4s2: an inconsistent arqueo is rejected ──────────────────


def test_cc4s2_inconsistent_total_is_422_naming_the_difference_and_persists_nothing():
    store = FakeCashStore()
    repo, journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        repo.create(
            ArqueoCreate(**{**_BODY, "salcaj": "300000"}),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    message = excinfo.value.detail()["fields"]["salcaj"]
    assert "300000" in message  # the declared total
    assert "312500" in message  # the computed sum
    assert "-12500" in message  # the difference
    assert store.cajaarqueo == []
    assert store.detcajarq == []
    assert journal.entries == []


def test_cc4s2_rows_without_a_valid_class_are_rejected():
    store = FakeCashStore()
    repo, _journal = _repo(store)

    with pytest.raises(LegacyValidationError) as excinfo:
        repo.create(
            ArqueoCreate(
                **{**_BODY, "rows": [{"denarq": "1000", "cantden": 1, "tiparq": 7}]}
            ),
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            request_id="r1",
            idempotency_key=None,
        )

    assert "rows[0].tiparq" in excinfo.value.detail()["fields"]
    assert store.cajaarqueo == []


def test_arqueo_replay_does_not_write_twice():
    store = FakeCashStore()
    repo, journal = _repo(store)
    key = "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"

    first = repo.create(
        ArqueoCreate(**_BODY),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=key,
    )
    second = repo.create(
        ArqueoCreate(**_BODY),
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        request_id="r1",
        idempotency_key=key,
    )

    assert first == second
    assert len(store.cajaarqueo) == 1
    assert len(store.detcajarq) == 3
    assert len([e for e in journal.entries if e["status"] == "COMMITTED"]) == 1
