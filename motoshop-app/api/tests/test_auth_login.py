"""Tests de autenticación: login, token expirado, credenciales malas, timing."""

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
    import motoshop_api.config as cfg

    original_ttl = cfg.settings.jwt_access_ttl_minutes
    cfg.settings.jwt_access_ttl_minutes = -1
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
    """Test refresh con token en body (no query string)."""
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    refresh = login_resp.json()["refresh_token"]

    resp = client.post("/auth/refresh", json={"token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_timing_is_similar(client, fake_users) -> None:
    """Timing-safe: tiempo similar para usuario existente vs inexistente."""
    # Usuario inexistente
    t0 = time.perf_counter()
    client.post("/auth/login", json={"username": "noexiste", "password": "x"})
    t_no = time.perf_counter() - t0

    # Usuario existente con password mala
    t1 = time.perf_counter()
    client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    t_yes = time.perf_counter() - t1

    # Diferencia menor al 50% del menor
    if min(t_no, t_yes) > 0:
        diff = abs(t_no - t_yes) / min(t_no, t_yes)
        assert diff < 0.5, f"timing leak: no={t_no:.3f}s, yes={t_yes:.3f}s"
