"""Tests de stock con FakeStockRepo — no requieren MySQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

FAKE_STOCK = {
    "MOTS1011": {
        "sku": "MOTS1011",
        "nomprod": "ACEITE 2T PREMIUN",
        "total": 15.0,
        "by_bodega": [
            {"codbod": "BD01", "nombod": "BODEGA PRINCIPAL", "cantidad": 10.0},
            {"codbod": "BD02", "nombod": "BODEGA SECUNDARIA", "cantidad": 5.0},
        ],
    }
}


@pytest.fixture()
def client_with_stock(fake_users):
    """Cliente con FakeStockRepo inyectado."""
    from motoshop_api.main import app
    from motoshop_api.stock.repo import FakeStockRepo
    from motoshop_api.stock.router import get_stock_repo

    fake = FakeStockRepo(data=FAKE_STOCK)
    app.dependency_overrides[get_stock_repo] = lambda: fake
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


def test_stock_requires_auth(client_with_stock) -> None:
    resp = client_with_stock.get("/products/MOTS1011/stock")
    assert resp.status_code == 401


def test_stock_returns_data(client_with_stock, fake_users, admin_token) -> None:
    resp = client_with_stock.get(
        "/products/MOTS1011/stock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sku"] == "MOTS1011"
    assert data["nomprod"] == "ACEITE 2T PREMIUN"
    assert data["total"] == 15.0
    assert len(data["by_bodega"]) == 2
    assert data["by_bodega"][0]["cantidad"] == 10.0
    assert data["by_bodega"][1]["cantidad"] == 5.0


def test_stock_not_found(client_with_stock, fake_users, admin_token) -> None:
    resp = client_with_stock.get(
        "/products/NOEXISTE/stock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_stock_cache_hits_second_call() -> None:
    """R-X2: segunda llamada al mismo SKU sale del caché, no del repo."""
    from motoshop_api.stock import repo as stock_repo_module

    stock_repo_module.clear_stock_cache()

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def first(self):
            return self._rows[0] if self._rows else None

        def all(self):
            return self._rows

    class FakeConnection:
        def __init__(self):
            self.execute_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, stmt):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return FakeResult([{"codprod": "MOTS1011", "nomprod": "ACEITE 2T PREMIUN"}])
            return FakeResult(
                [
                    {"codbod": "BD01", "cantidad": "10"},
                    {"codbod": "BD02", "cantidad": "5"},
                ]
            )

    class FakeEngine:
        def __init__(self):
            self.connect_calls = 0
            self.connection = FakeConnection()

        def connect(self):
            self.connect_calls += 1
            return self.connection

    repo = stock_repo_module.StockRepo(FakeEngine())
    first = repo.get_stock_by_sku("MOTS1011")
    second = repo.get_stock_by_sku("MOTS1011")

    assert first == second
    assert first["total"] == 15.0
    assert len(first["by_bodega"]) == 2
    assert first["by_bodega"][0]["cantidad"] == 10.0
    assert first["by_bodega"][1]["cantidad"] == 5.0
    assert repo._engine.connect_calls == 1
    stock_repo_module.clear_stock_cache()
