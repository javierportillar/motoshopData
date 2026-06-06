"""Router de administración: refresh de datos, health, etc.

POST /api/admin/data/refresh — recarga DuckDB desde R2 sin reiniciar uvicorn.
Requiere rol admin.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.metrics.router import _clear_metrics_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

limiter = Limiter(key_func=get_remote_address)


class RefreshResponse(BaseModel):
    status: str
    detail: str
    path: str
    size_bytes: int
    freshness_utc: str | None = None


def _get_duckdb_path() -> Path:
    db_path = settings.duckdb_path or (
        "/tmp/motoshop_gold.duckdb" if os.environ.get("ENV") == "prod"
        else "out/motoshop_gold.duckdb"
    )
    return Path(db_path)


@router.post("/data/refresh", response_model=RefreshResponse)
@limiter.limit("3/minute")
async def data_refresh(
    request: Request,
    user: User = Depends(require_role("admin")),
) -> RefreshResponse:
    """Recarga el archivo DuckDB desde R2 y limpia el cache de métricas.

    No requiere restart de uvicorn. La próxima request a cualquier endpoint
    de métricas usará los datos frescos.

    Solo accesible por usuarios con rol admin.
    """
    from motoshop_api.metrics.repo_duckdb import _bootstrap_duckdb_from_r2

    db_path = _get_duckdb_path()

    r2_endpoint = os.environ.get("R2_ENDPOINT")
    r2_key = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY")

    if not all([r2_endpoint, r2_key, r2_secret]):
        raise HTTPException(
            status_code=503,
            detail="R2 credentials not configured. Set R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.",
        )

    try:
        # Forzar re-download: borrar el archivo existente y bootstrap de vuelta
        if db_path.exists():
            db_path.unlink()
            logger.info("Deleted existing DuckDB at %s before refresh", db_path)

        _bootstrap_duckdb_from_r2(db_path)

        if not db_path.exists():
            raise HTTPException(
                status_code=503,
                detail="Refresh failed: DuckDB file not found after download. Check R2 connectivity.",
            )

        # Limpiar cache de métricas para que la próxima request use datos frescos
        _clear_metrics_cache()
        logger.info("Metrics cache cleared after DuckDB refresh")

        size_bytes = db_path.stat().st_size
        freshness = None
        try:
            from datetime import UTC, datetime
            mtime = db_path.stat().st_mtime
            freshness = datetime.fromtimestamp(mtime, UTC).isoformat()
        except Exception:
            pass

        return RefreshResponse(
            status="ok",
            detail="DuckDB refreshed from R2. Metrics cache cleared.",
            path=str(db_path),
            size_bytes=size_bytes,
            freshness_utc=freshness,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("DuckDB refresh failed")
        raise HTTPException(
            status_code=500,
            detail=f"Refresh failed: {exc}",
        )
