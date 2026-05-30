"""Router de métricas de negocio: GET /metrics/*

Cache server-side de 5 min (TTL en memoria). Los marts gold solo
cambian nocturno, no tiene sentido re-consultar Databricks en cada request.

Conecta a Databricks SQL Warehouse vía RealMetricsRepo cuando DATABRICKS_HTTP_PATH
está configurado; si no, cae a FakeMetricsRepo (datos mock).
"""

from __future__ import annotations

from time import time

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from starlette.requests import Request as StarletteRequest

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.metrics.repo import (
    MetricsRepoProtocol,
    RealMetricsRepo,
)
from motoshop_api.metrics.schemas import (
    AbcSegmentation,
    CohortesResponse,
    DormidosResponse,
    InventorySummary,
    SalesSummary,
    SalesTrendResponse,
)

router = APIRouter(tags=["metrics"])


def _rate_limit_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)

_CACHE_TTL = 300  # 5 minutos
_cache: dict[str, tuple[float, object]] = {}
_workspace_client = None  # lazy singleton
_workspace_created_at: float = 0.0
_WORKSPACE_TTL = 3600  # Refresh workspace client hourly


def _get_workspace():
    global _workspace_client, _workspace_created_at
    now = time()
    if _workspace_client is None or (now - _workspace_created_at > _WORKSPACE_TTL):
        from databricks.sdk import WorkspaceClient

        _workspace_client = WorkspaceClient(
            host=settings.databricks_host,
            token=settings.databricks_token,
        )
        _workspace_created_at = now
    return _workspace_client


def _cached_or_fetch(key: str, fetch_fn, ttl: int = _CACHE_TTL):
    now = time()
    if key in _cache:
        ts, val = _cache[key]
        if now - ts < ttl:
            return val
    val = fetch_fn()
    _cache[key] = (now, val)
    return val


def _clear_metrics_cache():
    _cache.clear()


def get_repo() -> MetricsRepoProtocol:
    if settings.databricks_http_path:
        w = _get_workspace()
        # Extract warehouse ID from the http_path
        wh_id = settings.databricks_http_path.split("/")[-1]
        return RealMetricsRepo(w, wh_id)
    from motoshop_api.metrics.repo import FakeMetricsRepo

    return FakeMetricsRepo()


@router.get("/metrics/sales-summary", response_model=SalesSummary)
@limiter.limit("30/minute")
def sales_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesSummary:
    """Resumen de ventas del mes actual vs anterior + top 10 SKUs."""
    return _cached_or_fetch("sales-summary", repo.get_sales_summary)


@router.get("/metrics/inventory-summary", response_model=InventorySummary)
@limiter.limit("30/minute")
def inventory_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> InventorySummary:
    """Resumen de inventario: stock total, valor, distribución por bodega."""
    return _cached_or_fetch("inventory-summary", repo.get_inventory_summary)


@router.get("/metrics/abc-segmentation", response_model=AbcSegmentation)
@limiter.limit("30/minute")
def abc_segmentation(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> AbcSegmentation:
    """Segmentación ABC de ingresos (80/15/5) del mes actual."""
    return _cached_or_fetch("abc-segmentation", repo.get_abc_segmentation)


@router.get("/metrics/dormidos", response_model=DormidosResponse)
@limiter.limit("30/minute")
def dormidos(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> DormidosResponse:
    """Productos sin venta > 90 días."""
    return _cached_or_fetch("dormidos", repo.get_dormidos)


@router.get("/metrics/cohortes", response_model=CohortesResponse)
@limiter.limit("30/minute")
def cohortes(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> CohortesResponse:
    """Cohortes de clientes por mes de primera compra."""
    return _cached_or_fetch("cohortes", repo.get_cohortes)


@router.get("/metrics/sales-trend", response_model=SalesTrendResponse)
@limiter.limit("30/minute")
def sales_trend(
    request: Request,
    periods: int = 6,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesTrendResponse:
    """Tendencia de ventas mensual: total, facturas y ticket promedio."""
    if periods < 1 or periods > 24:
        raise HTTPException(status_code=422, detail="periods must be between 1 and 24")
    return _cached_or_fetch(f"sales-trend:{periods}", lambda: repo.get_sales_trend(periods))


@router.post("/metrics/cache/clear")
def clear_metrics_cache(
    _user: User = Depends(get_current_user),
) -> dict:
    """Invalidar cache de métricas manualmente."""
    _clear_metrics_cache()
    return {"status": "ok", "message": "Cache cleared"}
