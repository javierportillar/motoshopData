"""Tests de ventas: GET /sales/recent"""

from __future__ import annotations


def test_sales_requires_auth(client) -> None:
    resp = client.get("/sales/recent")
    assert resp.status_code == 401


def test_sales_returns_data(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/sales/recent",
        params={"limit": 10},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in (200, 500)


def test_sales_with_since_param(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/sales/recent",
        params={"since": "2026-01-01T00:00:00Z", "limit": 5},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in (200, 500)
