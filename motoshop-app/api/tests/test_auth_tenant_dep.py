"""Tests para tenant_dep.py — dependencia get_tenant."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.tenants import Tenant, _tenants_cache


def _populate_tenants() -> None:
    """Puebla el cache de tenants con datos de prueba."""
    _tenants_cache.clear()
    _tenants_cache["motoshop"] = Tenant(
        id="motoshop",
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
        enabled_features=["products", "stock", "sales"],
    )
    _tenants_cache["masvital"] = Tenant(
        id="masvital",
        nombre="MasVital",
        r2_object_key="masvital_gold.duckdb",
        local_db_path="/tmp/masvital_gold.duckdb",
        enabled_features=["products", "stock"],
    )


@pytest.fixture(autouse=True)
def _reset_tenant_cache():
    """Limpia el cache de tenants entre tests."""
    _populate_tenants()
    yield
    _tenants_cache.clear()


def _make_app(current_user_override: User) -> FastAPI:
    """Crea una app de prueba con un endpoint que usa get_tenant.
    
    Sobrescribe get_current_user para evitar la autenticación real.
    """
    app = FastAPI()

    app.dependency_overrides[get_current_user] = lambda: current_user_override

    @app.get("/test-tenant")
    async def test_endpoint(tenant: str = Depends(get_tenant)) -> dict:
        return {"tenant": tenant}

    return app


class TestGetTenant:
    """Tests para la dependencia get_tenant."""

    def test_reads_x_tenant_header(self) -> None:
        """Debe leer el tenant del header X-Tenant."""
        user = User(
            username="admin",
            hashed_password="hash",
            email="admin@test.com",
            role="admin",
            tenants_allowed=["masvital"],
        )
        app = _make_app(user)
        client = TestClient(app)
        resp = client.get("/test-tenant", headers={"X-Tenant": "masvital"})
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "masvital"

    def test_defaults_to_motoshop_when_header_absent(self) -> None:
        """Sin header X-Tenant, debe default a 'motoshop'."""
        user = User(
            username="admin",
            hashed_password="hash",
            email="admin@test.com",
            role="admin",
            tenants_allowed=["motoshop"],
        )
        app = _make_app(user)
        client = TestClient(app)
        resp = client.get("/test-tenant")
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "motoshop"

    def test_infers_only_allowed_tenant_when_header_absent(self) -> None:
        """A single-tenant user should not be forced through MotoShop first."""
        user = User(
            username="masvital-only",
            hashed_password="hash",
            email="masvital-only@test.com",
            role="vendedor",
            tenants_allowed=["masvital"],
            allowed_modules=["ventas-summary"],
            source="supabase",
        )
        app = _make_app(user)
        client = TestClient(app)

        resp = client.get("/test-tenant")

        assert resp.status_code == 200
        assert resp.json()["tenant"] == "masvital"

    def test_returns_403_when_user_not_allowed(self) -> None:
        """Debe retornar 403 si el usuario no tiene acceso al tenant."""
        user = User(
            username="vendedor1",
            hashed_password="hash",
            email="vendedor1@test.com",
            role="vendedor",
            tenants_allowed=["motoshop"],
        )
        app = _make_app(user)
        client = TestClient(app)
        resp = client.get("/test-tenant", headers={"X-Tenant": "masvital"})
        assert resp.status_code == 403
        assert "masvital" in resp.json()["detail"]

    def test_returns_404_when_tenant_not_configured(self) -> None:
        """Debe retornar 404 si el tenant no existe en la configuración."""
        user = User(
            username="admin",
            hashed_password="hash",
            email="admin@test.com",
            role="admin",
            tenants_allowed=["unknown"],
        )
        app = _make_app(user)
        client = TestClient(app)
        resp = client.get("/test-tenant", headers={"X-Tenant": "unknown"})
        assert resp.status_code == 404
        assert "unknown" in resp.json()["detail"]

    def test_empty_tenants_allowed_allows_default_tenant(self) -> None:
        """Usuario con tenants_allowed=[] (backward compat) debe acceder al default."""
        user = User(
            username="legacy",
            hashed_password="hash",
            email="legacy@test.com",
            role="vendedor",
            tenants_allowed=[],
        )
        app = _make_app(user)
        client = TestClient(app)
        # Empty list = no restriction (backward compat)
        resp = client.get("/test-tenant")
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "motoshop"
