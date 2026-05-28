"""Router de autenticación: POST /auth/login, POST /auth/refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.hash import verify_password
from motoshop_api.auth.jwt import create_access_token, create_refresh_token, decode_token
from motoshop_api.auth.schemas import LoginRequest, TokenPair
from motoshop_api.auth.users import get_user_by_username
from motoshop_api.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=TokenPair)
@limiter.limit("100/minute")
async def login(request: Request, body: LoginRequest) -> TokenPair:
    """Login con username/password. Retorna access + refresh tokens."""
    user = get_user_by_username(body.username)
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    access = create_access_token(subject=user.username, role=user.role)
    refresh = create_refresh_token(subject=user.username)

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_ttl_minutes * 60,
    )


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh(request: Request, token: str) -> TokenPair:
    """Renueva tokens usando un refresh token válido."""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o vencido",
        )

    username = payload.get("sub")
    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    access = create_access_token(subject=user.username, role=user.role)
    refresh_new = create_refresh_token(subject=user.username)

    return TokenPair(
        access_token=access,
        refresh_token=refresh_new,
        expires_in=settings.jwt_access_ttl_minutes * 60,
    )
