"""
Upload notebooks silver a Databricks Workspace vía REST API.

Uso:
    # 1. Crear .env en la raíz del repo con:
    #    DATABRICKS_HOST=https://dbc-e311b140-dab8.cloud.databricks.com
    #    DATABRICKS_TOKEN=tu_pat_aqui
    #
    # 2. Ejecutar:
    python infra/upload_silver_notebooks.py

Requiere: requests (ya en requirements.txt de infra)
"""

from __future__ import annotations

import base64
import os
import pathlib
import sys

try:
    import requests
except ImportError:
    print("❌ requests no instalado. Ejecutá: pip install requests")
    sys.exit(1)

# ─── Configuración ──────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SILVER_DIR = REPO_ROOT / "notebooks" / "silver"

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

# Destino en Databricks Workspace
# Nota: el prefijo /Workspace/ se agrega para la API, el path real es sin él
DEST_PATH = "/Repos/javierportillar/motoshopData/notebooks/silver"

# Archivos a subir (excluyendo _runs/, .gitkeep, __pycache__)
NOTEBOOK_PATTERNS = [
    "01_dim_producto.py",
    "02_dim_bodega.py",
    "03_dim_tercero.py",
    "04_dim_sucursal.py",
    "05_dim_formapago.py",
    "06_dim_tiempo.py",
    "10_fact_ventas.py",
    "11_fact_ventas_detalle.py",
    "12_fact_compras.py",
    "13_fact_compras_detalle.py",
    "14_fact_inventario.py",
    "20_quality_run.py",
    "30_validate_silver.py",
    "31_reconciliation.py",
]


def upload_notebook(host: str, token: str, local_path: pathlib.Path, dest_path: str) -> bool:
    """Sube un notebook .py a Databricks vía API."""
    url = f"{host}/api/2.0/workspace/import"

    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "path": dest_path,
        "format": "SOURCE",
        "language": "SQL",
        "content": content,
        "overwrite": True,
    }

    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    if resp.status_code == 200:
        print(f"  ✅ {local_path.name} → {dest_path}")
        return True
    else:
        print(f"  ❌ {local_path.name}: {resp.status_code} — {resp.text[:200]}")
        return False


def ensure_directory(host: str, token: str, dir_path: str) -> bool:
    """Crea un directorio en Databricks si no existe."""
    url = f"{host}/api/2.0/workspace/mkdirs"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(url, json={"path": dir_path}, headers=headers, timeout=15)
    return resp.status_code in (200, 409)  # 409 = ya existe


def main():
    if not DATABRICKS_HOST:
        print("❌ DATABRICKS_HOST no configurado. Agregá la variable de entorno.")
        print("   Ejemplo: export DATABRICKS_HOST=https://dbc-e311b140-dab8.cloud.databricks.com")
        sys.exit(1)

    if not DATABRICKS_TOKEN:
        print("❌ DATABRICKS_TOKEN no configurado. Agregá la variable de entorno.")
        print("   Ejemplo: export DATABRICKS_TOKEN=dapi...")
        print("\n   Para obtener tu PAT:")
        print("   1. Abrí tu workspace Databricks")
        print("   2. User Settings → Access Tokens → Generate New Token")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Destino: {DEST_PATH}")
    print(f"Archivos: {len(NOTEBOOK_PATTERNS)}")
    print("=" * 50)

    # Verificar conexión
    print("\n1. Verificando conexión...")
    try:
        resp = requests.get(
            f"{DATABRICKS_HOST}/api/2.0/workspace/list",
            params={"path": "/"},
            headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"},
            timeout=10,
        )
        if resp.status_code == 200:
            print("  ✅ Conexión exitosa")
        else:
            print(f"  ❌ Error de conexión: {resp.status_code} — {resp.text[:200]}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ No se pudo conectar: {e}")
        sys.exit(1)

    # Crear directorio destino
    print("\n2. Creando directorio destino...")
    ensure_directory(DATABRICKS_HOST, DATABRICKS_TOKEN, DEST_PATH)

    # Subir notebooks
    print("\n3. Subiendo notebooks...")
    success = 0
    failed = 0

    for filename in NOTEBOOK_PATTERNS:
        local_path = SILVER_DIR / filename
        if not local_path.exists():
            print(f"  ⚠️ {filename} no existe localmente — skip")
            failed += 1
            continue

        dest_file = f"{DEST_PATH}/{filename}"
        if upload_notebook(DATABRICKS_HOST, DATABRICKS_TOKEN, local_path, dest_file):
            success += 1
        else:
            failed += 1

    # Resumen
    print(f"\n{'='*50}")
    print(f"  RESUMEN UPLOAD")
    print(f"{'='*50}")
    print(f"  Subidos: {success}/{len(NOTEBOOK_PATTERNS)}")
    print(f"  Fallidos: {failed}")

    if success == len(NOTEBOOK_PATTERNS):
        print(f"\n  ✅ Todos los notebooks subidos a {DEST_PATH}")
        print(f"  Abrí Databricks → Workspace → Repos → motoshopdata → notebooks → silver")
    else:
        print(f"\n  ⚠️ Algunos notebooks fallaron. Revisar errores arriba.")


if __name__ == "__main__":
    main()
