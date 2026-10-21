"""Task 2.3 tests: productos repo — units, barcodes, per-list prices.

Scenarios (erp-masters-write):
- MW-2s1: product + `produndmeds` (caja × 12) + `preciosxpro` atomic
  all-or-none via the journal (one UoW; φ3 failure compensates).
- MW-2s2: barcode reuse → 409 on `codbar`, no partial rows.
- MW-2s3: `pvsini`/`pvconi` inclusive ↔ exclusive × (1 + rate) computed
  server-side with exact Decimal (MW: never float, ADR-0008-07).
- MW-3s1: missing `codlin1` → 422 aggregate naming all offending fields.
- MW-3s2: `exiprod` edit → 422 "stock moves through transactions", unchanged.
- `porutil` recomputation parity from the transaction-owned cost base
  (modules.md §15 ModPrecio).

Fake twins mirror the legacy contract: one UoW = one staged batch preserved
for the journal φ-sequence; injected `fail_table` simulates a MyISAM partial
land followed by the engine's compensating cleanup.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.repo import (
    FakeMastersStore,
    FakeProductosRepo,
    get_productos_repo,
)
from motoshop_api.erp.masters.schemas import (
    BarcodeEntry,
    ProductCreate,
    ProductPriceEntry,
    ProductUpdate,
    UnitEntry,
)
from motoshop_api.erp.masters.validators import (
    DuplicateMasterError,
    LegacyValidationError,
    recompute_porutil,
)

_IDEM = "9f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"


def _body(**overrides) -> ProductCreate:
    values = {
        "codprod": "PROD1",
        "nomprod": "Bujía NGK Ñ-P",
        "codmed": "UND",
        "codlin1": "L01",
        "prices": [ProductPriceEntry(
            codlis="L01", pvtipo="1", pvsini=Decimal("10000"), iva_rate=Decimal("19"),
        )],
    }
    values.update(overrides)
    return ProductCreate(**values)


def _unit() -> UnitEntry:
    return UnitEntry(
        codmed="CJA", divmul="M", facumed=Decimal("12"),
        pventa=Decimal("120000"), tipovc="0",
    )


def _repo(store, journal=None):
    return FakeProductosRepo(
        store=store,
        journal=journal or FakeJournalRepo(),
        idempotency=FakeIdempotencyRepo(),
    )


def _save_kwargs() -> dict:
    return {
        "tenant": "motoshop", "empresa": "E01", "actor": "gerente1",
        "request_id": "r-1", "idempotency_key": _IDEM,
    }


# ─── MW-2s1: atomic product + unit + price save ────────────────


def test_create_product_units_prices_atomic_committed():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    repo = _repo(store, journal)

    response = repo.create(
        _body(barcodes=[BarcodeEntry(codbar="7701234012345")], units=[_unit()]),
        **_save_kwargs(),
    )

    product = store.productos["PROD1"]
    assert product["nomprod"] == "Bujía NGK Ñ-P"
    assert product["actprod"] == "A"
    units = store.tables()["produndmeds"]
    assert units == [{
        "codprod": "PROD1", "codmed": "CJA", "divmul": "M",
        "facumed": Decimal("12"), "pventa": Decimal("120000"), "tipovc": "0",
    }]
    prices = store.preciosxpro
    assert len(prices) == 1
    assert prices[0]["codlis"] == "L01"
    assert prices[0]["actupr"] == "S"
    bars = store.prodcodbars
    assert bars == [{"codprod": "PROD1", "codbar": "7701234012345"}]
    assert response["prices"][0]["venprod"] == Decimal("10000.00")
    assert [e["status"] for e in journal.entries] == ["COMMITTED"]
    assert journal.entries[0]["doc_type"] == "producto"


def test_phi3_failure_compensates_all_product_tables():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    store.fail_table = "produndmeds"  # product lands first, then unit fails
    repo = _repo(store, journal)

    with pytest.raises(ErpSaveFailed) as exc:
        repo.create(
            _body(units=[_unit()], prices=[ProductPriceEntry(
                codlis="L01", pvtipo="1", pvsini=Decimal("1"), iva_rate=Decimal("19"),
            )]),
            **_save_kwargs(),
        )

    assert exc.value.retryable is True
    assert store.productos == {}
    assert [e["status"] for e in journal.entries] == ["FAILED"]


# ─── MW-2s2: barcode uniqueness ────────────────────────────────


def test_barcode_reuse_rejected_409_no_partial_rows():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    store.prodcodbars.append({"codprod": "PROD0", "codbar": "7701234012345"})
    repo = _repo(store, journal)

    with pytest.raises(DuplicateMasterError) as exc:
        repo.create(
            _body(codprod="PROD1", barcodes=[BarcodeEntry(codbar="7701234012345")]),
            **_save_kwargs(),
        )

    assert exc.value.field == "codbar"
    assert "PROD1" not in store.productos
    assert store.preciosxpro == []  # even when the another table is the dup source
    assert journal.entries == []


# ─── MW-2s3: IVA price consistency (server-side Decimal) ───────


def test_exclusive_price_derives_inclusive_pair():
    store = FakeMastersStore()
    repo = _repo(store)
    repo.create(_body(), **_save_kwargs())

    product = store.productos["PROD1"]
    assert product["pvsini"] == Decimal("10000.00")
    assert product["pvconi"] == Decimal("11900.00")  # 10000 × 1.19 half-up
    assert product["pvtipo"] == "1"
    price = store.preciosxpro[0]
    assert price["venprod"] == Decimal("10000.00")
    assert price["veniva"] == Decimal("1900.00")


def test_inclusive_price_derives_exclusive_pair():
    store = FakeMastersStore()
    repo = _repo(store)
    repo.create(
        _body(prices=[ProductPriceEntry(
            codlis="L01", pvtipo="2", pvconi=Decimal("11900"), iva_rate=Decimal("19"),
        )]),
        **_save_kwargs(),
    )

    product = store.productos["PROD1"]
    assert product["pvconi"] == Decimal("11900.00")
    assert product["pvsini"] == Decimal("10000.00")  # 11900 / 1.19 — exact
    assert product["pvtipo"] == "2"
    assert store.preciosxpro[0]["veniva"] == Decimal("1900.00")


def test_inconsistent_price_pair_rejected_422():
    store = FakeMastersStore()
    repo = _repo(store)

    with pytest.raises(LegacyValidationError) as exc:
        repo.create(
            _body(prices=[ProductPriceEntry(
                codlis="L01", pvtipo="1", pvsini=Decimal("10000"),
                pvconi=Decimal("15000"), iva_rate=Decimal("19"),
            )]),
            **_save_kwargs(),
        )

    assert any(k.startswith("prices[0]") for k in exc.value.fields)


# ─── MW-3s1: required-field aggregate ─────────────────────────


def test_missing_required_fields_aggregate_422():
    store = FakeMastersStore()
    repo = _repo(store)
    body = _body(nomprod="", codlin1=None)

    with pytest.raises(LegacyValidationError) as exc:
        repo.create(body, **_save_kwargs())

    assert set(exc.value.fields) >= {"nomprod", "codlin1"}


# ─── MW-3s2: transaction-owned fields protected ───────────────


def test_exiprod_edit_rejected_and_unchanged():
    store = FakeMastersStore()
    repo = _repo(store)
    repo.create(_body(), **_save_kwargs())
    store.productos["PROD1"]["exiprod"] = 10.0

    with pytest.raises(LegacyValidationError) as exc:
        repo.update(
            "PROD1",
            ProductUpdate(exiprod=Decimal("5")),
            tenant="motoshop", empresa="E01", actor="gerente1", request_id="r-2",
        )

    assert "transacciones" in exc.value.fields["exiprod"]
    assert store.productos["PROD1"]["exiprod"] == 10.0  # unchanged


# ─── porutil parity (modules.md §15) ──────────────────────────


def test_porutil_recompute_from_transaction_owned_cost():
    assert recompute_porutil(Decimal("12000"), Decimal("8000")) == Decimal("50.00")
    assert recompute_porutil(Decimal("11900"), Decimal("0")) == Decimal("0")


def test_price_update_recomputes_porutil_from_stored_cost():
    store = FakeMastersStore()
    repo = _repo(store)
    repo.create(_body(), **_save_kwargs())
    store.productos["PROD1"]["cosprod"] = 8000.0

    repo.update(
        "PROD1",
        ProductUpdate(prices=[ProductPriceEntry(
            codlis="L01", pvtipo="1", pvsini=Decimal("12000"), iva_rate=Decimal("19"),
        )]),
        tenant="motoshop", empresa="E01", actor="gerente1", request_id="r-3",
    )

    assert store.productos["PROD1"]["pvsini"] == Decimal("12000.00")
    assert store.preciosxpro[0]["venprod"] == Decimal("12000.00")
    assert store.preciosxpro[0]["porutil"] == Decimal("50.00")


# ─── idempotent replay + factory ──────────────────────────────


def test_idempotent_replay_no_second_price_row():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    repo = _repo(store, journal)
    first = repo.create(_body(), **_save_kwargs())
    replay = repo.create(_body(), **_save_kwargs())
    assert replay == first
    assert len(store.preciosxpro) == 1
    assert len(journal.entries) == 1


def test_get_productos_repo_returns_fake_under_test_env():
    assert isinstance(get_productos_repo(), FakeProductosRepo)
