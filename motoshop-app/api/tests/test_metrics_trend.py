"""Pruebas del endpoint /api/metrics/sales-trend con FakeMetricsRepo."""
from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from motoshop_api.metrics.repo import FakeMetricsRepo
from motoshop_api.metrics.router import get_repo
from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo, close_all_shared_connections
from motoshop_api.main import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def fake_metrics_repository():
    previous = app.dependency_overrides.get(get_repo)
    app.dependency_overrides[get_repo] = lambda: FakeMetricsRepo()
    yield
    if previous is None:
        app.dependency_overrides.pop(get_repo, None)
    else:
        app.dependency_overrides[get_repo] = previous


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


def test_sales_trend_requires_auth(client: TestClient) -> None:
    """Sin token, el endpoint debe devolver 401."""
    resp = client.get("/api/metrics/sales-trend")
    assert resp.status_code == 401


class TestSalesTrend:
    def test_happy_path_default_periods(self, client, admin_token) -> None:
        """Con token válido y 6 periodos por defecto, devuelve 200 con datos."""
        resp = client.get(
            "/api/metrics/sales-trend",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["periods"] == 6
        assert "items" in body
        assert len(body["items"]) == 6
        item = body["items"][0]
        for field in ("year", "month", "total_ventas", "num_facturas", "ticket_promedio"):
            assert field in item, f"Missing field: {field}"
        assert isinstance(item["year"], int)
        assert isinstance(item["month"], int)
        assert isinstance(item["num_facturas"], int)
        assert isinstance(item["total_ventas"], float)
        assert item["total_ventas"] > 0

    def test_custom_periods(self, client, admin_token) -> None:
        """Con periods=3 devuelve exactamente 3 items."""
        resp = client.get(
            "/api/metrics/sales-trend?periods=3",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["periods"] == 3
        assert len(body["items"]) == 3

    def test_periods_1(self, client, admin_token) -> None:
        """periods=1 devuelve 1 item."""
        resp = client.get(
            "/api/metrics/sales-trend?periods=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["periods"] == 1
        assert len(body["items"]) == 1

    def test_periods_max_24(self, client, admin_token) -> None:
        """periods=24 es el máximo permitido."""
        resp = client.get(
            "/api/metrics/sales-trend?periods=24",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 24

    def test_invalid_periods_zero(self, client, admin_token) -> None:
        """periods=0 → 422."""
        resp = client.get(
            "/api/metrics/sales-trend?periods=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_invalid_periods_over_max(self, client, admin_token) -> None:
        """periods=100 → 422."""
        resp = client.get(
            "/api/metrics/sales-trend?periods=100",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_items_are_chronological(self, client, admin_token) -> None:
        """Los items deben venir ordenados cronológicamente."""
        resp = client.get(
            "/api/metrics/sales-trend?periods=6",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        items = body["items"]
        for i in range(1, len(items)):
            prev = items[i - 1]
            curr = items[i]
            # Same year: month must increase
            if prev["year"] == curr["year"]:
                assert curr["month"] > prev["month"], f"Months out of order at index {i}"
            else:
                assert curr["year"] > prev["year"], f"Years out of order at index {i}"


def test_fake_sales_trend_uses_consecutive_calendar_months() -> None:
    response = FakeMetricsRepo().get_sales_trend(periods=6)
    month_indices = [item.year * 12 + item.month - 1 for item in response.items]

    assert len(response.items) == 6
    assert all(
        month_indices[index] + 1 == month_indices[index + 1]
        for index in range(len(month_indices) - 1)
    )


@pytest.mark.parametrize("periods", [1, 3, 6, 24])
def test_duckdb_sales_trend_returns_exact_month_window(
    tmp_path,
    monkeypatch,
    periods: int,
) -> None:
    db_path = tmp_path / "trend.duckdb"
    today = date.today()
    current_index = today.year * 12 + today.month - 1
    months = []
    for offset in range(periods - 1, -1, -1):
        year, month_index = divmod(current_index - offset, 12)
        months.append(date(year, month_index + 1, 1))

    connection = duckdb.connect(str(db_path))
    connection.execute(
        "CREATE TABLE silver_fact_ventas "
        "(business_date DATE, total_factura DOUBLE, estado_documento VARCHAR)"
    )
    connection.executemany(
        "INSERT INTO silver_fact_ventas VALUES (?, ?, ?)",
        [(month, 100.0, "B") for month in months]
        + [(today + timedelta(days=1), 10_000.0, "B")]
        + [(months[0] - timedelta(days=1), 10_000.0, "B")],
    )
    connection.close()
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb._bootstrap_duckdb_from_r2",
        lambda *_args: None,
    )

    try:
        response = DuckDBMetricsRepo(db_path=db_path, tenant="trend-test").get_sales_trend(periods)
    finally:
        close_all_shared_connections()

    returned_months = [(item.year, item.month) for item in response.items]
    expected_months = [(month.year, month.month) for month in months]
    assert returned_months == expected_months
    assert response.periods == periods
    assert all(item.total_ventas == 100.0 for item in response.items)
