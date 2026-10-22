"""Contrato del portal Bancolombia: rutas confirmadas y selectores del DOM (S5).

Este módulo es la **única** fuente de verdad sobre el portal: si el banco
rediseña la pantalla, el arreglo se hace aquí y en ningún otro lado. Ningún
otro módulo conoce selectores, textos ni rutas del portal.

Tres reglas del contrato
------------------------

1. **Ninguna ruta XHR.** El endpoint interno que el portal usa para listar
   movimientos **no se conoce** (nadie lo verificó) y **no se inventa**: el
   scraper navega por la pantalla, como una persona. Por eso el contrato sólo
   declara rutas de página y selectores de elemento.
2. **Rutas relativas.** El contrato describe *dónde* está cada cosa
   (`/autenticacion`, `/home`, `/detalles-y-movimientos/cuentas`), nunca la
   URL absoluta: el host vive en `URL_BASE_PORTAAL`.
3. **Roles y texto antes que CSS.** Cada elemento se declara con una
   `LocatorSpec` que guarda varias estrategias (rol accesible, texto, etiqueta,
   `data-testid` y, al final, el CSS de respaldo). El scraper prueba las
   estrategias en orden de robustez y se queda con la primera que encuentra
   algo, así que un cambio de clases no rompe el scraping mientras los roles y
   los textos se mantengan.

Lo que NO está verificado
-------------------------

El DOM real del portal **nunca se vio**: los fixtures de
`tests/fixtures/bank/` son una aproximación (ver su README). Los selectores de
este módulo son, por tanto, una *hipótesis razonable* —la de quien décritió
la pantalla— y no un hecho comprobable. Una corrida viva contra el portal es
la única forma de confirmarlos.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CONTRATO_PORTAAL",
    "URL_BASE_PORTAAL",
    "URL_BASE_PORTAAL_POR_DEFECTO",
    "ENV_URL_BASE",
    "LocatorSpec",
    "PortalContract",
]

#: Variable de entorno con la URL base del portal (sin barra final).
ENV_URL_BASE = "BANK_PORTAL_BASE_URL"

#: URL base por defecto. **No está verificada**: el operador la ajusta con
#: `BANK_PORTAL_BASE_URL` si el banco cambia de dominio.
URL_BASE_PORTAAL_POR_DEFECTO = "https://www.bancocolombia.com"

#: URL base efectiva (se resuelve en el momento de abrir el navegador).
URL_BASE_PORTAAL = URL_BASE_PORTAAL_POR_DEFECTO


@dataclass(frozen=True)
class LocatorSpec:
    """Cómo encontrar un elemento del portal, sin depender de Playwright.

    Cada campo es una estrategia distinta de localización; el scraper las
    prueba en orden de robustez (rol → texto → etiqueta → `data-testid` → CSS)
    y se queda con la primera que encuentra elementos. Varias estrategias
    pueden estar presentes a la vez: eso es deliberado, porque el DOM real
    no está verificado y una sola apuesta fallaría.

    Attributes:
        rol: rol ARIA (`article`, `tab`, `table`, `button`...).
        nombre: nombre accesible del elemento (`get_by_role(name=...)`).
        texto: texto visible exacto (`get_by_text`).
        etiqueta: etiqueta del campo de formulario (`get_by_label`).
        testid: valor de `data-testid`.
        css: selector CSS de respaldo (el último recurso).
    """

    rol: str | None = None
    nombre: str | None = None
    texto: str | None = None
    etiqueta: str | None = None
    testid: str | None = None
    css: str | None = None


@dataclass(frozen=True)
class PortalContract:
    """Rutas y selectores del portal, versionados.

    Frozen y versionable a propósito: si el portal cambia, se sube `version`
    y se corrigen **aquí** los selectores, de modo que el diff del cambio
    quede aislado en un archivo.

    Attributes:
        version: versión del contrato (súbela cuando cambien los selectores).
        path_auth: pantalla de autenticación.
        path_home: pantalla principal (tras autenticar).
        path_movimientos: pantalla de cuentas con sus movimientos.
        login_usuario: campo del usuario.
        login_clave: campo de la contraseña.
        login_enviar: botón de envío del formulario de acceso.
        otp_codigo: campo del código de un solo uso.
        otp_enviar: botón de envío del código.
        otp_prompt: texto del prompt en la consola del nodo.
        account_cards: tarjetas de cuenta listadas en la pantalla.
        account_card_label: etiqueta (nombre) de cada tarjeta.
        movements_tab: pestaña "Movimientos".
        movements_table: tabla "Tus movimientos".
        pagination_next: botón "Siguiente".
        pagination_prev: botón "Anterior".
    """

    version: int = 1

    # --- rutas confirmadas por el operador ---
    path_auth: str = "/autenticacion"
    path_home: str = "/home"
    path_movimientos: str = "/detalles-y-movimientos/cuentas"

    # --- acceso ---
    login_usuario: LocatorSpec = LocatorSpec(
        rol="textbox",
        nombre="Usuario",
        css="input[name='usuario'], input[type='email'], input[autocomplete='username']",
    )
    login_clave: LocatorSpec = LocatorSpec(
        etiqueta="Contraseña",
        css="input[type='password']",
    )
    login_enviar: LocatorSpec = LocatorSpec(
        rol="button",
        nombre="Ingresar",
        texto="Ingresar",
        css="button[type='submit']",
    )

    # --- verificación en dos pasos ---
    otp_codigo: LocatorSpec = LocatorSpec(
        etiqueta="Código",
        css="input[autocomplete='one-time-code'], input[name='codigo']",
    )
    otp_enviar: LocatorSpec = LocatorSpec(
        rol="button",
        nombre="Validar",
        texto="Validar",
        css="button[type='submit']",
    )
    otp_prompt: str = "Código de verificación del banco (escríbalo aquí): "

    # --- cuentas y movimientos ---
    account_cards: LocatorSpec = LocatorSpec(
        rol="article",
        testid="cuenta",
        css="article.account-card",
    )
    account_card_label: LocatorSpec = LocatorSpec(
        rol="heading",
        css="h3.account-card__label",
    )
    movements_tab: LocatorSpec = LocatorSpec(
        rol="tab",
        nombre="Movimientos",
        texto="Movimientos",
    )
    movements_table: LocatorSpec = LocatorSpec(
        rol="table",
        nombre="Tus movimientos",
        css="table",
    )
    pagination_next: LocatorSpec = LocatorSpec(
        rol="button",
        nombre="Siguiente",
        texto="Siguiente",
    )
    pagination_prev: LocatorSpec = LocatorSpec(
        rol="button",
        nombre="Anterior",
        texto="Anterior",
    )


#: Contrato vigente. Los módulos que raspan lo reciben inyectado.
CONTRATO_PORTAAL = PortalContract()
