"""Router de predicciones de demanda: GET /forecast/{sku}

Cache server-side de 5 min. Usa RealForecastRepo (gold.forecast_demanda_sku)
en prod/dev; FakeForecastRepo solo en tests.
"""

from __future__ import annotations

from time import time

from fastapi import APIRouter, Depends, HTTPException, Query

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.forecast.repo import (
    DuckDBForecastRepo,
    FakeForecastRepo,
    ForecastRepoProtocol,
    RealForecastRepo,
    get_forecast_repo,
)
from motoshop_api.forecast.schemas import ForecastResponse

router = APIRouter(tags=["forecast"])


_CACHE_TTL = 300  # 5 minutos
_cache: dict[str, tuple[float, object]] = {}
_workspace_client = None
_workspace_created_at: float = 0.0
_WORKSPACE_TTL = 3600


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


def _clear_forecast_cache():
    _cache.clear()


def get_repo() -> ForecastRepoProtocol:
    """Inyección de dependencias: DuckDB si DATA_BACKEND=duckdb, Databricks si no."""
    if settings.data_backend == "duckdb":
        db_path = settings.duckdb_path or (
            "/tmp/motoshop_gold.duckdb" if settings.env == "prod" else "out/motoshop_gold.duckdb"
        )
        return DuckDBForecastRepo(db_path)
    if settings.env != "test":
        w = _get_workspace()
        wh_id = settings.databricks_http_path.split("/")[-1] if settings.databricks_http_path else ""
        return RealForecastRepo(w, wh_id)
    return FakeForecastRepo()


@router.get("/forecast/{sku}", response_model=ForecastResponse)
def forecast_sku(
    sku: str,
    horizon: int = Query(default=7, ge=7, le=30, description="Horizonte en días (7, 14, 30)"),
    repo: ForecastRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> ForecastResponse:
    """Predicción de demanda para un SKU en un horizonte dado.

    - `horizon`: 7, 14, o 30 días
    - V1.5 DuckDB: forecast por SKU descontinuado (ADR-0020). Usar /api/metrics/forecast-categoria
    - 404 si el SKU no tiene datos de forecast
    """
    if isinstance(repo, DuckDBForecastRepo):
        raise HTTPException(
            status_code=410,
            detail="Forecast por SKU descontinuado en V1.5 (ADR-0020). Usá /api/metrics/forecast-categoria para forecast agregado por categoría.",
        )
    cache_key = f"forecast:{sku}:{horizon}"
    result = _cached_or_fetch(cache_key, lambda: repo.get_forecast(sku, horizon))
    if result is None:
        raise HTTPException(status_code=404, detail=f"No forecast data for SKU '{sku}'")
    return result


@router.post("/forecast/cache/clear")
def clear_forecast_cache(
    _user: User = Depends(get_current_user),
) -> dict:
    """Invalidar cache de forecast manualmente."""
    _clear_forecast_cache()
    return {"status": "ok", "message": "Forecast cache cleared"}
