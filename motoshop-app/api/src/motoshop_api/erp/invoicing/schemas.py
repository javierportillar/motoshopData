"""Invoice save schemas (POS sale request payloads).

The client sends per-line prices/discounts/taxes and its OWN header totals
(``client_totals``) when the POS UI already computed them; the server
recomputes everything with exact Decimal formuleo (ADR-0008-07) and rejects
mismatches 422 naming the field (SI-5s2). Costs and stock are
transaction-owned: the client never sends them.

The schema owns the *shape* of the payload (latin1 text, decimal digits, at
least one line). The *business* rules (positive quantity, non-negative
amounts, non-negative total, payment sum = total, master state) live in the
repo so they surface as one aggregate 422 body naming every offending field
instead of a pydantic error list (spec SI-6s2).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from motoshop_api.erp.common import ErpMoney, ErpQty, LegacyText

_STR_MAX = Field(max_length=200)


class InvoiceLineIn(BaseModel):
    """One `detfventas` line as the POS client sends it.

    ``totdet`` is NEVER accepted from the client — the server computes
    ``totdet = (valuni − dctpes + ivapes + ipopes) × candet`` exactly.
    """

    model_config = ConfigDict(extra="forbid")

    codprod: LegacyText = Field(min_length=1, max_length=20)
    nomdet: LegacyText | None = _STR_MAX  # frozen description; server fills
    candet: ErpQty = Field(default=Decimal("1"))
    valuni: ErpMoney = Field(default=Decimal("0"))
    dctpes: ErpMoney = Field(default=Decimal("0"))
    ivapes: ErpMoney = Field(default=Decimal("0"))
    ipopes: ErpMoney = Field(default=Decimal("0"))
    dctpor: ErpQty = Field(default=Decimal("0"))
    ivapor: ErpQty = Field(default=Decimal("0"))
    ipopor: ErpQty = Field(default=Decimal("0"))
    codbod: LegacyText = Field(default="01", min_length=1, max_length=2)
    codmed: LegacyText = Field(default="UND", min_length=1, max_length=3)
    facumed: ErpQty = Field(default=Decimal("1"))


class ClientTotals(BaseModel):
    """Client-computed header snapshot for mismatch detection (SI-5s2).

    Omitted fields are not compared; present fields must match the server
    formuleo exactly.
    """

    model_config = ConfigDict(extra="forbid")

    subfven: ErpMoney | None = None
    totdct: ErpMoney | None = None
    totiva: ErpMoney | None = None
    totipo: ErpMoney | None = None
    totfven: ErpMoney | None = None


class InvoicePaymentIn(BaseModel):
    """One `detapago` payment line (minimal slice-3 capture).

    ``amount`` is the payment value; duality fields (soldeb/solcre) are the
    save engine's job (task 3.4), never client data. A non-positive amount is
    rejected by the repo with the aggregate 422 body.
    """

    model_config = ConfigDict(extra="forbid")

    codpag: LegacyText = Field(min_length=1, max_length=8)
    amount: ErpMoney = Field(default=Decimal("0"))
    referencia: LegacyText | None = Field(default=None, max_length=40)


class InvoiceCreate(BaseModel):
    """POST /api/erp/invoices body."""

    model_config = ConfigDict(extra="forbid")

    nitter: LegacyText = Field(min_length=1, max_length=15)
    nitvend: LegacyText = Field(min_length=1, max_length=13)  # seller (venfven)
    #: The client's name (legacy ``facventas.clifven``) - optional.
    nomclien: LegacyText | None = Field(default=None, max_length=120)
    codcaj: LegacyText = Field(default="01", min_length=1, max_length=3)
    obsfven: LegacyText | None = Field(default=None, max_length=120)
    lines: list[InvoiceLineIn] = Field(min_length=1)
    payments: list[InvoicePaymentIn] = Field(default_factory=list)
    client_totals: ClientTotals | None = None
