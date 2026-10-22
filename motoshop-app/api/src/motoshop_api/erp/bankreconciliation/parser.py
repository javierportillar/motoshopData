"""Parser puro de los movimientos de la tabla "Tus movimientos" (S5).

Este módulo **no hace E/S**: no toca el disco, ni el navegador, ni la red. Recibe
las **celdas** de una fila del portal y devuelve un movimiento tipado. Es
determinista: las mismas celdas producen siempre el mismo movimiento, y por eso
se puede probar con fixtures offline (sin portal).

Contrato con el portal (verificado contra el portal real el 21 oct 2026)
---------------------------------------------------------------------------
La tabla "Tus movimientos" del portal Bancolombia tiene cuatro columnas, pero
cada fila entrega **cinco celdas**: la primera es una celda *sticky* que
**duplica la fecha** (el header real es `Fecha | Fecha | Descripción | Referencia
| Valor | exchange`). El parser descarta esa celda fija.

    Fecha | Descripción | Referencia | Valor

- **Fecha**: dos formatos reales, ambos aceptados:
  `21 oct 2026` (mes en letras, es lo que muestra el portal) y `DD/MM/YYYY`
  (`10/02/2025` es 10 de febrero).
- **Descripción**: el texto de la operación. Las descripciones que **empiezan**
  con `PAGO QR`, `PAGO LLAVE` o `PAGO PSE` traen el nombre del pagador (o la
  razón social); cualquier otra descripción deja el pagador vacío y **nunca**
  lanza una excepción.
- **Referencia**: puede venir con el sufijo `" null"` que el portal agrega
  cuando la referencia no existe, o ser una referencia de sólo ceros
  (`00000000000`), que **no** sirve para conciliar.
- **Valor**: importes en formato colombiano (`$ 458.200,00`, `- $ 7.590,00`)
  con **espacio no separable** (U+00A0) entre el símbolo y las cifras.

Reglas de dinero (ADR-0008-07)
-----------------------------
Todo el camino del importe es `Decimal`: el texto se normaliza **antes** de
construir el número, así que `1.005,50` da `Decimal("1005.50")` exacto y nunca
pasa por `float` (que devolvería `1005.4999999...`).

Compatibilidad con la persistencia (S4)
---------------------------------------
`ParsedMovement` es compatible con `BankMovementIn` (`schemas.py`): mismos
nombres de campo, misma fecha (`datetime.date`) y mismo importe (`Decimal` con
dos decimales). La conversión a `BankMovementIn` es trabajo de la capa de
ingesta: este módulo se mantiene sin dependencias para poder probarlo aislado.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "BankMovement",
    "FormatoDeMovimientoInvalido",
    "MovementDirection",
    "ParsedMovement",
    "parse_colombian_amount",
    "parse_movement_row",
    "sanitize_reference",
]


class FormatoDeMovimientoInvalido(ValueError):
    """Una celda del portal no se pudo interpretar.

    Es un error explícito y en español: un importe ilegible o una fila sin
    fecha/valor son un problema del dato de origen, no un cero silencioso.
    """


class MovementDirection(StrEnum):
    """Sentido del dinero del movimiento.

    `StrEnum` (y no `str` + `Enum`) porque el repositorio usa `ruff` con las
    reglas `UP` —`UP042` exige `StrEnum`— y porque `schemas.EstadoMovimiento`
    ya sigue la misma convención. El comportamiento pedido se mantiene:
    `MovementDirection.EGRESO == "egreso"` y `isinstance(x, str)`.
    """

    INGRESO = "ingreso"
    EGRESO = "egreso"


@dataclass(frozen=True)
class ParsedMovement:
    """Un movimiento del portal, ya interpretado.

    - `fecha`: día del movimiento (`datetime.date`).
    - `descripcion`: texto de la operación, con espacios normalizados.
    - `referencia`: referencia saneada (sin el sufijo `" null"`).
    - `referencia_utilizable`: `False` si la referencia está vacía o es sólo
      ceros: con esas referencias no se puede conciliar.
    - `pagador_nombre`: nombre del pagador, sólo si la descripción empieza con
      `PAGO QR`; en otro caso es `""`.
    - `valor`: importe exacto (`Decimal`), nunca `float`.
    - `direccion`: `INGRESO` (positivo) o `EGRESO` (negativo).
    - `es_candidato_pago`: `True` sólo si el movimiento es un ingreso: es lo
      que puede llegar a conciliarse contra una factura.
    """

    fecha: datetime.date
    descripcion: str
    referencia: str
    referencia_utilizable: bool
    pagador_nombre: str
    valor: Decimal
    direccion: MovementDirection
    es_candidato_pago: bool


#: Alias con el nombre que usan las slices de matching (S7/S9).
BankMovement = ParsedMovement

#: Orden de las columnas en la tabla "Tus movimientos" del portal.
ORDEN_DE_COLUMNAS = ("fecha", "descripcion", "referencia", "valor")

#: Orden alternativo tolerado: algunos extractores del DOM entregan la fecha al
#: final. Se detecta por contenido (la fecha y el importe se reconocen solos),
#: nunca por posición a ciegas.
ORDEN_DE_COLUMNAS_ALTERNATIVO = ("descripcion", "referencia", "valor", "fecha")

#: Prefijos de la descripción que traen el nombre del pagador.
#:
#: Verificados contra el portal real: `PAGO QR <nombre>` (pago con QR) y
#: `PAGO LLAVE <nombre>` (transferencia por llave) son **entradas** y traen el
#: nombre de quien pagó. `PAGO PSE <razón social>` **no** entra: en este portal
#: es una salida (el nombre es a quién se le pagó, no quién pagó), igual que
#: `CONSIGNACION CORRESPONSAL CB` o `ABONO INTERESES AHORROS`.
PREFIJOS_DE_PAGO = ("PAGO QR", "PAGO LLAVE")

#: Prefijo de la descripción que trae el nombre del pagador (alias del primero).
PREFIJO_PAGO_QR = "PAGO QR"

#: Meses en abreviatura, como los muestra el portal (`21 oct 2026`).
MESES_EN_ABREVIATURA = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}

_RE_FECHA = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_RE_FECHA_CON_MES = re.compile(r"^(\d{1,2})\s+([a-záéíóúñ]{3,10})\s+(\d{4})$", re.IGNORECASE)
_RE_PAGO = re.compile(
    r"^(?P<prefijo>PAGO\s+(?:QR|LLAVE))\s+(?P<nombre>\S.*)$",
    re.IGNORECASE,
)
_RE_NULO_AL_FINAL = re.compile(r"\s*null$", re.IGNORECASE)
_RE_ESPACIOS = re.compile(r"\s+")
#: Espacios (incluido el espacio duro del portal: `\s` también lo cubre) y el
#: símbolo pesos: nada más.
_RE_SOLO_ESPACIOS_Y_PESOS = re.compile(r"[\s$]")
_RE_IMPORTE_CON_MILES = re.compile(r"^[+-]?\s*\$?\s*\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?$")
_RE_IMPORTE_CON_DECIMAL = re.compile(r"^[+-]?\s*\$?\s*\d+,\d{1,2}$")
_RE_SOLO_MILES = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_RE_DECIMAL_CON_PUNTO = re.compile(r"^\d+\.\d{1,2}$")
_RE_NUMERO = re.compile(r"^\d+(?:\.\d{1,2})?$")


def parse_colombian_amount(raw: str) -> Decimal:
    """Convierte un importe en formato colombiano a `Decimal` exacto.

    Acepta `"$ 458.200,00"`, `"- $ 7.590,00"`, `" $ 1.005,50 "` y las variantes
    sin símbolo pesos. El texto se normaliza **antes** de construir el número:
    nunca se convierte a `float`, así que no hay redondeo binario.

    Args:
        raw: importe tal como lo muestra el portal.

    Returns:
        El importe exacto, con dos decimales.

    Raises:
        FormatoDeMovimientoInvalido: si el texto no es un importe legible.
    """
    texto = (raw or "").strip()
    if not texto:
        raise FormatoDeMovimientoInvalido("El importe del movimiento está vacío.")

    negativo = False
    if texto.startswith(("+", "-")):
        negativo = texto[0] == "-"
        texto = texto[1:]
    elif texto.endswith("-"):
        negativo = True
        texto = texto[:-1]

    limpio = _RE_SOLO_ESPACIOS_Y_PESOS.sub("", texto)
    entero, decimales = _partir_cifras(limpio)
    if decimales is not None and len(decimales) > 2:
        raise FormatoDeMovimientoInvalido(
            f"El importe del movimiento tiene más de dos decimales: {raw!r}"
        )
    if not _RE_NUMERO.match(entero):
        raise FormatoDeMovimientoInvalido(f"El importe del movimiento no es un número: {raw!r}")

    valor = Decimal(f"{entero}.{decimales or '00'}")
    return -valor if negativo else valor


def sanitize_reference(raw: str) -> str:
    """Limpia la referencia que devuelve el portal.

    Quita el sufijo `" null"` que el portal agrega cuando la referencia no
    existe (`"0092055984 null"` → `"0092055984"`) y normaliza los espacios. El
    sufijo sólo se quita cuando está **al final**: en el medio forma parte del
    dato y se conserva.

    Args:
        raw: referencia tal como la muestra el portal.

    Returns:
        La referencia saneada (puede quedar vacía).
    """
    texto = _normalizar_texto(raw)
    return _RE_NULO_AL_FINAL.sub("", texto).strip()


def parse_movement_row(cells: Sequence[str]) -> ParsedMovement:
    """Interpreta las celdas de una fila de la tabla "Tus movimientos".

    Las celdas llegan en el orden del portal. La fila real trae **cinco** celdas:
    la primera es una celda *sticky* que duplica la fecha y se descarta. El orden
    de las columnas se confirma por contenido (la fecha y el importe se
    reconocen solos), de modo que también se acepta la variante con la fecha al
    final.

    Args:
        cells: las celdas de la fila, en cualquier orden reconocible.

    Returns:
        El movimiento interpretado, con importes exactos (`Decimal`).

    Raises:
        FormatoDeMovimientoInvalido: si a la fila le falta una celda, si no se
            reconoce la fecha o el importe, o si el importe no es un número.
    """
    celdas = [str(celda or "").strip() for celda in cells]
    celdas = _descartar_celda_fija(celdas)
    if len(celdas) != 4:
        raise FormatoDeMovimientoInvalido(
            "La fila del portal debe traer 4 celdas (Fecha, Descripción, Referencia y "
            f"Valor); llegaron {len(celdas)}."
        )

    orden = _detectar_orden(celdas)
    fecha = _parsear_fecha(celdas[orden["fecha"]])
    descripcion = _normalizar_texto(celdas[orden["descripcion"]])
    referencia = sanitize_reference(celdas[orden["referencia"]])
    valor = parse_colombian_amount(celdas[orden["valor"]])
    es_ingreso = valor > 0

    return ParsedMovement(
        fecha=fecha,
        descripcion=descripcion,
        referencia=referencia,
        referencia_utilizable=_referencia_utilizable(referencia),
        # El pagador sólo existe en los **ingresos**: en una salida (`PAGO PSE
        # ASOPAGOS`, `PAGO PSE HAAN SAS`) el nombre es a quién se le pagó, no
        # quién pagó.
        pagador_nombre=_extraer_pagador(descripcion) if es_ingreso else "",
        valor=valor,
        direccion=(
            MovementDirection.EGRESO if valor < 0 else MovementDirection.INGRESO
        ),
        es_candidato_pago=es_ingreso,
    )


def _descartar_celda_fija(celdas: list[str]) -> list[str]:
    """Quita la celda *sticky* que duplica la fecha.

    El portal entrega la primera columna dos veces: una como celda fija
    (`bc-table-fixed-column-left`) para que la fecha quede visible al
    desplazamiento horizontal, y la otra como la columna sortable real. Cuando
    las dos primeras celdas son la misma fecha, se descarta la primera.
    """
    if (
        len(celdas) == 5
        and _es_fecha(celdas[0])
        and _es_fecha(celdas[1])
        and _parsear_fecha(celdas[0]) == _parsear_fecha(celdas[1])
    ):
        return celdas[1:]
    return celdas


def _partir_cifras(texto: str) -> tuple[str, str | None]:
    """Separa la parte entera de la decimal en el formato colombiano.

    La coma es el separador decimal y el punto el separador de miles. Cuando
    no hay coma, un punto con tres dígitos es de miles (`1.005` → `1005`) y un
    punto con uno o dos dígitos es decimal (`1.50` → `1.50`).
    """
    if "," in texto:
        entero, _, decimales = texto.rpartition(",")
        return entero.replace(".", ""), decimales
    if _RE_SOLO_MILES.match(texto):
        return texto.replace(".", ""), None
    if _RE_DECIMAL_CON_PUNTO.match(texto):
        entero, _, decimales = texto.partition(".")
        return entero, decimales
    return texto.replace(".", ""), None


def _detectar_orden(celdas: list[str]) -> dict[str, int]:
    """Ubica cada columna por contenido, no por posición a ciegas."""
    for orden in (ORDEN_DE_COLUMNAS, ORDEN_DE_COLUMNAS_ALTERNATIVO):
        if _es_fecha(celdas[orden.index("fecha")]) and _parece_importe(
            celdas[orden.index("valor")]
        ):
            return {nombre: orden.index(nombre) for nombre in orden}
    raise FormatoDeMovimientoInvalido(
        "No se pudo identificar la fecha y el importe de la fila del portal: "
        + " | ".join(celdas)
    )


def _es_fecha(celda: str) -> bool:
    """¿La celda es una fecha que existe en el calendario?

    Acepta los dos formatos reales del portal: `21 oct 2026` (mes en letras) y
    `DD/MM/YYYY`.
    """
    if not _RE_FECHA.match(celda) and not _RE_FECHA_CON_MES.match(celda):
        return False
    try:
        _parsear_fecha(celda)
    except FormatoDeMovimientoInvalido:
        return False
    return True


def _parece_importe(celda: str) -> bool:
    """¿La celda es un importe? (El portal siempre muestra el símbolo pesos.)"""
    if "$" in celda:
        return True
    return bool(_RE_IMPORTE_CON_MILES.match(celda) or _RE_IMPORTE_CON_DECIMAL.match(celda))


def _parsear_fecha(celda: str) -> datetime.date:
    """Fecha del portal: `21 oct 2026` (mes en letras) o `DD/MM/YYYY`."""
    texto = celda.strip()
    coincidencia = _RE_FECHA.match(texto)
    if coincidencia is not None:
        dia, mes, anio = (int(grupo) for grupo in coincidencia.groups())
        return _construir_fecha(dia, mes, anio, texto)

    coincidencia = _RE_FECHA_CON_MES.match(texto)
    if coincidencia is not None:
        dia, mes_texto, anio = coincidencia.groups()
        clave = mes_texto.strip().lower()[:3]
        mes = MESES_EN_ABREVIATURA.get(clave)
        if mes is None:
            raise FormatoDeMovimientoInvalido(
                f"La fecha del movimiento tiene un mes desconocido: {celda!r}"
            )
        return _construir_fecha(int(dia), mes, int(anio), texto)

    raise FormatoDeMovimientoInvalido(
        f"La fecha del movimiento no tiene un formato reconocido: {celda!r}"
    )


def _construir_fecha(dia: int, mes: int, anio: int, original: str) -> datetime.date:
    """Construye la fecha o explica que no existe en el calendario."""
    try:
        return datetime.date(anio, mes, dia)
    except ValueError as exc:
        raise FormatoDeMovimientoInvalido(
            f"La fecha del movimiento no existe en el calendario: {original!r}"
        ) from exc


def _extraer_pagador(descripcion: str) -> str:
    """Nombre del pagador si la descripción es un pago **entrante**.

    El portal real usa dos prefijos de entrada: `PAGO QR <nombre>` y
    `PAGO LLAVE <nombre>`. `PAGO PSE` es una salida (el nombre es el
    acreedor), así que no trae pagador. Cualquier otra descripción deja el
    pagador vacío y no lanza excepción.
    """
    coincidencia = _RE_PAGO.match(descripcion)
    if coincidencia is None:
        return ""
    return _normalizar_texto(coincidencia.group("nombre"))


def _referencia_utilizable(referencia: str) -> bool:
    """Una referencia vacía o de sólo ceros no sirve para conciliar."""
    if not referencia:
        return False
    return referencia.strip("0") != ""


def _normalizar_texto(texto: str) -> str:
    """Espacios colapsados y sin bordes.

    El portal usa espacios **no separables** (U+00A0) entre el símbolo pesos y
    las cifras, y a veces U+202F. Se convierten a un espacio normal para que el
    resto del análisis no dependa del carácter exacto.
    """
    limpio = (texto or "").replace("\u00a0", " ").replace("\u202f", " ")
    return _RE_ESPACIOS.sub(" ", limpio).strip()
