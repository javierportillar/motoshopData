"""Contratos de entrada y salida de los movimientos bancarios (S4).

Un movimiento es lo que el portal del banco muestra: un identificador externo,
una fecha, un importe, el pagador y la referencia. El estado (`EstadoMovimiento`)
es del ciclo de conciliación y lo escribe la capa de matching, no el portal.

Reglas de la frontera:
- los importes son `Decimal` exactos con 2 decimales (`DECIMAL(18,2)`), nunca
  float (ADR-0008-07);
- los modelos son cerrados (`extra="forbid"`): un campo de más es un error, no
  un dato ignorado en silencio.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from motoshop_api.erp.common.conversions import from_legacy_num


class EstadoMovimiento(StrEnum):
    """Estados del ciclo de conciliación de un movimiento."""

    PENDIENTE = "PENDIENTE"
    APLICADO = "APLICADO"
    AMBIGUA = "AMBIGUA"
    SIN_MATCH = "SIN_MATCH"
    SOBREPAGO = "SOBREPAGO"
    IGNORADO = "IGNORADO"


#: Importes: `DECIMAL(18,2)` — exacto, sin float y sin más de dos decimales.
BankMoney = Annotated[
    Decimal,
    BeforeValidator(from_legacy_num),
    Field(max_digits=18, decimal_places=2),
]


class BankMovementIn(BaseModel):
    """Movimiento leído del portal: la entrada de la ingesta."""

    model_config = ConfigDict(extra="forbid")

    id_externo: str = Field(min_length=1, max_length=64)
    fecha_movimiento: datetime.date
    valor: BankMoney
    descripcion: str = Field(default="", max_length=255)
    referencia: str = Field(default="", max_length=64)
    referencia_norm: str = Field(default="", max_length=64)
    pagador_nombre: str = Field(default="", max_length=128)
    cuenta_origen: str = Field(default="", max_length=64)


class BankMovementOut(BankMovementIn):
    """Movimiento persistido: la lectura (identidad, tenant y estado)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant: str
    empresa: str
    estado: EstadoMovimiento
    recibo_numero: str | None = None
    recibo_pref: str | None = None
    confianza: int | None = None
    razones: str | None = None
    scraped_at: datetime.datetime | None = None
