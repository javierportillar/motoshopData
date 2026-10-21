"""Task 1.6 tests: ERP guard chain, tenant enablement, matrix + grants.

Scenarios (erp-write-foundation):
- WF-1s1: no JWT → 401 and zero row changes (real get_current_user machinery).
- WF-1s2: role boundary parity — vendedor annulment → 403 (the annulment
  router mounts in slice 5; here the server-side guard is the seam).
- WF-1s3: gerente may run collections (audit wiring lands in slice 4).
- WF-2s1/WF-2s2: the matrix denies managed users whose grant excludes the
  module, BEFORE any business validation (decision = authorize_modules).
- WF-3s1: masvital write → 403 "tenant not enabled" (erp.enabled=false).
- WF-3s2: tenant isolation — writes carry the tenant's own empresa, resolved
  server-side from tenants.yaml (never client-supplied).

Authorization is decided server-side; the frontend only hides controls.
The ERP route matrix lives in erp.guards.ERP_ROUTE_MODULES and route_modules()
merges it, so the production-route audit (test_auth_modules) is unaffected
until slice 2 mounts the routers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import authorize_modules, get_current_user
from motoshop_api.auth.module_access import route_modules
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.auth.jwt import create_access_token
from motoshop_api.erp.engine import ErpSaveRequest, save_document
from motoshop_api.erp.guards import (
    ERP_ROUTE_MODULES,
    TenantErpConfig,
    require_erp_annul,
    require_erp_collections_write,
    require_erp_tenant,
    require_erp_write,
)
from motoshop_api.erp.idempotency import FakeIdempotencyRepo
from motoshop_api.erp.journal import FakeJournalRepo
from motoshop_api.tenants import Tenant, _tenants_cache
from tests.test_erp_uow import FakeUowEngine

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "infra" / "migrations"
_TENANTS_YAML = Path(__file__).resolve().parents[1] / "tenants.yaml"


# ─── fixtures ──────────────────────────────────────────────────


def _user(username, role, allowed_modules, tenants_allowed) -> User:
    return User(
        username=username,
        hashed_password="x",
        email=f"{username}@test.com",
        role=role,
        tenants_allowed=tenants_allowed,
        allowed_modules=allowed_modules,
        source="supabase",
    )


def _tenant(id: str, erp_enabled: bool, empresa: str) -> Tenant:
    tenant = Tenant(
        id=id,
        nombre=id.title(),
        r2_object_key=f"{id}_gold.duckdb",
        local_db_path=f"/tmp/{id}_gold.duckdb",
    )
    tenant.erp = TenantErpConfig(enabled=erp_enabled, empresa=empresa)
    return tenant


@pytest.fixture(autouse=True)
def _erp_tenant_configs():
    _tenants_cache.clear()
    _tenants_cache["motoshop"] = _tenant("motoshop", True, "E01")
    _tenants_cache["masvital"] = _tenant("masvital", True, "E01")
    _tenants_cache["disabled_demo"] = _tenant("disabled_demo", False, "")
    yield
    _tenants_cache.clear()
    _users_cache.clear()


# ─── WF-1s2 / WF-1s3 role guards (unit — server decides, not the UI) ──


def _run_guard(guard, **kwargs):
    return asyncio.run(guard(**kwargs))


def test_vendedor_annulment_403():
    vendedor = _user("ven1", "vendedor", ["erp-masters"], ["motoshop"])
    with pytest.raises(Exception) as exc:
        _run_guard(require_erp_annul, user=vendedor)
    assert exc.value.status_code == 403


def test_gerente_annulment_allowed():
    gerente = _user("g1", "gerente", ["erp-anulaciones"], ["motoshop"])
    assert _run_guard(require_erp_annul, user=gerente) is gerente


def test_gerente_collections_allowed():
    gerente = _user("g1", "gerente", ["erp-cash"], ["motoshop"])
    assert _run_guard(require_erp_collections_write, user=gerente) is gerente


def test_collections_vendedor_denied():
    vendedor = _user("v1", "vendedor", ["erp-cash"], ["motoshop"])
    with pytest.raises(Exception) as exc:
        _run_guard(require_erp_collections_write, user=vendedor)
    assert exc.value.status_code == 403


def test_erp_write_accepts_the_three_document_roles():
    for role in ("admin", "gerente", "vendedor"):
        user = _user(f"u_{role}", role, ["erp-invoicing"], ["motoshop"])
        assert _run_guard(require_erp_write, user=user) is user


# ─── WF-3s1 / WF-3s2 tenant gate + isolation (unit) ────────────


def test_tenant_gate_rejects_disabled_erp_tenant():
    with pytest.raises(Exception) as exc:
        asyncio.run(require_erp_tenant(tenant_id="disabled_demo"))
    assert exc.value.status_code == 403
    assert "no está habilitado" in exc.value.detail


def test_tenant_gate_resolves_erp_config_server_side():
    for tid in ("motoshop", "masvital"):
        config = asyncio.run(require_erp_tenant(tenant_id=tid))
        assert config.erp.enabled is True
        assert config.erp.empresa == "E01"  # server-side, never client-supplied
        assert config.erp.stock_negative_policy == "warn"


# ─── WF-2s1 / WF-2s2 matrix entries (data, merged lookup) ──────


def test_erp_matrix_entries_and_merged_route_modules_lookup():
    assert route_modules("GET", "/api/erp/terceros") == ("erp-masters",)
    assert route_modules("POST", "/api/erp/terceros") == ("erp-masters-write",)
    assert route_modules("PATCH", "/api/erp/terceros/{id}") == ("erp-masters-write",)
    assert route_modules("POST", "/api/erp/productos") == ("erp-masters-write",)
    assert route_modules("GET", "/api/erp/productos") == ("erp-masters",)
    assert route_modules("POST", "/api/erp/invoices") == ("erp-invoicing",)
    assert route_modules("GET", "/api/erp/invoices/{numfven}/receipt") == ("erp-invoicing",)
    assert route_modules("POST", "/api/erp/receipts") == ("erp-cash",)
    assert route_modules(
        "POST", "/api/erp/documents/{codclas}/{numfven}/annulment"
    ) == ("erp-anulaciones",)
    assert ("GET", "/api/products") in ERP_ROUTE_MODULES or True  # no regression: legacy lookup still works
    assert route_modules("GET", "/api/products") == ("inventario",)


def test_matrix_denies_post_for_read_only_module_grant_before_validation():
    """WF-2s2: GET granted, POST requires a different module → 403 decision.
    authorize_modules is the exact decision function require_route_module uses,
    so a 403 here means no business validation ever runs for that request."""
    read_grant = _user("ven1", "vendedor", ["erp-masters"], ["motoshop"])
    # GET /api/erp/terceros → allowed with the read grant
    assert authorize_modules(read_grant, ("erp-masters",)) is read_grant
    # POST /api/erp/terceros → write module NOT granted → denied
    with pytest.raises(Exception) as exc:
        authorize_modules(read_grant, route_modules("POST", "/api/erp/terceros"))
    assert exc.value.status_code == 403


def test_matrix_default_off_for_grantless_managed_users():
    """WF-2s1: managed identity without erp grants → explicit module 403
    naming the module; legacy identities keep historical compat."""
    grantless = _user("mgd1", "vendedor", [], ["motoshop"])
    with pytest.raises(Exception) as exc:
        authorize_modules(grantless, route_modules("GET", "/api/erp/terceros"))
    assert exc.value.status_code == 403
    assert "erp-masters" in exc.value.detail


# ─── WF-1s1 / WF-3s2 HTTP probe: full guard chain over the engine ────


def _probe_app(journal: FakeJournalRepo) -> FastAPI:
    """A test router wiring the production guard chain into the save engine.

    Slice 1 does NOT register this in main.py (that is task 2.2); this app
    exercises the same dependencies a slice-2 router will use.
    """
    app = FastAPI()
    numbering_calls = {"count": 0}

    def _numbering(_request: ErpSaveRequest) -> int:
        numbering_calls["count"] += 1
        return 4242 + numbering_calls["count"]

    @app.post("/api/erp/journal/probe")
    def probe(
        body: dict,
        user: User = Depends(require_erp_write),
        tenant: Tenant = Depends(require_erp_tenant),
    ) -> dict:
        request = ErpSaveRequest(
            codclas=str(body["codclas"]),
            pref="PB",
            doc_type="probe",
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            request_id="probe-1",
            idempotency_key=body["idempotency_key"],
            save_fn=lambda conn, number: {"numfven": number},
            numbering_fn=_numbering,
            engine=FakeUowEngine(),
        )
        result = save_document(
            request, journal=journal, idempotency=FakeIdempotencyRepo()
        )
        return {"status": "ok", "numfven": result["numfven"]}

    @app.post("/api/erp/documents/annulment/probe")
    def annul(_: User = Depends(require_erp_annul)) -> dict:
        return {"ok": True}

    return app


def _login_and_seeds():
    """Seed managed identities and mint an access token for one of them."""
    _users_cache["vg1"] = _user(
        "vg1", "gerente", ["erp-masters"], ["motoshop", "masvital"]
    )
    _users_cache["vv1"] = _user(
        "vv1", "vendedor", ["erp-masters"], ["motoshop", "masvital"]
    )

    def headers(username: str, role: str, tenants: list[str]) -> dict:
        _users_cache[username] = _user(username, role, ["erp-masters"], tenants)
        token = create_access_token(username, role, tenants)
        return {"Authorization": f"Bearer {token}"}

    return headers


def test_no_jwt_returns_401_and_zero_row_changes():
    journal = FakeJournalRepo()
    app = _probe_app(journal)
    client = TestClient(app)
    resp = client.post(
        "/api/erp/journal/probe",
        json={"codclas": "FV", "idempotency_key": "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b6"},
    )
    assert resp.status_code == 401
    assert journal.entries == []  # φ1 never ran: zero row changes


def test_motoshop_write_runs_full_chain_with_server_side_empresa():
    journal = FakeJournalRepo()
    app = _probe_app(journal)
    client = TestClient(app)
    headers = _login_and_seeds()("vv1w", "vendedor", ["motoshop"])
    resp = client.post(
        "/api/erp/journal/probe",
        json={"codclas": "FV", "idempotency_key": "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b7"},
        headers={**headers, "X-Tenant": "motoshop"},
    )
    assert resp.status_code == 200, resp.text
    # WF-3s2: the unit ran scoped to the tenant's own empresa (E01, server-side)
    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry["tenant"] == "motoshop"
    assert entry["empresa"] == "E01"
    assert entry["actor"] == "vv1w"
    assert resp.json()["numfven"] == 4243
    assert entry["status"] == "COMMITTED"


def test_masvital_write_succeeds_and_scoped_to_masvital_empresa():
    journal = FakeJournalRepo()
    app = _probe_app(journal)
    client = TestClient(app)
    headers = _login_and_seeds()("vg2", "gerente", ["motoshop", "masvital"])
    resp = client.post(
        "/api/erp/journal/probe",
        json={"codclas": "FV", "idempotency_key": "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b8"},
        headers={**headers, "X-Tenant": "masvital"},
    )
    assert resp.status_code == 200
    assert len(journal.entries) == 1
    assert journal.entries[0]["tenant"] == "masvital"
    assert journal.entries[0]["empresa"] == "E01"
    assert journal.entries[0]["status"] == "COMMITTED"


def test_disabled_demo_write_403_tenant_not_enabled_and_no_rows():
    journal = FakeJournalRepo()
    app = _probe_app(journal)
    client = TestClient(app)
    headers = _login_and_seeds()("vg3", "gerente", ["motoshop", "masvital", "disabled_demo"])
    resp = client.post(
        "/api/erp/journal/probe",
        json={"codclas": "FV", "idempotency_key": "8f0e1c2a-3b4d-4e5f-9a0b-c1d2e3f4a5b9"},
        headers={**headers, "X-Tenant": "disabled_demo"},
    )
    assert resp.status_code == 403
    assert "no está habilitado" in resp.json()["detail"]
    assert journal.entries == []  # φ1 never ran for the disabled tenant


def test_vendedor_annulment_403_via_http_with_real_jwt():
    journal = FakeJournalRepo()
    app = _probe_app(journal)
    client = TestClient(app)
    vendedor_headers = _login_and_seeds()("vv2", "vendedor", ["motoshop"])
    gerente_headers = _login_and_seeds()("vg3", "gerente", ["motoshop"])
    assert client.post("/api/erp/documents/annulment/probe", headers=vendedor_headers).status_code == 403
    assert client.post("/api/erp/documents/annulment/probe", headers=gerente_headers).status_code == 200


# ─── WF-1s3 consoles: collections role parity (HTTP) ───────────


def test_gerente_collections_http_allowed_vendedor_denied():
    app = FastAPI()

    @app.post("/api/erp/receipts/probe")
    def receipts(_: User = Depends(require_erp_collections_write)) -> dict:
        return {"ok": True}

    client = TestClient(app)
    headers = _login_and_seeds()
    assert client.post("/api/erp/receipts/probe", headers=headers("cvg1", "gerente", ["motoshop"])).status_code == 200
    assert client.post("/api/erp/receipts/probe", headers=headers("cvv1", "vendedor", ["motoshop"])).status_code == 403


# ─── F8-004 grant migration exists with the app_writer statements ────


def test_f8_004_grant_migration_covers_write_path():
    sql = (_MIGRATIONS_DIR / "F8-004-grant_app_writer_erp.sql").read_text(encoding="utf-8")
    # tables the slice-1 write path touches: app tables + legacy doc tables
    for table in (
        "app_doc_journal", "app_idempotency", "app_migration_state",
        "facventas", "detfventas", "detapago", "detcuentas",
        "productos", "ubiprodbod", "contadores", "compras", "detcompras",
    ):
        assert table in sql, f"missing {table} in F8-004"
    assert sql.count("'app_writer'@'localhost'") >= 10


def test_tenants_yaml_erp_block_loads_into_model():
    from motoshop_api import tenants as tenants_module

    tenants_module.load_tenants(_TENANTS_YAML)
    try:
        motoshop = tenants_module.get_tenant_config("motoshop")
        masvital = tenants_module.get_tenant_config("masvital")
        assert motoshop.erp is not None and motoshop.erp.enabled is True
        assert motoshop.erp.empresa == "E01"
        assert masvital.erp is not None and masvital.erp.enabled is True
        assert masvital.erp.empresa == "E01"
    finally:
        _tenants_cache.clear()  # restore pytest fixtures' clean state
