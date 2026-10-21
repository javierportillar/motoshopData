"""Task 3.3 tests (RED): invoice formuleo — exact Decimal parity.

Scenarios (erp-sales-invoicing):
- SI-5s1: line formula `totdet = (valuni − dctpes + ivapes + ipopes) ×
  candet` and header `totfven = subfven − totdct + totiva + totipo` are
  exact Decimal products/sums with NO extra rounding (ADR-0008-07;
  slice-3-parity-test assumption: half-up applies only to derived
  normalized amounts, e.g. inclusive-price splits — not to line/header
  totals).
"""

from __future__ import annotations

from decimal import Decimal

from motoshop_api.erp.invoicing.schemas import InvoiceLineIn
from motoshop_api.erp.invoicing.totals import header_totals, line_totals


def _line(**overrides) -> InvoiceLineIn:
    base = dict(
        codprod="PROD1", nomdet="Bujía NGK Ñ-Spec",
        candet=3, valuni=10000.50, dctpes=500.25, ivapes=950.05, ipopes=0,
    )
    base.update(overrides)
    return InvoiceLineIn(**base)


def test_line_formula_exact():
    computed = line_totals(_line())
    assert computed["totdet"] == Decimal("31350.90")
    assert computed["valuni"] == Decimal("10000.50")
    assert computed["dctpes"] == Decimal("500.25")
    assert computed["ivapes"] == Decimal("950.05")
    assert computed["ipopes"] == Decimal("0")


def test_line_totals_have_no_extra_rounding():
    # repeating product keeps full precision — never quantized to 2 decimals
    line = _line(candet=3, valuni=10.005, dctpes=0, ivapes=0, ipopes=0)
    assert line_totals(line)["totdet"] == Decimal("30.015")


def test_header_formula_subfven_dct_iva():
    lines = [
        _line(),
        _line(codprod="PROD2", candet=2, valuni=2000.00,
              dctpes=0, ivapes=0, ipopes=0),
    ]
    header = header_totals(lines)
    assert header["subfven"] == Decimal("34001.50")
    assert header["totdct"] == Decimal("1500.75")
    assert header["totiva"] == Decimal("2850.15")
    assert header["totipo"] == Decimal("0")
    assert header["totfven"] == Decimal("35350.90")
    assert header["totfven"] == sum(line_totals(l)["totdet"] for l in lines)
