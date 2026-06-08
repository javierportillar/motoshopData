"""PipelineRunsRepo — queries sobre app_pipeline_runs/steps vía MySQL writer.

Usa la conexión de escritura (app_writer) porque estas tablas están en MySQL Windows.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PipelineRunsRepo:
    """Repo de solo lectura sobre app_pipeline_runs + app_pipeline_steps."""

    def __init__(self, conn):
        """Recibe una conexión pymysql abierta (app_writer)."""
        self._conn = conn

    def list_runs(self, limit: int = 30, pipeline: str | None = None, status: str | None = None) -> list[dict]:
        params = []
        wheres = []
        if pipeline:
            wheres.append("pipeline_name = %s")
            params.append(pipeline)
        if status:
            wheres.append("status = %s")
            params.append(status)
        where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        params.append(limit)

        with self._conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, pipeline_name, started_at, finished_at, status,
                       duration_seconds, rows_processed, triggered_by, error_message
                FROM app_pipeline_runs {where}
                ORDER BY started_at DESC LIMIT %s
            """, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    def get_run(self, run_id: int) -> dict | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, pipeline_name, started_at, finished_at, status, duration_seconds, rows_processed, triggered_by, error_message FROM app_pipeline_runs WHERE id = %s",
                [run_id],
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            run = dict(zip(cols, row))

            # Steps
            cur.execute(
                "SELECT id, run_id, step_order, step_name, started_at, finished_at, status, duration_seconds, rows_processed, log_excerpt, error_message FROM app_pipeline_steps WHERE run_id = %s ORDER BY step_order",
                [run_id],
            )
            srows = cur.fetchall()
            scols = [d[0] for d in cur.description]
            run["steps"] = [dict(zip(scols, sr)) for sr in srows]
            return run

    def get_summary(self) -> dict:
        with self._conn.cursor() as cur:
            # Success rate últimos 30 días
            cur.execute("""
                SELECT
                    ROUND(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100, 1) AS success_rate,
                    COALESCE(ROUND(AVG(duration_seconds), 0), 0) AS avg_duration,
                    COUNT(*) AS total_runs
                FROM app_pipeline_runs
                WHERE started_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            totals = cur.fetchone()

            # Último run
            cur.execute("""
                SELECT status, finished_at
                FROM app_pipeline_runs
                ORDER BY started_at DESC LIMIT 1
            """)
            last = cur.fetchone()

        return {
            "success_rate_30d_pct": float(totals[0]) if totals and totals[0] else 0.0,
            "avg_duration_seconds": float(totals[1]) if totals and totals[1] else 0.0,
            "total_runs_30d": int(totals[2]) if totals and totals[2] else 0,
            "last_run_status": last[0] if last else None,
            "last_run_finished_at": last[1] if last else None,
        }
