"""Hotfix S1 (task 1.1) — el saldo abierto contra la cartera real.

La causación de la factura escribe la cuenta de cartera real ``13050501``
(``erp/invoicing/repo.py``), pero los recibos acreditaban el alias legacy
``1305``: como ``detcuentas.codcue`` se comparaba con igualdad exacta, el
saldo disponible se leía 0 en producción.

Escenarios (spec erp-collections-cash, delta de la conciliación bancaria):
- el saldo abierto lee la cuenta canónica ``13050501``;
- el saldo abierto suma el alias legacy ``1305`` (filas escritas antes del fix);
- una fila de otra cuenta (``1105``) NO entra en el saldo de cartera;
- un recibo sobre una factura sembrada en el alias legacy cierra el saldo a
  cero y deja el journal COMMITTED.
"""

from __future__ import annotations

from decimal import Decimal

from motoshop_api.erp.cash.repo import FakeReceiptsRepo, open_balance
from motoshop_api.erp.cash.schemas import ReceiptCreate
from motoshop_api.erp.cash.store import FakeCashStore
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
    "concepto": "ABONO CARTERA",
}


def _store(rows: list[tuple[str, str]]) -> FakeCashStore:
    """Invoice whose ledger rows live on the given ``(codcue, valdeb)`` pairs."""
    store = FakeCashStore()
    store.facventas.append(
        {
            "numfven": 100,
            "prefven": "FVP",
            "nitter": "222222222222",
            "estfven": "B",
            "codclas": "S15",
            "totfven": Decimal("0"),
        }
    )
    for codcue, valdeb in rows:
        store.detcuentas.append(
            {
                "numnum": "100",
                "codclas": "S15",
                "prenum": "FVP",
                "codcue": codcue,
                "valdeb": Decimal(valdeb),
                "valhab": Decimal("0"),
                "nitter": "222222222222",
                "estcue": "B",
            }
        )
    return store


def _repo(store: FakeCashStore, journal: FakeJournalRepo | None = None):
    journal = journal or FakeJournalRepo()
    return (
        FakeReceiptsRepo(
            store=store, journal=journal, idempotency=FakeIdempotencyRepo()
        ),
        journal,
    )


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


# ─── la cuenta canónica entra en el saldo ────────────────────────


def test_open_balance_lee_la_cuenta_cartera_canonica_13050501():
    store = _store([("13050501", "150000")])

    assert open_balance(store, 100) == Decimal("150000")


# ─── el alias legacy también entra en el saldo ───────────────────


def test_open_balance_suma_el_alias_1305():
    store = _store([("1305", "150000")])

    assert open_balance(store, 100) == Decimal("150000")


def test_open_balance_suma_las_cuentas_canonica_y_legacy():
    store = _store([("1305", "150000"), ("13050501", "50000")])

    assert open_balance(store, 100) == Decimal("200000")


# ─── otra cuenta NO entra en el saldo de cartera ─────────────────


def test_open_balance_de_otra_cuenta_no_entra():
    store = _store([("1105", "150000")])

    assert open_balance(store, 100) == Decimal("0")


# ─── el recibo cierra el saldo sembrado en el alias legacy ───────


def test_receipt_sobre_factura_con_alias_1305_cierra_el_saldo_a_cero():
    store = _store([("1305", "150000")])
    repo, journal = _repo(store)

    response = _create(repo)

    assert response["saldo_anterior"] == "150000"
    assert response["saldo_actual"] == "0"
    assert open_balance(store, 100) == Decimal("0")
    assert [entry["status"] for entry in journal.entries] == ["COMMITTED"]


def test_se_puede_cobrar_una_factura_causada_en_la_cuenta_canonica():
    store = _store([("13050501", "150000")])
    repo, _journal = _repo(store)

    response = _create(repo)

    assert response["saldo_anterior"] == "150000"
    assert response["saldo_actual"] == "0"
    assert open_balance(store, 100) == Decimal("0")


def test_el_recibo_reduce_el_saldo_exacto_sin_contar_dos_veces():
    store = _store([("1305", "150000"), ("13050501", "50000")])
    repo, _journal = _repo(store)

    response = _create(repo, {"valor": "150000"})

    assert response["saldo_anterior"] == "200000"
    assert response["saldo_actual"] == "50000"
    assert open_balance(store, 100) == Decimal("50000")


def test_el_recibo_nunca_escribe_en_el_alias_legacy():
    """Las filas nuevas van a la cuenta canónica; el alias solo se lee."""
    store = _store([("1305", "150000"), ("13050501", "50000")])
    repo, _journal = _repo(store)

    _create(repo, {"valor": "150000"})

    credit = [r for r in store.detcuentas if r["valhab"] == Decimal("150000")]
    assert len(credit) == 1
    assert credit[0]["codcue"] == "13050501"
    legacy = [r for r in store.detcuentas if r["codcue"] == "1305"]
    assert len(legacy) == 1
    assert legacy[0]["valdeb"] == Decimal("150000")
