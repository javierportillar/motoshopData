"""Exporta tablas gold+silver desde Databricks a Parquet para seed local.

Ventana limitada: Databricks Free Edition puede perder Serverless Compute
en cualquier momento. Exportar todo lo que necesitemos para Sprint 2.

Credenciales via env vars: DATABRICKS_HOST, DATABRICKS_TOKEN
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient

OUTPUT_DIR = Path("_staging/parquet")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Tablas a exportar (gold marts + auxiliares + dims necesarias)
TABLES = [
    ("motoshop.gold.mart_ventas_diarias_sku", "mart_ventas_diarias_sku"),
    ("motoshop.gold.mart_inventario_actual", "mart_inventario_actual"),
    ("motoshop.gold.mart_rotacion_abc", "mart_rotacion_abc"),
    ("motoshop.gold.mart_cohortes_clientes", "mart_cohortes_clientes"),
    ("motoshop.gold.mart_productos_dormidos", "mart_productos_dormidos"),
    ("motoshop.gold.alertas_quiebre", "alertas_quiebre"),
    ("motoshop.gold.alertas_drift", "alertas_drift"),
    ("motoshop.gold.forecast_categoria", "forecast_categoria"),
    ("motoshop.gold.mart_rotacion_promedio", "mart_rotacion_promedio"),
    ("motoshop.gold.mart_abc_xyz", "mart_abc_xyz"),
    ("motoshop.silver.fact_ventas", "fact_ventas"),
    ("motoshop.silver.fact_ventas_detalle", "fact_ventas_detalle"),
    ("motoshop.silver.fact_compras", "fact_compras"),
    ("motoshop.silver.fact_compras_detalle", "fact_compras_detalle"),
    ("motoshop.silver.dim_bodega", "dim_bodega"),
    ("motoshop.silver.dim_producto", "dim_producto"),
]

WH_ID = "43bc044eaef4cca4"


def _query_all(w: WorkspaceClient, sql: str) -> list[dict]:
    result = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=WH_ID,
        wait_timeout="50s",
    )
    if result.status.state.name != "SUCCEEDED":
        raise RuntimeError(f"Query failed: {result.status.state.name}")
    cols = [c.name for c in result.manifest.schema.columns]
    all_rows = []
    total_chunks = result.manifest.total_chunk_count if hasattr(result.manifest, 'total_chunk_count') else 1
    for i in range(total_chunks):
        chunk = w.statement_execution.get_statement_result_chunk_n(result.statement_id, i)
        if chunk.data_array:
            all_rows.extend([dict(zip(cols, row)) for row in chunk.data_array])
    return all_rows


def export_table(w: WorkspaceClient, full_table: str, alias: str) -> dict:
    print(f"\n📦 Exportando {full_table} ...")
    rows = _query_all(w, f"SELECT * FROM {full_table}")
    count = len(rows)
    print(f"   Filas: {count}")

    out_path = OUTPUT_DIR / f"{alias}.json"
    out_path.write_text(json.dumps(rows, default=str, indent=2), encoding="utf-8")
    print(f"   Guardado: {out_path}")
    return {"alias": alias, "full_table": full_table, "rows": count, "path": str(out_path)}


def main():
    host = os.environ.get("DATABRICKS_HOST", "")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if not host or not token:
        print("❌ ERROR: DATABRICKS_HOST y DATABRICKS_TOKEN deben estar en env vars")
        return

    w = WorkspaceClient(host=host, token=token)
    results = []
    for full_table, alias in TABLES:
        try:
            meta = export_table(w, full_table, alias)
            results.append(meta)
        except Exception as e:
            print(f"   ❌ ERROR: {type(e).__name__}: {str(e)[:200]}")
            results.append({"alias": alias, "full_table": full_table, "error": str(e)[:200]})

    summary_path = OUTPUT_DIR / "_export_summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n✅ Resumen guardado en {summary_path}")
    ok = sum(1 for r in results if "error" not in r)
    print(f"Exportados: {ok}/{len(TABLES)}")


if __name__ == "__main__":
    main()
