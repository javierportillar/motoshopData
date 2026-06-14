"""Carga de tenants desde tenants.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class TenantBriefing(BaseModel):
    activo: bool
    hora_cron_utc: str = ""


class Tenant(BaseModel):
    id: str
    nombre: str
    descripcion: str = ""
    color_brand: str = ""
    logo: str = ""
    r2_object_key: str
    local_db_path: str
    mysql_source: str = ""
    telegram_chat_id_gerente: Optional[str] = None
    enabled_features: list[str] = []
    briefing: TenantBriefing = TenantBriefing(activo=False)


_tenants_cache: dict[str, Tenant] = {}


def load_tenants(path: str | Path = "tenants.yaml") -> dict[str, Tenant]:
    global _tenants_cache
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _tenants_cache.clear()
    for t in data.get("tenants", []):
        tenant = Tenant(**t)
        _tenants_cache[tenant.id] = tenant
    return _tenants_cache


def get_tenant_config(tenant_id: str) -> Tenant | None:
    return _tenants_cache.get(tenant_id)


def get_all_tenants() -> dict[str, Tenant]:
    return _tenants_cache.copy()
