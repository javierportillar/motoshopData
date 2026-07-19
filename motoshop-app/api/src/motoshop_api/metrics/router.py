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

from motoshop_api.auth.deps import get_current_user, require_module, require_role
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.metrics.repo import (
    MetricsRepoProtocol,
    RealMetricsRepo,
)
from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo
from motoshop_api.metrics.snapshot import get_snapshot_generation, publish_snapshot
from motoshop_api.metrics.schemas import (
    AbcDetalleResponse,
    AbcSegmentation,
    ActionRecommendationItem,
    ActionRecommendationsResponse,
    BalanceResponse,
    CashClosureResponse,
    CohortesDetailResponse,
    CohortesResponse,
    DormidosResponse,
    DriftSummaryResponse,
    ForecastCategoriaResponse,
    HoraPicoResponse,
    InventorySummary,
    PaymentsHistoryResponse,
    PlanComprasResponse,
    PurchasesDayDetailResponse,
    SalesDailyResponse,
    SalesDailyMonthResponse,
    SalesDayDetailResponse,
    SalesDayInvoicesResponse,
    SalesForecastMonthlyResponse,
    SalesHistoricalResponse,
    SalesMonthDetailResponse,
    SalesMonthlyResponse,
    SalesSummary,
    SalesSummaryV2Response,
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
_cache: dict[tuple[int, str], tuple[float, object]] = {}
_workspace_client = None  # lazy singleton
_workspace_created_at: float = 0.0
_WORKSPACE_TTL = 3600  # Refresh workspace client hourly

# Cache de repos DuckDB por tenant para evitar fugas de conexión
# (cada DuckDBMetricsRepo abre su propia conexión duckdb.connect())
_duckdb_repos: dict[str, DuckDBMetricsRepo] = {}


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
    tenant = key.partition(":")[0]
    versioned_key = (get_snapshot_generation(tenant), key)
    now = time()
    if versioned_key in _cache:
        ts, val = _cache[versioned_key]
        if now - ts < ttl:
            return val
    val = fetch_fn()
    # Store under the generation captured before the fetch. A concurrent R2
    # replacement advances the generation, making this value unreachable.
    _cache[versioned_key] = (now, val)
    return val


def _clear_metrics_cache():
    _cache.clear()


def get_repo(tenant: str = Depends(get_tenant)) -> MetricsRepoProtocol:
    # V1.5: DATA_BACKEND env var determina el backend
    if settings.data_backend == "duckdb":
        # Singleton por tenant: abre UNA conexión DuckDB por proceso,
        # no una por request (previene OOM en Render Free).
        if tenant not in _duckdb_repos:
            _duckdb_repos[tenant] = DuckDBMetricsRepo(tenant=tenant)
        return _duckdb_repos[tenant]
    # Legacy: Databricks
    if settings.env == "prod":
        return _get_real_metrics_repo()
    if settings.databricks_http_path and settings.databricks_host and settings.databricks_token:
        return _get_real_metrics_repo()
    from motoshop_api.metrics.repo import FakeMetricsRepo

    return FakeMetricsRepo()


@router.get(
    "/metrics/sales-summary",
    response_model=SalesSummary,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesSummary:
    """Resumen de ventas del mes actual vs anterior + top 10 SKUs."""
    return _cached_or_fetch(f"{tenant}:sales-summary", repo.get_sales_summary)


# ── Sales Summary V2 (V1.8) ──────────────────────────────────────────────

@router.get(
    "/metrics/sales-summary-v2",
    response_model=SalesSummaryV2Response,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_summary_v2(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Ventas con comparación justa: parcial vs parcial, años anteriores."""
    return _cached_or_fetch(f"{tenant}:sales-summary-v2", repo.get_sales_summary_v2)


# ── Sales Daily Month (V1.8) ─────────────────────────────────────────────

@router.get(
    "/metrics/sales-daily-month",
    response_model=SalesDailyMonthResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_daily_month(
    request: Request,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Evolución diaria de ventas para un mes específico."""
    return _cached_or_fetch(f"{tenant}:sales-daily-month:{month}", lambda: repo.get_sales_daily_month(month))


# ── Inventory Detail + Discrepancies (V1.8) ──────────────────────────────

@router.get(
    "/metrics/inventory-detail",
    dependencies=[Depends(require_module("inventario"))],
)
@limiter.limit("30/minute")
def inventory_detail(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(default="cod_producto"),
    q: str | None = Query(default=None),
    bodega: str | None = Query(default=None),
    stock: str = Query(default="todos", pattern="^(todos|con_stock|sin_stock)$"),
    dormido: str = Query(default="todos", pattern="^(todos|true|false)$"),
    abc: str | None = Query(default=None, pattern="^(A|B|C)$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Inventario detallado con costo, última venta, dormido status, ABC."""
    return _cached_or_fetch(
        f"{tenant}:inv-detail:{page}:{page_size}:{sort}:{q or ''}:{bodega or ''}:{stock}:{dormido}:{abc or ''}",
        lambda: repo.get_inventory_detail(page, page_size, sort, q, bodega, stock, dormido, abc),
        ttl=60,
    )


@router.get("/metrics/inventory-discrepancies")
@limiter.limit("10/minute")
def inventory_discrepancies(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """SKUs con diferencias de stock entre inventario y dormidos + invariante SQL."""
    return _cached_or_fetch(f"{tenant}:inv-discrepancies", repo.get_inventory_discrepancies, ttl=300)

@router.get(
    "/metrics/sales-forecast-monthly",
    response_model=SalesForecastMonthlyResponse,
    dependencies=[Depends(require_module("forecast"))],
)
@limiter.limit("10/minute")
def sales_forecast_monthly(
    request: Request,
    horizon: Literal[2] = Query(
        default=2,
        description="Only the implemented current+next month horizon is supported",
    ),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesForecastMonthlyResponse:
    """Proyección de ventas (run-rate) para mes actual y siguiente. Sin LLM."""
    payload = _cached_or_fetch(
        f"{tenant}:sales-forecast:2",
        repo.get_sales_forecast_monthly,
    )
    return SalesForecastMonthlyResponse(**payload)


@router.get(
    "/metrics/sales-daily",
    response_model=SalesDailyResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_daily(
    request: Request,
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesDailyResponse:
    """Ventas del día específico: productos vendidos, totales."""
    if not date:
        from datetime import date as d
        date = d.today().isoformat()
    return _cached_or_fetch(f"{tenant}:sales-daily:{date}", lambda: repo.get_sales_daily(date))


@router.get(
    "/metrics/sales-monthly",
    response_model=SalesMonthlyResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_monthly(
    request: Request,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    products_limit: int = Query(default=10, ge=1, le=5000,
                                description="Cantidad de productos top. Pasar >10 para 'ver todos'."),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesMonthlyResponse:
    """Ventas del mes: total vs mes anterior + productos top (limit configurable)."""
    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
    return _cached_or_fetch(
        f"{tenant}:sales-monthly:{month}:lim{products_limit}",
        lambda: repo.get_sales_monthly(month, products_limit=products_limit),
    )


@router.get("/metrics/sales-historical-products")
@limiter.limit("30/minute")
def sales_historical_products(
    request: Request,
    limit: int = Query(default=10, ge=1, le=5000,
                       description="Cantidad de productos top. Pasar >10 para 'ver todos'."),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Top productos vendidos en TODO el histórico (agregado por SKU)."""
    return _cached_or_fetch(
        f"{tenant}:sales-historical-products:lim{limit}",
        lambda: repo.get_sales_historical_products(limit=limit),
        ttl=600,
    )


@router.get(
    "/metrics/sales-day-detail",
    response_model=SalesDayDetailResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_day_detail(
    request: Request,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesDayDetailResponse:
    """Detalle completo de un dia: KPIs, distribucion horaria, productos, vendedores,
    forma de pago, margen, comparativas. Sirve al popup del calendario de la tab Diaria."""
    return _cached_or_fetch(
        f"{tenant}:sales-day-detail:{date}",
        lambda: SalesDayDetailResponse(**repo.get_sales_day_detail(date)),
    )


@router.get(
    "/metrics/sales-month-detail",
    response_model=SalesMonthDetailResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_month_detail(
    request: Request,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesMonthDetailResponse:
    """Detalle enriquecido del mes: margen, vendedores top, forma de pago, mejor/peor dia,
    productos en aceleracion/desaceleracion. Complementa a sales-summary."""
    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
    return _cached_or_fetch(
        f"{tenant}:sales-month-detail:{month}",
        lambda: SalesMonthDetailResponse(**repo.get_sales_month_detail(month)),
    )


@router.get(
    "/metrics/sales-day-invoices",
    response_model=SalesDayInvoicesResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_day_invoices(
    request: Request,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesDayInvoicesResponse:
    """Facturas del dia con detalle expandido de items por factura.
    Sirve a la pagina dedicada del dia (no popup) — cada factura con
    sus lineas: producto, cantidad, valor unitario, descuento, IVA, total."""
    return _cached_or_fetch(
        f"{tenant}:sales-day-invoices:{date}",
        lambda: SalesDayInvoicesResponse(**repo.get_sales_day_invoices(date)),
    )


@router.get(
    "/metrics/cash-closure",
    response_model=CashClosureResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def cash_closure(
    request: Request,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> CashClosureResponse:
    """Cierre de caja del dia tipo Z-report del POS: desglose por forma de
    pago, lista de facturas con su forma+hora+cliente+vendedor, top 5
    facturas grandes del dia."""
    return _cached_or_fetch(
        f"{tenant}:cash-closure:{date}",
        lambda: CashClosureResponse(**repo.get_cash_closure(date)),
    )


@router.get("/metrics/payments-history", response_model=PaymentsHistoryResponse)
@limiter.limit("30/minute")
def payments_history(
    request: Request,
    months: int = Query(default=12, ge=1, le=36, description="Cantidad de meses hacia atras"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> PaymentsHistoryResponse:
    """Tendencia historica del mix de formas de pago. Serie mensual stacked
    + variacion del mix actual vs hace 6 meses (cambios de tendencia)."""
    return _cached_or_fetch(
        f"{tenant}:payments-history:{months}",
        lambda: PaymentsHistoryResponse(**repo.get_payments_history(months)),
    )


@router.get("/metrics/purchases-day-detail", response_model=PurchasesDayDetailResponse)
@limiter.limit("30/minute")
def purchases_day_detail(
    request: Request,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> PurchasesDayDetailResponse:
    """Detalle de compras de un día específico. Sirve a la página /dashboards/compras/dia/[date]."""
    return _cached_or_fetch(
        f"{tenant}:purchases-day-detail:{date}",
        lambda: PurchasesDayDetailResponse(**repo.get_purchases_day_detail(date)),
    )


@router.get(
    "/metrics/sales-historical",
    response_model=SalesHistoricalResponse,
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def sales_historical(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesHistoricalResponse:
    """Ventas históricas: total acumulado + tendencia mensual."""
    return _cached_or_fetch(f"{tenant}:sales-historical", repo.get_sales_historical)


@router.get(
    "/metrics/inventory-summary",
    response_model=InventorySummary,
    dependencies=[Depends(require_module("inventario"))],
)
@limiter.limit("30/minute")
def inventory_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> InventorySummary:
    """Resumen de inventario: stock total, valor, distribución por bodega."""
    return _cached_or_fetch(f"{tenant}:inventory-summary", repo.get_inventory_summary)


# ── Analítica de productos / inventario (V1.10) ──────────────────────────

@router.get(
    "/metrics/inventory-overview",
    dependencies=[Depends(require_module("inventario"))],
)
@limiter.limit("30/minute")
def inventory_overview(
    request: Request,
    window: int = Query(default=180, ge=30, le=720, description="Ventana de análisis en días"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Resumen ejecutivo del inventario: KPIs reales, concentración Pareto
    (qué % de productos hace el 80% de las ventas), distribución por estado,
    y las 4 listas de decisión (quiebre, capital atrapado, importantes sin
    recompra, dormidos premium)."""
    return _cached_or_fetch(
        f"{tenant}:inv-overview:{window}",
        lambda: repo.get_inventory_overview(window),
        ttl=120,
    )


@router.get("/metrics/product-analytics")
@limiter.limit("60/minute")
def product_analytics(
    request: Request,
    window: int = Query(default=180, ge=30, le=720),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None),
    abc: str | None = Query(default=None, pattern="^(A|B|C)$"),
    estado: str | None = Query(default=None),
    sort: str = Query(default="revenue_win"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    preset: str | None = Query(default=None, pattern="^(por_agotarse|capital_atrapado|importantes|dormidos)$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Tabla rica de productos: stock real, velocidad, días de stock, rotación,
    ABC dinámico, margen, estado y acción sugerida. Con búsqueda, filtros y orden.

    V1.31: `preset` scopea al criterio EXACTO de una decision card
    (por_agotarse, capital_atrapado, importantes, dormidos) para que el plan
    del frontend muestre el mismo count que la card."""
    key = f"{tenant}:prod-analytics:{window}:{page}:{page_size}:{q or ''}:{abc or ''}:{estado or ''}:{sort}:{order}:{preset or ''}"
    return _cached_or_fetch(
        key,
        lambda: repo.get_product_analytics(window, page, page_size, q, abc, estado, sort, order, preset),
        ttl=120,
    )


@router.get("/metrics/product-detail")
@limiter.limit("60/minute")
def product_detail(
    request: Request,
    sku: str = Query(..., description="Código del producto (puede contener /, se pasa como query param para evitar problemas de encoding)"),
    window: int = Query(default=180, ge=30, le=720),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Ficha completa de un producto: todas las métricas + timeline mensual
    de compras vs ventas + últimos movimientos.

    NOTA: SKU se pasa como query parameter (no path) porque muchos SKUs
    contienen '/' en su nombre y rompen el route matching si van en el path."""
    return _cached_or_fetch(
        f"{tenant}:prod-detail:{sku}:{window}",
        lambda: repo.get_product_detail(sku, window),
        ttl=120,
    )


@router.get("/metrics/product-abc-map")
@limiter.limit("60/minute")
def product_abc_map(
    request: Request,
    window: int = Query(default=180, ge=30, le=720),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Mapa liviano sku → {abc, estado, pct_revenue, rank}. El frontend lo usa
    para etiquetar productos en cualquier lista (mensual, diaria, facturas)
    sin recalcular ABC en esos endpoints."""
    return _cached_or_fetch(
        f"{tenant}:abc-map:{window}",
        lambda: repo.get_product_abc_map(window),
        ttl=300,
    )


@router.get("/metrics/sales-history-extended")
@limiter.limit("30/minute")
def sales_history_extended(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Histórico enriquecido: serie mensual con margen, mejor/peor mes y
    comparativa año vs año."""
    return _cached_or_fetch(
        f"{tenant}:sales-hist-ext",
        repo.get_sales_history_extended,
        ttl=300,
    )


@router.get("/metrics/abc-segmentation", response_model=AbcSegmentation)
@limiter.limit("30/minute")
def abc_segmentation(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> AbcSegmentation:
    """Segmentación ABC de ingresos (80/15/5) del mes actual."""
    return _cached_or_fetch(f"{tenant}:abc-segmentation", repo.get_abc_segmentation)


@router.get("/metrics/abc-detalle", response_model=AbcDetalleResponse)
@limiter.limit("30/minute")
def abc_detalle(
    request: Request,
    bucket: str = Query(pattern=r"^[ABC]$", description="Bucket A, B o C"),
    limit: int = Query(default=20, ge=1, le=100, description="Máx items"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> AbcDetalleResponse:
    """Detalle de productos en un bucket ABC específico."""
    cache_key = f"{tenant}:abc-detalle:{bucket}:{limit}"
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
    tenant: str = Depends(get_tenant),
) -> DormidosResponse:
    """Productos sin venta > 90 días, paginados."""
    cache_key = f"{tenant}:dormidos:{page}:{page_size}:{sort_by}:{sort_order}"
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
    tenant: str = Depends(get_tenant),
) -> CohortesResponse:
    """Cohortes de clientes por mes de primera compra."""
    return _cached_or_fetch(f"{tenant}:cohortes", repo.get_cohortes)


@router.get("/metrics/sales-trend", response_model=SalesTrendResponse)
@limiter.limit("30/minute")
def sales_trend(
    request: Request,
    periods: int = 6,
    year: int | None = Query(default=None),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> SalesTrendResponse:
    """Tendencia de ventas mensual: total, facturas y ticket promedio."""
    if periods < 1 or periods > 24:
        raise HTTPException(status_code=422, detail="periods must be between 1 and 24")
    cache_key = f"{tenant}:sales-trend:{periods}:{year}"
    return _cached_or_fetch(cache_key, lambda: repo.get_sales_trend(periods, year))


@router.get("/metrics/vendedores-summary")
@limiter.limit("30/minute")
def vendedores_summary(
    request: Request,
    period: Literal["month", "historical", "6months"] = "month",
    vendedor_id: str | None = Query(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Ranking top 10 vendedores o detalle de uno específico.
    period: month | historical | 6months.
    vendedor_id: NIT del vendedor para ver detalle.
    """
    if vendedor_id:
        cache_key = f"{tenant}:vendedor-detail:{vendedor_id}:{period}"
        return _cached_or_fetch(cache_key, lambda: repo.get_vendedor_detail(vendedor_id, period))
    cache_key = f"{tenant}:vendedores-summary:{period}"
    return _cached_or_fetch(cache_key, lambda: repo.get_vendedores_summary(period))


@router.get("/metrics/cohortes-detail", response_model=CohortesDetailResponse)
@limiter.limit("30/minute")
def cohortes_detail(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> CohortesDetailResponse:
    """Detalle de cohortes: LTV, retención por mes, nuevos vs recurrentes."""
    return _cached_or_fetch(f"{tenant}:cohortes-detail", repo.get_cohortes_detail)


@router.get("/metrics/drift-summary", response_model=DriftSummaryResponse)
@limiter.limit("30/minute")
def drift_summary(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> DriftSummaryResponse:
    """Alertas de drift: métricas desviadas, severidad y acciones recomendadas."""
    return _cached_or_fetch(f"{tenant}:drift-summary", repo.get_drift_summary)


@router.get(
    "/metrics/plan-compras",
    response_model=PlanComprasResponse,
    dependencies=[Depends(require_module("decisiones"))],
)
@limiter.limit("30/minute")
def plan_compras(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> PlanComprasResponse:
    """Plan de compras: SKUs con stock < demanda, urgencia, ABC, dormidos."""
    return _cached_or_fetch(f"{tenant}:plan-compras", repo.get_plan_compras)


@router.get("/metrics/forecast-categoria", response_model=ForecastCategoriaResponse)
@limiter.limit("30/minute")
def forecast_categoria(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> ForecastCategoriaResponse:
    """Forecast de demanda por categoría: real vs predicho, WAPE, cobertura."""
    return _cached_or_fetch(f"{tenant}:forecast-categoria", repo.get_forecast_categoria)


@router.post("/metrics/cache/clear")
def clear_metrics_cache(
    _user: User = Depends(require_role("admin", "gerente")),
    tenant: str = Depends(get_tenant),
) -> dict:
    """Invalidar cache de métricas manualmente."""
    publish_snapshot(tenant)
    return {"status": "ok", "message": "Cache cleared"}


@router.get(
    "/metrics/recommendations",
    response_model=ActionRecommendationsResponse,
    dependencies=[Depends(require_module("decisiones", "acciones"))],
)
@limiter.limit("30/minute")
def action_recommendations(
    request: Request,
    period: Literal["today", "week", "month"] = Query(default="month"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
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


# ── Análisis financiero (V1.11) ─────────────────────────────────────────────

def _validate_date_range(fecha_inicio: str, fecha_fin: str) -> None:
    """Valida formato YYYY-MM-DD y que inicio <= fin."""
    import re
    fmt = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not fmt.match(fecha_inicio) or not fmt.match(fecha_fin):
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar YYYY-MM-DD.")
    if fecha_inicio > fecha_fin:
        raise HTTPException(status_code=400, detail="fecha_inicio debe ser <= fecha_fin.")


@router.get(
    "/metrics/horas-pico",
    response_model=HoraPicoResponse,
    dependencies=[Depends(require_module("analisis"))],
)
@limiter.limit("30/minute")
def horas_pico(
    request: Request,
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> HoraPicoResponse:
    """Ventas y facturas agregadas por hora del día (0-23) en el rango."""
    _validate_date_range(fecha_inicio, fecha_fin)
    cache_key = f"{tenant}:horas-pico:{fecha_inicio}:{fecha_fin}"
    return _cached_or_fetch(
        cache_key,
        lambda: repo.get_hours_peak(fecha_inicio, fecha_fin),
        ttl=300,
    )


@router.get(
    "/metrics/analisis-balance",
    response_model=BalanceResponse,
    dependencies=[Depends(require_module("analisis"))],
)
@limiter.limit("30/minute")
def analisis_balance(
    request: Request,
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> BalanceResponse:
    """Balance financiero día a día: ventas, costo mercancía, gastos operativos,
    ganancia bruta/neta y balance acumulado.

    Los gastos operativos vienen de Supabase y se prorratean entre los días
    calendario del mes correspondiente.
    """
    _validate_date_range(fecha_inicio, fecha_fin)

    # Gastos operativos prorrateados por día desde Supabase.
    # Si Supabase no está configurado, el helper devuelve {} y el balance
    # se calcula sin gastos operativos (queda ganancia_bruta == ganancia_neta).
    from motoshop_api.gastos.supabase_client import gastos_prorrateados_por_dia
    gastos_diarios = gastos_prorrateados_por_dia(tenant, fecha_inicio, fecha_fin)

    # Cache key incluye un hash de gastos para invalidar al modificarlos
    gastos_signature = hash(tuple(sorted(gastos_diarios.items())))
    cache_key = f"{tenant}:analisis-balance:{fecha_inicio}:{fecha_fin}:{gastos_signature}"
    return _cached_or_fetch(
        cache_key,
        lambda: repo.get_analisis_balance(fecha_inicio, fecha_fin, gastos_diarios),
        ttl=60,  # TTL bajo: si el user carga un gasto, lo ve casi al instante
    )


# ── V1.16: catálogo zombie, salud, heatmap, vendor flag (derivados del EDA) ──

@router.get("/metrics/productos-zombie")
@limiter.limit("30/minute")
def productos_zombie(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Productos que NUNCA se vendieron desde que entraron al catálogo.

    Distinto a 'dormidos' (productos que vendían y dejaron de vender).
    Útil para liquidación, devolución a proveedor, descatalogación.
    Incluye capital_inmovilizado (stock × costo) por SKU y total.
    """
    return _cached_or_fetch(
        f"{tenant}:productos-zombie:p{page}:ps{page_size}",
        lambda: repo.get_productos_zombie(page=page, page_size=page_size),
        ttl=600,
    )


@router.get("/metrics/salud-catalogo")
@limiter.limit("30/minute")
def salud_catalogo(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """KPI agregado del catálogo: activos/lentos/dormidos/zombie + score salud."""
    return _cached_or_fetch(
        f"{tenant}:salud-catalogo",
        repo.get_salud_catalogo,
        ttl=600,
    )


@router.get("/metrics/heatmap-dia-hora")
@limiter.limit("30/minute")
def heatmap_dia_hora(
    request: Request,
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Matriz 7 días × 24 horas: facturas, ventas, ticket promedio por celda.

    Útil para identificar picos cruzados (ej: 'sábados a las 5pm') y
    detectar patrones de cierre (ej: 'masvital cierra dominicales')."""
    _validate_date_range(fecha_inicio, fecha_fin)
    return _cached_or_fetch(
        f"{tenant}:heatmap-dia-hora:{fecha_inicio}:{fecha_fin}",
        lambda: repo.get_heatmap_dia_hora(fecha_inicio, fecha_fin),
        ttl=300,
    )


@router.get("/metrics/vendor-data-flag")
@limiter.limit("30/minute")
def vendor_data_flag(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Indica si el tenant tiene datos confiables de vendedor (NULL <50%).

    El frontend usa este flag para ocultar el bloque 'Top vendedores'
    cuando no es útil (caso MasVital con 99% NULL)."""
    return _cached_or_fetch(
        f"{tenant}:vendor-data-flag",
        repo.get_vendor_data_flag,
        ttl=600,
    )


# ── V1.17: Inventario inteligente (refactor /dashboards/inventario) ──

@router.get(
    "/metrics/inventario-overview",
    dependencies=[Depends(require_module("inventario"))],
)
@limiter.limit("30/minute")
def inventario_overview(
    request: Request,
    lead_time_dias: int = Query(default=7, ge=1, le=90),
    colchon_dias: int = Query(default=14, ge=0, le=180),
    umbral_sobrestock_dias: int = Query(default=180, ge=30, le=720),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Endpoint único de inventario. Devuelve TODOS los SKUs clasificados
    en buckets de acción (comprar_ya, comprar_pronto, sobrestock, liquidar,
    zombie_con_stock, ok, sin_accion) + cobertura, sugerencia de compra,
    capital inmovilizado y resumen agregado.

    Reemplaza la lógica fragmentada de /abc, /plan-compras, /dormidos
    consolidando todo en una sola fuente de verdad."""
    return _cached_or_fetch(
        f"{tenant}:inv-overview:{lead_time_dias}:{colchon_dias}:{umbral_sobrestock_dias}",
        lambda: repo.get_inventario_overview(
            lead_time_dias=lead_time_dias,
            colchon_dias=colchon_dias,
            umbral_sobrestock_dias=umbral_sobrestock_dias,
        ),
        ttl=300,
    )


# ── V1.19: Compras refactor (overview mensual + histórico + por proveedor) ──

@router.get(
    "/metrics/compras-overview",
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def compras_overview(
    request: Request,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Overview de compras del mes: KPIs + serie diaria (calendario) +
    top proveedores + top productos."""
    return _cached_or_fetch(
        f"{tenant}:compras-overview:{month}",
        lambda: repo.get_compras_overview(month),
        ttl=300,
    )


@router.get(
    "/metrics/compras-historico",
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def compras_historico(
    request: Request,
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Histórico mensual de compras + agregados totales (para gráfico
    de tendencia y comparativo año-vs-año)."""
    return _cached_or_fetch(
        f"{tenant}:compras-historico",
        repo.get_compras_historico,
        ttl=600,
    )


@router.get("/metrics/compras-por-proveedor")
@limiter.limit("30/minute")
def compras_por_proveedor(
    request: Request,
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Compras agrupadas por proveedor en un rango. # docs, total,
    primera/última compra por proveedor. Ordenado por total desc."""
    _validate_date_range(fecha_inicio, fecha_fin)
    return _cached_or_fetch(
        f"{tenant}:compras-por-prov:{fecha_inicio}:{fecha_fin}",
        lambda: repo.get_compras_por_proveedor(fecha_inicio, fecha_fin),
        ttl=300,
    )


# ── V1.20: Compras enriquecidas (popup día + proveedor detalle) ──────────

@router.get(
    "/metrics/purchases-day-grouped",
    dependencies=[Depends(require_module("ventas-summary"))],
)
@limiter.limit("30/minute")
def purchases_day_grouped(
    request: Request,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Detalle del día agrupado por DOCUMENTO + PROVEEDOR. Cada compra
    aparece con su proveedor y la lista de productos que se compraron
    en ella. Reemplaza al shape plano de purchases-day-detail."""
    return _cached_or_fetch(
        f"{tenant}:purchases-day-grouped:{date}",
        lambda: repo.get_purchases_day_grouped(date),
        ttl=300,
    )


@router.get("/metrics/compras-proveedor-detalle")
@limiter.limit("30/minute")
def compras_proveedor_detalle(
    request: Request,
    nit_proveedor: str = Query(..., min_length=1),
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Detalle de compras a un proveedor específico en un rango. Devuelve
    todos los documentos del proveedor + sus items + un resumen agregado
    de qué productos le comprás más a ese proveedor."""
    _validate_date_range(fecha_inicio, fecha_fin)
    return _cached_or_fetch(
        f"{tenant}:compras-prov-det:{nit_proveedor}:{fecha_inicio}:{fecha_fin}",
        lambda: repo.get_compras_proveedor_detalle(nit_proveedor, fecha_inicio, fecha_fin),
        ttl=300,
    )


# ── V1.21: Análisis de productos y proveedores ──────────────────────────

@router.get(
    "/metrics/analisis-productos",
    dependencies=[Depends(require_module("analisis"))],
)
@limiter.limit("30/minute")
def analisis_productos(
    request: Request,
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=10, le=200),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Análisis de productos: 3 rankings (revenue, margen, unidades) +
    Pareto + crecimiento vs período anterior comparable."""
    _validate_date_range(fecha_inicio, fecha_fin)
    return _cached_or_fetch(
        f"{tenant}:analisis-prod:{fecha_inicio}:{fecha_fin}:{limit}",
        lambda: repo.get_analisis_productos(fecha_inicio, fecha_fin, limit),
        ttl=300,
    )


@router.get(
    "/metrics/analisis-proveedores",
    dependencies=[Depends(require_module("analisis"))],
)
@limiter.limit("30/minute")
def analisis_proveedores(
    request: Request,
    fecha_inicio: str = Query(..., description="YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="YYYY-MM-DD"),
    repo: MetricsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
):
    """Análisis estratégico de proveedores: top + concentración (HHI, top
    1/3/5) + frecuencia + alertas de dependencia."""
    _validate_date_range(fecha_inicio, fecha_fin)
    return _cached_or_fetch(
        f"{tenant}:analisis-prov:{fecha_inicio}:{fecha_fin}",
        lambda: repo.get_analisis_proveedores(fecha_inicio, fecha_fin),
        ttl=300,
    )
