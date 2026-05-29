"""
Execute fixed silver notebooks in Databricks SQL Warehouse (F3.5 hardening).

1. Extracts SQL cells from each notebook
2. Executes via REST API /api/2.0/sql/statements
3. Captures results as evidence in notebooks/silver/_runs/

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_silver_fix.py

Requiere: requests
.env debe tener DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

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

# ─── Cargar .env ──────────────────────────────────────────────────────────

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ─── Config ───────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SILVER_DIR = REPO_ROOT / "notebooks" / "silver"
RUNS_DIR = SILVER_DIR / "_runs"

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
WAREHOUSE_ID = "43bc044eaef4cca4"

# Notebooks a ejecutar (orden de dependencias)
EXECUTION_ORDER = [
    "10_fact_ventas.py",
    "11_fact_ventas_detalle.py",
    "12_fact_compras.py",
    "13_fact_compras_detalle.py",
    "14_fact_inventario.py",
    "20_quality_run.py",
    "31_reconciliation.py",
]

HEADERS = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 60

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
run_tag = f"silver_fix_{timestamp}"


# ─── Helpers ──────────────────────────────────────────────────────────────


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


def extract_sql_cells(notebook_path: pathlib.Path) -> list[dict]:
    """
    Extrae statements SQL individuales de un notebook .py estilo Databricks.
    """
    with open(notebook_path) as f:
        content = f.read()

    cells = re.split(r"\n-- COMMAND ----------\n", content)

    extracted = []
    global_line = 1

    for cell in cells:
        raw_lines = cell.split("\n")
        is_md = any(l.startswith("-- MAGIC %md") for l in raw_lines)

        if is_md:
            global_line += len(raw_lines) + 1
            continue

        stmt_buffer = []
        in_statement = False

        for line in raw_lines:
            stripped = line.strip()

            if stripped.startswith("-- MAGIC") or stripped.startswith("-- Databricks notebook source"):
                continue

            if in_statement:
                stmt_buffer.append(line)
                if stripped.rstrip().endswith(";"):
                    stmt = "\n".join(stmt_buffer).strip()
                    if stmt:
                        extracted.append({"type": "sql", "sql": stmt, "line_number": global_line})
                    stmt_buffer = []
                    in_statement = False
                continue

            if stripped.startswith("--"):
                continue
            if not stripped:
                continue

            stmt_buffer.append(line)
            if stripped.rstrip().endswith(";"):
                stmt = "\n".join(stmt_buffer).strip()
                if stmt:
                    extracted.append({"type": "sql", "sql": stmt, "line_number": global_line})
                stmt_buffer = []
                in_statement = False
            else:
                in_statement = True

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

    result = api_post(
        "/api/2.0/sql/statements",
        payload,
        f"{notebook_name} cell {cell_index}",
    )
    if result is None:
        return {"status": "FAIL", "error": "HTTP error", "data": []}

    statement_id = result.get("statement_id")
    status = result.get("status", {}).get("state", "UNKNOWN")

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

    if status == "SUCCEEDED":
        manifest = result.get("manifest", {})
        columns = [c["name"] for c in manifest.get("columns", [])]
        data = []
        for row in result.get("result", {}).get("data_array", []):
            data.append(row)
        row_count = manifest.get("total_row_count", len(data))
        return {"status": "OK", "columns": columns, "data": data, "row_count": row_count}
    elif status == "FAILED":
        error_obj = result.get("status", {}).get("error", {})
        error_msg = error_obj.get("message", "Unknown error")
        error_code = error_obj.get("error_code", "")
        if error_code:
            error_msg = f"[{error_code}] {error_msg}"
        return {"status": "FAIL", "error": error_msg, "data": []}
    else:
        return {"status": "TIMEOUT", "error": f"Status: {status}", "data": []}


# ─── Main ──────────────────────────────────────────────────────────────────


def main():
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

    # ── Execute notebooks ──
    print("\nEjecutando notebooks silver (F3.5 fix)...")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_log_path = RUNS_DIR / f"run_{run_tag}.md"

    all_results = {}
    global_ok = 0
    global_total = 0

    for nb_name in EXECUTION_ORDER:
        local_path = SILVER_DIR / nb_name
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

    # ── Write run log ──
    print(f"\nEscribiendo evidencia en {run_log_path}...")

    run_lines = [
        f"# Run Silver Fix (F3.5) — {run_tag}",
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
                    # Mostrar hasta 10 filas para resultados con datos reales
                    max_rows = 10 if len(cell_result["result"]["data"]) <= 10 else 5
                    for row in cell_result["result"]["data"][:max_rows]:
                        run_lines.append(f"   → {row}")
                    if len(cell_result["result"]["data"]) > max_rows:
                        run_lines.append(f"   → ... y {len(cell_result['result']['data']) - max_rows} más")
                elif cell_result["result"].get("row_count"):
                    run_lines.append(f"   → {cell_result['result']['row_count']} rows affected")
                if not cell_result["result"]["data"] and not cell_result["result"].get("row_count"):
                    run_lines.append("   → 0 rows")
            else:
                run_lines.append(f"   → ERROR: {cell_result['result'].get('error', 'unknown')[:200]}")

    run_log = "\n".join(run_lines)

    with open(run_log_path, "w") as f:
        f.write(run_log)

    print(f"  ✅ Evidencia escrita en {run_log_path}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  RUN SILVER FIX COMPLETADO")
    print(f"{'='*60}")
    all_pass = all(r["fail"] == 0 for r in all_results.values())
    if all_pass:
        print(f"  ✅ Todos los notebooks silver ejecutados exitosamente")
    else:
        print(f"  ❌ Algunos notebooks tienen errores. Revisar {run_log_path}")
    print(f"  OK: {global_ok}/{global_total}")
    print(f"  Evidencia: {run_log_path}")


if __name__ == "__main__":
    main()
