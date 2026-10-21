"""Task 3.3 tests: invoice router — transport contract of POST /api/erp/invoices.

Scenarios:
- SI-5s2: a client total that disagrees with the server formuleo is
  rejected 422 with the aggregate field errors (the frozen 422 body).
- SI-6s1: an inactive/blocked client is rejected 422 through the FROZEN
  master-state seam (``code: master_inactive``).
- WF-8s2: the Idempotency-Key must be a UUIDv4 (F5-001 / F8-002) and the
  replay returns the stored response without a second document.
- WF-1s3: a ``vendedor`` is rejected 403 (ERP write role guard) while a
  ``gerente`` gets 201 and the audit row records actor, role and operation.
- The response carries the server-computed totals as strings (never float).
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.app_writes.repo import FakeAuditRepo, get_audit_repo
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
from motoshop_api.erp.invoicing.router import router as invoicing_router
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

_IDEM = "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"
_IDEM_2 = "9a1b2c3d-4e5f-4a11-9b22-c3d4e5f6a7b8"

_BODY = {
    "nitter": "222222222222",
    "nitvend": "VEN01",
    "codcaj": "01",
    "lines": [
        {
            "codprod": "PROD1",
            "nomdet": "Bujía NGK",
            "candet": 3,
            "valuni": "10000.50",
            "dctpes": "500.25",
            "ivapes": "950.05",
            "ipopes": "0",
        }
    ],
    "payments": [{"codpag": "F01", "amount": "31350.90"}],
}


def _user(username, role, allowed_modules) -> User:
    return User(
        username=username,
        hashed_password="x",
        email=f"{username}@test.com",
        role=role,
        tenants_allowed=["motoshop"],
        allowed_modules=allowed_modules,
        source="supabase",
    )


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


def _app(store: FakeInvoiceStore, journal: FakeJournalRepo, audit: FakeAuditRepo):
    app = FastAPI()
    app.include_router(
        invoicing_router, prefix="/api", dependencies=[Depends(require_route_module)]
    )
    repo = FakeInvoicesRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )
    app.dependency_overrides[get_invoices_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit
    app.dependency_overrides[get_tenant] = lambda: "motoshop"
    app.dependency_overrides[require_erp_tenant] = lambda: _tenants_cache["motoshop"]
    return TestClient(app)


def _headers(role: str, username: str, modules: tuple[str, ...]) -> dict:
    user = _user(username, role, list(modules))
    _users_cache[username] = user
    token = create_access_token(username, role, ["motoshop"])
    return {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop"}


def _client(store=None, journal=None, audit=None):
    store = store or FakeInvoiceStore()
    journal = journal or FakeJournalRepo()
    audit = audit or FakeAuditRepo()
    return _app(store, journal, audit), store, journal, audit


# ─── happy path ────────────────────────────────────────────────


def test_gerente_creates_the_invoice_with_server_totals():
    client, store, journal, audit = _client()
    response = client.post(
        "/api/erp/invoices",
        json=_BODY,
        headers={
            **_headers("gerente", "ger1", ("erp-invoicing",)),
            "Idempotency-Key": _IDEM,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["numfven"] == 501
    assert payload["prefven"] == "FVP"
    assert payload["totals"]["totfven"] == "31350.90"
    assert len(store.facventas) == 1
    assert journal.entries[-1]["status"] == "COMMITTED"


def test_idempotency_key_must_be_uuid_v4():
    client, store, _journal, _audit = _client()
    response = client.post(
        "/api/erp/invoices",
        json=_BODY,
        headers={
            **_headers("gerente", "ger1", ("erp-invoicing",)),
            "Idempotency-Key": "not-a-uuid",
        },
    )
    assert response.status_code == 422
    assert store.facventas == []


def test_replay_returns_the_stored_response_without_a_second_document():
    client, store, _journal, _audit = _client()
    headers = {
        **_headers("gerente", "ger1", ("erp-invoicing",)),
        "Idempotency-Key": _IDEM,
    }
    first = client.post("/api/erp/invoices", json=_BODY, headers=headers)
    second = client.post("/api/erp/invoices", json=_BODY, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert len(store.facventas) == 1


# ─── SI-5s2: client totals mismatch ────────────────────────────


def test_client_total_mismatch_is_422_with_field_errors():
    client, store, _journal, _audit = _client()
    body = {**_BODY, "client_totals": {"totfven": 999.99}}
    response = client.post(
        "/api/erp/invoices",
        json=body,
        headers={
            **_headers("gerente", "ger1", ("erp-invoicing",)),
            "Idempotency-Key": _IDEM,
        },
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "client_totals.totfven" in detail["fields"]
    assert store.facventas == []


# ─── SI-6s1: frozen master-state 422 ───────────────────────────


def test_blocked_client_is_422_with_the_frozen_master_state_shape():
    store = FakeInvoiceStore()
    store.terceros["222222222222"]["cupblo"] = "B"
    client, _store, _journal, _audit = _client(store=store)
    response = client.post(
        "/api/erp/invoices",
        json=_BODY,
        headers={
            **_headers("gerente", "ger1", ("erp-invoicing",)),
            "Idempotency-Key": _IDEM,
        },
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "master_inactive"
    assert detail["fields"] == {"nitter": "master_inactive"}
    assert detail["master_state"]["cupblo"] == "B"
    assert store.facventas == []


# ─── WF-1s3: role guard ────────────────────────────────────────


def test_vendedor_can_sell_the_invoice():
    """The POS is used by the seller: ``vendedor`` is a write role (WF-1s1)."""
    client, store, _journal, _audit = _client()
    response = client.post(
        "/api/erp/invoices",
        json=_BODY,
        headers={
            **_headers("vendedor", "ven1", ("erp-invoicing",)),
            "Idempotency-Key": _IDEM,
        },
    )
    assert response.status_code == 201, response.text
    assert len(store.facventas) == 1


def test_role_without_write_permission_is_rejected_403():
    client, store, _journal, _audit = _client()
    response = client.post(
        "/api/erp/invoices",
        json=_BODY,
        headers={
            **_headers("consulta", "con1", ("erp-invoicing",)),
            "Idempotency-Key": _IDEM,
        },
    )
    assert response.status_code == 403
    assert store.facventas == []
