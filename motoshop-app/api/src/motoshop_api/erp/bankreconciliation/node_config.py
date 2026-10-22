"""Configuración por nodo para la conciliación de transferencias (S3).

Un proceso de API = un tenant. La configuración vive en el `.env` de cada máquina
(PC MasVital, PC MotoShop, Mac de desarrollo) y este módulo la carga con dos
garantías:

* **Fail-fast**: si al nodo le falta un dato obligatorio, la carga lanza
  `NodeConfigError` diciendo qué variable falta. Un nodo nunca arranca a medias
  ni opera con la configuración de otro tenant.
* **Diagnóstico**: `run_preflight` explica, sin revelar secretos, si el nodo está
  listo para raspar (etiqueta de cuenta, credencial del vault y perfil del
  navegador).

La ventana de consulta es, por defecto, el día en curso (00:00 → 23:59:59) y el
intervalo mínimo entre corridas es de 30 s (decisión D2 del diseño).
"""

from __future__ import annotations

import dataclasses
import datetime
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from motoshop_api.erp.bankreconciliation.vault import (
    CredentialVault,
    EntryMeta,
    VaultError,
    VaultNotFound,
)

# --- Variables de entorno ---

ENV_SCRAPER_ENABLED = "BANK_SCRAPER_ENABLED"
ENV_TENANT = "BANK_TENANT"
ENV_CREDENTIAL_ENTRY = "BANK_CREDENTIAL_ENTRY"
ENV_ACCOUNT_LABEL = "BANK_ACCOUNT_LABEL"
ENV_VAULT_BACKEND = "BANK_VAULT_BACKEND"
ENV_PROFILE_DIR = "BANK_PROFILE_DIR"
ENV_WINDOW_START = "BANK_WINDOW_START"
ENV_WINDOW_END = "BANK_WINDOW_END"

# --- Constantes ---

#: Convención de las entradas del vault: una por tenant, nunca una compartida.
CREDENTIAL_ENTRY_PREFIX = "bancolombia-"

#: Intervalo mínimo entre dos corridas del mismo nodo (decisión D2 del diseño).
MIN_INTERVAL_SECONDS = 30

#: Modo del directorio del perfil del navegador: sólo el propietario.
PROFILE_MODE = 0o700

#: Etiquetas de la ventana de consulta.
VENTANA_POR_DEFECTO = "dia"
VENTANA_PERSONALIZADA = "personalizada"

#: Límites del día en curso (hora local del nodo).
INICIO_DEL_DIA = datetime.time(0, 0, 0)
FIN_DEL_DIA = datetime.time(23, 59, 59)

#: Backends de custodia soportados. `dpapi` sigue siendo un stub (ADR-0026).
VAULT_BACKENDS = ("passphrase", "keychain", "dpapi")

VERDADEROS = frozenset({"1", "true", "t", "yes", "y", "si", "sí", "on"})
FALSOS = frozenset({"0", "false", "f", "no", "n", "off", ""})

FORMATOS_FECHA_HORA = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)

#: Raíz del repositorio: el perfil del navegador NUNCA debe vivir dentro.
REPO_ROOT = Path(__file__).resolve().parents[6]

# --- Motivos de fallo (códigos estables, documentados en `docs/runbook-banco.md`) ---

#: La credencial del tenant no está en el vault.
CODIGO_CREDENCIAL_AUSENTE = "credencial_ausente"
#: Falta la etiqueta de cuenta o no existe en la sesión del portal.
CODIGO_CUENTA_NO_ENCONTRADA = "cuenta_no_encontrada"
#: La sesión del portal expiró (sólo el scraper puede detectarlo).
CODIGO_SESION_EXPIRADA = "sesion_expirada"
#: El portal pidió una verificación antibot (sólo el scraper puede detectarlo).
CODIGO_ANTIBOT = "antibot"
#: El portal no respondió (sólo el scraper puede detectarlo).
CODIGO_PORTAL_NO_DISPONIBLE = "portal_no_disponible"

#: Motivos propios del diagnóstico local del nodo.
CODIGO_VAULT_NO_ACCESIBLE = "vault_no_accesible"
CODIGO_PERFIL_DENTRO_DEL_REPO = "perfil_dentro_del_repo"
CODIGO_PERFIL_INEXISTENTE = "perfil_inexistente"
CODIGO_PERFIL_PERMISOS = "perfil_permisos_insuficientes"
CODIGO_TENANT_NO_CONFIGURADO = "tenant_no_configurado"
CODIGO_CONFIGURACION_INVALIDA = "configuracion_invalida"

#: Motivos que sólo el scraper puede producir (S5). El preflight NO los inventa:
#: detectarlos exigiría una sesión viva contra el portal.
CODIGOS_DEL_SCRAPER = (
    CODIGO_SESION_EXPIRADA,
    CODIGO_ANTIBOT,
    CODIGO_PORTAL_NO_DISPONIBLE,
)

_CODIGO_POR_CAMPO = {
    ENV_TENANT: CODIGO_TENANT_NO_CONFIGURADO,
    ENV_ACCOUNT_LABEL: CODIGO_CUENTA_NO_ENCONTRADA,
    ENV_CREDENTIAL_ENTRY: CODIGO_CREDENCIAL_AUSENTE,
    ENV_VAULT_BACKEND: CODIGO_CONFIGURACION_INVALIDA,
}


class NodeConfigError(Exception):
    """La configuración del nodo es inválida o incompleta.

    `campo` identifica la variable de entorno responsable del fallo (o `None` si
    el problema no corresponde a una variable concreta), para que el diagnóstico
    pueda traducirlo a un motivo estable.
    """

    def __init__(self, message: str, campo: str | None = None) -> None:
        super().__init__(message)
        self.campo = campo


# --- Configuración del nodo ---


@dataclasses.dataclass(frozen=True)
class NodeConfig:
    """Configuración efectiva de un nodo (un tenant por proceso de API)."""

    tenant: str
    scraper_enabled: bool
    credential_entry: str
    account_label: str
    vault_backend: str
    profile_dir: Path
    window_start: datetime.datetime
    window_end: datetime.datetime
    min_interval_seconds: int = MIN_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        self._validar_presencia()
        self._validar_invariantes()

    def _validar_presencia(self) -> None:
        """Con el scraper habilitado no se puede operar sin tenant, etiqueta ni credencial."""
        if not self.scraper_enabled:
            return
        if not self.tenant:
            raise NodeConfigError(
                f"{ENV_TENANT} es obligatorio cuando {ENV_SCRAPER_ENABLED} está habilitado.",
                campo=ENV_TENANT,
            )
        if not self.account_label:
            raise NodeConfigError(
                f"{ENV_ACCOUNT_LABEL} es obligatorio cuando {ENV_SCRAPER_ENABLED} está habilitado.",
                campo=ENV_ACCOUNT_LABEL,
            )
        if not self.credential_entry:
            raise NodeConfigError(
                f"{ENV_CREDENTIAL_ENTRY} es obligatorio "
                f"cuando {ENV_SCRAPER_ENABLED} está habilitado.",
                campo=ENV_CREDENTIAL_ENTRY,
            )

    def _validar_invariantes(self) -> None:
        if self.window_end < self.window_start:
            raise NodeConfigError("La ventana de consulta no puede ser inversa.")
        if self.vault_backend not in VAULT_BACKENDS:
            raise NodeConfigError(
                f"{ENV_VAULT_BACKEND} debe ser uno de: {', '.join(VAULT_BACKENDS)}.",
                campo=ENV_VAULT_BACKEND,
            )
        if self.min_interval_seconds <= 0:
            raise NodeConfigError("El intervalo mínimo entre corridas debe ser mayor que cero.")

    @property
    def ventana_por_defecto(self) -> str:
        """`dia` si la ventana es el día en curso; `personalizada` si fue ajustada."""
        dia = self.window_start.date()
        es_dia_en_curso = self.window_start == datetime.datetime.combine(
            dia, INICIO_DEL_DIA
        ) and self.window_end == datetime.datetime.combine(dia, FIN_DEL_DIA)
        return VENTANA_POR_DEFECTO if es_dia_en_curso else VENTANA_PERSONALIZADA


def _parse_bool(bruto: str, campo: str) -> bool:
    """Interpreta un booleano de entorno; un valor desconocido es un error."""
    valor = bruto.strip().lower()
    if valor in VERDADEROS:
        return True
    if valor in FALSOS:
        return False
    raise NodeConfigError(
        f"{campo} debe ser un booleano (true/false/1/0), no {bruto!r}.",
        campo=campo,
    )


def _config_dir(env: Mapping[str, str]) -> Path:
    """Directorio de configuración del usuario.

    Aplica la misma regla que `vault._get_config_dir`, pero contra el `env`
    recibido en vez de `os.environ`: así la carga de la configuración es
    hermética y no depende del entorno real del proceso.
    """
    if sys.platform == "win32":
        base = env.get("APPDATA", "").strip() or "~/AppData/Roaming"
        return Path(base).expanduser() / "motoshop"
    xdg = env.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser() / "motoshop"
    return Path("~/.config").expanduser() / "motoshop"


def _resolve_credential_entry(env: Mapping[str, str], tenant: str) -> str:
    """Resuelve el nombre de la entrada del vault.

    Por defecto sigue la convención `bancolombia-<tenant>`; `BANK_CREDENTIAL_ENTRY`
    la sobreescribe. Si la variable está presente pero vacía, la credencial NO se
    puede resolver (y la validación lo convierte en `NodeConfigError`).
    """
    if ENV_CREDENTIAL_ENTRY in env:
        return env[ENV_CREDENTIAL_ENTRY].strip()
    if not tenant:
        return ""
    return f"{CREDENTIAL_ENTRY_PREFIX}{tenant}"


def _resolve_profile_dir(env: Mapping[str, str], tenant: str) -> Path:
    """Directorio del perfil del navegador: fuera del repositorio, siempre."""
    bruto = env.get(ENV_PROFILE_DIR, "").strip()
    if bruto:
        return Path(bruto).expanduser()
    base = _config_dir(env) / "bank-profile"
    return base / tenant if tenant else base


def _parse_datetime(bruto: str, campo: str, *, fin_de_dia: bool = False) -> datetime.datetime:
    """Interpreta una fecha/hora ISO-8601; un día a secas cubre el día completo."""
    for formato in FORMATOS_FECHA_HORA:
        try:
            return datetime.datetime.strptime(bruto, formato)
        except ValueError:
            continue
    try:
        dia = datetime.datetime.strptime(bruto, "%Y-%m-%d").date()
    except ValueError as error:
        raise NodeConfigError(
            f"{campo} no tiene un formato de fecha/hora válido: {bruto!r} (ISO-8601).",
            campo=campo,
        ) from error
    return datetime.datetime.combine(dia, FIN_DEL_DIA if fin_de_dia else INICIO_DEL_DIA)


def _resolve_window(env: Mapping[str, str]) -> tuple[datetime.datetime, datetime.datetime]:
    """Ventana de consulta: el día en curso por defecto, ajustable por entorno."""
    hoy = datetime.date.today()
    inicio = datetime.datetime.combine(hoy, INICIO_DEL_DIA)
    fin = datetime.datetime.combine(hoy, FIN_DEL_DIA)

    bruto_inicio = env.get(ENV_WINDOW_START, "").strip()
    bruto_fin = env.get(ENV_WINDOW_END, "").strip()
    if bruto_inicio:
        inicio = _parse_datetime(bruto_inicio, ENV_WINDOW_START)
    if bruto_fin:
        fin = _parse_datetime(bruto_fin, ENV_WINDOW_END, fin_de_dia=True)
    # Si sólo se ajusta un extremo, el otro acompaña al día indicado.
    if bruto_inicio and not bruto_fin:
        fin = datetime.datetime.combine(inicio.date(), FIN_DEL_DIA)
    if bruto_fin and not bruto_inicio:
        inicio = datetime.datetime.combine(fin.date(), INICIO_DEL_DIA)

    if fin < inicio:
        raise NodeConfigError(
            f"La ventana de consulta no puede ser inversa: {inicio} → {fin}.",
        )
    return inicio, fin


def _leer_variables(env: Mapping[str, str]) -> dict[str, Any]:
    """Traduce el entorno a los campos de `NodeConfig` (sin validar todavía)."""
    tenant = env.get(ENV_TENANT, "").strip()
    window_start, window_end = _resolve_window(env)
    return {
        "tenant": tenant,
        "scraper_enabled": _parse_bool(env.get(ENV_SCRAPER_ENABLED, ""), ENV_SCRAPER_ENABLED),
        "credential_entry": _resolve_credential_entry(env, tenant),
        "account_label": env.get(ENV_ACCOUNT_LABEL, "").strip(),
        "vault_backend": env.get(ENV_VAULT_BACKEND, "").strip() or "passphrase",
        "profile_dir": _resolve_profile_dir(env, tenant),
        "window_start": window_start,
        "window_end": window_end,
        "min_interval_seconds": MIN_INTERVAL_SECONDS,
    }


def _construir_sin_validar(**campos: Any) -> NodeConfig:
    """Construye un `NodeConfig` sin ejecutar la validación de `__post_init__`.

    Uso exclusivo del diagnóstico: el preflight DEBE poder recibir y reportar una
    configuración rota; si el constructor la rechazara, no podría explicar qué le
    falta al operador.
    """
    config = object.__new__(NodeConfig)
    for nombre, valor in campos.items():
        object.__setattr__(config, nombre, valor)
    return config


def load_node_config(env: Mapping[str, str] | None = None, *, estricto: bool = True) -> NodeConfig:
    """Carga la configuración del nodo desde el entorno.

    Args:
        env: variables a leer. Si es `None`, se usa `os.environ`.
        estricto: con `True` (por defecto) una configuración incompleta lanza
            `NodeConfigError`: es lo que debe pasar en el proceso de la API. Con
            `False` la configuración se carga tal cual, para que el preflight
            pueda *diagnosticar* una configuración rota en vez de reventar.

    Returns:
        La configuración del nodo.

    Raises:
        NodeConfigError: si la configuración es inválida o incompleta.
    """
    variables = dict(os.environ) if env is None else dict(env)
    campos = _leer_variables(variables)
    if estricto:
        return NodeConfig(**campos)
    return _construir_sin_validar(**campos)


# --- Preflight del nodo ---


class CredentialLookup(Protocol):
    """Vista mínima del vault que necesita el preflight: sólo metadatos.

    Existe para que sea estructuralmente imposible que el diagnóstico toque el
    material secreto (usuario o contraseña) de una entrada.
    """

    def list_entries(self) -> list[EntryMeta]: ...


@dataclasses.dataclass(frozen=True)
class PreflightCheck:
    """Resultado de una comprobación: nombre, estado y motivo."""

    name: str
    ok: bool
    motivo: str | None = None


@dataclasses.dataclass(frozen=True)
class PreflightResult:
    """Resumen del preflight: nunca contiene usuario ni contraseña."""

    tenant: str
    ok: bool
    checks: tuple[PreflightCheck, ...]

    @property
    def motivo(self) -> str | None:
        """Primer motivo de fallo (código estable) o `None` si todo está bien."""
        for check in self.checks:
            if not check.ok:
                return check.motivo
        return None

    @property
    def fallos(self) -> tuple[PreflightCheck, ...]:
        """Comprobaciones que fallaron."""
        return tuple(check for check in self.checks if not check.ok)


def _verificar_credencial(config: NodeConfig, vault: CredentialLookup | None) -> PreflightCheck:
    """Comprueba que el vault tiene la entrada de este tenant (y sólo su nombre)."""
    if not config.credential_entry:
        return PreflightCheck("credencial", False, CODIGO_CREDENCIAL_AUSENTE)
    try:
        lookup = (
            vault if vault is not None else CredentialVault(custody_backend=config.vault_backend)
        )
        entradas = lookup.list_entries()
    except VaultNotFound:
        # No hay vault o no hay entrada: para este nodo es lo mismo.
        return PreflightCheck("credencial", False, CODIGO_CREDENCIAL_AUSENTE)
    except VaultError:
        # Vault inaccesible o corrupto: es un problema de custodia, no de tenant.
        return PreflightCheck("credencial", False, CODIGO_VAULT_NO_ACCESIBLE)
    nombres = {entrada.name for entrada in entradas}
    if config.credential_entry not in nombres:
        return PreflightCheck("credencial", False, CODIGO_CREDENCIAL_AUSENTE)
    return PreflightCheck("credencial", True)


def _verificar_perfil(profile_dir: Path) -> PreflightCheck:
    """El perfil es la sesión del banco: fuera del repo y con permisos 0700."""
    try:
        perfil = profile_dir.expanduser().resolve()
        repo = REPO_ROOT.resolve()
    except OSError:
        return PreflightCheck("perfil", False, CODIGO_PERFIL_INEXISTENTE)
    if perfil == repo or repo in perfil.parents:
        return PreflightCheck("perfil", False, CODIGO_PERFIL_DENTRO_DEL_REPO)
    if not perfil.is_dir():
        return PreflightCheck("perfil", False, CODIGO_PERFIL_INEXISTENTE)
    if sys.platform != "win32":
        if stat.S_IMODE(perfil.stat().st_mode) != PROFILE_MODE:
            return PreflightCheck("perfil", False, CODIGO_PERFIL_PERMISOS)
    return PreflightCheck("perfil", True)


def run_preflight(
    config: NodeConfig,
    vault: CredentialLookup | None = None,
    *,
    verificar_credencial: bool = True,
) -> PreflightResult:
    """Comprueba que el nodo puede raspar: tenant, etiqueta, credencial y perfil.

    El resultado sólo contiene nombres, estados y motivos: nunca el usuario ni
    la contraseña del vault.

    Args:
        config: configuración del nodo a verificar.
        vault: fuente de la lista de entradas del vault. Si es `None`, se usa el
            `CredentialVault` real (que puede pedir la clave maestra).
        verificar_credencial: si es `False`, no se consulta el vault (el nodo de
            la nube no debe pedir ninguna clave).

    Returns:
        El resumen del preflight.
    """
    if not config.scraper_enabled:
        return PreflightResult(
            tenant=config.tenant,
            ok=True,
            checks=(PreflightCheck("scraper_deshabilitado", True),),
        )

    checks: list[PreflightCheck] = [PreflightCheck("configuracion", True)]
    checks.append(
        PreflightCheck(
            "tenant",
            bool(config.tenant),
            None if config.tenant else CODIGO_TENANT_NO_CONFIGURADO,
        )
    )
    checks.append(
        PreflightCheck(
            "etiqueta_cuenta",
            bool(config.account_label),
            None if config.account_label else CODIGO_CUENTA_NO_ENCONTRADA,
        )
    )
    if verificar_credencial:
        checks.append(_verificar_credencial(config, vault))
    checks.append(_verificar_perfil(config.profile_dir))

    return PreflightResult(
        tenant=config.tenant,
        ok=all(check.ok for check in checks),
        checks=tuple(checks),
    )


def _codigo_de_campo(campo: str | None) -> str:
    """Traduce la variable de entorno culpable al motivo estable del diagnóstico."""
    if campo is None:
        return CODIGO_CONFIGURACION_INVALIDA
    return _CODIGO_POR_CAMPO.get(campo, CODIGO_CONFIGURACION_INVALIDA)


def preflight_from_env(
    env: Mapping[str, str] | None = None, *, verificar_credencial: bool = True
) -> PreflightResult:
    """Diagnostica el nodo leyendo la configuración del entorno.

    A diferencia de `load_node_config`, una configuración incompleta NO interrumpe
    el diagnóstico: se reporta como un fallo más.
    """
    variables = dict(os.environ) if env is None else dict(env)
    try:
        config = load_node_config(variables, estricto=False)
    except NodeConfigError as error:
        return PreflightResult(
            tenant=variables.get(ENV_TENANT, "").strip(),
            ok=False,
            checks=(PreflightCheck("configuracion", False, _codigo_de_campo(error.campo)),),
        )
    return run_preflight(config, verificar_credencial=verificar_credencial)
