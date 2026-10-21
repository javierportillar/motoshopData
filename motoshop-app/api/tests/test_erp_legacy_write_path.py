"""Regression tests for the legacy write path against real MySQL.

The save engine is exercised hermetically by ``test_erp_invoice_save.py``
through ``FakeInvoiceStore``, which masked three defects that only appear
against the legacy schema (found by the F8 E2E probe on masvital_clone):

- ``RealInvoiceStore`` did not expose the ``terceros``/``sellers``/
  ``productos`` mappings that ``_validate`` and the stock block consume,
  so every real save died with ``AttributeError`` before the first INSERT.
- ``app_doc_journal`` did not declare ``updated_at`` while the repository
  writes it, so ``record_number`` raised ``CompileError: Unconsumed column
  names: updated_at``.
- ``commit`` used ``exec_driver_sql`` with named placeholders, shipping
  ``:numfven`` literally to pymysql (ERROR 1064).

No database is touched here: the store is driven through a fake engine.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from motoshop_api.erp.invoicing.store import RealInvoiceStore, _LazyMasterMap


def test_real_store_exposes_the_master_mappings_the_engine_reads():
    store = RealInvoiceStore()

    assert hasattr(store, "terceros")
    assert hasattr(store, "sellers")
    assert hasattr(store, "productos")


def test_lazy_master_map_fetches_once_and_supports_membership():
    calls: list[str] = []

    def fetch(key: str) -> dict | None:
        calls.append(key)
        return {"nitter": key} if key == "A" else None

    masters = _LazyMasterMap(fetch)

    assert masters.get("A") == {"nitter": "A"}
    assert masters.get("A") == {"nitter": "A"}
    assert calls == ["A"], "a repeated key must not hit the database again"
    assert "A" in masters
    assert "B" not in masters
    assert masters.get("B", "fallback") == "fallback"


def test_journal_model_declares_the_updated_at_column():
    from motoshop_api.erp.models import app_doc_journal

    assert "updated_at" in app_doc_journal.c


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []

    def execute(self, statement, params) -> None:
        self.statements.append((str(statement), dict(params)))


class _FakeTransaction:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeConnection:
        return self._connection

    def __exit__(self, *exc_info) -> None:
        return None


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self.connection)


def test_commit_binds_parameters_instead_of_shipping_named_placeholders():
    engine = _FakeEngine()
    store = RealInvoiceStore(engine_factory=lambda: engine)
    store.stage_insert(
        "facventas", {"numfven": 501, "totfven": Decimal("11900")}
    )

    store.commit()

    assert len(engine.connection.statements) == 1
    sql, params = engine.connection.statements[0]
    assert "INSERT INTO facventas" in sql
    assert ":numfven" in sql, "named placeholders are compiled by SQLAlchemy"
    assert params == {"numfven": 501, "totfven": Decimal("11900")}
    assert store._pending == [], "the buffer is drained after the commit"


def test_commit_applies_the_stock_delta_with_the_invoice_rows():
    engine = _FakeEngine()
    store = RealInvoiceStore(engine_factory=lambda: engine)
    store.stage_insert("facventas", {"numfven": 501})
    store.stage_stock_decrement("PROD1", Decimal("0.250"))

    store.commit()

    assert len(engine.connection.statements) == 2
    sql, params = engine.connection.statements[1]
    assert "UPDATE productos" in sql
    assert "ROUND(exiprod - :qty, 3)" in sql, "a delta, not an absolute value"
    assert params == {"qty": Decimal("0.250"), "codprod": "PROD1"}
    assert store._pending_stock == []


# ─── Legacy header/causación conventions (fake twin) ─────────────────────


def _fake_repo(candet: Decimal = Decimal("3"), payments=None):
    from motoshop_api.erp.idempotency import FakeIdempotencyRepo
    from motoshop_api.erp.invoicing.repo import FakeInvoiceStore, FakeInvoicesRepo
    from motoshop_api.erp.invoicing.schemas import (
        InvoiceCreate,
        InvoiceLineIn,
        InvoicePaymentIn,
    )
    from motoshop_api.erp.journal import FakeJournalRepo

    store = FakeInvoiceStore()
    repo = FakeInvoicesRepo(
        store=store, journal=FakeJournalRepo(), idempotency=FakeIdempotencyRepo()
    )
    unit_price = Decimal("10000.50")
    discount = Decimal("500.25")
    vat = Decimal("950.05")
    total = (unit_price - discount + vat) * candet
    if payments is None:
        payments = [{"codpag": "F01", "amount": total}]
    body = InvoiceCreate(
        nitter="222222222222",
        nitvend="VEN01",
        lines=[
            InvoiceLineIn(
                codprod="PROD1",
                nomdet="BUJIA NGK",
                candet=candet,
                valuni=unit_price,
                dctpes=discount,
                ivapes=vat,
            )
        ],
        payments=[InvoicePaymentIn(**payment) for payment in payments],
    )
    return repo, store, body


def _save(repo, body):
    return repo.create(
        body,
        tenant="masvital",
        empresa="E01",
        actor="cajero1",
        request_id="r-legacy",
        idempotency_key=None,
    )


def test_header_follows_the_legacy_operator_conventions():
    repo, store, body = _fake_repo()

    _save(repo, body)

    header = store.facventas[0]
    assert header["codemp"] == "59312669", "legacy stores the operator NIT"
    assert header["empcod"] == ""
    assert header["nomuso"] == ""
    assert header["codcaj"] == "C1", "the payload placeholder 01 maps to C1"


def test_causacion_books_the_legacy_puc_chart_and_balances():
    repo, store, body = _fake_repo()

    result = _save(repo, body)

    entries = {row["codcue"]: row for row in store.detcuentas}
    assert set(entries) == {"11050501", "41359501", "24080102"}
    totals = result["totals"]
    assert entries["11050501"]["valdeb"] == totals["totfven"]
    assert entries["41359501"]["valhab"] == totals["totfven"] - totals["totiva"]
    assert entries["24080102"]["valhab"] == totals["totiva"]
    assert sum(r["valdeb"] for r in store.detcuentas) == sum(
        r["valhab"] for r in store.detcuentas
    )


def test_fractional_stock_is_decremented_without_losing_precision():
    repo, store, body = _fake_repo(candet=Decimal("0.250"))
    before = Decimal(str(store.productos["PROD1"]["exiprod"]))

    _save(repo, body)

    after = Decimal(str(store.productos["PROD1"]["exiprod"]))
    assert after == before - Decimal("0.250")


# ─── Debit account per payment form ──────────────────────────────────────


def test_cash_payment_debits_caja():
    repo, store, body = _fake_repo()

    _save(repo, body)

    debits = [r["codcue"] for r in store.detcuentas if r["valdeb"] > 0]
    assert debits == ["11050501"]


def test_credit_payment_debits_the_receivable_and_names_the_client():
    repo, store, body = _fake_repo(
        payments=[{"codpag": "F10", "amount": Decimal("31350.90")}]
    )

    _save(repo, body)

    row = next(r for r in store.detcuentas if r["codcue"] == "13050501")
    assert row["valdeb"] == Decimal("31350.90")
    assert row["valhab"] == Decimal("0")
    assert row["nitter"] == "222222222222"
    assert store.facventas[0]["codpag"] == "F10"


def test_card_and_transfer_forms_debit_bancos():
    for form in ("F03", "F04", "F07", "TARJETA", "TRANSFER"):
        repo, store, body = _fake_repo(
            payments=[{"codpag": form, "amount": Decimal("31350.90")}]
        )

        _save(repo, body)

        debits = [r["codcue"] for r in store.detcuentas if r["valdeb"] > 0]
        assert debits == ["11100501"], form


def test_mixed_payments_split_the_debit_and_keep_the_entry_balanced():
    repo, store, body = _fake_repo(
        payments=[
            {"codpag": "F01", "amount": Decimal("15675.45")},
            {"codpag": "F07", "amount": Decimal("15675.45")},
        ]
    )

    result = _save(repo, body)

    debits = [r["codcue"] for r in store.detcuentas if r["valdeb"] > 0]
    assert debits == ["11050501", "11100501"]
    total_debits = sum(r["valdeb"] for r in store.detcuentas)
    total_credits = sum(r["valhab"] for r in store.detcuentas)
    assert total_debits == result["totals"]["totfven"]
    assert total_debits == total_credits


def test_cost_is_booked_from_the_sale_time_snapshot():
    repo, store, body = _fake_repo(candet=Decimal("2"))
    store.productos["PROD1"]["cosulc"] = Decimal("4000")

    _save(repo, body)

    line = store.detfventas[0]
    assert line["cosprod"] == Decimal("4000"), "detfventas snapshots the unit cost"
    cost = next(r for r in store.detcuentas if r["codcue"] == "61359501")
    inventory = next(r for r in store.detcuentas if r["codcue"] == "14350101")
    assert cost["valdeb"] == Decimal("8000.00")
    assert cost["valhab"] == Decimal("0")
    assert inventory["valdeb"] == Decimal("0")
    assert inventory["valhab"] == Decimal("8000.00")
    assert sum(r["valdeb"] for r in store.detcuentas) == sum(
        r["valhab"] for r in store.detcuentas
    )


def test_zero_cost_products_add_no_noise_to_the_ledger():
    repo, store, body = _fake_repo()

    _save(repo, body)

    assert not [r for r in store.detcuentas if r["codcue"] in ("61359501", "14350101")]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
