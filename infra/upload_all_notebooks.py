"""
Upload ALL notebooks (bronze, silver, gold) to Databricks Workspace.

Sube todo lo que los jobs necesitan para ejecutar en Databricks.
Usa la misma lógica de upload que run_gold_notebooks.py pero para los 3 layers.

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/upload_all_notebooks.py

Requiere: requests (pip install requests)
.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import time

try:
    import requests
except ImportError:
    print("❌ requests no instalado. Ejecutá: pip install requests")
    sys.exit(1)

# ─── Cargar .env manualmente si existe ──────────────────────────────────

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ─── Config ──────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
DEST_BASE = "/Repos/javierportillar/motoshopData/notebooks"

HEADERS = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 60

# Lenguaje de cada capa: bronze usa PySpark, silver/gold usan SQL puro
LAYER_LANGUAGE = {
    "bronze": "PYTHON",
    "silver": "SQL",
    "gold": "SQL",
}

LAYERS = {
    "bronze": {
        "local_dir": REPO_ROOT / "notebooks" / "bronze",
        "dest_dir": f"{DEST_BASE}/bronze",
        "language": "PYTHON",
    },
    "silver": {
        "local_dir": REPO_ROOT / "notebooks" / "silver",
        "dest_dir": f"{DEST_BASE}/silver",
        "language": "SQL",
    },
    "gold": {
        "local_dir": REPO_ROOT / "notebooks" / "gold",
        "dest_dir": f"{DEST_BASE}/gold",
        "language": "SQL",
    },
}

# ─── Helpers ─────────────────────────────────────────────────────────────


def api_post(endpoint: str, payload: dict, description: str = "") -> dict | None:
    url = f"{DATABRICKS_HOST}{endpoint}"
    try:
        resp = SESSION.post(url, json=payload, timeout=TIMEOUT)
        if resp.status_code in (200, 201, 202):
            return resp.json()
        else:
            print(f"  ❌ {description}: HTTP {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ {description}: {e}")
        return None


def ensure_directory(dir_path: str) -> bool:
    """Crea un directorio en Databricks si no existe."""
    resp = api_post("/api/2.0/workspace/mkdirs", {"path": dir_path}, f"mkdir {dir_path}")
    return resp is not None


def upload_notebook(local_path: pathlib.Path, dest_path: str, language: str = "SQL") -> bool:
    """Sube un notebook .py a Databricks vía API /api/2.0/workspace/import.

    Args:
        local_path: Path local del archivo.
        dest_path: Path destino en Databricks Workspace.
        language: "PYTHON" para notebooks con PySpark/dbutils, "SQL" para SQL puro.
    """
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "path": dest_path,
        "format": "SOURCE",
        "language": language,
        "content": content,
        "overwrite": True,
    }

    lang_label = "PY" if language == "PYTHON" else "SQL"
    resp = api_post("/api/2.0/workspace/import", payload, f"Upload {local_path.name} [{lang_label}]")
    return resp is not None


# ─── Main ─────────────────────────────────────────────────────────────────


def main():
    # ── Pre-flight ──
    if not DATABRICKS_HOST:
        print("❌ DATABRICKS_HOST no configurado en .env")
        sys.exit(1)
    if not DATABRICKS_TOKEN:
        print("❌ DATABRICKS_TOKEN no configurado en .env")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Destino base: {DEST_BASE}")
    print("=" * 60)

    total_uploaded = 0
    total_failed = 0

    for layer_name, layer_cfg in LAYERS.items():
        local_dir = layer_cfg["local_dir"]
        dest_dir = layer_cfg["dest_dir"]

        if not local_dir.exists():
            print(f"\n⚠️  {layer_name}: directorio {local_dir} no existe — skip")
            continue

        # Listar .py files ordenados
        files = sorted(local_dir.glob("*.py"))
        if not files:
            print(f"\n⚠️  {layer_name}: no hay archivos .py en {local_dir} — skip")
            continue

        print(f"\n── ▶ {layer_name.upper()} ({len(files)} notebooks) ──")

        # Crear directorio de destino
        if not ensure_directory(dest_dir):
            print(f"  ❌ No se pudo crear {dest_dir}")
            total_failed += len(files)
            continue

        # Subir cada notebook con su lenguaje correcto
        uploaded = 0
        failed = 0
        for f in files:
            dest_path = f"{dest_dir}/{f.name}"
            lang = layer_cfg.get("language", "SQL")
            if upload_notebook(f, dest_path, language=lang):
                uploaded += 1
            else:
                failed += 1

        print(f"  ✅ {layer_name}: {uploaded} subidos, {failed} fallos")
        total_uploaded += uploaded
        total_failed += failed

    # ── Resumen ──
    print(f"\n{'='*60}")
    print(f"  UPLOAD COMPLETADO")
    print(f"{'='*60}")
    print(f"  Total subidos: {total_uploaded}")
    print(f"  Fallos: {total_failed}")
    if total_failed == 0:
        print(f"  ✅ Todos los notebooks disponibles en el Workspace")
    else:
        print(f"  ⚠️  Revisar los fallos arriba")


if __name__ == "__main__":
    main()
