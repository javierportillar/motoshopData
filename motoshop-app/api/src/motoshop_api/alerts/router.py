"""Router de alertas de quiebre: GET /alerts/stockout

Cache server-side de 5 min. Ordena por urgencia (alta primero) y
dias_hasta_quiebre ASC.
"""

from __future__ import annotations

from time import time

from fastapi import APIRouter, Depends, Query

from motoshop_api.alerts.repo import (
    AlertsRepoProtocol,
    FakeAlertsRepo,
    RealAlertsRepo,
)
from motoshop_api.alerts.schemas import AlertsResponse
from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.config import settings

router = APIRouter(tags=["alerts"])


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


def _clear_alerts_cache():
    _cache.clear()


def get_repo() -> AlertsRepoProtocol:
    """Inyección de dependencias: RealAlertsRepo en prod/dev, Fake solo en tests."""
    if settings.env != "test":
        w = _get_workspace()
        wh_id = settings.databricks_http_path.split("/")[-1] if settings.databricks_http_path else ""
        return RealAlertsRepo(w, wh_id)
    return FakeAlertsRepo()


@router.get("/alerts/stockout", response_model=AlertsResponse)
def stockout_alerts(
    urgency: str | None = Query(default=None, description="Filtrar por urgencia: alta, media, baja"),
    repo: AlertsRepoProtocol = Depends(get_repo),
    _user: User = Depends(get_current_user),
) -> AlertsResponse:
    """Alertas de quiebre de stock, ordenadas por urgencia (alta → baja) y días hasta quiebre ASC.

    - Sin filtro: devuelve todas las alertas
    - `?urgency=alta`: solo alertas críticas
    - `?urgency=media`: solo alertas medias
    - `?urgency=baja`: solo alertas bajas
    """
    if urgency and urgency not in ("alta", "media", "baja"):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Urgency must be one of: alta, media, baja (got '{urgency}')",
        )

    cache_key = f"alerts:stockout:{urgency or 'all'}"
    result = _cached_or_fetch(cache_key, lambda: repo.get_stockout_alerts(urgency))
    return result


@router.post("/alerts/cache/clear")
def clear_alerts_cache(
    _user: User = Depends(get_current_user),
) -> dict:
    """Invalidar cache de alertas manualmente."""
    _clear_alerts_cache()
    return {"status": "ok", "message": "Alerts cache cleared"}
