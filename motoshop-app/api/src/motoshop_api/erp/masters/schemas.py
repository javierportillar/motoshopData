"""Pydantic schemas for masters writes (terceros + productos).

Boundary rules (ADR-0008-07):
- All text uses ``LegacyText`` (astral-plane codepoints rejected so the
  latin1 MySQL 5.0.45 connection round-trips without mojibake).
- Money/quantity fields are ``ErpMoney``/``ErpQty`` — ``Decimal``, never float.
- Transaction-owned fields (`exiprod`, cost fields) are accepted only so the
  validator can reject them with the legacy-legacy message (MW-3s2); they
  never reach a write.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from motoshop_api.erp.common.conversions import ErpMoney, ErpQty, LegacyText


def _opt(max_len: int):  # optional string bound (legacy varchar length)
    return Field(default=None, max_length=max_len)


Str30 = _opt(30)
Str100 = _opt(100)
Str120 = _opt(120)


class TerceroCreate(BaseModel):
    """Legacy-required subset per BotGuarMa parity (spec MW-1)."""

    model_config = ConfigDict(extra="forbid")

    nitter: LegacyText = Field(min_length=3, max_length=15, pattern=r"^\d+$")
    tipnit: LegacyText = Field(min_length=1, max_length=2)
    digter: LegacyText = Field(default="", max_length=2, pattern=r"^\d{0,2}$")
    perjur: Literal["S", "N"] = "N"
    apeter: LegacyText | None = Str30
    apeter2: LegacyText | None = Str30
    nomter: LegacyText | None = Str30
    nomter2: LegacyText | None = Str30
    razsoc: LegacyText | None = Str120
    nomcom: LegacyText | None = Str120
    dirter: LegacyText = Field(max_length=100)
    telter: LegacyText = Field(max_length=50)
    movter: LegacyText | None = Field(default=None, max_length=15)
    codciu: LegacyText | None = Field(default=None, max_length=6)
    codzon: LegacyText | None = Field(default=None, max_length=4)
    codlis: LegacyText | None = Field(default=None, max_length=3)
    cupblo: LegacyText = Field(default="R", max_length=1)  # R normal / B blocked
    inater: LegacyText = Field(default="NO", max_length=2)
    emails: list[LegacyText] = Field(default_factory=list, max_length=10)


class TerceroUpdate(BaseModel):
    """Partial edit; identity fields (nitter/tipnit/digter) are immutable."""

    model_config = ConfigDict(extra="forbid")

    apeter: LegacyText | None = Str30
    nomter: LegacyText | None = Str30
    razsoc: LegacyText | None = Str120
    nomcom: LegacyText | None = Str120
    dirter: LegacyText | None = Str100
    telter: LegacyText | None = Field(default=None, max_length=50)
    movter: LegacyText | None = Field(default=None, max_length=15)
    codciu: LegacyText | None = Field(default=None, max_length=6)
    codlis: LegacyText | None = Field(default=None, max_length=3)
    cupblo: LegacyText | None = Field(default=None, max_length=1)
    inater: LegacyText | None = Field(default=None, max_length=2)
    emails: list[LegacyText] | None = None  # full replacement when present


class ProductPriceEntry(BaseModel):
    """Per-list price over `listapre` (spec MW-2, pricing rules modules.md §15).

    Exactly one of ``pvsini`` (exclusive) / ``pvconi`` (inclusive) is supplied;
    the server derives the other pair member with Decimal (MW-2s3).
    """

    model_config = ConfigDict(extra="forbid")

    codlis: LegacyText = Field(min_length=1, max_length=3)
    pvtipo: Literal["1", "2"]  # 2 = IVA-inclusive price level
    pvsini: ErpMoney | None = None
    pvconi: ErpMoney | None = None
    iva_rate: ErpQty = Field(gt=Decimal("0"), le=Decimal("150"))


class UnitEntry(BaseModel):
    """Selling unit with conversion factor (`produndmeds`, ej. caja × 12)."""

    model_config = ConfigDict(extra="forbid")

    codmed: LegacyText = Field(min_length=1, max_length=3)
    divmul: Literal["M", "D"] = "M"
    facumed: ErpQty = Field(gt=Decimal("0"))
    pventa: ErpMoney = Field(default=Decimal("0"), ge=Decimal("0"))
    tipovc: LegacyText = Field(default="0", max_length=1)


class BarcodeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codbar: LegacyText = Field(min_length=1, max_length=30)


class ProductCreate(BaseModel):
    """Product master + units + barcodes + per-list prices (one UoW)."""

    model_config = ConfigDict(extra="forbid")

    codprod: LegacyText = Field(min_length=1, max_length=20)
    nomprod: LegacyText | None = Field(default=None, max_length=200)  # aggregate (MW-3s1)
    codbar: LegacyText | None = Field(default=None, max_length=40)
    codmed: LegacyText = Field(min_length=1, max_length=3)
    valmed: ErpQty = Field(default=Decimal("1"), gt=Decimal("0"))
    codlin1: LegacyText | None = Field(default=None, max_length=4)  # aggregate (MW-3s1)
    actprod: Literal["A", "I", "S"] = "A"
    stockmin: ErpQty = Field(default=Decimal("0"), ge=Decimal("0"))
    stockmax: ErpQty = Field(default=Decimal("0"), ge=Decimal("0"))
    desprod: LegacyText | None = Field(default=None, max_length=800)
    exiprod: ErpQty | None = None  # accepted only to reject with MW-3s2 message
    units: list[UnitEntry] = Field(default_factory=list, max_length=20)
    barcodes: list[BarcodeEntry] = Field(default_factory=list, max_length=20)
    prices: list[ProductPriceEntry] = Field(default_factory=list, max_length=10)


class ProductUpdate(BaseModel):
    """Partial product edit; price changes recompute the pvsini/pvconi pair."""

    model_config = ConfigDict(extra="forbid")

    nomprod: LegacyText | None = Field(default=None, min_length=1, max_length=200)
    codbar: LegacyText | None = Field(default=None, max_length=40)
    codlin1: LegacyText | None = Field(default=None, min_length=1, max_length=4)
    actprod: Literal["A", "I", "S"] | None = None
    stockmin: ErpQty | None = Field(default=None, ge=Decimal("0"))
    stockmax: ErpQty | None = Field(default=None, ge=Decimal("0"))
    desprod: LegacyText | None = Field(default=None, max_length=800)
    exiprod: ErpQty | None = None  # accepted only to reject with MW-3s2 message
    units: list[UnitEntry] | None = None      # full replacement when present
    barcodes: list[BarcodeEntry] | None = None
    prices: list[ProductPriceEntry] | None = None
