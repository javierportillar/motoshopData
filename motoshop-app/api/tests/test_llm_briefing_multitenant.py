"""Multi-tenant contract for the scheduled Telegram briefing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import duckdb
import pytest
import yaml
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user, require_refresh_token_or_admin
from motoshop_api.auth.tenant_dep import get_tenant_for_admin_or_machine
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.llm import router as llm_router
from motoshop_api.llm.briefing import BriefingGenerator
from motoshop_api.main import app
from motoshop_api.metrics import repo_duckdb
from motoshop_api.tenants import Tenant, TenantBriefing, _tenants_cache


def _tenant(tenant_id: str, name: str) -> Tenant:
    return Tenant(
        id=tenant_id,
        nombre=name,
        r2_object_key=f"{tenant_id}_gold.duckdb",
        local_db_path=f"/tmp/{tenant_id}_gold.duckdb",
        briefing=TenantBriefing(activo=True),
    )


def _result(text: str) -> dict[str, object]:
    return {
        "briefing_text": text, "tokens_used": 10, "tokens_input": 8,
        "tokens_output": 2, "model": "test-model", "cost_usd": 0.0,
    }


def _create_briefing_db(path: Path, sales: float) -> None:
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE gold_mart_ventas_diarias_sku (
            business_date DATE, valor_total DOUBLE, num_facturas INTEGER,
            cod_producto VARCHAR, nom_producto VARCHAR
        );
        CREATE TABLE gold_alertas_quiebre (
            sku VARCHAR, nom_producto VARCHAR, stock_actual DOUBLE,
            demanda_predicha DOUBLE, dias_hasta_quiebre INTEGER, urgencia VARCHAR
        );
        CREATE TABLE gold_mart_productos_dormidos (
            cod_producto VARCHAR, nom_producto VARCHAR, dias_sin_venta INTEGER
        );
        CREATE TABLE silver_fact_ventas (
            business_date DATE, nit_vendedor VARCHAR,
            nombre_vendedor VARCHAR, total_factura DOUBLE
        );
    """)
    con.execute(
        "INSERT INTO gold_mart_ventas_diarias_sku VALUES "
        "('2026-07-20', ?, 1, 'SKU-1', 'Producto')",
        [sales],
    )
    con.close()


@pytest.fixture()
def briefing_client() -> TestClient:
    storage = llm_router.limiter._storage
    storage.storage.clear()
    _tenants_cache.clear()
    _tenants_cache.update({
        "motoshop": _tenant("motoshop", "MotoShop"),
        "masvital": _tenant("masvital", "MasVital"),
    })
    admin = User(
        username="admin", hashed_password="hash", email="admin@test.com", role="admin",
        tenants_allowed=["motoshop", "masvital"], allowed_modules=[], source="supabase",
    )
    def resolve_test_tenant(request: Request) -> str:
        return request.headers.get("X-Tenant", "motoshop")

    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[require_refresh_token_or_admin] = lambda: True
    app.dependency_overrides[get_tenant_for_admin_or_machine] = resolve_test_tenant
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_refresh_token_or_admin, None)
        app.dependency_overrides.pop(get_tenant_for_admin_or_machine, None)
        _tenants_cache.clear()
        storage.storage.clear()


@pytest.fixture()
def machine_briefing_client() -> TestClient:
    storage = llm_router.limiter._storage
    storage.storage.clear()
    _tenants_cache.clear()
    _tenants_cache.update({
        "motoshop": _tenant("motoshop", "MotoShop"),
        "masvital": _tenant("masvital", "MasVital"),
    })
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        _tenants_cache.clear()
        storage.storage.clear()

def test_briefing_uses_isolated_db_and_explicit_destination_per_tenant(
    briefing_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = {tenant: tmp_path / f"{tenant}.duckdb" for tenant in ("motoshop", "masvital")}
    _create_briefing_db(paths["motoshop"], 101.0)
    _create_briefing_db(paths["masvital"], 202.0)
    legacy_path = tmp_path / "legacy-motoshop.duckdb"
    _create_briefing_db(legacy_path, 999.0)
    monkeypatch.setattr(settings, "duckdb_path", str(legacy_path))
    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda tenant: paths[tenant])
    monkeypatch.setattr(
        BriefingGenerator,
        "generate",
        lambda _self, context: _result(f"{context['empresa']}:{context['ventas_ayer']}"),
    )
    payloads: list[dict[str, object]] = []

    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"ok": True, "result": {"message_id": len(payloads)}}

    monkeypatch.setattr(llm_router, "TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_MOTOSHOP", "chat-motoshop")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_MASVITAL", "chat-masvital")
    monkeypatch.setattr(
        llm_router.httpx, "post",
        lambda _url, **kwargs: payloads.append(kwargs["json"]) or Response(),
    )

    responses = [
        briefing_client.post("/api/llm/briefing/send", headers={"X-Tenant": tenant})
        for tenant in ("motoshop", "masvital")
    ]

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["briefing_text"] for response in responses] == [
        "[MotoShop]\nMotoShop:101.0", "[MasVital]\nMasVital:202.0",
    ]
    assert [payload["chat_id"] for payload in payloads] == ["chat-motoshop", "chat-masvital"]


def test_missing_tenant_destination_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_router, "TELEGRAM_TOKEN", "test-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID_MASVITAL", raising=False)
    monkeypatch.setenv("TELEGRAM_GERENTE_CHAT_ID", "legacy-motoshop-chat")
    with pytest.raises(HTTPException) as exc_info:
        llm_router._send_telegram("MasVital data", "masvital")
    assert exc_info.value.status_code == 503
    assert "masvital" in exc_info.value.detail


@pytest.mark.parametrize("tenant", ["motoshop", "masvital"])
@pytest.mark.parametrize("endpoint", ["generate", "send"])
def test_briefing_bootstraps_missing_tenant_snapshot_before_opening(
    briefing_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tenant: str,
    endpoint: str,
) -> None:
    paths = {
        tenant_id: tmp_path / f"{tenant_id}_gold.duckdb" for tenant_id in ("motoshop", "masvital")
    }
    bootstrap_calls: list[tuple[Path, str]] = []

    def bootstrap(path: Path, tenant_id: str) -> None:
        assert path == paths[tenant_id]
        assert not path.exists()
        bootstrap_calls.append((path, tenant_id))
        _create_briefing_db(path, 101.0 if tenant_id == "motoshop" else 202.0)

    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda tenant_id: paths[tenant_id])
    monkeypatch.setattr(repo_duckdb, "_bootstrap_duckdb_from_r2", bootstrap)
    monkeypatch.setattr(
        BriefingGenerator,
        "generate",
        lambda _self, context: _result(f"{context['empresa']}:{context['ventas_ayer']}"),
    )
    monkeypatch.setattr(llm_router, "_send_telegram", lambda _text, _tenant: 1)

    response = briefing_client.post(f"/api/llm/briefing/{endpoint}", headers={"X-Tenant": tenant})

    assert response.status_code == 200
    assert bootstrap_calls == [(paths[tenant], tenant)]
    assert paths[tenant].exists()


@pytest.mark.parametrize("tenant", ["motoshop", "masvital"])
@pytest.mark.parametrize("endpoint", ["generate", "send"])
def test_briefing_returns_controlled_503_when_tenant_snapshot_stays_unavailable(
    briefing_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tenant: str,
    endpoint: str,
) -> None:
    paths = {
        tenant_id: tmp_path / f"{tenant_id}_gold.duckdb" for tenant_id in ("motoshop", "masvital")
    }
    bootstrap_calls: list[tuple[Path, str]] = []

    monkeypatch.setattr(repo_duckdb, "_make_db_path", lambda tenant_id: paths[tenant_id])
    monkeypatch.setattr(
        repo_duckdb,
        "_bootstrap_duckdb_from_r2",
        lambda path, tenant_id: bootstrap_calls.append((path, tenant_id)),
    )
    monkeypatch.setattr(llm_router, "_send_telegram", lambda _text, _tenant: 1)

    response = briefing_client.post(f"/api/llm/briefing/{endpoint}", headers={"X-Tenant": tenant})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {
        "detail": "El servidor está terminando de cargar los datos. Reintentá en unos segundos.",
        "status": "loading",
        "retry_after_seconds": 5,
    }
    assert bootstrap_calls == [(paths[tenant], tenant)]
    assert not paths[tenant].exists()


def test_briefing_send_accepts_machine_refresh_token(
    machine_briefing_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REFRESH_TOKEN", "machine-token")
    monkeypatch.setattr(llm_router, "_generate_briefing", lambda tenant: _result(tenant))
    monkeypatch.setattr(llm_router, "_send_telegram", lambda _text, _tenant: 1)

    response = machine_briefing_client.post(
        "/api/llm/briefing/send",
        headers={"Authorization": "Bearer machine-token", "X-Tenant": "motoshop"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"


def test_briefing_send_rejects_wrong_machine_token(
    machine_briefing_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REFRESH_TOKEN", "machine-token")
    monkeypatch.setattr(llm_router, "_generate_briefing", lambda tenant: _result(tenant))

    response = machine_briefing_client.post(
        "/api/llm/briefing/send",
        headers={"Authorization": "Bearer wrong-token", "X-Tenant": "motoshop"},
    )

    assert response.status_code == 401


def test_tenant_failure_does_not_duplicate_another_send(
    briefing_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []

    def generate(tenant: str) -> dict[str, object]:
        if tenant == "masvital":
            raise HTTPException(status_code=404, detail="Sin datos para MasVital")
        return _result(tenant)

    monkeypatch.setattr(llm_router, "_generate_briefing", generate)
    monkeypatch.setattr(
        llm_router, "_send_telegram", lambda _text, tenant: sent.append(tenant) or 1,
    )
    ok = briefing_client.post("/api/llm/briefing/send", headers={"X-Tenant": "motoshop"})
    failed = briefing_client.post("/api/llm/briefing/send", headers={"X-Tenant": "masvital"})
    assert (ok.status_code, failed.status_code) == (200, 404)
    assert sent == ["motoshop"]


def test_workflow_reports_non_json_503_without_leaking_body_or_token(tmp_path: Path) -> None:
    workflow_path = Path(__file__).parents[3] / ".github/workflows/briefing-daily.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    script = workflow["jobs"]["send-briefing"]["steps"][0]["run"]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("""#!/usr/bin/env bash
out=''; url=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == */api/llm/briefing/send ]]; then
  printf '<html>temporarily unavailable</html>' > "$out"; printf '503'
else
  printf 'unexpected url' > "$out"; printf '404'
fi
""")
    fake_curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BRIEFING_REFRESH_TOKEN": "fake-machine-token",
        "TENANT": "masvital",
    }

    result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "tenant=masvital http=503 category=non_json_response" in output
    assert "temporarily unavailable" not in output
    assert "fake-machine-token" not in output


def test_workflow_fails_closed_when_machine_token_secret_missing(tmp_path: Path) -> None:
    workflow_path = Path(__file__).parents[3] / ".github/workflows/briefing-daily.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    script = workflow["jobs"]["send-briefing"]["steps"][0]["run"]
    env = {**os.environ, "TENANT": "motoshop"}
    env.pop("BRIEFING_REFRESH_TOKEN", None)

    result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "tenant=motoshop http=000 category=missing_machine_token" in output
