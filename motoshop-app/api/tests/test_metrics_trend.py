"""Pruebas del endpoint /metrics/sales-trend con FakeMetricsRepo."""
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


def test_sales_trend_requires_auth(client: TestClient) -> None:
    """Sin token, el endpoint debe devolver 401."""
    resp = client.get("/metrics/sales-trend")
    assert resp.status_code == 401


class TestSalesTrend:
    def test_happy_path_default_periods(self, client, admin_token) -> None:
        """Con token válido y 6 periodos por defecto, devuelve 200 con datos."""
        resp = client.get(
            "/metrics/sales-trend",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["periods"] == 6
        assert "items" in body
        assert len(body["items"]) == 6
        item = body["items"][0]
        for field in ("year", "month", "total_ventas", "num_facturas", "ticket_promedio"):
            assert field in item, f"Missing field: {field}"
        assert isinstance(item["year"], int)
        assert isinstance(item["month"], int)
        assert isinstance(item["num_facturas"], int)
        assert isinstance(item["total_ventas"], float)
        assert item["total_ventas"] > 0

    def test_custom_periods(self, client, admin_token) -> None:
        """Con periods=3 devuelve exactamente 3 items."""
        resp = client.get(
            "/metrics/sales-trend?periods=3",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["periods"] == 3
        assert len(body["items"]) == 3

    def test_periods_1(self, client, admin_token) -> None:
        """periods=1 devuelve 1 item."""
        resp = client.get(
            "/metrics/sales-trend?periods=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["periods"] == 1
        assert len(body["items"]) == 1

    def test_periods_max_24(self, client, admin_token) -> None:
        """periods=24 es el máximo permitido."""
        resp = client.get(
            "/metrics/sales-trend?periods=24",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 24

    def test_invalid_periods_zero(self, client, admin_token) -> None:
        """periods=0 → 422."""
        resp = client.get(
            "/metrics/sales-trend?periods=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_invalid_periods_over_max(self, client, admin_token) -> None:
        """periods=100 → 422."""
        resp = client.get(
            "/metrics/sales-trend?periods=100",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_items_are_chronological(self, client, admin_token) -> None:
        """Los items deben venir ordenados cronológicamente."""
        resp = client.get(
            "/metrics/sales-trend?periods=6",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        items = body["items"]
        for i in range(1, len(items)):
            prev = items[i - 1]
            curr = items[i]
            # Same year: month must increase
            if prev["year"] == curr["year"]:
                assert curr["month"] > prev["month"], f"Months out of order at index {i}"
            else:
                assert curr["year"] > prev["year"], f"Years out of order at index {i}"
