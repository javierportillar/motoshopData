"""Router de métricas de negocio: GET /metrics/*

Cache server-side de 5 min (TTL en memoria). Los marts gold solo
cambian nocturno, no tiene sentido re-consultar Databricks en cada request.

Conecta a Databricks SQL Warehouse vía RealMetricsRepo cuando DATABRICKS_HTTP_PATH
está configurado; si no, cae a FakeMetricsRepo (datos mock).
"""

from __future__ import annotations

from time import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from starlette.requests import Request as StarletteRequest

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.metrics.repo import (
    MetricsRepoProtocol,
    RealMetricsRepo,
)
from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo
from motoshop_api.metrics.schemas import (
    AbcDetalleResponse,
    AbcSegmentation,
    CohortesDetailResponse,
    CohortesResponse,
    DormidosResponse,
    DriftSummaryResponse,
    ActionRecommendationItem,
    ActionRecommendationsResponse,
    ForecastCategoriaResponse,
    InventorySummary,
    PlanComprasResponse,
    SalesDailyResponse,
    SalesHistoricalResponse,
    SalesMonthlyResponse,
    SalesSummary,
    SalesTrendResponse,
    VendedoresSummaryResponse,
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


def _get_real_metrics_repo() -> RealMetricsRepo:
    if not settings.databricks_host or not settings.databricks_token or not settings.databricks_http_path:
        raise HTTPException(
            status_code=503,
            detail="Metrics require Databricks configuration in production",
        )
    w = _get_workspace()
    wh_id = settings.databricks_http_path.split("/")[-1]
    return RealMetricsRepo(w, wh_id)


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
    # V1.5: DATA_BACKEND env var determina el backend
    if settings.data_backend == "duckdb":
        return DuckDBMetricsRepo(
            db_path=settings.duckdb_path or "/tmp/motoshop_gold.duckdb"
        )
    # Legacy: Databricks
    if settings.env == "prod":
        return _get_real_metrics_repo()
    if settings.databricks_http_path and settings.databricks_host and settings.databricks_token:
        return _get_real_metrics_repo()
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


# ── Sales Summary V2 (V1.8) ──────────────────────────────────────────────

@router.get("/metrics/sales-summary-v2")
@limiter.limit("30/minute")
def sales_summary_v2(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
):
    """Ventas con comparación justa: parcial vs parcial, años anteriores."""
    return _cached_or_fetch("sales-summary-v2", repo.get_sales_summary_v2)


# ── Sales Daily Month (V1.8) ─────────────────────────────────────────────

@router.get("/metrics/sales-daily-month")
@limiter.limit("30/minute")
def sales_daily_month(
    request: Request,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
):
    """Evolución diaria de ventas para un mes específico."""
    return _cached_or_fetch(f"sales-daily-month:{month}", lambda: repo.get_sales_daily_month(month))


# ── Inventory Detail + Discrepancies (V1.8) ──────────────────────────────

@router.get("/metrics/inventory-detail")
@limiter.limit("30/minute")
def inventory_detail(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(default="cod_producto"),
    q: str | None = Query(default=None),
    bodega: str | None = Query(default=None),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
):
    """Inventario detallado con costo, última venta, dormido status, ABC."""
    return _cached_or_fetch(
        f"inv-detail:{page}:{page_size}:{sort}:{q or ''}:{bodega or ''}",
        lambda: repo.get_inventory_detail(page, page_size, sort, q, bodega),
        ttl=60,
    )


@router.get("/metrics/inventory-discrepancies")
@limiter.limit("10/minute")
def inventory_discrepancies(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
):
    """SKUs con diferencias de stock entre inventario y dormidos + invariante SQL."""
    return _cached_or_fetch("inv-discrepancies", repo.get_inventory_discrepancies, ttl=300)

@router.get("/metrics/sales-forecast-monthly")
@limiter.limit("10/minute")
def sales_forecast_monthly(
    request: Request,
    horizon: int = Query(default=2, ge=1, le=3),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
):
    """Proyección de ventas (run-rate) para mes actual y siguiente. Sin LLM."""
    return _cached_or_fetch(f"sales-forecast:{horizon}", lambda: repo.get_sales_forecast_monthly(horizon))


@router.get("/metrics/sales-daily", response_model=SalesDailyResponse)
@limiter.limit("30/minute")
def sales_daily(
    request: Request,
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesDailyResponse:
    """Ventas del día específico: productos vendidos, totales."""
    if not date:
        from datetime import date as d
        date = d.today().isoformat()
    return _cached_or_fetch(f"sales-daily:{date}", lambda: repo.get_sales_daily(date))


@router.get("/metrics/sales-monthly", response_model=SalesMonthlyResponse)
@limiter.limit("30/minute")
def sales_monthly(
    request: Request,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesMonthlyResponse:
    """Ventas del mes: total vs mes anterior + top 10 SKUs."""
    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
    return _cached_or_fetch(f"sales-monthly:{month}", lambda: repo.get_sales_monthly(month))


@router.get("/metrics/sales-historical", response_model=SalesHistoricalResponse)
@limiter.limit("30/minute")
def sales_historical(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesHistoricalResponse:
    """Ventas históricas: total acumulado + tendencia mensual."""
    return _cached_or_fetch("sales-historical", repo.get_sales_historical)


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


@router.get("/metrics/abc-detalle", response_model=AbcDetalleResponse)
@limiter.limit("30/minute")
def abc_detalle(
    request: Request,
    bucket: str = Query(pattern=r"^[ABC]$", description="Bucket A, B o C"),
    limit: int = Query(default=20, ge=1, le=100, description="Máx items"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> AbcDetalleResponse:
    """Detalle de productos en un bucket ABC específico."""
    cache_key = f"abc-detalle:{bucket}:{limit}"
    return _cached_or_fetch(cache_key, lambda: repo.get_abc_detalle(bucket, limit))


@router.get("/metrics/dormidos", response_model=DormidosResponse)
@limiter.limit("30/minute")
def dormidos(
    request: Request,
    page: int = Query(default=1, ge=1, description="Número de página"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items por página"),
    sort_by: Literal["dias_sin_venta", "ultima_compra", "ultima_venta"] = Query(default="dias_sin_venta"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> DormidosResponse:
    """Productos sin venta > 90 días, paginados."""
    cache_key = f"dormidos:{page}:{page_size}:{sort_by}:{sort_order}"
    return _cached_or_fetch(
        cache_key,
        lambda: repo.get_dormidos(page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
    )


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
    year: int | None = Query(default=None),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> SalesTrendResponse:
    """Tendencia de ventas mensual: total, facturas y ticket promedio."""
    if periods < 1 or periods > 24:
        raise HTTPException(status_code=422, detail="periods must be between 1 and 24")
    cache_key = f"sales-trend:{periods}:{year}"
    return _cached_or_fetch(cache_key, lambda: repo.get_sales_trend(periods, year))


@router.get("/metrics/vendedores-summary")
@limiter.limit("30/minute")
def vendedores_summary(
    request: Request,
    period: Literal["month", "historical", "6months"] = "month",
    vendedor_id: str | None = Query(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
):
    """Ranking top 10 vendedores o detalle de uno específico.
    period: month | historical | 6months.
    vendedor_id: NIT del vendedor para ver detalle.
    """
    if vendedor_id:
        cache_key = f"vendedor-detail:{vendedor_id}:{period}"
        return _cached_or_fetch(cache_key, lambda: repo.get_vendedor_detail(vendedor_id, period))
    cache_key = f"vendedores-summary:{period}"
    return _cached_or_fetch(cache_key, lambda: repo.get_vendedores_summary(period))


@router.get("/metrics/cohortes-detail", response_model=CohortesDetailResponse)
@limiter.limit("30/minute")
def cohortes_detail(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> CohortesDetailResponse:
    """Detalle de cohortes: LTV, retención por mes, nuevos vs recurrentes."""
    return _cached_or_fetch("cohortes-detail", repo.get_cohortes_detail)


@router.get("/metrics/drift-summary", response_model=DriftSummaryResponse)
@limiter.limit("30/minute")
def drift_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> DriftSummaryResponse:
    """Alertas de drift: métricas desviadas, severidad y acciones recomendadas."""
    return _cached_or_fetch("drift-summary", repo.get_drift_summary)


@router.get("/metrics/plan-compras", response_model=PlanComprasResponse)
@limiter.limit("30/minute")
def plan_compras(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> PlanComprasResponse:
    """Plan de compras: SKUs con stock < demanda, urgencia, ABC, dormidos."""
    return _cached_or_fetch("plan-compras", repo.get_plan_compras)


@router.get("/metrics/forecast-categoria", response_model=ForecastCategoriaResponse)
@limiter.limit("30/minute")
def forecast_categoria(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> ForecastCategoriaResponse:
    """Forecast de demanda por categoría: real vs predicho, WAPE, cobertura."""
    return _cached_or_fetch("forecast-categoria", repo.get_forecast_categoria)


@router.post("/metrics/cache/clear")
def clear_metrics_cache(
    _user: User = Depends(require_role("admin", "gerente")),
) -> dict:
    """Invalidar cache de métricas manualmente."""
    _clear_metrics_cache()
    return {"status": "ok", "message": "Cache cleared"}


@router.get("/metrics/recommendations", response_model=ActionRecommendationsResponse)
@limiter.limit("30/minute")
def action_recommendations(
    request: Request,
    period: Literal["today", "week", "month"] = Query(default="month"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> ActionRecommendationsResponse:
    """Recomendaciones accionables para la vista de Acciones.

    Combina plan de compras y dormidos para proponer decisiones concretas.
    """
    limit = {"today": 5, "week": 10, "month": 15}[period]
    plan = repo.get_plan_compras()
    dormidos = repo.get_dormidos(page=1, page_size=limit, sort_by="dias_sin_venta", sort_order="desc")

    items: list[ActionRecommendationItem] = []
    seen: set[str] = set()

    for item in plan.items[:limit]:
        if item.sku in seen:
            continue
        seen.add(item.sku)
        priority = item.urgencia or ("alta" if item.cantidad_a_comprar >= 20 else "media")
        items.append(
            ActionRecommendationItem(
                sku=item.sku,
                nom_producto=item.nombre,
                reason=(
                    f"La demanda de 7 días ({item.demanda_7d:.0f}) supera el stock actual "
                    f"({item.stock_actual:.0f}) y requiere comprar {item.cantidad_a_comprar:.0f} unidades."
                ),
                priority=priority if priority in ("alta", "media", "baja") else "media",
                period=period,
                status="open" if item.urgencia == "alta" or item.cantidad_a_comprar > 0 else "monitor",
                action_type="comprar",
            )
        )

    for item in dormidos.items[:limit]:
        if item.cod_producto in seen:
            continue
        seen.add(item.cod_producto)
        priority = "alta" if item.dias_sin_venta >= 180 else "media" if item.dias_sin_venta >= 120 else "baja"
        items.append(
            ActionRecommendationItem(
                sku=item.cod_producto,
                nom_producto=item.nom_producto,
                reason=(
                    f"Producto sin ventas hace {item.dias_sin_venta} días; "
                    "evaluar liquidación o salida promocional."
                ),
                priority=priority,
                period=period,
                status="open" if item.dias_sin_venta >= 120 else "monitor",
                action_type="liquidar",
            )
        )

    return ActionRecommendationsResponse(period=period, total=len(items), items=items)
