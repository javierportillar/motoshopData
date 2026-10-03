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
    duplicate_sales: int = 0,
    orphan_sales: int = 0,
    canceled_purchases: int = 0,
    duplicate_purchases: int = 0,
    catalog_stock: float = 7.0,
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
                presentacion VARCHAR,
                existencia DOUBLE,
                snapshot_date DATE
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
                business_date DATE,
                num_documento VARCHAR,
                cod_clase VARCHAR,
                nit_proveedor VARCHAR,
                nombre_proveedor VARCHAR,
                estado_documento VARCHAR
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
            "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                SKU,
                "HABAS SALADAS X 50 GRAMOS",
                2200.0,
                1848.0,
                0.0,
                1750.0,
                "UNIDAD",
                catalog_stock,
                today,
            ],
        )
        con.execute(
            "INSERT INTO gold_mart_abc_xyz VALUES (?, ?, ?)",
            [SKU, today.strftime("%Y-%m"), "B"],
        )
        con.execute(
            "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?)",
            [purchase_date, "49", "FC", "9001", "LIDIA MERCEDES NARVAEZ MADRIGAL", "B"],
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

        for duplicate_index in range(duplicate_sales):
            sale_date = purchase_date + timedelta(days=19)
            doc = f"DUPV{duplicate_index + 1}"
            for _ in range(2):
                con.execute(
                    "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
                    [doc, "FV", sale_date, "B"],
                )
            con.execute(
                "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [SKU, sale_date, 1.0, 2200.0, 1750.0, doc, "FV"],
            )

        for orphan_index in range(orphan_sales):
            sale_date = purchase_date + timedelta(days=18)
            doc = f"ORPHAN{orphan_index + 1}"
            con.execute(
                "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [SKU, sale_date, 1.0, 2200.0, 1750.0, doc, "FV"],
            )

        for canceled_index in range(canceled_purchases):
            canceled_date = purchase_date + timedelta(days=1)
            doc = f"CANCELED-P{canceled_index + 1}"
            con.execute(
                "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?)",
                [canceled_date, doc, "FC", "9001", "Canceled supplier", "A"],
            )
            con.execute(
                "INSERT INTO silver_fact_compras_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [SKU, canceled_date, 5.0, 1750.0, 8750.0, doc, "FC"],
            )

        for duplicate_index in range(duplicate_purchases):
            duplicate_date = purchase_date + timedelta(days=2)
            doc = f"DUP-P{duplicate_index + 1}"
            for _ in range(2):
                con.execute(
                    "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?)",
                    [duplicate_date, doc, "FC", "9001", "Duplicated supplier", "B"],
                )
            con.execute(
                "INSERT INTO silver_fact_compras_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [SKU, duplicate_date, 4.0, 1750.0, 7000.0, doc, "FC"],
            )
    finally:
        con.close()


def _repo(db_path: Path, tenant: str = "test") -> DuckDBMetricsRepo:
    close_all_shared_connections()
    return DuckDBMetricsRepo(db_path=db_path, tenant=tenant)


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


def test_masvital_product_detail_uses_validated_catalog_existence(tmp_path: Path) -> None:
    db_path = tmp_path / "masvital.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9, catalog_stock=7)
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [SKU, "HABAS SALADAS X 50 GRAMOS", 2200.0, 1848.0, 0.0, 1750.0,
             "UNIDAD", 8.0, date.today()],
        )

    detail = _repo(db_path, tenant="masvital").get_product_detail(SKU, window_days=180)

    assert detail["metrics"]["comprado_total"] == 10
    assert detail["metrics"]["vendido_total"] == 9
    assert detail["metrics"]["cantidad_actual"] == 8
    assert detail["metrics"]["valor_inventario"] == 14_000
    assert detail["metrics"]["stock_source"] == "catalog_snapshot"


def test_motoshop_product_detail_identifies_reconstructed_stock_source(tmp_path: Path) -> None:
    db_path = tmp_path / "motoshop.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9)

    detail = _repo(db_path, tenant="motoshop").get_product_detail(SKU, window_days=180)

    assert detail["metrics"]["cantidad_actual"] == 1
    assert detail["metrics"]["stock_source"] == "purchases_minus_sales_estimate"


def test_canceled_sales_do_not_reduce_stock_or_appear_as_movements(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9, canceled_sales=1)

    detail = _repo(db_path).get_product_detail(SKU, window_days=180)

    metrics = detail["metrics"]
    sales_movements = [m for m in detail["movimientos"] if m["tipo"] == "venta"]

    assert metrics["vendido_total"] == 9
    assert metrics["cantidad_actual"] == 1
    assert len(sales_movements) == 9


def test_product_metrics_and_fifo_movements_exclude_canceled_duplicate_and_orphan_docs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "metrics.duckdb"
    _create_product_metrics_db(
        db_path,
        valid_sales=3,
        canceled_sales=1,
        duplicate_sales=1,
        orphan_sales=1,
        canceled_purchases=1,
        duplicate_purchases=1,
    )

    detail = _repo(db_path, tenant="motoshop").get_product_detail(SKU, window_days=180)

    sales_movements = [movement for movement in detail["movimientos"] if movement["tipo"] == "venta"]
    purchase_movements = [movement for movement in detail["movimientos"] if movement["tipo"] == "compra"]
    assert detail["metrics"]["comprado_total"] == 10
    assert detail["metrics"]["vendido_total"] == 3
    assert detail["metrics"]["cantidad_actual"] == 7
    assert {movement["num_documento"] for movement in sales_movements} == {
        "V1", "V2", "V3",
    }
    assert {movement["num_documento"] for movement in purchase_movements} == {"49"}


def test_catalog_and_product_detail_metrics_match_for_the_same_window_and_snapshot(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "metrics-parity.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9, catalog_stock=5)
    repo = _repo(db_path, tenant="masvital")

    catalog = repo.get_product_analytics(
        window_days=180, page=1, page_size=50, q=SKU, sort="revenue_win", order="desc"
    )
    detail = repo.get_product_detail(SKU, window_days=180)

    catalog_item = next(item for item in catalog["items"] if item["cod_producto"] == SKU)
    detail_metrics = detail["metrics"]
    for key in (
        "cantidad_actual", "unidades_win", "velocidad_mensual", "dias_stock",
        "abc", "estado", "accion",
    ):
        assert catalog_item[key] == detail_metrics[key]
    assert catalog["data_freshness"] == detail["data_freshness"]
    assert catalog["data_freshness"]["inventory_snapshot"] == date.today().isoformat()


def test_catalog_abc_filter_uses_dynamic_window_and_has_stable_pages(tmp_path: Path) -> None:
    db_path = tmp_path / "catalog-abc.duckdb"
    _create_product_metrics_db(db_path, valid_sales=9, catalog_stock=3)
    today = date.today()
    purchase_date = today - timedelta(days=20)
    with duckdb.connect(str(db_path)) as connection:
        for product_index in range(1, 5):
            sku = f"SKU-{product_index}"
            connection.execute(
                "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [sku, f"Product {product_index}", 2200, 1848, 1750, 1750, "UNIDAD", 3, today],
            )
            document = f"P-{product_index}"
            connection.execute(
                "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?)",
                [purchase_date, document, "FC", "9001", "Supplier", "B"],
            )
            connection.execute(
                "INSERT INTO silver_fact_compras_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                [sku, purchase_date, 10, 1750, 17500, document, "FC"],
            )
            for sale_index in range(9):
                sale_date = purchase_date + timedelta(days=sale_index + 1)
                sale_document = f"V-{product_index}-{sale_index}"
                connection.execute(
                    "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
                    [sale_document, "FV", sale_date, "B"],
                )
                connection.execute(
                    "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [sku, sale_date, 1, 2200, 1750, sale_document, "FV"],
                )

    repo = _repo(db_path, tenant="motoshop")
    first = repo.get_product_analytics(window_days=180, page=1, page_size=2, abc="A")
    second = repo.get_product_analytics(window_days=180, page=2, page_size=2, abc="A")
    other_category = repo.get_product_analytics(window_days=180, page=1, page_size=20, abc="B")

    first_skus = {item["cod_producto"] for item in first["items"]}
    second_skus = {item["cod_producto"] for item in second["items"]}
    assert first["total"] == second["total"] == 4
    assert first["page"] == 1 and second["page"] == 2
    assert len(first_skus) == len(second_skus) == 2
    assert first_skus.isdisjoint(second_skus)
    assert all(item["abc"] == "A" for item in first["items"] + second["items"])
    assert other_category["total"] == 0


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
