"""Pruebas del endpoint /api/metrics/vendedores-summary con FakeMetricsRepo."""
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
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_vendedores_requires_auth(client: TestClient) -> None:
    """Sin token, el endpoint debe devolver 401."""
    resp = client.get("/api/metrics/vendedores-summary")
    assert resp.status_code == 401


class TestVendedoresSummary:
    def test_happy_path_returns_items(self, client, admin_token) -> None:
        """Con token válido, devuelve ranking de vendedores."""
        resp = client.get(
            "/api/metrics/vendedores-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) > 0

    def test_items_have_correct_fields(self, client, admin_token) -> None:
        """Cada item tiene los campos requeridos con tipos correctos."""
        resp = client.get(
            "/api/metrics/vendedores-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        item = body["items"][0]
        for field in ("nit_vendedor", "nombre_vendedor", "facturas", "total_ventas", "ticket_promedio"):
            assert field in item, f"Missing field: {field}"
        assert isinstance(item["nit_vendedor"], str)
        assert isinstance(item["nombre_vendedor"], str)
        assert isinstance(item["facturas"], int)
        assert isinstance(item["total_ventas"], float)
        assert isinstance(item["ticket_promedio"], float)

    def test_ranking_ordered_by_ventas(self, client, admin_token) -> None:
        """El ranking debe venir ordenado por total_ventas descendente."""
        resp = client.get(
            "/api/metrics/vendedores-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        items = body["items"]
        for i in range(1, len(items)):
            assert items[i - 1]["total_ventas"] >= items[i]["total_ventas"], \
                f"Vendedor {i} tiene más ventas que el anterior"

    def test_all_values_positive(self, client, admin_token) -> None:
        """Todos los valores deben ser positivos."""
        resp = client.get(
            "/api/metrics/vendedores-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        for item in body["items"]:
            assert item["facturas"] > 0
            assert item["total_ventas"] > 0
            assert item["ticket_promedio"] > 0

    def test_cache_returns_same_data(self, client, admin_token) -> None:
        """Dos llamadas seguidas deben devolver los mismos datos (cache)."""
        resp1 = client.get(
            "/api/metrics/vendedores-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/api/metrics/vendedores-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
