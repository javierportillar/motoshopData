"""Construye out/motoshop_gold.duckdb desde JSON exportados de Databricks.

Obtiene los tipos reales de Databricks via DESCRIBE para garantizar compatibilidad.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
from databricks.sdk import WorkspaceClient

INPUT_DIR = Path("_staging/parquet")
OUTPUT_PATH = Path("out/motoshop_gold.duckdb")

WH_ID = "43bc044eaef4cca4"
HOST = os.environ.get("DATABRICKS_HOST", "")
TOKEN = os.environ.get("DATABRICKS_TOKEN", "")

TABLES = [
    ("motoshop.gold.mart_ventas_diarias_sku", "gold_mart_ventas_diarias_sku"),
    ("motoshop.gold.mart_inventario_actual", "gold_mart_inventario_actual"),
    ("motoshop.gold.mart_rotacion_abc", "gold_mart_rotacion_abc"),
    ("motoshop.gold.mart_cohortes_clientes", "gold_mart_cohortes_clientes"),
    ("motoshop.gold.mart_productos_dormidos", "gold_mart_productos_dormidos"),
    ("motoshop.gold.alertas_quiebre", "gold_alertas_quiebre"),
    ("motoshop.gold.alertas_drift", "gold_alertas_drift"),
    ("motoshop.gold.forecast_categoria", "gold_forecast_categoria"),
    ("motoshop.gold.mart_abc_xyz", "gold_mart_abc_xyz"),
    ("motoshop.silver.fact_ventas", "silver_fact_ventas"),
    ("motoshop.silver.fact_ventas_detalle", "silver_fact_ventas_detalle"),
    ("motoshop.silver.fact_compras", "silver_fact_compras"),
    ("motoshop.silver.fact_compras_detalle", "silver_fact_compras_detalle"),
    ("motoshop.silver.dim_bodega", "silver_dim_bodega"),
    ("motoshop.silver.dim_producto", "silver_dim_producto"),
]

_TYPE_MAP = {
    "string": "VARCHAR",
    "varchar": "VARCHAR",
    "int": "BIGINT",
    "integer": "BIGINT",
    "bigint": "BIGINT",
    "double": "DOUBLE",
    "float": "DOUBLE",
    "decimal": "DECIMAL(18,2)",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "boolean": "BOOLEAN",
}


def _get_schema(w: WorkspaceClient, full_table: str) -> list[tuple[str, str]]:
    result = w.statement_execution.execute_statement(
        statement=f"DESCRIBE {full_table}",
        warehouse_id=WH_ID,
        wait_timeout="50s",
    )
    cols = [c.name for c in result.manifest.schema.columns]
    schema = []
    for i in range(result.manifest.total_chunk_count):
        chunk = w.statement_execution.get_statement_result_chunk_n(result.statement_id, i)
        if chunk.data_array:
            for row in chunk.data_array:
                d = dict(zip(cols, row))
                col_name = d["col_name"]
                data_type = d["data_type"]
                # Solo columnas reales, parar en metadata
                if col_name.startswith("#") or data_type is None:
                    break
                duck_type = _TYPE_MAP.get(data_type.lower(), "VARCHAR")
                schema.append((col_name, duck_type))
    return schema


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


def build_from_databricks(duckdb_path: str | Path) -> str:
    w = WorkspaceClient(host=HOST, token=TOKEN)
    con = duckdb.connect(str(duckdb_path))
    total_rows = 0

    for full_table, alias in TABLES:
        # El nombre del archivo json usa el nombre corto (sin prefijo gold_/silver_)
        short_name = alias.replace("gold_", "").replace("silver_", "")
        json_path = INPUT_DIR / f"{short_name}.json"

        if not json_path.exists():
            print(f"  ⚠️  SKIP {alias}: JSON no encontrado")
            continue

        rows = json.loads(json_path.read_text(encoding="utf-8"))
        count = len(rows)
        if count == 0:
            print(f"  ⚠️  SKIP {alias}: 0 filas")
            continue

        # Obtener schema real de Databricks
        try:
            schema = _get_schema(w, full_table)
        except Exception as e:
            print(f"  ⚠️  Schema error para {full_table}: {e}. Usando VARCHAR.")
            schema = [(k, "VARCHAR") for k in rows[0].keys()]

        con.execute(f"DROP TABLE IF EXISTS {alias}")
        schema_sql = ", ".join([f'"{col}" {dtype}' for col, dtype in schema])
        con.execute(f"CREATE TABLE {alias} ({schema_sql})")

        cols = [col for col, _ in schema]
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join([f'"{c}"' for c in cols])
        stmt = f"INSERT INTO {alias} ({col_names}) VALUES ({placeholders})"

        batch = []
        for r in rows:
            row_vals = []
            for c in cols:
                v = r.get(c)
                if isinstance(v, str) and v.strip() == "":
                    v = None
                row_vals.append(v)
            batch.append(row_vals)
            if len(batch) >= 1000:
                con.executemany(stmt, batch)
                batch = []
        if batch:
            con.executemany(stmt, batch)

        total_rows += count
        print(f"  ✅ {alias}: {count} filas")

    con.close()
    print(f"\n✅✅✅ DuckDB listo: {duckdb_path} ({total_rows} filas totales)")
    return str(duckdb_path)


if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_from_databricks(OUTPUT_PATH)
