"""Receipt payload (P80 ticket) — built OUTSIDE the save unit-of-work.

Spec SI-10: the browser renders the ticket from a JSON payload; the legacy
desktop printed it with GDI *after* the save (`Varuno.Imp_Des_Gra` →
`Botonesaux.Bot_Imprimir`, code_analysis §5.6) — never inside the
transaction. The payload therefore carries:

``header``      documento (número, prefijo, fecha, cliente, vendedor, caja)
``resolution``  datos de la resolución (tipo de documento, prefijo, rango)
``lines``       detalle con cantidades y montos
``totals``      totales del documento
``payments``    formas de pago aplicadas
``qr``          marcador explícito del QR DIAN (placeholder mientras no
                exista CUFE — spec DI-5s2: jamás un CUFE inventado)

Amounts travel as Decimal strings (ADR-0008-07: nunca float).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

QR_PLACEHOLDER_LABEL = "QR DIAN pendiente de aceptación"

__all__ = ["QR_PLACEHOLDER_LABEL", "build_receipt", "decimal_str"]


def decimal_str(value: object) -> str:
    """Decimal → exact legacy-friendly string (never a float)."""
    if isinstance(value, Decimal):
        return str(value)
    if value is None:
        return "0"
    return str(Decimal(str(value)))


def build_receipt(
    *,
    header: Mapping[str, Any],
    resolution: Mapping[str, Any],
    lines: Sequence[Mapping[str, Any]],
    payments: Sequence[Mapping[str, Any]],
    totals: Mapping[str, Any],
    warnings: Sequence[Mapping[str, Any]] = (),
    qr_url: str | None = None,
) -> dict[str, Any]:
    """Assemble the receipt payload (no I/O — the caller supplies the rows)."""
    qr: dict[str, Any] = {
        "placeholder": qr_url is None,
        "label": QR_PLACEHOLDER_LABEL if qr_url is None else "QR DIAN",
        "url": qr_url,
    }
    return {
        "header": {k: v for k, v in header.items()},
        "resolution": {k: v for k, v in resolution.items()},
        "lines": [
            {
                "numite": row.get("numite"),
                "codprod": row.get("codprod", ""),
                "nomdet": row.get("nomdet", ""),
                "candet": decimal_str(row.get("candet", 0)),
                "valuni": decimal_str(row.get("valuni", 0)),
                "dctpes": decimal_str(row.get("dctpes", 0)),
                "ivapes": decimal_str(row.get("ivapes", 0)),
                "ipopes": decimal_str(row.get("ipopes", 0)),
                "totdet": decimal_str(row.get("totdet", 0)),
            }
            for row in lines
        ],
        "totals": {
            "subfven": decimal_str(totals.get("subfven", 0)),
            "totdct": decimal_str(totals.get("totdct", 0)),
            "totiva": decimal_str(totals.get("totiva", 0)),
            "totipo": decimal_str(totals.get("totipo", 0)),
            "totfven": decimal_str(totals.get("totfven", 0)),
        },
        "payments": [
            {
                "numite": row.get("numite"),
                "codpag": row.get("codpag", ""),
                "despag": row.get("despag", ""),
                "valpag": decimal_str(row.get("valpag", 0)),
                "valefe": decimal_str(row.get("valefe", 0)),
                "soldeb": decimal_str(row.get("soldeb", 0)),
                "solcre": decimal_str(row.get("solcre", 0)),
                "estado": row.get("estado", "B"),
                "referencia": row.get("referencia") or row.get("numpag") or "",
            }
            for row in payments
        ],
        "qr": qr,
        "warnings": [dict(warning) for warning in warnings],
    }
