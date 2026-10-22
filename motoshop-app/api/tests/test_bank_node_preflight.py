"""Tests del preflight del nodo (`run_preflight`).

El preflight es la herramienta de diagnóstico del nodo local: comprueba que la
configuración está completa, que la credencial del tenant existe en el vault y
que el perfil del navegador vive fuera del repositorio con permisos 0700.

El resultado NUNCA revela el usuario ni la contraseña: sólo nombres, estados y
motivos.
"""

from __future__ import annotations

import datetime
import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest

from motoshop_api.erp.bankreconciliation.node_config import (
    REPO_ROOT,
    PreflightResult,
    load_node_config,
    run_preflight,
)
from motoshop_api.erp.bankreconciliation.vault import Entry, EntryMeta


class _FakeVault:
    """Doble del vault que sólo expone metadatos.

    `get_entry` existe a propósito (con secretos) para comprobar que el preflight
    NUNCA lo usa: la credencial se resuelve por nombre, sin material secreto.
    """

    USUARIO = "usuario_secreto"
    CLAVE = "clave_secreta_123"

    def __init__(self, nombres: list[str]) -> None:
        self._nombres = nombres
        self.llamadas_get_entry: list[str] = []

    def list_entries(self) -> list[EntryMeta]:
        return [
            EntryMeta(name=nombre, updated_at=datetime.datetime(2026, 1, 1, 12, 0, 0))
            for nombre in self._nombres
        ]

    def get_entry(self, name: str) -> Entry:
        self.llamadas_get_entry.append(name)
        return Entry(
            username=self.USUARIO,
            password=self.CLAVE,
            updated_at=datetime.datetime(2026, 1, 1, 12, 0, 0),
        )


def _perfil_valido(tmp_path: Path) -> Path:
    """Directorio de perfil fuera del repo con permisos 0700."""
    perfil = tmp_path / "bank-profile" / "motoshop"
    perfil.mkdir(parents=True)
    if sys.platform != "win32":
        perfil.chmod(0o700)
    return perfil


def _env_nodo(perfil: Path, **extra: str) -> dict[str, str]:
    env = {
        "BANK_SCRAPER_ENABLED": "true",
        "BANK_TENANT": "motoshop",
        "BANK_ACCOUNT_LABEL": "AHORROS MOTO SHOP",
        "BANK_PROFILE_DIR": str(perfil),
    }
    env.update(extra)
    return env


# --- Etiqueta de cuenta ---


def test_preflight_falla_si_falta_la_etiqueta_de_cuenta(tmp_path: Path) -> None:
    """Sin `BANK_ACCOUNT_LABEL` el nodo no sabe qué cuenta abrir."""
    perfil = _perfil_valido(tmp_path)
    env = _env_nodo(perfil)
    del env["BANK_ACCOUNT_LABEL"]

    config = load_node_config(env, estricto=False)
    resultado = run_preflight(config, vault=_FakeVault(["bancolombia-motoshop"]))

    assert isinstance(resultado, PreflightResult)
    assert resultado.ok is False
    assert resultado.motivo == "cuenta_no_encontrada"


# --- Credencial del tenant ---


def test_preflight_falla_si_la_entrada_de_vault_del_tenant_no_existe(tmp_path: Path) -> None:
    """La credencial se resuelve por tenant: no se usa la de otro tenant."""
    perfil = _perfil_valido(tmp_path)
    config = load_node_config(_env_nodo(perfil), estricto=False)

    resultado = run_preflight(config, vault=_FakeVault(["bancolombia-otro-tenant"]))

    assert resultado.ok is False
    assert resultado.motivo == "credencial_ausente"


# --- Perfil del navegador ---


def test_preflight_falla_si_el_perfil_del_nodo_esta_dentro_del_repo(tmp_path: Path) -> None:
    """El perfil ES la sesión del banco: no puede vivir dentro del repositorio."""
    perfil = REPO_ROOT / "motoshop-app" / "api" / "bank-profile"
    config = load_node_config(_env_nodo(perfil), estricto=False)

    resultado = run_preflight(config, vault=_FakeVault(["bancolombia-motoshop"]))

    assert resultado.ok is False
    assert resultado.motivo == "perfil_dentro_del_repo"


@pytest.mark.skipif(
    sys.platform == "win32", reason="Los permisos de directorio se comportan distinto en Windows"
)
def test_preflight_falla_si_el_perfil_no_tiene_permisos_700(tmp_path: Path) -> None:
    """Un perfil legible por otros usuarios del equipo queda rechazado."""
    perfil = tmp_path / "bank-profile" / "motoshop"
    perfil.mkdir(parents=True)
    perfil.chmod(0o755)
    config = load_node_config(_env_nodo(perfil), estricto=False)

    resultado = run_preflight(config, vault=_FakeVault(["bancolombia-motoshop"]))

    assert resultado.ok is False
    assert resultado.motivo == "perfil_permisos_insuficientes"
    assert stat.S_IMODE(perfil.stat().st_mode) == 0o755


def test_preflight_falla_si_el_perfil_no_existe(tmp_path: Path) -> None:
    """Un perfil inexistente todavía no se puede usar para raspar."""
    perfil = tmp_path / "bank-profile" / "motoshop"
    config = load_node_config(_env_nodo(perfil), estricto=False)

    resultado = run_preflight(config, vault=_FakeVault(["bancolombia-motoshop"]))

    assert resultado.ok is False
    assert resultado.motivo == "perfil_inexistente"


# --- Caso feliz ---


def test_preflight_ok_devuelve_resumen_sin_revelar_secretos(tmp_path: Path) -> None:
    """El resumen del preflight no contiene ni el usuario ni la contraseña."""
    perfil = _perfil_valido(tmp_path)
    config = load_node_config(_env_nodo(perfil), estricto=False)
    vault = _FakeVault(["bancolombia-motoshop"])

    resultado = run_preflight(config, vault=vault)

    assert resultado.ok is True
    assert resultado.motivo is None

    resumen = repr(resultado)
    assert _FakeVault.USUARIO not in resumen
    assert _FakeVault.CLAVE not in resumen
    # La credencial se resolvió por nombre: nunca se pidió el material secreto.
    assert vault.llamadas_get_entry == []


# --- Comportamientos adicionales del diagnóstico ---


def test_el_preflight_reporta_todos_los_problemas(tmp_path: Path) -> None:
    """Un diagnóstico útil lista todas las fallas, no sólo la primera."""
    perfil = tmp_path / "bank-profile" / "motoshop"
    perfil.mkdir(parents=True)
    if sys.platform != "win32":
        perfil.chmod(0o755)
    env = _env_nodo(perfil)
    del env["BANK_ACCOUNT_LABEL"]

    config = load_node_config(env, estricto=False)
    resultado = run_preflight(config, vault=_FakeVault([]))

    motivos = {check.motivo for check in resultado.fallos}
    assert "cuenta_no_encontrada" in motivos
    assert "credencial_ausente" in motivos
    if sys.platform != "win32":
        # El modo 0o700 del perfil no tiene equivalente en Windows: ahí el
        # preflight no reporta esta falla.
        assert "perfil_permisos_insuficientes" in motivos


def test_el_scraper_deshabilitado_no_pide_la_credencial(tmp_path: Path) -> None:
    """El nodo de la nube no raspa: el preflight no toca el vault."""
    config = load_node_config({"BANK_SCRAPER_ENABLED": "false"})

    resultado = run_preflight(config, vault=_FakeVault([]))

    assert resultado.ok is True
    assert resultado.motivo is None
    assert [check.name for check in resultado.checks] == ["scraper_deshabilitado"]


# --- CLI del operador ---


def _cargar_cli():
    """Carga `scripts/bank_verify.py` como módulo (no es un paquete instalable)."""
    ruta = Path(__file__).resolve().parents[1] / "scripts" / "bank_verify.py"
    spec = importlib.util.spec_from_file_location("bank_verify", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _limpiar_entorno_banco(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deja el entorno sin variables `BANK_*` heredadas de la máquina del dev."""
    for clave in list(os.environ):
        if clave.startswith("BANK_"):
            monkeypatch.delenv(clave, raising=False)


def test_el_cli_termina_con_cero_cuando_el_preflight_pasa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Un nodo bien configurado termina con código 0."""
    _limpiar_entorno_banco(monkeypatch)
    monkeypatch.setenv("BANK_TENANT", "motoshop")
    monkeypatch.setenv("BANK_ACCOUNT_LABEL", "AHORROS MOTO SHOP")
    monkeypatch.setenv("BANK_PROFILE_DIR", str(_perfil_valido(tmp_path)))
    monkeypatch.setenv("BANK_SCRAPER_ENABLED", "true")

    codigo = _cargar_cli().main(["--tenant", "motoshop", "--check"])
    salida = capsys.readouterr()

    assert codigo == 0
    assert "PREFLIGHT OK" in salida.out


def test_el_cli_termina_con_uno_y_motivo_cuando_el_preflight_falla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Un nodo mal configurado termina con código 1 y el motivo explícito."""
    _limpiar_entorno_banco(monkeypatch)
    monkeypatch.setenv("BANK_TENANT", "motoshop")
    monkeypatch.setenv("BANK_PROFILE_DIR", str(_perfil_valido(tmp_path)))
    monkeypatch.setenv("BANK_SCRAPER_ENABLED", "true")

    codigo = _cargar_cli().main(["--tenant", "motoshop", "--check"])
    salida = capsys.readouterr()

    assert codigo == 1
    assert "cuenta_no_encontrada" in salida.err
    assert "PREFLIGHT FALLO" in salida.err
