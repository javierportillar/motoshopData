"""
Crea (o verifica) el SQL Warehouse Serverless de MotoShop con auto-stop ≤ 10 min.

Cumple la verificación crítica #4 de Fase 0 de forma reproducible (no depende
de clicks en la UI). Idempotente: si ya existe, valida la configuración y
reporta — no la sobreescribe.

Uso:

    pip install -r infra/requirements.txt
    python infra/create_sql_warehouse.py

Variables requeridas en `.env`:
    DATABRICKS_HOST
    DATABRICKS_TOKEN
    DATABRICKS_WAREHOUSE_NAME    default: motoshop-warehouse
"""

from __future__ import annotations

import os
import pathlib
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import (
    CreateWarehouseRequestWarehouseType,
    EndpointInfoWarehouseType,
)
from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

MAX_AUTO_STOP_MINUTES = 10


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    host = os.getenv("DATABRICKS_HOST")
    token = os.getenv("DATABRICKS_TOKEN")
    if not host or not token:
        sys.stderr.write("[ERROR] DATABRICKS_HOST y DATABRICKS_TOKEN son obligatorios en .env\n")
        return 1

    name = os.getenv("DATABRICKS_WAREHOUSE_NAME", "motoshop-warehouse")

    w = WorkspaceClient(host=host, token=token)

    # ¿Ya existe?
    existing = next(
        (wh for wh in w.warehouses.list() if wh.name == name),
        None,
    )

    if existing is not None:
        auto_stop = existing.auto_stop_mins or 0
        wh_type = existing.warehouse_type.value if existing.warehouse_type else "?"
        print(f"✓ Warehouse existe: {existing.name}  (id={existing.id}, type={wh_type})")
        print(f"  auto_stop_mins:    {auto_stop}")
        print(f"  state:             {existing.state}")
        if 0 < auto_stop <= MAX_AUTO_STOP_MINUTES:
            print(f"✅ Verificación crítica #4 OK (auto_stop_mins={auto_stop} ≤ {MAX_AUTO_STOP_MINUTES}).")
            return 0
        print(
            f"⚠️ auto_stop_mins={auto_stop} no cumple ≤ {MAX_AUTO_STOP_MINUTES}.\n"
            f"   Ajustar manualmente desde la UI (Edit warehouse → Auto stop).\n"
            f"   Este script NO modifica warehouses existentes para evitar sorpresas."
        )
        return 2

    # No existe: crear con la config objetivo.
    print(f"Creando warehouse {name!r} (Serverless, Starter, auto-stop {MAX_AUTO_STOP_MINUTES} min)...")
    created = w.warehouses.create(
        name=name,
        cluster_size="2X-Small",  # equivalente a "Starter" en la UI
        warehouse_type=CreateWarehouseRequestWarehouseType.PRO,
        enable_serverless_compute=True,
        auto_stop_mins=MAX_AUTO_STOP_MINUTES,
        channel=None,  # default = Current
    ).result()  # bloqueante hasta que arranca

    print(f"✓ Creado: {created.name}  (id={created.id})")
    print(f"✅ Verificación crítica #4 OK (auto_stop_mins={created.auto_stop_mins}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
