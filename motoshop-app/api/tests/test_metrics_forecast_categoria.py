"""Pruebas del endpoint /metrics/forecast-categoria con FakeMetricsRepo."""
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


def test_forecast_categoria_requires_auth(client: TestClient) -> None:
    resp = client.get("/metrics/forecast-categoria")
    assert resp.status_code == 401


class TestForecastCategoria:
    def test_happy_path_returns_items(self, client, admin_token) -> None:
        resp = client.get(
            "/metrics/forecast-categoria",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) > 0

    def test_item_fields(self, client, admin_token) -> None:
        resp = client.get(
            "/metrics/forecast-categoria",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        item = body["items"][0]
        for f in ("cod_grupo", "demanda_real", "demanda_predicha", "desviacion_pct", "metodo"):
            assert f in item, f"Missing: {f}"
        assert isinstance(item["demanda_real"], float)
        assert item["demanda_real"] > 0

    def test_summary_fields(self, client, admin_token) -> None:
        resp = client.get(
            "/metrics/forecast-categoria",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert body["total_categorias"] == len(body["items"])
        assert body["wape_promedio"] >= 0
        assert 0 < body["cobertura_pct"] <= 100

    def test_cache_returns_same_data(self, client, admin_token) -> None:
        resp1 = client.get(
            "/metrics/forecast-categoria",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/metrics/forecast-categoria",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
