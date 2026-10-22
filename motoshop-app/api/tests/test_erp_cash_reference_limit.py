"""Hotfix S1 (task 1.2) — el ancho legacy de ``detapago.numpag``.

``detapago.numpag`` es ``varchar(20)`` y el servidor corre con
``STRICT_TRANS_TABLES``: una referencia más larga NO se recorta sola — es un
error 1406 (MySQL) que la API traduce a 503. El recorte se hace en el path
de escritura (``erp/cash/repo.py``), no en el request: la validación de
request (``max_length=40``) se mantiene igual.

Escenarios (spec erp-collections-cash, delta de la conciliación bancaria):
- una referencia de 40 caracteres responde 201 y guarda los 20 primeros;
- una referencia de 12 caracteres se guarda verbatim;
- el recorte NO altera el importe, la factura objetivo ni la fecha del documento;
- una referencia de más de 40 caracteres sigue siendo 422 de request.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.app_writes.repo import FakeAuditRepo, get_audit_repo
from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.cash.repo import FakeReceiptsRepo, get_receipts_repo
from motoshop_api.erp.cash.router import router as cash_router
from motoshop_api.erp.cash.store import FakeCashStore
from motoshop_api.erp.guards import require_erp_tenant
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

_IDEM = "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"
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


@pytest.fixture(autouse=True)
def _seed_backend_state():
    _tenants_cache.clear()
    tenant = Tenant(
        id="motoshop",
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
    )
    tenant.erp = TenantErpConfig(enabled=True, empresa="E01")
    _tenants_cache["motoshop"] = tenant
    yield
    _tenants_cache.clear()
    _users_cache.clear()


def _store() -> FakeCashStore:
    store = FakeCashStore()
    store.facventas.append(
        {
            "numfven": 100,
            "prefven": "FVP",
            "nitter": "222222222222",
            "estfven": "B",
            "codclas": "S15",
            "totfven": Decimal("150000"),
        }
    )
    store.detcuentas.append(
        {
            "numnum": "100",
            "codclas": "S15",
            "prenum": "FVP",
            "codcue": "1305",
            "valdeb": Decimal("150000"),
            "valhab": Decimal("0"),
            "nitter": "222222222222",
            "estcue": "B",
        }
    )
    return store


def _client(store: FakeCashStore) -> TestClient:
    """Production router + full guard chain; fake repos via DI overrides."""
    app = FastAPI()
    app.include_router(
        cash_router, prefix="/api", dependencies=[Depends(require_route_module)]
    )
    repo = FakeReceiptsRepo(
        store=store, journal=FakeJournalRepo(), idempotency=FakeIdempotencyRepo()
    )
    app.dependency_overrides[get_receipts_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: FakeAuditRepo()
    app.dependency_overrides[get_tenant] = lambda: "motoshop"
    app.dependency_overrides[require_erp_tenant] = lambda: _tenants_cache["motoshop"]
    return TestClient(app)


def _headers() -> dict:
    user = User(
        username="ger1",
        hashed_password="x",
        email="ger1@test.com",
        role="gerente",
        tenants_allowed=["motoshop"],
        allowed_modules=["erp-cash"],
        source="supabase",
    )
    _users_cache["ger1"] = user
    token = create_access_token("ger1", "gerente", ["motoshop"])
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant": "motoshop",
        "Idempotency-Key": _IDEM,
    }


# ─── una referencia larga se recorta, no se rechaza ──────────────


def test_receipt_con_referencia_de_40_chars_responde_201_y_guarda_los_20_primeros():
    store = _store()
    client = _client(store)
    referencia = "REF" + "0" * 37  # 40 caracteres — el límite del request

    response = client.post(
        "/api/erp/receipts",
        json={**_BODY, "referencia": referencia},
        headers=_headers(),
    )

    assert response.status_code == 201, response.text
    assert len(store.detapago) == 1
    assert store.detapago[0]["numpag"] == referencia[:20]
    assert len(store.detapago[0]["numpag"]) == 20


def test_receipt_con_referencia_de_12_chars_se_guarda_verbatim():
    store = _store()
    client = _client(store)
    referencia = "REF-00001234"

    response = client.post(
        "/api/erp/receipts",
        json={**_BODY, "referencia": referencia},
        headers=_headers(),
    )

    assert response.status_code == 201, response.text
    assert store.detapago[0]["numpag"] == referencia


def test_el_clip_no_altera_el_importe_la_factura_ni_la_fecha():
    store = _store()
    client = _client(store)
    referencia = "REF" + "0" * 37

    response = client.post(
        "/api/erp/receipts",
        json={**_BODY, "referencia": referencia},
        headers=_headers(),
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["valor"] == "150000"
    assert payload["documento"] == {"numfven": 100, "prefven": "FVP"}
    row = store.detapago[0]
    assert row["valpag"] == Decimal("150000")
    assert row["fecdoc"] == date(2025, 2, 10)
    assert row["numnum"] == "101"


def test_una_referencia_de_mas_de_40_chars_sigue_siendo_422():
    store = _store()
    client = _client(store)

    response = client.post(
        "/api/erp/receipts",
        json={**_BODY, "referencia": "R" * 41},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert store.detapago == []
