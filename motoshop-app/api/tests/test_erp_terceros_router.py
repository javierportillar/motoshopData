"""Task 2.2 tests: terceros router — role gating (MW-5) + audit trail (MW-4).

Scenarios (erp-masters-write):
- MW-5: vendedor GET reads masters; POST/PATCH → 403 and nothing changes —
  even if the access matrix granted the write module (server-side role parity).
- MW-4: every create/edit appends one `app_audit_log` row with actor, action,
  target key and before/after snapshot; legacy `motanudoc` is untouched (its
  contract is reserved for document annulment — masters never write it).
- Matrix integration (WF-2s1/s2): the erp route entries resolve through
  route_modules() and deny BEFORE business validation.

The full production guard chain runs: JWT (HTTPBearer) → require_route_module
→ require_erp_tenant → require_erp_masters_write. Only the repos/audit are
fakes (dependency overrides).
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.app_writes.repo import FakeAuditRepo, get_audit_repo
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.guards import require_erp_masters_write, require_erp_tenant
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.repo import FakeMastersStore, FakeTercerosRepo, get_terceros_repo
from motoshop_api.erp.masters.router import router as terceros_router
from motoshop_api.erp.masters.schemas import TerceroCreate
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

_IDEM = "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"
_BODY = {
    "nitter": "900123456", "tipnit": "N", "digter": "8", "perjur": "S",
    "apeter": "Garcés", "nomter": "Andrés", "dirter": "Cra 5 #20-10",
    "telter": "3012345678", "emails": ["aj@example.com"],
}


def _user(username, role, allowed_modules) -> User:
    return User(
        username=username, hashed_password="x", email=f"{username}@test.com",
        role=role, tenants_allowed=["motoshop"], allowed_modules=allowed_modules,
        source="supabase",
    )


@pytest.fixture(autouse=True)
def _seed_backend_state():
    _tenants_cache.clear()
    tenant = Tenant(
        id="motoshop", nombre="MotoShop", r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
    )
    tenant.erp = TenantErpConfig(enabled=True, empresa="E01")
    _tenants_cache["motoshop"] = tenant
    yield
    _tenants_cache.clear()
    _users_cache.clear()


def _app(store: FakeMastersStore, journal: FakeJournalRepo, audit: FakeAuditRepo) -> TestClient:
    """Production router + full guard chain; fake repos via DI overrides."""
    app = FastAPI()
    app.include_router(
        terceros_router, prefix="/api", dependencies=[Depends(require_route_module)]
    )
    repo = FakeTercerosRepo(store=store, journal=journal, idempotency=FakeIdempotencyRepo())
    app.dependency_overrides[get_terceros_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit
    app.dependency_overrides[get_tenant] = lambda: "motoshop"
    app.dependency_overrides[require_erp_tenant] = lambda: _tenants_cache["motoshop"]
    return TestClient(app)


def _headers(role: str, username: str, modules: tuple[str, ...]) -> dict:
    user = _user(username, role, list(modules))
    _users_cache[username] = user
    token = create_access_token(username, role, ["motoshop"])
    return {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop"}


# ─── MW-5: vendedor read-only ──────────────────────────────────


def test_vendedor_reads_terceros_but_write_is_403_and_no_op():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    audit = FakeAuditRepo()
    client = _app(store, journal, audit)

    get = client.get(
        "/api/erp/terceros",
        headers=_headers("vendedor", "ven1", ("erp-masters",)),
    )
    assert get.status_code == 200  # reads stay open to all tenant roles
    assert get.json() == []

    post = client.post(
        "/api/erp/terceros",
        json=_BODY,
        headers={**_headers("vendedor", "ven1", ("erp-masters",)), "Idempotency-Key": _IDEM},
    )
    patch = client.patch(
        "/api/erp/terceros/900123456",
        json={"dirter": "otra"},
        headers=_headers("vendedor", "ven1", ("erp-masters", "erp-masters-write")),
    )
    assert post.status_code == 403
    assert patch.status_code == 403  # role parity: matrix grant cannot override it
    assert store.terceros == {}
    assert audit.logs == []


# ─── MW-5 write path happy + audit (MW-4) ──────────────────────


def test_gerente_create_201_journaled_and_audited():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    audit = FakeAuditRepo()
    client = _app(store, journal, audit)

    response = client.post(
        "/api/erp/terceros",
        json=_BODY,
        headers={
            **_headers("gerente", "ger1", ("erp-masters", "erp-masters-write")),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["nitter"] == "900123456"
    assert [e["status"] for e in journal.entries] == ["COMMITTED"]
    assert len(audit.logs) == 1
    log = audit.logs[0]
    assert log["user_id"] == "ger1"
    assert log["user_role"] == "gerente"
    assert log["action"] == "create"
    assert log["target_type"] == "tercero"
    assert log["target_id"] == "900123456"
    assert log["payload"]["after"]["nomcom"] == "Andrés Garcés"
    assert log["status"] == "success"


def test_gerente_edit_records_before_after_snapshot():
    store = FakeMastersStore()
    journal = FakeJournalRepo()
    audit = FakeAuditRepo()
    repo = FakeTercerosRepo(store=store, journal=journal, idempotency=FakeIdempotencyRepo())
    repo.create(
        TerceroCreate(**_BODY), tenant="motoshop", empresa="E01",
        actor="seed", request_id="r0", idempotency_key=_IDEM,
    )
    client = _app(store, journal, audit)
    client.app.dependency_overrides[get_terceros_repo] = lambda: repo

    response = client.patch(
        "/api/erp/terceros/900123456",
        json={"dirter": "Av Perú 555"},
        headers=_headers("gerente", "ger2", ("erp-masters", "erp-masters-write")),
    )

    assert response.status_code == 200, response.text
    assert response.json()["dirter"] == "Av Perú 555"
    assert len(audit.logs) == 1
    log = audit.logs[0]
    assert log["action"] == "update"
    assert log["target_type"] == "tercero"
    assert log["target_id"] == "900123456"
    assert log["payload"]["before"]["dirter"] == "Cra 5 #20-10"
    assert log["payload"]["after"]["dirter"] == "Av Perú 555"


# ─── HTTP error contract shapes ────────────────────────────────


def test_duplicate_nitter_http_409_names_the_field():
    store = FakeMastersStore()
    store.terceros["900123456"] = {"nitter": "900123456", "nomcom": "Existente"}
    audit = FakeAuditRepo()
    client = _app(store, FakeJournalRepo(), audit)

    response = client.post(
        "/api/erp/terceros",
        json=_BODY,
        headers={
            **_headers("gerente", "ger3", ("erp-masters", "erp-masters-write")),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["field"] == "nitter"
    assert audit.logs == []  # rejected writes record no success audit row


def test_checksum_failure_http_422_is_aggregate():
    store = FakeMastersStore()
    audit = FakeAuditRepo()
    client = _app(store, FakeJournalRepo(), audit)

    response = client.post(
        "/api/erp/terceros",
        json={**_BODY, "digter": "7", "dirter": "", "telter": ""},
        headers={
            **_headers("gerente", "ger4", ("erp-masters", "erp-masters-write")),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 422
    fields = response.json()["detail"]["fields"]
    assert set(fields) >= {"digter", "dirter", "telter"}


def test_missing_tercero_edit_returns_404():
    store = FakeMastersStore()
    client = _app(store, FakeJournalRepo(), FakeAuditRepo())

    response = client.patch(
        "/api/erp/terceros/000000000",
        json={"dirter": "x"},
        headers=_headers("gerente", "ger5", ("erp-masters", "erp-masters-write")),
    )
    assert response.status_code == 404


# ─── Router registration in the production app ─────────────────


def test_production_app_mounts_terceros_router():
    from motoshop_api.main import app as production_app

    paths = {getattr(route, "path", "") for route in production_app.routes}
    assert "/api/erp/terceros" in paths
    assert "/api/erp/terceros/{id}" in paths
