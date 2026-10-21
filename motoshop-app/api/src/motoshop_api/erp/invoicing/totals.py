"""Server-side formuleo — exact Decimal parity with the legacy POS form.

Legacy parity (docs/hermes/code_analysis.md §4, ADR-0008-07):

    totdet = (valuni − dctpes + ivapes + ipopes) × candet
    subfven = Σ valuni × candet
    totdct  = Σ dctpes × candet
    totiva  = Σ ivapes × candet
    totipo  = Σ ipopes × candet
    totfven = subfven − totdct + totiva + totipo

``dctpes``/``ivapes``/``ipopes`` are PER-UNIT amounts (the percentages live in
``dctpor``/``ivapor``/``ipopor``). The arithmetic is exact Decimal — no
quantization is applied to line or header totals (ROUND_HALF_UP is reserved
for derived normalized amounts, ADR-0008-07); the slice-3 parity tests pin
the exactness.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal

from motoshop_api.erp.invoicing.schemas import InvoiceLineIn

ZERO = Decimal("0")

__all__ = [
    "aggregate_totals",
    "header_totals",
    "line_totals",
]


def _dec(value: object) -> Decimal:
    """Legacy numeric → Decimal (exact; never a float)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def line_totals(line: InvoiceLineIn) -> dict[str, Decimal]:
    """Line figures: ``totdet`` plus the per-unit and extended amounts.

    ``totdet`` is the only figure the client never sends: the server owns it
    (spec SI-5s1). ``neto``/``iva``/``ipo`` are the extended (× candet)
    counterparts used by the header aggregates and the accounting causación.
    """
    valuni = _dec(line.valuni)
    dctpes = _dec(line.dctpes)
    ivapes = _dec(line.ivapes)
    ipopes = _dec(line.ipopes)
    candet = _dec(line.candet)
    return {
        "valuni": valuni,
        "dctpes": dctpes,
        "ivapes": ivapes,
        "ipopes": ipopes,
        "candet": candet,
        "totdet": (valuni - dctpes + ivapes + ipopes) * candet,
        "neto": (valuni - dctpes) * candet,
        "iva": ivapes * candet,
        "ipo": ipopes * candet,
    }


def aggregate_totals(
    computed: Iterable[Mapping[str, Decimal]],
) -> dict[str, Decimal]:
    """Header aggregates from already-computed lines (exact Decimal sums)."""
    rows = list(computed)
    subfven = sum((row["valuni"] * row["candet"] for row in rows), ZERO)
    totdct = sum((row["dctpes"] * row["candet"] for row in rows), ZERO)
    totiva = sum((row["ivapes"] * row["candet"] for row in rows), ZERO)
    totipo = sum((row["ipopes"] * row["candet"] for row in rows), ZERO)
    return {
        "subfven": subfven,
        "totdct": totdct,
        "totiva": totiva,
        "totipo": totipo,
        "totfven": subfven - totdct + totiva + totipo,
    }


def header_totals(lines: Iterable[InvoiceLineIn]) -> dict[str, Decimal]:
    """Header totals of the invoice lines (spec SI-5s1)."""
    return aggregate_totals(line_totals(line) for line in lines)
