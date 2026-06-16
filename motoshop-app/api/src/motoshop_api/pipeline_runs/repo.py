"""PipelineRunsRepo — queries sobre app_pipeline_runs/steps vía DuckDB.

Lee de pipeline_runs.duckdb, descargado desde R2 si no existe localmente.
Mismo patrón que DuckDBMetricsRepo.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

from motoshop_api.metrics.repo_duckdb import get_shared_connection

logger = logging.getLogger(__name__)

# Ruta por defecto — /tmp en Render, out/ local
_DEFAULT_DB_PATH = Path(os.environ.get(
    "PIPELINE_RUNS_DB_PATH",
    "/tmp/pipeline_runs.duckdb" if os.environ.get("ENV") == "prod" else "out/pipeline_runs.duckdb"
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


def _bootstrap_pipeline_db_from_r2(db_path: Path) -> None:
    """Descarga pipeline_runs.duckdb desde R2 si no existe localmente."""
    if db_path.exists():
        return

    r2_endpoint = os.environ.get("R2_ENDPOINT")
    r2_key = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    r2_bucket = os.environ.get("R2_BUCKET", "motoshop-gold")

    if not all([r2_endpoint, r2_key, r2_secret]):
        logger.warning("R2 credentials not set; creating empty DB")
        _ensure_db_exists(db_path)
        return

    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
            region_name="auto",
        )
        logger.info("Downloading pipeline_runs.duckdb from R2: %s/%s", r2_bucket, "pipeline_runs.duckdb")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(r2_bucket, "pipeline_runs.duckdb", str(db_path))
        logger.info("Pipeline runs DuckDB downloaded to %s", db_path)
    except Exception as exc:
        logger.warning("Failed to download pipeline_runs.duckdb from R2: %s — creating empty DB", exc)
        _ensure_db_exists(db_path)


class PipelineRunsRepo:
    """Repo de solo lectura sobre app_pipeline_runs + app_pipeline_steps vía DuckDB."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path or _DEFAULT_DB_PATH)
        _bootstrap_pipeline_db_from_r2(self._path)
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
