"""Router para descarga segura de reportes generados.

Aislamiento multi-tenant: el token es obligatorio y el tenant del reporte
debe estar dentro de los tenants permitidos del usuario.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from motoshop_api.auth.jwt import decode_token
from motoshop_api.auth.users import get_user_by_username
from motoshop_api.reports.storage import get_report_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


def _extract_token(request: Request, query_token: str | None) -> str | None:
    """Token desde: Bearer header, cookie motoshop_token o ?token= (browser download)."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip() or None
    cookie_token = request.cookies.get("motoshop_token")
    if cookie_token:
        return cookie_token
    return (query_token or "").strip() or None


@router.get("/download/{report_id}")
async def download_report(
    report_id: str,
    request: Request,
    token: str | None = Query(default=None),
):
    storage = get_report_storage()
    rec = storage.get_report(report_id)
    if rec is None or not rec.file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado o expirado")

    effective_token = _extract_token(request, token)
    if not effective_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida para descargar reportes",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(effective_token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o vencido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_username(payload.get("sub"))
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inválido o inactivo")

    # Aislamiento por tenant: mismo criterio que auth.tenant_dep — los usuarios
    # legacy sin tenants_allowed retienen el comportamiento histórico abierto.
    legacy_unrestricted = user.source == "legacy" and not user.tenants_allowed
    if not legacy_unrestricted and rec.tenant not in user.tenants_allowed:
        logger.warning(
            "report_download_denied user=%s report_tenant=%s", user.username, rec.tenant
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenés acceso a este reporte",
        )

    safe_ascii_name = quote(rec.filename)
    headers = {
        "Content-Disposition": f'attachment; filename="{rec.filename}"; filename*=UTF-8\'\'{safe_ascii_name}',
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    return FileResponse(
        path=rec.file_path,
        media_type=rec.mime_type,
        filename=rec.filename,
        headers=headers,
    )
