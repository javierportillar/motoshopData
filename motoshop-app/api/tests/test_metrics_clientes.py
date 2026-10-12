"""Pruebas del directorio y perfiles de clientes (V1.22).

Cubren dos capas:

1. Contrato de los endpoints `/api/metrics/clientes*` con ``FakeMetricsRepo``
   (backend por defecto en tests, ``data_backend=databricks``).
2. Lógica real de agregación en ``DuckDBMetricsRepo`` contra un snapshot DuckDB
   sintético: reglas de venta válida, exclusión del cliente genérico y de NIT
   vacíos, reconciliación cabecera↔detalle y normalización de nombres.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.main import app
from motoshop_api.metrics.repo import FakeMetricsRepo
from motoshop_api.metrics.repo_duckdb import (
    DuckDBMetricsRepo,
    close_all_shared_connections,
)
from motoshop_api.metrics.router import get_customer_repo

PERIOD_START = "2024-01-01"
PERIOD_END = "2026-12-31"


# ── Endpoint contract (FakeMetricsRepo) ─────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def fake_client():
    """Client wired to FakeMetricsRepo so endpoint tests never touch local data."""
    authorized_user = User(
        username="admin",
        hashed_password="x",
        email="admin@test.com",
        role="admin",
        tenants_allowed=["motoshop"],
        allowed_modules=["ventas-summary"],
    )
    overrides = {
        get_current_user: lambda: authorized_user,
        get_tenant: lambda: "motoshop",
        get_customer_repo: lambda: FakeMetricsRepo(),
    }
    app.dependency_overrides.update(overrides)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


def test_clientes_requires_auth(client: TestClient) -> None:
    assert client.get("/api/metrics/clientes").status_code == 401


def test_perfil_requires_auth(client: TestClient) -> None:
    assert client.get("/api/metrics/clientes/1085320887/perfil").status_code == 401


def test_facturas_requires_auth(client: TestClient) -> None:
    assert client.get("/api/metrics/clientes/1085320887/facturas").status_code == 401


class TestClientesDirectoryEndpoint:
    def test_happy_path_shape(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"periodo", "resumen", "items", "paginacion"}
        assert body["resumen"]["ventas_totales_validas"] > 0
        item = body["items"][0]
        assert set(item) == {
            "customer_id",
            "nombre_canonico",
            "ventas_total",
            "facturas",
            "ticket_promedio",
            "primera_compra",
            "ultima_compra",
        }

    def test_participacion_is_ratio(self, fake_client) -> None:
        body = fake_client.get("/api/metrics/clientes").json()
        ratio = body["resumen"]["top10_participacion"]
        assert 0.0 <= ratio <= 1.0

    def test_invalid_sort_field_is_rejected(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes?sort_by=drop_table")
        assert resp.status_code == 422

    def test_page_size_over_limit_is_rejected(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes?page_size=101")
        assert resp.status_code == 422

    def test_inverted_date_range_is_rejected(self, fake_client) -> None:
        resp = fake_client.get(
            "/api/metrics/clientes?fecha_inicio=2026-01-01&fecha_fin=2025-01-01"
        )
        assert resp.status_code == 422


class TestClienteProfileEndpoint:
    def test_happy_path_shape(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes/1085320887/perfil")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cliente"]["customer_id"] == "1085320887"
        assert set(body["resumen"]) == {
            "ventas_total",
            "facturas",
            "ticket_promedio",
            "primera_compra",
            "ultima_compra",
            "unidades_vendidas",
        }
        assert isinstance(body["productos_top"], list)

    def test_generic_customer_returns_404(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes/222222222/perfil")
        assert resp.status_code == 404


class TestClienteFacturasEndpoint:
    def test_happy_path_shape(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes/1085320887/facturas")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {
            "items",
            "total",
            "total_lineas",
            "total_paginas",
            "pagina",
            "tamano_pagina",
        }

    def test_unknown_customer_returns_404(self, fake_client) -> None:
        resp = fake_client.get("/api/metrics/clientes/0000000000/facturas")
        assert resp.status_code == 404



# ── DuckDB aggregation logic ────────────────────────────────────────────


def _create_clientes_db(db_path: Path) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE silver_fact_ventas (
                business_date DATE,
                cod_clase VARCHAR,
                num_documento VARCHAR,
                nit_cliente VARCHAR,
                nombre_cliente VARCHAR,
                total_factura DOUBLE,
                estado_documento VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE silver_fact_ventas_detalle (
                business_date DATE,
                cod_clase VARCHAR,
                num_documento VARCHAR,
                cod_producto VARCHAR,
                nombre_detalle VARCHAR,
                cantidad DOUBLE,
                total_detalle DOUBLE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR,
                nombre_producto VARCHAR
            )
            """
        )
        con.executemany(
            "INSERT INTO silver_fact_ventas VALUES (?, 'FV', ?, ?, ?, ?, 'B')",
            [
                ("2024-05-01", "1", "1001", "ACME REPUESTOS", 100.0),
                ("2025-06-01", "2", "1001", "ACME REPUESTOS", 200.0),
                ("2026-07-01", "3", "1001", "ACME REPUESTOS", 300.0),
                ("2025-01-01", "4", "1002", "TALLER   XYZ", 100.0),
                ("2026-01-01", "5", "222222222", "CONSUMIDOR FINAL", 500.0),
                ("2026-02-01", "6", "", "CLIENTE VARIOS", 50.0),
            ],
        )
        # Canceled invoice: must be excluded from every customer view.
        con.execute(
            "INSERT INTO silver_fact_ventas VALUES ('2026-03-01','FV','7','1003','CANCELADO',999.0,'A')"
        )
        # Duplicate header (same business_date/cod_clase/num_documento): identity_count=2 → excluded.
        con.execute(
            "INSERT INTO silver_fact_ventas VALUES ('2026-04-01','FV','8','1004','DUPLICADO',100.0,'B')"
        )
        con.execute(
            "INSERT INTO silver_fact_ventas VALUES ('2026-04-01','FV','8','1004','DUPLICADO',100.0,'B')"
        )
        con.execute("INSERT INTO silver_dim_producto VALUES ('P1','ACEITE 20W50')")
        con.execute("INSERT INTO silver_dim_producto VALUES ('P2','FILTRO AIRE')")
        con.executemany(
            "INSERT INTO silver_fact_ventas_detalle VALUES (?, 'FV', ?, ?, ?, ?, ?)",
            [
                ("2024-05-01", "1", "P1", "ACEITE 20W50", 2.0, 100.0),
                ("2025-06-01", "2", "P1", "ACEITE 20W50", 3.0, 150.0),
                ("2025-06-01", "2", "P2", "FILTRO AIRE", 1.0, 50.0),
                ("2026-07-01", "3", "P1", "ACEITE 20W50", 5.0, 300.0),
            ],
        )
    finally:
        con.close()


@pytest.fixture()
def duckdb_repo(tmp_path: Path):
    db_path = tmp_path / "clientes.duckdb"
    _create_clientes_db(db_path)
    repo = DuckDBMetricsRepo(db_path=db_path, tenant="motoshop")
    yield repo
    close_all_shared_connections()


class TestClientesDirectoryDuckDB:
    def test_reconciles_and_excludes_unidentified(self, duckdb_repo) -> None:
        result = duckdb_repo.get_clientes(PERIOD_START, PERIOD_END, page=1, page_size=50)
        resumen = result["resumen"]
        # 600 (A) + 100 (B) identified; 500 sentinel + 50 empty unidentified.
        assert resumen["ventas_totales_validas"] == pytest.approx(1250.0)
        assert resumen["ventas_identificadas"] == pytest.approx(700.0)
        assert resumen["ventas_sin_identificar"] == pytest.approx(550.0)
        assert resumen["clientes_identificados"] == 2
        assert resumen["top10_ventas_suma"] == pytest.approx(700.0)
        assert resumen["top10_participacion"] == pytest.approx(700.0 / 1250.0)
        # Canceled and duplicate headers never appear in the ranking.
        ids = {item["customer_id"] for item in result["items"]}
        assert ids == {"1001", "1002"}

    def test_head_vs_lines_reconcile(self, duckdb_repo) -> None:
        perfil = duckdb_repo.get_cliente_perfil("1001", PERIOD_START, PERIOD_END)
        assert perfil["resumen"]["ventas_total"] == pytest.approx(600.0)
        assert perfil["resumen"]["facturas"] == 3
        assert perfil["resumen"]["unidades_vendidas"] == pytest.approx(11.0)
        products = {p["sku"]: p for p in perfil["productos_top"]}
        assert products["P1"]["unidades"] == pytest.approx(10.0)
        assert products["P1"]["ventas_valor"] == pytest.approx(550.0)
        assert products["P1"]["facturas"] == 3
        assert products["P2"]["unidades"] == pytest.approx(1.0)

    def test_name_whitespace_is_normalized(self, duckdb_repo) -> None:
        perfil = duckdb_repo.get_cliente_perfil("1002", PERIOD_START, PERIOD_END)
        assert perfil["cliente"]["nombre_canonico"] == "TALLER XYZ"

    def test_generic_and_unknown_return_none(self, duckdb_repo) -> None:
        assert duckdb_repo.get_cliente_perfil("222222222", PERIOD_START, PERIOD_END) is None
        assert duckdb_repo.get_cliente_perfil("9999999999", PERIOD_START, PERIOD_END) is None
        assert duckdb_repo.get_cliente_facturas("222222222", PERIOD_START, PERIOD_END) is None

    def test_search_matches_literally(self, duckdb_repo) -> None:
        found = duckdb_repo.get_clientes(PERIOD_START, PERIOD_END, q="acme")
        assert found["paginacion"]["total_filas"] == 1
        # SQL wildcards must be treated as literal characters, not patterns.
        none = duckdb_repo.get_clientes(PERIOD_START, PERIOD_END, q="%")
        assert none["paginacion"]["total_filas"] == 0

    def test_facturas_pagination_and_lines(self, duckdb_repo) -> None:
        page = duckdb_repo.get_cliente_facturas("1001", PERIOD_START, PERIOD_END, page=1, page_size=2)
        assert page["total"] == 3
        assert page["total_paginas"] == 2
        assert len(page["items"]) == 2
        # Newest first, with header↔detail line counts.
        assert page["items"][0]["fecha_negocio"] == "2026-07-01"
        assert page["items"][0]["lineas"] == 1
        assert page["items"][1]["lineas"] == 2
        assert page["total_lineas"] == 3
