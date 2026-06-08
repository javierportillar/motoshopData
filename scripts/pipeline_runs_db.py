#!/usr/bin/env python3
"""CLI helper para loguear pipeline runs a pipeline_runs.duckdb.

Uso:
    python scripts/pipeline_runs_db.py start-run --pipeline refresh_v15 --triggered-by scheduled
    python scripts/pipeline_runs_db.py start-step --run-id 1 --step-order 1 --step-name run_all
    python scripts/pipeline_runs_db.py complete-step --step-id 1 --duration 321 --status success
    python scripts/pipeline_runs_db.py complete-run --run-id 1 --duration 368 --status success
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

DB_PATH = Path("out/pipeline_runs.duckdb")


def _get_conn() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
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
    return con


def start_run(pipeline_name: str, triggered_by: str) -> None:
    con = _get_conn()
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM app_pipeline_runs").fetchone()[0]
    con.execute(
        "INSERT INTO app_pipeline_runs (id, pipeline_name, started_at, status, triggered_by) VALUES (?, ?, NOW(), 'running', ?)",
        [max_id, pipeline_name, triggered_by],
    )
    con.commit()
    con.close()
    print(max_id)  # stdout para que PS1 lo capture


def start_step(run_id: int, step_order: int, step_name: str) -> None:
    con = _get_conn()
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM app_pipeline_steps").fetchone()[0]
    con.execute(
        "INSERT INTO app_pipeline_steps (id, run_id, step_order, step_name, started_at, status) VALUES (?, ?, ?, ?, NOW(), 'running')",
        [max_id, run_id, step_order, step_name],
    )
    con.commit()
    con.close()
    print(max_id)


def _read_env(key: str, default: str = "") -> str:
    """Lee texto largo desde variable de entorno (para evitar quoting issues en PS)."""
    import os as _os
    return _os.environ.pop(key, default)


def complete_step(step_id: int, duration: float, status: str = "success",
                  log_excerpt: str = "", error_message: str = "") -> None:
    con = _get_conn()
    # Leer de env vars si PS las seteó (pueden contener espacios/newlines)
    log_excerpt = _read_env("PIPELINE_DB_LOG_EXCERPT", log_excerpt)
    error_message = _read_env("PIPELINE_DB_ERROR_MSG", error_message)
    safe_excerpt = log_excerpt[:8000] if log_excerpt else ""
    if error_message:
        con.execute(
            "UPDATE app_pipeline_steps SET finished_at=NOW(), status=?, duration_seconds=?, log_excerpt=?, error_message=? WHERE id=?",
            [status, int(duration), safe_excerpt, error_message, step_id],
        )
    else:
        con.execute(
            "UPDATE app_pipeline_steps SET finished_at=NOW(), status=?, duration_seconds=?, log_excerpt=? WHERE id=?",
            [status, int(duration), safe_excerpt, step_id],
        )
    con.commit()
    con.close()


def complete_run(run_id: int, duration: float, status: str = "success",
                 error_message: str = "") -> None:
    con = _get_conn()
    error_message = _read_env("PIPELINE_DB_ERROR_MSG", error_message)
    if error_message:
        con.execute(
            "UPDATE app_pipeline_runs SET finished_at=NOW(), status=?, duration_seconds=?, error_message=? WHERE id=?",
            [status, int(duration), error_message, run_id],
        )
    else:
        con.execute(
            "UPDATE app_pipeline_runs SET finished_at=NOW(), status=?, duration_seconds=? WHERE id=?",
            [status, int(duration), run_id],
        )
    con.commit()
    con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline runs DuckDB logger")
    sub = parser.add_subparsers(dest="command")

    p1 = sub.add_parser("start-run")
    p1.add_argument("--pipeline", required=True)
    p1.add_argument("--triggered-by", default="scheduled")

    p2 = sub.add_parser("start-step")
    p2.add_argument("--run-id", type=int, required=True)
    p2.add_argument("--step-order", type=int, required=True)
    p2.add_argument("--step-name", required=True)

    p3 = sub.add_parser("complete-step")
    p3.add_argument("--step-id", type=int, required=True)
    p3.add_argument("--duration", type=float, required=True)
    p3.add_argument("--status", default="success")
    p3.add_argument("--log-excerpt", default="")
    p3.add_argument("--error-message", default="")

    p4 = sub.add_parser("complete-run")
    p4.add_argument("--run-id", type=int, required=True)
    p4.add_argument("--duration", type=float, required=True)
    p4.add_argument("--status", default="success")
    p4.add_argument("--error-message", default="")

    args = parser.parse_args()

    if args.command == "start-run":
        start_run(args.pipeline, args.triggered_by)
    elif args.command == "start-step":
        start_step(args.run_id, args.step_order, args.step_name)
    elif args.command == "complete-step":
        complete_step(args.step_id, args.duration, args.status, args.log_excerpt, args.error_message)
    elif args.command == "complete-run":
        complete_run(args.run_id, args.duration, args.status, args.error_message)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
