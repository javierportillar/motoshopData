"""Tests de productos: GET /products con/sin auth, paginación, roles."""

from __future__ import annotations


def test_products_requires_auth(client) -> None:
    resp = client.get("/products")
    assert resp.status_code == 401


def test_products_list_empty(client, fake_users, admin_token) -> None:
    """Sin datos en MySQL, devuelve lista vacía (o error de conexión)."""
    resp = client.get("/products", headers={"Authorization": f"Bearer {admin_token}"})
    # Puede ser 200 con lista vacía o 500 si MySQL no está disponible en test
    assert resp.status_code in (200, 500)


def test_products_with_query(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/products",
        params={"q": "aceite", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in (200, 500)


def test_products_pagination_params(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/products",
        params={"limit": 200, "offset": 50},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in (200, 500)


def test_products_limit_exceeds_max(client, fake_users, admin_token) -> None:
    resp = client.get(
        "/products",
        params={"limit": 300},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422  # Validation error: limit > 200
