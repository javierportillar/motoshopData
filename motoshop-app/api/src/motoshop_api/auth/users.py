"""Carga de usuarios desde users.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class User(BaseModel):
    username: str
    hashed_password: str
    email: str
    role: str
    tenants_allowed: list[str] = []


_users_cache: dict[str, User] = {}


def load_users(path: str | Path) -> dict[str, User]:
    """Carga usuarios desde un archivo YAML y los cachea."""
    global _users_cache
    path = Path(path)
    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _users_cache.clear()
    for u in data.get("users", []):
        user = User(**u)
        _users_cache[user.username] = user
    return _users_cache


def get_user_by_username(username: str) -> User | None:
    """Retorna un usuario por nombre de usuario."""
    return _users_cache.get(username)


def get_all_users() -> dict[str, User]:
    """Retorna todos los usuarios cacheados."""
    return _users_cache.copy()
