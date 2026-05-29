"""Router de métricas de negocio: GET /metrics/*

Cache server-side de 5 min (TTL en memoria). Los marts gold solo
cambian nocturno, no tiene sentido re-consultar Databricks en cada request.

Conecta a Databricks SQL Warehouse vía RealMetricsRepo cuando DATABRICKS_HTTP_PATH
está configurado; si no, cae a FakeMetricsRepo (datos mock).
"""

from __future__ import annotations

from time import time

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

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
)

router = APIRouter(tags=["metrics"])

limiter = Limiter(key_func=get_remote_address)

_CACHE_TTL = 300  # 5 minutos
_cache: dict[str, tuple[float, object]] = {}
_workspace_client = None  # lazy singleton


def _get_workspace():
    global _workspace_client
    if _workspace_client is None:
        from databricks.sdk import WorkspaceClient

        _workspace_client = WorkspaceClient(
            host=settings.databricks_host,
            token=settings.databricks_token,
        )
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
async def sales_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesSummary:
    """Resumen de ventas del mes actual vs anterior + top 10 SKUs."""
    return _cached_or_fetch("sales-summary", repo.get_sales_summary)


@router.get("/metrics/inventory-summary", response_model=InventorySummary)
@limiter.limit("30/minute")
async def inventory_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> InventorySummary:
    """Resumen de inventario: stock total, valor, distribución por bodega."""
    return _cached_or_fetch("inventory-summary", repo.get_inventory_summary)


@router.get("/metrics/abc-segmentation", response_model=AbcSegmentation)
@limiter.limit("30/minute")
async def abc_segmentation(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> AbcSegmentation:
    """Segmentación ABC de ingresos (80/15/5) del mes actual."""
    return _cached_or_fetch("abc-segmentation", repo.get_abc_segmentation)


@router.get("/metrics/dormidos", response_model=DormidosResponse)
@limiter.limit("30/minute")
async def dormidos(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> DormidosResponse:
    """Productos sin venta > 90 días."""
    return _cached_or_fetch("dormidos", repo.get_dormidos)


@router.get("/metrics/cohortes", response_model=CohortesResponse)
@limiter.limit("30/minute")
async def cohortes(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> CohortesResponse:
    """Cohortes de clientes por mes de primera compra."""
    return _cached_or_fetch("cohortes", repo.get_cohortes)
