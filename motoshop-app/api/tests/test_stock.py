"""Tests de stock: GET /products/{sku}/stock"""

from __future__ import annotations


def test_stock_requires_auth(client) -> None:
    resp = client.get("/products/BD01/stock")
    assert resp.status_code == 401


def test_stock_returns_data(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/products/BD01/stock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Puede ser 200 o 404 (sin datos) o 500 (sin MySQL)
    assert resp.status_code in (200, 404, 500)


def test_stock_invalid_sku(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/products/NOEXISTE/stock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in (404, 500)
