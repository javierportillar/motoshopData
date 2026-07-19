"""Cliente HTTP para la tabla app_users en Supabase (PostgREST).

Espeja el patrón de gastos/supabase_client.py: httpx directo con la service key
(sólo server-side). Nunca se expone el hash de contraseña fuera del backend.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

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
        upstream = _safe_upstream_error(r)
        code = upstream.get("code") or "unknown"
        correlation_id = str(uuid4())
        logger.error(
            (
                "Supabase users %s failed: correlation_id=%s status=%s "
                "code=%s message=%r details=%r hint=%r"
            ),
            action,
            correlation_id,
            r.status_code,
            code,
            upstream.get("message"),
            upstream.get("details"),
            upstream.get("hint"),
        )
        unavailable = (
            r.status_code in {401, 403, 404, 429}
            or r.status_code >= 500
            or str(code).startswith(("PGRST0", "PGRST2"))
        )
        if unavailable:
            api_status = 503
            public_code = "users_upstream_unavailable"
            message = "Servicio de usuarios no disponible"
        elif r.status_code == 409:
            api_status = 409
            public_code = "users_upstream_conflict"
            message = "La operación de usuarios entra en conflicto con datos existentes"
        else:
            api_status = 400
            public_code = "users_upstream_rejected"
            message = "El servicio de usuarios rechazó la operación"
        raise HTTPException(
            status_code=api_status,
            detail={
                "code": public_code,
                "upstream_status": r.status_code,
                "message": message,
                "correlation_id": correlation_id,
            },
        )
    if r.status_code == 204:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _safe_upstream_error(r: httpx.Response) -> dict[str, str | None]:
    """Return only documented PostgREST error fields, with bounded values."""
    allowed = ("code", "message", "details", "hint")
    try:
        payload = r.json()
    except ValueError:
        payload = {"message": r.text}
    if not isinstance(payload, dict):
        payload = {"message": "Respuesta de error no estructurada"}
    result: dict[str, str | None] = {}
    for key in allowed:
        value = payload.get(key)
        if value is None:
            result[key] = None
        else:
            result[key] = str(value)[:500]
    return result


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    action: str,
    **kwargs: Any,
) -> httpx.Response:
    """Call PostgREST and turn connectivity failures into a diagnostic 503."""
    try:
        return client.request(method, path, **kwargs)
    except httpx.RequestError as exc:
        correlation_id = str(uuid4())
        logger.error(
            "Supabase users %s connection failed: correlation_id=%s cause=%s",
            action,
            correlation_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "users_upstream_unavailable",
                "upstream_status": None,
                "message": "Servicio de usuarios no disponible",
                "correlation_id": correlation_id,
            },
        ) from exc


def list_users() -> list[dict]:
    """Todos los usuarios (incluye el hash — sólo para uso server-side/cache)."""
    with _client() as c:
        r = _request(c, "GET", f"/{_TABLE}", "list", params={"order": "username.asc"})
        return _handle(r, "list") or []


def get_user(username: str) -> dict | None:
    with _client() as c:
        r = _request(
            c,
            "GET",
            f"/{_TABLE}",
            "get",
            params={"username": f"eq.{username}", "limit": "1"},
        )
        data = _handle(r, "get") or []
        return data[0] if data else None


def create_user(row: dict) -> dict:
    with _client() as c:
        r = _request(c, "POST", f"/{_TABLE}", "create", json=row)
        data = _handle(r, "create")
        if not data:
            raise HTTPException(status_code=502, detail="Supabase no devolvió el usuario creado")
        return data[0] if isinstance(data, list) else data


def update_user(username: str, patch: dict) -> dict:
    if not patch:
        raise HTTPException(status_code=400, detail="Nada para actualizar")
    with _client() as c:
        r = _request(
            c,
            "PATCH",
            f"/{_TABLE}",
            "update",
            json=patch,
            params={"username": f"eq.{username}"},
        )
        data = _handle(r, "update")
        if not data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return data[0] if isinstance(data, list) else data
