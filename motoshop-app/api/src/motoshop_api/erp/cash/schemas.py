"""Collections & cash request schemas (slice 4 — erp-collections-cash).

The client sends the *business* facts only (who pays, how much, which form of
payment, which document is being collected). Every total, every account and
every document number is server-owned:

- the receipt amount is validated against the LIVE CxC balance
  (``SUM(detcuentas.valdeb − valhab)`` on the cartera account) — the client
  never declares the balance it is paying (spec CC-1);
- the debit/credit duality of the payment row is derived from the document
  class (``tipclas``), never from client data (spec CC-2, ``Graba_Fpago``);
- the arqueo header total is recomputed from the denomination rows (CC-4);
- the egress total (``totegr``) is computed server-side (CC-3).

Shape errors are pydantic errors; BUSINESS errors live in the repos so they
surface as one aggregate 422 body naming every offending field.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from motoshop_api.erp.common import ErpMoney, LegacyText

_STR_MAX = Field(max_length=200)


class ReceiptCreate(BaseModel):
    """POST /api/erp/receipts body — a cash receipt (S01) against open CxC.

    ``numfven``/``prefven`` point at the invoice whose cartera balance is
    being collected. ``tipclas`` drives the payment duality (CC-2); it defaults
    to S01 (RECIBO DE CAJA) and may only name a payment-capable document class.
    """

    model_config = ConfigDict(extra="forbid")

    nitter: LegacyText = Field(min_length=1, max_length=15)
    numfven: int = Field(ge=1)
    prefven: LegacyText = Field(default="FVP", min_length=1, max_length=8)
    codpag: LegacyText = Field(min_length=1, max_length=8)
    valor: ErpMoney = Field(default=Decimal("0"))
    fecha: date = Field(default_factory=date.today)
    codcaj: LegacyText = Field(default="01", min_length=1, max_length=4)
    tipclas: LegacyText = Field(default="S01", min_length=1, max_length=4)
    referencia: LegacyText | None = Field(default=None, max_length=40)
    concepto: LegacyText | None = Field(default=None, max_length=100)


class CashMovementCreate(BaseModel):
    """POST /api/erp/cash/movements body — concept cash movement (in/out).

    ``tipo`` selects the legacy document class: ``ENTRADA`` → S03 (ingreso),
    ``SALIDA`` → S02 (egreso). Both are stored in ``comprobantes`` and caused
    into ``detcuentas`` (debit expense / credit cash, or the mirror).
    """

    model_config = ConfigDict(extra="forbid")

    tipo: LegacyText = Field(min_length=1, max_length=8)
    codcon: LegacyText = Field(min_length=1, max_length=12)
    valor: ErpMoney = Field(default=Decimal("0"))
    fecha: date = Field(default_factory=date.today)
    codpag: LegacyText = Field(default="01", min_length=1, max_length=8)
    codcaj: LegacyText = Field(default="01", min_length=1, max_length=4)
    nitter: LegacyText | None = Field(default=None, max_length=15)
    concepto: LegacyText | None = Field(default=None, max_length=120)


class EgressCreate(BaseModel):
    """POST /api/erp/cash/egresos body — comprobante de egreso (S02).

    Same shape as a cash movement forced to ``SALIDA``; kept as its own model
    so the legacy-named endpoint keeps its own contract (CC-3).
    """

    model_config = ConfigDict(extra="forbid")

    codcon: LegacyText = Field(min_length=1, max_length=12)
    valor: ErpMoney = Field(default=Decimal("0"))
    fecha: date = Field(default_factory=date.today)
    codpag: LegacyText = Field(default="01", min_length=1, max_length=8)
    codcaj: LegacyText = Field(default="01", min_length=1, max_length=4)
    nitter: LegacyText | None = Field(default=None, max_length=15)
    concepto: LegacyText | None = Field(default=None, max_length=120)


class ArqueoDenominationIn(BaseModel):
    """One ``detcajarq`` row: a denomination and how many were counted."""

    model_config = ConfigDict(extra="forbid")

    denarq: ErpMoney = Field(default=Decimal("0"))
    cantden: int = Field(default=1, ge=1)
    tiparq: int = Field(ge=1, le=3)  # 1=billetes 2=monedas 3=otros
    tipdet: LegacyText | None = Field(default=None, max_length=30)
    bandes: LegacyText | None = Field(default=None, max_length=150)
    numche: LegacyText | None = Field(default=None, max_length=30)


class ArqueoCreate(BaseModel):
    """POST /api/erp/cash/arqueo body — cash count (S38).

    ``salcaj`` is optional: when present it is CHECKED against the
    denomination sum (CC-4s2 — a mismatch is a 422 that persists nothing);
    when absent the server owns the total (CC-4s1).
    """

    model_config = ConfigDict(extra="forbid")

    fecha: date = Field(default_factory=date.today)
    codcaj: LegacyText = Field(default="01", min_length=1, max_length=4)
    codcue: LegacyText = Field(default="1105", min_length=1, max_length=12)
    nitter: LegacyText | None = Field(default=None, max_length=15)
    salcaj: ErpMoney | None = None
    obsarq: LegacyText | None = Field(default=None, max_length=400)
    rows: list[ArqueoDenominationIn] = Field(min_length=1)


class ConsignmentCreate(BaseModel):
    """POST /api/erp/bank/consignments body — bank consignment (CC-5).

    The consignment number comes from the payment form's own counter
    (``formapago.numcon``), NOT from ``contadores`` (legacy §3).
    """

    model_config = ConfigDict(extra="forbid")

    codpag: LegacyText = Field(min_length=1, max_length=8)
    valor: ErpMoney = Field(default=Decimal("0"))
    fecha: date = Field(default_factory=date.today)
    codcaj: LegacyText = Field(default="01", min_length=1, max_length=4)
    codban: LegacyText | None = Field(default=None, max_length=8)
    detalle: LegacyText | None = Field(default=None, max_length=300)
    tipret: LegacyText = Field(default="DEPOSITO", max_length=8)
