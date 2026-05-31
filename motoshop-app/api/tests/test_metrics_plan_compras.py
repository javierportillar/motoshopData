"""Pruebas del endpoint /api/metrics/plan-compras con FakeMetricsRepo."""
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


def test_plan_compras_requires_auth(client: TestClient) -> None:
    """Sin token, el endpoint debe devolver 401."""
    resp = client.get("/api/metrics/plan-compras")
    assert resp.status_code == 401


class TestPlanCompras:
    def test_happy_path_returns_items(self, client, admin_token) -> None:
        """Con token válido, devuelve plan de compras."""
        resp = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) > 0

    def test_item_fields_match_frontend_contract(self, client, admin_token) -> None:
        """Cada item tiene los campos que espera Dev T2 en plan-compras/page.tsx."""
        resp = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        item = body["items"][0]
        for field in ("sku", "nombre", "stock_actual", "demanda_7d", "cantidad_a_comprar", "abc", "urgencia", "dormido", "supplier"):
            assert field in item, f"Missing field: {field}"
        assert isinstance(item["sku"], str)
        assert isinstance(item["stock_actual"], float)
        assert item["abc"] in ("A", "B", "C")
        assert isinstance(item["dormido"], bool)

    def test_summary_fields(self, client, admin_token) -> None:
        """Los campos de resumen son coherentes."""
        resp = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert body["total_skus"] == len(body["items"])
        assert body["total_unidades"] >= 0
        assert body["total_valor_estimado"] >= 0
        assert body["skus_urgentes"] >= 0
        assert body["skus_dormidos"] >= 0
        assert body["skus_urgentes"] + body["skus_dormidos"] <= body["total_skus"] + body["skus_urgentes"]

    def test_cantidad_comprar_correcta(self, client, admin_token) -> None:
        """cantidad_a_comprar = max(0, demanda_7d - stock_actual)."""
        resp = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        for item in body["items"]:
            esperado = max(0, item["demanda_7d"] - item["stock_actual"])
            # Fake data is hand-crafted, but the formula should hold
            assert abs(item["cantidad_a_comprar"] - esperado) < 0.01, \
                f"{item['sku']}: cantidad={item['cantidad_a_comprar']}, esperado={esperado}"

    def test_items_ordered_by_priority(self, client, admin_token) -> None:
        """Primero SKUs con más cantidad_a_comprar, urgente primero."""
        resp = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        items = body["items"]
        for i in range(1, len(items)):
            prev, curr = items[i - 1], items[i]
            assert prev["cantidad_a_comprar"] >= curr["cantidad_a_comprar"], \
                f"Order violation at {i}: {prev['sku']} < {curr['sku']}"

    def test_cache_returns_same_data(self, client, admin_token) -> None:
        """Dos llamadas seguidas deben devolver los mismos datos (cache)."""
        resp1 = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/api/metrics/plan-compras",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
