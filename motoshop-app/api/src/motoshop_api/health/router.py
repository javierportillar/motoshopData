"""Health + data freshness endpoint.

Soporta dos backends:
- duckdb:   lee fecha de modificación del archivo DuckDB local
- databricks: consulta UC Volume via SDK (legacy)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from motoshop_api.config import settings

router = APIRouter(tags=["meta"])


def _get_db_path() -> Path:
    """Devuelve la ruta real del archivo DuckDB según config."""
    from motoshop_api.metrics.repo_duckdb import _make_db_path

    db_path = settings.duckdb_path or str(_make_db_path("motoshop"))
    return Path(db_path)


def _duckdb_freshness() -> dict:
    """Lag del archivo DuckDB local (R2 download freshness)."""
    db_path = _get_db_path()

    if not db_path.exists():
        return {"status": "CRITICAL", "error": f"DuckDB file not found at {db_path}"}

    try:
        mtime = db_path.stat().st_mtime
        file_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        lag_hours = (datetime.now(tz=timezone.utc) - file_dt).total_seconds() / 3600

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
            "backend": "duckdb",
            "lag_hours": round(lag_hours, 2),
            "file_mtime_utc": file_dt.isoformat(),
            "file_path": str(db_path),
            "file_size_bytes": db_path.stat().st_size,
        }
    except Exception as exc:
        return {"status": "ERROR", "backend": "duckdb", "error": str(exc)}


def _databricks_freshness() -> dict:
    """Lag del último manifest en UC Volume (Databricks)."""
    if not settings.databricks_host or not settings.databricks_token:
        return {"status": "ERROR", "backend": "databricks", "error": "Databricks credentials not configured"}

    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient(host=settings.databricks_host, token=settings.databricks_token)
        manifests = list(
            w.files.list_directory_contents(
                f"{settings.databricks_volume_path.rstrip('/')}/_manifests"
            )
        )
        if not manifests:
            return {"status": "CRITICAL", "backend": "databricks", "lag_hours": None, "last_manifest": None}

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
            "backend": "databricks",
            "lag_hours": round(lag_hours, 2),
            "last_manifest": latest.name,
        }
    except Exception as exc:
        return {"status": "ERROR", "backend": "databricks", "error": str(exc)}


@router.get("/health/data-freshness")
def data_freshness() -> dict:
    """Devuelve frescura de datos según el backend activo.

    - duckdb: lag desde la última descarga de R2 (mtime del archivo)
    - databricks: lag desde el último manifest en UC Volume
    """
    if settings.data_backend == "duckdb":
        return _duckdb_freshness()
    return _databricks_freshness()
