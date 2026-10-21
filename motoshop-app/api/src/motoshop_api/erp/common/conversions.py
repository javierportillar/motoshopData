"""Decimal + latin1 boundary palette between the API and legacy MySQL 5.0.45.

ADR-0008-07 rules materialized here:
- Money/quantity values are `Decimal` from the API boundary onward — never
  float. Values stored in varchar numerics (`valuni`, `dctpes`, `ivapes`,
  `ipopes`, `candet`, `totdet`, `totfven`…) pass through the
  ``to_legacy_num``/``from_legacy_num`` string palette, which also accepts the
  comma-decimal ``Conversion.Val``/``PuntX_Coma`` legacy rows.
- Arithmetic uses exact Decimal operations; ROUND_HALF_UP quantization exists
  ONLY for derived normalized amounts (inclusive-price splits, arqueo sums) —
  stored passthrough values are never silently quantized. Line/header totals
  are exact products/sums (slice-3 parity tests validate against formuleo).
- Text entering the write path must be latin1-representable (MySQL 5.0.45 has
  no utf8/utf8mb4); ``LegacyText`` rejects astral-plane codepoints so the
  latin1 connection round-trips without mojibake.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated
import re

from pydantic import BeforeValidator, Field

_NUMERIC_RE = re.compile(r"^-?\d+$")
# latin1 alphabet size; anything above or any surrogates cannot round-trip
# through the MySQL 5.0.45 latin1 connection without mojibake.
_LATIN1_MAX_CODEPOINT = 0xFF


class LegacyValueError(ValueError):
    """A legacy numeric string cannot be parsed to a Decimal exactly."""


# ─── Numeric palette ───────────────────────────────────────────


def to_legacy_num(value: Decimal, *, decimal_comma: bool = False) -> str:
    """Decimal → legacy varchar-string numeric; NO quantization applied.

    ``decimal_comma=True`` renders in the ``PuntX_Coma`` legacy style
    (``"19990,625"``); the default renders with ``.``.
    """
    text = str(value)
    return text.replace(".", ",") if decimal_comma else text


def from_legacy_num(raw: str | Decimal | None) -> Decimal:
    """Legacy varchar numeric → Decimal, exactly.

    Accepts ``.`` and ``,`` decimal separators (the two legacy row styles:
    ``Conversion.Val`` dot-style and ``PuntX_Coma`` comma-style) plus dot /
    comma as thousands markers when the other separator carries the decimals.
    Blank/None parse to zero. Anything ambiguous or non-numeric raises
    LegacyValueError — those columns are weakly typed, and a silent zero
    would corrupt the formuleo.
    """
    if raw is None:
        return Decimal("0")
    if isinstance(raw, Decimal):
        return raw
    text = str(raw).strip().replace(" ", "")
    if not text:
        return Decimal("0")

    if "," in text and "." in text:
        # Mixed separators: whichever appears LAST carries the decimals.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") > 1 or text.count(".") > 1:
        # Repeated single separator: thousands markers, e.g. "1,234,567".
        text = text.replace(",", "").replace(".", "") or text
        if not _NUMERIC_RE.fullmatch(text):
            raise LegacyValueError(f"unparseable legacy numeric: {raw!r}")
        return Decimal(text)
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise LegacyValueError(f"unparseable legacy numeric: {raw!r}") from exc


def quantize_half_up(value: Decimal, places: int = 2) -> Decimal:
    """ROUND_HALF_UP quantization — ONLY for derived normalized amounts."""
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


# ─── Pydantic boundary types ───────────────────────────────────

MONEY_MAX_DIGITS = Field(max_digits=15, decimal_places=6)
QTY_MAX_DIGITS = Field(max_digits=15, decimal_places=3)

ErpMoney = Annotated[Decimal, BeforeValidator(from_legacy_num), MONEY_MAX_DIGITS]
ErpQty = Annotated[Decimal, BeforeValidator(from_legacy_num), QTY_MAX_DIGITS]


def _validate_latin1_text(value: object) -> str:
    """Reject text that cannot round-trip the latin1 connection (WF-7s2)."""
    text = value if isinstance(value, str) else str(value)
    for char in text:
        codepoint = ord(char)
        if codepoint >= 0xD800 and codepoint <= 0xDFFF:  # surrogate pair remnants
            raise ValueError(
                f"cod U+{codepoint:04X} (surrogate) no representable en latin1"
            )
        if codepoint > _LATIN1_MAX_CODEPOINT:
            raise ValueError(
                f"cod U+{codepoint:04X} fuera de latin1 (MySQL 5.0.45); "
                "el texto debe ser latin1-representable"
            )
    return text


LegacyText = Annotated[str, BeforeValidator(_validate_latin1_text)]
