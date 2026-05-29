"""
Upload and execute gold notebooks in Databricks SQL Warehouse.

1. Uploads notebooks to Databricks Workspace
2. Starts SQL Warehouse if needed
3. Extracts SQL cells from each notebook
4. Executes via REST API /api/2.0/sql/statements
5. Captures results as evidence in notebooks/gold/_runs/

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_gold_notebooks.py

Requiere: requests (pip install requests)
.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

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
GOLD_DIR = REPO_ROOT / "notebooks" / "gold"
RUNS_DIR = GOLD_DIR / "_runs"

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
WAREHOUSE_ID = "43bc044eaef4cca4"

DEST_PATH = "/Repos/javierportillar/motoshopData/notebooks/gold"

# Notebooks a subir (marts 10-14 + quality 20 + validate 30)
NOTEBOOKS = [
    "10_mart_ventas_diarias_sku.py",
    "11_mart_inventario_actual.py",
    "12_mart_rotacion_abc.py",
    "13_mart_cohortes_clientes.py",
    "14_mart_productos_dormidos.py",
    "20_quality_gold.py",
    "30_validate_gold.py",
]

# Notebooks a ejecutar (orden: marts → quality → validate)
EXECUTION_ORDER = [
    "10_mart_ventas_diarias_sku.py",
    "11_mart_inventario_actual.py",
    "12_mart_rotacion_abc.py",
    "13_mart_cohortes_clientes.py",
    "14_mart_productos_dormidos.py",
    "20_quality_gold.py",
    "30_validate_gold.py",
]

HEADERS = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 60

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
run_tag = f"gold_{timestamp}"

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


def api_get(endpoint: str, description: str = "") -> dict | None:
    url = f"{DATABRICKS_HOST}{endpoint}"
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  ❌ {description}: HTTP {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ {description}: {e}")
        return None


def upload_notebook(local_path: pathlib.Path, dest_path: str) -> bool:
    """Sube un notebook .py a Databricks vía API /api/2.0/workspace/import."""
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "path": dest_path,
        "format": "SOURCE",
        "language": "SQL",
        "content": content,
        "overwrite": True,
    }

    resp = api_post("/api/2.0/workspace/import", payload, f"Upload {local_path.name}")
    if resp is not None:
        print(f"  ✅ {local_path.name} → {dest_path}")
        return True
    return False


def ensure_directory(dir_path: str) -> bool:
    """Crea un directorio en Databricks si no existe."""
    resp = api_post("/api/2.0/workspace/mkdirs", {"path": dir_path}, f"mkdir {dir_path}")
    return resp is not None


def start_warehouse() -> bool:
    """Arranca el SQL Warehouse si está detenido."""
    status = api_get(
        f"/api/2.0/sql/warehouses/{WAREHOUSE_ID}",
        f"Check warehouse {WAREHOUSE_ID}",
    )
    if status is None:
        return False

    state = status.get("state", "UNKNOWN")
    print(f"  🟡 Warehouse state: {state}")

    if state == "RUNNING":
        print("  ✅ Warehouse ya está RUNNING")
        return True

    if state in ("STARTING", "STOPPING"):
        print("  ⏳ Warehouse está en transición, esperando...")
        return _wait_for_warehouse_ready()

    # Intentar arrancar
    print("  🟢 Arrancando Warehouse...")
    resp = api_post(
        f"/api/2.0/sql/warehouses/{WAREHOUSE_ID}/start",
        {},
        "Start warehouse",
    )
    if resp is None:
        return False

    return _wait_for_warehouse_ready()


def _wait_for_warehouse_ready(max_attempts: int = 30, delay: int = 10) -> bool:
    """Espera a que el warehouse esté RUNNING."""
    for attempt in range(1, max_attempts + 1):
        time.sleep(delay)
        status = api_get(
            f"/api/2.0/sql/warehouses/{WAREHOUSE_ID}",
            f"Check warehouse (attempt {attempt})",
        )
        if status is None:
            continue
        state = status.get("state", "UNKNOWN")
        if state == "RUNNING":
            print(f"  ✅ Warehouse RUNNING (attempt {attempt})")
            return True
        print(f"  ⏳ Warehouse state: {state} (attempt {attempt}/{max_attempts})")
    print("  ❌ Warehouse no arrancó después de", max_attempts * delay, "segundos")
    return False


def extract_sql_cells(notebook_path: pathlib.Path) -> list[dict]:
    """
    Extrae statements SQL individuales de un notebook .py estilo Databricks.

    Itera línea por línea:
    - Salta líneas -- MAGIC, -- Databricks notebook source
    - Acumula líneas en un buffer
    - Cuando encuentra un ; al final de una línea no-comentario, emite el statement
    - Salta líneas de comentario -- que están solas (entre statements)

    Cada statement se ejecuta individualmente (la API /sql/statements solo
    acepta una sentencia por llamada).

    Returns lista de dicts con {type, sql, line_number}.
    """
    with open(notebook_path) as f:
        content = f.read()

    # Split por separadores de celda
    cells = re.split(r"\n-- COMMAND ----------\n", content)

    extracted = []
    # Rastreamos línea global aproximada
    global_line = 1

    for cell in cells:
        raw_lines = cell.split("\n")
        is_md = any(l.startswith("-- MAGIC %md") for l in raw_lines)

        if is_md:
            global_line += len(raw_lines) + 1
            continue

        # Acumulador de statement actual
        stmt_buffer = []
        in_statement = False

        for line in raw_lines:
            stripped = line.strip()

            # Saltar metadata
            if stripped.startswith("-- MAGIC") or stripped.startswith("-- Databricks notebook source"):
                continue

            # Si estamos en un statement
            if in_statement:
                stmt_buffer.append(line)
                # Si la línea termina con ; (sin contar espacios), cerramos el statement
                if stripped.rstrip().endswith(";"):
                    stmt = "\n".join(stmt_buffer).strip()
                    if stmt:
                        extracted.append({"type": "sql", "sql": stmt, "line_number": global_line})
                    stmt_buffer = []
                    in_statement = False
                continue

            # No estamos en un statement actualmente

            # Si es línea comentario -- (no MAGIC), la saltamos
            if stripped.startswith("--"):
                continue

            # Si es línea en blanco, saltar
            if not stripped:
                continue

            # Es inicio de un nuevo statement
            stmt_buffer.append(line)
            if stripped.rstrip().endswith(";"):
                # Statement completo en una línea
                stmt = "\n".join(stmt_buffer).strip()
                if stmt:
                    extracted.append({"type": "sql", "sql": stmt, "line_number": global_line})
                stmt_buffer = []
                in_statement = False
            else:
                in_statement = True

        # Si quedó algo sin ; (posible DDL sin punto y coma), emitirlo igual
        if stmt_buffer:
            stmt = "\n".join(stmt_buffer).strip()
            if stmt and not stmt.startswith("--"):
                if not stmt.endswith(";"):
                    stmt += ";"
                extracted.append({"type": "sql", "sql": stmt, "line_number": global_line})

        global_line += len(raw_lines) + 1

    return extracted


def execute_sql(sql: str, notebook_name: str, cell_index: int) -> dict:
    """Ejecuta SQL via /api/2.0/sql/statements y espera resultado."""
    payload = {
        "statement": sql,
        "warehouse_id": WAREHOUSE_ID,
        "wait_timeout": "50s",
        "on_wait_timeout": "CONTINUE",
    }

    # Iniciar ejecución
    result = api_post(
        "/api/2.0/sql/statements",
        payload,
        f"{notebook_name} cell {cell_index}",
    )
    if result is None:
        return {"status": "FAIL", "error": "HTTP error", "data": []}

    statement_id = result.get("statement_id")
    status = result.get("status", {}).get("state", "UNKNOWN")

    # Si timeout, poll
    if status == "PENDING" and statement_id:
        for _ in range(30):
            time.sleep(2)
            poll = api_get(
                f"/api/2.0/sql/statements/{statement_id}",
                f"Poll {notebook_name} cell {cell_index}",
            )
            if poll is None:
                break
            poll_status = poll.get("status", {}).get("state", "UNKNOWN")
            if poll_status in ("SUCCEEDED", "FAILED", "CANCELED"):
                result = poll
                status = poll_status
                break
            if poll_status == "RUNNING":
                continue

    # Parsear resultado
    if status == "SUCCEEDED":
        manifest = result.get("manifest", {})
        columns = [c["name"] for c in manifest.get("columns", [])]
        data = []
        for row in result.get("result", {}).get("data_array", []):
            data.append(row)

        # Obtener row count de manifest
        row_count = manifest.get("total_row_count", len(data))

        return {
            "status": "OK",
            "columns": columns,
            "data": data,
            "row_count": row_count,
        }
    elif status == "FAILED":
        # Capturar mensaje de error completo
        error_obj = result.get("status", {}).get("error", {})
        error_msg = error_obj.get("message", "Unknown error")
        error_code = error_obj.get("error_code", "")
        if error_code:
            error_msg = f"[{error_code}] {error_msg}"
        return {"status": "FAIL", "error": error_msg, "data": []}
    else:
        return {"status": "TIMEOUT", "error": f"Status: {status}", "data": []}


def is_ddl_or_dml(sql: str) -> bool:
    """Detecta si una sentencia es DDL/DML (no SELECT)."""
    upper = sql.strip().upper()
    return any(
        upper.startswith(kw)
        for kw in ["CREATE", "DELETE", "INSERT", "DROP", "ALTER", "TRUNCATE"]
    )


# ─── Main ─────────────────────────────────────────────────────────────────


def main():
    # ── Pre-flight checks ──
    if not DATABRICKS_HOST:
        print("❌ DATABRICKS_HOST no configurado en .env")
        sys.exit(1)
    if not DATABRICKS_TOKEN:
        print("❌ DATABRICKS_TOKEN no configurado en .env")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Warehouse: {WAREHOUSE_ID}")
    print(f"Run tag: {run_tag}")
    print("=" * 60)

    # ── Step 1: Upload notebooks to Workspace ──
    print("\n1. Subiendo notebooks gold a Databricks Workspace...")
    ensure_directory(DEST_PATH)
    uploaded = 0
    failed_upload = 0
    for nb in NOTEBOOKS:
        local_path = GOLD_DIR / nb
        if not local_path.exists():
            print(f"  ⚠️ {nb} no existe — skip")
            failed_upload += 1
            continue
        dest_file = f"{DEST_PATH}/{nb}"
        if upload_notebook(local_path, dest_file):
            uploaded += 1
        else:
            failed_upload += 1
    print(f"  Uploaded: {uploaded}/{len(NOTEBOOKS)}, Failed: {failed_upload}")

    # ── Step 2: Start SQL Warehouse ──
    print("\n2. Verificando/arrancando SQL Warehouse...")
    if not start_warehouse():
        print("❌ No se pudo arrancar el Warehouse. Abortando.")
        sys.exit(1)

    # ── Step 3: Execute notebooks ──
    print("\n3. Ejecutando notebooks gold...")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_log_path = RUNS_DIR / f"run_{run_tag}.md"

    all_results = {}
    global_ok = 0
    global_total = 0

    for nb_name in EXECUTION_ORDER:
        local_path = GOLD_DIR / nb_name
        if not local_path.exists():
            print(f"\n  ⚠️ {nb_name} no existe — skip")
            continue

        print(f"\n  ── ▶ {nb_name} ──")

        cells = extract_sql_cells(local_path)
        sql_cells = [c for c in cells if c["type"] == "sql"]

        nb_results = []
        cell_ok = 0
        cell_fail = 0

        for idx, cell in enumerate(sql_cells):
            sql = cell["sql"]
            preview = sql.strip()[:80].replace("\n", " ")
            print(f"    Cell {idx + 1}/{len(sql_cells)}: {preview}...")

            result = execute_sql(sql, nb_name, idx + 1)

            if result["status"] == "OK":
                status_icon = "✅"
                cell_ok += 1
            else:
                status_icon = "❌"
                cell_fail += 1

            detail = f"    {status_icon} → {result['status']}"
            if result.get("row_count") is not None and result["status"] == "OK":
                detail += f" | {result['row_count']} rows"
            if result.get("error"):
                detail += f" | {result['error'][:100]}"
            print(detail)

            nb_results.append({
                "cell": idx + 1,
                "sql": sql.strip(),
                "result": result,
            })

        nb_status = "✅" if cell_fail == 0 else "❌"
        print(f"  {nb_status} {nb_name}: {cell_ok}/{len(sql_cells)} OK, {cell_fail} fail")
        all_results[nb_name] = {
            "total": len(sql_cells),
            "ok": cell_ok,
            "fail": cell_fail,
            "cells": nb_results,
        }
        global_ok += cell_ok
        global_total += len(sql_cells)

    # ── Step 4: Write run log ──
    print(f"\n4. Escribiendo evidencia en {run_log_path}...")

    run_lines = [
        f"# Run Gold Notebooks — {run_tag}",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}",
        f"Warehouse: {WAREHOUSE_ID}",
        "",
        "## Resumen",
        "",
    ]

    for nb_name in EXECUTION_ORDER:
        if nb_name in all_results:
            r = all_results[nb_name]
            icon = "✅" if r["fail"] == 0 else "❌"
            run_lines.append(
                f"| {icon} {nb_name} | {r['ok']}/{r['total']} OK | {r['fail']} fail |"
            )

    run_lines.append(f"\n**Total:** {global_ok}/{global_total} OK\n")

    for nb_name in EXECUTION_ORDER:
        if nb_name not in all_results:
            continue

        run_lines.append(f"\n## {nb_name}\n")
        for cell_result in all_results[nb_name]["cells"]:
            sql_preview = cell_result["sql"][:200].replace("\n", " ")
            icon = "✅" if cell_result["result"]["status"] == "OK" else "❌"
            run_lines.append(f"{icon} {sql_preview}")
            if cell_result["result"]["status"] == "OK":
                if cell_result["result"]["data"]:
                    for row in cell_result["result"]["data"][:5]:  # max 5 rows
                        run_lines.append(f"   → {row}")
                elif cell_result["result"].get("row_count"):
                    run_lines.append(f"   → {cell_result['result']['row_count']} rows affected")
                # Si es SELECT con columnas pero sin data (0 rows), mostrar igual
                if not cell_result["result"]["data"] and not cell_result["result"].get("row_count"):
                    run_lines.append(f"   → 0 rows")
            else:
                run_lines.append(f"   → ERROR: {cell_result['result'].get('error', 'unknown')[:200]}")

    run_log = "\n".join(run_lines)

    with open(run_log_path, "w") as f:
        f.write(run_log)

    print(f"  ✅ Evidencia escrita en {run_log_path}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  RUN GOLD COMPLETADO")
    print(f"{'='*60}")
    all_pass = all(r["fail"] == 0 for r in all_results.values())
    if all_pass:
        print(f"  ✅ Todos los notebooks gold ejecutados exitosamente")
    else:
        print(f"  ❌ Algunos notebooks tienen errores. Revisar {run_log_path}")
    print(f"  OK: {global_ok}/{global_total}")
    print(f"  Evidencia: {run_log_path}")


if __name__ == "__main__":
    main()
