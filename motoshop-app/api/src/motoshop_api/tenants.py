"""Carga de tenants desde tenants.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TenantBriefing(BaseModel):
    activo: bool
    hora_cron_utc: str = ""


class TenantAgent(BaseModel):
    """Perfil operativo que se inyecta en el agente sin duplicar prompts."""

    display_name: str = "Asistente de negocio"
    business_description: str = ""
    locale: str = "es-CO"
    currency: str = "COP"
    enabled_tools: list[str] = Field(default_factory=list)
    knowledge_namespace: str = ""


class Tenant(BaseModel):
    id: str
    nombre: str
    descripcion: str = ""
    color_brand: str = ""
    logo: str = ""
    r2_object_key: str
    local_db_path: str
    mysql_source: str = ""
    telegram_chat_id_gerente: str | None = None
    enabled_features: list[str] = Field(default_factory=list)
    briefing: TenantBriefing = TenantBriefing(activo=False)
    agent: TenantAgent = Field(default_factory=TenantAgent)


_tenants_cache: dict[str, Tenant] = {}


def load_tenants(path: str | Path = "tenants.yaml") -> dict[str, Tenant]:
    global _tenants_cache
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        fallback = Path(__file__).resolve().parent.parent.parent / p
        if fallback.exists():
            p = fallback
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _tenants_cache.clear()
    for t in data.get("tenants", []):
        tenant = Tenant(**t)
        _tenants_cache[tenant.id] = tenant
    return _tenants_cache


def get_tenant_config(tenant_id: str) -> Tenant | None:
    if not _tenants_cache:
        load_tenants()
    return _tenants_cache.get(tenant_id)


def get_all_tenants() -> dict[str, Tenant]:
    if not _tenants_cache:
        load_tenants()
    return _tenants_cache.copy()
