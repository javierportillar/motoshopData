"""Tests de ventas con FakeSalesRepo — no requieren MySQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

FAKE_SALES = [
    {
        "numfven": "4857",
        "fecfven": "2025-11-07 12:43:20",
        "nitter": "900123456",
        "estfven": "A",
        "totfven": 99200.0,
    },
    {
        "numfven": "4746",
        "fecfven": "2025-10-29 09:09:08",
        "nitter": "900123456",
        "estfven": "A",
        "totfven": 2000.0,
    },
    {
        "numfven": "4109",
        "fecfven": "2025-08-15 16:01:58",
        "nitter": "900123456",
        "estfven": "A",
        "totfven": 410400.0,
    },
]


@pytest.fixture()
def client_with_sales(fake_users):
    """Cliente con FakeSalesRepo inyectado."""
    from motoshop_api.main import app
    from motoshop_api.sales.repo import FakeSalesRepo
    from motoshop_api.sales.router import get_sales_repo

    fake = FakeSalesRepo(items=FAKE_SALES)
    app.dependency_overrides[get_sales_repo] = lambda: fake
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


def test_sales_requires_auth(client_with_sales) -> None:
    resp = client_with_sales.get("/sales/recent")
    assert resp.status_code == 401


def test_sales_returns_data(client_with_sales, fake_users, admin_token) -> None:
    resp = client_with_sales.get(
        "/sales/recent?limit=5",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["items"][0]["numfven"] == "4857"
    assert data["items"][0]["totfven"] == 99200.0


def test_sales_with_limit(client_with_sales, fake_users, admin_token) -> None:
    resp = client_with_sales.get(
        "/sales/recent?limit=2",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
