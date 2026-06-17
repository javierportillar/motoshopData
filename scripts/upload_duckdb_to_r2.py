#!/usr/bin/env python3
"""Sube el DuckDB con embeddings a Cloudflare R2.

Uso:
    python scripts/upload_duckdb_to_r2.py

Requiere en .env (o entorno):
    R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── R2 config desde entorno (mismas vars que Render) ────────────────────
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "https://4bd1502b7fa3f33d1d3c45ae2d252cfd.r2.cloudflarestorage.com")
R2_KEY = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "motoshop-gold")
TENANT = os.environ.get("TENANT", "motoshop")
DB_PATH = Path(os.environ.get("DUCKDB_PATH", f"out/{TENANT}_gold.duckdb"))
PIPELINE_DB_PATH = Path("out/pipeline_runs.duckdb")


def _upload_file(s3, local_path: Path, r2_key: str) -> None:
    if not local_path.exists():
        print(f"[SKIP] {local_path} no existe, saltando {r2_key}")
        return
    size_mb = local_path.stat().st_size / (1024 * 1024)
    print(f"Subiendo {local_path} ({size_mb:.0f} MB) -> s3://{R2_BUCKET}/{r2_key}")
    s3.upload_file(str(local_path), R2_BUCKET, r2_key)
    print(f"[OK] {r2_key}")


# ── Subir ───────────────────────────────────────────────────────────────

def main():
    if not R2_KEY or not R2_SECRET:
        print("ERROR: R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY requeridas en entorno.")
        print("Set eas from Render Dashboard > Environment Variables.")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"ERROR: DuckDB no encontrado en {DB_PATH}")
        print("Corré primero: python -m pipeline.run_all")
        sys.exit(1)

    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_KEY,
        aws_secret_access_key=R2_SECRET,
        region_name="auto",
    )

    _upload_file(s3, DB_PATH, f"{TENANT}_gold.duckdb")
    # Pipeline runs: subir como tenant-specific + legacy para transición
    _upload_file(s3, PIPELINE_DB_PATH, f"{TENANT}_pipeline_runs.duckdb")
    _upload_file(s3, PIPELINE_DB_PATH, "pipeline_runs.duckdb")


if __name__ == "__main__":
    main()
