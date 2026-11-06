"""Dobles offline del portal de Bancolombia (slice S5).

El DOM real del portal **no está verificado**: los fixtures de
`tests/fixtures/bank/` son una aproximación (ver el README de ese
directorio). Estos dobles leen esos fixtures sin navegador y sin red, y
exponen la misma interfaz que la sesión real de Playwright
(`PortalSession` del módulo `scraper`).

El lector de HTML es deliberadamente simple (expresiones regulares sobre los
propios fixtures): no pretende ser un parser de HTML, sólo un doble de prueba
determinista.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

RUTA_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bank"

_TARJETA = re.compile(r'<article class="account-card".*?</article>', re.S)
# La etiqueta real de la cuenta en el home es el <p> del card de producto.
_ETIQUETA = re.compile(
    r'<p[^>]*class="[^"]*bc-cibsans-font-style-4-bold[^"]*"[^>]*>(.*?)</p>', re.S
)
_FILA = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELDA = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
# La paginación real son enlaces <a> con aria-disabled (no el atributo disabled).
_PAGINACION = re.compile(
    r'<a class="bc-link[^"]*bc-paginator-v2-(?:next|prev)-link"([^>]*)>(.*?)</a>', re.S
)
_TAG = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"[ \t\r\n]+")
_CABECERA = ("Fecha", "Descripción", "Referencia", "Valor")


def leer_fixture(nombre: str) -> str:
    """Contenido de un fixture del directorio `tests/fixtures/bank/`."""
    return (RUTA_FIXTURES / nombre).read_text(encoding="utf-8")


def _texto(bruto: str) -> str:
    """Texto visible de un fragmento de HTML, como el `inner_text` del navegador.

    Las entidades se desescapan (el portal real escribe los importes con
    `&nbsp;`, espacio **no separable**, entre el símbolo pesos y las cifras) y
    sólo se colapsan los espacios ASCII: el espacio no separable se conserva
    para que el número quede igual que en el portal (`$ 7.590,00`, sin
    separación entre la coma y los centavos).
    """
    texto = html.unescape(_TAG.sub("", bruto))
    return _ESPACIOS.sub(" ", texto).strip()


def etiquetas_de_cuentas(html: str) -> list[str]:
    """Etiquetas de las tarjetas de cuenta, en el orden del DOM."""
    return [_texto(etiqueta) for etiqueta in _ETIQUETA.findall(html)]


def tarjetas_de_cuenta(html: str) -> list[str]:
    """Etiquetas de las tarjetas de cuenta (alias explícito del lector)."""
    return etiquetas_de_cuentas(html)


def filas_de_movimientos(html: str) -> list[list[str]]:
    """Celdas de cada fila de datos de la tabla "Tus movimientos"."""
    filas: list[list[str]] = []
    for fila in _FILA.findall(html):
        celdas = [_texto(celda) for celda in _CELDA.findall(fila)]
        if not celdas or any(celda in _CABECERA for celda in celdas):
            continue  # fila de cabecera
        filas.append(celdas)
    return filas


def paginacion_habilitada(html: str) -> bool:
    """`True` si el enlace "Siguiente" existe y no está deshabilitado.

    El portal real marca la paginación con `aria-disabled` en un `<a>`, así que
    el atributo `disabled` no aplica.
    """
    for atributos, contenido in _PAGINACION.findall(html):
        if "Siguiente" in _texto(contenido):
            return 'aria-disabled="true"' not in atributos.lower()
    return False


class PortalFalso:
    """Sesión del portal simulada con los fixtures offline.

    Reproduce la navegación que hace el scraper: autenticación (con posible
    código de un solo uso), home, tarjetas de cuenta, tabla de movimientos y
    paginación. Los errores del portal se inyectan por bandera para poder
    probar cada código de fallo sin red.
    """

    def __init__(
        self,
        *,
        cuentas_html: str,
        paginas_html: list[str],
        otp_html: str | None = None,
        credencial_valida: bool = True,
        sesion_expirada: bool = False,
        antibot_en_pagina: int | None = None,
        cuenta_esperada: str | None = None,
    ) -> None:
        self.cuentas_html = cuentas_html
        self.paginas_html = list(paginas_html)
        self.otp_html = otp_html
        self.credencial_valida = credencial_valida
        self.sesion_expirada = sesion_expirada
        self.antibot_en_pagina = antibot_en_pagina
        self.cuenta_esperada = cuenta_esperada

        self.pagina = 0
        self.cuenta_abierta: str | None = None
        self.codigo_otp: str | None = None
        self.texto = ""
        self.url = "/autenticacion"
        self.acciones: list[str] = []
        self.cuentas_servidas: set[str] = set()

    # --- navegación ---

    def ir_a_autenticacion(self) -> None:
        self.acciones.append("ir_a_autenticacion")
        self.url = "/autenticacion"
        self.texto = "Autenticación"

    def escribir_credenciales(self, usuario: str, clave: str) -> None:
        # Nunca se guardan los valores: sólo el hecho de haberlos escrito.
        self.acciones.append("escribir_credenciales")
        assert usuario and clave

    def enviar_formulario(self) -> None:
        self.acciones.append("enviar_formulario")
        if not self.credencial_valida:
            self.texto = "Credenciales incorrectas. Intenta de nuevo."
            self.url = "/autenticacion"
            return
        if self.otp_html is not None and self.codigo_otp is None:
            self.texto = "Ingresa el código de verificación"
            self.url = "/autenticacion"
            return
        self.texto = ""
        self.url = "/home"

    def hay_codigo_otp(self) -> bool:
        return self.otp_html is not None and self.codigo_otp is None

    def escribir_codigo_otp(self, codigo: str) -> None:
        self.acciones.append("escribir_codigo_otp")
        self.codigo_otp = codigo

    def ir_a_home(self) -> None:
        self.acciones.append("ir_a_home")
        if self.sesion_expirada:
            self.texto = "Su sesión expiró. Inicie sesión nuevamente."
            self.url = "/autenticacion"
            return
        self.texto = ""
        self.url = "/home"

    def ir_a_movimientos(self) -> None:
        self.acciones.append("ir_a_movimientos")
        self.texto = ""
        self.url = "/detalles-y-movimientos/cuentas"

    def url_actual(self) -> str:
        return self.url

    def texto_visible(self) -> str:
        return self.texto

    # --- cuentas ---

    def tarjetas_de_cuenta(self) -> list[str]:
        return etiquetas_de_cuentas(self.cuentas_html)

    def abrir_cuenta(self, etiqueta: str) -> None:
        self.acciones.append(f"abrir_cuenta:{etiqueta}")
        assert etiqueta in self.tarjetas_de_cuenta(), (
            f"se intentó abrir una cuenta que no está en la página: {etiqueta!r}"
        )
        self.cuenta_abierta = etiqueta

    # --- movimientos ---

    def filas_de_movimientos(self) -> list[list[str]]:
        assert self.cuenta_abierta is not None, "se pidieron movimientos sin abrir una cuenta"
        if self.cuenta_esperada is not None and self.cuenta_abierta != self.cuenta_esperada:
            raise AssertionError(
                f"se pidieron movimientos de la cuenta {self.cuenta_abierta!r}, "
                f"pero la del tenant es {self.cuenta_esperada!r}"
            )
        self.cuentas_servidas.add(self.cuenta_abierta)
        if self.antibot_en_pagina == self.pagina:
            self.texto = "Verificación de seguridad: confirma que no eres un robot"
            return []
        return filas_de_movimientos(self.paginas_html[self.pagina])

    def hay_pagina_siguiente(self) -> bool:
        return paginacion_habilitada(self.paginas_html[self.pagina])

    def ir_a_pagina_siguiente(self) -> None:
        self.acciones.append("ir_a_pagina_siguiente")
        self.pagina += 1

    def responder_inactividad(self) -> bool:
        """El modal "¿Sigues ahí?" aparece si el nodo tarda más de 2 minutos."""
        self.acciones.append("responder_inactividad")
        return False

    def cerrar(self) -> None:
        self.acciones.append("cerrar")
