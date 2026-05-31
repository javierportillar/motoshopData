"""Pruebas del endpoint /metrics/drift-summary con FakeMetricsRepo."""
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
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_drift_requires_auth(client: TestClient) -> None:
    """Sin token, el endpoint debe devolver 401."""
    resp = client.get("/metrics/drift-summary")
    assert resp.status_code == 401


class TestDriftSummary:
    def test_happy_path_returns_items(self, client, admin_token) -> None:
        """Con token válido, devuelve alertas de drift."""
        resp = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) > 0

    def test_item_fields_match_frontend_contract(self, client, admin_token) -> None:
        """Cada item tiene los campos que espera Dev T2 en drift/page.tsx."""
        resp = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        item = body["items"][0]
        for field in ("metric_name", "detected_at", "drift_magnitude", "threshold", "status", "recommended_action"):
            assert field in item, f"Missing field: {field}"
        assert isinstance(item["metric_name"], str)
        assert isinstance(item["drift_magnitude"], float)
        assert isinstance(item["threshold"], float)
        assert item["status"] in ("active", "resolved", "warning")

    def test_summary_counts(self, client, admin_token) -> None:
        """Los contadores de resumen son coherentes."""
        resp = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert body["total_alerts"] == len(body["items"])
        assert body["active_count"] >= 0
        assert body["warning_count"] >= 0
        assert body["active_count"] + body["warning_count"] <= body["total_alerts"]
        assert body["current_threshold"] > 0

    def test_items_ordered_by_date_desc(self, client, admin_token) -> None:
        """Las alertas deben venir ordenadas por fecha descendente."""
        resp = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        items = body["items"]
        for i in range(1, len(items)):
            assert items[i - 1]["detected_at"] >= items[i]["detected_at"], \
                f"Drift alerts out of order: {items[i-1]['detected_at']} < {items[i]['detected_at']}"

    def test_cache_returns_same_data(self, client, admin_token) -> None:
        """Dos llamadas seguidas deben devolver los mismos datos (cache)."""
        resp1 = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()

    def test_summary_types(self, client, admin_token) -> None:
        """Los campos de resumen tienen tipos correctos."""
        resp = client.get(
            "/metrics/drift-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert isinstance(body["total_alerts"], int)
        assert isinstance(body["active_count"], int)
        assert isinstance(body["warning_count"], int)
        assert isinstance(body["current_threshold"], float)
