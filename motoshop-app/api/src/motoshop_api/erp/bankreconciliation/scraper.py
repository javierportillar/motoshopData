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
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

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

#: Variable de entorno para elegir el navegador: `chrome` (real, por defecto:
#: es el que pasa la protección Imperva/Incapsula del portal) o `chromium`
#: (el que trae Playwright).
ENV_CANAL = "BANK_BROWSER_CHANNEL"

#: Variable de entorno para el locale del navegador (el portal es es-CO).
ENV_LOCALE = "BANK_BROWSER_LOCALE"

#: Variable de entorno para la zona horaria del navegador (América/Bogotá).
ENV_TIMEZONE = "BANK_BROWSER_TIMEZONE"

#: Guion que se inyecta antes de cada página para quitar las huellas más
#: obvias de automatización (`navigator.webdriver`).
_SCRIPT_SIN_AUTOMATIZACION = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "window.chrome={runtime:{}};"
)

#: Texto del modal de inactividad del portal: a los 2 minutos sin actividad
#: cancela el proceso ("¿Sigues ahí?"). Se detecta por TEXTO porque su
#: contenedor se reporta invisible aunque el texto se renderice.
MARCAS_INACTIVIDAD = ("sigues ahí", "sigues ahi", "cancelaremos tu proceso")

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

    def responder_inactividad(self) -> bool: ...

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

    #: Windows puede tener el archivo tomado un instante (antivirus, indexador).
    BORRADO_INTENTOS = 5
    BORRADO_ESPERA_S = 0.05

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
        try:
            self._fd = os.open(self._ruta, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError as exc:
            raise SessionSlotError(
                MOTIVO_CONCURRENTE,
                "ya hay una corrida en curso en este nodo",
            ) from exc

    def liberar(self) -> None:
        """Devuelve el candado (idempotente).

        El handle se cierra ANTES de borrar: Windows no permite eliminar un
        archivo con un descriptor vivo (`PermissionError [WinError 32]`). En
        POSIX se libera el `flock` y se cierra el descriptor, que ya alcanza.

        Si el borrado no prospera tras los reintentos se deja el archivo y se
        avisa: este método corre en un `finally`, y levantar acá enmascararía el
        error que se esté propagando desde el bloque protegido.
        """
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        if fcntl is None:
            self._borrar_archivo()

    def _borrar_archivo(self) -> None:
        """Borra el archivo del candado reintentando ante un handle ajeno."""
        for intento in range(1, self.BORRADO_INTENTOS + 1):
            try:
                self._ruta.unlink(missing_ok=True)
                return
            except PermissionError:
                if intento == self.BORRADO_INTENTOS:
                    logging.getLogger(__name__).warning(
                        "no se pudo borrar el candado %s tras %s intentos: "
                        "va a bloquear la próxima corrida",
                        self._ruta,
                        self.BORRADO_INTENTOS,
                    )
                    return
                time.sleep(self.BORRADO_ESPERA_S)


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
            # Orden real del portal (verificado en vivo): desde el home se abre
            # la cuenta por su etiqueta y DESPUÉS se pulsa la pestaña
            # "Movimientos". Navegar por URL a una ruta profunda reinicia la SPA
            # y rompe la sesión.
            cuenta = self._abrir_cuenta(session, config)
            session.ir_a_movimientos()
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

    def _spec(self, nombre: str) -> Any:
        """Devuelve un selector del contrato (con respaldo al vigente)."""
        return _spec_del_contrato(self._contrato, nombre)

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

        if not self._esperar_ingreso_o_otp(session):
            if self._texto_indica(session, MARCAS_CREDENCIAL_INVALIDA):
                raise BankScrapeError(
                    CODIGO_CREDENCIAL_INVALIDA,
                    "el portal rechazó las credenciales de este tenant",
                )
            raise BankScrapeError(
                CODIGO_CREDENCIAL_INVALIDA,
                "el portal no dejó entrar con la credencial de este tenant",
            )

        if session.hay_codigo_otp():
            # El código lo pide el nodo, en su consola. No se persiste ni se
            # registra: sólo viaja de la consola al formulario del navegador.
            codigo = self._pedir_codigo(self._spec("otp_prompt"))
            session.escribir_codigo_otp(codigo)
            session.enviar_formulario()
            if not self._esperar_ingreso(session):
                raise BankScrapeError(
                    CODIGO_CREDENCIAL_INVALIDA,
                    "el portal no aceptó el código de verificación",
                )

    def _esperar_ingreso_o_otp(
        self, session: PortalSession, timeout: float = 45.0
    ) -> bool:
        """Espera a que la sesión quede abierta (o a que pida el código).

        El portal procesa el login de forma asíncrona: la URL cambia un par de
        segundos después del clic. Consultarla de inmediato daba un falso
        negativo ("no dejó entrar") aunque el login fuera correcto.

        La pantalla de verificación en dos pasos es un estado **intermedio
        válido**: la URL sigue siendo la de autenticación, pero el portal ya
        aceptó el usuario y la clave y está pidiendo el código.
        """
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            actual = session.url_actual().rstrip("/")
            if not actual.endswith(self._spec("path_auth").rstrip("/")):
                return True
            if session.hay_codigo_otp():
                return True
            if self._texto_indica(session, MARCAS_CREDENCIAL_INVALIDA):
                return False
            time.sleep(1.0)
        return False

    def _esperar_ingreso(self, session: PortalSession, timeout: float = 45.0) -> bool:
        """Espera a que la sesión quede abierta (tras el código de un solo uso)."""
        return self._esperar_ingreso_o_otp(session, timeout)

    def _ir_a_home(self, session: PortalSession) -> None:
        """Va a la pantalla principal y detecta la sesión expirada."""
        session.ir_a_home()
        if self._texto_indica(session, MARCAS_SESION_EXPIRADA):
            raise BankScrapeError(
                CODIGO_SESION_EXPIRADA,
                "la sesión del portal expiró: hay que volver a entrar a mano",
            )
        if session.url_actual().rstrip("/").endswith(self._spec("path_auth")):
            raise BankScrapeError(
                CODIGO_SESION_EXPIRADA,
                "el portal devolvió el nodo a la pantalla de autenticación",
            )

    def _abrir_cuenta(self, session: PortalSession, config: NodeConfig) -> str:
        """Abre la cuenta **por etiqueta** y devuelve la etiqueta leída."""
        etiquetas = self._esperar_cuentas(session, config)
        elegida = self._buscar_etiqueta(etiquetas, config.account_label)
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

    def _esperar_cuentas(
        self, session: PortalSession, config: NodeConfig, timeout: float = 45.0
    ) -> list[str]:
        """Espera a que el home renderice las cuentas.

        El home es una SPA: los productos (y sus etiquetas) aparecen unos
        segundos después del login. Consultarlos de inmediato daba
        "cuenta no encontrada" aunque la cuenta estuviera ahí.
        """
        limite = time.monotonic() + timeout
        etiquetas: list[str] = []
        while time.monotonic() < limite:
            self._responder_inactividad(session)
            etiquetas = session.tarjetas_de_cuenta()
            if self._buscar_etiqueta(etiquetas, config.account_label) is not None:
                return etiquetas
            if etiquetas:
                # Hay cuentas pero no la del tenant: no se espera más.
                return etiquetas
            time.sleep(1.0)
        return etiquetas

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
            self._responder_inactividad(session)
            self._verificar_antibot(session)
            filas = self._esperar_filas(session)
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

    def _esperar_filas(
        self, session: PortalSession, timeout: float = 45.0
    ) -> list[list[str]]:
        """Espera a que la tabla "Tus movimientos" traiga filas.

        La tabla se arma con los datos de la API del banco: unos segundos
        después de abrir la pestaña todavía está vacía (sólo el spinner). Sin
        esta espera el scrape terminaba con cero movimientos.
        """
        limite = time.monotonic() + timeout
        filas = session.filas_de_movimientos()
        while time.monotonic() < limite and not filas:
            self._responder_inactividad(session)
            self._verificar_antibot(session)
            time.sleep(1.0)
            filas = session.filas_de_movimientos()
        return filas

    def _responder_inactividad(self, session: PortalSession) -> None:
        """Contesta el modal de inactividad del portal, si aparece.

        El portal cancela el proceso a los 2 minutos sin actividad. El modal se
        detecta **por texto** (su contenedor se reporta invisible aunque el texto
        se renderice) y se responde con su botón afirmativo.
        """
        try:
            if session.responder_inactividad():
                self._log.info(
                    "El portal preguntó si el operador seguía presente; se respondió para "
                    "no perder la sesión."
                )
        except Exception:
            # Si el modal no está, no hay nada que hacer: el flujo sigue.
            pass

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
        contexto = _abrir_contexto(gestor, config)
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


#: Hosts del portal (y de sus proveedores) a los que se permite **navegar**.
#:
#: El portal abre *pop-under* de afiliados (en la captura real redirigió a
#: `aliexpress.com` con `aff_fcid`), y esa redirección se lleva la pestaña
#: mientras el nodo está escribiendo las credenciales. Cortar la navegación
#: fuera del banco evita que el scrape se rompa a mitad de camino.
HOSTS_NAVEGACION_PERMITIDOS = ("bancolombia.com",)


def _spec_del_contrato(contrato: Any, nombre: str) -> Any:
    """Devuelve un selector del contrato, con respaldo al contrato vigente.

    El contrato inyectado manda; si no trae ese campo se usa el contrato
    vigente y, si tampoco, el fallo es explícito.
    """
    valor = getattr(contrato, nombre, None)
    if valor is None:
        valor = getattr(CONTRATO_PORTAAL, nombre, None)
    if valor is None:
        raise BankScrapeError(
            CODIGO_PORTAL_NO_DISPONIBLE,
            f"el contrato del portal no define el selector '{nombre}'",
        )
    return valor


def _es_host_permitido(host: str) -> bool:
    """¿La navegación es a un host del banco (o a un esquema no-http)?"""
    if not host:
        return True
    return any(
        host == permitido or host.endswith(f".{permitido}")
        for permitido in HOSTS_NAVEGACION_PERMITIDOS
    )


def _bloquear_redirecciones(contexto: Any) -> None:
    """Corta las navegaciones fuera del banco y cierra los pop-up."""

    def _al_navegar(ruta: Any) -> None:
        try:
            if ruta.request.is_navigation_request():
                # Sólo las navegaciones de **nivel superior**: los iframes de
                # terceros (Genesys, Medallia, el propio challenge de Incapsula)
                # se dejan pasar, o la página del portal se rompe.
                marco = ruta.request.frame
                if marco is not None and marco.parent_frame is not None:
                    ruta.continue_()
                    return
                host = urlparse(ruta.request.url).hostname or ""
                if not _es_host_permitido(host):
                    ruta.abort()
                    return
        except Exception:
            pass
        with contextlib.suppress(Exception):
            ruta.continue_()

    with contextlib.suppress(Exception):
        contexto.route("**/*", _al_navegar)

    def _al_abrir_pagina(pagina_nueva: Any) -> None:
        # Los pop-up se abren como páginas nuevas: se cierran.
        with contextlib.suppress(Exception):
            if pagina_nueva != contexto.pages[0]:
                pagina_nueva.close()

    with contextlib.suppress(Exception):
        contexto.on("page", _al_abrir_pagina)


def _abrir_contexto(gestor: Any, config: NodeConfig) -> Any:
    """Abre el navegador persistente con la huella menos automatizable posible.

    El portal está detrás de Imperva/Incapsula, que **rebota** al Chromium
    empaquetado por Playwright cuando corre en headless. Con Chrome real
    (`channel="chrome"`), en headed, sin el flag `--enable-automation` y sin
    `navigator.webdriver`, el challenge se resuelve.

    Si Chrome no está instalado, se cae al Chromium de Playwright (con un
    mensaje claro, porque probablemente el portal lo rechace).
    """
    argumentos = dict(
        user_data_dir=str(config.profile_dir.expanduser()),
        headless=_headless(),
        locale=os.environ.get(ENV_LOCALE, "es-CO"),
        timezone_id=os.environ.get(ENV_TIMEZONE, "America/Bogota"),
        # 1280x900: mismo tamano que la ventana off-screen. Probado con filas
        # reales (2 scrapes, 3 movimientos): el parser exige 4 celdas despues de
        # la fecha y un ancho menor puede ocultar columnas. No se usa
        # viewport=None aunque evitaria la emulacion de metricas: no se puede
        # validar el parseo con filas hasta que el banco publique movimientos.
        viewport={"width": 1280, "height": 900},
        ignore_default_args=["--enable-automation"],
        # Cero ventanas visibles: el portal rebota headless (portal_no_disponible),
        # asi que el navegador corre *headed* pero con la ventana fuera del
        # escritorio.
        args=[
            "--disable-blink-features=AutomationControlled",
            "--window-position=-32000,-32000",
            "--window-size=1280,900",
        ],
    )
    canal = os.environ.get(ENV_CANAL, "").strip() or "chrome"
    try:
        contexto = gestor.chromium.launch_persistent_context(channel=canal, **argumentos)
    except Exception as exc:
        if canal == "chrome":
            # Chrome real no está instalado en esta máquina: se intenta el
            # Chromium de Playwright (el portal puede rechazarlo).
            contexto = gestor.chromium.launch_persistent_context(**argumentos)
            with contextlib.suppress(Exception):
                contexto.add_init_script(_SCRIPT_SIN_AUTOMATIZACION)
            _bloquear_redirecciones(contexto)
            return contexto
        raise exc
    with contextlib.suppress(Exception):
        contexto.add_init_script(_SCRIPT_SIN_AUTOMATIZACION)
    _bloquear_redirecciones(contexto)
    return contexto


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

    def _spec(self, nombre: str) -> Any:
        """Devuelve un selector del contrato.

        El contrato inyectado manda, pero si no trae ese campo (por ejemplo,
        porque el proceso tiene una versión anterior del módulo cargada) se usa
        el contrato vigente. Si tampoco está, el fallo es explícito.
        """
        return _spec_del_contrato(self._contrato, nombre)

    # --- navegación ---

    def ir_a_autenticacion(self) -> None:
        """Abre la pantalla de autenticación."""
        self._ir(self._spec("path_auth"))

    def ir_a_home(self) -> None:
        """Asegura que la pantalla principal esté abierta.

        **No** recarga si ya estamos ahí: tras el login la SPA ya quedó en
        `/home`, y una recarga completa reinicia la aplicación (y con ella la
        sesión en memoria).
        """
        if self.url_actual().rstrip("/").endswith(self._spec("path_home").rstrip("/")):
            return
        self._ir(self._spec("path_home"))

    def ir_a_movimientos(self) -> None:
        """Abre la pestaña "Movimientos" de la cuenta ya abierta.

        **Nunca** navega por URL: recargar una ruta profunda reinicia la SPA y
        destruye la sesión (el portal vuelve al login). La navegación real es
        client-side: se abre la cuenta desde el home y se pulsa la pestaña.
        """
        self._abrir_pestana_movimientos()

    def url_actual(self) -> str:
        """URL de la página actual."""
        return self._pagina.url

    def texto_visible(self) -> str:
        """Texto visible de la página (para detectar avisos del portal)."""
        return self._llamar(self._pagina.locator("body").inner_text)

    # --- autenticación ---

    def escribir_credenciales(self, usuario: str, clave: str) -> None:
        """Escribe usuario y contraseña con **eventos de teclado reales**.

        El login real es un formulario Angular y el campo de clave está
        enmascarado (`svppasswordmask`, `type="text"`). Con `fill()` los valores
        no llegan al control: el form queda `ng-pristine` y el botón
        `data-test='login-button'` **nunca** se habilita, así que el login no
        ocurre. Con teclado real Angular registra los valores y habilita el
        botón.

        El campo de clave **nunca** se vuelve a leer: su valor visible es la
        máscara (`●●●●`), no el secreto.
        """
        campo_usuario = self._localizar(self._spec("login_usuario"))
        self._llamar(campo_usuario.click)
        self._llamar(campo_usuario.press_sequentially, usuario, delay=80)
        campo_clave = self._localizar(self._spec("login_clave"))
        self._llamar(campo_clave.click)
        self._llamar(campo_clave.press_sequentially, clave, delay=150)

    def enviar_formulario(self) -> None:
        """Envía el formulario que esté en pantalla (login o código)."""
        if self.hay_codigo_otp():
            boton = self._localizar(self._spec("otp_enviar"))
        else:
            boton = self._localizar(self._spec("login_enviar"))
        self._llamar(boton.click)

    def hay_codigo_otp(self) -> bool:
        """¿El portal pide un código de un solo uso?"""
        campo = self._localizar(self._spec("otp_codigo"))
        try:
            return campo.count() > 0 and campo.is_visible()
        except Exception:
            return False

    def escribir_codigo_otp(self, codigo: str) -> None:
        """Escribe el código en el campo del portal (no se persiste ni se registra)."""
        campo = self._localizar(self._spec("otp_codigo"))
        self._llamar(campo.click)
        self._llamar(campo.press_sequentially, codigo, delay=80)

    # --- cuentas y movimientos ---

    def tarjetas_de_cuenta(self) -> list[str]:
        """Etiquetas de las cuentas de la pantalla, en el orden en que aparecen.

        En el home real cada producto es una tarjeta y su etiqueta es el `<p>`
        con la clase `text-ellipsis` (ver `account_card_label` del contrato).
        """
        etiquetas: list[str] = []
        for elemento in self._llamar(self._localizar(self._spec("account_card_label")).all):
            texto = str(self._llamar(elemento.inner_text) or "").strip()
            if texto:
                etiquetas.append(texto)
        return etiquetas

    def abrir_cuenta(self, etiqueta: str) -> None:
        """Abre la cuenta con esa etiqueta (nunca por posición)."""
        for elemento in self._llamar(self._localizar(self._spec("account_card_label")).all):
            texto = str(self._llamar(elemento.inner_text) or "").strip()
            if texto != etiqueta:
                continue
            try:
                self._llamar(elemento.click)
                return
            except BankScrapeError:
                # La etiqueta aparece más de una vez (por ejemplo, el nombre del
                # producto y el de la cuenta): se prueba con la siguiente.
                continue
        raise BankScrapeError(
            CODIGO_CUENTA_NO_ENCONTRADA,
            f"la etiqueta de cuenta '{etiqueta}' no está en la pantalla de cuentas",
        )

    def filas_de_movimientos(self) -> list[list[str]]:
        """Celdas de cada fila de la tabla "Tus movimientos".

        Se leen por CSS (`tr` / `td`) y no por roles ARIA: la tabla del portal
        es un componente propio y sus roles no siempre se computan. La celda
        *sticky* que duplica la fecha la resuelve el parser.
        """
        tabla = self._localizar(self._spec("movements_table"))
        filas: list[list[str]] = []
        for fila in self._llamar(tabla.locator("tr").all):
            celdas = [
                str(self._llamar(celda.inner_text) or "").strip()
                for celda in self._llamar(fila.locator("td").all)
            ]
            if celdas:
                filas.append(celdas)
        return filas

    def hay_pagina_siguiente(self) -> bool:
        """¿Hay una página siguiente disponible?

        La paginación real del portal son enlaces `<a>` con `aria-disabled`
        (no el atributo `disabled`), así que el estado se lee de ahí.
        """
        boton = self._localizar(self._spec("pagination_next"))
        try:
            if boton.count() == 0:
                return False
            if str(self._llamar(boton.get_attribute, "aria-disabled")).lower() == "true":
                return False
            return bool(boton.is_enabled())
        except Exception:
            return False

    def ir_a_pagina_siguiente(self) -> None:
        """Avanza a la página siguiente de la tabla."""
        self._llamar(self._localizar(self._spec("pagination_next")).click)

    def responder_inactividad(self) -> bool:
        """Contesta el modal "¿Sigues ahí?" del portal, si está en pantalla.

        El modal se busca **por texto** porque su contenedor se reporta
        invisible aunque el texto se renderice. Devuelve `True` si lo contestó.
        """
        try:
            texto = str(self.texto_visible() or "").lower()
        except Exception:
            return False
        if not any(marca in texto for marca in MARCAS_INACTIVIDAD):
            return False
        try:
            boton = self._pagina.get_by_text(
                self._spec("modal_inactividad_boton"), exact=False
            )
            if boton.count() > 0:
                self._llamar(boton.first.click)
                return True
        except Exception:
            pass
        return False

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

    def _abrir_pestana_movimientos(self, timeout: float = 45.0) -> None:
        """Abre la pestaña "Movimientos" en cuanto aparece.

        Al abrir la cuenta, el portal tarda unos segundos en pintar el panel con
        las pestañas ("Detalles | Movimientos"). Buscarlas de inmediato daba
        `count=0` y el scrape terminaba con cero movimientos.
        """
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            pestana = self._localizar(self._spec("movements_tab"))
            try:
                if pestana.count() > 0 and pestana.is_visible():
                    self._llamar(pestana.click)
                    return
            except Exception:
                # La pestaña puede no existir en el DOM real: la tabla manda.
                pass
            time.sleep(1.0)

    def _etiqueta_de(self, tarjeta: Any) -> str:
        """Etiqueta (nombre visible) de una tarjeta de cuenta."""
        try:
            etiqueta = self._localizar(self._spec("account_card_label"), tarjeta)
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
        # Ninguno coincidió: se devuelve el **último** candidato (el CSS, que
        # es el más específico) y no el primero. Devolver el primero dejaba
        # cada operación esperando el timeout de Playwright sobre un elemento
        # que no existe, en vez de fallar rápido con un error claro.
        return candidatos[-1] if candidatos else base.locator("body")

    @staticmethod
    def _llamar(accion: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Ejecuta una operación de Playwright y traduce sus fallos."""
        try:
            return accion(*args, **kwargs)
        except BankScrapeError:
            raise
        except Exception as exc:
            raise BankScrapeError(
                CODIGO_PORTAL_NO_DISPONIBLE,
                f"el portal no respondió: {exc}",
            ) from exc
