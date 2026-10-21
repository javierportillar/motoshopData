"""Task 3.3 tests: invoice save engine — formuleo + pre-save validation.

Scenarios (erp-sales-invoicing):
- SI-5s2: a client-sent header total that differs from the server
  computation is rejected 422 naming the mismatch field with zero rows.
- WF-5s1: the journal row is PENDING before the first legacy insert.
- WF-4s2: an injected failure between the detail and the payment insert
  leaves zero legacy rows, journal FAILED, and the retryable 503 contract.
- SI-6s1: a credit-blocked or inactive client is rejected 422 through the
  FROZEN slice-2 master-state seam (ensure_master_active / InactiveMasterError).
- SI-6s2: an empty or negative invoice is rejected 422 — nothing reserved
  (journal and contadores untouched).
- φ2 failure: contadores window rejection marks the journal FAILED.
- Idempotent replay (WF-8s1 seam): duplicate save returns the stored
  response without reserving a second number.

Tests run hermetically (FakeInvoiceStore + Fake contadores/journal).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.invoicing.repo import FakeInvoiceStore, FakeInvoicesRepo
from motoshop_api.erp.invoicing.schemas import InvoiceCreate, InvoiceLineIn
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.validators import (
    InactiveMasterError,
    LegacyValidationError,
)
from motoshop_api.erp.numbering import ContadorRow, ResolverRangeError

KEY = "0a1b2c3d-4e5f-4a11-9b22-c3d4e5f6a7b8"

#: conres baseline seeded by FakeInvoiceStore for codcon S15 / pref FVP
BASE_CONRES = 501


def _line(**overrides) -> InvoiceLineIn:
    base: dict[str, Any] = dict(
        codprod="PROD1", nomdet="Bujía NGK Ñ-Spec",
        candet=3, valuni=10000.50, dctpes=500.25, ivapes=950.05, ipopes=0,
    )
    base.update(overrides)
    return InvoiceLineIn(**base)


def _body(**overrides) -> InvoiceCreate:
    base: dict[str, Any] = dict(
        nitter="222222222222",
        nitvend="VEN01",
        lines=[_line()],
        payments=[{"codpag": "F01", "amount": 31350.90}],
    )
    base.update(overrides)
    return InvoiceCreate(**base)


def _repo(store: FakeInvoiceStore | None = None) -> FakeInvoicesRepo:
    store = store or FakeInvoiceStore()
    return FakeInvoicesRepo(
        store=store,
        journal=FakeJournalRepo(),
        idempotency=FakeIdempotencyRepo(),
    )


def _create(repo: FakeInvoicesRepo, body: InvoiceCreate, req: str = "r-1"):
    return repo.create(
        body, tenant="motoshop", empresa="E01", actor="cajero1",
        request_id=req, idempotency_key=KEY,
    )


def _header_row(store: FakeInvoiceStore, numfven: int) -> dict:
    return next(r for r in store.facventas if r["numfven"] == numfven)


# ─── saved invoice stores server-computed totals ───────────────


def test_saved_invoice_stores_server_totals():
    repo = _repo()
    response = _create(repo, _body())
    assert response["numfven"] == BASE_CONRES
    assert response["prefven"] == "FVP"
    assert response["totals"]["totfven"] == Decimal("31350.90")
    header = _header_row(repo.store, BASE_CONRES)
    assert header["totfven"] == Decimal("31350.90")
    assert header["subfven"] == Decimal("30001.50")
    assert header["totdct"] == Decimal("1500.75")
    assert header["totiva"] == Decimal("2850.15")
    assert repo.store.detfventas[0]["totdet"] == Decimal("31350.90")
    assert repo.journal.entries[-1]["status"] == "COMMITTED"


# ─── SI-5s2: client totals mismatch ────────────────────────────


def test_matching_client_totals_are_accepted():
    repo = _repo()
    body = _body(
        # Parity anchor: the second line carries no discount/IVA, exactly as
        # in test_erp_invoice_totals.py (the formuleo authority). Without the
        # zeroed amounts the header total would be 36250.90, not 35350.90.
        lines=[_line(), _line(codprod="PROD2", candet=2, valuni=2000.00,
                              dctpes=0, ivapes=0, ipopes=0)],
        payments=[{"codpag": "F01", "amount": 35350.90}],
        client_totals={"totfven": 35350.90},
    )
    response = _create(repo, body)
    assert response["totals"]["totfven"] == Decimal("35350.90")


def test_client_totals_mismatch_is_422_naming_the_field():
    repo = _repo()
    body = _body(
        # Parity anchor: the second line carries no discount/IVA, exactly as
        # in test_erp_invoice_totals.py (the formuleo authority). Without the
        # zeroed amounts the header total would be 36250.90, not 35350.90.
        lines=[_line(), _line(codprod="PROD2", candet=2, valuni=2000.00,
                              dctpes=0, ivapes=0, ipopes=0)],
        payments=[{"codpag": "F01", "amount": 35350.90}],
        client_totals={"totfven": 999.99},
    )
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    fields = exc.value.fields
    assert any("totfven" in key for key in fields), fields
    assert repo.store.facventas == []  # zero rows written
    assert repo.journal.entries == []  # rejected before φ1


def test_partial_client_totals_are_checked_field_by_field():
    repo = _repo()
    body = _body(
        # Parity anchor: the second line carries no discount/IVA, exactly as
        # in test_erp_invoice_totals.py (the formuleo authority). Without the
        # zeroed amounts the header total would be 36250.90, not 35350.90.
        lines=[_line(), _line(codprod="PROD2", candet=2, valuni=2000.00,
                              dctpes=0, ivapes=0, ipopes=0)],
        payments=[{"codpag": "F01", "amount": 35350.90}],
        client_totals={"subfven": 34001.50, "totiva": 2850.15,
                       "totdct": 999.75},
    )
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    assert "client_totals.totdct" in exc.value.fields


# ─── WF-5s1: journal leads the save ────────────────────────────


def test_journal_pending_before_first_legacy_insert():
    repo = _repo()
    seen: dict = {}
    original = repo.store.stage_insert

    def _spy(table: str, _row: dict) -> None:
        if table == "facventas" and "journal_status" not in seen:
            seen["journal_status"] = repo.journal.entries[-1]["status"]
        original(table, _row)

    repo.store.stage_insert = _spy  # type: ignore[method-assign]
    _create(repo, _body())
    assert seen["journal_status"] == "PENDING"
    assert repo.journal.entries[-1]["status"] == "COMMITTED"


# ─── WF-4s2: injected mid-save failure ─────────────────────────


def test_failure_at_payment_insert_leaves_zero_rows_journal_failed():
    repo = _repo()
    repo.store.fail_table = "detapago"
    with pytest.raises(ErpSaveFailed) as exc:
        _create(repo, _body())
    assert exc.value.retryable is True
    assert exc.value.docnum == BASE_CONRES
    # MyISAM compensation: no partial rows survive
    assert repo.store.facventas == []
    assert repo.store.detfventas == []
    assert repo.store.detapago == []
    entry = repo.journal.entries[0]
    assert entry["status"] == "FAILED"
    assert "detapago" in entry["error_msg"]


# ─── SI-6s1: pre-save validation parity (desktop Validar) ──────


def test_credit_blocked_client_is_422_frozen_contract():
    store = FakeInvoiceStore()
    store.terceros["222222222222"]["cupblo"] = "B"
    repo = _repo(store)
    with pytest.raises(InactiveMasterError) as exc:
        _create(repo, _body())
    detail = exc.value.detail()  # frozen cross-slice payload dict
    assert detail["code"] == "master_inactive"
    assert detail["fields"] == {"nitter": "master_inactive"}
    assert detail["master_state"]["cupblo"] == "B"
    # nothing reserved
    assert repo.journal.entries == []
    assert repo.store.numbering.read("S15", "FVP").conres == BASE_CONRES


def test_inactive_client_is_422_frozen_contract():
    store = FakeInvoiceStore()
    store.terceros["222222222222"]["inater"] = "SI"
    repo = _repo(store)
    with pytest.raises(InactiveMasterError) as exc:
        _create(repo, _body())
    assert exc.value.detail()["master_state"]["inater"] == "SI"


def test_inactive_product_line_is_422_master_state():
    store = FakeInvoiceStore()
    store.productos["PROD1"]["actprod"] = "I"
    repo = _repo(store)
    with pytest.raises(InactiveMasterError) as exc:
        _create(repo, _body())
    assert "code" in exc.value.detail()
    assert repo.store.facventas == []


def test_missing_product_is_422_naming_line():
    repo = _repo()
    body = _body(lines=[_line(codprod="GHOST")])
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    assert any(".codprod" in key for key in exc.value.fields)
    assert repo.journal.entries == []


def test_unknown_client_is_422_naming_nitter():
    repo = _repo()
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, _body(nitter="999999999"))
    assert "nitter" in exc.value.fields
    assert repo.journal.entries == []


def test_unknown_seller_is_422():
    repo = _repo()
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, _body(nitvend="NOPE"))
    assert "nitvend" in exc.value.fields


def test_multiple_bad_lines_are_aggregated():
    repo = _repo()
    body = _body(lines=[_line(codprod="GHOST-A"),
                        _line(codprod="GHOST-B")])
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    assert len(exc.value.fields) >= 2  # aggregate, not first-fail


# ─── SI-6s2: empty / negative invoice ──────────────────────────


def test_empty_lines_rejected_by_schema():
    with pytest.raises(PydanticValidationError):
        _body(lines=[])


def test_empty_lines_defense_in_depth_at_repo():
    repo = _repo()
    body = _body().model_construct(
        nitter="222222222222", nitvend="VEN01", lines=[],
        payments=[], client_totals=None,
    )
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    assert any("lines" in key for key in exc.value.fields)
    assert repo.journal.entries == []
    assert repo.store.numbering.read("S15", "FVP").conres == BASE_CONRES


def test_negative_computed_total_is_422_nothing_reserved():
    repo = _repo()
    body = _body(lines=[_line(valuni=-100.0, dctpes=0, ivapes=0, ipopes=0)])
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    assert "totfven" in exc.value.fields
    assert repo.journal.entries == []
    assert repo.store.numbering.read("S15", "FVP").conres == BASE_CONRES


def test_nonpositive_quantity_is_422_nothing_reserved():
    repo = _repo()
    body = _body(lines=[_line(candet=0)])
    with pytest.raises(LegacyValidationError) as exc:
        _create(repo, body)
    assert any("candet" in key for key in exc.value.fields)
    assert repo.journal.entries == []


# ─── φ2 failure: window rejection journals FAILED ──────────────


def test_window_rejection_marks_journal_failed():
    store = FakeInvoiceStore()
    store.numbering.seed(ContadorRow(
        codcon="S15", descon="FACTURA DE VENTA POS", numcon=15,
        numini=1, numfin=500, numauto="SI", preres="FVP",
        conres=BASE_CONRES, actcon="S", tipclas="S15",
    ))
    repo = _repo(store)
    with pytest.raises(ResolverRangeError):
        _create(repo, _body())
    assert repo.journal.entries[0]["status"] == "FAILED"


# ─── Idempotent replay (WF-8s1 seam) ───────────────────────────


def test_replay_returns_stored_response_without_second_number():
    repo = _repo()
    first = _create(repo, _body(), req="r1")
    second = _create(repo, _body(), req="r1")
    assert first == second
    assert len(repo.store.facventas) == 1
    assert repo.store.numbering.read("S15", "FVP").conres == BASE_CONRES + 1
