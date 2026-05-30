"""Pruebas de los endpoints POST /alerts/{id}/action + GET /alerts/actions/me."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from motoshop_api.app_writes.repo import (
    FakeAlertActionsRepo,
    FakeAuditRepo,
    get_alert_actions_repo,
    get_audit_repo,
    _reset_fake_repos,
)
from motoshop_api.main import app

# ─── Shared fake repos via dependency_overrides ──────────────

_SHARED_ALERT_REPO = FakeAlertActionsRepo()
_SHARED_AUDIT_REPO = FakeAuditRepo()

app.dependency_overrides[get_alert_actions_repo] = lambda: _SHARED_ALERT_REPO
app.dependency_overrides[get_audit_repo] = lambda: _SHARED_AUDIT_REPO


@pytest.fixture(autouse=True)
def _reset_fakes():
    """Limpia los fake repos entre tests."""
    _SHARED_ALERT_REPO._clear()
    _SHARED_AUDIT_REPO._clear()
    yield


IDEMPOTENCY_KEY = str(uuid.uuid4())
USER_ID = "admin"
ALERT_ID = "PROD-001"


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


@pytest.fixture()
def gerente_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import _users_cache, User

    _users_cache.clear()
    _users_cache["gerente1"] = User(
        username="gerente1",
        hashed_password=hash_password("gerente123"),
        email="gerente1@test.com",
        role="gerente",
    )
    resp = client.post("/auth/login", json={"username": "gerente1", "password": "gerente123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def vendedor_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import _users_cache, User

    _users_cache.clear()
    _users_cache["vendedor1"] = User(
        username="vendedor1",
        hashed_password=hash_password("vend123"),
        email="vendedor1@test.com",
        role="vendedor",
    )
    resp = client.post("/auth/login", json={"username": "vendedor1", "password": "vend123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(token: str, idempotency_key: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        h["Idempotency-Key"] = idempotency_key
    return h


# ─── Tests ────────────────────────────────────────────────────


class TestCreateActionUnauthenticated:
    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed", "reason": "ya cubierto"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code == 401


class TestCreateActionAuthorization:
    def test_vendedor_cannot_create_action(self, client: TestClient, vendedor_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed", "reason": "ya cubierto"},
            headers=_headers(vendedor_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 403

    def test_gerente_can_create_action(self, client: TestClient, gerente_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed", "reason": "ya cubierto"},
            headers=_headers(gerente_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 201


class TestCreateActionValidation:
    def test_missing_idempotency_key_returns_422(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed", "reason": "ok"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_invalid_idempotency_key_returns_422(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed", "reason": "ok"},
            headers=_headers(admin_token, idempotency_key="not-a-uuid"),
        )
        assert resp.status_code == 422

    def test_ordered_without_quantity_returns_422(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "ordered"},
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 422

    def test_dismissed_without_reason_returns_422(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed"},
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 422

    def test_postponed_without_postponed_to_returns_422(
        self, client: TestClient, admin_token: str
    ) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "postponed"},
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 422


class TestCreateActionSuccess:
    def test_ordered_action_returns_201(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "ordered", "quantity": 50, "supplier": "Proveedor X"},
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["alert_id"] == ALERT_ID
        assert body["action_type"] == "ordered"
        assert body["user_id"] == "admin"
        assert "id" in body
        assert "created_at" in body

    def test_dismissed_action_returns_201(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "dismissed", "reason": "stock cubierto por otro canal"},
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 201
        assert resp.json()["action_type"] == "dismissed"

    def test_postponed_action_returns_201(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={"action_type": "postponed", "postponed_to": "2026-06-15"},
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 201
        assert resp.json()["action_type"] == "postponed"

    def test_idempotency_same_key_returns_200_on_replay(
        self, client: TestClient, admin_token: str
    ) -> None:
        key = str(uuid.uuid4())
        body = {"action_type": "dismissed", "reason": "ya gestionado"}
        first = client.post(
            f"/alerts/{ALERT_ID}/action",
            json=body,
            headers=_headers(admin_token, key),
        )
        assert first.status_code == 201

        second = client.post(
            f"/alerts/{ALERT_ID}/action",
            json=body,
            headers=_headers(admin_token, key),
        )
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_can_add_notes_and_supplier(self, client: TestClient, admin_token: str) -> None:
        resp = client.post(
            f"/alerts/{ALERT_ID}/action",
            json={
                "action_type": "ordered",
                "quantity": 100,
                "supplier": "Distribuidora ABC",
                "notes": "Urgente, prioridad alta",
            },
            headers=_headers(admin_token, str(uuid.uuid4())),
        )
        assert resp.status_code == 201


class TestListMyActions:
    def test_list_actions_returns_paginated(self, client: TestClient, admin_token: str) -> None:
        # Crear 3 acciones
        for i in range(3):
            client.post(
                f"/alerts/{ALERT_ID}/action",
                json={"action_type": "dismissed", "reason": f"razón {i}"},
                headers=_headers(admin_token, str(uuid.uuid4())),
            )

        resp = client.get(
            "/alerts/actions/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body
        assert body["total"] >= 3
        assert len(body["items"]) >= 3

    def test_list_actions_respects_limit(self, client: TestClient, admin_token: str) -> None:
        for i in range(3):
            client.post(
                f"/alerts/{ALERT_ID}/action",
                json={"action_type": "dismissed", "reason": f"limit {i}"},
                headers=_headers(admin_token, str(uuid.uuid4())),
            )

        resp = client.get(
            "/alerts/actions/me?limit=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 1
