"""Schemas Pydantic para la gestión de usuarios (RBAC)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from motoshop_api.users.service import VALID_ROLES, validate_modules, validate_tenants

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,64}$")


class UserCreate(BaseModel):
    username: str = Field(..., description="3-64 chars: letras, números, . _ -")
    password: str = Field(..., min_length=4, max_length=128)
    email: str = Field(default="", max_length=255)
    role: str
    tenants_allowed: list[str] = Field(..., min_length=1)
    allowed_modules: list[str] = Field(default_factory=list)
    migrate_legacy: bool = Field(
        default=False,
        description="Explicitly replace a users.yaml identity with a managed Supabase row",
    )

    @field_validator("username")
    @classmethod
    def validar_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError("username inválido (3-64 chars: letras, números, . _ -)")
        return v

    @field_validator("role")
    @classmethod
    def validar_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role inválido. Válidos: {', '.join(VALID_ROLES)}")
        return v

    @field_validator("tenants_allowed")
    @classmethod
    def validar_tenants(cls, v: list[str]) -> list[str]:
        return validate_tenants(v)

    @field_validator("allowed_modules")
    @classmethod
    def validar_modulos(cls, v: list[str]) -> list[str]:
        return validate_modules(v)


class UserUpdate(BaseModel):
    """Edición parcial. Sólo los campos presentes se modifican."""

    password: str | None = Field(default=None, min_length=4, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    role: str | None = None
    tenants_allowed: list[str] | None = None
    allowed_modules: list[str] | None = None
    active: bool | None = None

    @field_validator("role")
    @classmethod
    def validar_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"role inválido. Válidos: {', '.join(VALID_ROLES)}")
        return v

    @field_validator("tenants_allowed")
    @classmethod
    def validar_tenants(cls, v: list[str] | None) -> list[str] | None:
        return validate_tenants(v) if v is not None else None

    @field_validator("allowed_modules")
    @classmethod
    def validar_modulos(cls, v: list[str] | None) -> list[str] | None:
        return validate_modules(v) if v is not None else None


class UserPublic(BaseModel):
    username: str
    email: str
    role: str
    tenants_allowed: list[str]
    allowed_modules: list[str]
    active: bool
    source: str
    manageable: bool
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UsersListResponse(BaseModel):
    items: list[UserPublic]
    total: int


class ModuleItem(BaseModel):
    key: str
    label: str


class ModulesResponse(BaseModel):
    modules: list[ModuleItem]
    roles: list[str]
