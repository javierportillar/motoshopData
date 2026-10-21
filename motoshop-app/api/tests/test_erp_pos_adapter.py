"""Task: the POS adapter — the web POS screen -> the transactional engine.

The POS screen posts its own payload to ``POST /api/pos/sales``. Before
this adapter the route did not exist, so every sale was silently queued
as "offline" and never reached the legacy ledger.

Scenarios:
- The POS payload is mapped onto the invoice contract (legacy field names
  ``candet``/``valuni``/``dctpes``/``ivapes``/``ipopes``) and the sale is
  written to ``facventas``/``detfventas``/``detapago`` with the numbering
  reserved from ``contadores`` and the journal COMMITTED.
- The payment methods map to the legacy ``formapago`` codes (F01/F03/F07/F10).
- The client NIT comes from ``customer.nit`` (the "CF-" prefix of the
  consumer final is stripped) and the seller is the company.
- The idempotency key may arrive as ``Idempotency-Key`` or
  ``X-Idempotency-Key`` (the POS screen uses the latter) and the replay
  does not create a second document.
- An unknown product is rejected 422 naming the line, and nothing is written.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.guards import require_erp_tenant
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.invoicing.repo import (
    FakeInvoicesRepo,
    FakeInvoiceStore,
    get_invoices_repo,
)
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.pos.router import router as pos_router
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

_IDEM = "9b0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"

_BODY = {
    "id": _IDEM,
    "documentType": "POS",
    "customer": {"id": "CF-222222222222", "nit": "222222222222", "name": "CONSUMIDOR FINAL"},
    "items": [
        {
            "product": {"sku": "PROD1", "name": "Bujía NGK", "unit": "UND"},
            "candet": 3,
            "valuni": 10000.50,
            "dctpes": 500.25,
            "ivapes": 950.05,
            "ipopes": 0,
        }
    ],
    "payments": [{"method": "EFECTIVO", "amount": 31350.90}],
    "cashier": "cajero1",
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


def _client(store: FakeInvoiceStore | None = None, journal=None):
    store = store or FakeInvoiceStore()
    journal = journal or FakeJournalRepo()
    app = FastAPI()
    app.include_router(
        pos_router, prefix="", dependencies=[Depends(require_route_module)]
    )
    repo = FakeInvoicesRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )
    app.dependency_overrides[get_invoices_repo] = lambda: repo
    app.dependency_overrides[get_tenant] = lambda: "motoshop"
    app.dependency_overrides[require_erp_tenant] = lambda: _tenants_cache["motoshop"]
    user = User(
        username="cajero1",
        hashed_password="x",
        email="cajero1@test.com",
        role="vendedor",
        tenants_allowed=["motoshop"],
        allowed_modules=["erp-invoicing"],
        source="supabase",
    )
    _users_cache["cajero1"] = user
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), store, journal


def _headers(key: str = _IDEM, header: str = "X-Idempotency-Key") -> dict:
    token = create_access_token("cajero1", "vendedor", ["motoshop"])
    return {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop", header: key}


# ─── the sale lands in the legacy ledger ───────────────────────


def test_pos_sale_is_written_to_the_legacy_tables():
    client, store, journal = _client()
    response = client.post("/api/pos/sales", json=_BODY, headers=_headers())
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["numfven"] == 501
    assert payload["prefven"] == "FVP"
    assert payload["totals"]["totfven"] == "31350.90"  # Decimal -> str (never float)

    assert len(store.facventas) == 1
    header = store.facventas[0]
    assert header["numfven"] == 501
    assert header["nitter"] == "222222222222"
    assert header["clifven"] == "CONSUMIDOR FINAL"
    assert len(store.detfventas) == 1
    assert store.detfventas[0]["totdet"] == Decimal("31350.90")
    assert len(store.detapago) == 1
    assert store.detapago[0]["codpag"] == "F01"
    assert journal.entries[-1]["status"] == "COMMITTED"


def test_payment_methods_map_to_the_legacy_forms():
    client, store, _journal = _client()
    body = {
        **_BODY,
        "payments": [
            {"method": "EFECTIVO", "amount": 10000},
            {"method": "DATAFONO", "amount": 10000},
            {"method": "TRANSFERENCIA", "amount": 11350.90},
        ],
    }
    response = client.post("/api/pos/sales", json=body, headers=_headers())
    assert response.status_code == 201, response.text
    forms = sorted(row["codpag"] for row in store.detapago)
    assert forms == ["F01", "F03", "F07"]


def test_consumer_final_prefix_is_stripped():
    client, store, _journal = _client()
    body = {**_BODY, "customer": {"id": "CF-222222222222", "nit": "CF-222222222222"}}
    response = client.post("/api/pos/sales", json=body, headers=_headers())
    assert response.status_code == 201, response.text
    assert store.facventas[0]["nitter"] == "222222222222"


def test_idempotency_key_is_accepted_in_both_headers():
    client, store, _journal = _client()
    first = client.post("/api/pos/sales", json=_BODY, headers=_headers())
    second = client.post("/api/pos/sales", json=_BODY, headers=_headers())
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["numfven"] == second.json()["numfven"]
    assert len(store.facventas) == 1

    # the same key under the canonical header name replays too
    third = client.post(
        "/api/pos/sales", json=_BODY, headers=_headers(header="Idempotency-Key")
    )
    assert third.json()["numfven"] == first.json()["numfven"]
    assert len(store.facventas) == 1


def test_unknown_product_is_422_and_nothing_is_written():
    client, store, journal = _client()
    body = {
        **_BODY,
        "items": [{**_BODY["items"][0], "product": {"sku": "GHOST", "name": "X"}}],
    }
    response = client.post("/api/pos/sales", json=body, headers=_headers())
    assert response.status_code == 422, response.text
    assert store.facventas == []
    assert journal.entries == []


def test_empty_cart_is_422():
    client, store, _journal = _client()
    response = client.post(
        "/api/pos/sales", json={**_BODY, "items": []}, headers=_headers()
    )
    assert response.status_code == 422
    assert store.facventas == []
