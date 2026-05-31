"""Pruebas CRUD /api/purchase-plans con FakePurchasePlansRepo."""
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
    _users_cache["admin"] = User(username="admin", hashed_password=hash_password("admin123"), email="admin@test.com", role="admin")
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def vendedor_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import _users_cache, User
    _users_cache["vendedor1"] = User(username="vendedor1", hashed_password=hash_password("vend123"), email="vendedor1@test.com", role="vendedor")
    resp = client.post("/api/auth/login", json={"username": "vendedor1", "password": "vend123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def gerente_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import _users_cache, User
    _users_cache["gerente1"] = User(username="gerente1", hashed_password=hash_password("ger123"), email="gerente1@test.com", role="gerente")
    resp = client.post("/api/auth/login", json={"username": "gerente1", "password": "ger123"})
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
    assert client.get("/api/purchase-plans").status_code == 401
    assert client.post("/api/purchase-plans", json={"plan_name": "test", "items": [], "total_skus": 0, "total_value": 0}).status_code == 401


class TestPurchasePlansCRUD:
    def test_create_and_get(self, client, admin_token):
        resp = client.post(
            "/api/purchase-plans",
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
        resp2 = client.get(f"/api/purchase-plans/{body['id']}", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp2.status_code == 200
        assert resp2.json()["id"] == 1

    def test_list(self, client, admin_token):
        # Create 2 plans
        for i in range(2):
            client.post(
                "/api/purchase-plans",
                json={"plan_name": f"Plan {i}", "items": [{"sku": "X", "nombre": "X", "cantidad": 1}], "total_skus": 1, "total_value": 1000.0},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        resp = client.get("/api/purchase-plans", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_get_nonexistent(self, client, admin_token):
        resp = client.get("/api/purchase-plans/999", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 404

    def test_update_status(self, client, admin_token):
        # Create
        resp = client.post(
            "/api/purchase-plans",
            json={"plan_name": "P", "items": [{"sku": "A", "nombre": "A", "cantidad": 1}], "total_skus": 1, "total_value": 5000.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = resp.json()["id"]

        # Update to approved
        resp2 = client.patch(
            f"/api/purchase-plans/{pid}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "approved"

    def test_invalid_status(self, client, admin_token):
        resp = client.post(
            "/api/purchase-plans",
            json={"plan_name": "P", "items": [{"sku": "A", "nombre": "A", "cantidad": 1}], "total_skus": 1, "total_value": 5000.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = resp.json()["id"]
        resp2 = client.patch(
            f"/api/purchase-plans/{pid}/status",
            json={"status": "invalid"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 422

    def test_create_empty_items(self, client, admin_token):
        resp = client.post(
            "/api/purchase-plans",
            json={"plan_name": "Empty", "items": [], "total_skus": 0, "total_value": 0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422


class TestPurchasePlansAuthorization:
    def _create_plan(self, client, token, name="Plan"):
        return client.post(
            "/api/purchase-plans",
            json={"plan_name": name, "items": [{"sku": "A", "nombre": "A", "cantidad": 1}], "total_skus": 1, "total_value": 1000.0},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_vendedor_cannot_read_other_plan(self, client, admin_token, vendedor_token):
        resp = self._create_plan(client, admin_token)
        pid = resp.json()["id"]
        resp2 = client.get(f"/api/purchase-plans/{pid}", headers={"Authorization": f"Bearer {vendedor_token}"})
        assert resp2.status_code == 403

    def test_vendedor_cannot_update_status(self, client, admin_token, vendedor_token):
        resp = self._create_plan(client, admin_token)
        pid = resp.json()["id"]
        resp2 = client.patch(
            f"/api/purchase-plans/{pid}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {vendedor_token}"},
        )
        assert resp2.status_code == 403  # role check: vendedor no tiene permiso

    def test_admin_can_read_any_plan(self, client, vendedor_token, admin_token):
        resp = self._create_plan(client, vendedor_token, "VendedorPlan")
        pid = resp.json()["id"]
        resp2 = client.get(f"/api/purchase-plans/{pid}", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp2.status_code == 200
        assert resp2.json()["plan_name"] == "VendedorPlan"

    def test_gerente_can_update_own_plan(self, client, gerente_token):
        resp = self._create_plan(client, gerente_token, "GerentePlan")
        pid = resp.json()["id"]
        resp2 = client.patch(
            f"/api/purchase-plans/{pid}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {gerente_token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "approved"

    def test_gerente_cannot_update_admin_plan(self, client, admin_token, gerente_token):
        resp = self._create_plan(client, admin_token, "AdminPlan")
        pid = resp.json()["id"]
        resp2 = client.patch(
            f"/api/purchase-plans/{pid}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {gerente_token}"},
        )
        assert resp2.status_code == 403
