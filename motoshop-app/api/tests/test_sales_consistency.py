"""Regression tests for movement dates and DuckDB snapshot replacement."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread

import duckdb

from motoshop_api.metrics.repo_duckdb import (
    DuckDBMetricsRepo,
    _retired_connections,
    close_all_shared_connections,
    get_shared_connection,
    publish_duckdb_snapshot,
)

def _create_sales_db(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas (
                num_documento VARCHAR,
                cod_clase VARCHAR,
                business_date DATE,
                total_factura DOUBLE,
                estado_documento VARCHAR
            )
            """
        )
        connection.execute(
            """
            INSERT INTO silver_fact_ventas VALUES
                ('V17', 'FV', '2026-07-17', 100.0, 'B'),
                ('V18', 'FV', '2026-07-18', 200.0, 'B'),
                ('A19', 'FV', '2026-07-19', 999.0, 'A')
            """
        )
        connection.execute(
            """
            CREATE TABLE silver_fact_ventas_detalle (
                num_documento VARCHAR,
                cod_clase VARCHAR,
                business_date DATE,
                cod_producto VARCHAR,
                cantidad DOUBLE,
                total_detalle DOUBLE
            );
            INSERT INTO silver_fact_ventas_detalle VALUES
                ('V17', 'FV', '2026-07-17', 'A', 1, 100),
                ('V18', 'FV', '2026-07-18', 'B', 1, 200),
                ('A19', 'FV', '2026-07-19', 'C', 1, 999);
            CREATE TABLE silver_dim_producto (
                cod_producto VARCHAR,
                nombre_producto VARCHAR
            );
            INSERT INTO silver_dim_producto VALUES
                ('A', 'Item A'), ('B', 'Item B'), ('C', 'Canceled item');
            """
        )
        connection.execute(
            """
            CREATE TABLE gold_mart_ventas_diarias_sku (
                business_date DATE,
                cod_producto VARCHAR,
                nom_producto VARCHAR,
                cantidad_total DOUBLE,
                valor_total DOUBLE,
                num_facturas INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO gold_mart_ventas_diarias_sku VALUES
                ('2026-07-17', 'A', 'Item A', 1, 100, 1),
                ('2026-07-18', 'B', 'Item B', 1, 200, 1)
            """
        )
    finally:
        connection.close()


def _repo(path: Path) -> DuckDBMetricsRepo:
    close_all_shared_connections()
    return DuckDBMetricsRepo(db_path=path, tenant="test-sales")


def test_explicit_day_without_sales_does_not_fall_back(tmp_path: Path) -> None:
    db_path = tmp_path / "sales.duckdb"
    _create_sales_db(db_path)

    response = _repo(db_path).get_sales_daily("2026-07-19")

    assert response.date == "2026-07-19"
    assert response.total_ventas == 0
    assert response.total_facturas == 0
    assert response.productos_vendidos == []


def test_summary_and_daily_calendar_share_business_cutoff(tmp_path: Path) -> None:
    db_path = tmp_path / "sales.duckdb"
    _create_sales_db(db_path)
    repo = _repo(db_path)

    summary = repo.get_sales_summary_v2()
    calendar = repo.get_sales_daily_month("2026-07")

    assert summary["as_of_business_date"] == "2026-07-18"
    assert calendar["as_of_business_date"] == "2026-07-18"
    assert [day["date"] for day in calendar["days"]] == ["2026-07-17", "2026-07-18"]


def test_empty_sales_dataset_has_null_business_cutoff(tmp_path: Path) -> None:
    db_path = tmp_path / "empty-sales.duckdb"
    _create_sales_db(db_path)
    connection = duckdb.connect(str(db_path))
    try:
        connection.execute("DELETE FROM silver_fact_ventas")
    finally:
        connection.close()
    repo = _repo(db_path)

    summary = repo.get_sales_summary_v2()
    calendar = repo.get_sales_daily_month("2026-07")

    assert summary["business_month"] is None
    assert summary["max_sales_date"] is None
    assert summary["as_of_business_date"] is None
    assert calendar["as_of_business_date"] is None



def test_snapshot_publication_cannot_pool_connection_to_old_inode(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "published.duckdb"
    tmp_snapshot = tmp_path / "published.duckdb.downloading"
    for path, marker in ((db_path, "old"), (tmp_snapshot, "new")):
        connection = duckdb.connect(str(path))
        try:
            connection.execute("CREATE TABLE snapshot_marker (value VARCHAR)")
            connection.execute("INSERT INTO snapshot_marker VALUES (?)", [marker])
        finally:
            connection.close()

    close_all_shared_connections()
    old_connection = get_shared_connection(db_path)
    replace_entered = Event()
    release_replace = Event()
    reader_started = Event()
    reader_finished = Event()
    reader_connections: list[duckdb.DuckDBPyConnection] = []
    publication_errors: list[BaseException] = []
    real_replace = Path.replace

    def blocking_replace(path: Path, target: Path) -> Path:
        if path == tmp_snapshot:
            replace_entered.set()
            release_replace.wait(timeout=2)
        return real_replace(path, target)

    def publish() -> None:
        try:
            publish_duckdb_snapshot(tmp_snapshot, db_path)
        except BaseException as exc:  # pragma: no cover - surfaced by assertion
            publication_errors.append(exc)

    def read_published() -> None:
        reader_started.set()
        reader_connections.append(get_shared_connection(db_path))
        reader_finished.set()

    monkeypatch.setattr(Path, "replace", blocking_replace)
    publisher = Thread(target=publish)
    reader = Thread(target=read_published)
    publisher.start()
    assert replace_entered.wait(timeout=2)
    reader.start()
    assert reader_started.wait(timeout=2)
    assert not reader_finished.wait(timeout=0.1)

    release_replace.set()
    publisher.join(timeout=2)
    reader.join(timeout=2)

    try:
        assert not publisher.is_alive()
        assert not reader.is_alive()
        assert publication_errors == []
        assert len(reader_connections) == 1
        published_connection = reader_connections[0]
        assert published_connection is old_connection
        assert published_connection.execute("SELECT value FROM snapshot_marker").fetchone() == (
            "new",
        )
        assert get_shared_connection(db_path) is published_connection
        assert _retired_connections == []
    finally:
        close_all_shared_connections()
        old_connection.close()


def test_active_query_finishes_on_old_snapshot_before_retired_connection_closes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leased.duckdb"
    tmp_snapshot = tmp_path / "leased.duckdb.downloading"
    for path, marker in ((db_path, "old"), (tmp_snapshot, "new")):
        connection = duckdb.connect(str(path))
        try:
            connection.execute("CREATE TABLE snapshot_marker (value VARCHAR)")
            connection.execute("INSERT INTO snapshot_marker VALUES (?)", [marker])
        finally:
            connection.close()

    close_all_shared_connections()
    shared_connection = get_shared_connection(db_path)
    old_result = shared_connection.execute("SELECT value FROM snapshot_marker")

    try:
        publish_duckdb_snapshot(tmp_snapshot, db_path)

        assert len(_retired_connections) == 1
        assert _retired_connections[0].active_readers == 1
        assert shared_connection.execute("SELECT value FROM snapshot_marker").fetchone() == (
            "new",
        )
        assert old_result.fetchone() == ("old",)
        assert _retired_connections == []
    finally:
        old_result.close()
        close_all_shared_connections()
