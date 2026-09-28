from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


@pytest.fixture
def replenishment_database(tmp_path: Path) -> Path:
    path = tmp_path / "replenishment.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR, nombre_producto VARCHAR, existencia DOUBLE,
                cod_medida VARCHAR, presentacion VARCHAR, nit_proveedor VARCHAR,
                snapshot_date DATE, fecha_actualizacion DATE
            )
            """
        )
        connection.executemany(
            "INSERT INTO silver_dim_producto VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "SKU-A", "Kombucha A", 0, "UND", "UNIDAD", "900111111-1",
                    "2026-09-26", "2026-09-26",
                ),
                (
                    "SKU-B", "Kombucha B", 0, "UND", "UNIDAD", "900222222-2",
                    "2026-09-26", "2026-09-26",
                ),
                (
                    "SKU-C", "Kombucha C", 4, "UND", "UNIDAD", "900333333-3",
                    "2026-09-26", "2026-09-26",
                ),
                (
                    "SKU-D", "Kombucha D", 0, "GR", "GRAMO", "900444444-4",
                    "2026-09-26", "2026-09-26",
                ),
                (
                    "SKU-E", "Sin demanda", 0, "UND", "UNIDAD", None,
                    "2026-09-26", "2026-09-26",
                ),
            ],
        )
        connection.execute(
            "CREATE TABLE silver_fact_ventas (business_date DATE, num_documento VARCHAR, "
            "cod_clase VARCHAR, estado_documento VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE silver_fact_ventas_detalle (business_date DATE, num_documento VARCHAR, "
            "cod_clase VARCHAR, cod_producto VARCHAR, cantidad DOUBLE, total_detalle DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
            [
                ("2026-06-01", "V-A-OLD", "FV", "B"),
                ("2026-09-26", "V-A", "FV", "B"),
                ("2026-09-26", "V-B-CANCEL", "FV", "A"),
                ("2026-01-01", "V-B-OLD", "FV", "B"),
                ("2026-08-01", "V-C", "FV", "B"),
                ("2026-09-20", "V-D", "FV", "B"),
            ],
        )
        connection.executemany(
            "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("2026-06-01", "V-A-OLD", "FV", "SKU-A", 13, 97500),
                ("2026-09-26", "V-A", "FV", "SKU-A", 5, 37500),
                ("2026-09-26", "V-B-CANCEL", "FV", "SKU-B", 100, 500000),
                ("2026-01-01", "V-B-OLD", "FV", "SKU-B", 50, 250000),
                ("2026-08-01", "V-C", "FV", "SKU-C", 30, 225000),
                ("2026-09-20", "V-D", "FV", "SKU-D", 90, 90000),
            ],
        )
        connection.execute(
            "CREATE TABLE silver_fact_compras (business_date DATE, num_documento VARCHAR, "
            "cod_clase VARCHAR, nit_proveedor VARCHAR, nombre_proveedor VARCHAR, "
            "estado_documento VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE silver_fact_compras_detalle (business_date DATE, num_documento VARCHAR, "
            "cod_clase VARCHAR, cod_producto VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("2026-08-20", "P-A", "FC", "900111111-1", "Supplier A", "B"),
                ("2026-09-20", "P-D", "FC", "900444444-4", "Supplier D", "B"),
                ("2026-09-25", "P-D-CANCEL", "FC", "999999999-9", "Canceled Supplier", "A"),
            ],
        )
        connection.executemany(
            "INSERT INTO silver_fact_compras_detalle VALUES (?, ?, ?, ?)",
            [
                ("2026-08-20", "P-A", "FC", "SKU-A"),
                ("2026-09-20", "P-D", "FC", "SKU-D"),
                ("2026-09-25", "P-D-CANCEL", "FC", "SKU-D"),
            ],
        )
    return path


def test_replenishment_shortlist_uses_valid_sales_snapshot_and_supplier(
    replenishment_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(replenishment_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(replenishment_database), tenant="motoshop")

    result = executor.get_productos_para_reponer(target_cover_days=45, sales_window_days=180)

    items = {item["sku"]: item for item in result["productos"]}
    assert set(items) == {"SKU-A", "SKU-D"}
    assert items["SKU-A"]["unidades_vendidas"] == 18
    assert items["SKU-A"]["cantidad_referencia"] == 4.5
    assert items["SKU-A"]["proveedor"] == "Supplier A"
    assert items["SKU-D"]["unidad"] == "GRAMO"
    assert items["SKU-D"]["cantidad_referencia"] == 22.5
    assert items["SKU-D"]["proveedor"] == "Supplier D"
    assert result["sales_cutoff"] == result["inventory_cutoff"] == "2026-09-26"
    assert "no una orden" in result["respuesta_fallback"]
    assert "lead time" in result["respuesta_fallback"]
    connection.close()


def test_replenishment_filter_matches_latest_supplier_name_or_nit(
    replenishment_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(replenishment_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(replenishment_database), tenant="motoshop")

    by_name = executor.get_productos_para_reponer(supplier_query="supplier a")
    by_nit = executor.get_productos_para_reponer(supplier_query="900444444-4")
    missing = executor.get_productos_para_reponer(supplier_query="Santo Sano")

    assert [product["sku"] for product in by_name["productos"]] == ["SKU-A"]
    assert [product["sku"] for product in by_nit["productos"]] == ["SKU-D"]
    assert missing["productos"] == []
    assert "Santo Sano" in missing["respuesta_fallback"]
    connection.close()


@pytest.mark.parametrize(
    ("target_cover_days", "sales_window_days", "limit"),
    [(0, 180, 50), (45, 500, 50), (45, 180, 101)],
)
def test_replenishment_rejects_unbounded_parameters(
    replenishment_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_cover_days: int,
    sales_window_days: int,
    limit: int,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(replenishment_database), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(duckdb_path=str(replenishment_database), tenant="motoshop")
    with pytest.raises(ValueError):
        executor.get_productos_para_reponer(target_cover_days, sales_window_days, limit)
    connection.close()
