"""Router para descarga de reportes generados."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from motoshop_api.auth.jwt import decode_token
from motoshop_api.reports.storage import get_report_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


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

    # Autenticación opcional / permisiva para descarga directa desde navegador:
    # 1. Bearer header
    # 2. Cookie motoshop_token
    # 3. Query param ?token=
    auth_header = request.headers.get("authorization", "")
    bearer_token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else None
    cookie_token = request.cookies.get("motoshop_token")
    effective_token = bearer_token or cookie_token or token

    if effective_token:
        try:
            payload = decode_token(effective_token)
            if payload.get("type") != "access":
                raise HTTPException(status_code=401, detail="Token no válido para descarga")
        except Exception:
            logger.warning("Token inválido en descarga de reporte %s", report_id)

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
