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


def get_conn() -> duckdb.DuckDBPyConnection:
    """Obtiene conexión a pipeline_runs.duckdb (pública)."""
    return _get_conn()


def _get_conn() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Reintentar si el archivo está bloqueado por otro proceso (dump, etc.)
    import time
    for attempt in range(3):
        try:
            con = duckdb.connect(str(DB_PATH))
            return con
        except Exception as exc:
            if "locked" in str(exc).lower() or "used by another process" in str(exc).lower():
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, 2s
                    continue
            raise
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
    con.execute("""
        CREATE TABLE IF NOT EXISTS app_pipeline_table_stats (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            layer VARCHAR NOT NULL,
            table_name VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            max_date VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'ok',
            captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
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


def start_stats_run(pipeline_name: str = "run_all") -> int:
    """Crea un nuevo pipeline run para captura de stats. Retorna run_id."""
    con = _get_conn()
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM app_pipeline_runs").fetchone()[0]
    con.execute(
        "INSERT INTO app_pipeline_runs (id, pipeline_name, started_at, status, triggered_by) VALUES (?, ?, NOW(), 'running', ?)",
        [max_id, pipeline_name, "table-stats"],
    )
    con.commit()
    con.close()
    return max_id


def complete_stats_run(run_id: int, status: str = "success") -> None:
    """Marca un pipeline run como completado."""
    con = _get_conn()
    con.execute(
        "UPDATE app_pipeline_runs SET finished_at=NOW(), status=? WHERE id=?",
        [status, run_id],
    )
    con.commit()
    con.close()


# ── Detect date-like columns for max_date heuristic ────────────────────
_DATE_KEYWORDS = ["date", "fecha", "timestamp", "ts", "fecfven", "fecapa", "feccom"]


def capture_layer_stats(run_id: int, layer: str, gold_db_path: str) -> None:
    """Captura estadísticas de tablas de una capa (bronze/silver/gold).

    Lee las tablas del DuckDB principal y guarda row_count + max_date
    por tabla en app_pipeline_table_stats.
    """
    if not Path(gold_db_path).exists():
        print(f"  ⚠️  DuckDB not found: {gold_db_path}")
        return

    con_gold = duckdb.connect(gold_db_path, read_only=True)
    con_runs = _get_conn()

    # Determinar prefijos según la capa
    if layer == "bronze":
        prefixes = ("bronze_", "motoshop_bronze_")
    elif layer == "silver":
        prefixes = ("motoshop_silver_",)
    elif layer == "gold":
        prefixes = ("motoshop_gold_",)
    else:
        print(f"  ⚠️  Unknown layer: {layer}")
        con_gold.close()
        con_runs.close()
        return

    # Listar tablas del DuckDB principal
    tables = con_gold.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()

    matched = []
    for (tname,) in tables:
        for prefix in prefixes:
            if tname.startswith(prefix):
                matched.append((tname, prefix))
                break

    if not matched:
        print(f"  ⚠️  No {layer} tables found in {gold_db_path}")
        con_gold.close()
        con_runs.close()
        return

    for table_name, prefix in matched:
        try:
            row_count = con_gold.execute(
                f"SELECT COUNT(*) FROM \"{table_name}\""
            ).fetchone()[0]
        except Exception:
            row_count = -1

        # Heurística: buscar columna con fecha
        cols = con_gold.execute(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' AND table_schema = 'main'"
        ).fetchall()
        col_names = [c[0] for c in cols]

        max_date = None
        date_col = _find_date_column(col_names)
        if date_col:
            try:
                result = con_gold.execute(
                    f"SELECT MAX(\"{date_col}\") FROM \"{table_name}\""
                ).fetchone()[0]
                if result is not None:
                    max_date = str(result)[:19]  # ISO-ish
            except Exception:
                pass

        status = "ok"
        if row_count == 0:
            status = "empty"
        elif row_count < 0:
            status = "error"

        # Insert stats
        next_id = con_runs.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM app_pipeline_table_stats"
        ).fetchone()[0]
        con_runs.execute(
            "INSERT INTO app_pipeline_table_stats (id, run_id, layer, table_name, row_count, max_date, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [next_id, run_id, layer, table_name, row_count, max_date, status],
        )

        tab_short = table_name.replace(prefix, "") if row_count >= 0 else table_name
        print(f"    {tab_short:30s}  rows={row_count:>8}  max_date={max_date or 'N/A':19s}  {status}")

    con_runs.commit()
    con_gold.close()
    con_runs.close()


def _find_date_column(col_names: list[str]) -> str | None:
    """Encuentra la mejor columna candidata para max_date."""
    # Prioridad: business_date > columnas con keywords de fecha
    if "business_date" in col_names:
        return "business_date"
    if "fecha_documento_ts" in col_names:
        return "fecha_documento_ts"
    # Buscar por keyword
    for kw in _DATE_KEYWORDS:
        for c in col_names:
            if kw in c.lower():
                return c
    return None


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

    p5 = sub.add_parser("capture-layer-stats")
    p5.add_argument("--run-id", type=int, required=True)
    p5.add_argument("--layer", required=True, choices=["bronze", "silver", "gold"])
    p5.add_argument("--db-path", default="out/motoshop_gold.duckdb",
                    help="Path al DuckDB productivo")

    args = parser.parse_args()

    if args.command == "start-run":
        start_run(args.pipeline, args.triggered_by)
    elif args.command == "start-step":
        start_step(args.run_id, args.step_order, args.step_name)
    elif args.command == "complete-step":
        complete_step(args.step_id, args.duration, args.status, args.log_excerpt, args.error_message)
    elif args.command == "complete-run":
        complete_run(args.run_id, args.duration, args.status, args.error_message)
    elif args.command == "capture-layer-stats":
        capture_layer_stats(args.run_id, args.layer, args.db_path)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
