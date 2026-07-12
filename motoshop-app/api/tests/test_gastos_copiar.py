"""Tests para copiar gastos de un mes a otro (Feature: gastos repetitivos)."""

from __future__ import annotations

import pytest

from motoshop_api.gastos import supabase_client
from motoshop_api.gastos import router as gastos_router
from motoshop_api.tenants import Tenant, _tenants_cache


@pytest.fixture()
def tenant_motoshop():
    """Registra el tenant por defecto para que get_tenant resuelva en tests."""
    _tenants_cache["motoshop"] = Tenant(
        id="motoshop",
        nombre="MotoShop",
        r2_object_key="motoshop.duckdb",
        local_db_path="/tmp/motoshop.duckdb",
    )
    yield
    _tenants_cache.pop("motoshop", None)


def test_copy_gastos_skips_duplicates_in_destination(monkeypatch) -> None:
    origen = [
        {"id": 1, "mes": "2026-06", "categoria": "arriendo", "monto": 300000.0, "descripcion": "local"},
        {"id": 2, "mes": "2026-06", "categoria": "nomina", "monto": 500000.0, "descripcion": None},
    ]
    # El destino ya tiene el arriendo → sólo debe copiarse la nómina.
    destino = [
        {"id": 9, "mes": "2026-07", "categoria": "arriendo", "monto": 300000.0, "descripcion": "local"},
    ]
    created: list[dict] = []

    def fake_list(tenant, mes=None, **_kw):
        return origen if mes == "2026-06" else destino

    def fake_create(tenant, payload, created_by):
        row = {"id": 100 + len(created), "tenant": tenant, **payload, "created_by": created_by}
        created.append(row)
        return row

    monkeypatch.setattr(supabase_client, "list_gastos", fake_list)
    monkeypatch.setattr(supabase_client, "create_gasto", fake_create)

    result = supabase_client.copy_gastos(
        tenant="motoshop", mes_origen="2026-06", mes_destino="2026-07", created_by="admin"
    )
    assert len(result) == 1
    assert result[0]["categoria"] == "nomina"
    assert result[0]["mes"] == "2026-07"


def test_copy_gastos_filters_by_ids(monkeypatch) -> None:
    origen = [
        {"id": 1, "mes": "2026-06", "categoria": "arriendo", "monto": 300000.0, "descripcion": None},
        {"id": 2, "mes": "2026-06", "categoria": "nomina", "monto": 500000.0, "descripcion": None},
    ]

    def fake_list(tenant, mes=None, **_kw):
        return origen if mes == "2026-06" else []

    monkeypatch.setattr(supabase_client, "list_gastos", fake_list)
    monkeypatch.setattr(
        supabase_client, "create_gasto", lambda tenant, payload, created_by: {"id": 1, **payload}
    )

    result = supabase_client.copy_gastos(
        tenant="motoshop", mes_origen="2026-06", mes_destino="2026-07", created_by="admin", ids=[2]
    )
    assert len(result) == 1
    assert result[0]["categoria"] == "nomina"


def test_copiar_endpoint_requires_privileged_role(client, vendedor_token, tenant_motoshop) -> None:
    resp = client.post(
        "/api/gastos/copiar",
        json={"mes_origen": "2026-06", "mes_destino": "2026-07"},
        headers={"Authorization": f"Bearer {vendedor_token}", "X-Tenant": "motoshop"},
    )
    assert resp.status_code == 403


def test_copiar_endpoint_rejects_same_month(client, admin_token, tenant_motoshop) -> None:
    resp = client.post(
        "/api/gastos/copiar",
        json={"mes_origen": "2026-07", "mes_destino": "2026-07"},
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
    )
    assert resp.status_code == 400


def test_copiar_endpoint_happy_path(client, admin_token, tenant_motoshop, monkeypatch) -> None:
    monkeypatch.setattr(
        gastos_router,
        "copy_gastos",
        lambda **_kw: [
            {
                "id": 1,
                "tenant": "motoshop",
                "mes": "2026-07",
                "categoria": "arriendo",
                "monto": 300000.0,
                "descripcion": "local",
                "created_at": "2026-07-01T00:00:00Z",
                "updated_at": "2026-07-01T00:00:00Z",
                "created_by": "admin",
            }
        ],
    )
    resp = client.post(
        "/api/gastos/copiar",
        json={"mes_origen": "2026-06", "mes_destino": "2026-07", "ids": [5]},
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant": "motoshop"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["mes"] == "2026-07"
