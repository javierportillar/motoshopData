"""Regression tests for DuckDB product inventory health metrics."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from motoshop_api.metrics.repo_duckdb import (
    DuckDBMetricsRepo,
    close_all_shared_connections,
)

SKU = "7707242890132"


def _create_product_metrics_db(
    db_path: Path,
    *,
    valid_sales: int,
    canceled_sales: int = 0,
) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR,
                nombre_producto VARCHAR,
                precio_venta_con_iva DOUBLE,
                precio_venta_sin_iva DOUBLE,
                costo_producto DOUBLE,
                costo_ultima_compra DOUBLE,
                presentacion VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE silver_fact_compras_detalle (
                cod_producto VARCHAR,
                business_date DATE,
                cantidad DOUBLE,
                costo_producto DOUBLE,
                total_detalle DOUBLE,
                num_documento VARCHAR,
                cod_clase VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE silver_fact_compras (
                num_documento VARCHAR,
                cod_clase VARCHAR,
                nit_proveedor VARCHAR,
                nombre_proveedor VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE silver_fact_ventas_detalle (
                cod_producto VARCHAR,
                business_date DATE,
                cantidad DOUBLE,
                total_detalle DOUBLE,
                costo_producto DOUBLE,
                num_documento VARCHAR,
                cod_clase VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE silver_fact_ventas (
                num_documento VARCHAR,
                cod_clase VARCHAR,
                business_date DATE,
                estado_documento VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE gold_mart_abc_xyz (
                cod_producto VARCHAR,
                business_month VARCHAR,
                abc VARCHAR
            )
            """
        )

        today = date.today()
        purchase_date = today - timedelta(days=20)
        con.execute(
            "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?, ?)",
            [SKU, "HABAS SALADAS X 50 GRAMOS", 2200.0, 1848.0, 0.0, 1750.0, "UNIDAD"],
        )
        con.execute(
            "INSERT INTO gold_mart_abc_xyz VALUES (?, ?, ?)",
            [SKU, today.strftime("%Y-%m"), "B"],
        )
        con.execute(
            "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?)",
            ["49", "FC", "9001", "LIDIA MERCEDES NARVAEZ MADRIGAL"],
        )
        con.execute(
            "INSERT INTO silver_fact_compras_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
            [SKU, purchase_date, 10.0, 1750.0, 17500.0, "49", "FC"],
        )

        sale_index = 0
        for sale_index in range(valid_sales):
            sale_date = purchase_date + timedelta(days=min(sale_index + 1, 20))
            doc = f"V{sale_index + 1}"
            con.execute(
                "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
                [doc, "FV", sale_date, "B"],
            )
            con.execute(
                "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [SKU, sale_date, 1.0, 2200.0, 1750.0, doc, "FV"],
            )

        for canceled_index in range(canceled_sales):
            sale_date = purchase_date + timedelta(days=20)
            doc = f"A{canceled_index + 1}"
            con.execute(
                "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
                [doc, "FV", sale_date, "A"],
            )
            con.execute(
                "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [SKU, sale_date, 1.0, 2200.0, 1750.0, doc, "FV"],
            )
    finally:
        con.close()


def _repo(db_path: Path) -> DuckDBMetricsRepo:
    close_all_shared_connections()
    return DuckDBMetricsRepo(db_path=db_path, tenant="test")


def test_product_with_one_unit_and_twenty_days_of_cover_is_reorder_risk(tmp_path: Path) -> None:
    """A nearly depleted SKU must not be displayed as healthy."""
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9)

    detail = _repo(db_path).get_product_detail(SKU, window_days=180)

    metrics = detail["metrics"]
    assert metrics["cantidad_actual"] == 1
    assert metrics["dias_stock"] == 20
    assert metrics["estado"] == "quiebre"
    assert metrics["accion"] == "reabastecer"


def test_product_with_all_purchased_units_sold_is_exhausted(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(db_path, valid_sales=10)

    detail = _repo(db_path).get_product_detail(SKU, window_days=180)

    metrics = detail["metrics"]
    assert metrics["cantidad_actual"] == 0
    assert metrics["estado"] == "agotado"
    assert metrics["accion"] == "reabastecer"


def test_canceled_sales_do_not_reduce_stock_or_appear_as_movements(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9, canceled_sales=1)

    detail = _repo(db_path).get_product_detail(SKU, window_days=180)

    metrics = detail["metrics"]
    sales_movements = [m for m in detail["movimientos"] if m["tipo"] == "venta"]

    assert metrics["vendido_total"] == 9
    assert metrics["cantidad_actual"] == 1
    assert len(sales_movements) == 9


def test_inventory_purchase_list_includes_products_below_lead_time_plus_buffer(
    tmp_path: Path,
) -> None:
    """The suggested purchase list must include SKUs that do not cover the target window."""
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9)

    overview = _repo(db_path).get_inventario_overview(lead_time_dias=7, colchon_dias=14)
    item = next(i for i in overview["items"] if i["cod_producto"] == SKU)

    assert item["stock"] == 1
    assert item["sugerido_comprar"] > 0
    assert item["accion"] == "comprar_pronto"
    assert overview["buckets_count"]["comprar_pronto"] == 1


def test_inventory_purchase_list_ignores_canceled_sales(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(db_path, valid_sales=8, canceled_sales=10)

    overview = _repo(db_path).get_inventario_overview(lead_time_dias=7, colchon_dias=14)
    item = next(i for i in overview["items"] if i["cod_producto"] == SKU)

    assert item["stock"] == 2
    assert item["uds_90d"] == 8
