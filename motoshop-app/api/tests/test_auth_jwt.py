"""Tests para JWT con soporte multi-tenant (tenants_allowed claim)."""

from __future__ import annotations

import jwt as pyjwt

from motoshop_api.auth.jwt import create_access_token, decode_token
from motoshop_api.config import settings


def test_create_access_token_includes_tenants_allowed() -> None:
    """create_access_token debe incluir tenants_allowed en el payload."""
    token = create_access_token(
        subject="admin",
        role="admin",
        tenants_allowed=["motoshop", "masvital"],
    )
    payload = decode_token(token)
    assert payload is not None
    assert payload["tenants_allowed"] == ["motoshop", "masvital"]


def test_create_access_token_defaults_to_empty_list() -> None:
    """create_access_token sin tenants_allowed debe default a []."""
    token = create_access_token(subject="admin", role="admin")
    payload = decode_token(token)
    assert payload is not None
    assert payload["tenants_allowed"] == []


def test_create_access_token_with_none_tenants_allowed() -> None:
    """create_access_token con tenants_allowed=None debe poner []."""
    token = create_access_token(subject="admin", role="admin", tenants_allowed=None)
    payload = decode_token(token)
    assert payload is not None
    assert payload["tenants_allowed"] == []


def test_create_access_token_single_tenant() -> None:
    """create_access_token con un solo tenant."""
    token = create_access_token(
        subject="vendedor1",
        role="vendedor",
        tenants_allowed=["motoshop"],
    )
    payload = decode_token(token)
    assert payload is not None
    assert payload["tenants_allowed"] == ["motoshop"]


def test_login_returns_token_with_tenants_allowed(client, fake_users) -> None:
    """Login debe retornar un token con tenants_allowed del usuario."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = decode_token(token)
    assert payload is not None
    # fake_users crea User sin tenants_allowed, debe ser []
    assert payload["tenants_allowed"] == []


def test_refresh_returns_token_with_tenants_allowed(client, fake_users) -> None:
    """Refresh debe retornar un token con tenants_allowed del usuario."""
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post("/api/auth/refresh", json={"token": refresh_token})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    payload = decode_token(new_access)
    assert payload is not None
    assert "tenants_allowed" in payload
