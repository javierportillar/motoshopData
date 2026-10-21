"""Task 4.5 tests: bank consignment (consbancab).

Scenarios (erp-collections-cash):
- CC-5s1: a bank consignment is written to `consbancab` with the number
  taken from the payment form's own counter (`formapago.numcon`) — NOT from
  `contadores` — and that counter advances EXACTLY ONCE.
- CC-5s2: the idempotent replay returns the stored response and does NOT
  advance the payment-form counter a second time (f0 short-circuit).
- CC-5s3: a payment form that is not a bank consignment is rejected 422
  naming `codpag` (tippag/afepag contract).
- CC-5s4: a non-positive value is rejected 422 naming `valor`, and nothing
  is reserved.
- CC-5s5: a consignment dated inside a locked period is rejected 409 by the
  shared Hay_Cie_Eli guard.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from motoshop_api.erp.cash.repo import FakeConsignmentRepo
from motoshop_api.erp.cash.schemas import ConsignmentCreate
from motoshop_api.erp.cash.store import FakeCashStore
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError

KEY = "1b2c3d4e-5f60-4a11-9b22-c3d4e5f6a7b8"


def _repo(store: FakeCashStore | None = None) -> FakeConsignmentRepo:
    store = store or FakeCashStore()
    return FakeConsignmentRepo(
        store=store,
        journal=FakeJournalRepo(),
        idempotency=FakeIdempotencyRepo(),
    )


def _body(**overrides) -> ConsignmentCreate:
    base: dict = dict(
        codpag="22",
        valor=Decimal("500000"),
        fecha=date(2026, 3, 10),
        codcaj="01",
        codban="001",
        detalle="Consignación prueba",
    )
    base.update(overrides)
    return ConsignmentCreate(**base)


def _create(
    repo: FakeConsignmentRepo,
    body: ConsignmentCreate,
    req: str = "r-1",
    key: str = KEY,
):
    return repo.create(
        body, tenant="motoshop", empresa="E01", actor="cajero1",
        request_id=req, idempotency_key=key,
    )


# ─── CC-5s1: consignment number comes from formapago.numcon ───


def test_consignment_uses_payment_form_counter():
    store = FakeCashStore()
    repo = _repo(store)
    response = _create(repo, _body())
    assert response["numero"] == store.formapago["22"]["numcon"] - 1
    assert response["codpag"] == "22"
    assert response["totcon"] == "500000"
    assert len(store.consbancab) == 1
    row = store.consbancab[0]
    assert row["numcon"] == str(store.formapago["22"]["numcon"] - 1)
    assert row["precon"]
    assert row["feccon"] == date(2026, 3, 10)
    assert row["estcon"] == "B"
    # the payment form counter advanced exactly once
    assert store.formapago["22"]["numcon"] == 701


def test_consignment_advances_counter_once_per_posting():
    store = FakeCashStore()
    repo = _repo(store)
    _create(repo, _body(), req="r-1", key=KEY)
    _create(
        repo, _body(valor=Decimal("250000")), req="r-2",
        key="2b2c3d4e-5f60-4a11-9b22-c3d4e5f6a7b8",
    )
    assert store.formapago["22"]["numcon"] == 702
    assert [row["numcon"] for row in store.consbancab] == ["700", "701"]


# ─── CC-5s2: idempotent replay ────────────────────────────────


def test_replay_does_not_advance_the_counter_twice():
    store = FakeCashStore()
    repo = _repo(store)
    first = _create(repo, _body(), req="r-1")
    second = _create(repo, _body(), req="r-1")
    assert first == second
    assert len(store.consbancab) == 1
    assert store.formapago["22"]["numcon"] == 701


# ─── CC-5s3: only bank-consignment payment forms are accepted ─


def test_non_consignment_payment_form_is_422():
    repo = _repo()
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, _body(codpag="01"))
    assert "codpag" in exc.value.fields


def test_unknown_payment_form_is_422():
    repo = _repo()
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, _body(codpag="99"))
    assert "codpag" in exc.value.fields


# ─── CC-5s4: value must be positive ────────────────────────────


def test_non_positive_value_is_422_nothing_reserved():
    store = FakeCashStore()
    repo = _repo(store)
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, _body(valor=Decimal("0")))
    assert "valor" in exc.value.fields
    assert store.consbancab == []
    assert store.formapago["22"]["numcon"] == 700


# ─── CC-5s5: period lock (Hay_Cie_Eli) ─────────────────────────


def test_consignment_inside_locked_period_is_rejected():
    store = FakeCashStore()
    store.cierresper.append(
        {"codcie": 1, "fecdes": date(2026, 3, 1), "fechas": date(2026, 3, 31),
         "tipcie": "P"}
    )
    repo = _repo(store)
    with pytest.raises(Exception) as exc:
        _create(repo, _body(fecha=date(2026, 3, 10)))
    assert exc.type.__name__ in {"PeriodLockedError", "HTTPException"}
    assert store.consbancab == []
    assert store.formapago["22"]["numcon"] == 700
