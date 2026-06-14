"""Schemas de autenticación."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    username: str
    email: str
    role: str


class RefreshRequest(BaseModel):
    token: str


class UserMeResponse(BaseModel):
    username: str
    email: str
    role: str
    tenants_allowed: list[str] = []
    current_tenant: str = "motoshop"
    enabled_features: list[str] = []
