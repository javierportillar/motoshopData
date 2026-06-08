"""Router de pipeline runs — observability V1.7.

GET /api/admin/pipeline/runs        — list runs (filtrable)
GET /api/admin/pipeline/runs/{id}   — detail + steps
GET /api/admin/pipeline/summary     — KPIs 30d
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.users import User

router = APIRouter(prefix="/admin/pipeline", tags=["pipeline_runs"])

_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 30  # seconds


def get_repo():
    from motoshop_api.pipeline_runs.repo import PipelineRunsRepo
    return PipelineRunsRepo()


@router.get("/runs")
def list_runs(
    request: Request,
    limit: int = Query(default=30, ge=1, le=200),
    pipeline: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _user: User = Depends(require_role("admin", "gerente")),
    repo=Depends(get_repo),
):
    """Lista las últimas N ejecuciones de pipeline."""
    rows = repo.list_runs(limit=limit, pipeline=pipeline, status=status)
    return {"runs": rows, "total": len(rows)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    _user: User = Depends(require_role("admin", "gerente")),
    repo=Depends(get_repo),
):
    """Detalle de una ejecución de pipeline con sus steps."""
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} no encontrado")
    return run


@router.get("/summary")
def get_summary(
    _user: User = Depends(require_role("admin", "gerente")),
    repo=Depends(get_repo),
):
    """Resumen de KPIs de pipeline: success rate, avg duration, último estado."""
    return repo.get_summary()
