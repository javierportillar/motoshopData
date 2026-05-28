"""Tests de productos con FakeRepos — no requieren MySQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


FAKE_PRODUCTS = [
    {"codprod": "MOTS1011", "nomprod": "ACEITE 2T PREMIUN", "codbar": "MOTS1011"},
    {"codprod": "MOTS1012", "nomprod": "ACEITE 20W-50 4T", "codbar": "MOTS1012"},
    {"codprod": "MOTS1016", "nomprod": "ACEITE MOBIL 20W-50", "codbar": "MOTS1016"},
]


@pytest.fixture()
def client_with_fakes(fake_users):
    """Cliente con FakeProductsRepo inyectado."""
    from motoshop_api.main import app
    from motoshop_api.products.router import get_products_repo
    from motoshop_api.products.repo import FakeProductsRepo

    fake = FakeProductsRepo(items=FAKE_PRODUCTS)
    app.dependency_overrides[get_products_repo] = lambda: fake
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


def test_products_requires_auth(client_with_fakes) -> None:
    resp = client_with_fakes.get("/products")
    assert resp.status_code == 401


def test_products_list(client_with_fakes, fake_users, admin_token) -> None:
    resp = client_with_fakes.get(
        "/products?limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["items"][0]["codprod"] == "MOTS1011"


def test_products_search(client_with_fakes, fake_users, admin_token) -> None:
    resp = client_with_fakes.get(
        "/products?q=aceite&limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3  # all 3 products contain "aceite"


def test_products_pagination(client_with_fakes, fake_users, admin_token) -> None:
    resp = client_with_fakes.get(
        "/products?limit=2&offset=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0


def test_products_limit_exceeds_max(client_with_fakes, fake_users, admin_token) -> None:
    resp = client_with_fakes.get(
        "/products?limit=300",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422  # Validation error: limit > 200
