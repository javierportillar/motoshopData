"""Router de administración: refresh de datos, health, etc.

POST /api/admin/data/refresh — recarga DuckDB desde R2 sin reiniciar uvicorn.
Requiere rol admin.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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


@router.post("/pipeline/refresh", response_model=RefreshResponse)
@limiter.limit("3/minute")
async def pipeline_refresh(
    request: Request,
    user: User = Depends(require_role("admin")),
) -> RefreshResponse:
    """Recarga pipeline_runs.duckdb desde R2 sin reiniciar uvicorn.

    Solo accesible por usuarios con rol admin.
    """
    from motoshop_api.pipeline_runs.repo import _bootstrap_pipeline_db_from_r2

    db_path = Path(os.environ.get(
        "PIPELINE_RUNS_DB_PATH",
        "/tmp/pipeline_runs.duckdb" if os.environ.get("ENV") == "prod" else "out/pipeline_runs.duckdb",
    ))

    r2_endpoint = os.environ.get("R2_ENDPOINT")
    r2_key = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY")

    if not all([r2_endpoint, r2_key, r2_secret]):
        raise HTTPException(
            status_code=503,
            detail="R2 credentials not configured. Set R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.",
        )

    try:
        if db_path.exists():
            db_path.unlink()
            logger.info("Deleted existing pipeline_runs.duckdb at %s before refresh", db_path)

        _bootstrap_pipeline_db_from_r2(db_path)

        if not db_path.exists():
            raise HTTPException(
                status_code=503,
                detail="Refresh failed: pipeline_runs.duckdb not found after download. Check R2 connectivity.",
            )

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
            detail="Pipeline runs DuckDB refreshed from R2.",
            path=str(db_path),
            size_bytes=size_bytes,
            freshness_utc=freshness,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Pipeline refresh failed")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline refresh failed: {exc}",
        )


# ── Data status (V1.8) ──────────────────────────────────────────────────


class DataStatusResponse(BaseModel):
    sales_max_date: str | None = None
    sales_days_lag: int | None = None
    inventory_snapshot_date: str | None = None
    invalid_future_sales_rows: int = 0
    latest_pipeline_run_status: str | None = None
    duckdb_freshness_utc: str | None = None
    duckdb_backend: str = "duckdb"


@router.get("/data/status", response_model=DataStatusResponse)
async def data_status(
    request: Request,
    user: User = Depends(require_role("admin", "gerente")),
) -> DataStatusResponse:
    """Estado real de los datos: fecha máxima, lag, filas inválidas, frescura."""
    import duckdb
    from datetime import date, datetime, timezone

    db_path = _get_duckdb_path()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # Max sales date
        max_date = con.execute(
            "SELECT MAX(business_date) FROM motoshop_gold_mart_ventas_diarias_sku"
        ).fetchone()[0]

        max_date_str = str(max_date) if max_date else None
        days_lag = (date.today() - max_date).days if max_date else None

        # Inventory snapshot
        inv_snapshot = con.execute(
            "SELECT MAX(snapshot_date) FROM motoshop_gold_mart_inventario_actual"
        ).fetchone()[0]
        inv_snapshot_str = str(inv_snapshot) if inv_snapshot else None

        # Invalid future sales (> tomorrow)
        invalid = con.execute(
            "SELECT COUNT(*) FROM motoshop_silver_fact_ventas WHERE business_date > CURRENT_DATE + 1"
        ).fetchone()[0]

        # DuckDB freshness
        mtime = db_path.stat().st_mtime
        freshness_utc = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        return DataStatusResponse(
            sales_max_date=max_date_str,
            sales_days_lag=days_lag,
            inventory_snapshot_date=inv_snapshot_str,
            invalid_future_sales_rows=int(invalid or 0),
            duckdb_freshness_utc=freshness_utc,
        )
    finally:
        con.close()


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
        logger.warning("llm_cost: MySQL unavailable, trying JSONL fallback: %s", exc)
        # Fallback: leer del archivo JSONL local
        try:
            import json as _json
            log_path = "/tmp/llm_usage.jsonl"
            calls = []
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        calls.append(_json.loads(line))
            
            # Filtrar por mes actual
            month_prefix = month_str  # "2026-06"
            month_calls = [c for c in calls if c.get("timestamp", "").startswith(month_prefix)]
            
            per_model = {}
            for c in month_calls:
                m = c.get("model", "unknown")
                if m not in per_model:
                    per_model[m] = {"calls": 0, "tokens_input": 0, "tokens_output": 0, "success": 0}
                per_model[m]["calls"] += 1
                per_model[m]["tokens_input"] += c.get("tokens_input", 0)
                per_model[m]["tokens_output"] += c.get("tokens_output", 0)
                if c.get("success"):
                    per_model[m]["success"] += 1

            return LLMCostResponse(
                month=month_str,
                total_calls=len(month_calls),
                total_tokens_input=sum(c.get("tokens_input", 0) for c in month_calls),
                total_tokens_output=sum(c.get("tokens_output", 0) for c in month_calls),
                total_cost_usd=0.0,
                per_model=[
                    LLMCostItem(
                        model=m, calls=v["calls"], tokens_input=v["tokens_input"],
                        tokens_output=v["tokens_output"], cost_usd=0.0,
                        success_rate=round(v["success"] / v["calls"] * 100, 1) if v["calls"] else 100.0,
                    )
                    for m, v in sorted(per_model.items(), key=lambda x: -x[1]["calls"])
                ],
            )
        except Exception as exc2:
            logger.warning("llm_cost: JSONL also unavailable: %s", exc2)
            return LLMCostResponse(
                month=month_str, total_calls=0, total_tokens_input=0,
                total_tokens_output=0, total_cost_usd=0.0, per_model=[],
            )
