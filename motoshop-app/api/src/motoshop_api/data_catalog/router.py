"""Medallion Data Catalog — V1.8.1

Endpoints read-only para inspeccionar el DuckDB productivo por capas:
- GET /api/admin/data/catalog — resumen por capa + listado de tablas
- GET /api/admin/data/catalog/{table} — detalle de tabla (columnas, muestra, calidad)
- GET /api/admin/data/lineage — lineage simple Bronze → Silver → Gold
"""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from motoshop_api.auth.deps import require_role
from motoshop_api.auth.users import User
from motoshop_api.admin.router import _get_duckdb_path, DataStatusResponse

catalog_router = APIRouter(prefix="/admin/data", tags=["data_catalog"])

LAYER_RULES = [
    ("bronze", "bronze_"),
    ("silver", "silver_"),
    ("gold", "gold_"),
    ("silver", "mart_"),           # some gold marts without prefix
    ("app", "app_"),
]


def _classify_layer(table_name: str) -> str:
    for layer, prefix in LAYER_RULES:
        if table_name.startswith(prefix):
            return layer
    return "other"


def _get_con():
    db_path = _get_duckdb_path()
    return duckdb.connect(str(db_path), read_only=True)


# ── Catalog ────────────────────────────────────────────────────────────────


@catalog_router.get("/catalog")
def data_catalog(
    request: Request,
    _user: User = Depends(require_role("admin", "gerente")),
):
    """Catálogo de tablas del DuckDB productivo por capa Medallion."""
    con = _get_con()
    try:
        # Todas las tablas (DuckDB: SHOW TABLES es más confiable que information_schema)
        tables = con.execute("SHOW TABLES").fetchall()

        table_list = []
        layer_summary: dict[str, dict] = {}

        for (tname,) in tables:
            layer = _classify_layer(tname)
            row_count = con.execute(f"SELECT COUNT(*) FROM \"{tname}\"").fetchone()[0]

            # Columnas y date column
            cols = con.execute(f"DESCRIBE \"{tname}\"").fetchall()
            col_count = len(cols)
            date_col = None
            for c in cols:
                if c[1] in ("DATE", "TIMESTAMP") and ("date" in c[0].lower() or "fecha" in c[0].lower()):
                    date_col = c[0]
                    break

            max_date = None
            if date_col:
                try:
                    md = con.execute(f"SELECT MAX(\"{date_col}\") FROM \"{tname}\"").fetchone()[0]
                    max_date = str(md) if md else None
                except Exception:
                    pass

            status = "ok"
            warnings = []
            if row_count == 0:
                status = "empty"
                warnings.append("Tabla vacía")
            elif max_date and date_col and "2028" in str(max_date):
                status = "stale"
                warnings.append(f"Fecha futura anómala: {max_date}")

            table_list.append({
                "table_name": tname, "layer": layer, "row_count": row_count,
                "column_count": col_count, "date_column": date_col,
                "max_date": max_date, "status": status,
            })

            if layer not in layer_summary:
                layer_summary[layer] = {"layer": layer, "table_count": 0, "total_rows": 0, "max_business_date": None, "warnings": []}
            layer_summary[layer]["table_count"] += 1
            layer_summary[layer]["total_rows"] += row_count
            if max_date and (not layer_summary[layer]["max_business_date"] or max_date > layer_summary[layer]["max_business_date"]):
                layer_summary[layer]["max_business_date"] = max_date
            layer_summary[layer]["warnings"].extend(warnings)

        return {
            "duckdb_freshness_utc": DataStatusResponse().duckdb_freshness_utc,
            "layers": sorted(layer_summary.values(), key=lambda x: ["bronze", "silver", "gold", "app", "other"].index(x["layer"])),
            "tables": table_list,
        }
    finally:
        con.close()


# ── Table detail ───────────────────────────────────────────────────────────


@catalog_router.get("/catalog/{table_name}")
def data_catalog_detail(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=100),
    _user: User = Depends(require_role("admin")),
):
    """Detalle de una tabla: columnas, muestra, calidad. Admin-only."""
    con = _get_con()
    try:
        # Validar que existe
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ? AND table_schema = 'main'",
            [table_name],
        ).fetchone()[0]
        if not exists:
            raise HTTPException(status_code=404, detail=f"Tabla '{table_name}' no encontrada")

        layer = _classify_layer(table_name)
        row_count = con.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()[0]

        # Columnas
        cols = con.execute(f"DESCRIBE \"{table_name}\"").fetchall()
        columns = [{"name": c[0], "type": c[1], "nullable": c[2] == "YES"} for c in cols]

        # Muestra
        sample = con.execute(f"SELECT * FROM \"{table_name}\" LIMIT ?", [limit]).fetchall()
        col_names = [c[0] for c in cols]
        sample_rows = [dict(zip(col_names, [str(v) if v is not None else None for v in row])) for row in sample]

        # Calidad: null counts + max date
        null_counts = {}
        for c in cols:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM \"{table_name}\" WHERE \"{c[0]}\" IS NULL").fetchone()[0]
                if n > 0:
                    null_counts[c[0]] = n
            except Exception:
                pass

        max_date = None
        for c in cols:
            if c[1] in ("DATE", "TIMESTAMP") and ("date" in c[0].lower() or "fecha" in c[0].lower()):
                try:
                    md = con.execute(f"SELECT MAX(\"{c[0]}\") FROM \"{table_name}\"").fetchone()[0]
                    max_date = str(md) if md else None
                except Exception:
                    pass
                break

        warnings = []
        if row_count == 0:
            warnings.append("Tabla vacía")
        if null_counts:
            for col, n in null_counts.items():
                if n == row_count:
                    warnings.append(f"Columna '{col}' es 100% NULL")

        return {
            "table_name": table_name, "layer": layer, "row_count": row_count,
            "columns": columns, "sample_rows": sample_rows,
            "quality": {"null_counts": null_counts, "max_date": max_date, "warnings": warnings},
        }
    finally:
        con.close()


# ── Lineage ─────────────────────────────────────────────────────────────────


@catalog_router.get("/lineage")
def data_lineage(
    _user: User = Depends(require_role("admin", "gerente")),
):
    """Lineage simple: Bronze → Silver → Gold basado en prefijos de tabla."""
    edges = [
        {"from": "bronze_productos", "to": "silver_dim_producto", "transform": "silver"},
        {"from": "bronze_bodegas", "to": "silver_dim_bodega", "transform": "silver"},
        {"from": "bronze_facventas", "to": "silver_fact_ventas", "transform": "silver"},
        {"from": "bronze_detfventas", "to": "silver_fact_ventas_detalle", "transform": "silver"},
        {"from": "bronze_faccompras", "to": "silver_fact_compras", "transform": "silver"},
        {"from": "bronze_detfcompras", "to": "silver_fact_compras_detalle", "transform": "silver"},
        {"from": "silver_fact_ventas", "to": "gold_mart_ventas_diarias_sku", "transform": "gold"},
        {"from": "silver_dim_producto", "to": "gold_mart_inventario_actual", "transform": "gold"},
        {"from": "silver_fact_ventas", "to": "gold_mart_cohortes_clientes", "transform": "gold"},
        {"from": "gold_mart_ventas_diarias_sku", "to": "gold_mart_rotacion_abc", "transform": "gold"},
        {"from": "silver_fact_ventas_detalle", "to": "gold_alertas_quiebre", "transform": "gold"},
        {"from": "gold_mart_ventas_diarias_sku", "to": "gold_forecast_categoria", "transform": "gold"},
    ]
    return {"edges": edges}
