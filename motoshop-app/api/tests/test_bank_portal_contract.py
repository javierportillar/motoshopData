"""Tests del contrato del portal y del scraper DOM (slice S5).

**Todo es offline**: los fixtures de `tests/fixtures/bank/` son una
APROXIMACIÓN del DOM real (ver el README de ese directorio). Ningún test abre
un navegador ni una red; la sesión del portal es un doble (`PortalFalso`).

Lo que se verifica aquí:

* la cuenta se abre **por etiqueta**, nunca por índice;
* todo fallo del portal deja **cero movimientos** y un código explícito;
* el código OTP se pide en la **consola del nodo** y no se persiste ni se
  registra;
* el nodo se serializa con un **lock** y un **intervalo mínimo**.
"""

from __future__ import annotations

import datetime
import importlib.util
import logging
import stat
import sys
from pathlib import Path

import pytest

from motoshop_api.erp.bankreconciliation import scraper as scraper_module
from motoshop_api.erp.bankreconciliation.node_config import (
    REPO_ROOT,
    NodeConfig,
    load_node_config,
)
from motoshop_api.erp.bankreconciliation.portal_pages import CONTRATO_PORTAAL, PortalContract
from motoshop_api.erp.bankreconciliation.scraper import (
    BankScrapeError,
    BankScraper,
    SessionSlotError,
    acquire_session_slot,
)
from motoshop_api.erp.bankreconciliation.store import FakeBankStore
from motoshop_api.erp.bankreconciliation.vault import Entry, VaultNotFound
from tests.bank_fakes import PortalFalso, leer_fixture

ETIQUETA_TENANT = "MasVital"
ETIQUETA_OTRO_TENANT = "Distribuidora del Norte S.A."


class _VaultFalso:
    """Vault de prueba: entrega la credencial o falla como el vault real."""

    def __init__(self, con_entrada: bool = True) -> None:
        self.con_entrada = con_entrada
        self.peticiones: list[str] = []

    def get_entry(self, name: str) -> Entry:
        self.peticiones.append(name)
        if not self.con_entrada:
            raise VaultNotFound("no existe la entrada")
        return Entry(
            username="usuario_secreto",
            password="clave_secreta_123",
            updated_at=datetime.datetime(2026, 1, 1, 12, 0, 0),
        )


def _config(
    tmp_path: Path,
    *,
    tenant: str = "masvital",
    etiqueta: str = ETIQUETA_TENANT,
    ventana_amplia: bool = True,
) -> NodeConfig:
    """Configuración de un nodo con el perfil fuera del repo."""
    env = {
        "BANK_SCRAPER_ENABLED": "true",
        "BANK_TENANT": tenant,
        "BANK_ACCOUNT_LABEL": etiqueta,
        "BANK_CREDENTIAL_ENTRY": f"bancolombia-{tenant}",
        "BANK_PROFILE_DIR": str(tmp_path / "perfil"),
    }
    if ventana_amplia:
        # Los fixtures son una captura REAL del portal (21 oct 2026): la
        # ventana tiene que cubrir esa fecha.
        env["BANK_WINDOW_START"] = "2026-01-01"
        env["BANK_WINDOW_END"] = "2026-12-31"
    return load_node_config(env)


def _sesion(**extra) -> PortalFalso:
    """Portal falso con las dos páginas de movimientos de los fixtures."""
    return PortalFalso(
        cuentas_html=leer_fixture("cuentas.html"),
        paginas_html=[
            leer_fixture("movimientos_pagina1.html"),
            leer_fixture("movimientos_pagina2.html"),
        ],
        **extra,
    )


def _scraper(sesion: PortalFalso, vault: _VaultFalso | None = None, **extra) -> BankScraper:
    """Scraper con la sesión y el vault de prueba inyectados."""
    return BankScraper(
        session_factory=lambda _config: sesion,
        vault=vault or _VaultFalso(),
        **extra,
    )


def _cargar_script():
    """Carga `scripts/bank_sync.py` como módulo (no es un paquete instalable)."""
    ruta = Path(__file__).resolve().parents[1] / "scripts" / "bank_sync.py"
    spec = importlib.util.spec_from_file_location("bank_sync", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# --- Selección de la cuenta por etiqueta ---


def test_cuenta_se_selecciona_por_etiqueta_y_nunca_por_indice(tmp_path: Path) -> None:
    """La cuenta del tenant es la segunda del DOM: se abre por etiqueta."""
    sesion = _sesion()
    config = _config(tmp_path)

    resultado = _scraper(sesion).scrape(config)

    assert sesion.cuenta_abierta == ETIQUETA_TENANT
    assert sesion.tarjetas_de_cuenta() == [ETIQUETA_OTRO_TENANT, ETIQUETA_TENANT]
    assert resultado.cuenta == ETIQUETA_TENANT


def test_etiquetas_de_distintos_tenants_solo_abre_la_del_tenant_actual(tmp_path: Path) -> None:
    """Cada nodo abre su cuenta, aunque la otra esté en la misma sesión."""
    sesion_masvital = _sesion(cuenta_esperada=ETIQUETA_TENANT)
    sesion_otro = _sesion(cuenta_esperada=ETIQUETA_OTRO_TENANT)

    _scraper(sesion_masvital).scrape(_config(tmp_path, tenant="masvital"))
    _scraper(sesion_otro).scrape(
        _config(tmp_path, tenant="distribuidora", etiqueta=ETIQUETA_OTRO_TENANT)
    )

    assert sesion_masvital.cuenta_abierta == ETIQUETA_TENANT
    assert sesion_otro.cuenta_abierta == ETIQUETA_OTRO_TENANT


def test_no_solicita_movimientos_de_la_cuenta_de_otro_tenant(tmp_path: Path) -> None:
    """Sólo se piden movimientos de la cuenta abierta (la del tenant)."""
    sesion = _sesion(cuenta_esperada=ETIQUETA_TENANT)

    _scraper(sesion).scrape(_config(tmp_path))

    assert sesion.cuentas_servidas == {ETIQUETA_TENANT}
    assert ETIQUETA_OTRO_TENANT not in sesion.cuentas_servidas


def test_etiqueta_del_tenant_ausente_falla_con_cuenta_no_encontrada_y_no_registra_movimientos(
    tmp_path: Path,
) -> None:
    """Si la etiqueta no existe, el nodo falla y no lee otra cuenta."""
    sesion = _sesion()
    store = FakeBankStore()
    config = _config(tmp_path, etiqueta="Cuenta Que No Existe")

    with pytest.raises(BankScrapeError) as error:
        _cargar_script().sincronizar(config, scraper=_scraper(sesion), store=store)

    assert error.value.codigo == "cuenta_no_encontrada"
    assert sesion.cuenta_abierta is None
    assert store.list_movimientos(config.tenant) == []


# --- Paginación y ventana ---


def test_recorre_todas_las_paginas_de_la_ventana_y_expone_pagina_y_ventana(tmp_path: Path) -> None:
    """El movimiento de la página 2 se encuentra y expone su página."""
    sesion = _sesion()
    config = _config(tmp_path)

    resultado = _scraper(sesion).scrape(config)

    assert resultado.paginas == 2
    objetivo = next(
        mov for mov in resultado.movimientos if mov.pagador_nombre == "CRISTOPHER BENAVIDES P"
    )
    assert objetivo.pagina == 2
    assert objetivo.cuenta_origen == ETIQUETA_TENANT
    assert resultado.ventana == (config.window_start, config.window_end)


def test_ventana_por_defecto_es_el_dia_en_curso(tmp_path: Path) -> None:
    """Sin `BANK_WINDOW_*` la ventana es hoy de 00:00:00 a 23:59:59."""
    config = _config(tmp_path, ventana_amplia=False)
    hoy = datetime.date.today()

    assert config.window_start == datetime.datetime.combine(hoy, datetime.time(0, 0, 0))
    assert config.window_end == datetime.datetime.combine(hoy, datetime.time(23, 59, 59))
    assert config.ventana_por_defecto == "dia"

    resultado = _scraper(_sesion()).scrape(config)
    assert resultado.ventana == (config.window_start, config.window_end)


def test_los_movimientos_fuera_de_la_ventana_no_se_ingresan(tmp_path: Path) -> None:
    """La ventana acota qué movimientos se leen del portal.

    Los fixtures son una captura real del 21 oct 2026: la ventana de esta
    prueba termina el día anterior, así que ninguno debe entrar.
    """
    env = {
        "BANK_SCRAPER_ENABLED": "true",
        "BANK_TENANT": "masvital",
        "BANK_ACCOUNT_LABEL": ETIQUETA_TENANT,
        "BANK_CREDENTIAL_ENTRY": "bancolombia-masvital",
        "BANK_PROFILE_DIR": str(tmp_path / "perfil"),
        "BANK_WINDOW_START": "2026-10-01",
        "BANK_WINDOW_END": "2026-10-20",
    }
    config = load_node_config(env)

    resultado = _scraper(_sesion()).scrape(config)

    assert resultado.movimientos == ()


# --- Perfil persistente ---


@pytest.mark.skipif(sys.platform == "win32", reason="los permisos POSIX no aplican en Windows")
def test_perfil_persistente_fuera_del_repo_y_con_permisos_700(tmp_path: Path) -> None:
    """El perfil del navegador vive fuera del repo y con permisos 700."""
    sesion = _sesion()
    config = _config(tmp_path)
    perfiles: list[Path] = []

    def factory(cfg: NodeConfig) -> PortalFalso:
        perfiles.append(cfg.profile_dir)
        return sesion

    BankScraper(session_factory=factory, vault=_VaultFalso()).scrape(config)

    perfil = config.profile_dir.resolve()
    assert perfiles == [config.profile_dir]
    assert REPO_ROOT.resolve() not in perfil.parents
    assert stat.S_IMODE(config.profile_dir.stat().st_mode) == 0o700


# --- OTP ---


def test_otp_se_solicita_en_el_nodo_y_no_se_persiste(tmp_path: Path) -> None:
    """El código se pide con `input()` en la consola y no queda en ningún lado."""
    codigo = "483920"
    pedidos: list[str] = []

    def pedir(prompt: str) -> str:
        pedidos.append(prompt)
        return codigo

    sesion = _sesion(otp_html=leer_fixture("login_otp.html"))
    config = _config(tmp_path)

    resultado = _scraper(sesion, pedir_codigo=pedir).scrape(config)

    assert pedidos, "el código OTP debe pedirlo el nodo, no el navegador"
    assert sesion.codigo_otp == codigo
    assert codigo not in repr(resultado.movimientos)
    for archivo in config.profile_dir.rglob("*"):
        if archivo.is_file():
            assert codigo.encode() not in archivo.read_bytes()


def test_el_codigo_otp_no_aparece_en_el_log(tmp_path: Path, caplog) -> None:
    """El log del nodo no contiene el código OTP."""
    codigo = "483920"

    with caplog.at_level(logging.INFO):
        _scraper(
            _sesion(otp_html=leer_fixture("login_otp.html")),
            pedir_codigo=lambda _prompt: codigo,
        ).scrape(_config(tmp_path))

    assert codigo not in caplog.text


# --- Errores del portal ---


def test_credencial_ausente_falla_con_codigo_explicito_y_no_registra_movimientos(
    tmp_path: Path,
) -> None:
    """Sin entrada en el vault el nodo no raspa: `credencial_ausente`."""
    store = FakeBankStore()
    config = _config(tmp_path)

    with pytest.raises(BankScrapeError) as error:
        _cargar_script().sincronizar(
            config, scraper=_scraper(_sesion(), vault=_VaultFalso(con_entrada=False)), store=store
        )

    assert error.value.codigo == "credencial_ausente"
    assert store.list_movements(config.tenant) == []


def test_credencial_invalida_falla_con_codigo_explicito(tmp_path: Path) -> None:
    """El portal rechaza las credenciales: `credencial_invalida`."""
    sesion = _sesion(credencial_valida=False)

    with pytest.raises(BankScrapeError) as error:
        _scraper(sesion).scrape(_config(tmp_path))

    assert error.value.codigo == "credencial_invalida"


def test_sesion_expirada_falla_con_codigo_explicito(tmp_path: Path) -> None:
    """La sesión caduca antes de leer movimientos: `sesion_expirada`."""
    sesion = _sesion(sesion_expirada=True)

    with pytest.raises(BankScrapeError) as error:
        _scraper(sesion).scrape(_config(tmp_path))

    assert error.value.codigo == "sesion_expirada"


def test_desafio_antibot_no_deja_movimientos_parciales(tmp_path: Path) -> None:
    """El antibot en la página 2 descarta lo leído en la página 1."""
    store = FakeBankStore()
    config = _config(tmp_path)
    sesion = _sesion(antibot_en_pagina=1)

    with pytest.raises(BankScrapeError) as error:
        _cargar_script().sincronizar(config, scraper=_scraper(sesion), store=store)

    assert error.value.codigo == "antibot"
    assert store.list_movements(config.tenant) == []


# --- Lock e intervalo ---


def test_ejecucion_concurrente_rechazada_por_lock(tmp_path: Path) -> None:
    """Dos corridas a la vez no pueden: la segunda encuentra el lock."""
    config = _config(tmp_path)

    with acquire_session_slot(config), pytest.raises(SessionSlotError) as error:
        _scraper(_sesion()).scrape(config)

    assert error.value.motivo == "ejecucion_concurrente"


def test_candado_windows_cierra_el_handle_antes_de_borrar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows no deja borrar un archivo con el descriptor abierto (WinError 32)."""
    monkeypatch.setattr(scraper_module, "fcntl", None)
    ruta = tmp_path / scraper_module.NOMBRE_LOCK
    candado = scraper_module._Candado(ruta)

    candado.adquirir()
    assert ruta.exists()

    candado.liberar()
    candado.liberar()  # idempotente: el segundo llamado no hace nada

    assert not ruta.exists()


def test_candado_reintenta_el_borrado_tras_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un antivirus puede tener el archivo tomado un instante."""
    monkeypatch.setattr(scraper_module, "fcntl", None)
    monkeypatch.setattr(scraper_module.time, "sleep", lambda _segundos: None)
    ruta = tmp_path / scraper_module.NOMBRE_LOCK
    candado = scraper_module._Candado(ruta)
    candado.adquirir()

    unlink_original = Path.unlink
    intentos = {"n": 0}

    def unlink_con_un_fallo(self: Path, *args: object, **kwargs: object) -> None:
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise PermissionError(32, "El proceso no tiene acceso al archivo")
        unlink_original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", unlink_con_un_fallo)

    candado.liberar()

    assert intentos["n"] == 2
    monkeypatch.setattr(Path, "unlink", unlink_original)
    assert not ruta.exists()


def test_corrida_reciente_dentro_del_intervalo_minimo_rechazada(tmp_path: Path) -> None:
    """Dos corridas seguidas violan el intervalo mínimo de 30 s."""
    config = _config(tmp_path)
    instante = datetime.datetime(2026, 1, 1, 8, 0, 0)
    scraper = _scraper(_sesion(), reloj=lambda: instante)

    scraper.scrape(config)
    with pytest.raises(SessionSlotError) as error:
        scraper.scrape(config)

    assert error.value.motivo == "intervalo_minimo"


# --- Ingesta idempotente ---


def test_la_ingesta_es_idempotente(tmp_path: Path) -> None:
    """La segunda corrida no crea filas nuevas."""
    store = FakeBankStore()
    config = _config(tmp_path)
    instante = datetime.datetime(2026, 1, 1, 8, 0, 0)
    minutos = iter([instante, instante + datetime.timedelta(seconds=60)])

    scraper = _scraper(_sesion(), reloj=lambda: next(minutos))
    script = _cargar_script()

    primera = script.sincronizar(config, scraper=scraper, store=store)
    segunda = script.sincronizar(config, scraper=scraper, store=store)

    assert primera.nuevos > 0
    assert segunda.nuevos == 0
    assert len(store.list_movements(config.tenant)) == primera.nuevos


# --- El contrato del portal ---


def test_el_contrato_no_declara_ningun_endpoint_xhr() -> None:
    """El contrato sólo conoce las tres rutas que el operador confirmó."""
    contrato = CONTRATO_PORTAAL

    assert isinstance(contrato, PortalContract)
    assert contrato.path_auth == "/autenticacion"
    assert contrato.path_home == "/home"
    assert contrato.path_movimientos == "/detalles-y-movimientos/cuentas"
    assert not any(
        "http" in str(getattr(contrato, campo)).lower() for campo in contrato.__dataclass_fields__
    )
    assert not any(
        "endpoint" in campo or "xhr" in campo for campo in contrato.__dataclass_fields__
    )


def test_el_contrato_centraliza_los_selectores_del_portal() -> None:
    """Un rediseño del portal se corrige en `portal_pages.py` y en ningún otro lado."""
    contrato = CONTRATO_PORTAAL

    for campo in (
        "account_cards",
        "movements_tab",
        "movements_table",
        "pagination_next",
        "pagination_prev",
    ):
        assert getattr(contrato, campo) is not None


# --- Hechos verificados contra el portal real (21 oct 2026) ---


class _ElementoFalso:
    """Elemento mínimo que registra los clics."""

    def __init__(self) -> None:
        self.clics = 0

    def click(self) -> None:
        self.clics += 1

    def inner_text(self) -> str:
        return "Estoy aquí"


class _LocadorFalso:
    """Localizador mínimo: cuenta, visibilidad y elementos."""

    def __init__(
        self, elementos: list[_ElementoFalso] | None = None, texto: str = ""
    ) -> None:
        self._elementos = elementos or []
        self._texto = texto

    def all(self) -> list[_ElementoFalso]:
        return self._elementos

    def count(self) -> int:
        return len(self._elementos)

    def is_visible(self) -> bool:
        return bool(self._elementos)

    @property
    def first(self) -> _ElementoFalso:
        # En Playwright `locator.first` es una propiedad, no un método.
        return self._elementos[0]

    def inner_text(self) -> str:
        return self._texto


class _PaginaFalsa:
    """Página que registra cualquier navegación por URL."""

    def __init__(self, texto: str = "") -> None:
        self.gotos: list[str] = []
        self.texto = texto

    def goto(self, url: str, **_kwargs: object) -> None:
        self.gotos.append(url)

    def locator(self, _css: str) -> _LocadorFalso:
        return _LocadorFalso(texto=self.texto)

    def get_by_text(self, _texto: str, **_kwargs: object) -> _LocadorFalso:
        return _LocadorFalso([_ElementoFalso()])

    def get_by_role(self, _rol: str, **_kwargs: object) -> _LocadorFalso:
        return _LocadorFalso([_ElementoFalso()])


def test_ir_a_movimientos_no_navega_por_url() -> None:
    """Navegar por URL a una ruta profunda reinicia la SPA y rompe la sesión.

    El portal real pierde la sesión si se recarga una ruta profunda: vuelve al
    login. La navegación tiene que ser client-side (clic en la cuenta y clic
    en la pestaña).
    """
    from motoshop_api.erp.bankreconciliation.scraper import PlaywrightPortalSession

    pagina = _PaginaFalsa()
    sesion = PlaywrightPortalSession(
        gestor=None,
        contexto=None,
        pagina=pagina,
        contrato=CONTRATO_PORTAAL,
        base_url="https://svpersonas.apps.bancolombia.com",
    )

    sesion.ir_a_movimientos()

    assert pagina.gotos == []


def test_el_scraper_abre_la_cuenta_antes_de_los_movimientos(tmp_path: Path) -> None:
    """El orden real del portal: home → cuenta → pestaña Movimientos."""
    sesion = _sesion()

    _scraper(sesion).scrape(_config(tmp_path))

    assert sesion.acciones.index("ir_a_home") < sesion.acciones.index(
        "abrir_cuenta:MasVital"
    )
    assert sesion.acciones.index("abrir_cuenta:MasVital") < sesion.acciones.index(
        "ir_a_movimientos"
    )


def test_el_modal_de_inactividad_se_responde_por_texto() -> None:
    """El portal cancela el proceso a los 2 minutos: hay que contestar."""
    from motoshop_api.erp.bankreconciliation.scraper import PlaywrightPortalSession

    pagina = _PaginaFalsa(texto="¿Sigues ahí? Por seguridad, cancelaremos tu proceso")
    sesion = PlaywrightPortalSession(
        gestor=None,
        contexto=None,
        pagina=pagina,
        contrato=CONTRATO_PORTAAL,
        base_url="https://svpersonas.apps.bancolombia.com",
    )

    assert sesion.responder_inactividad() is True


def test_sin_modal_de_inactividad_no_hay_que_responder_nada() -> None:
    """Fuera del modal, `responder_inactividad` no hace nada."""
    from motoshop_api.erp.bankreconciliation.scraper import PlaywrightPortalSession

    pagina = _PaginaFalsa(texto="Tus productos")
    sesion = PlaywrightPortalSession(
        gestor=None,
        contexto=None,
        pagina=pagina,
        contrato=CONTRATO_PORTAAL,
        base_url="https://svpersonas.apps.bancolombia.com",
    )

    assert sesion.responder_inactividad() is False


def test_la_paginacion_real_se_lee_de_aria_disabled() -> None:
    """La paginación real son enlaces `<a>` con `aria-disabled`, no `disabled`."""
    from tests.bank_fakes import leer_fixture, paginacion_habilitada

    assert paginacion_habilitada(leer_fixture("movimientos_pagina1.html")) is True
    assert paginacion_habilitada(leer_fixture("movimientos_pagina2.html")) is False


def test_ir_a_autenticacion_navega_con_wait_until() -> None:
    """La navegación inicial SÍ puede ser por URL (antes del login).

    Regresión: `_llamar` no aceptaba `**kwargs`, así que `goto(..., wait_until=)`
    reventaba con `TypeError` y el login nunca empezaba. La suite offline no lo
    cubría porque el doble no navega.
    """
    from motoshop_api.erp.bankreconciliation.scraper import PlaywrightPortalSession

    pagina = _PaginaFalsa()
    sesion = PlaywrightPortalSession(
        gestor=None,
        contexto=None,
        pagina=pagina,
        contrato=CONTRATO_PORTAAL,
        base_url="https://svpersonas.apps.bancolombia.com",
    )

    sesion.ir_a_autenticacion()

    assert pagina.gotos == ["https://svpersonas.apps.bancolombia.com/autenticacion"]
