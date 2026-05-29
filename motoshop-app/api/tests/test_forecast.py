"""Pruebas de los endpoints /forecast/* con FakeForecastRepo."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from motoshop_api.main import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def admin_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import _users_cache, User

    _users_cache.clear()
    _users_cache["admin"] = User(
        username="admin",
        hashed_password=hash_password("admin123"),
        email="admin@test.com",
        role="admin",
    )
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


class TestForecastUnauthenticated:
    def test_forecast_requires_auth(self, client: TestClient) -> None:
        """Sin token, /forecast/{sku} debe devolver 401."""
        resp = client.get("/forecast/MOTS1297?horizon=7")
        assert resp.status_code == 401


class TestForecastAuthenticated:
    def test_forecast_known_sku_returns_200(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/forecast/MOTS1297?horizon=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == "MOTS1297"
        assert len(body["forecast"]) > 0
        assert "forecast" in body
        assert "metrics" in body

    def test_forecast_unknown_sku_returns_404(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/forecast/INEXISTENTE?horizon=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_forecast_item_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/forecast/MOTS1297?horizon=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        item = resp.json()["forecast"][0]
        assert "sku" in item
        assert "forecast_date" in item
        assert "horizon" in item
        assert "predicted_qty" in item
        assert "model_version" in item
        assert "confidence_lower" in item
        assert "confidence_upper" in item

    def test_forecast_metrics_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/forecast/MOTS1297?horizon=14",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        metrics = resp.json()["metrics"]
        assert metrics is not None
        assert "model_version" in metrics
        assert "mape" in metrics
        assert "smape" in metrics

    def test_forecast_horizon_respected(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/forecast/MOTS1297?horizon=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["forecast"]
        assert all(item["horizon"] == 7 for item in items)

    def test_forecast_horizon_30(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/forecast/MOTS1297?horizon=30",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    def test_forecast_invalid_horizon(self, client: TestClient, admin_token: str) -> None:
        """Horizontes fuera de rango (7-30) deben dar error de validación."""
        resp = client.get(
            "/forecast/MOTS1297?horizon=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code in (400, 422)

    def test_forecast_cache_returns_same_data(self, client: TestClient, admin_token: str) -> None:
        resp1 = client.get(
            "/forecast/MOTS1297?horizon=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/forecast/MOTS1297?horizon=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
