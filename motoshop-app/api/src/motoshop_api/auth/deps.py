"""Dependencias FastAPI para autenticación y autorización."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from motoshop_api.auth.jwt import decode_token
from motoshop_api.auth.users import User, get_user_by_username

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """Extrae y valida el usuario del JWT en el header Authorization."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o vencido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere access token",
        )

    username = payload.get("sub")
    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo",
        )

    return user


def require_role(*roles: str):
    """Dependency factory que verifica que el usuario tenga uno de los roles indicados."""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol '{user.role}' no tiene acceso a este recurso",
            )
        return user

    return _check


def require_module(*modules: str):
    """Authorize a user for at least one feature module.

    Administrators bypass module checks. Legacy YAML identities whose
    ``allowed_modules`` is ``None`` retain their historical unrestricted
    behavior; managed Supabase identities always carry an explicit list.
    """
    if not modules:
        raise ValueError("require_module necesita al menos un módulo")

    async def _check(user: User = Depends(get_current_user)) -> User:
        return authorize_modules(user, modules)

    return _check


def authorize_modules(user: User, modules: tuple[str, ...]) -> User:
    """Apply the shared module policy to an already-authenticated user.

    This function is intentionally separate from FastAPI's dependency factory so
    route-level policies can be driven by the central route/module matrix and unit
    tested without constructing a request.
    """
    if user.role == "admin":
        return user
    # Explicit compatibility rule: identities still sourced from users.yaml did
    # not historically have module scopes. Managed identities never use None.
    if user.source == "legacy" and user.allowed_modules is None:
        return user
    granted = set(user.allowed_modules or [])
    if not granted.intersection(modules):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario no tiene acceso al módulo requerido: " + " o ".join(modules),
        )
    return user


async def require_refresh_token_or_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> bool:
    """Acepta JWT con rol admin O un REFRESH_TOKEN compartido como Bearer.

    Para refresh automático desde scripts (capture_new_sales.py):
        Authorization: Bearer <REFRESH_TOKEN>

    Para acceso desde la UI/dashboard:
        Authorization: Bearer <jwt-admin-token>
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Intentar como REFRESH_TOKEN compartido (rápido, sin JWT)
    refresh_token = os.environ.get("REFRESH_TOKEN", "")
    if refresh_token and credentials.credentials == refresh_token:
        return True

    # 2. Fallback: JWT con rol admin
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o vencido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere access token",
        )

    username = payload.get("sub")
    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol '{user.role}' no tiene acceso a este recurso",
        )

    return True
