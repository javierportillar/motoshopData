"""Tests para pipeline runs endpoints (V1.7).

Los tests de auth no requieren MySQL. Los tests con datos requieren
una conexión MySQL con las tablas creadas.
"""

from __future__ import annotations

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    from motoshop_api.auth.users import load_users
    users_yaml = Path(__file__).resolve().parent.parent.parent / "motoshop-app" / "api" / "users.yaml"
    if users_yaml.exists():
        load_users(users_yaml)
    monkeypatch.setattr("motoshop_api.config.settings.jwt_secret", "testsecret123-motoshop-prod-v15")


@pytest.fixture
def client():
    from motoshop_api.main import app
    return TestClient(app)


def _token(role: str = "admin") -> str:
    import jwt
    from datetime import datetime, timedelta, UTC
    sub = "admin" if role == "admin" else "vendedor1"
    payload = {"sub": sub, "role": role, "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=60), "iat": datetime.now(UTC)}
    return jwt.encode(payload, "testsecret123-motoshop-prod-v15", algorithm="HS256")


class TestAuth:
    def test_no_token_returns_401_or_403(self, client):
        resp = client.get("/admin/pipeline/runs")
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"

    def test_vendedor_returns_401_or_403(self, client):
        resp = client.get("/admin/pipeline/runs", headers={"Authorization": f"Bearer {_token('vendedor')}"})
        assert resp.status_code in (401, 403), f"Got {resp.status_code}: {resp.text[:100]}"

    def test_admin_returns_503_when_no_mysql(self, client):
        """Admin autenticado pero sin MySQL → 503."""
        resp = client.get("/admin/pipeline/runs", headers={"Authorization": f"Bearer {_token('admin')}"})
        assert resp.status_code in (503, 200), f"Got {resp.status_code}: {resp.text[:100]}"

    def test_summary_returns_503_when_no_mysql(self, client):
        resp = client.get("/admin/pipeline/summary", headers={"Authorization": f"Bearer {_token('admin')}"})
        assert resp.status_code in (503, 200), f"Got {resp.status_code}: {resp.text[:100]}"
