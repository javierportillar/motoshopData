"""Task 4.2 tests: cash router — role gating (WF-1s3) + matrix (WF-2s1).

Scenarios:
- WF-1s3: collections writes are admin/gerente only — a ``gerente`` creates
  the receipt (201) and the audit row records actor, role and operation;
  a ``vendedor`` is rejected 403 even when the matrix grants the module.
- WF-2s1: the ``erp-cash`` module is disabled for the user → 403 with the
  explicit reason, and the request never reaches the repo.
- The Idempotency-Key must be a UUIDv4 (F5-001 / F8-002 convention).

The full production guard chain runs: JWT (HTTPBearer) → require_route_module
→ require_erp_tenant → require_erp_collections_write. Only the repos/audit
are fakes (dependency overrides).
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


def _app(store: FakeCashStore, journal: FakeJournalRepo, audit: FakeAuditRepo):
    """Production router + full guard chain; fake repos via DI overrides."""
    app = FastAPI()
    app.include_router(
        cash_router, prefix="/api", dependencies=[Depends(require_route_module)]
    )
    repo = FakeReceiptsRepo(
        store=store, journal=journal, idempotency=FakeIdempotencyRepo()
    )
    app.dependency_overrides[get_receipts_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit
    app.dependency_overrides[get_tenant] = lambda: "motoshop"
    app.dependency_overrides[require_erp_tenant] = lambda: _tenants_cache["motoshop"]
    return TestClient(app)


def _headers(role: str, username: str, modules: tuple[str, ...]) -> dict:
    user = _user(username, role, list(modules))
    _users_cache[username] = user
    token = create_access_token(username, role, ["motoshop"])
    return {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop"}


# ─── WF-1s3: gerente writes, audit records actor+role+operation ──


def test_wf1s3_gerente_creates_the_receipt_and_the_audit_records_the_operation():
    store = _store()
    journal = FakeJournalRepo()
    audit = FakeAuditRepo()
    client = _app(store, journal, audit)

    response = client.post(
        "/api/erp/receipts",
        json=_BODY,
        headers={
            **_headers("gerente", "ger1", ("erp-cash",)),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["saldo_actual"] == "0"
    assert payload["pref"] == "RC"
    assert [entry["status"] for entry in journal.entries] == ["COMMITTED"]
    assert len(audit.logs) == 1
    log = audit.logs[0]
    assert log["user_id"] == "ger1"
    assert log["user_role"] == "gerente"
    assert log["action"] == "create"
    assert log["target_type"] == "recibo_caja"
    assert log["target_id"] == str(payload["numero"])
    assert log["status"] == "success"


def test_wf1s3_vendedor_is_403_even_with_the_matrix_module_granted():
    store = _store()
    audit = FakeAuditRepo()
    client = _app(store, FakeJournalRepo(), audit)

    response = client.post(
        "/api/erp/receipts",
        json=_BODY,
        headers={
            **_headers("vendedor", "ven1", ("erp-cash",)),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 403
    assert store.detapago == []
    assert audit.logs == []


# ─── WF-2s1: the module matrix denies BEFORE the repo runs ──────


def test_wf2s1_collections_module_disabled_is_403_with_an_explicit_reason():
    store = _store()
    audit = FakeAuditRepo()
    client = _app(store, FakeJournalRepo(), audit)

    response = client.post(
        "/api/erp/receipts",
        json=_BODY,
        headers={
            **_headers("gerente", "ger2", ("erp-masters",)),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 403
    assert "erp-cash" in str(response.json()["detail"])
    assert store.detapago == []
    assert audit.logs == []


# ─── HTTP contract details ───────────────────────────────────────


def test_invalid_idempotency_key_is_422():
    store = _store()
    client = _app(store, FakeJournalRepo(), FakeAuditRepo())

    response = client.post(
        "/api/erp/receipts",
        json=_BODY,
        headers={
            **_headers("gerente", "ger3", ("erp-cash",)),
            "Idempotency-Key": "not-a-uuid",
        },
    )

    assert response.status_code == 422
    assert store.detapago == []


def test_annulled_target_is_409_through_the_router():
    store = _store()
    store.facventas[0]["estfven"] = "A"
    client = _app(store, FakeJournalRepo(), FakeAuditRepo())

    response = client.post(
        "/api/erp/receipts",
        json=_BODY,
        headers={
            **_headers("gerente", "ger4", ("erp-cash",)),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "document_annulled"


def test_locked_period_is_409_through_the_router():
    from datetime import date

    store = _store()
    store.cierresper.append(
        {
            "codcie": 1,
            "fecdes": date(2025, 1, 1),
            "fechas": date(2025, 1, 31),
            "tipcie": "P",
            "numaju": "",
            "codclas": "",
        }
    )
    client = _app(store, FakeJournalRepo(), FakeAuditRepo())

    response = client.post(
        "/api/erp/receipts",
        json={**_BODY, "fecha": "2025-01-15"},
        headers={
            **_headers("gerente", "ger5", ("erp-cash",)),
            "Idempotency-Key": _IDEM,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "period_locked"
    assert store.detapago == []


def test_production_app_mounts_the_cash_router():
    from motoshop_api.main import app as production_app

    paths = {getattr(route, "path", "") for route in production_app.routes}
    assert "/api/erp/receipts" in paths
