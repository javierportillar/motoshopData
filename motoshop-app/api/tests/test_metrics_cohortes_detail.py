"""Pruebas del endpoint /api/metrics/cohortes-detail con FakeMetricsRepo."""
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
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_cohortes_detail_requires_auth(client: TestClient) -> None:
    """Sin token, el endpoint debe devolver 401."""
    resp = client.get("/api/metrics/cohortes-detail")
    assert resp.status_code == 401


class TestCohortesDetail:
    def test_happy_path_returns_cohortes(self, client, admin_token) -> None:
        """Con token válido, devuelve detalle de cohortes."""
        resp = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "cohortes" in body
        assert len(body["cohortes"]) > 0
        assert "total_cohortes" in body
        assert body["total_cohortes"] > 0

    def test_cohorte_item_fields(self, client, admin_token) -> None:
        """Cada cohorte tiene los campos requeridos con tipos correctos."""
        resp = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        cohorte = body["cohortes"][0]
        for field in ("cohorte_mes", "total_clientes", "ltv_promedio", "retencion"):
            assert field in cohorte, f"Missing field: {field}"
        assert isinstance(cohorte["cohorte_mes"], str)
        assert isinstance(cohorte["total_clientes"], int)
        assert isinstance(cohorte["ltv_promedio"], float)
        assert len(cohorte["retencion"]) > 0

    def test_retencion_item_fields(self, client, admin_token) -> None:
        """Cada item de retención tiene los campos correctos."""
        resp = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        cohorte = body["cohortes"][0]
        ret = cohorte["retencion"][0]
        for field in ("mes_observacion", "num_clientes", "tasa_recurrencia"):
            assert field in ret, f"Missing field: {field}"
        assert isinstance(ret["num_clientes"], int)
        assert ret["num_clientes"] > 0

    def test_summary_fields(self, client, admin_token) -> None:
        """Los campos de resumen están presentes y tienen valores coherentes."""
        resp = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert body["total_cohortes"] == len(body["cohortes"])
        assert body["nuevos_este_mes"] >= 0
        assert body["recurrentes_este_mes"] >= 0
        assert body["top_recurrentes"] >= 0
        assert isinstance(body["nuevos_este_mes"], int)
        assert isinstance(body["recurrentes_este_mes"], int)
        assert isinstance(body["top_recurrentes"], int)

    def test_cohortes_ordered_chronologically(self, client, admin_token) -> None:
        """Las cohortes deben venir ordenadas cronológicamente."""
        resp = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        cohortes = body["cohortes"]
        for i in range(1, len(cohortes)):
            assert cohortes[i - 1]["cohorte_mes"] < cohortes[i]["cohorte_mes"], \
                f"Cohortes out of order: {cohortes[i-1]['cohorte_mes']} >= {cohortes[i]['cohorte_mes']}"

    def test_cache_returns_same_data(self, client, admin_token) -> None:
        """Dos llamadas seguidas deben devolver los mismos datos (cache)."""
        resp1 = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/api/metrics/cohortes-detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()
