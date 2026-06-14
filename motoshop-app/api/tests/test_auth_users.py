"""Tests para el modelo User con soporte multi-tenant."""

from __future__ import annotations

from pathlib import Path

import yaml

from motoshop_api.auth.users import User, get_user_by_username, load_users


def test_user_model_accepts_tenants_allowed() -> None:
    """User debe aceptar tenants_allowed como lista de strings."""
    user = User(
        username="test",
        hashed_password="hash",
        email="test@test.com",
        role="admin",
        tenants_allowed=["motoshop", "masvital"],
    )
    assert user.tenants_allowed == ["motoshop", "masvital"]


def test_user_without_tenants_allowed_defaults_to_empty_list() -> None:
    """User sin tenants_allowed debe tener lista vacía (backward compat)."""
    user = User(
        username="legacy",
        hashed_password="hash",
        email="legacy@test.com",
        role="vendedor",
    )
    assert user.tenants_allowed == []


def test_load_users_parses_tenants_allowed() -> None:
    """load_users debe parsear tenants_allowed del YAML."""
    yaml_content = {
        "users": [
            {
                "username": "multi_admin",
                "hashed_password": "hash1",
                "email": "multi@test.com",
                "role": "admin",
                "tenants_allowed": ["motoshop", "masvital"],
            },
        ],
    }
    path = Path("/tmp/_test_users_multi.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_content, f)
    try:
        users = load_users(path)
        user = users.get("multi_admin")
        assert user is not None
        assert user.tenants_allowed == ["motoshop", "masvital"]
    finally:
        path.unlink(missing_ok=True)


def test_load_users_without_tenants_allowed_gets_empty_list() -> None:
    """Usuario en YAML sin tenants_allowed debe cargar con lista vacía."""
    yaml_content = {
        "users": [
            {
                "username": "old_user",
                "hashed_password": "hash2",
                "email": "old@test.com",
                "role": "vendedor",
            },
        ],
    }
    path = Path("/tmp/_test_users_no_tenant.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_content, f)
    try:
        users = load_users(path)
        user = users.get("old_user")
        assert user is not None
        assert user.tenants_allowed == []
    finally:
        path.unlink(missing_ok=True)


def test_get_user_by_username_returns_user_with_tenants_allowed() -> None:
    """get_user_by_username debe retornar User con tenants_allowed."""
    yaml_content = {
        "users": [
            {
                "username": "tenant_user",
                "hashed_password": "hash3",
                "email": "tu@test.com",
                "role": "gerente",
                "tenants_allowed": ["motoshop"],
            },
        ],
    }
    path = Path("/tmp/_test_users_get.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_content, f)
    try:
        load_users(path)
        user = get_user_by_username("tenant_user")
        assert user is not None
        assert user.tenants_allowed == ["motoshop"]
    finally:
        path.unlink(missing_ok=True)
