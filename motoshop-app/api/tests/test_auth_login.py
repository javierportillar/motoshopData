"""Tests de autenticación: login, token expirado, credenciales malas."""

from __future__ import annotations

import time

from motoshop_api.auth.jwt import create_access_token


def test_login_success(client, fake_users) -> None:
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_wrong_password_returns_401_without_user_enumeration(client, fake_users) -> None:
    """V4: login con password mala devuelve 401 genérico, sin filtrar si el usuario existe."""
    resp = client.post("/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Credenciales incorrectas"

    # Mismo error para usuario inexistente
    resp2 = client.post("/auth/login", json={"username": "noexiste", "password": "algo"})
    assert resp2.status_code == 401
    assert resp2.json()["detail"] == "Credenciales incorrectas"


def test_login_missing_fields(client) -> None:
    resp = client.post("/auth/login", json={})
    assert resp.status_code == 422


def test_auth_required_without_token(client) -> None:
    resp = client.get("/products")
    assert resp.status_code == 401


def test_auth_expired_token(client, fake_users) -> None:
    """V3: token vencido devuelve 401."""
    # Crear token con TTL 0 (expira inmediatamente)
    import motoshop_api.config as cfg
    original_ttl = cfg.settings.jwt_access_ttl_minutes
    cfg.settings.jwt_access_ttl_minutes = -1  # Forzar expiración
    try:
        token = create_access_token(subject="admin", role="admin")
    finally:
        cfg.settings.jwt_access_ttl_minutes = original_ttl

    resp = client.get("/products", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_auth_invalid_token(client) -> None:
    resp = client.get("/products", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


def test_auth_refresh_token_works(client, fake_users) -> None:
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    refresh = login_resp.json()["refresh_token"]

    resp = client.post("/auth/refresh", params={"token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
