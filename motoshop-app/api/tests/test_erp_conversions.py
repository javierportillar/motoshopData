"""Task 1.5 tests: Decimal + latin1 conversion palette (WF-7s1, WF-7s2).

Contract (ADR-0008-07):
- Money and quantities are handled as Decimal from the API boundary onward;
  varchar-numeric legacy columns round-trip without float drift.
- latin1 (MySQL 5.0.45 charset) text round-trips without mojibake; text that
  cannot be represented in latin1 (astral-plane codepoints, surrogate pairs)
  is rejected at the Pydantic boundary.
- Legacy comma-decimal rows (Conversion.Val / PuntX_Coma style) parse to
  exact Decimals.
- ROUND_HALF_UP quantization applies ONLY to derived normalized amounts;
  stored passthrough values are never quantized.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from motoshop_api.erp.common.conversions import (
    ErpMoney,
    ErpQty,
    LegacyText,
    from_legacy_num,
    quantize_half_up,
    to_legacy_num,
)


# ─── WF-7s1 Decimal round-trip is exact ────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        Decimal("19990.625"),
        Decimal("31350.90"),
        Decimal("0.05"),
        Decimal("77500"),
        Decimal("1234567.89"),
    ],
)
def test_numeric_roundtrip_is_exact(value: Decimal):
    stored = to_legacy_num(value)
    assert isinstance(stored, str)
    assert from_legacy_num(stored) == value  # no float intermediates


def test_float_never_used_for_money_boundary():
    value = Decimal("19990.625")
    legacy = to_legacy_num(value)
    # the stored string must not have gone through a float (which would
    # render 31350.90-style values with binary noise like ...8999999)
    assert legacy == "19990.625"
    assert from_legacy_num("31350.90") == Decimal("31350.90")


def test_header_total_precision_survives():
    # slice-3 formuleo example: (10000.50 − 500.25 + 950.05 + 0) × 3
    line = (Decimal("10000.50") - Decimal("500.25") + Decimal("950.05")) * 3
    assert line == Decimal("31350.90")
    assert from_legacy_num(to_legacy_num(line)) == line


# ─── WF-7s2 accented text survives latin1 ──────────────────────


def test_latin1_roundtrip_without_mojibake():
    name = "Bujía NGK Ñ-P"
    stored_bytes = name.encode("latin1")
    assert stored_bytes == b"Buj\xeda NGK \xd1-P"
    back = stored_bytes.decode("latin1")
    assert back == name


def test_legacy_text_field_accepts_accented_names():
    class Product(BaseModel):
        name: LegacyText

    assert Product(name="Bujía NGK Ñ-P").name == "Bujía NGK Ñ-P"


def test_legacy_text_field_rejects_astral_plane_codepoints():
    class Product(BaseModel):
        name: LegacyText

    with pytest.raises(ValidationError):
        Product(name="emoji \U0001f680")  # astral plane (not latin1-representable)


def test_legacy_text_rejects_cyrillic_and_cjk():
    class Product(BaseModel):
        name: LegacyText

    with pytest.raises(ValidationError):
        Product(name="кириллица")
    with pytest.raises(ValidationError):
        Product(name="铝合金汽缸")


# ─── Comma-decimal legacy rows (PuntX_Coma / Conversion.Val) ───


def test_from_legacy_num_accepts_comma_decimals():
    assert from_legacy_num("19990,625") == Decimal("19990.625")
    assert from_legacy_num("31350,90") == Decimal("31350.90")


def test_from_legacy_num_accepts_dot_decimals_empty_and_none():
    assert from_legacy_num("10.75") == Decimal("10.75")
    assert from_legacy_num("") == Decimal("0")
    assert from_legacy_num(None) == Decimal("0")
    assert from_legacy_num("   ") == Decimal("0")


def test_to_legacy_num_can_emit_comma_decimal_style():
    out = to_legacy_num(Decimal("19990.625"), decimal_comma=True)
    assert out == "19990,625"
    assert from_legacy_num(out) == Decimal("19990.625")


def test_from_legacy_num_rejects_garbage():
    with pytest.raises(ValueError):
        from_legacy_num("ABC")

    with pytest.raises(ValueError):
        from_legacy_num("12,3.4,5")


# ─── Rounding: HALF_UP only for derived normalized amounts ─────


def test_quantize_half_up_used_only_for_derived_amounts():
    assert quantize_half_up(Decimal("100.005")) == Decimal("100.01")
    assert quantize_half_up(Decimal("100.004")) == Decimal("100.00")
    # passthrough values keep their full precision (never auto-quantized)
    assert to_legacy_num(Decimal("19990.625")) == "19990.625"


def test_money_amount_quantize_is_half_up_not_bankers():
    # Python default rounding is ROUND_HALF_EVEN: 105.125 → 105.12; legacy
    # parity requires ROUND_HALF_UP → 105.13
    assert quantize_half_up(Decimal("105.125")) == Decimal("105.13")


# ─── Pydantic boundary coerces legacy numerics to Decimal ──────


def test_erp_money_and_qty_types_coerce_legacy_strings():
    class Line(BaseModel):
        valuni: ErpMoney
        candet: ErpQty

    line = Line(valuni="19990,625", candet="3")
    assert line.valuni == Decimal("19990.625")
    assert line.candet == Decimal("3")


def test_erp_money_rejects_float_noise_input():
    class Line(BaseModel):
        valuni: ErpMoney

    with pytest.raises(ValidationError):
        Line(valuni="n/a-not-a-number")
