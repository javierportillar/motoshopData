"""Tests para tenants.py — carga y consulta de configuración multi-tenant."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from motoshop_api.tenants import (
    Tenant,
    TenantBriefing,
    get_all_tenants,
    get_tenant_config,
    load_tenants,
)


def _write_tenants_yaml(path: Path, tenants_data: list[dict]) -> None:
    """Helper para escribir un archivo tenants.yaml de prueba."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"tenants": tenants_data}, f)


def test_load_tenants_returns_dict_keyed_by_id() -> None:
    """load_tenants debe retornar un dict con tenant.id como key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "tenants.yaml"
        _write_tenants_yaml(yaml_path, [
            {
                "id": "motoshop",
                "nombre": "MotoShop",
                "r2_object_key": "motoshop_gold.duckdb",
                "local_db_path": "/tmp/motoshop_gold.duckdb",
            },
        ])
        result = load_tenants(yaml_path)
        assert isinstance(result, dict)
        assert "motoshop" in result
        assert result["motoshop"].id == "motoshop"


def test_get_tenant_config_returns_tenant() -> None:
    """get_tenant_config debe retornar el Tenant solicitado."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "tenants.yaml"
        _write_tenants_yaml(yaml_path, [
            {
                "id": "masvital",
                "nombre": "MasVital",
                "r2_object_key": "masvital_gold.duckdb",
                "local_db_path": "/tmp/masvital_gold.duckdb",
            },
        ])
        load_tenants(yaml_path)
        tenant = get_tenant_config("masvital")
        assert tenant is not None
        assert tenant.nombre == "MasVital"


def test_get_tenant_config_unknown_returns_none() -> None:
    """get_tenant_config con tenant inexistente debe retornar None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "tenants.yaml"
        _write_tenants_yaml(yaml_path, [
            {
                "id": "motoshop",
                "nombre": "MotoShop",
                "r2_object_key": "motoshop_gold.duckdb",
                "local_db_path": "/tmp/motoshop_gold.duckdb",
            },
        ])
        load_tenants(yaml_path)
        assert get_tenant_config("nonexistent") is None


def test_get_all_tenants_returns_copy() -> None:
    """get_all_tenants debe retornar una copia del cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "tenants.yaml"
        _write_tenants_yaml(yaml_path, [
            {
                "id": "motoshop",
                "nombre": "MotoShop",
                "r2_object_key": "motoshop_gold.duckdb",
                "local_db_path": "/tmp/motoshop_gold.duckdb",
            },
        ])
        load_tenants(yaml_path)
        all_t = get_all_tenants()
        assert "motoshop" in all_t
        # Verify it's a copy (mutating returned dict doesn't affect cache)
        all_t["extra"] = "test"
        assert "extra" not in get_all_tenants()


def test_load_tenants_empty_yaml_returns_empty_dict() -> None:
    """load_tenants con YAML sin tenants debe retornar dict vacío."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "empty.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump({}, f)
        result = load_tenants(yaml_path)
        assert result == {}


def test_load_tenants_nonexistent_file_returns_empty_dict() -> None:
    """load_tenants con archivo inexistente debe retornar dict vacío."""
    result = load_tenants("/tmp/does_not_exist_12345.yaml")
    assert result == {}


def test_tenant_with_full_fields_is_parsed() -> None:
    """Tenant con todos los campos (incluyendo briefing) debe parsearse."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "tenants.yaml"
        _write_tenants_yaml(yaml_path, [
            {
                "id": "full",
                "nombre": "Full Tenant",
                "descripcion": "A tenant with all fields",
                "color_brand": "#FF0000",
                "logo": "/tenants/full/logo.png",
                "r2_object_key": "full_gold.duckdb",
                "local_db_path": "/tmp/full_gold.duckdb",
                "mysql_source": "full_db",
                "telegram_chat_id_gerente": "12345",
                "enabled_features": ["products", "stock"],
                "briefing": {"activo": True, "hora_cron_utc": "0 6 * * *"},
            },
        ])
        load_tenants(yaml_path)
        tenant = get_tenant_config("full")
        assert tenant is not None
        assert tenant.descripcion == "A tenant with all fields"
        assert tenant.color_brand == "#FF0000"
        assert tenant.mysql_source == "full_db"
        assert tenant.telegram_chat_id_gerente == "12345"
        assert tenant.enabled_features == ["products", "stock"]
        assert tenant.briefing.activo is True
        assert tenant.briefing.hora_cron_utc == "0 6 * * *"


def test_tenant_with_null_telegram_chat_id() -> None:
    """telegram_chat_id_gerente como null debe parsearse como None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "tenants.yaml"
        _write_tenants_yaml(yaml_path, [
            {
                "id": "notenant",
                "nombre": "No Telegram",
                "r2_object_key": "no_gold.duckdb",
                "local_db_path": "/tmp/no_gold.duckdb",
                "telegram_chat_id_gerente": None,
            },
        ])
        load_tenants(yaml_path)
        tenant = get_tenant_config("notenant")
        assert tenant is not None
        assert tenant.telegram_chat_id_gerente is None
