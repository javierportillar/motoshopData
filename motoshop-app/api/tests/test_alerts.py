"""Pruebas de los endpoints /alerts/* con FakeAlertsRepo."""
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


class TestAlertsUnauthenticated:
    def test_alerts_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/alerts/stockout")
        assert resp.status_code == 401


class TestAlertsAuthenticated:
    def test_alerts_returns_list(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/alerts/stockout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "alerts" in body
        assert "total" in body
        assert "timestamp" in body
        assert len(body["alerts"]) > 0

    def test_alert_item_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/alerts/stockout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        item = resp.json()["alerts"][0]
        assert "sku" in item
        assert "nom_producto" in item
        assert "stock_actual" in item
        assert "demanda_predicha" in item
        assert "dias_hasta_quiebre" in item
        assert "urgencia" in item
        assert item["urgencia"] in ("alta", "media", "baja")

    def test_alerts_ordered_by_urgency(self, client: TestClient, admin_token: str) -> None:
        """Las alertas deben venir ordenadas: alta → media → baja."""
        resp = client.get(
            "/alerts/stockout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        items = resp.json()["alerts"]
        order = {"alta": 1, "media": 2, "baja": 3}
        urgencias = [order[a["urgencia"]] for a in items]
        assert urgencias == sorted(urgencias), "Alertas no ordenadas por urgencia"

    def test_alerts_filter_high(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/alerts/stockout?urgency=alta",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        for a in resp.json()["alerts"]:
            assert a["urgencia"] == "alta"

    def test_alerts_filter_low(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/alerts/stockout?urgency=baja",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        for a in resp.json()["alerts"]:
            assert a["urgencia"] == "baja"

    def test_alerts_invalid_urgency_returns_400(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/alerts/stockout?urgency=supercritica",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_alerts_cache_returns_same_data(self, client: TestClient, admin_token: str) -> None:
        resp1 = client.get(
            "/alerts/stockout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/alerts/stockout",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
