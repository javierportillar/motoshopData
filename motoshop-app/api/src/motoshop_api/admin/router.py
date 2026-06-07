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


# ── LLM cost dashboard ─────────────────────────────────────────────────

class LLMCostItem(BaseModel):
    model: str
    calls: int
    tokens_input: int
    tokens_output: int
    success_rate: float
    cost_usd: float


class LLMCostResponse(BaseModel):
    month: str
    total_calls: int
    total_tokens_input: int
    total_tokens_output: int
    total_cost_usd: float
    per_model: list[LLMCostItem]


@router.get("/llm-cost", response_model=LLMCostResponse)
@limiter.limit("10/minute")
async def llm_cost(
    request: Request,
    user: User = Depends(require_role("admin")),
) -> LLMCostResponse:
    """Dashboard de costos LLM del mes actual. Admin-only.

    Lee la tabla app_llm_usage en MySQL. Si MySQL no está disponible,
    devuelve ceros (el cost logging es best-effort, no bloquea la API).
    """
    from datetime import datetime

    month_str = datetime.now().strftime("%Y-%m")

    try:
        import pymysql
        conn = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            connect_timeout=5,
        )
        cur = conn.cursor()

        # Totales del mes
        cur.execute("""
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(tokens_input), 0) AS total_tokens_input,
                COALESCE(SUM(tokens_output), 0) AS total_tokens_output,
                COALESCE(SUM(cost_usd), 0) AS total_cost_usd
            FROM app_llm_usage
            WHERE DATE_FORMAT(timestamp, '%Y-%m') = %s
        """, [month_str])
        totals = cur.fetchone()

        # Por modelo
        cur.execute("""
            SELECT
                model,
                COUNT(*) AS calls,
                COALESCE(SUM(tokens_input), 0) AS tokens_input,
                COALESCE(SUM(tokens_output), 0) AS tokens_output,
                COALESCE(SUM(cost_usd), 0) AS cost_usd,
                ROUND(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS success_rate
            FROM app_llm_usage
            WHERE DATE_FORMAT(timestamp, '%Y-%m') = %s
            GROUP BY model
            ORDER BY calls DESC
        """, [month_str])
        rows = cur.fetchall()

        conn.close()

        return LLMCostResponse(
            month=month_str,
            total_calls=int(totals[0]) if totals else 0,
            total_tokens_input=int(totals[1]) if totals else 0,
            total_tokens_output=int(totals[2]) if totals else 0,
            total_cost_usd=float(totals[3]) if totals else 0.0,
            per_model=[
                LLMCostItem(
                    model=r[0],
                    calls=int(r[1]),
                    tokens_input=int(r[2]),
                    tokens_output=int(r[3]),
                    cost_usd=float(r[4]),
                    success_rate=float(r[5]),
                )
                for r in rows
            ],
        )

    except Exception as exc:
        logger.warning("llm_cost: MySQL unavailable, trying DuckDB fallback: %s", exc)
        # Fallback: leer de DuckDB cost tracking (archivo separado)
        try:
            import duckdb
            cost_path = (settings.duckdb_path or "/tmp/motoshop_gold.duckdb").replace(".duckdb", "_cost.duckdb")
            con = duckdb.connect(cost_path, read_only=True)

            exists = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'llm_usage'"
            ).fetchone()[0]

            if not exists:
                con.close()
                raise Exception("llm_usage table not found")

            totals = con.execute(f"""
                SELECT COUNT(*), COALESCE(SUM(tokens_input), 0), COALESCE(SUM(tokens_output), 0)
                FROM llm_usage
                WHERE STRFTIME(timestamp, '%Y-%m') = ?
            """, [month_str]).fetchone()

            rows = con.execute(f"""
                SELECT model, COUNT(*) AS calls,
                       COALESCE(SUM(tokens_input), 0), COALESCE(SUM(tokens_output), 0),
                       ROUND(SUM(CASE WHEN success THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1)
                FROM llm_usage
                WHERE STRFTIME(timestamp, '%Y-%m') = ?
                GROUP BY model ORDER BY calls DESC
            """, [month_str]).fetchall()

            con.close()

            return LLMCostResponse(
                month=month_str,
                total_calls=int(totals[0]) if totals else 0,
                total_tokens_input=int(totals[1]) if totals else 0,
                total_tokens_output=int(totals[2]) if totals else 0,
                total_cost_usd=0.0,
                per_model=[
                    LLMCostItem(
                        model=r[0], calls=int(r[1]), tokens_input=int(r[2]),
                        tokens_output=int(r[3]), cost_usd=0.0, success_rate=float(r[4]),
                    )
                    for r in rows
                ],
            )
        except Exception as exc2:
            logger.warning("llm_cost: DuckDB also unavailable: %s", exc2)
            return LLMCostResponse(
                month=month_str, total_calls=0, total_tokens_input=0,
                total_tokens_output=0, total_cost_usd=0.0, per_model=[],
            )
