"""Health + data freshness endpoint."""
from __future__ import annotations

from datetime import datetime, timezone

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter

from motoshop_api.config import settings

router = APIRouter(tags=["meta"])


@router.get("/health/data-freshness")
def data_freshness() -> dict:
    """Devuelve lag desde el último manifest subido al UC Volume."""
    if not settings.databricks_host or not settings.databricks_token:
        return {"status": "ERROR", "error": "Databricks credentials not configured"}

    try:
        w = WorkspaceClient(host=settings.databricks_host, token=settings.databricks_token)
        manifests = list(
            w.files.list_directory_contents(
                f"{settings.databricks_volume_path.rstrip('/')}/_manifests"
            )
        )
        if not manifests:
            return {"status": "CRITICAL", "lag_hours": None, "last_manifest": None}

        latest = max(manifests, key=lambda f: f.last_modified)
        latest_dt = datetime.fromtimestamp(latest.last_modified / 1000, tz=timezone.utc)
        lag_hours = (datetime.now(tz=timezone.utc) - latest_dt).total_seconds() / 3600

        if lag_hours < 2:
            status = "OK"
        elif lag_hours < 6:
            status = "WARN"
        elif lag_hours < 24:
            status = "STALE"
        else:
            status = "CRITICAL"

        return {
            "status": status,
            "lag_hours": round(lag_hours, 2),
            "last_manifest": latest.name,
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
