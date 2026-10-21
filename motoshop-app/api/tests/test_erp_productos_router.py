"""Task 2.4 tests: productos router + inactive-master frozen seam (MW-3s3).

Scenarios (erp-masters-write):
- MW-3s3: creating a NEW transactional document against an inactive master
  rejects with 422 before φ1 via ``ensure_master_active`` (frozen contract
  copied into apply-progress.md for slice-3 + PR-3 frontend).
- MW-4: price edits record an audit trail with before/after snapshots.
- MW-6: desktop-visibility parity — edits are the same writes the desktop
  goes through, so a rename is visible through the plain read endpoint.
- Router wiring: role matrix (read everyone / write admin & gerente),
  dependency chain, audit logging, 404 for missing product.

Not covered here (slice-3): the invariant that the engine is never opened
when the seam raises — proven at the invoice-endpoint level.
"""

from __future__ import annotations

from decimal import Decimal

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
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.erp.masters.repo import (
    FakeMastersStore,
    FakeProductosRepo,
    get_productos_repo,
)
from motoshop_api.erp.masters.router import router
from motoshop_api.erp.masters.validators import ensure_master_active
from motoshop_api.main import app as production_app
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

_IDEM = "aa0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b1"
_HEADERS = {"X-Tenant": "motoshop"}


def _seed_tenant() -> None:
    tenant = Tenant(id="motoshop", nombre="M", r2_object_key="k", local_db_path="m.db")
    tenant.erp = TenantErpConfig(enabled=True, empresa="E01")
    _tenants_cache["motoshop"] = tenant


def _user(username: str, role: str, allowed_modules) -> User:
    return User(
        username=username, hashed_password="x", email=f"{username}@t.com",
        role=role, tenants_allowed=["motoshop"], allowed_modules=allowed_modules,
        source="supabase",
    )


def _token(username: str) -> str:
    return create_access_token(username, "gerente", ["motoshop"])


@pytest.fixture()
def client(monkeypatch):
    _seed_tenant()
    store = FakeMastersStore()
    repo = FakeProductosRepo(store, journal=FakeJournalRepo(), idempotency=FakeIdempotencyRepo())
    audit = FakeAuditRepo()
    app = FastAPI()
    app.include_router(router, prefix="/api", dependencies=[Depends(require_route_module)])
    app.dependency_overrides[get_productos_repo] = lambda: repo
    app.dependency_overrides[get_tenant] = lambda: "motoshop"
    app.dependency_overrides[require_erp_tenant] = lambda: _tenants_cache["motoshop"]
    app.dependency_overrides[get_audit_repo] = lambda: audit
    yield TestClient(app, raise_server_exceptions=True), store, audit
    _tenants_cache.clear()
    _users_cache.clear()


def _auth(role: str) -> dict:
    # matrix granted to all (presence of require_route_module does not decide
    # the write path); the masters-write role guard rules MW-5 outcomes.
    _users_cache[f"{role}1"] = _user(f"{role}1", role, ["erp-masters", "erp-masters-write"])
    return {"Authorization": f"Bearer {_token(f'{role}1')}"}


def _product_body(**overrides) -> dict:
    values = {
        "codprod": "PROD1", "nomprod": "Bujía NGK Ñ-P",
        "codmed": "UND", "codlin1": "L01",
        "prices": [{"codlis": "L01", "pvtipo": "1", "pvsini": "10000", "iva_rate": "19"}],
    }
    values.update(overrides)
    return values


# ═════ FROZEN cross-slice seam (MW-3s3) — slice-3 consumes this shape ═════


def test_ensure_master_active_rejects_inactive_product():
    with pytest.raises(Exception) as exc:
        ensure_master_active(
            {"codprod": "PROD9", "actprod": "I", "nomprod": "X"}, "producto"
        )
    assert exc.value.kind == "producto"
    assert exc.value.detail()["code"] == "master_inactive"


def test_ensure_master_active_accepts_active_product_and_tercero():
    ensure_master_active({"codprod": "PROD9", "actprod": "A"}, "producto")
    ensure_master_active({"nitter": "9T", "inater": "NO", "cupblo": "R"}, "tercero")


# ═════ Router wiring (guard chain, audit, 404) ═════════════════════════


def test_vendedor_403_on_product_write_even_with_module_grant(client):
    http, store, _ = client
    headers = {**_HEADERS, **_auth("vendedor"), "Idempotency-Key": _IDEM}
    ok = http.post("/api/erp/productos", json=_product_body(), headers=headers)
    assert ok.status_code == 403
    assert store.productos == {}


def test_gerente_creates_product_201_and_audits(client):
    http, store, audit = client
    headers = {**_HEADERS, **_auth("gerente"), "Idempotency-Key": _IDEM}
    response = http.post("/api/erp/productos", json=_product_body(), headers=headers)
    assert response.status_code == 201, response.text
    assert store.productos["PROD1"]["nomprod"] == "Bujía NGK Ñ-P"
    assert response.json()["prices"][0]["venprod"] == "10000.00"
    events = [e for e in audit.logs if e["target_id"] == "PROD1"]
    assert len(events) == 1


def test_missing_product_edit_returns_404(client):
    http, _, _ = client
    response = http.patch(
        "/api/erp/productos/NOEXIST", json={"nomprod": "X"}, headers=_HEADERS | _auth("gerente")
    )
    assert response.status_code == 404


def test_getters_allow_read_for_any_tenant_role(client):
    http, store, _ = client
    store.productos["PROD1"] = {
        "codprod": "PROD1", "nomprod": "Bujía NGK Ñ-P", "actprod": "A",
        "pvsini": Decimal("10000.00"), "pvconi": Decimal("11900.00"), "pvtipo": "1",
    }
    response = http.get("/api/erp/productos/PROD1", headers=_HEADERS | _auth("cajero"))
    assert response.status_code == 200
    assert response.json()["nomprod"] == "Bujía NGK Ñ-P"


# ═════ MW-4: price-edit audit before/after snapshot ═════════════════════


def test_price_edit_records_before_after_audit_snapshot(client):
    http, store, audit = client
    headers = {**_HEADERS, **_auth("gerente")}
    create = http.post(
        "/api/erp/productos", json=_product_body(), headers=headers | {"Idempotency-Key": _IDEM}
    )
    assert create.status_code == 201, create.text
    store.productos["PROD1"]["cosprod"] = 8000.0

    edit = http.patch(
        "/api/erp/productos/PROD1",
        json={"prices": [{"codlis": "L01", "pvtipo": "1", "pvsini": "12000", "iva_rate": "19"}]},
        headers=headers,
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["prices"][0]["porutil"] == "50.00"  # (12000−8000)/8000 × 100
    payload = store.productos["PROD1"]
    assert payload["pvsini"] == Decimal("12000.00")
    events = [e for e in audit.logs if e["target_id"] == "PROD1" and e["action"] == "update"]
    assert events[-1]["payload"]["before"]["pvsini"] == "10000.00"
    assert events[-1]["payload"]["after"]["pvsini"] == "12000.00"


# ═════ MW-6: desktop-visibility parity via plain read ══════════════════


def test_rename_visible_through_read_endpoint(client):
    http, store, _ = client
    store.productos["PROD1"] = {
        "codprod": "PROD1", "nomprod": "Viejo nombre", "actprod": "A",
        "pvsini": Decimal("0"), "pvconi": Decimal("0"), "pvtipo": "1",
    }
    http.patch(
        "/api/erp/productos/PROD1", json={"nomprod": "Nombre nuevo"},
        headers=_HEADERS | _auth("gerente"),
    )
    assert http.get("/api/erp/productos/PROD1", headers=_HEADERS | _auth("cajero")).json()[
        "nomprod"
    ] == "Nombre nuevo"


# ═════ Production app mount ════════════════════════════════════════════


def test_master_review_paths_mounted_on_production_app():
    paths = {getattr(r, "path", "") for r in production_app.routes}
    assert "/api/erp/productos" in paths
    assert "/api/erp/productos/{id}" in paths
