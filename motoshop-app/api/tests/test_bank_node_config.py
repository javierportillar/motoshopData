"""Tests de la configuración por nodo (`motoshop_api.erp.bankreconciliation.node_config`).

Un proceso de API = un tenant. La configuración vive en el `.env` de cada máquina
(PC MasVital, PC MotoShop, Mac de desarrollo). Si a un nodo le falta un dato
obligatorio, NO debe arrancar: falla rápido (`NodeConfigError`) diciendo qué falta.

La nube (`BANK_SCRAPER_ENABLED=false`) no raspa: su configuración es válida sin
credencial y sin etiqueta de cuenta.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

from motoshop_api.erp.bankreconciliation.node_config import (
    CREDENTIAL_ENTRY_PREFIX,
    FIN_DEL_DIA,
    INICIO_DEL_DIA,
    MIN_INTERVAL_SECONDS,
    NodeConfigError,
    load_node_config,
)


def _env_nodo(**extra: str) -> dict[str, str]:
    """Entorno mínimo de un nodo local con el scraper habilitado."""
    env = {
        "BANK_SCRAPER_ENABLED": "true",
        "BANK_TENANT": "motoshop",
        "BANK_ACCOUNT_LABEL": "AHORROS MOTO SHOP",
        "BANK_PROFILE_DIR": "/tmp/motoshop/bank-profile/motoshop",
    }
    env.update(extra)
    return env


# --- Fail-fast: el nodo no arranca con la configuración incompleta ---


def test_scraper_habilitado_sin_tenant_falla_rapido() -> None:
    """Sin `BANK_TENANT` el nodo no debe arrancar: falta el tenant que sirve."""
    env = _env_nodo()
    del env["BANK_TENANT"]

    with pytest.raises(NodeConfigError, match="BANK_TENANT"):
        load_node_config(env)


def test_scraper_habilitado_sin_etiqueta_de_cuenta_falla_rapido() -> None:
    """Sin `BANK_ACCOUNT_LABEL` el nodo no debe arrancar: no sabría qué cuenta abrir."""
    env = _env_nodo()
    del env["BANK_ACCOUNT_LABEL"]

    with pytest.raises(NodeConfigError, match="BANK_ACCOUNT_LABEL"):
        load_node_config(env)


def test_scraper_habilitado_sin_credencial_resuelta_falla_rapido() -> None:
    """Con `BANK_CREDENTIAL_ENTRY` presente pero vacía la credencial no se puede resolver."""
    env = _env_nodo(BANK_CREDENTIAL_ENTRY="   ")

    with pytest.raises(NodeConfigError, match="BANK_CREDENTIAL_ENTRY"):
        load_node_config(env)


def test_scraper_deshabilitado_no_exige_credencial_ni_etiqueta() -> None:
    """La nube no raspa: su configuración es válida sin credencial y sin etiqueta."""
    config = load_node_config({"BANK_SCRAPER_ENABLED": "false"})

    assert config.scraper_enabled is False
    assert config.tenant == ""
    assert config.account_label == ""
    assert config.credential_entry == ""


# --- Convención de la entrada del vault ---


@pytest.mark.parametrize(
    ("tenant", "esperada"),
    [("motoshop", "bancolombia-motoshop"), ("masvital", "bancolombia-masvital")],
)
def test_entrada_de_vault_por_tenant_usa_la_convencion_bancolombia_tenant(
    tenant: str, esperada: str
) -> None:
    """Cada tenant resuelve SU entrada de vault: nunca una compartida entre tenants."""
    config = load_node_config(_env_nodo(BANK_TENANT=tenant))

    assert config.credential_entry == esperada
    assert config.credential_entry == f"{CREDENTIAL_ENTRY_PREFIX}{tenant}"


def test_la_entrada_de_vault_puede_sobrescribirse() -> None:
    """`BANK_CREDENTIAL_ENTRY` manda sobre la convención cuando está definida."""
    config = load_node_config(_env_nodo(BANK_CREDENTIAL_ENTRY="bancolombia-corporativo"))

    assert config.credential_entry == "bancolombia-corporativo"


# --- Ventana de consulta ---


def test_ventana_por_defecto_es_el_dia_en_curso() -> None:
    """Sin ventana explícita, la consulta cubre el día en curso (00:00 → 23:59:59)."""
    config = load_node_config(_env_nodo())
    hoy = datetime.date.today()

    assert config.window_start == datetime.datetime.combine(hoy, INICIO_DEL_DIA)
    assert config.window_end == datetime.datetime.combine(hoy, FIN_DEL_DIA)
    assert config.ventana_por_defecto == "dia"


def test_la_ventana_se_puede_sobrescribir_por_entorno() -> None:
    """`BANK_WINDOW_START` / `BANK_WINDOW_END` ajustan la ventana y queda auditable."""
    config = load_node_config(
        _env_nodo(BANK_WINDOW_START="2026-10-01", BANK_WINDOW_END="2026-10-05")
    )

    assert config.window_start == datetime.datetime(2026, 10, 1, 0, 0, 0)
    assert config.window_end == datetime.datetime(2026, 10, 5, 23, 59, 59)
    assert config.ventana_por_defecto == "personalizada"


def test_una_ventana_invertida_falla_rapido() -> None:
    """Una ventana con el fin antes del inicio es un error de configuración."""
    with pytest.raises(NodeConfigError, match="ventana"):
        load_node_config(_env_nodo(BANK_WINDOW_START="2026-10-05", BANK_WINDOW_END="2026-10-01"))


# --- Otros controles de configuración ---


def test_un_flag_de_scraper_invalido_falla_rapido() -> None:
    """Un valor que no es booleano no se interpreta en silencio."""
    with pytest.raises(NodeConfigError, match="BANK_SCRAPER_ENABLED"):
        load_node_config(_env_nodo(BANK_SCRAPER_ENABLED="quiz"))


def test_un_backend_de_vault_no_soportado_falla_rapido() -> None:
    """`dpapi` sigue siendo un stub: no se puede seleccionar desde la configuración."""
    with pytest.raises(NodeConfigError, match="BANK_VAULT_BACKEND"):
        load_node_config(_env_nodo(BANK_VAULT_BACKEND="dpapi"))


def test_el_intervalo_minimo_es_de_30_segundos() -> None:
    """Decisión D2 del diseño: 30 s mínimo entre corridas del mismo nodo."""
    config = load_node_config(_env_nodo())

    assert config.min_interval_seconds == 30
    assert config.min_interval_seconds == MIN_INTERVAL_SECONDS


def test_el_perfil_por_defecto_vive_fuera_del_repo(tmp_path: Path) -> None:
    """Sin `BANK_PROFILE_DIR` el perfil va al directorio de configuración del usuario."""
    env = _env_nodo()
    del env["BANK_PROFILE_DIR"]
    env.setdefault("APPDATA", str(tmp_path))
    env["XDG_CONFIG_HOME"] = str(tmp_path)

    config = load_node_config(env)

    if sys.platform == "win32":
        base = Path(env["APPDATA"]) / "motoshop"
    else:
        base = tmp_path / "motoshop"
    assert config.profile_dir == base / "bank-profile" / "motoshop"
