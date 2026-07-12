"""Cliente HTTP para la tabla app_users en Supabase (PostgREST).

Espeja el patrón de gastos/supabase_client.py: httpx directo con la service key
(sólo server-side). Nunca se expone el hash de contraseña fuera del backend.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException

from motoshop_api.config import settings

logger = logging.getLogger(__name__)

_TABLE = "app_users"


def is_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _client() -> httpx.Client:
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Supabase no configurado. Setear SUPABASE_URL y SUPABASE_SERVICE_KEY.",
        )
    return httpx.Client(
        base_url=f"{settings.supabase_url}/rest/v1",
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        timeout=15.0,
    )


def _handle(r: httpx.Response, action: str) -> Any:
    if r.status_code >= 400:
        logger.error("Supabase users %s falló: %s %s", action, r.status_code, r.text)
        raise HTTPException(
            status_code=502 if r.status_code >= 500 else 400,
            detail=f"Error en Supabase (users {action}): {r.status_code}",
        )
    if r.status_code == 204:
        return None
    try:
        return r.json()
    except Exception:
        return None


def list_users() -> list[dict]:
    """Todos los usuarios (incluye el hash — sólo para uso server-side/cache)."""
    with _client() as c:
        r = c.get(f"/{_TABLE}", params={"order": "username.asc"})
        return _handle(r, "list") or []


def get_user(username: str) -> dict | None:
    with _client() as c:
        r = c.get(f"/{_TABLE}", params={"username": f"eq.{username}", "limit": "1"})
        data = _handle(r, "get") or []
        return data[0] if data else None


def create_user(row: dict) -> dict:
    with _client() as c:
        r = c.post(f"/{_TABLE}", json=row)
        data = _handle(r, "create")
        if not data:
            raise HTTPException(status_code=502, detail="Supabase no devolvió el usuario creado")
        return data[0] if isinstance(data, list) else data


def update_user(username: str, patch: dict) -> dict:
    if not patch:
        raise HTTPException(status_code=400, detail="Nada para actualizar")
    with _client() as c:
        r = c.patch(f"/{_TABLE}", json=patch, params={"username": f"eq.{username}"})
        data = _handle(r, "update")
        if not data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return data[0] if isinstance(data, list) else data
