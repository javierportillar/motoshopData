#!/usr/bin/env python3
"""Descarga el DuckDB gold desde Cloudflare R2.

Si el DuckDB no existe localmente, lo descarga desde R2.
Útil para recuperar el archivo si fue borrado del servidor.

Uso:
    python scripts/download_duckdb_from_r2.py

Requiere en entorno:
    R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (se leen de las mismas vars que upload)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_r2")

R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "https://4bd1502b7fa3f33d1d3c45ae2d252cfd.r2.cloudflarestorage.com")
R2_KEY = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "motoshop-gold")
DB_PATH = Path(os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb"))


def main() -> int:
    if not R2_KEY or not R2_SECRET:
        logger.error("R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY requeridas en entorno")
        return 1

    if DB_PATH.exists():
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        logger.info("DuckDB ya existe en %s (%.0f MB), nada que descargar", DB_PATH, size_mb)
        return 0

    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_KEY,
        aws_secret_access_key=R2_SECRET,
        region_name="auto",
    )

    r2_key = "motoshop_gold.duckdb"
    logger.info("Descargando s3://%s/%s -> %s", R2_BUCKET, r2_key, DB_PATH)

    try:
        # Verificar que existe
        s3.head_object(Bucket=R2_BUCKET, Key=r2_key)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            logger.error("El archivo %s no existe en el bucket R2", r2_key)
            logger.error("¿Se subió alguna vez? Corré el pipeline completo para crearlo.")
            return 1
        raise

    # Asegurar directorio
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Descargar
    s3.download_file(R2_BUCKET, r2_key, str(DB_PATH))

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    logger.info("Descarga completa: %s (%.0f MB)", DB_PATH, size_mb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
