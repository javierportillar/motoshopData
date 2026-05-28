"""
Extracción local de tablas de `motoshop2024` (MySQL 5.0) a Parquet y subida
a un Unity Catalog Volume de Databricks.

Implementa la **Opción A** de [ADR-0005](../docs/decisions/0005-databricks-mysql-connectivity.md)
y la decisión de compute de [ADR-0010](../docs/decisions/0010-compute-databricks-free.md):
el cluster de Databricks NUNCA habla con MySQL; recibe Parquet por Volume.

Uso (manual):

    python -m venv .venv-infra
    source .venv-infra/bin/activate   # o .\\.venv-infra\\Scripts\\Activate.ps1 en Windows
    pip install -r infra/requirements.txt

    # Smoke test (1 tabla pequeña, sin subir a Databricks)
    python infra/dump_to_cloud.py --tables sucursales --dry-run

    # Smoke test completo (sube a UC Volume)
    python infra/dump_to_cloud.py --tables sucursales

    # Producción (las 12 tablas core de Fase 1)
    python infra/dump_to_cloud.py --tables-core

Variables de entorno requeridas (en .env de la raíz del repo):
    MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD
    DATABRICKS_HOST          (URL del workspace)
    DATABRICKS_TOKEN         (PAT)
    DATABRICKS_VOLUME_PATH   (default: /Volumes/motoshop/bronze/_landing)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from datetime import date

import mysql.connector
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

# Tablas core de Fase 1 (ver PLAN.md §7 y AGENT_PROMPT.md §7)
TABLES_CORE = [
    "facventas",
    "detfventas",
    "productos",
    "auxinventario",
    "bodegas",
    "terceros",
    "compras",
    "detcompras",
    "sucursales",
    "formapago",
    "subproduct",
    "preciosxpro",
]

# Filtros estándar a aplicar a tablas con `estdoc` (documentos activos).
# Si la tabla no tiene esa columna, el filtro se omite automáticamente.
ACTIVE_DOC_FILTER = "estdoc = 'A'"

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
STAGING_DIR = PROJECT_ROOT / "_staging"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dump_to_cloud")


@dataclass
class Config:
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    databricks_host: str
    databricks_token: str
    databricks_volume_path: str

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(PROJECT_ROOT / ".env")
        missing: list[str] = []

        def need(key: str, default: str | None = None) -> str:
            value = os.getenv(key, default)
            if value is None or value == "":
                missing.append(key)
                return ""
            return value

        cfg = cls(
            mysql_host=need("MYSQL_HOST", "localhost"),
            mysql_port=int(need("MYSQL_PORT", "3306")),
            mysql_database=need("MYSQL_DATABASE", "motoshop2024"),
            mysql_user=need("MYSQL_USER"),
            mysql_password=need("MYSQL_PASSWORD"),
            databricks_host=need("DATABRICKS_HOST"),
            databricks_token=need("DATABRICKS_TOKEN"),
            databricks_volume_path=need(
                "DATABRICKS_VOLUME_PATH",
                "/Volumes/motoshop/bronze/_landing",
            ),
        )
        if missing:
            raise SystemExit(
                f"[ERROR] Faltan variables en .env: {', '.join(missing)}"
            )
        return cfg


def open_connection(cfg: Config):
    """Conecta a MySQL con charset utf8 (MySQL 5.0 no soporta utf8mb4)."""
    return mysql.connector.connect(
        host=cfg.mysql_host,
        port=cfg.mysql_port,
        database=cfg.mysql_database,
        user=cfg.mysql_user,
        password=cfg.mysql_password,
        charset="utf8",
        use_unicode=True,
    )


def table_has_column(conn, table: str, column: str) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (conn.database, table, column),
    )
    (count,) = cursor.fetchone()
    cursor.close()
    return count > 0


def fetch_table(conn, table: str) -> tuple[list[str], list[tuple]]:
    """Lee la tabla completa. Filtra documentos activos si aplica."""
    where = ""
    if table_has_column(conn, table, "estdoc"):
        where = f" WHERE {ACTIVE_DOC_FILTER}"
        log.info(f"  · {table}: aplicando filtro {ACTIVE_DOC_FILTER}")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM `{table}`{where}")
    rows = cursor.fetchall()
    columns = [c[0] for c in cursor.description]
    cursor.close()
    return columns, rows


def write_parquet(
    table: str,
    columns: list[str],
    rows: list[tuple],
    ingest_date: str,
) -> pathlib.Path:
    """Escribe Parquet a `_staging/<tabla>/ingest_date=YYYY-MM-DD/part-0.parquet`."""
    out_dir = STAGING_DIR / table / f"ingest_date={ingest_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "part-0.parquet"

    # Convertir a strings los tipos que pyarrow no infiere bien desde MyISAM
    # (decimal -> str, datetime -> str ISO). Bronze guarda como string para
    # ser tolerante; silver hará el casteo formal.
    data = {col: [] for col in columns}
    for row in rows:
        for col, value in zip(columns, row):
            data[col].append(None if value is None else str(value))

    table_pa = pa.table(data)
    pq.write_table(table_pa, out_file, compression="snappy")
    return out_file


def upload_to_volume(local_file: pathlib.Path, table: str, ingest_date: str, cfg: Config) -> str:
    """Sube el Parquet al UC Volume vía Databricks SDK."""
    from databricks.sdk import WorkspaceClient

    remote_dir = f"{cfg.databricks_volume_path.rstrip('/')}/{table}/ingest_date={ingest_date}"
    remote_file = f"{remote_dir}/part-0.parquet"

    w = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token)
    # files.upload no crea directorios — los UC Volumes manejan rutas planas.
    with open(local_file, "rb") as fh:
        w.files.upload(file_path=remote_file, contents=fh, overwrite=True)
    return remote_file


def process_table(conn, table: str, ingest_date: str, cfg: Config, dry_run: bool) -> dict:
    t0 = time.time()
    log.info(f"→ {table}: extrayendo de MySQL...")
    columns, rows = fetch_table(conn, table)
    t1 = time.time()
    log.info(f"  · {len(rows):,} filas en {t1 - t0:.1f}s")

    local_file = write_parquet(table, columns, rows, ingest_date)
    t2 = time.time()
    size_kb = local_file.stat().st_size / 1024
    log.info(f"  · parquet local: {local_file.relative_to(PROJECT_ROOT)} ({size_kb:.1f} KB) en {t2 - t1:.1f}s")

    remote_path = None
    if not dry_run:
        remote_path = upload_to_volume(local_file, table, ingest_date, cfg)
        t3 = time.time()
        log.info(f"  · subido a {remote_path} en {t3 - t2:.1f}s")
    else:
        log.info("  · dry-run: NO se sube a Databricks")

    return {
        "table": table,
        "rows": len(rows),
        "columns": columns,
        "local_file": str(local_file),
        "remote_path": remote_path,
        "ingest_date": ingest_date,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--tables", nargs="+", help="Lista explícita de tablas")
    group.add_argument("--tables-core", action="store_true", help="Las 12 tablas core de F1")
    p.add_argument("--ingest-date", default=date.today().isoformat(), help="Fecha de ingesta (YYYY-MM-DD)")
    p.add_argument("--dry-run", action="store_true", help="No subir a Databricks; solo Parquet local")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = Config.from_env()
    tables = TABLES_CORE if args.tables_core else args.tables

    log.info(
        f"Origen:  {cfg.mysql_user}@{cfg.mysql_host}:{cfg.mysql_port}/{cfg.mysql_database}"
    )
    log.info(f"Destino: {cfg.databricks_volume_path}  (host {cfg.databricks_host})")
    log.info(f"Fecha:   {args.ingest_date}")
    log.info(f"Tablas:  {', '.join(tables)}")
    if args.dry_run:
        log.info("Modo:    DRY-RUN (sin subida)")

    STAGING_DIR.mkdir(exist_ok=True)
    conn = open_connection(cfg)

    summary = []
    t_start = time.time()
    try:
        for table in tables:
            try:
                result = process_table(conn, table, args.ingest_date, cfg, args.dry_run)
                summary.append(result)
            except Exception as exc:
                log.error(f"  ✗ {table}: {exc}")
                summary.append({"table": table, "error": str(exc)})
    finally:
        conn.close()

    t_total = time.time() - t_start
    log.info(f"\nResumen: {len(summary)} tablas en {t_total:.1f}s")

    # Manifiesto del run — útil para auditoría y para que el notebook bronze sepa qué leer.
    manifest_path = STAGING_DIR / f"manifest_{args.ingest_date}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ingest_date": args.ingest_date,
                "duration_seconds": round(t_total, 1),
                "tables": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info(f"Manifiesto: {manifest_path.relative_to(PROJECT_ROOT)}")

    return 0 if all("error" not in t for t in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
