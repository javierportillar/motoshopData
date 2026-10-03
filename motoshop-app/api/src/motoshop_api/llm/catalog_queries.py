"""Intent parsing for bounded catalog queries from the assistant."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ABC_CATEGORY = re.compile(
    r"\b(?:abc[\s:-]*(?:categoria\s*)?|categor(?:ia|izacion)\s+(?:abc\s*)?|"
    r"calificacion\s+(?:abc\s*)?)([abc])\b"
)
_CATALOG_TERMS = re.compile(r"\b(?:catalogo|productos?|sku)\b")
_LIST_TERMS = re.compile(
    r"\b(?:lista|listame|listado|muestr\w*|dame|enumera\w*|cuales?|"
    r"que\s+productos?|siguiente\s+pagina|otra\s+pagina)\b"
)
_PAGE_NUMBER = re.compile(r"\b(?:pagina|page)\s+(\d{1,4})\b")
_NEXT_PAGE = re.compile(r"\b(?:siguiente|otra)\s+(?:pagina|page)\b")
_WINDOW_DAYS = re.compile(r"\b(?:ultimos?|ultimas?)\s+(\d{1,3})\s+dias\b")
_STATUS_PATTERNS = (
    (re.compile(r"\b(?:por\s+agotarse|quiebre)\b"), ("agotado", "quiebre")),
    (re.compile(r"\b(?:agotad\w*|sin\s+stock)\b"), ("agotado", "sin_stock")),
    (
        re.compile(r"\b(?:sobre\s*stock|sobreinventario|exceso\s+de\s+inventario)\b"),
        ("sobrestock",),
    ),
    (re.compile(r"\bdormid\w*\b"), ("dormido",)),
    (re.compile(r"\bsaludabl\w*\b"), ("saludable",)),
    (re.compile(r"\bsin\s+movimiento\b"), ("sin_movimiento",)),
    (re.compile(r"\bservicios?\b"), ("servicio",)),
)


@dataclass(frozen=True, slots=True)
class CatalogListRequest:
    abc: str
    window_days: int = 180
    page: int = 1
    page_size: int = 50
    estado: str | None = None

    def tool_arguments(self) -> dict[str, str | int | None]:
        arguments: dict[str, str | int | None] = {
            "abc": self.abc,
            "window_days": self.window_days,
            "page": self.page,
            "page_size": self.page_size,
        }
        if self.estado:
            arguments["estado"] = self.estado
        return arguments


def _normalize(message: str) -> str:
    return unicodedata.normalize("NFKD", message).encode("ascii", "ignore").decode("ascii").lower()


def parse_catalog_list_request(
    message: str,
    *,
    inherited_abc: str | None = None,
    inherited_page: int | None = None,
    inherited_estado: str | None = None,
    default_window_days: int = 180,
) -> CatalogListRequest | None:
    """Recognize explicit ABC list requests and immediate page follow-ups."""
    text = _normalize(message)
    category_match = _ABC_CATEGORY.search(text)
    page_match = _PAGE_NUMBER.search(text)
    next_page = _NEXT_PAGE.search(text) is not None

    if category_match:
        if not _CATALOG_TERMS.search(text) and not _LIST_TERMS.search(text):
            return None
        abc = category_match.group(1).upper()
        page = int(page_match.group(1)) if page_match else 1
    elif inherited_abc and (next_page or page_match):
        abc = inherited_abc.upper()
        page = int(page_match.group(1)) if page_match else (inherited_page or 1) + 1
    else:
        return None

    window_match = _WINDOW_DAYS.search(text)
    window_days = int(window_match.group(1)) if window_match else default_window_days
    if not 30 <= window_days <= 720 or not 1 <= page <= 1000:
        return None
    requested_states: list[str] = []
    for pattern, states in _STATUS_PATTERNS:
        if pattern.search(text):
            requested_states.extend(state for state in states if state not in requested_states)
    estado = ",".join(requested_states) or inherited_estado
    return CatalogListRequest(abc=abc, window_days=window_days, page=page, estado=estado)
