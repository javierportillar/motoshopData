"""Matching explicable de un movimiento bancario contra facturas abiertas.

El puntaje es una **suma de señales ponderadas**, y cada candidatura expone
cuáles coincidieron para que el operador entienda por qué el sistema la propone:

| Señal                  | Peso |
| ---------------------- | ---- |
| Referencia exacta      | 100  |
| NIT del pagador        | 80   |
| Nombre normalizado     | 60   |
| Importe exacto         | 40   |
| Importe parcial        | 20   |

Es una función **pura**: no toca base de datos, ni red, ni reloj. Eso es lo que
la hace testeable y lo que garantiza que el mismo movimiento y las mismas
facturas den siempre el mismo resultado.

La aplicación NUNCA es automática: con puntaje ≥ 80 y candidata única el
movimiento queda *listo para aplicar*, y el operador confirma.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

PESO_REFERENCIA = 100
PESO_NIT = 80
PESO_NOMBRE = 60
PESO_IMPORTE_EXACTO = 40
PESO_IMPORTE_PARCIAL = 20

#: Puntaje mínimo para considerar una factura "plausible" para el operador.
UMBRAL_LISTO_PARA_APLICAR = 80

_SUFIJO_NULL = re.compile(r"\s*null\s*$", re.IGNORECASE)
_NO_DIGITOS = re.compile(r"\D+")
_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9 ]+")
_ESPACIOS = re.compile(r"\s+")

_SUFIJOS_EMPRESA = (
    "S A S",
    "SAS",
    "S A",
    "SA",
    "LTDA",
    "LIMITADA",
)


class MovimientoParaMatching(Protocol):
    """Lo mínimo que el matching necesita de un movimiento del banco."""

    tenant: str
    valor: Decimal
    descripcion: str
    referencia: str
    referencia_norm: str
    pagador_nombre: str


@dataclass(frozen=True, slots=True)
class FacturaCandidata:
    """Factura abierta contra la que se puede conciliar un movimiento."""

    factura_id: str
    tenant: str
    numfven: int
    prefven: str
    nitter: str
    cliente_nombre: str
    saldo: Decimal
    referencia: str | None = None


@dataclass(frozen=True, slots=True)
class Candidatura:
    """Una factura puntuada, con las señales que la hicieron subir."""

    factura_id: str
    score: int
    razones: tuple[str, ...]


def normalizar_referencia(valor: str | None) -> str:
    """Deja sólo dígitos, sin el sufijo ``" null"`` y sin ceros a la izquierda.

    El portal del banco agrega ``" null"`` al final de la referencia y la
    presenta con ceros a la izquierda; la factura no lleva ninguna de las dos
    cosas. Comparar en crudo nunca daría match.
    """
    if not valor:
        return ""
    sin_null = _SUFIJO_NULL.sub("", valor)
    digitos = _NO_DIGITOS.sub("", sin_null)
    limpio = digitos.lstrip("0")
    # Una referencia que era sólo ceros es indistinguible del vacío.
    return limpio


def normalizar_nombre(valor: str | None) -> str:
    """Mayúsculas, sin tildes, sin signos y sin sufijos societarios."""
    if not valor:
        return ""
    descompuesto = unicodedata.normalize("NFKD", valor)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    mayusculas = _NO_ALFANUMERICO.sub(" ", sin_tildes.upper())
    colapsado = _ESPACIOS.sub(" ", mayusculas).strip()
    for sufijo in _SUFIJOS_EMPRESA:
        if colapsado.endswith(f" {sufijo}"):
            colapsado = colapsado[: -(len(sufijo) + 1)].strip()
            break
    return colapsado


def _digitos(valor: str | None) -> str:
    return _NO_DIGITOS.sub("", valor or "")


def _coincide_nit(movimiento: MovimientoParaMatching, factura: FacturaCandidata) -> bool:
    """El NIT del cliente aparece en el texto que publicó el banco.

    El portal no expone el NIT como campo: cuando el pagador lo incluye, viaja
    dentro de la descripción, la referencia o el nombre. Se compara por dígitos
    para que ``900.123.456-7`` y ``9001234567`` sean el mismo NIT.
    """
    nit = _digitos(factura.nitter)
    if len(nit) < 6:
        return False
    texto = " ".join(
        (
            movimiento.descripcion or "",
            movimiento.referencia or "",
            movimiento.pagador_nombre or "",
        )
    )
    return nit in _digitos(texto)


def _coincide_nombre(movimiento: MovimientoParaMatching, factura: FacturaCandidata) -> bool:
    esperado = normalizar_nombre(factura.cliente_nombre)
    if not esperado:
        return False
    publicado = normalizar_nombre(movimiento.pagador_nombre)
    if not publicado:
        return False
    return esperado in publicado or publicado in esperado


def _coincide_referencia(movimiento: MovimientoParaMatching, factura: FacturaCandidata) -> bool:
    esperada = normalizar_referencia(factura.referencia)
    if not esperada:
        return False
    publicada = normalizar_referencia(movimiento.referencia_norm or movimiento.referencia)
    return esperada == publicada


def puntuar(movimiento: MovimientoParaMatching, factura: FacturaCandidata) -> Candidatura:
    """Puntúa una factura y explica por qué."""
    score = 0
    razones: list[str] = []

    if _coincide_referencia(movimiento, factura):
        score += PESO_REFERENCIA
        razones.append("referencia_exacta")

    if _coincide_nit(movimiento, factura):
        score += PESO_NIT
        razones.append("nit_pagador")

    if _coincide_nombre(movimiento, factura):
        score += PESO_NOMBRE
        razones.append("nombre_normalizado")

    if movimiento.valor == factura.saldo:
        score += PESO_IMPORTE_EXACTO
        razones.append("importe_exacto")
    elif movimiento.valor < factura.saldo:
        score += PESO_IMPORTE_PARCIAL
        razones.append("importe_parcial")

    return Candidatura(
        factura_id=factura.factura_id,
        score=score,
        razones=tuple(razones),
    )


def score_candidates(
    movimiento: MovimientoParaMatching,
    facturas: Sequence[FacturaCandidata],
) -> list[Candidatura]:
    """Puntúa todas las facturas y devuelve las que tienen alguna señal.

    El orden es de mayor a menor puntaje; a igual puntaje, el orden de entrada
    se conserva (lo que permite al llamador detectar la ambigüedad).
    """
    # Defensa en profundidad: una factura de otro tenant no puede ser candidata
    # aunque el llamador se equivoque al armar la lista.
    propias = [factura for factura in facturas if factura.tenant == movimiento.tenant]
    candidaturas = [puntuar(movimiento, factura) for factura in propias]
    con_senal = [c for c in candidaturas if c.score > 0]
    return sorted(con_senal, key=lambda c: c.score, reverse=True)


def es_sobrepago(
    movimiento: MovimientoParaMatching,
    facturas: Sequence[FacturaCandidata],
    candidaturas: Sequence[Candidatura],
) -> bool:
    """El movimiento trae más plata que el saldo de la mejor factura plausible.

    Un sobrepago no se aplica ni se parte: lo resuelve el operador.
    """
    if not candidaturas:
        return False
    mejor = candidaturas[0]
    if mejor.score < UMBRAL_LISTO_PARA_APLICAR:
        return False
    saldos = {factura.factura_id: factura.saldo for factura in facturas}
    saldo = saldos.get(mejor.factura_id)
    return saldo is not None and movimiento.valor > saldo
