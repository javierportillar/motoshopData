"""Fixtures para tests de la API."""

from __future__ import annotations

import os

# Set test environment BEFORE any imports
os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENV"] = "test"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,https://api.fragloesja.uk,http://localhost:8000"
os.environ["DATABRICKS_HTTP_PATH"] = ""  # Force FakeForecastRepo / FakeAlertsRepo
os.environ["DATABRICKS_HOST"] = ""
os.environ["DATABRICKS_TOKEN"] = ""

import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.router import limiter
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.db.engine import reset_engine
from motoshop_api.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Limpia el rate limiter entre tests."""
    storage = limiter._storage
    # Limpiar el dict interno del storage
    if hasattr(storage, "storage") and isinstance(storage.storage, dict):
        storage.storage.clear()
    yield


@pytest.fixture()
def client():
    """Cliente HTTP de prueba."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_engine():
    """Reset del engine singleton entre tests."""
    yield
    reset_engine()


@pytest.fixture()
def fake_users():
    """Crea 3 usuarios fake en memoria para tests de auth."""
    from motoshop_api.auth.hash import hash_password

    _users_cache.clear()
    users = {
        "admin": User(
            username="admin",
            hashed_password=hash_password("admin123"),
            email="admin@test.com",
            role="admin",
        ),
        "vendedor1": User(
            username="vendedor1",
            hashed_password=hash_password("vend123"),
            email="vendedor1@test.com",
            role="vendedor",
        ),
    }
    _users_cache.update(users)
    yield users
    _users_cache.clear()


@pytest.fixture()
def admin_token(client, fake_users) -> str:
    """Obtiene un access token de admin."""
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture()
def vendedor_token(client, fake_users) -> str:
    """Obtiene un access token de vendedor."""
    resp = client.post("/auth/login", json={"username": "vendedor1", "password": "vend123"})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]
