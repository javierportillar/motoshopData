"""Safe intent and period planning for purchase invoice queries."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}
MONTH_PATTERN = re.compile(r"\b(?:" + "|".join(MONTHS) + r")\b")
RANKING_PATTERN = re.compile(
    r"\b(?:top|ranking|(?:compras?|facturas?)\s+(?:mas\s+)?(?:grandes?|mayores?)|"
    r"mayores?\s+(?:compras?|facturas?)|(?:compras?|facturas?)\s+de\s+mayor\s+(?:monto|valor))\b"
)
AUDIT_TERMS = re.compile(
    r"\b(?:analiz\w*|audit\w*|rotacion|stock|demanda|ventas?|movimiento|"
    r"necesari\w*|comportamiento|sobrecompr\w*)\b"
)
LIST_TERMS = re.compile(
    r"\b(?:realizad\w*|hech\w*|registrad\w*|listado|listame|desglos\w*)\b"
    r"|\bcuales?\b.*\b(?:compras?|facturas?)\b"
    r"|\b(?:compras?|facturas?)\s+(?:del|de)\s+(?:mes|este\s+mes)\b"
)
SUMMARY_TERMS = re.compile(r"\b(?:tiene|hay|hubo)\s+compras?\b")
LIST_FOLLOWUP = re.compile(
    r"\b(?:detall\w*|desglos\w*|proveedor|total|esas\s+compras|esas\s+facturas|"
    r"siguientes|otra\s+pagina|pagina\s+\d+)\b"
)
RANKING_FOLLOWUP = re.compile(
    r"\b(?:las\s+del\s+mes|del\s+mes|te\s+estoy\s+pidiendo|quise\s+decir)\b"
)
SINGLE_INVOICE = re.compile(
    r"\b(?:factura|documento|comprobante|doc)\s*(?:n(?:ro|um(?:ero)?)\.?\s*)?\d+\b"
)
SUPPLIER_STOP_WORDS = (
    "el|la|los|las|de|del|en|durante|este|mes|año|y|por|segun|total|factura|facturas|"
    "compra|compras|mi|mis|su|sus|siguiente|proxima|proximo|una|un"
)
SUPPLIER_PATTERNS = (
    re.compile(rf"\b(?:hacia|para)\s+(.+?)(?=\s+(?:{SUPPLIER_STOP_WORDS})\b|[,;.!?]|$)"),
    re.compile(rf"\bproveedor(?:a)?\s*[:=]?\s+(.+?)(?=\s+(?:{SUPPLIER_STOP_WORDS})\b|[,;.!?]|$)"),
)
COUNT_WORDS = {
    "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


@dataclass(frozen=True, slots=True)
class PurchasePeriod:
    month: str
    date_from: str
    date_to: str
    label: str


@dataclass(frozen=True, slots=True)
class PurchaseQueryRequest:
    periods: tuple[PurchasePeriod, ...]
    view: str
    limit: int
    page: int = 1
    supplier_query: str | None = None
    clarification: str | None = None
    limit_capped: bool = False

    def tool_arguments(self) -> dict:
        arguments = {
            "periods": [
                {"date_from": period.date_from, "date_to": period.date_to}
                for period in self.periods
            ],
            "view": self.view,
            "limit": self.limit,
            "page": self.page,
        }
        if self.supplier_query:
            arguments["supplier_query"] = self.supplier_query
        if self.limit_capped:
            arguments["limit_capped"] = True
        return arguments


def normalize_query_text(message: str) -> str:
    return unicodedata.normalize("NFKD", message).encode("ascii", "ignore").decode("ascii").lower()


def parse_cutoff(value: date | str | None) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _month_is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 16):start]
    return bool(re.search(r"\bno\s+(?:(?:el|de)\s+)?$", prefix))


def _requested_months(text: str, cutoff: date | None) -> list[int]:
    mentions: list[tuple[int, int]] = [
        (match.start(), MONTHS[match.group(0)])
        for match in MONTH_PATTERN.finditer(text)
        if not _month_is_negated(text, match.start())
    ]
    if cutoff:
        current_month = re.compile(r"\beste\s+mes\b|\bmes\s+actual\b|\bmes\s+en\s+curso\b")
        mentions.extend((match.start(), cutoff.month) for match in current_month.finditer(text))
    mentions.sort()
    return list(dict.fromkeys(month for _, month in mentions))


def resolve_calendar_months(
    message: str,
    cutoff_value: date | str | None,
    *,
    domain_label: str,
) -> tuple[tuple[PurchasePeriod, ...], str | None]:
    text = normalize_query_text(message)
    cutoff = parse_cutoff(cutoff_value)
    months = _requested_months(text, cutoff)
    years = {int(value) for value in re.findall(r"\b(20\d{2})\b", text)}
    if len(years) > 1:
        return (), "Para comparar los períodos, indicame un solo año."
    if not months:
        return (), f"¿De qué mes y año querés consultar {domain_label}?"
    if cutoff is None and not years:
        return (), f"No tengo un corte de {domain_label} para inferir el año; indicame el año."
    year = next(iter(years)) if years else cutoff.year  # type: ignore[union-attr]
    if not years and cutoff and any(month > cutoff.month for month in months):
        return (), (
            f"El corte de {domain_label} llega a {cutoff.isoformat()}; "
            "indicame el año solicitado."
        )
    periods = []
    for month in months:
        start = date(year, month, 1)
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        end = next_month - timedelta(days=1)
        periods.append(PurchasePeriod(
            start.strftime("%Y-%m"), start.isoformat(), end.isoformat(),
            f"{MONTH_NAMES[month]} {year}",
        ))
    return tuple(periods), None


def _supplier_filter(text: str) -> str | None:
    for pattern in SUPPLIER_PATTERNS:
        match = pattern.search(text)
        if match:
            supplier = " ".join(match.group(1).split()).strip(" :-")
            if supplier and supplier not in SUPPLIER_STOP_WORDS.split("|"):
                return supplier[:100]
    return None


def _purchase_limit(text: str, default: int) -> tuple[int, bool, bool]:
    count_words = {**COUNT_WORDS}
    number_pattern = r"(\d+|" + "|".join(count_words) + r")"
    match = re.search(r"\b" + number_pattern + r"\s+(?:compras?|facturas?)\b", text)
    if match is None:
        match = re.search(r"\btop\s+" + number_pattern + r"\b", text)
    if match is None:
        return default, False, False
    raw = match.group(1)
    requested = int(raw) if raw.isdigit() else count_words[raw]
    return max(1, min(requested, 20)), requested > 20, True


def parse_purchase_ranking_request(
    message: str,
    *,
    purchase_cutoff: date | str | None,
    inherited_limit: int | None = None,
    inherited_supplier_query: str | None = None,
    inherited_limit_capped: bool = False,
) -> PurchaseQueryRequest | None:
    text = normalize_query_text(message)
    explicit_ranking = RANKING_PATTERN.search(text) is not None
    correction = inherited_limit is not None and RANKING_FOLLOWUP.search(text) is not None
    if (not explicit_ranking and not correction) or AUDIT_TERMS.search(text):
        return None
    periods, clarification = resolve_calendar_months(
        message, purchase_cutoff, domain_label="el ranking de compras"
    )
    limit, limit_capped, explicit_limit = _purchase_limit(text, inherited_limit or 3)
    if not explicit_limit and inherited_limit is not None:
        limit_capped = inherited_limit_capped
    return PurchaseQueryRequest(
        periods=periods,
        view="top",
        limit=limit,
        supplier_query=_supplier_filter(text) or inherited_supplier_query,
        clarification=clarification,
        limit_capped=limit_capped,
    )


def parse_purchase_period_request(
    message: str,
    *,
    purchase_cutoff: date | str | None,
    inherited_periods: tuple[PurchasePeriod, ...] | None = None,
    inherited_supplier_query: str | None = None,
) -> PurchaseQueryRequest | None:
    text = normalize_query_text(message)
    if AUDIT_TERMS.search(text) or SINGLE_INVOICE.search(text):
        return None
    has_purchase = bool(re.search(r"\b(?:compras?|facturas?)\b", text))
    is_summary = has_purchase and SUMMARY_TERMS.search(text) is not None
    has_month = bool(_requested_months(text, parse_cutoff(purchase_cutoff)))
    explicit_list = has_purchase and (LIST_TERMS.search(text) is not None or has_month)
    inherit_details = (
        bool(inherited_periods)
        and LIST_FOLLOWUP.search(text) is not None
        and not has_month
    )
    if not is_summary and not explicit_list and not inherit_details:
        return None
    clarification = None
    if inherit_details:
        periods = inherited_periods or ()
        view = "list"
    else:
        periods, clarification = resolve_calendar_months(
            message, purchase_cutoff, domain_label="las compras"
        )
        view = "summary" if is_summary else "list"
    return PurchaseQueryRequest(
        periods=periods,
        view=view,
        limit=50,
        supplier_query=_supplier_filter(text) or inherited_supplier_query,
        clarification=clarification,
    )
