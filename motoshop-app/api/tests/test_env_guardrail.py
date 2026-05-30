"""Pruebas del ENV guardrail (R16).

Verifica que:
  - ENV=test + host no-localhost → RuntimeError
  - ENV=test + host no-localhost + ALLOW_TEST_ENV_IN_PROD=true → OK
  - ENV=dev → siempre OK (sin importar host)
  - _is_localhost() detecta correctamente loopback
"""

from __future__ import annotations

from unittest.mock import patch

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from motoshop_api.config import settings
from motoshop_api.main import _is_localhost, lifespan


@pytest.fixture(autouse=True)
def _reset_settings():
    """Restaura settings.env después de cada test."""
    yield
    settings.env = "dev"


class TestIsLocalhost:
    def test_returns_true_for_localhost(self) -> None:
        """En la máquina actual, _is_localhost() debe retornar True."""
        assert _is_localhost() is True

    @patch("motoshop_api.main.socket.gethostname", return_value="server-prod")
    @patch("motoshop_api.main.socket.gethostbyname", return_value="192.168.1.100")
    def test_returns_false_for_external_ip(self, mock_gethostbyname, mock_gethostname) -> None:
        assert _is_localhost() is False

    @patch("motoshop_api.main.socket.gethostname", return_value="localhost")
    def test_returns_true_for_hostname_localhost(self, mock_gethostname) -> None:
        assert _is_localhost() is True


class TestEnvGuardrailLifespan:
    """Prueba que el lifespan valide ENV guardrail al arrancar la app."""

    async def _run_lifespan(self) -> None:
        """Ejecuta el lifespan contra una app dummy y espera que pase."""
        app = FastAPI()
        async with lifespan(app):
            pass

    def _run_lifespan_sync(self) -> None:
        """Wrapper síncrono para _run_lifespan."""
        asyncio.run(self._run_lifespan())

    # ── Test 1: ENV=dev siempre pasa ──────────────────────────────────

    def test_env_dev_on_external_host_ok(self, monkeypatch) -> None:
        """ENV=dev pasa aunque sea host externo."""
        monkeypatch.setattr(settings, "env", "dev")

        with patch("motoshop_api.main.socket.gethostname", return_value="server-prod"):
            with patch("motoshop_api.main.socket.gethostbyname", return_value="10.0.0.5"):
                self._run_lifespan_sync()  # no debe fallar

    # ── Test 2: ENV=test + localhost → pasa ────────────────────────────

    def test_env_test_on_localhost_ok(self, monkeypatch) -> None:
        """ENV=test en localhost NO debe levantar RuntimeError."""
        monkeypatch.setattr(settings, "env", "test")

        with patch("motoshop_api.main.socket.gethostname", return_value="localhost"):
            self._run_lifespan_sync()

    # ── Test 3: ENV=test + host remoto → RuntimeError ──────────────────

    def test_env_test_on_external_host_raises(self, monkeypatch) -> None:
        """ENV=test + host remoto → RuntimeError."""
        monkeypatch.setattr(settings, "env", "test")

        with patch("motoshop_api.main.socket.gethostname", return_value="server-prod"):
            with patch("motoshop_api.main.socket.gethostbyname", return_value="10.0.0.5"):
                with pytest.raises(RuntimeError, match="ENV=test detected"):
                    self._run_lifespan_sync()

    # ── Test 4: ENV=test + host remoto + ALLOW_TEST_ENV_IN_PROD=true → OK ──

    def test_env_test_external_with_allow_flag_ok(self, monkeypatch) -> None:
        """ENV=test + host remoto + ALLOW_TEST_ENV_IN_PROD=true → OK."""
        monkeypatch.setattr(settings, "env", "test")
        monkeypatch.setenv("ALLOW_TEST_ENV_IN_PROD", "true")

        with patch("motoshop_api.main.socket.gethostname", return_value="server-prod"):
            with patch("motoshop_api.main.socket.gethostbyname", return_value="10.0.0.5"):
                self._run_lifespan_sync()

    # ── Test 5: End-to-end via TestClient (smoke) ────────────────────

    def test_real_app_health_with_test_env_on_localhost(self, monkeypatch) -> None:
        """TestClient + app real con ENV=test en localhost → debe arrancar."""
        monkeypatch.setattr(settings, "env", "test")

        from motoshop_api.main import app as real_app

        with patch("motoshop_api.main.socket.gethostname", return_value="localhost"):
            client = TestClient(real_app)
            resp = client.get("/health")
            assert resp.status_code == 200
