"""Tests para la gestión de usuarios (RBAC) admin-only sobre Supabase (app_users)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from motoshop_api.auth.hash import hash_password
from motoshop_api.auth.users import _users_cache
from motoshop_api.tenants import Tenant, _tenants_cache
from motoshop_api.users import router as users_router
from motoshop_api.users import supabase_repo


class FakeUsersStore:
    """Fake en memoria de la tabla app_users."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def list_users(self) -> list[dict]:
        return list(self.rows.values())

    def get_user(self, username: str) -> dict | None:
        return self.rows.get(username)

    def create_user(self, row: dict) -> dict:
        row = {**row, "created_at": "2026-07-12T00:00:00Z", "updated_at": "2026-07-12T00:00:00Z"}
        self.rows[row["username"]] = row
        return row

    def update_user(self, username: str, patch: dict) -> dict:
        self.rows[username] = {**self.rows[username], **patch}
        return self.rows[username]


@pytest.fixture()
def fake_store(monkeypatch):
    store = FakeUsersStore()
    monkeypatch.setattr(supabase_repo, "is_configured", lambda: True)
    for name in ("list_users", "get_user", "create_user", "update_user"):
        monkeypatch.setattr(supabase_repo, name, getattr(store, name))
    yield store


@pytest.fixture(autouse=True)
def configured_tenants() -> None:
    """Expose the same tenant registry the admin API validates in production."""
    _tenants_cache.clear()
    for tenant_id in ("motoshop", "masvital"):
        _tenants_cache[tenant_id] = Tenant(
            id=tenant_id,
            nombre=tenant_id.title(),
            r2_object_key=f"{tenant_id}_gold.duckdb",
            local_db_path=f"/tmp/{tenant_id}_gold.duckdb",
        )
    yield
    _tenants_cache.clear()


def _admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop"}


def test_list_requires_admin(client, vendedor_token, fake_store) -> None:
    resp = client.get("/api/admin/users", headers=_admin_headers(vendedor_token))
    assert resp.status_code == 403


def test_create_user_hides_hash_and_appears_in_list(client, admin_token, fake_store) -> None:
    resp = client.post(
        "/api/admin/users",
        json={
            "username": "gerencia1",
            "password": "clave123",
            "email": "g@test.com",
            "role": "gerente",
            "tenants_allowed": ["motoshop"],
            "allowed_modules": ["inventario", "analisis", "forecast"],
        },
        headers=_admin_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "hashed_password" not in body
    assert body["allowed_modules"] == ["inventario", "analisis", "forecast"]
    # queda en la cache en memoria tras el sync
    assert "gerencia1" in _users_cache
    assert _users_cache["gerencia1"].allowed_modules == ["inventario", "analisis", "forecast"]

    lst = client.get("/api/admin/users", headers=_admin_headers(admin_token))
    assert any(u["username"] == "gerencia1" for u in lst.json()["items"])


def test_create_duplicate_is_conflict(client, admin_token, fake_store) -> None:
    # 'admin' ya existe en la cache (fixture fake_users)
    resp = client.post(
        "/api/admin/users",
        json={
            "username": "admin",
            "password": "x1234",
            "role": "admin",
            "tenants_allowed": ["motoshop"],
        },
        headers=_admin_headers(admin_token),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "legacy_user_requires_explicit_migration"


def test_explicit_legacy_migration_creates_managed_supabase_identity(
    client, admin_token, fake_store
) -> None:
    response = client.post(
        "/api/admin/users",
        json={
            "username": "admin",
            "password": "a-new-password",
            "email": "managed-admin@test.com",
            "role": "admin",
            "tenants_allowed": ["motoshop"],
            "allowed_modules": [],
            "migrate_legacy": True,
        },
        headers=_admin_headers(admin_token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["source"] == "supabase"
    assert response.json()["manageable"] is True
    assert fake_store.rows["admin"]["created_by"] == "admin:legacy-migration"
    assert _users_cache["admin"].source == "supabase"


def test_empty_supabase_table_still_lists_legacy_admin(
    client, admin_token, fake_store
) -> None:
    response = client.get("/api/admin/users", headers=_admin_headers(admin_token))

    assert response.status_code == 200, response.text
    body = response.json()
    admin = next(item for item in body["items"] if item["username"] == "admin")
    assert admin == {
        "username": "admin",
        "email": "admin@test.com",
        "role": "admin",
        "tenants_allowed": [],
        "allowed_modules": [],
        "active": True,
        "source": "legacy",
        "manageable": False,
        "created_by": None,
        "created_at": None,
        "updated_at": None,
    }
    assert body["total"] == len(body["items"])


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    [
        (
            {
                "username": "badtenant",
                "password": "clave123",
                "role": "vendedor",
                "tenants_allowed": ["unknown"],
                "allowed_modules": ["inventario"],
            },
            "tenant",
        ),
        (
            {
                "username": "badmodule",
                "password": "clave123",
                "role": "vendedor",
                "tenants_allowed": ["motoshop"],
                "allowed_modules": ["inventario", "root-shell"],
            },
            "módulo",
        ),
        (
            {
                "username": "notenant",
                "password": "clave123",
                "role": "vendedor",
                "tenants_allowed": [],
                "allowed_modules": ["inventario"],
            },
            "tenant",
        ),
        (
            {
                "username": "missingtenant",
                "password": "clave123",
                "role": "vendedor",
                "allowed_modules": ["inventario"],
            },
            "tenant",
        ),
    ],
)
def test_create_rejects_invalid_scope(
    client, admin_token, fake_store, payload: dict, expected_fragment: str
) -> None:
    response = client.post(
        "/api/admin/users",
        json=payload,
        headers=_admin_headers(admin_token),
    )

    assert response.status_code == 422, response.text
    assert expected_fragment in response.text.lower()


def test_deactivated_user_cannot_login(client, admin_token, fake_store) -> None:
    client.post(
        "/api/admin/users",
        json={
            "username": "empleado1",
            "password": "clave123",
            "role": "vendedor",
            "tenants_allowed": ["motoshop"],
        },
        headers=_admin_headers(admin_token),
    )
    # login ok mientras activo
    ok = client.post("/api/auth/login", json={"username": "empleado1", "password": "clave123"})
    assert ok.status_code == 200
    # desactivar
    d = client.delete("/api/admin/users/empleado1", headers=_admin_headers(admin_token))
    assert d.status_code == 200
    assert d.json()["active"] is False
    # ahora no puede loguear
    blocked = client.post("/api/auth/login", json={"username": "empleado1", "password": "clave123"})
    assert blocked.status_code == 403


def test_cannot_deactivate_self(client, admin_token, fake_store) -> None:
    # admin existe en Supabase para pasar el get_user, pero es uno mismo
    fake_store.rows["admin"] = {
        "username": "admin",
        "hashed_password": hash_password("admin123"),
        "email": "a@test.com",
        "role": "admin",
        "tenants_allowed": [],
        "allowed_modules": [],
        "active": True,
    }
    resp = client.delete("/api/admin/users/admin", headers=_admin_headers(admin_token))
    assert resp.status_code == 400


def test_update_changes_modules_and_role(client, admin_token, fake_store) -> None:
    client.post(
        "/api/admin/users",
        json={
            "username": "user1",
            "password": "clave123",
            "role": "vendedor",
            "tenants_allowed": ["motoshop"],
            "allowed_modules": ["alerts"],
        },
        headers=_admin_headers(admin_token),
    )
    resp = client.patch(
        "/api/admin/users/user1",
        json={"role": "gerente", "allowed_modules": ["inventario"]},
        headers=_admin_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "gerente"
    assert resp.json()["allowed_modules"] == ["inventario"]


def test_guard_blocks_deactivating_last_admin() -> None:
    _users_cache.clear()
    from motoshop_api.auth.users import User

    _users_cache["solo"] = User(
        username="solo", hashed_password="x", email="", role="admin", active=True
    )
    existing = {"username": "solo", "role": "admin", "active": True}
    with pytest.raises(HTTPException) as exc:
        users_router._guard_last_admin(existing, {"active": False}, actor="solo", username="solo")
    assert exc.value.status_code == 400
    _users_cache.clear()
