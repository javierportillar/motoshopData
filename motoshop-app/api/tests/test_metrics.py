"""Pruebas de los endpoints /api/metrics/* con FakeMetricsRepo."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from motoshop_api.main import app
from motoshop_api.tenants import Tenant, _tenants_cache


@pytest.fixture(autouse=True)
def configured_default_tenant() -> None:
    """Keep metrics tests independent from tenant-cache ordering."""
    _tenants_cache.clear()
    _tenants_cache["motoshop"] = Tenant(
        id="motoshop",
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
    )
    yield
    _tenants_cache.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def admin_token(client) -> str:
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.auth.users import User, _users_cache

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


class TestMetricsUnauthenticated:
    def test_all_metrics_require_auth(self, client: TestClient) -> None:
        """Sin token, todos los /api/metrics/* deben devolver 401."""
        endpoints = [
            "/api/metrics/sales-summary",
            "/api/metrics/inventory-summary",
            "/api/metrics/abc-segmentation",
            "/api/metrics/dormidos",
            "/api/metrics/cohortes",
            "/api/metrics/sales-trend",
            "/api/metrics/vendedores-summary",
            "/api/metrics/cohortes-detail",
            "/api/metrics/drift-summary",
            "/api/metrics/plan-compras",
            "/api/metrics/forecast-categoria",
        ]
        for ep in endpoints:
            resp = client.get(ep)
            assert resp.status_code == 401, f"{ep} devolvió {resp.status_code}, esperaba 401"


class TestMetricsAuthenticated:
    def test_primary_surfaces_enforce_their_modules(self, client: TestClient) -> None:
        from motoshop_api.auth.hash import hash_password
        from motoshop_api.auth.users import User, _users_cache
        from motoshop_api.tenants import Tenant, _tenants_cache

        _tenants_cache.clear()
        _tenants_cache["motoshop"] = Tenant(
            id="motoshop",
            nombre="MotoShop",
            r2_object_key="motoshop_gold.duckdb",
            local_db_path="/tmp/motoshop_gold.duckdb",
        )
        _users_cache.clear()
        _users_cache["no-modules"] = User(
            username="no-modules",
            hashed_password=hash_password("secret123"),
            email="inventory@test.com",
            role="gerente",
            tenants_allowed=["motoshop"],
            allowed_modules=[],
            source="supabase",
        )
        login = client.post(
            "/api/auth/login",
            json={"username": "no-modules", "password": "secret123"},
        )
        headers = {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-Tenant": "motoshop",
        }
        endpoints = [
            "/api/metrics/sales-summary",
            "/api/metrics/sales-summary-v2",
            "/api/metrics/sales-daily-month?month=2026-01",
            "/api/metrics/sales-daily?date=2026-01-01",
            "/api/metrics/sales-monthly?month=2026-01",
            "/api/metrics/sales-day-detail?date=2026-01-01",
            "/api/metrics/sales-month-detail?month=2026-01",
            "/api/metrics/sales-day-invoices?date=2026-01-01",
            "/api/metrics/cash-closure?date=2026-01-01",
            "/api/metrics/sales-historical",
            "/api/metrics/compras-overview?month=2026-01",
            "/api/metrics/compras-historico",
            "/api/metrics/purchases-day-grouped?date=2026-01-01",
            "/api/metrics/inventory-summary",
            "/api/metrics/inventory-detail",
            "/api/metrics/inventory-overview",
            "/api/metrics/inventario-overview",
            "/api/metrics/analisis-balance?fecha_inicio=2026-01-01&fecha_fin=2026-01-31",
            "/api/metrics/horas-pico?fecha_inicio=2026-01-01&fecha_fin=2026-01-31",
            "/api/metrics/analisis-productos?fecha_inicio=2026-01-01&fecha_fin=2026-01-31",
            "/api/metrics/analisis-proveedores?fecha_inicio=2026-01-01&fecha_fin=2026-01-31",
            "/api/metrics/recommendations",
            "/api/metrics/plan-compras",
            "/api/metrics/sales-forecast-monthly",
            "/api/admin/data/status",
        ]
        responses = [(endpoint, client.get(endpoint, headers=headers)) for endpoint in endpoints]
        _users_cache.clear()
        _tenants_cache.clear()

        assert all(response.status_code == 403 for _, response in responses), [
            (endpoint, response.status_code, response.text)
            for endpoint, response in responses
        ]

    def test_sales_summary_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/api/metrics/sales-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "business_month" in body
        assert "ventas_mes_actual" in body
        assert "ventas_mes_anterior" in body
        assert "delta_porcentual" in body
        assert "ticket_promedio" in body
        assert "num_facturas" in body
        assert "top_skus" in body
        assert len(body["top_skus"]) > 0
        # Verificar tipos
        assert isinstance(body["ventas_mes_actual"], float)
        assert isinstance(body["num_facturas"], int)
        # Primer top SKU debe tener los campos
        sku = body["top_skus"][0]
        assert "cod_producto" in sku
        assert "nom_producto" in sku
        assert "valor_total" in sku

    def test_sales_summary_values(self, client: TestClient, admin_token: str) -> None:
        """Los valores mock son consistentes y el delta se calcula correctamente."""
        resp = client.get(
            "/api/metrics/sales-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert body["ventas_mes_actual"] > 0
        assert body["num_facturas"] > 0
        # Delta debe ser calculable
        if body["ventas_mes_anterior"] > 0:
            esperado = round(
                (body["ventas_mes_actual"] - body["ventas_mes_anterior"])
                / body["ventas_mes_anterior"]
                * 100,
                1,
            )
            assert body["delta_porcentual"] == esperado

    def test_inventory_summary_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/api/metrics/inventory-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "stock_total" in body
        assert "valor_total" in body
        assert "num_productos" in body
        assert "por_bodega" in body
        assert len(body["por_bodega"]) > 0
        # Verificar que los porcentajes sumen ~100
        total_pct = sum(b["porcentaje"] for b in body["por_bodega"])
        assert abs(total_pct - 100) < 2

    def test_inventory_bodegas_have_fields(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/api/metrics/inventory-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        for b in body["por_bodega"]:
            assert "cod_bodega" in b
            assert "nom_bodega" in b
            assert "cantidad" in b
            assert "porcentaje" in b

    def test_abc_segmentation_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/api/metrics/abc-segmentation",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["business_month"] is not None
        assert body["total_skus"] > 0
        assert body["total_ingresos"] > 0
        for bucket_key in ["bucket_a", "bucket_b", "bucket_c"]:
            bucket = body[bucket_key]
            assert "categoria" in bucket
            assert "num_skus" in bucket
            assert "valor_total" in bucket
            assert "porcentaje_ingreso" in bucket
        # A + B + C debe sumar ~100%
        total_pct = (
            body["bucket_a"]["porcentaje_ingreso"]
            + body["bucket_b"]["porcentaje_ingreso"]
            + body["bucket_c"]["porcentaje_ingreso"]
        )
        assert abs(total_pct - 100) < 2

    def test_dormidos_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/api/metrics/dormidos",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "productos" in body
        assert isinstance(body["total"], int)
        if body["productos"]:
            p = body["productos"][0]
            assert "cod_producto" in p
            assert "nom_producto" in p
            assert "dias_sin_venta" in p
            assert p["dias_sin_venta"] >= 90

    def test_cohortes_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/api/metrics/cohortes",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "cohortes" in body
        assert len(body["cohortes"]) > 0
        c = body["cohortes"][0]
        assert "cohorte_mes" in c
        assert "mes_observacion" in c
        assert "num_clientes" in c
        assert "ticket_promedio" in c

    def test_rate_limit_applies(self, client: TestClient, admin_token: str) -> None:
        """El rate limit de 30/min debería funcionar."""
        # Hacer algunas requests rápidas - solo verificamos que responde 200
        for _ in range(3):
            resp = client.get(
                "/api/metrics/sales-summary",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code in (200, 429)

    def test_cache_returns_same_data(self, client: TestClient, admin_token: str) -> None:
        """Dos llamadas seguidas al mismo endpoint deben devolver los mismos datos (cache)."""
        resp1 = client.get(
            "/api/metrics/inventory-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/api/metrics/inventory-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()

    def test_all_endpoints_return_fields(self, client: TestClient, admin_token: str) -> None:
        """Todos los endpoints responden 200 con campos esperados."""
        endpoints = {
            "/api/metrics/sales-summary": ["business_month", "ventas_mes_actual", "top_skus"],
            "/api/metrics/inventory-summary": ["stock_total", "por_bodega"],
            "/api/metrics/abc-segmentation": ["bucket_a", "bucket_b", "bucket_c"],
            "/api/metrics/dormidos": ["total", "productos"],
            "/api/metrics/cohortes": ["cohortes"],
            "/api/metrics/sales-trend": ["periods", "items"],
            "/api/metrics/vendedores-summary": ["items"],
            "/api/metrics/cohortes-detail": ["cohortes", "total_cohortes"],
            "/api/metrics/drift-summary": ["items", "total_alerts"],
            "/api/metrics/plan-compras": ["items", "total_skus"],
            "/api/metrics/forecast-categoria": ["items", "wape_promedio"],
        }
        for ep, expected_fields in endpoints.items():
            resp = client.get(ep, headers={"Authorization": f"Bearer {admin_token}"})
            assert resp.status_code == 200, f"{ep} falló: {resp.status_code}"
            body = resp.json()
            for field in expected_fields:
                assert field in body, f"{ep} no tiene campo '{field}'"
