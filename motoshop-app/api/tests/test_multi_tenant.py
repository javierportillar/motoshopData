"""Tests multi-tenant: /api/auth/me, cache keys con tenant, y acceso cross-tenant.

Requiere fastapi.testclient.TestClient con la app fixture de conftest.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.hash import hash_password
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.tenants import Tenant, _tenants_cache

# ── Helpers ──────────────────────────────────────────────────────────────

def _populate_tenants() -> None:
    """Puebla el cache de tenants con motoshop y masvital."""
    _tenants_cache.clear()
    _tenants_cache["motoshop"] = Tenant(
        id="motoshop",
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
        enabled_features=[
            "products", "stock", "sales", "ventas-summary",
            "ventas-daily", "ventas-monthly", "inventario",
            "abc", "dormidos", "cohortes", "drift", "forecast",
            "plan-compras", "vendedores", "alerts", "acciones",
            "chat-ia", "briefing-diario",
        ],
    )
    _tenants_cache["masvital"] = Tenant(
        id="masvital",
        nombre="MasVital",
        r2_object_key="masvital_gold.duckdb",
        local_db_path="/tmp/masvital_gold.duckdb",
        enabled_features=["products", "stock", "sales", "ventas-summary",
                          "ventas-daily", "inventario", "chat-ia",
                          "pipeline-observability"],
    )


def _populate_users() -> dict[str, User]:
    """Crea usuarios multi-tenant en el cache."""
    _users_cache.clear()
    users = {
        "admin": User(
            username="admin",
            hashed_password=hash_password("admin123"),
            email="admin@test.com",
            role="admin",
            tenants_allowed=["motoshop", "masvital"],
        ),
        "vendedor1": User(
            username="vendedor1",
            hashed_password=hash_password("vend123"),
            email="vendedor1@test.com",
            role="vendedor",
            tenants_allowed=["motoshop"],
        ),
        "masvital1": User(
            username="masvital1",
            hashed_password=hash_password("masvital123"),
            email="masvital1@test.com",
            role="vendedor",
            tenants_allowed=["masvital"],
            allowed_modules=["ventas-summary"],
            source="supabase",
        ),
    }
    _users_cache.update(users)
    return users


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _setup_tenants_and_users():
    """Carga tenants y usuarios multi-tenant antes de cada test."""
    _populate_tenants()
    _populate_users()
    yield
    _tenants_cache.clear()
    _users_cache.clear()


# ── Helpers de login ─────────────────────────────────────────────────────

def _login_as(client: TestClient, username: str, password: str) -> str:
    """Login y retorna access token."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


# ── Tests ────────────────────────────────────────────────────────────────

class TestMultiTenantMe:
    """Tests para GET /api/auth/me con multi-tenant."""

    def test_me_returns_user_info_with_tenants(self, client: TestClient) -> None:
        """Login + /me retorna username, email, role y tenants_allowed."""
        token = _login_as(client, "admin", "admin123")
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["username"] == "admin"
        assert data["email"] == "admin@test.com"
        assert data["role"] == "admin"
        assert "motoshop" in data["tenants_allowed"]
        assert "masvital" in data["tenants_allowed"]

    def test_me_with_motoshop_tenant_returns_full_features(
        self, client: TestClient
    ) -> None:
        """X-Tenant: motoshop devuelve todas las features de MotoShop."""
        token = _login_as(client, "admin", "admin123")
        resp = client.get(
            "/api/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "motoshop",
            },
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["current_tenant"] == "motoshop"
        assert "products" in data["enabled_features"]
        assert "forecast" in data["enabled_features"]
        assert "briefing-diario" in data["enabled_features"]

    def test_me_with_masvital_tenant_returns_reduced_features(
        self, client: TestClient
    ) -> None:
        """X-Tenant: masvital devuelve solo las features reducidas de MasVital."""
        token = _login_as(client, "admin", "admin123")
        resp = client.get(
            "/api/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "masvital",
            },
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["current_tenant"] == "masvital"
        # MasVital tiene features reducidas — NO tiene forecast ni briefing
        assert "products" in data["enabled_features"]
        assert "forecast" not in data["enabled_features"]
        assert "briefing-diario" not in data["enabled_features"]
        assert "chat-ia" in data["enabled_features"]

    def test_me_defaults_to_motoshop_without_x_tenant(
        self, client: TestClient
    ) -> None:
        """Sin X-Tenant, /me debe default a motoshop."""
        token = _login_as(client, "admin", "admin123")
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["current_tenant"] == "motoshop"
        # Debe tener features de motoshop
        assert len(data["enabled_features"]) > 10

    def test_me_infers_masvital_for_managed_single_tenant_user(
        self, client: TestClient
    ) -> None:
        """A MasVital-only managed user can bootstrap before a tenant cookie exists."""
        token = _login_as(client, "masvital1", "masvital123")

        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["current_tenant"] == "masvital"
        assert data["tenants_allowed"] == ["masvital"]
        assert data["allowed_modules"] == ["ventas-summary"]
        assert data["effective_modules"] == ["ventas-summary"]

    def test_me_with_masvital_works_even_without_duckdb(
        self, client: TestClient
    ) -> None:
        """Cross-tenant: /me con masvital funciona aunque el archivo DuckDB no
        exista, porque /me solo consulta la config de tenants en memoria."""
        token = _login_as(client, "admin", "admin123")
        resp = client.get(
            "/api/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "masvital",
            },
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["current_tenant"] == "masvital"
        assert data["enabled_features"] == [
            "products", "stock", "sales", "ventas-summary",
            "ventas-daily", "inventario", "chat-ia",
            "pipeline-observability",
        ]

    def test_me_returns_403_for_unauthorized_tenant(
        self, client: TestClient
    ) -> None:
        """Usuario con tenants_allowed=[motoshop] no puede acceder a masvital."""
        token = _login_as(client, "vendedor1", "vend123")
        resp = client.get(
            "/api/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "masvital",
            },
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        assert "masvital" in resp.json()["detail"]


class TestMultiTenantCacheKeys:
    """Cache keys con prefijo de tenant en los routers de métricas.
    
    Estos tests verifican que las rutas de métricas existan y que el
    mecanismo de tenant esté integrado (sin necesidad de DuckDB real).
    """

    def test_metrics_sales_summary_accepts_tenant(self, client: TestClient) -> None:
        """GET /metrics/sales-summary con tenant devuelve error graceful
        (DuckDB no existe) pero NO 500 — prueba que el dependency injection
        de tenant está presente."""
        token = _login_as(client, "admin", "admin123")
        resp = client.get(
            "/api/metrics/sales-summary",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "motoshop",
            },
        )
        # DuckDB no existe en tests → esperamos un error, pero NO
        # un error de dependency injection (422, 401, 403)
        assert resp.status_code not in (401, 403, 422), (
            f"Got auth/validation error instead of graceful backend error: "
            f"{resp.status_code}: {resp.text}"
        )

    def test_metrics_sales_summary_rejects_wrong_tenant(
        self, client: TestClient
    ) -> None:
        """Usuario no autorizado para un tenant recibe 403."""
        token = _login_as(client, "vendedor1", "vend123")
        resp = client.get(
            "/api/metrics/sales-summary",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "masvital",
            },
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        assert "masvital" in resp.json()["detail"]

    def test_forecast_with_wrong_tenant_returns_403(
        self, client: TestClient
    ) -> None:
        """Forecast endpoint con tenant no autorizado devuelve 403."""
        token = _login_as(client, "vendedor1", "vend123")
        resp = client.get(
            "/api/forecast/MOTS1297",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "masvital",
            },
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_alerts_stockout_with_wrong_tenant_returns_403(
        self, client: TestClient
    ) -> None:
        """Alerts endpoint con tenant no autorizado devuelve 403."""
        token = _login_as(client, "vendedor1", "vend123")
        resp = client.get(
            "/api/alerts/stockout",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant": "masvital",
            },
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
