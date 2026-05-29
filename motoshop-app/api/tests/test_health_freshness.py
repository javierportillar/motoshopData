"""Pruebas del endpoint /health/data-freshness."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from motoshop_api.main import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _make_manifest(name: str, modification_time_ms: int) -> MagicMock:
    m = MagicMock()
    m.name = name
    m.last_modified = modification_time_ms
    return m


class TestDataFreshness:
    def test_ok_status(self, client: TestClient) -> None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        manifest = _make_manifest("manifest_2026-05-29.json", now_ms)

        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = "https://test.cloud.databricks.com"
            mock_settings.databricks_token = "dapi_test"
            mock_settings.databricks_volume_path = "/Volumes/motoshop/bronze/_landing"

            with patch("motoshop_api.health.router.WorkspaceClient") as MockWC:
                mock_w = MagicMock()
                MockWC.return_value = mock_w
                mock_w.files.list_directory_contents.return_value = [manifest]

                resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "OK"
        assert body["lag_hours"] < 0.1
        assert body["last_manifest"] == "manifest_2026-05-29.json"

    def test_warn_status(self, client: TestClient) -> None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        three_hours_ago = now_ms - 3 * 3600 * 1000
        manifest = _make_manifest("manifest_2026-05-28.json", three_hours_ago)

        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = "https://test.cloud.databricks.com"
            mock_settings.databricks_token = "dapi_test"
            mock_settings.databricks_volume_path = "/Volumes/motoshop/bronze/_landing"

            with patch("motoshop_api.health.router.WorkspaceClient") as MockWC:
                mock_w = MagicMock()
                MockWC.return_value = mock_w
                mock_w.files.list_directory_contents.return_value = [manifest]

                resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "WARN"
        assert 2 < body["lag_hours"] < 4

    def test_stale_status(self, client: TestClient) -> None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        ten_hours_ago = now_ms - 10 * 3600 * 1000
        manifest = _make_manifest("manifest_2026-05-27.json", ten_hours_ago)

        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = "https://test.cloud.databricks.com"
            mock_settings.databricks_token = "dapi_test"
            mock_settings.databricks_volume_path = "/Volumes/motoshop/bronze/_landing"

            with patch("motoshop_api.health.router.WorkspaceClient") as MockWC:
                mock_w = MagicMock()
                MockWC.return_value = mock_w
                mock_w.files.list_directory_contents.return_value = [manifest]

                resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "STALE"
        assert 6 < body["lag_hours"] < 24

    def test_critical_status(self, client: TestClient) -> None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        two_days_ago = now_ms - 48 * 3600 * 1000
        manifest = _make_manifest("manifest_2026-05-25.json", two_days_ago)

        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = "https://test.cloud.databricks.com"
            mock_settings.databricks_token = "dapi_test"
            mock_settings.databricks_volume_path = "/Volumes/motoshop/bronze/_landing"

            with patch("motoshop_api.health.router.WorkspaceClient") as MockWC:
                mock_w = MagicMock()
                MockWC.return_value = mock_w
                mock_w.files.list_directory_contents.return_value = [manifest]

                resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "CRITICAL"
        assert body["lag_hours"] > 24

    def test_no_manifests(self, client: TestClient) -> None:
        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = "https://test.cloud.databricks.com"
            mock_settings.databricks_token = "dapi_test"
            mock_settings.databricks_volume_path = "/Volumes/motoshop/bronze/_landing"

            with patch("motoshop_api.health.router.WorkspaceClient") as MockWC:
                mock_w = MagicMock()
                MockWC.return_value = mock_w
                mock_w.files.list_directory_contents.return_value = []

                resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "CRITICAL"
        assert body["lag_hours"] is None

    def test_no_databricks_config(self, client: TestClient) -> None:
        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = ""
            mock_settings.databricks_token = ""

            resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ERROR"
        assert "not configured" in body["error"]

    def test_databricks_error(self, client: TestClient) -> None:
        with patch("motoshop_api.health.router.settings") as mock_settings:
            mock_settings.databricks_host = "https://test.cloud.databricks.com"
            mock_settings.databricks_token = "dapi_test"
            mock_settings.databricks_volume_path = "/Volumes/motoshop/bronze/_landing"

            with patch("motoshop_api.health.router.WorkspaceClient") as MockWC:
                mock_w = MagicMock()
                MockWC.return_value = mock_w
                mock_w.files.list_directory_contents.side_effect = Exception("Timeout")

                resp = client.get("/health/data-freshness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ERROR"
        assert "Timeout" in body["error"]
