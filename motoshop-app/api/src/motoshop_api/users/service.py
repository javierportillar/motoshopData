"""Lógica de usuarios RBAC: catálogo de módulos, sync de cache y mapeo.

Modelo híbrido: los usuarios de users.yaml se cargan al arrancar y siguen
funcionando; los de Supabase se superponen encima (Supabase gana por username).
El hot-path (get_current_user) lee siempre la cache en memoria, así que tras
cada mutación se re-sincroniza la cache desde Supabase.
"""

from __future__ import annotations

import logging

from motoshop_api.auth.users import User, _users_cache
from motoshop_api.users import supabase_repo

logger = logging.getLogger(__name__)


# Catálogo de módulos asignables (fuente única). Las keys deben coincidir con las
# `feature` de los items de navegación del frontend y con enabled_features del tenant.
MANAGEABLE_MODULES: list[dict[str, str]] = [
    {"key": "ventas-summary", "label": "Movimientos (ventas/compras)"},
    {"key": "inventario", "label": "Inventario"},
    {"key": "decisiones", "label": "Decisiones"},
    {"key": "analisis", "label": "Análisis (gastos, balance)"},
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
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


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
