"""Lógica de usuarios RBAC: catálogo de módulos, sync de cache y mapeo.

Modelo híbrido: los usuarios de users.yaml se cargan al arrancar y siguen
funcionando; los de Supabase se superponen encima (Supabase gana por username).
El hot-path (get_current_user) lee siempre la cache en memoria, así que tras
cada mutación se re-sincroniza la cache desde Supabase.
"""

from __future__ import annotations

import logging

from motoshop_api.auth.users import User, _users_cache, get_all_users
from motoshop_api.tenants import get_all_tenants
from motoshop_api.users import supabase_repo

logger = logging.getLogger(__name__)


# Catálogo de módulos asignables (fuente única). Las keys deben coincidir con las
# `feature` de los items de navegación del frontend y con enabled_features del tenant.
MANAGEABLE_MODULES: list[dict[str, str]] = [
    {"key": "ventas-summary", "label": "Movimientos (ventas/compras)"},
    {"key": "inventario", "label": "Inventario"},
    {"key": "decisiones", "label": "Decisiones"},
    {"key": "analisis", "label": "Análisis (gastos, balance)"},
    {"key": "forecast", "label": "Proyección"},
    {"key": "alerts", "label": "Alertas"},
    {"key": "acciones", "label": "Acciones"},
    {"key": "cohortes", "label": "Cohortes"},
    {"key": "vendedores", "label": "Vendedores"},
    {"key": "drift", "label": "Drift"},
    {"key": "pipeline-observability", "label": "Pipeline"},
    {"key": "data-catalog", "label": "Catálogo de datos"},
]

_VALID_MODULE_KEYS = {m["key"] for m in MANAGEABLE_MODULES}
VALID_ROLES = ("admin", "gerente", "vendedor")


def valid_modules(modules: list[str]) -> list[str]:
    """Filtra a keys de módulo conocidas, preservando el orden del catálogo."""
    requested = set(modules)
    return [m["key"] for m in MANAGEABLE_MODULES if m["key"] in requested]


def validate_modules(modules: list[str]) -> list[str]:
    """Validate module keys instead of silently widening/narrowing permissions."""
    unknown = sorted(set(modules) - _VALID_MODULE_KEYS)
    if unknown:
        raise ValueError(f"módulo(s) inválido(s): {', '.join(unknown)}")
    return valid_modules(modules)


def validate_tenants(tenant_ids: list[str]) -> list[str]:
    """Require at least one configured tenant for every managed user."""
    if not tenant_ids:
        raise ValueError("tenants_allowed debe incluir al menos un tenant")
    known = set(get_all_tenants())
    unknown = sorted(set(tenant_ids) - known)
    if unknown:
        raise ValueError(f"tenant(s) inválido(s): {', '.join(unknown)}")
    # Deduplicate without changing the order selected by the administrator.
    return list(dict.fromkeys(tenant_ids))


def row_to_user(row: dict) -> User:
    """Construye un User de dominio desde una fila de app_users."""
    return User(
        username=row["username"],
        hashed_password=row["hashed_password"],
        email=row.get("email") or "",
        role=row["role"],
        tenants_allowed=list(row.get("tenants_allowed") or []),
        allowed_modules=list(row.get("allowed_modules") or []),
        active=bool(row.get("active", True)),
        source="supabase",
    )


def public_view(row: dict) -> dict:
    """Vista de un usuario sin el hash de contraseña, para respuestas de la API."""
    return {
        "username": row["username"],
        "email": row.get("email") or "",
        "role": row["role"],
        "tenants_allowed": list(row.get("tenants_allowed") or []),
        "allowed_modules": list(row.get("allowed_modules") or []),
        "active": bool(row.get("active", True)),
        "source": "supabase",
        "manageable": True,
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def legacy_public_view(user: User) -> dict:
    """Represent a YAML user without pretending it can be edited in Supabase."""
    return {
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "tenants_allowed": list(user.tenants_allowed),
        "allowed_modules": list(user.allowed_modules or []),
        "active": user.active,
        "source": "legacy",
        "manageable": False,
        "created_by": None,
        "created_at": None,
        "updated_at": None,
    }


def merge_public_users(rows: list[dict]) -> list[dict]:
    """Merge Supabase-managed rows with non-overridden legacy YAML identities."""
    managed_usernames = {row["username"] for row in rows}
    views = [public_view(row) for row in rows]
    views.extend(
        legacy_public_view(user)
        for username, user in get_all_users().items()
        if username not in managed_usernames and user.source == "legacy"
    )
    return sorted(views, key=lambda item: item["username"].casefold())


def sync_users_from_supabase() -> int:
    """Superpone los usuarios de Supabase en la cache en memoria. Supabase gana.

    Degrada en silencio: si Supabase no está configurado o falla, no toca la
    cache (queda lo cargado de YAML). Se llama al arrancar y tras cada mutación.
    """
    if not supabase_repo.is_configured():
        return 0
    try:
        rows = supabase_repo.list_users()
    except Exception as exc:  # noqa: BLE001 — degradación deliberada
        logger.warning("sync de usuarios Supabase omitido: %s", exc)
        return 0
    for row in rows:
        _users_cache[row["username"]] = row_to_user(row)
    return len(rows)


def count_active_admins() -> int:
    """Cuántos admin activos hay en la cache (para no dejar el sistema sin admin)."""
    return sum(1 for u in _users_cache.values() if u.role == "admin" and u.active)
