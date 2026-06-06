"""Helper para leer desde MySQL bronze. Si MySQL no está disponible,
usa los JSON exportados de Databricks como seed interino.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

STAGING_DIR = Path("_staging/parquet")


def _load_json_as_table(con: duckdb.DuckDBPyConnection, table_name: str, json_path: Path) -> bool:
    if not json_path.exists():
        return False
    rows = json.loads(json_path.read_text(encoding="utf-8"))
    if not rows:
        return False
    # Infer schema
    sample = rows[0]
    cols = []
    for k, v in sample.items():
        if isinstance(v, bool):
            t = "BOOLEAN"
        elif isinstance(v, int):
            t = "BIGINT"
        elif isinstance(v, float):
            t = "DOUBLE"
        else:
            t = "VARCHAR"
        cols.append(f'"{k}" {t}')
    schema = ", ".join(cols)
    con.execute(f"DROP TABLE IF EXISTS {table_name}")
    con.execute(f"CREATE TABLE {table_name} ({schema})")
    col_names = ", ".join([f'"{c}"' for c in sample.keys()])
    placeholders = ", ".join(["?"] * len(sample))
    stmt = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
    batch = []
    for r in rows:
        row_vals = []
        for c in sample.keys():
            v = r.get(c)
            if isinstance(v, str) and v.strip() == "":
                v = None
            row_vals.append(v)
        batch.append(row_vals)
        if len(batch) >= 1000:
            con.executemany(stmt, batch)
            batch = []
    if batch:
        con.executemany(stmt, batch)
    return True


def seed_from_exports(con: duckdb.DuckDBPyConnection) -> None:
    """Carga tablas bronze desde JSON exportados como seed interino."""
    seeds = [
        ("bronze_productos", "productos"),
        ("bronze_bodegas", "bodegas"),
        ("bronze_facventas", "facventas"),
        ("bronze_detfventas", "detfventas"),
    ]
    for target, source in seeds:
        path = STAGING_DIR / f"{source}.json"
        if path.exists():
            _load_json_as_table(con, target, path)
            print(f"  ✅ Seeded {target} from {path}")
        else:
            print(f"  ⚠️  Seed not found: {path}")


def get_mysql_connection():
    """Intenta conectar a MySQL. Devuelve None si no puede."""
    try:
        import pymysql
        conn = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", ""),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DATABASE", "motoshop2024"),
            charset="utf8",
            connect_timeout=5,
        )
        return conn
    except Exception:
        return None
