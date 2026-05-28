"""
Crea (o verifica que existe) el Unity Catalog Volume de aterrizaje del Track A.

Idempotente: si el volume ya existe, no hace nada y reporta que está OK.

Uso:

    pip install -r infra/requirements.txt
    python infra/create_uc_volume.py

Variables requeridas en `.env` (raíz del repo):
    DATABRICKS_HOST           URL del workspace
    DATABRICKS_TOKEN          PAT con permiso de crear volumes en motoshop.bronze
    DATABRICKS_CATALOG        default: motoshop
    DATABRICKS_VOLUME_PATH    default: /Volumes/motoshop/bronze/_landing
                              (se usa para derivar catálogo/esquema/nombre)
"""

from __future__ import annotations

import os
import pathlib
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import ResourceAlreadyExists
from databricks.sdk.service.catalog import VolumeType
from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def parse_volume_path(volume_path: str) -> tuple[str, str, str]:
    """`/Volumes/motoshop/bronze/_landing` → (`motoshop`, `bronze`, `_landing`)."""
    parts = volume_path.strip("/").split("/")
    if len(parts) != 4 or parts[0] != "Volumes":
        raise ValueError(
            f"DATABRICKS_VOLUME_PATH debe tener la forma /Volumes/<catalog>/<schema>/<name>; "
            f"recibido: {volume_path!r}"
        )
    return parts[1], parts[2], parts[3]


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    host = os.getenv("DATABRICKS_HOST")
    token = os.getenv("DATABRICKS_TOKEN")
    if not host or not token:
        sys.stderr.write("[ERROR] DATABRICKS_HOST y DATABRICKS_TOKEN son obligatorios en .env\n")
        return 1

    volume_path = os.getenv("DATABRICKS_VOLUME_PATH", "/Volumes/motoshop/bronze/_landing")
    catalog, schema, name = parse_volume_path(volume_path)

    print(f"Workspace: {host}")
    print(f"Volume:    {catalog}.{schema}.{name}  (path: {volume_path})")

    w = WorkspaceClient(host=host, token=token)

    # Verificar que el esquema padre existe (sin crearlo — se hizo en F0).
    try:
        w.schemas.get(full_name=f"{catalog}.{schema}")
    except Exception as exc:
        sys.stderr.write(
            f"[ERROR] Esquema {catalog}.{schema} no existe o no es accesible: {exc}\n"
            "        Crearlo desde el Catalog Explorer antes de ejecutar este script.\n"
        )
        return 2

    try:
        vol = w.volumes.create(
            catalog_name=catalog,
            schema_name=schema,
            name=name,
            volume_type=VolumeType.MANAGED,
            comment="Staging de Parquet subidos por dump_to_cloud.py (Track A · F1).",
        )
        print(f"✓ Creado: {vol.full_name}")
    except ResourceAlreadyExists:
        existing = w.volumes.read(name=f"{catalog}.{schema}.{name}")
        print(f"✓ Ya existía: {existing.full_name} ({existing.volume_type.value})")

    # Sanity check: listar el volume (vacío al inicio está bien).
    listing = list(w.files.list_directory_contents(volume_path))
    print(f"  Archivos actualmente en el volume: {len(listing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
