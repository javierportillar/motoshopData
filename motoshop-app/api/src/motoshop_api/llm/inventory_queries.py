"""Intent parsing for explicit zero-stock replenishment shortlists."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReplenishmentRequest:
    target_cover_days: int = 45
    sales_window_days: int = 180
    limit: int = 50

    def tool_arguments(self) -> dict[str, int]:
        return {
            "target_cover_days": self.target_cover_days,
            "sales_window_days": self.sales_window_days,
            "limit": self.limit,
        }


def parse_replenishment_request(message: str) -> ReplenishmentRequest | None:
    text = unicodedata.normalize("NFKD", message).encode("ascii", "ignore").decode("ascii").lower()
    no_stock = re.search(
        r"\b(?:sin\s+stock|no\s+(?:tengo|hay|queda)\s+(?:nada\s+)?(?:(?:de|en)\s+)?stock|"
        r"stock\s+(?:cero|agotado)|agotad[oa]s?)\b",
        text,
    )
    action = re.search(
        r"\b(?:reponer|reabastecer|enlistar|siguiente\s+compra|proxima\s+compra|"
        r"deberia\s+comprar|debo\s+comprar|comprar)\b",
        text,
    )
    if no_stock is None or action is None:
        return None
    target = re.search(r"\b(\d{1,3})\s+dias?\s+(?:de\s+)?cobertura\b", text)
    window = re.search(r"\b(?:ultimos?|ultimas?)\s+(\d{1,3})\s+dias?\b", text)
    return ReplenishmentRequest(
        target_cover_days=int(target.group(1)) if target else 45,
        sales_window_days=int(window.group(1)) if window else 180,
    )
