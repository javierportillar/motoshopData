"""Módulo de autenticación (JWT + bcrypt)."""

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.jwt import create_access_token, create_refresh_token, decode_token
from motoshop_api.auth.hash import hash_password, verify_password
from motoshop_api.auth.router import router as auth_router
from motoshop_api.auth.schemas import LoginRequest, RefreshRequest, TokenPair, UserOut

__all__ = [
    "get_current_user",
    "require_role",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
    "auth_router",
    "LoginRequest",
    "RefreshRequest",
    "TokenPair",
    "UserOut",
]
