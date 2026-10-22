"""El `.env` del repo tiene que llegar a `os.environ` para la reconciliación bancaria.

`load_node_config` lee el entorno del proceso, no el objeto `Settings` de
pydantic. Antes de este arreglo, la API y los scripts recorrían el camino
bancario sólo si el shell que los lanzaba había exportado las `BANK_*` a mano:
el preflight dentro de `uv run` se quedaba esperando una frase maestra y la
tarea programada arrancaba sin tenant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from motoshop_api import config


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Deja `_candidate_env_paths` apuntando a un `.env` temporal y limpio."""
    archivo = tmp_path / ".env"
    monkeypatch.setattr(config, "_candidate_env_paths", lambda: [archivo])
    for clave in ("BANK_TENANT", "BANK_ACCOUNT_LABEL", "BANK_VAULT_BACKEND", "OTRA_COSA"):
        monkeypatch.delenv(clave, raising=False)
    return archivo


def test_las_bank_del_env_llegan_a_os_environ(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file.write_text(
        "BANK_TENANT=motoshop\nBANK_ACCOUNT_LABEL=Cuenta de Ahorros\n",
        encoding="utf-8",
    )

    config._sync_env_to_os_environ()

    assert config.os.environ["BANK_TENANT"] == "motoshop"
    assert config.os.environ["BANK_ACCOUNT_LABEL"] == "Cuenta de Ahorros"


def test_el_entorno_real_gana_sobre_el_archivo(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Un operador que exporta BANK_TENANT a mano no puede quedar pisado por el
    # `.env` del repo.
    monkeypatch.setenv("BANK_TENANT", "masvital")
    env_file.write_text("BANK_TENANT=motoshop\n", encoding="utf-8")

    config._sync_env_to_os_environ()

    assert config.os.environ["BANK_TENANT"] == "masvital"


def test_el_prefijo_no_sincroniza_claves_ajenas(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sólo se copian las claves de la lista blanca y las del prefijo bancario:
    # el `.env` no debe volcarse entero al entorno del proceso.
    env_file.write_text("BANK_TENANT=motoshop\nOTRA_COSA=no-deberia\n", encoding="utf-8")

    config._sync_env_to_os_environ()

    assert "OTRA_COSA" not in config.os.environ
