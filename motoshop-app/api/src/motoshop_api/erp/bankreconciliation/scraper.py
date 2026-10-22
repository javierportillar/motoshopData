"""Scraper del portal Bancolombia: cuenta por etiqueta, paginación y OTP (S5).

Este módulo habla con el portal a través de un **doble** (`PortalSession`):
en producción es Playwright (`PlaywrightPortalSession`) y en las pruebas es
`tests/bank_fakes.PortalFalso`. El scraper no sabe cuál es: por eso la suite
offline corre **sin navegador y sin red**, y por eso el mismo código es el que
se ejecuta contra el portal real.

Garantías del módulo
--------------------

* **La cuenta se abre por etiqueta**, nunca por índice: el nodo declara
  `BANK_ACCOUNT_LABEL` y si esa etiqueta no está en la sesión el scrape falla
  con `cuenta_no_encontrada` **sin leer ninguna otra cuenta**.
* **Todo fallo deja cero movimientos**: el scraper arma la lista en memoria y
  sólo la devuelve cuando terminó bien; el error se propaga antes.
* **El OTP se pide en la consola del nodo** (`input()`), nunca en el navegador,
  y no se persiste ni se registra: no viaja en ningún log ni en el resultado.
* **Un nodo, una corrida**: `acquire_session_slot()` usa un lock file y un
  intervalo mínimo de 30 s dentro del perfil del navegador.
* **Playwright se importa perezosamente**: el paquete importa (y la suite
  offline corre) sin la dependencia instalada.

Lo que NO se puede verificar aquí
---------------------------------

El DOM real del portal nunca se vio. Los selectores viven en `portal_pages.py`
y esta navegación es una *hipótesis* razonable, no un hecho comprobable: hace
falta una corrida viva para confirmarla.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import logging
import os
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from motoshop_api.erp.bankreconciliation.node_config import (
    CODIGO_ANTIBOT,
    CODIGO_CREDENCIAL_AUSENTE,
    CODIGO_CUENTA_NO_ENCONTRADA,
    CODIGO_PORTAL_NO_DISPONIBLE,
    CODIGO_SESION_EXPIRADA,
    PROFILE_MODE,
    REPO_ROOT,
    NodeConfig,
)
from motoshop_api.erp.bankreconciliation.parser import (
    FormatoDeMovimientoInvalido,
    MovementDirection,
    parse_movement_row,
)
from motoshop_api.erp.bankreconciliation.portal_pages import (
    CONTRATO_PORTAAL,
    ENV_URL_BASE,
    URL_BASE_PORTAAL,
    LocatorSpec,
    PortalContract,
)
from motoshop_api.erp.bankreconciliation.vault import CredentialVault, Entry, VaultError

try:  # pragma: no cover - POSIX only
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

__all__ = [
    "BankScrapeError",
    "BankScraper",
    "CODIGO_CREDENCIAL_INVALIDA",
    "MOTIVO_CONCURRENTE",
    "MOTIVO_INTERVALO",
    "MOTIVO_PERFIL_DENTRO_DEL_REPO",
    "PlaywrightPortalSession",
    "PortalSession",
    "ScrapeResult",
    "ScrapedMovement",
    "SessionSlot",
    "SessionSlotError",
    "acquire_session_slot",
    "default_session_factory",
    "identificador_externo",
]

# --- Códigos de error del portal (estables; los documenta el runbook) ---

#: El portal rechazó la credencial o el código de un solo uso.
CODIGO_CREDENCIAL_INVALIDA = "credencial_invalida"

#: Motivos por los que no se puede tomar el turno de sesión del nodo.
MOTIVO_CONCURRENTE = "ejecucion_concurrente"
MOTIVO_INTERVALO = "intervalo_minimo"
MOTIVO_PERFIL_DENTRO_DEL_REPO = "perfil_dentro_del_repo"

#: Lock de exclusión mutua: vive en el perfil, así que es **por máquina**
#: (dos tenants sobre el mismo perfil NO pueden raspar a la vez).
NOMBRE_LOCK = ".banco-sesion.lock"

#: Prefijo de la marca de la corrida anterior. La marca es **por tenant**:
#: el intervalo mínimo acota las corridas *de un nodo* (un tenant), no las de
#: dos tenants distintos que compartieran el mismo directorio de perfil.
PREFIJO_STAMP = ".banco-sesion"

#: Variable de entorno para correr el navegador sin ventana.
ENV_HEADLESS = "BANK_BROWSER_HEADLESS"

#: Marcas de texto con las que el portal se queja (todo en minúsculas).
MARCAS_CREDENCIAL_INVALIDA = (
    "credenciales incorrectas",
    "credencial inválida",
    "contraseña incorrecta",
    "clave incorrecta",
    "datos incorrectos",
    "usuario o contraseña",
)
MARCAS_SESION_EXPIRADA = (
    "sesión expiró",
    "sesion expiro",
    "inicie sesión nuevamente",
    "vuelva a iniciar sesión",
)
MARCAS_ANTIBOT = (
    "no eres un robot",
    "verificación de seguridad",
    "verificacion de seguridad",
    "desafío de seguridad",
    "captcha",
)


# --- Errores ---


class BankScrapeError(Exception):
    """Fallo del portal con un código estable y **sin movimientos parciales**.

    Attributes:
        codigo: código estable del fallo (`credencial_ausente`,
            `credencial_invalida`, `sesion_expirada`, `antibot`,
            `portal_no_disponible`, `cuenta_no_encontrada`).
        mensaje: explicación en español, sin secretos.
    """

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje


class SessionSlotError(Exception):
    """No se pudo tomar el turno de sesión del nodo.

    O bien hay otra corrida en curso (lock), o bien la anterior fue hace
    menos del intervalo mínimo, o bien el perfil del navegador está dentro
    del repositorio.

    Attributes:
        motivo: `ejecucion_concurrente`, `intervalo_minimo` o
            `perfil_dentro_del_repo`.
        mensaje: explicación en español.
    """

    def __init__(self, motivo: str, mensaje: str) -> None:
        super().__init__(f"{motivo}: {mensaje}")
        self.motivo = motivo
        self.mensaje = mensaje


# --- La sesión del portal (doble de pruebas o Playwright real) ---


class PortalSession(Protocol):
    """Lo que el scraper le pide a la sesión del portal.

    Es el contrato que implementa `tests/bank_fakes.PortalFalso` (offline) y
    `PlaywrightPortalSession` (producción). Si el portal cambia, se ajusta una
    de las dos implementaciones, no este protocolo.
    """

    def ir_a_autenticacion(self) -> None: ...

    def escribir_credenciales(self, usuario: str, clave: str) -> None: ...

    def enviar_formulario(self) -> None: ...

    def hay_codigo_otp(self) -> bool: ...

    def escribir_codigo_otp(self, codigo: str) -> None: ...

    def ir_a_home(self) -> None: ...

    def ir_a_movimientos(self) -> None: ...

    def url_actual(self) -> str: ...

    def texto_visible(self) -> str: ...

    def tarjetas_de_cuenta(self) -> list[str]: ...

    def abrir_cuenta(self, etiqueta: str) -> None: ...

    def filas_de_movimientos(self) -> list[list[str]]: ...

    def hay_pagina_siguiente(self) -> bool: ...

    def ir_a_pagina_siguiente(self) -> None: ...

    def cerrar(self) -> None: ...


# --- Resultado del scrape ---


@dataclass(frozen=True)
class ScrapedMovement:
    """Un movimiento leído del portal, con la página de la que salió.

    Attributes:
        id_externo: identificador estable del movimiento (lo usa la ingesta
            como clave de idempotencia).
        fecha: día del movimiento.
        descripcion: texto de la operación.
        referencia: referencia ya saneada (sin el sufijo `" null"`).
        referencia_utilizable: `False` si la referencia está vacía o es sólo
            ceros (con esas referencias no se puede conciliar).
        pagador_nombre: pagador, sólo si la descripción empieza con
            `PAGO QR`.
        valor: importe exacto (`Decimal`).
        direccion: `INGRESO` o `EGRESO` (por el signo del valor).
        es_candidato_pago: `True` sólo si el movimiento es un ingreso.
        pagina: página de la tabla de la que salió (1 = primera).
        cuenta_origen: etiqueta de la cuenta leída.
    """

    id_externo: str
    fecha: datetime.date
    descripcion: str
    referencia: str
    referencia_utilizable: bool
    pagador_nombre: str
    valor: Decimal
    direccion: MovementDirection
    es_candidato_pago: bool
    pagina: int
    cuenta_origen: str


@dataclass(frozen=True)
class ScrapeResult:
    """Lo que una corrida de scrape devuelve.

    Attributes:
        tenant: tenant del nodo.
        cuenta: etiqueta de la cuenta leída.
        ventana: `(inicio, fin)` de la ventana consultada.
        paginas: cuántas páginas de la tabla se recorrieron.
        movimientos: movimientos **dentro de la ventana** (vacío si no hay).
        leido_en: instante de la corrida.
    """

    tenant: str
    cuenta: str
    ventana: tuple[datetime.datetime, datetime.datetime]
    paginas: int
    movimientos: tuple[ScrapedMovement, ...]
    leido_en: datetime.datetime

    @property
    def candidatos(self) -> tuple[ScrapedMovement, ...]:
        """Sólo los ingresos: los que pueden conciliarse contra una factura."""
        return tuple(mov for mov in self.movimientos if mov.es_candidato_pago)


def identificador_externo(
    fecha: datetime.date,
    referencia: str,
    valor: Decimal,
    descripcion: str,
) -> str:
    """Identificador estable de un movimiento del portal.

    El portal **no muestra un identificador** de la fila, así que se deriva de
    su contenido (fecha, referencia, importe y descripción). Es determinista:
    la misma fila produce siempre el mismo identificador, y por eso la ingesta
    es idempotente. La referencia sola **no** sirve: dos pagos distintos del
    mismo día pueden compartirla.

    Args:
        fecha: día del movimiento.
        referencia: referencia saneada.
        valor: importe exacto.
        descripcion: descripción de la operación.

    Returns:
        Identificador hexadecimal de 64 caracteres.
    """
    crudo = f"{fecha.isoformat()}|{referencia}|{valor}|{descripcion}"
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


# --- El turno de sesión (lock + intervalo mínimo) ---


@dataclass(frozen=True)
class SessionSlot:
    """Turno de sesión tomado por este proceso.

    Attributes:
        config: configuración del nodo.
        perfil: directorio del perfil del navegador.
        iniciado_en: instante de la corrida (una sola lectura del reloj).
    """

    config: NodeConfig
    perfil: Path
    iniciado_en: datetime.datetime


class _Candado:
    """Candado de exclusión mutua sobre un archivo.

    En POSIX usa `flock` (se libera solo si el proceso muere); en Windows usa
    la creación exclusiva del archivo (se borra al liberar).
    """

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self._fd: int | None = None

    def adquirir(self) -> None:
        """Toma el candado o lanza `SessionSlotError` (`ejecucion_concurrente`)."""
        if fcntl is not None:
            self._fd = os.open(self._ruta, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                os.close(self._fd)
                self._fd = None
                raise SessionSlotError(
                    MOTIVO_CONCURRENTE,
                    "ya hay una corrida en curso en este nodo",
                ) from exc
            return
        try:  # pragma: no cover - Windows
            self._fd = os.open(self._ruta, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError as exc:  # pragma: no cover - Windows
            raise SessionSlotError(
                MOTIVO_CONCURRENTE,
                "ya hay una corrida en curso en este nodo",
            ) from exc

    def liberar(self) -> None:
        """Devuelve el candado (idempotente)."""
        if self._fd is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows
                self._ruta.unlink(missing_ok=True)
        finally:
            os.close(self._fd)
            self._fd = None


def _preparar_perfil(config: NodeConfig) -> Path:
    """Crea el perfil del navegador (fuera del repo, modo 700) y lo devuelve."""
    perfil = config.profile_dir.expanduser()
    repo = REPO_ROOT.resolve()
    resuelta = perfil.resolve()
    if resuelta == repo or repo in resuelta.parents:
        raise SessionSlotError(
            MOTIVO_PERFIL_DENTRO_DEL_REPO,
            "el perfil del navegador no puede vivir dentro del repositorio",
        )
    perfil.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        perfil.chmod(PROFILE_MODE)
    return perfil


def _slug(tenant: str) -> str:
    """Nombre de archivo seguro para el tenant."""
    limpio = "".join(c if (c.isalnum() or c in "-_") else "-" for c in tenant).strip("-")
    return limpio or "default"


def _ruta_stamp(perfil: Path, tenant: str) -> Path:
    """Marca de la corrida anterior de este tenant, dentro del perfil."""
    return perfil / f"{PREFIJO_STAMP}.{_slug(tenant)}.ultima"


def _leer_stamp(ruta: Path) -> datetime.datetime | None:
    """Instante de la corrida anterior (`None` si no hay o está corrupto)."""
    try:
        return datetime.datetime.fromisoformat(ruta.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _escribir_stamp(ruta: Path, instante: datetime.datetime) -> None:
    """Guarda el instante de la corrida (no es un secreto)."""
    ruta.write_text(instante.isoformat(), encoding="utf-8")
    if sys.platform != "win32":
        ruta.chmod(0o600)


@contextlib.contextmanager
def acquire_session_slot(
    config: NodeConfig,
    *,
    reloj: Callable[[], datetime.datetime] | None = None,
) -> Iterator[SessionSlot]:
    """Toma el turno de sesión del nodo: lock + intervalo mínimo.

    El lock y la marca de la corrida anterior viven **dentro de
    `config.profile_dir`** (fuera del repositorio, modo 700). El lock es
    **por perfil** (una sola sesión de navegador a la vez) y la marca es **por
    tenant** (el intervalo mínimo acota las corridas de un nodo). El reloj se
    lee **una sola vez** por corrida: el intervalo se mide contra la corrida
    anterior, no contra el momento de la comprobación.

    Args:
        config: configuración del nodo.
        reloj: reloj inyectable (las pruebas lo fijan).

    Yields:
        El turno tomado (`SessionSlot`).

    Raises:
        SessionSlotError: si hay otra corrida en curso, si la anterior fue
            hace menos del intervalo mínimo, o si el perfil está dentro del
            repositorio.
    """
    ahora_fn = reloj or (lambda: datetime.datetime.now())
    perfil = _preparar_perfil(config)
    candado = _Candado(perfil / NOMBRE_LOCK)
    candado.adquirir()
    try:
        ahora = ahora_fn()
        stamp = _ruta_stamp(perfil, config.tenant)
        previa = _leer_stamp(stamp)
        if previa is not None:
            transcurrido = (ahora - previa).total_seconds()
            if transcurrido < config.min_interval_seconds:
                raise SessionSlotError(
                    MOTIVO_INTERVALO,
                    (
                        f"la corrida anterior fue hace {int(transcurrido)} s y el "
                        f"intervalo mínimo es de {config.min_interval_seconds} s"
                    ),
                )
        _escribir_stamp(stamp, ahora)
        yield SessionSlot(config=config, perfil=perfil, iniciado_en=ahora)
    finally:
        candado.liberar()


# --- El scraper ---


def _pedir_codigo_en_consola(prompt: str) -> str:
    """Pide el código de un solo uso **en la consola del nodo**.

    El código se escribe en la terminal local del operador: no se guarda en
    disco, no va en el log y no viaja en el resultado. (No se usa `getpass`
    porque el portal lo pide en la pantalla del banco, no como una contraseña
    de la bóveda; aun así, la terminal del nodo es un lugar Trusted.)
    """
    return input(prompt)


class BankScraper:
    """Lee los movimientos de la cuenta del tenant en el portal.

    Args:
        session_factory: fábrica de la sesión del portal. Recibe la
            `NodeConfig` y devuelve una `PortalSession`. Por defecto usa
            Playwright con el perfil persistente del nodo.
        vault: fuente de la credencial (`get_entry`). Por defecto usa el
            `CredentialVault` del backend configurado.
        contrato: contrato del portal (selectores y rutas).
        pedir_codigo: cómo se pide el código OTP. Por defecto `input()` en la
            consola del nodo.
        reloj: reloj inyectable (las pruebas lo fijan).
        logger: logger del nodo.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[NodeConfig], PortalSession] | None = None,
        vault: Any | None = None,
        contrato: PortalContract = CONTRATO_PORTAAL,
        pedir_codigo: Callable[[str], str] | None = None,
        reloj: Callable[[], datetime.datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory or default_session_factory
        self._vault = vault
        self._contrato = contrato
        self._pedir_codigo = pedir_codigo or _pedir_codigo_en_consola
        self._reloj = reloj or (lambda: datetime.datetime.now())
        self._log = logger or logging.getLogger(__name__)

    # --- API pública ---

    def scrape(self, config: NodeConfig) -> ScrapeResult:
        """Raspa la cuenta del tenant dentro de la ventana configurada.

        Args:
            config: configuración del nodo.

        Returns:
            El resultado de la corrida (movimientos dentro de la ventana).

        Raises:
            SessionSlotError: si el turno de sesión no se puede tomar.
            BankScrapeError: si el portal falla; el error lleva un código
                estable y **no** deja movimientos parciales.
        """
        with acquire_session_slot(config, reloj=self._reloj) as slot:
            return self._raspar(config, slot)

    # --- implementación ---

    def _raspar(self, config: NodeConfig, slot: SessionSlot) -> ScrapeResult:
        entrada = self._credencial(config)
        session = self._session_factory(config)
        try:
            self._autenticar(session, entrada)
            self._ir_a_home(session)
            session.ir_a_movimientos()
            cuenta = self._abrir_cuenta(session, config)
            movimientos, paginas = self._leer_movimientos(session, config, cuenta)
        finally:
            with contextlib.suppress(Exception):
                session.cerrar()

        self._log.info(
            "Scrape del nodo '%s' terminado: cuenta '%s', %d páginas, %d movimientos.",
            config.tenant,
            cuenta,
            paginas,
            len(movimientos),
        )
        return ScrapeResult(
            tenant=config.tenant,
            cuenta=cuenta,
            ventana=(config.window_start, config.window_end),
            paginas=paginas,
            movimientos=movimientos,
            leido_en=slot.iniciado_en,
        )

    def _credencial(self, config: NodeConfig) -> Entry:
        """Resuelve la credencial **de este tenant** (nunca la de otro)."""
        vault = self._vault
        if vault is None:
            try:
                vault = CredentialVault(custody_backend=config.vault_backend)
            except VaultError as exc:
                raise BankScrapeError(
                    CODIGO_CREDENCIAL_AUSENTE,
                    "no se pudo abrir la bóveda de credenciales",
                ) from exc
        try:
            return vault.get_entry(config.credential_entry)
        except VaultError as exc:
            # No existe la entrada, o la bóveda no se pudo leer: en los dos
            # casos la credencial de este tenant no está disponible.
            raise BankScrapeError(
                CODIGO_CREDENCIAL_AUSENTE,
                f"no hay credencial para el tenant '{config.tenant}'",
            ) from exc

    def _autenticar(self, session: PortalSession, entrada: Entry) -> None:
        """Entra al portal y resuelve el código de un solo uso si lo pide."""
        session.ir_a_autenticacion()
        session.escribir_credenciales(entrada.username, entrada.password)
        session.enviar_formulario()

        if self._texto_indica(session, MARCAS_CREDENCIAL_INVALIDA):
            raise BankScrapeError(
                CODIGO_CREDENCIAL_INVALIDA,
                "el portal rechazó las credenciales de este tenant",
            )

        if session.hay_codigo_otp():
            # El código lo pide el nodo, en su consola. No se persiste ni se
            # registra: sólo viaja de la consola al formulario del navegador.
            codigo = self._pedir_codigo(self._contrato.otp_prompt)
            session.escribir_codigo_otp(codigo)
            session.enviar_formulario()
            if session.hay_codigo_otp():
                raise BankScrapeError(
                    CODIGO_CREDENCIAL_INVALIDA,
                    "el portal no aceptó el código de verificación",
                )

        if self._texto_indica(session, MARCAS_CREDENCIAL_INVALIDA):
            raise BankScrapeError(
                CODIGO_CREDENCIAL_INVALIDA,
                "el portal rechazó las credenciales de este tenant",
            )
        if session.url_actual().rstrip("/").endswith(self._contrato.path_auth):
            raise BankScrapeError(
                CODIGO_CREDENCIAL_INVALIDA,
                "el portal no dejó entrar con la credencial de este tenant",
            )

    def _ir_a_home(self, session: PortalSession) -> None:
        """Va a la pantalla principal y detecta la sesión expirada."""
        session.ir_a_home()
        if self._texto_indica(session, MARCAS_SESION_EXPIRADA):
            raise BankScrapeError(
                CODIGO_SESION_EXPIRADA,
                "la sesión del portal expiró: hay que volver a entrar a mano",
            )
        if session.url_actual().rstrip("/").endswith(self._contrato.path_auth):
            raise BankScrapeError(
                CODIGO_SESION_EXPIRADA,
                "el portal devolvió el nodo a la pantalla de autenticación",
            )

    def _abrir_cuenta(self, session: PortalSession, config: NodeConfig) -> str:
        """Abre la cuenta **por etiqueta** y devuelve la etiqueta leída."""
        tarjetas = session.tarjetas_de_cuenta()
        elegida = self._buscar_etiqueta(tarjetas, config.account_label)
        if elegida is None:
            raise BankScrapeError(
                CODIGO_CUENTA_NO_ENCONTRADA,
                (
                    f"la etiqueta de cuenta '{config.account_label}' no está en la "
                    "sesión del portal: no se leyó ninguna otra cuenta"
                ),
            )
        session.abrir_cuenta(elegida)
        return elegida

    @staticmethod
    def _buscar_etiqueta(tarjetas: Sequence[str], etiqueta: str) -> str | None:
        """La etiqueta del tenant dentro de las tarjetas (por texto, no por orden)."""
        objetivo = " ".join(etiqueta.split()).casefold()
        for tarjeta in tarjetas:
            if " ".join(str(tarjeta).split()).casefold() == objetivo:
                return tarjeta
        return None

    def _leer_movimientos(
        self,
        session: PortalSession,
        config: NodeConfig,
        cuenta: str,
    ) -> tuple[tuple[ScrapedMovement, ...], int]:
        """Recorre las páginas de la tabla y devuelve los movimientos de la ventana."""
        movimientos: list[ScrapedMovement] = []
        pagina = 1
        while True:
            self._verificar_antibot(session)
            filas = session.filas_de_movimientos()
            self._verificar_antibot(session)

            leidos = [self._interpretar(fila, pagina, cuenta) for fila in filas]
            movimientos.extend(
                mov for mov in leidos if self._dentro_de_ventana(mov, config)
            )

            if not session.hay_pagina_siguiente():
                break
            if self._ventana_cubierta(leidos, config):
                break
            session.ir_a_pagina_siguiente()
            pagina += 1

        return tuple(movimientos), pagina

    def _interpretar(self, fila: Sequence[str], pagina: int, cuenta: str) -> ScrapedMovement:
        """Convierte una fila del portal en movimiento (delega el formato al parser)."""
        try:
            parseado = parse_movement_row(fila)
        except FormatoDeMovimientoInvalido as exc:
            raise BankScrapeError(
                CODIGO_PORTAL_NO_DISPONIBLE,
                f"una fila de la tabla no se pudo interpretar: {exc}",
            ) from exc
        return ScrapedMovement(
            id_externo=identificador_externo(
                parseado.fecha,
                parseado.referencia,
                parseado.valor,
                parseado.descripcion,
            ),
            fecha=parseado.fecha,
            descripcion=parseado.descripcion,
            referencia=parseado.referencia,
            referencia_utilizable=parseado.referencia_utilizable,
            pagador_nombre=parseado.pagador_nombre,
            valor=parseado.valor,
            direccion=parseado.direccion,
            es_candidato_pago=parseado.es_candidato_pago,
            pagina=pagina,
            cuenta_origen=cuenta,
        )

    @staticmethod
    def _dentro_de_ventana(movimiento: ScrapedMovement, config: NodeConfig) -> bool:
        """¿El movimiento cae en la ventana? (El portal sólo muestra fechas.)"""
        return (
            config.window_start.date()
            <= movimiento.fecha
            <= config.window_end.date()
        )

    @staticmethod
    def _ventana_cubierta(
        leidos: Sequence[ScrapedMovement],
        config: NodeConfig,
    ) -> bool:
        """¿Se puede dejar de paginar? Sólo si la tabla va de antigua a nueva.

        El portal ordena las páginas de más antigua a más nueva (hipótesis): si
        una página entera es anterior a la ventana y viene ordenada, las
        páginas siguientes no pueden traer nada de la ventana. Con el orden
        inverso la condición nunca se cumple y se recorren todas las páginas.
        """
        if not leidos:
            return False
        fechas = [mov.fecha for mov in leidos]
        if max(fechas) >= config.window_start.date():
            return False
        return fechas == sorted(fechas)

    @staticmethod
    def _texto_indica(session: PortalSession, marcas: Sequence[str]) -> bool:
        """¿El texto visible de la sesión contiene alguna de las marcas?"""
        texto = session.texto_visible().casefold()
        return any(marca in texto for marca in marcas)

    def _verificar_antibot(self, session: PortalSession) -> None:
        """El desafío antibot es un fallo explícito, no algo que se esquive."""
        if self._texto_indica(session, MARCAS_ANTIBOT):
            raise BankScrapeError(
                CODIGO_ANTIBOT,
                "el portal pidió una verificación de seguridad: hay que entrar a mano",
            )


# --- Sesión real (Playwright) ---


def _headless() -> bool:
    """¿El navegador corre sin ventana? (por defecto, con ventana)."""
    return os.environ.get(ENV_HEADLESS, "").strip().lower() in {"1", "true", "yes", "si"}


def default_session_factory(config: NodeConfig) -> PortalSession:
    """Abre el navegador real con el perfil persistente del nodo.

    Playwright se importa **dentro** de la función: el paquete importa (y la
    suite offline corre) sin la dependencia instalada.

    Args:
        config: configuración del nodo (de ahí sale el perfil y la etiqueta).

    Returns:
        La sesión lista para raspar.

    Raises:
        BankScrapeError: si Playwright no está instalado o el navegador no
            arranca.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BankScrapeError(
            CODIGO_PORTAL_NO_DISPONIBLE,
            (
                "Playwright no está instalado: corré `uv sync --extra bank` y "
                "`playwright install chromium` en el nodo"
            ),
        ) from exc

    base = os.environ.get(ENV_URL_BASE, "").strip() or URL_BASE_PORTAAL
    gestor = sync_playwright().start()
    try:
        # Sin `trace`, sin `video` y sin capturas: el login es un secreto.
        # Nunca corras el nodo con `DEBUG=pw:api`: Playwright imprime en
        # pantalla los valores que se escriben en los formularios.
        contexto = gestor.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir.expanduser()),
            headless=_headless(),
        )
    except Exception as exc:
        with contextlib.suppress(Exception):
            gestor.stop()
        raise BankScrapeError(
            CODIGO_PORTAL_NO_DISPONIBLE,
            f"no se pudo abrir el navegador del nodo: {exc}",
        ) from exc

    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    return PlaywrightPortalSession(
        gestor=gestor,
        contexto=contexto,
        pagina=pagina,
        contrato=CONTRATO_PORTAAL,
        base_url=base,
    )


class PlaywrightPortalSession:
    """La sesión real del portal sobre Playwright (API síncrona).

    Traduce el `PortalSession` a la pantalla: los selectores salen del
    contrato (`portal_pages.py`) y las operaciones de red que fallen se
    traducen a `BankScrapeError("portal_no_disponible")`.
    """

    def __init__(
        self,
        *,
        gestor: Any,
        contexto: Any,
        pagina: Any,
        contrato: PortalContract,
        base_url: str,
    ) -> None:
        self._gestor = gestor
        self._contexto = contexto
        self._pagina = pagina
        self._contrato = contrato
        self._base_url = base_url.rstrip("/")

    # --- navegación ---

    def ir_a_autenticacion(self) -> None:
        """Abre la pantalla de autenticación."""
        self._ir(self._contrato.path_auth)

    def ir_a_home(self) -> None:
        """Abre la pantalla principal (si la sesión expiró, redirige al login)."""
        self._ir(self._contrato.path_home)

    def ir_a_movimientos(self) -> None:
        """Abre la pantalla de cuentas y sus movimientos."""
        self._ir(self._contrato.path_movimientos)

    def url_actual(self) -> str:
        """URL de la página actual."""
        return self._pagina.url

    def texto_visible(self) -> str:
        """Texto visible de la página (para detectar avisos del portal)."""
        return self._llamar(self._pagina.locator("body").inner_text)

    # --- autenticación ---

    def escribir_credenciales(self, usuario: str, clave: str) -> None:
        """Escribe usuario y contraseña (nunca se registran)."""
        self._llamar(self._localizar(self._contrato.login_usuario).fill, usuario)
        self._llamar(self._localizar(self._contrato.login_clave).fill, clave)

    def enviar_formulario(self) -> None:
        """Envía el formulario que esté en pantalla (login o código)."""
        if self.hay_codigo_otp():
            boton = self._localizar(self._contrato.otp_enviar)
        else:
            boton = self._localizar(self._contrato.login_enviar)
        self._llamar(boton.click)

    def hay_codigo_otp(self) -> bool:
        """¿El portal pide un código de un solo uso?"""
        campo = self._localizar(self._contrato.otp_codigo)
        try:
            return campo.count() > 0 and campo.is_visible()
        except Exception:
            return False

    def escribir_codigo_otp(self, codigo: str) -> None:
        """Escribe el código en el campo del portal (no se persiste ni se registra)."""
        self._llamar(self._localizar(self._contrato.otp_codigo).fill, codigo)

    # --- cuentas y movimientos ---

    def tarjetas_de_cuenta(self) -> list[str]:
        """Etiquetas de las tarjetas de cuenta, en el orden de la pantalla."""
        tarjetas = self._localizar(self._contrato.account_cards)
        etiquetas: list[str] = []
        for tarjeta in self._llamar(tarjetas.all):
            texto = self._etiqueta_de(tarjeta)
            if texto:
                etiquetas.append(texto)
        return etiquetas

    def abrir_cuenta(self, etiqueta: str) -> None:
        """Abre la cuenta con esa etiqueta (nunca por posición)."""
        tarjetas = self._localizar(self._contrato.account_cards)
        for tarjeta in self._llamar(tarjetas.all):
            if self._etiqueta_de(tarjeta) == etiqueta:
                self._llamar(tarjeta.click)
                self._abrir_pestana_movimientos()
                return
        raise BankScrapeError(
            CODIGO_CUENTA_NO_ENCONTRADA,
            f"la etiqueta de cuenta '{etiqueta}' no está en la pantalla de cuentas",
        )

    def filas_de_movimientos(self) -> list[list[str]]:
        """Celdas de cada fila de la tabla "Tus movimientos"."""
        tabla = self._localizar(self._contrato.movements_table)
        filas: list[list[str]] = []
        for fila in self._llamar(tabla.get_by_role("row").all):
            celdas = [celda.inner_text().strip() for celda in fila.get_by_role("cell").all()]
            if celdas:
                filas.append(celdas)
        return filas

    def hay_pagina_siguiente(self) -> bool:
        """¿Hay una página siguiente disponible?"""
        boton = self._localizar(self._contrato.pagination_next)
        try:
            return boton.count() > 0 and boton.is_enabled()
        except Exception:
            return False

    def ir_a_pagina_siguiente(self) -> None:
        """Avanza a la página siguiente de la tabla."""
        self._llamar(self._localizar(self._contrato.pagination_next).click)

    def cerrar(self) -> None:
        """Cierra el navegador y su perfil."""
        with contextlib.suppress(Exception):
            self._contexto.close()
        with contextlib.suppress(Exception):
            self._gestor.stop()

    # --- internos ---

    def _ir(self, ruta: str) -> None:
        """Navega a una ruta del portal (URL absoluta)."""
        url = f"{self._base_url}{ruta if ruta.startswith('/') else f'/{ruta}'}"
        self._llamar(self._pagina.goto, url, wait_until="domcontentloaded")

    def _abrir_pestana_movimientos(self) -> None:
        """Abre la pestaña "Movimientos" si la pantalla la tiene."""
        pestana = self._localizar(self._contrato.movements_tab)
        try:
            if pestana.count() > 0 and pestana.is_visible():
                self._llamar(pestana.click)
        except Exception:
            # La pestaña puede no existir en el DOM real: la tabla manda.
            pass

    def _etiqueta_de(self, tarjeta: Any) -> str:
        """Etiqueta (nombre visible) de una tarjeta de cuenta."""
        try:
            etiqueta = self._localizar(self._contrato.account_card_label, tarjeta)
            if etiqueta.count() > 0:
                return etiqueta.inner_text().strip()
        except Exception:
            pass
        return str(tarjeta.inner_text()).strip()

    def _localizar(self, spec: LocatorSpec, raiz: Any | None = None) -> Any:
        """Primer localizador que encuentra algo (rol → texto → etiqueta → CSS)."""
        base = raiz if raiz is not None else self._pagina
        candidatos: list[Any] = []
        if spec.rol and spec.nombre:
            candidatos.append(base.get_by_role(spec.rol, name=spec.nombre))
        if spec.rol and not spec.nombre:
            candidatos.append(base.get_by_role(spec.rol))
        if spec.texto:
            candidatos.append(base.get_by_text(spec.texto, exact=True))
        if spec.etiqueta:
            candidatos.append(base.get_by_label(spec.etiqueta))
        if spec.testid:
            candidatos.append(base.get_by_test_id(spec.testid))
        if spec.css:
            candidatos.append(base.locator(spec.css))
        for locator in candidatos:
            if locator.count() > 0:
                return locator
        return candidatos[0] if candidatos else base.locator("body")

    @staticmethod
    def _llamar(accion: Callable[..., Any], *args: Any) -> Any:
        """Ejecuta una operación de Playwright y traduce sus fallos."""
        try:
            return accion(*args)
        except BankScrapeError:
            raise
        except Exception as exc:
            raise BankScrapeError(
                CODIGO_PORTAL_NO_DISPONIBLE,
                f"el portal no respondió: {exc}",
            ) from exc
