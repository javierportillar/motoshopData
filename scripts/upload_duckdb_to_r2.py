#!/usr/bin/env python3
"""Sube el DuckDB con embeddings a Cloudflare R2.

Uso:
    python scripts/upload_duckdb_to_r2.py

Requiere en .env (o entorno):
    R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

from __future__ import annotations

import os
import subprocess
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
#: Artefacto chico: sólo las tablas que el backend lee (~16 de ~175). Es lo que
#: descarga Render, para no bajar 50 MB y duplicar la memoria en cada refresco.
METRICS_DB_PATH = Path(os.environ.get("METRICS_DB_PATH", f"out/{TENANT}_metrics.duckdb"))
BUILD_METRICS_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "motoshop-app"
    / "api"
    / "scripts"
    / "build_metrics_duckdb.py"
)


def _upload_file(s3, local_path: Path, r2_key: str) -> None:
    if not local_path.exists():
        print(f"[SKIP] {local_path} no existe, saltando {r2_key}")
        return
    size_mb = local_path.stat().st_size / (1024 * 1024)
    print(f"Subiendo {local_path} ({size_mb:.0f} MB) -> s3://{R2_BUCKET}/{r2_key}")
    s3.upload_file(str(local_path), R2_BUCKET, r2_key)
    print(f"[OK] {r2_key}")


def _construir_artefacto_chico() -> Path | None:
    """Copia del gold sólo las tablas que el backend lee.

    Si falla, se sigue publicando el gold completo: el respaldo de la nube usa
    el artefacto si existe y, si no, el gold (con más memoria, pero funciona).
    """
    if not BUILD_METRICS_SCRIPT.exists():
        print(f"[SKIP] no existe {BUILD_METRICS_SCRIPT}")
        return None
    print(f"Construyendo artefacto chico: {METRICS_DB_PATH}")
    try:
        subprocess.run(
            [sys.executable, str(BUILD_METRICS_SCRIPT), str(DB_PATH), str(METRICS_DB_PATH)],
            check=True,
        )
        return METRICS_DB_PATH
    except Exception as exc:  # nunca romper el pipeline por esto
        print(f"[WARN] no se pudo construir el artefacto chico: {exc}")
        return None


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

    # Artefacto chico para el backend (Render lo prefiere con
    # R2_METRICS_ARTIFACT=1). Misma frescura, ~10x menos bytes y memoria.
    metrics_path = _construir_artefacto_chico()
    if metrics_path is not None:
        _upload_file(s3, metrics_path, f"{TENANT}_metrics.duckdb")
    # Pipeline runs: subir como tenant-specific + legacy para transición
    _upload_file(s3, PIPELINE_DB_PATH, f"{TENANT}_pipeline_runs.duckdb")
    _upload_file(s3, PIPELINE_DB_PATH, "pipeline_runs.duckdb")


if __name__ == "__main__":
    main()
