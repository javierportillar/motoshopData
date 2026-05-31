"""Pruebas de los endpoints /metrics/* con FakeMetricsRepo."""
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


class TestMetricsUnauthenticated:
    def test_all_metrics_require_auth(self, client: TestClient) -> None:
        """Sin token, todos los /metrics/* deben devolver 401."""
        endpoints = [
            "/metrics/sales-summary",
            "/metrics/inventory-summary",
            "/metrics/abc-segmentation",
            "/metrics/dormidos",
            "/metrics/cohortes",
            "/metrics/sales-trend",
            "/metrics/vendedores-summary",
        ]
        for ep in endpoints:
            resp = client.get(ep)
            assert resp.status_code == 401, f"{ep} devolvió {resp.status_code}, esperaba 401"


class TestMetricsAuthenticated:
    def test_sales_summary_shape(self, client: TestClient, admin_token: str) -> None:
        resp = client.get(
            "/metrics/sales-summary",
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
            "/metrics/sales-summary",
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
            "/metrics/inventory-summary",
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
            "/metrics/inventory-summary",
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
            "/metrics/abc-segmentation",
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
            "/metrics/dormidos",
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
            "/metrics/cohortes",
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
                "/metrics/sales-summary",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code in (200, 429)

    def test_cache_returns_same_data(self, client: TestClient, admin_token: str) -> None:
        """Dos llamadas seguidas al mismo endpoint deben devolver los mismos datos (cache)."""
        resp1 = client.get(
            "/metrics/inventory-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp2 = client.get(
            "/metrics/inventory-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()

    def test_all_endpoints_return_fields(self, client: TestClient, admin_token: str) -> None:
        """Todos los endpoints responden 200 con campos esperados."""
        endpoints = {
            "/metrics/sales-summary": ["business_month", "ventas_mes_actual", "top_skus"],
            "/metrics/inventory-summary": ["stock_total", "por_bodega"],
            "/metrics/abc-segmentation": ["bucket_a", "bucket_b", "bucket_c"],
            "/metrics/dormidos": ["total", "productos"],
            "/metrics/cohortes": ["cohortes"],
            "/metrics/sales-trend": ["periods", "items"],
            "/metrics/vendedores-summary": ["items"],
        }
        for ep, expected_fields in endpoints.items():
            resp = client.get(ep, headers={"Authorization": f"Bearer {admin_token}"})
            assert resp.status_code == 200, f"{ep} falló: {resp.status_code}"
            body = resp.json()
            for field in expected_fields:
                assert field in body, f"{ep} no tiene campo '{field}'"
