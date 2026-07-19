"""CRUD de usuarios (RBAC). Sólo admin. Respaldado en Supabase (app_users).

Los módulos definen visibilidad en el frontend y autorización en las superficies
principales del backend. Este router no expone hashes de contraseña.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from motoshop_api.auth.deps import require_role
from motoshop_api.auth.hash import hash_password
from motoshop_api.auth.users import User, get_user_by_username
from motoshop_api.users import supabase_repo
from motoshop_api.users.schemas import (
    ModuleItem,
    ModulesResponse,
    UserCreate,
    UserPublic,
    UsersListResponse,
    UserUpdate,
)
from motoshop_api.users.service import (
    MANAGEABLE_MODULES,
    VALID_ROLES,
    count_active_admins,
    merge_public_users,
    public_view,
    sync_users_from_supabase,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.get("/modules", response_model=ModulesResponse)
def get_modules(_admin: User = Depends(require_role("admin"))) -> ModulesResponse:
    """Catálogo de módulos asignables y roles válidos (para poblar el formulario)."""
    return ModulesResponse(
        modules=[ModuleItem(**m) for m in MANAGEABLE_MODULES],
        roles=list(VALID_ROLES),
    )


@router.get("", response_model=UsersListResponse)
def list_users(_admin: User = Depends(require_role("admin"))) -> UsersListResponse:
    """List managed users plus visible, read-only legacy YAML identities."""
    rows = supabase_repo.list_users()
    views = merge_public_users(rows)
    return UsersListResponse(
        items=[UserPublic(**view) for view in views],
        total=len(views),
    )


@router.post("", response_model=UserPublic, status_code=201)
def create_user(
    payload: UserCreate,
    admin: User = Depends(require_role("admin")),
) -> UserPublic:
    """Create a managed identity, optionally replacing an explicit legacy one."""
    if supabase_repo.get_user(payload.username) is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese nombre")
    cached_user = get_user_by_username(payload.username)
    migrating_legacy = cached_user is not None and cached_user.source == "legacy"
    if cached_user is not None and not (migrating_legacy and payload.migrate_legacy):
        detail: str | dict[str, str] = "Ya existe un usuario con ese nombre"
        if migrating_legacy:
            detail = {
                "code": "legacy_user_requires_explicit_migration",
                "message": (
                    "El usuario existe en users.yaml. Repetí la creación con "
                    "migrate_legacy=true y una contraseña nueva para gestionarlo en Supabase."
                ),
            }
        raise HTTPException(status_code=409, detail=detail)
    row = {
        "username": payload.username,
        "hashed_password": hash_password(payload.password),
        "email": payload.email.strip(),
        "role": payload.role,
        "tenants_allowed": payload.tenants_allowed,
        "allowed_modules": payload.allowed_modules,
        "active": True,
        "created_by": (
            f"{admin.username}:legacy-migration" if migrating_legacy else admin.username
        ),
    }
    created = supabase_repo.create_user(row)
    sync_users_from_supabase()
    return UserPublic(**public_view(created))


@router.patch("/{username}", response_model=UserPublic)
def update_user(
    username: str,
    payload: UserUpdate,
    admin: User = Depends(require_role("admin")),
) -> UserPublic:
    """Edita un usuario gestionado en Supabase (email, rol, tenants, módulos,
    activo, contraseña opcional). No permite dejar el sistema sin admin activo."""
    existing = supabase_repo.get_user(username)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Usuario no gestionable (no está en Supabase). "
                "Recrealo desde acá para editarlo."
            ),
        )

    patch: dict = {}
    if payload.email is not None:
        patch["email"] = payload.email.strip()
    if payload.role is not None:
        patch["role"] = payload.role
    if payload.tenants_allowed is not None:
        patch["tenants_allowed"] = payload.tenants_allowed
    if payload.allowed_modules is not None:
        patch["allowed_modules"] = payload.allowed_modules
    if payload.active is not None:
        patch["active"] = payload.active
    if payload.password:
        patch["hashed_password"] = hash_password(payload.password)

    # Guardas: no dejar el sistema sin admin activo al degradar o desactivar al último.
    _guard_last_admin(existing, patch, actor=admin.username, username=username)

    if not patch:
        return UserPublic(**public_view(existing))

    patch["updated_at"] = datetime.now(UTC).isoformat()
    updated = supabase_repo.update_user(username, patch)
    sync_users_from_supabase()
    return UserPublic(**public_view(updated))


@router.delete("/{username}", response_model=UserPublic)
def deactivate_user(
    username: str,
    admin: User = Depends(require_role("admin")),
) -> UserPublic:
    """Desactiva un usuario (soft delete, reversible). No podés desactivarte a vos
    mismo ni al último admin activo."""
    existing = supabase_repo.get_user(username)
    if existing is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en Supabase")
    if username == admin.username:
        raise HTTPException(status_code=400, detail="No podés desactivar tu propio usuario")
    _guard_last_admin(existing, {"active": False}, actor=admin.username, username=username)

    updated = supabase_repo.update_user(
        username, {"active": False, "updated_at": datetime.now(UTC).isoformat()}
    )
    sync_users_from_supabase()
    return UserPublic(**public_view(updated))


def _guard_last_admin(existing: dict, patch: dict, *, actor: str, username: str) -> None:
    """Bloquea cambios que dejarían al sistema sin ningún admin activo."""
    was_active_admin = existing.get("role") == "admin" and bool(existing.get("active", True))
    if not was_active_admin:
        return
    becomes_admin = patch.get("role", "admin") == "admin"
    stays_active = patch.get("active", True)
    still_active_admin = becomes_admin and stays_active
    if not still_active_admin and count_active_admins() <= 1:
        raise HTTPException(
            status_code=400,
            detail="No podés desactivar ni degradar al último admin activo",
        )
