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
DB_PATH = Path(os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb"))

# ── Subir ───────────────────────────────────────────────────────────────

def main():
    if not R2_KEY or not R2_SECRET:
        print("ERROR: R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY requeridas en entorno.")
        print("Setéalas desde Render Dashboard → Environment Variables.")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"ERROR: DuckDB no encontrado en {DB_PATH}")
        print("Corré primero: python -m pipeline.run_all")
        sys.exit(1)

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"Subiendo {DB_PATH} ({size_mb:.0f} MB) -> s3://{R2_BUCKET}/motoshop_gold.duckdb")

    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_KEY,
        aws_secret_access_key=R2_SECRET,
        region_name="auto",
    )

    s3.upload_file(str(DB_PATH), R2_BUCKET, "motoshop_gold.duckdb")
    print("[OK] Upload exitoso. Render descargara el archivo en el proximo deploy.")


if __name__ == "__main__":
    main()
