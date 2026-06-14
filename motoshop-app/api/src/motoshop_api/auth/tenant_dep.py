"""Dependencia FastAPI para resolver el tenant activo desde X-Tenant header + JWT."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.tenants import get_tenant_config


_DEFAULT_TENANT = "motoshop"


async def get_tenant(
    request: Request,
    user: User = Depends(get_current_user),
) -> str:
    """Resuelve el tenant activo:
    1. Lee header X-Tenant (default: 'motoshop')
    2. Valida que el usuario tenga ese tenant en tenants_allowed
    3. Retorna el tenant ID
    """
    tenant = request.headers.get("X-Tenant", _DEFAULT_TENANT)

    if user.tenants_allowed and tenant not in user.tenants_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usuario no tiene acceso al tenant '{tenant}'",
        )

    # Verify tenant exists in config
    config = get_tenant_config(tenant)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant}' no encontrado en la configuración",
        )

    return tenant
