"""
Crea un cluster Python en Databricks para ejecutar notebooks silver.

Uso:
    set -a && source .env && set +a
    python3 infra/create_silver_cluster.py
"""

from __future__ import annotations

import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("❌ pip install requests")
    sys.exit(1)

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")


def api(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{DATABRICKS_HOST}/api/2.0{path}"
    headers = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
    resp = requests.request(method, url, json=payload, headers=headers, timeout=60)
    if resp.status_code not in (200, 201):
        print(f"  ❌ {method} {path}: {resp.status_code}")
        print(f"     {resp.text[:300]}")
        sys.exit(1)
    return resp.json()


def main():
    if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
        print("❌ Configurá DATABRICKS_HOST y DATABRICKS_TOKEN en .env")
        sys.exit(1)

    CLUSTER_NAME = "motoshop-silver"
    print(f"Host: {DATABRICKS_HOST}")
    print(f"Cluster: {CLUSTER_NAME}")
    print("=" * 50)

    # Verificar conexión
    print("\n1. Verificando conexión...")
    api("GET", "/clusters/list")
    print("  ✅ Conexión OK")

    # Verificar si ya existe un cluster con ese nombre
    print("\n2. Buscando clusters existentes...")
    clusters = api("GET", "/clusters/list")
    existing = [c for c in clusters.get("clusters", []) if c["cluster_name"] == CLUSTER_NAME]

    if existing:
        c = existing[0]
        cluster_id = c["cluster_id"]
        state = c["state"]
        print(f"  ℹ️  Cluster ya existe: {cluster_id} (estado: {state})")

        if state in ("PENDING", "RUNNING"):
            print(f"  Ya está activo o arrancando. ID: {cluster_id}")
        else:
            print(f"  Arrancando...")
            api("POST", "/clusters/start", {"cluster_id": cluster_id})
            print(f"  ✅ Señal de inicio enviada")
    else:
        # Crear cluster
        print("\n3. Creando cluster...")
        payload = {
            "cluster_name": CLUSTER_NAME,
            "spark_version": "14.3.x-scala2.12",  # LTS estable
            "node_type_id": "i3.xlarge",  # 4 cores, 30 GB RAM - barato
            "num_workers": 0,  # Single-node (más barato)
            "autotermination_minutes": 15,
            "spark_conf": {
                "spark.master": "local[*]",
                "spark.databricks.cluster.profile": "singleNode",
                "singleNode": "true",
            },
            "custom_tags": {
                "project": "motoshop",
                "sprint": "F2-A",
            },
        }

        result = api("POST", "/clusters/create", payload)
        cluster_id = result["cluster_id"]
        print(f"  ✅ Cluster creado: {cluster_id}")

    # Esperar a que esté RUNNING
    print("\n4. Esperando cluster RUNNING...")
    for i in range(30):
        info = api("GET", f"/clusters/get?cluster_id={cluster_id}")
        state = info["state"]
        print(f"  [{i*10}s] Estado: {state}")
        if state == "RUNNING":
            print(f"  ✅ Cluster listo: {cluster_id}")
            break
        if state in ("ERROR", "TERMINATED"):
            print(f"  ❌ Cluster falló: {state}")
            sys.exit(1)
        time.sleep(10)
    else:
        print(f"  ⚠️ Timeout esperando cluster. Verificar en UI.")
        sys.exit(1)

    # Instalar librería chispa
    print("\n5. Instalando chispa...")
    lib_payload = {
        "cluster_id": cluster_id,
        "libraries": [
            {"pypi": {"package": "chispa>=0.10"}},
        ],
    }
    api("POST", "/libraries/install", lib_payload)
    print("  ✅ chispa instalado")

    # Esperar a que la librería se instale
    print("\n6. Verificando librerías...")
    time.sleep(5)
    libs = api("GET", f"/libraries/cluster-status?cluster_id={cluster_id}")
    for lib in libs.get("library_statuses", []):
        name = lib["library"].get("pypi", {}).get("package", "?")
        status = lib["status"]
        icon = "✅" if status == "INSTALLED" else "⏳"
        print(f"  {icon} {name}: {status}")

    # Resumen
    print(f"\n{'='*50}")
    print(f"  CLUSTER LISTO")
    print(f"{'='*50}")
    print(f"  ID:        {cluster_id}")
    print(f"  Nombre:    {CLUSTER_NAME}")
    print(f"  Runtime:   14.3.x (Python 3.11, Spark 3.5)")
    print(f"  Node:      i3.xlarge (single-node)")
    print(f"  Auto-stop: 15 min")
    print(f"  Libs:      chispa")
    print(f"\n  Para ejecutar notebooks:")
    print(f"  1. Abrí un notebook silver en Databricks")
    print(f"  2. Click derecha arriba → 'Attached to' → selecciona '{CLUSTER_NAME}'")
    print(f"  3. Run All")


if __name__ == "__main__":
    main()
