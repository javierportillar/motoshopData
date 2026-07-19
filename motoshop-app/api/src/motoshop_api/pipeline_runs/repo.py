"""PipelineRunsRepo — queries sobre app_pipeline_runs/steps vía DuckDB.

Lee de pipeline_runs.duckdb, descargado desde R2 si no existe localmente.
Mismo patrón que DuckDBMetricsRepo.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

from motoshop_api.metrics.repo_duckdb import (
    get_shared_connection,
    publish_duckdb_snapshot,
)

logger = logging.getLogger(__name__)

# V1.11: auto-refresh desde R2 (mismo patron que metrics/repo_duckdb.py).
# Throttle separado para no chocar con el de gold.duckdb.
_PIPELINE_R2_LAST_CHECK: dict[str, float] = {}
_PIPELINE_R2_CHECK_INTERVAL_SEC = 60

# V1.12: trackear el LastModified de R2 de la ULTIMA bajada por tenant.
# Ver explicacion en metrics/repo_duckdb.py: comparar contra mtime local
# se rompia cuando uploads sucedian poco despues del replace local.
_PIPELINE_R2_DOWNLOADED_MTIME: dict[str, float] = {}

# Ruta por defecto — /tmp en Render, out/ local (tenant-aware desde 2026-06-16)
def _default_db_path(tenant: str = "motoshop") -> Path:
    return Path(os.environ.get(
        "PIPELINE_RUNS_DB_PATH",
        f"/tmp/{tenant}_pipeline_runs.duckdb" if os.environ.get("ENV") == "prod"
        else f"out/{tenant}_pipeline_runs.duckdb",
    ))


def _ensure_db_exists(db_path: Path) -> None:
    """Crea pipeline_runs.duckdb con las tablas vacías si no existe."""
    if db_path.exists():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS app_pipeline_runs (
            id INTEGER PRIMARY KEY,
            pipeline_name VARCHAR NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            status VARCHAR NOT NULL,
            duration_seconds INTEGER,
            rows_processed INTEGER,
            triggered_by VARCHAR NOT NULL,
            error_message TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS app_pipeline_steps (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            step_order TINYINT NOT NULL,
            step_name VARCHAR NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            status VARCHAR NOT NULL,
            duration_seconds INTEGER,
            rows_processed INTEGER,
            log_excerpt TEXT,
            error_message TEXT,
            FOREIGN KEY (run_id) REFERENCES app_pipeline_runs(id)
        )
    """)
    con.close()
    logger.info("Created empty pipeline_runs.duckdb at %s", db_path)


def _bootstrap_pipeline_db_from_r2(db_path: Path, tenant: str = "motoshop") -> None:
    """Descarga {tenant}_pipeline_runs.duckdb desde R2 si:
       - no existe localmente, O
       - el de R2 es mas nuevo que el local (auto-refresh).

    Fallback a pipeline_runs.duckdb (legacy) si el tenant-specific no existe.

    V1.11: agregado auto-refresh con throttle (1/min/tenant). Antes el backend
    bajaba el archivo UNA VEZ al arranque y quedaba congelado hasta el siguiente
    deploy. El pipeline subia a R2 cada 2 min pero la API mostraba el snapshot
    viejo. Esto causaba que los runs nuevos no se vieran en /api/admin/pipeline.
    """
    r2_endpoint = os.environ.get("R2_ENDPOINT")
    r2_key = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    r2_bucket = os.environ.get("R2_BUCKET", "motoshop-gold")
    r2_object_key = f"{tenant}_pipeline_runs.duckdb"

    if not all([r2_endpoint, r2_key, r2_secret]):
        if not db_path.exists():
            logger.warning("R2 credentials not set; creating empty DB")
            _ensure_db_exists(db_path)
        return

    # Decidir si descargar:
    # 1) no existe local -> SIEMPRE descargar
    # 2) existe pero ya paso el throttle -> chequear R2 mtime
    must_download = not db_path.exists()
    if not must_download:
        from time import time
        last = _PIPELINE_R2_LAST_CHECK.get(tenant, 0)
        now = time()
        if now - last < _PIPELINE_R2_CHECK_INTERVAL_SEC:
            return  # dentro del throttle, no chequear
        _PIPELINE_R2_LAST_CHECK[tenant] = now

    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
            region_name="auto",
        )

        # Determinar qué key existe en R2 (tenant-aware o legacy)
        effective_key = r2_object_key
        r2_mtime = None
        if not must_download:
            from time import time
            # HEAD para comparar LastModified
            try:
                head = s3.head_object(Bucket=r2_bucket, Key=r2_object_key)
            except Exception:
                # Fallback a legacy
                try:
                    head = s3.head_object(Bucket=r2_bucket, Key="pipeline_runs.duckdb")
                    effective_key = "pipeline_runs.duckdb"
                except Exception as exc:
                    logger.debug("HEAD check failed for %s: %s", tenant, exc)
                    return
            r2_mtime = head['LastModified'].timestamp()
            last_downloaded = _PIPELINE_R2_DOWNLOADED_MTIME.get(tenant, 0)
            # V1.12: comparar contra r2_mtime de la ultima bajada, no contra
            # mtime local (que se actualiza con cada replace).
            if r2_mtime > last_downloaded:
                must_download = True
                logger.info(
                    "R2 has newer pipeline_runs for %s (R2=%.0fs ago, last_dl=%.0fs ago) — refreshing",
                    tenant,
                    (time() - r2_mtime),
                    (time() - last_downloaded) if last_downloaded else -1,
                )

        if must_download:
            logger.info("Downloading pipeline_runs.duckdb from R2: %s/%s", r2_bucket, effective_key)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            # Bajar a un .downloading y mover atomicamente
            tmp_path = db_path.with_suffix(db_path.suffix + ".downloading")
            try:
                s3.download_file(r2_bucket, effective_key, str(tmp_path))
            except Exception:
                # Si falla el tenant-aware, intentar legacy
                if effective_key == r2_object_key:
                    logger.warning("%s not found in R2, trying legacy pipeline_runs.duckdb", r2_object_key)
                    s3.download_file(r2_bucket, "pipeline_runs.duckdb", str(tmp_path))
                    effective_key = "pipeline_runs.duckdb"
                else:
                    raise
            # Si no teniamos r2_mtime (caso must_download = not db_path.exists())
            if r2_mtime is None:
                from time import time
                try:
                    head = s3.head_object(Bucket=r2_bucket, Key=effective_key)
                    r2_mtime = head['LastModified'].timestamp()
                except Exception:
                    r2_mtime = time()
            # Use the shared lease-aware publisher. Active readers finish on
            # the old snapshot; subsequent queries acquire the new generation.
            try:
                publish_duckdb_snapshot(tmp_path, db_path)
            except Exception as exc:
                logger.warning("Could not publish pipeline_runs snapshot: %s", exc)
                raise
            _PIPELINE_R2_DOWNLOADED_MTIME[tenant] = r2_mtime
            logger.info("pipeline_runs.duckdb refreshed to %s (r2_mtime=%.0f)", db_path, r2_mtime)
    except Exception as exc:
        logger.warning("Failed to refresh pipeline_runs.duckdb from R2: %s", exc)
        if not db_path.exists():
            _ensure_db_exists(db_path)


class PipelineRunsRepo:
    """Repo de solo lectura sobre app_pipeline_runs + app_pipeline_steps vía DuckDB.

    Tenant-aware desde 2026-06-16: cada tenant tiene su propio pipeline_runs.duckdb
    en R2 con key {tenant}_pipeline_runs.duckdb. Fallback al legacy sin prefijo.
    """

    def __init__(self, db_path: str | Path | None = None, tenant: str = "motoshop") -> None:
        self._tenant = tenant
        self._path = Path(db_path or _default_db_path(tenant))
        _bootstrap_pipeline_db_from_r2(self._path, tenant=tenant)
        self._con = get_shared_connection(self._path)
        logger.info("PipelineRunsRepo connected to %s", self._path)

    def list_runs(self, limit: int = 30, pipeline: str | None = None, status: str | None = None) -> list[dict]:
        params = []
        wheres = []
        if pipeline:
            wheres.append("pipeline_name = ?")
            params.append(pipeline)
        if status:
            wheres.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        params.append(limit)

        rows = self._con.execute(f"""
            SELECT id, pipeline_name, started_at, finished_at, status,
                   duration_seconds, rows_processed, triggered_by, error_message
            FROM app_pipeline_runs {where}
            ORDER BY started_at DESC LIMIT ?
        """, params).fetchall()
        cols = ["id", "pipeline_name", "started_at", "finished_at", "status",
                "duration_seconds", "rows_processed", "triggered_by", "error_message"]
        return [dict(zip(cols, row)) for row in rows]

    def get_run(self, run_id: int) -> dict | None:
        row = self._con.execute("""
            SELECT id, pipeline_name, started_at, finished_at, status,
                   duration_seconds, rows_processed, triggered_by, error_message
            FROM app_pipeline_runs WHERE id = ?
        """, [run_id]).fetchone()
        if not row:
            return None
        cols = ["id", "pipeline_name", "started_at", "finished_at", "status",
                "duration_seconds", "rows_processed", "triggered_by", "error_message"]
        run = dict(zip(cols, row))

        # Steps
        srows = self._con.execute("""
            SELECT id, run_id, step_order, step_name, started_at, finished_at,
                   status, duration_seconds, rows_processed, log_excerpt, error_message
            FROM app_pipeline_steps WHERE run_id = ? ORDER BY step_order
        """, [run_id]).fetchall()
        scols = ["id", "run_id", "step_order", "step_name", "started_at", "finished_at",
                 "status", "duration_seconds", "rows_processed", "log_excerpt", "error_message"]
        run["steps"] = [dict(zip(scols, sr)) for sr in srows]
        return run

    def get_summary(self) -> dict:
        totals = self._con.execute("""
            SELECT
                ROUND(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100, 1) AS success_rate,
                COALESCE(ROUND(AVG(duration_seconds), 0), 0) AS avg_duration,
                COUNT(*) AS total_runs
            FROM app_pipeline_runs
            WHERE started_at >= DATE_TRUNC('month', NOW()) - INTERVAL '30 days'
        """).fetchone()

        last = self._con.execute("""
            SELECT status, finished_at
            FROM app_pipeline_runs
            ORDER BY started_at DESC LIMIT 1
        """).fetchone()

        return {
            "success_rate_30d_pct": float(totals[0]) if totals and totals[0] else 0.0,
            "avg_duration_seconds": float(totals[1]) if totals and totals[1] else 0.0,
            "total_runs_30d": int(totals[2]) if totals and totals[2] else 0,
            "last_run_status": last[0] if last else None,
            "last_run_finished_at": str(last[1]) if last and last[1] else None,
        }

    def close(self) -> None:
        pass  # Connection is shared and managed globally in repo_duckdb
