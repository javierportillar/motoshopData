"""Regression coverage for lease-aware pipeline-runs R2 publication."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb

from motoshop_api.metrics.repo_duckdb import (
    _retired_connections,
    close_all_shared_connections,
    get_shared_connection,
)
from motoshop_api.pipeline_runs.repo import (
    _PIPELINE_R2_DOWNLOADED_MTIME,
    _PIPELINE_R2_LAST_CHECK,
    _bootstrap_pipeline_db_from_r2,
)


def _create_pipeline_db(path: Path, pipeline_name: str) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE app_pipeline_runs (
                id INTEGER PRIMARY KEY,
                pipeline_name VARCHAR NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                status VARCHAR NOT NULL,
                duration_seconds INTEGER,
                rows_processed INTEGER,
                triggered_by VARCHAR NOT NULL,
                error_message TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO app_pipeline_runs
            VALUES (1, ?, '2026-07-19 00:00:00', NULL, 'success', 1, 1, 'test', NULL)
            """,
            [pipeline_name],
        )
    finally:
        connection.close()


def test_pipeline_r2_publish_keeps_active_old_query_and_serves_new_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "tenant_pipeline_runs.duckdb"
    r2_snapshot = tmp_path / "r2_pipeline_runs.duckdb"
    _create_pipeline_db(db_path, "old")
    _create_pipeline_db(r2_snapshot, "new")

    class FakeS3:
        def head_object(self, **_kwargs):
            return {"LastModified": datetime(2026, 7, 19, tzinfo=UTC)}

        def download_file(self, _bucket: str, _key: str, target: str) -> None:
            shutil.copyfile(r2_snapshot, target)

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3()),
    )
    monkeypatch.setenv("R2_ENDPOINT", "https://r2.test")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    tenant = "pipeline-snapshot-test"
    _PIPELINE_R2_LAST_CHECK.pop(tenant, None)
    _PIPELINE_R2_DOWNLOADED_MTIME[tenant] = 0

    close_all_shared_connections()
    shared_connection = get_shared_connection(db_path)
    old_result = shared_connection.execute(
        "SELECT pipeline_name FROM app_pipeline_runs WHERE id = 1"
    )

    try:
        _bootstrap_pipeline_db_from_r2(db_path, tenant=tenant)

        assert len(_retired_connections) == 1
        assert shared_connection.execute(
            "SELECT pipeline_name FROM app_pipeline_runs WHERE id = 1"
        ).fetchone() == ("new",)
        assert old_result.fetchone() == ("old",)
        assert _retired_connections == []
    finally:
        old_result.close()
        close_all_shared_connections()
