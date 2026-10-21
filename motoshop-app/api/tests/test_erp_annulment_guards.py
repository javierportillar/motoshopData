"""Task 5.1-5.4 tests: the legacy annulment guard chain and the full reversal.

Scenarios (erp-document-annulment):
- AN-1s1: an already annulled document is rejected 409 (Veri_Anul) and the
  audit row is NOT duplicated.
- AN-1s2: a document whose date falls inside a closed period is rejected
  409 (Hay_Cie_Eli) — nothing is written.
- AN-1s3: a document already accepted by the DIAN (estfele 1/2) is rejected
  409 (Valid_EdiDocele).
- AN-1s4: the role gate rejects a role without the annulment permission.
- AN-1s5: the reason is mandatory (422 naming the reason field).
- AN-2s1..s3: the reversal flips the document state, annuls the accounting
  entries and writes the `motanudoc` audit row in ONE journaled unit of work.
- AN-3s1/AN-3s2: the stock is recomputed from the KARDEX truth (the signed
  movements), not from a cached balance.
- AN-4s1/AN-4s2: the audit row carries the reason, the document class and
  the annulment date; the replay is idempotent.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from motoshop_api.erp.annulment.repo import (
    AlreadyAnnulledError,
    AnnulmentForbiddenError,
    DocumentNotFoundError,
    ElectronicDocumentError,
    FakeAnnulmentRepo,
)
from motoshop_api.erp.annulment.schemas import AnnulmentRequest
from motoshop_api.erp.annulment.store import FakeAnnulmentStore
from motoshop_api.erp.guards import PeriodLockedError
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError

KEY = "3c4d5e6f-7a8b-4c1d-9e2f-3a4b5c6d7e8f"
KEY_2 = "4d5e6f7a-8b9c-4d1e-9f2a-3a4b5c6d7e8f"


def _store() -> FakeAnnulmentStore:
    store = FakeAnnulmentStore()
    store.facventas.append(
        {
            "numfven": "501",
            "codclas": "S15",
            "prefven": "FVP",
            "pref": "FVP",
            "fecfven": date(2026, 3, 10),
            "nitter": "222222222222",
            "nitvend": "VEN01",
            "estado": "B",
            "estfven": "B",
            "estfin": "B",
            "totfven": Decimal("31350.90"),
        }
    )
    store.detfventas.append(
        {
            "numfven": "501",
            "numlin": 1,
            "codprod": "PROD1",
            "candet": Decimal("3"),
            "valuni": Decimal("10000.50"),
            "totdet": Decimal("31350.90"),
        }
    )
    store.detapago.append(
        {"numfven": "501", "codpag": "F01", "valpag": Decimal("31350.90")}
    )
    store.detcuentas.append(
        {
            "numnum": "501",
            "codclas": "S15",
            "prenum": "FVP",
            "codcue": "1305",
            "valdeb": Decimal("31350.90"),
            "valhab": Decimal("0"),
            "candet": Decimal("3"),
            "codprod": "PROD1",
            "estcue": "B",
        }
    )
    store.productos["PROD1"] = {
        "codprod": "PROD1",
        "exiprod": Decimal("120"),
    }
    return store


def _repo(store: FakeAnnulmentStore | None = None) -> FakeAnnulmentRepo:
    store = store or _store()
    return FakeAnnulmentRepo(
        store=store, journal=FakeJournalRepo(), idempotency=FakeIdempotencyRepo()
    )


def _body(motivo: str = "Error de digitacion en el precio") -> AnnulmentRequest:
    return AnnulmentRequest(motivo=motivo)


def _annul(
    repo: FakeAnnulmentRepo,
    body: AnnulmentRequest | None = None,
    key: str = KEY,
    req: str = "r-1",
    role: str = "gerente",
):
    return repo.annul(
        body or _body(),
        codclas="S15",
        numfven=501,
        tenant="motoshop",
        empresa="E01",
        actor="ger1",
        actor_role=role,
        request_id=req,
        idempotency_key=key,
    )


# ─── AN-1s1: already annulled ──────────────────────────────────


def test_already_annulled_document_is_rejected():
    store = _store()
    store.facventas[0]["estado"] = "A"
    store.facventas[0]["estfven"] = "A"
    repo = _repo(store)
    with pytest.raises(AlreadyAnnulledError):
        _annul(repo)
    assert store.motanudoc == []


def test_unknown_document_is_rejected():
    repo = _repo()
    with pytest.raises(DocumentNotFoundError):
        repo.annul(
            _body(),
            codclas="S15",
            numfven=999,
            tenant="motoshop",
            empresa="E01",
            actor="ger1",
            actor_role="gerente",
            request_id="r-1",
            idempotency_key=KEY,
        )


# ─── AN-1s2: closed period (Hay_Cie_Eli) ───────────────────────


def test_document_inside_closed_period_is_rejected():
    store = _store()
    store.cierresper.append(
        {
            "codcie": 1,
            "fecdes": date(2026, 3, 1),
            "fechas": date(2026, 3, 31),
            "tipcie": "P",
        }
    )
    repo = _repo(store)
    with pytest.raises(PeriodLockedError):
        _annul(repo)
    assert store.motanudoc == []
    assert store.facventas[0]["estado"] == "B"


# ─── AN-1s3: electronic document already accepted ──────────────


def test_electronic_document_accepted_is_rejected():
    store = _store()
    store.facventas[0]["estfele"] = "1"
    repo = _repo(store)
    with pytest.raises(ElectronicDocumentError):
        _annul(repo)
    assert store.motanudoc == []


# ─── AN-1s4: the role gate ─────────────────────────────────────


def test_role_without_annulment_permission_is_rejected():
    repo = _repo()
    with pytest.raises(AnnulmentForbiddenError):
        _annul(repo, role="consulta")
    assert repo.store.motanudoc == []


# ─── AN-1s5: the reason is mandatory ───────────────────────────


def test_reason_is_mandatory():
    repo = _repo()
    with pytest.raises(LegacyValidationError):
        _annul(repo, AnnulmentRequest(motivo=""))


# ─── AN-2s1..s3 + AN-4s1/AN-4s2: the full reversal ────────────


def test_reversal_annuls_the_document_and_writes_the_audit_row():
    store = _store()
    repo = _repo(store)
    response = _annul(repo)
    assert response["estado"] == "A"
    assert len(store.motanudoc) == 1
    audit = store.motanudoc[0]
    assert str(audit["numnum"]) == "501"
    assert audit["codclas"] == "S15"
    assert "digitacion" in str(audit["motanu"])


def test_journal_leads_the_annulment_and_commits():
    store = _store()
    journal = FakeJournalRepo()
    repo = FakeAnnulmentRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )
    _annul(repo)
    assert journal.entries[-1]["status"] in {"COMMITTED", "ANNULLED"}
    assert journal.entries[-1]["doc_type"] == "anulacion_documento"


# ─── AN-3s1/AN-3s2: the stock comes from the kardex truth ──────


def test_stock_is_recomputed_from_the_kardex_movements():
    store = _store()
    # the kardex truth: one movement of 30 units for PROD1
    store.detcuentas.append(
        {
            "numnum": "900",
            "codclas": "S15",
            "prenum": "FVP",
            "codcue": "1305",
            "valdeb": Decimal("30000"),
            "valhab": Decimal("0"),
            "candet": Decimal("30"),
            "codprod": "PROD1",
            "estcue": "B",
        }
    )
    repo = _repo(store)
    _annul(repo)
    assert store.productos["PROD1"]["exiprod"] == Decimal("30")


def test_stock_balance_does_not_just_subtract_the_annulled_quantity():
    store = _store()
    store.detcuentas.append(
        {
            "numnum": "901",
            "codclas": "S15",
            "prenum": "FVP",
            "codcue": "1305",
            "valdeb": Decimal("30000"),
            "valhab": Decimal("0"),
            "candet": Decimal("30"),
            "codprod": "PROD1",
            "estcue": "B",
        }
    )
    repo = _repo(store)
    _annul(repo)
    assert store.productos["PROD1"]["exiprod"] != Decimal("117")


# ─── AN-4s2: the replay is idempotent ──────────────────────────


def test_replay_returns_the_stored_response_without_a_second_audit_row():
    store = _store()
    repo = _repo(store)
    first = _annul(repo, req="r-1", key=KEY)
    second = _annul(repo, req="r-1", key=KEY)
    assert first == second
    assert len(store.motanudoc) == 1
