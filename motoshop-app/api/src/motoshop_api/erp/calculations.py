"""Pure calculation engine implementing sgHermes reverse-engineered formula.

Exact Colombian 2-decimal roundings:
  dctpes = round(valuni * (discount_pct / 100), 2)
  base = valuni - dctpes
  ivapes = round(base * (vat_pct / 100), 2)
  ipopes = round(base * (ipo_pct / 100), 2)
  totdet = round((valuni - dctpes + ivapes + ipopes) * quantity, 2)
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from motoshop_api.erp.models import DenominationCountIn, POSItemIn, SaleItemOut

DENOMINATION_VALUES: dict[str, Decimal] = {
    "b_100k": Decimal("100000"),
    "b_50k": Decimal("50000"),
    "b_20k": Decimal("20000"),
    "b_10k": Decimal("10000"),
    "b_5k": Decimal("5000"),
    "b_2k": Decimal("2000"),
    "c_1000": Decimal("1000"),
    "c_500": Decimal("500"),
    "c_200": Decimal("200"),
    "c_100": Decimal("100"),
    "c_50": Decimal("50"),
}


def round_cop(value: Decimal) -> Decimal:
    """Exact Colombian 2-decimal rounding using half-up arithmetic."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_line_item(
    unit_price: Decimal | float | int | POSItemIn,
    quantity: Decimal | float | int | None = None,
    discount_pct: Decimal | float | int = Decimal("0"),
    vat_pct: Decimal | float | int = Decimal("0"),
    ipo_pct: Decimal | float | int = Decimal("0"),
    product_id: str = "",
    sku: str = "",
    name: str = "",
    unit_measure: str = "UND",
) -> SaleItemOut:
    """Calculates all line item metrics according to sgHermes specifications."""
    if isinstance(unit_price, POSItemIn):
        item = unit_price
        p_id = item.product_id or item.sku or ""
        s_ku = item.sku or item.product_id or ""
        n_ame = item.name
        u_measure = item.unit_measure
        valuni = item.unit_price
        qty = item.quantity
        dct_p = item.discount_pct
        vat_p = item.vat_pct
        ipo_p = item.ipo_pct
    else:
        p_id = product_id or sku
        s_ku = sku or product_id
        n_ame = name
        u_measure = unit_measure
        valuni = Decimal(str(unit_price))
        qty = Decimal(str(quantity if quantity is not None else 1))
        dct_p = Decimal(str(discount_pct))
        vat_p = Decimal(str(vat_pct))
        ipo_p = Decimal(str(ipo_pct))

    valuni = round_cop(valuni)
    dctpes = round_cop(valuni * (dct_p / Decimal("100")))
    base = round_cop(valuni - dctpes)
    ivapes = round_cop(base * (vat_p / Decimal("100")))
    ipopes = round_cop(base * (ipo_p / Decimal("100")))
    unit_final = valuni - dctpes + ivapes + ipopes
    totdet = round_cop(unit_final * qty)

    return SaleItemOut(
        product_id=p_id,
        sku=s_ku,
        name=n_ame,
        unit_measure=u_measure,
        quantity=qty,
        unit_price=valuni,
        valuni=valuni,
        discount_pct=dct_p,
        dctpes=dctpes,
        base=base,
        vat_pct=vat_p,
        ivapes=ivapes,
        ipo_pct=ipo_p,
        ipopes=ipopes,
        totdet=totdet,
    )


def calculate_sale_totals(items: list[SaleItemOut]) -> dict[str, Decimal]:
    """Calculates header aggregates from calculated line items.

    subfven = Σ (valuni * candet)
    totdct  = Σ (dctpes * candet)
    totiva  = Σ (ivapes * candet)
    totipo  = Σ (ipopes * candet)
    total   = Σ totdet
    """
    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    vat_total = Decimal("0.00")
    ipo_total = Decimal("0.00")
    grand_total = Decimal("0.00")

    for item in items:
        subtotal += round_cop(item.valuni * item.quantity)
        discount_total += round_cop(item.dctpes * item.quantity)
        vat_total += round_cop(item.ivapes * item.quantity)
        ipo_total += round_cop(item.ipopes * item.quantity)
        grand_total += item.totdet

    tax_total = round_cop(vat_total + ipo_total)

    return {
        "subtotal": round_cop(subtotal),
        "discount_total": round_cop(discount_total),
        "vat_total": round_cop(vat_total),
        "ipo_total": round_cop(ipo_total),
        "tax_total": tax_total,
        "grand_total": round_cop(grand_total),
    }


def calculate_denominations_total(
    denominations: DenominationCountIn | dict[str, Any] | None,
) -> Decimal:
    """Calculates the total monetary amount from Colombian bills and coins."""
    if denominations is None:
        return Decimal("0.00")

    if isinstance(denominations, DenominationCountIn):
        counts = denominations.model_dump()
    elif isinstance(denominations, dict):
        counts = DenominationCountIn.model_validate(denominations).model_dump()
    else:
        return Decimal("0.00")

    total = Decimal("0")
    for key, val in DENOMINATION_VALUES.items():
        count = counts.get(key, 0) or 0
        total += val * Decimal(str(count))

    return round_cop(total)
