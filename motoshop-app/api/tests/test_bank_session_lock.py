"""Candado del turno de sesión: el huérfano de Windows no puede bloquear el nodo.

En Windows el candado es un archivo con creación exclusiva que se borra al
liberar. Si el proceso muere a mitad de un scrape (un reinicio de la API, por
ejemplo) el archivo queda y **todas** las corridas siguientes fallan con
`ejecucion_concurrente`. Pasó el 2026-10-27 en MasVital: el nodo quedó
inutilizable hasta que alguien borró el archivo a mano.

Acá se prueba la rama de Windows en cualquier plataforma: se fuerza
`fcntl = None` para que el candado use el archivo creado en exclusiva.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from motoshop_api.erp.bankreconciliation import scraper
from motoshop_api.erp.bankreconciliation.node_config import NodeConfig, load_node_config
from motoshop_api.erp.bankreconciliation.scraper import (
    NOMBRE_LOCK,
    SessionSlotError,
    acquire_session_slot,
)


def _config(tmp_path: Path) -> NodeConfig:
    return load_node_config(
        {
            "BANK_SCRAPER_ENABLED": "true",
            "BANK_TENANT": "masvital",
            "BANK_ACCOUNT_LABEL": "MasVital",
            "BANK_CREDENTIAL_ENTRY": "bancolombia-masvital",
            "BANK_PROFILE_DIR": str(tmp_path / "perfil"),
        }
    )


def _ruta_candado(config: NodeConfig) -> Path:
    return config.profile_dir / NOMBRE_LOCK


@pytest.fixture()
def _sin_fcntl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fuerza la rama de Windows (archivo creado en exclusiva)."""
    monkeypatch.setattr(scraper, "fcntl", None)


def test_candado_huerfano_no_bloquea_la_corrida(tmp_path: Path, _sin_fcntl) -> None:
    """El archivo de un proceso muerto se descarta y la corrida entra."""
    config = _config(tmp_path)
    config.profile_dir.mkdir(parents=True, exist_ok=True)
    _ruta_candado(config).write_text("", encoding="utf-8")

    with acquire_session_slot(config) as slot:
        assert slot.config.tenant == config.tenant

    # Al salir se libera y el archivo no queda para la próxima.
    assert not _ruta_candado(config).exists()


def test_candado_con_duenio_vivo_sigue_bloqueando(tmp_path: Path, _sin_fcntl, monkeypatch) -> None:
    """Si el archivo no se puede borrar, hay alguien corriendo: se rechaza."""
    config = _config(tmp_path)
    config.profile_dir.mkdir(parents=True, exist_ok=True)
    _ruta_candado(config).write_text("", encoding="utf-8")
    monkeypatch.setattr(scraper._Candado, "_descartar_huerfano", lambda self: False)

    with pytest.raises(SessionSlotError) as excinfo:
        with acquire_session_slot(config):
            pass

    assert excinfo.value.motivo == "ejecucion_concurrente"


def test_liberar_deja_el_perfil_limpio(tmp_path: Path, _sin_fcntl) -> None:
    """Sin candado residual después de una corrida normal."""
    config = _config(tmp_path)

    with acquire_session_slot(config):
        assert _ruta_candado(config).exists()

    assert not _ruta_candado(config).exists()
