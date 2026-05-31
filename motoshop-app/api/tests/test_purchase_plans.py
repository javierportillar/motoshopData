"""Pruebas CRUD /purchase-plans con FakePurchasePlansRepo."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from motoshop_api.main import app
from motoshop_api.purchase_plans.repo import FakePurchasePlansRepo, get_purchase_plans_repo


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def admin_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import _users_cache, User
    _users_cache.clear()
    _users_cache["admin"] = User(username="admin", hashed_password=hash_password("admin123"), email="admin@test.com", role="admin")
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(autouse=True)
def reset_repo():
    """Reset Fake repo entre tests."""
    from motoshop_api.purchase_plans.repo import _fake_repo
    _fake_repo = FakePurchasePlansRepo()
    import motoshop_api.purchase_plans.repo as mod
    mod._fake_repo = _fake_repo
    yield
    mod._fake_repo = None


def test_requires_auth(client):
    assert client.get("/purchase-plans").status_code == 401
    assert client.post("/purchase-plans", json={"plan_name": "test", "items": [], "total_skus": 0, "total_value": 0}).status_code == 401


class TestPurchasePlansCRUD:
    def test_create_and_get(self, client, admin_token):
        resp = client.post(
            "/purchase-plans",
            json={"plan_name": "Plan Mayo", "items": [{"sku": "MOTS1297", "nombre": "ACEITE", "cantidad": 10}], "total_skus": 1, "total_value": 85000.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == 1
        assert body["plan_name"] == "Plan Mayo"
        assert body["status"] == "draft"
        assert body["created_by"] == "admin"

        # GET by id
        resp2 = client.get(f"/purchase-plans/{body['id']}", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp2.status_code == 200
        assert resp2.json()["id"] == 1

    def test_list(self, client, admin_token):
        # Create 2 plans
        for i in range(2):
            client.post(
                "/purchase-plans",
                json={"plan_name": f"Plan {i}", "items": [{"sku": "X", "nombre": "X", "cantidad": 1}], "total_skus": 1, "total_value": 1000.0},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        resp = client.get("/purchase-plans", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_get_nonexistent(self, client, admin_token):
        resp = client.get("/purchase-plans/999", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 404

    def test_update_status(self, client, admin_token):
        # Create
        resp = client.post(
            "/purchase-plans",
            json={"plan_name": "P", "items": [{"sku": "A", "nombre": "A", "cantidad": 1}], "total_skus": 1, "total_value": 5000.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = resp.json()["id"]

        # Update to approved
        resp2 = client.patch(
            f"/purchase-plans/{pid}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "approved"

    def test_invalid_status(self, client, admin_token):
        resp = client.post(
            "/purchase-plans",
            json={"plan_name": "P", "items": [{"sku": "A", "nombre": "A", "cantidad": 1}], "total_skus": 1, "total_value": 5000.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = resp.json()["id"]
        resp2 = client.patch(
            f"/purchase-plans/{pid}/status",
            json={"status": "invalid"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 422

    def test_create_empty_items(self, client, admin_token):
        resp = client.post(
            "/purchase-plans",
            json={"plan_name": "Empty", "items": [], "total_skus": 0, "total_value": 0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422
