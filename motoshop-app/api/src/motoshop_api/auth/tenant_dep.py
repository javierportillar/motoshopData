"""Dependencia FastAPI para resolver el tenant activo desde X-Tenant header + JWT."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.tenants import get_tenant_config

_DEFAULT_TENANT = "motoshop"
_bearer = HTTPBearer(auto_error=False)


def _validate_configured_tenant(tenant: str) -> str:
    config = get_tenant_config(tenant)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant}' no encontrado en la configuración",
        )
    return tenant


def _resolve_user_tenant(request: Request, user: User) -> str:
    requested_tenant = request.headers.get("X-Tenant")
    if requested_tenant:
        tenant = requested_tenant
    elif len(user.tenants_allowed) == 1:
        tenant = user.tenants_allowed[0]
    else:
        tenant = _DEFAULT_TENANT

    # Only legacy YAML identities retain the old empty-list = unrestricted
    # behavior. A managed user with no tenant is denied instead of becoming
    # accidentally global.
    legacy_unrestricted = user.source == "legacy" and not user.tenants_allowed
    if not legacy_unrestricted and tenant not in user.tenants_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usuario no tiene acceso al tenant '{tenant}'",
        )

    return _validate_configured_tenant(tenant)


async def get_tenant(
    request: Request,
    user: User = Depends(get_current_user),
) -> str:
    """Resolve the active tenant from X-Tenant header plus an authenticated user."""
    return _resolve_user_tenant(request, user)


async def get_tenant_for_admin_or_machine(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Resolve tenant for endpoints that accept either admin JWT or machine token.

    Machine-token calls must send X-Tenant explicitly so scheduled jobs cannot
    fall back to the historical MotoShop default by accident.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    refresh_token = os.environ.get("REFRESH_TOKEN", "")
    if refresh_token and credentials.credentials == refresh_token:
        tenant = request.headers.get("X-Tenant")
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant requerido para token de máquina",
            )
        return _validate_configured_tenant(tenant)

    user = await get_current_user(credentials)
    return _resolve_user_tenant(request, user)
