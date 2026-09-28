"""Intent parsing for exact-period sales product rankings."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from motoshop_api.llm.purchase_queries import PurchasePeriod, parse_cutoff, resolve_calendar_months

_RANKING_TERMS = re.compile(r"\b(?:mas\s+vend\w*|vend\w*\s+mas|top|ranking)\b")
_PRODUCT_TERMS = re.compile(r"\b(?:product\w*|sku)\b")
_REVENUE_TERMS = re.compile(
    r"\b(?:por\s+valor|valor\s+vendido|facturaci\w*|revenue|ingresos?)\b"
)
_FOLLOWUP_DATE_TERMS = re.compile(
    r"\b(?:hoy|ayer|dia\s+\d{1,2}|fecha\s+20\d{2}-\d{2}-\d{2}|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|"
    r"octubre|noviembre|diciembre)\b"
)
_FOLLOWUP_RANKING_ELLIPSIS = re.compile(
    r"^(?:y\s+)?(?:(?:del?|de|en|para|el|la)\s+)?"
    r"(?:20\d{2}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2}|"
    r"(?:dia\s+(?:de\s+)?)?(?:hoy|ayer|dia\s+\d{1,2}|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|"
    r"octubre|noviembre|diciembre)|"
    r"\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre))"
    r"(?:\s+(?:de\s+)?20\d{2})?$"
)
_ISO_DATE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)")
_DATE_TOKEN = r"(?:20\d{2}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2})"
_DATE_RANGE = re.compile(
    rf"\b(?:desde|entre|del|de)\s+({_DATE_TOKEN})\s+(?:hasta|y|al|a)\s+({_DATE_TOKEN})\b"
)
_MONTH_DAY = re.compile(
    r"\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)(?:\s+de\s+(20\d{2}))?\b"
)
_MONTH_NUMBERS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


@dataclass(frozen=True, slots=True)
class SalesProductRankingRequest:
    periods: tuple[PurchasePeriod, ...]
    metric: str
    limit: int
    clarification: str | None = None

    def tool_arguments(self) -> dict:
        return {
            "periods": [
                {"date_from": period.date_from, "date_to": period.date_to, "label": period.label}
                for period in self.periods
            ],
            "metric": self.metric,
            "limit": self.limit,
        }


def _normalize(message: str) -> str:
    return unicodedata.normalize("NFKD", message).encode("ascii", "ignore").decode("ascii").lower()


def _day_period(value: date, label: str | None = None) -> PurchasePeriod:
    return PurchasePeriod(
        value.strftime("%Y-%m"), value.isoformat(), value.isoformat(),
        label or value.strftime("%d/%m/%Y"),
    )


def _exact_periods(text: str, cutoff: date | None) -> tuple[PurchasePeriod, ...] | None:
    date_range = _DATE_RANGE.search(text)
    if date_range:
        def parse_date_token(token: str) -> date:
            if "-" in token:
                return date.fromisoformat(token)
            day, month, year = map(int, re.split(r"[/-]", token))
            return date(year, month, day)

        start, end = (parse_date_token(token) for token in date_range.groups())
        if start > end:
            raise ValueError("invalid_range")
        label = f"{start.isoformat()} a {end.isoformat()}"
        return (PurchasePeriod(start.strftime("%Y-%m"), start.isoformat(), end.isoformat(), label),)

    values: list[date] = []
    for match in _ISO_DATE.finditer(text):
        try:
            values.append(date.fromisoformat(match.group(1)))
        except ValueError:
            continue
    for match in _NUMERIC_DATE.finditer(text):
        try:
            day, month, year = map(int, match.groups())
            values.append(date(year, month, day))
        except ValueError:
            continue
    if values:
        return tuple(dict.fromkeys(_day_period(value) for value in values))

    month_day = _MONTH_DAY.search(text)
    if month_day:
        day_number, month_name, year_text = month_day.groups()
        years = {int(value) for value in re.findall(r"\b(20\d{2})\b", text)}
        if len(years) > 1:
            raise ValueError("multiple_years")
        year = int(year_text) if year_text else next(iter(years), cutoff.year if cutoff else None)
        if year is None:
            raise ValueError("missing_year")
        return (_day_period(date(year, _MONTH_NUMBERS[month_name], int(day_number))),)

    relative_days: list[tuple[int, PurchasePeriod]] = []
    if cutoff:
        for match in re.finditer(r"\b(?:hoy|ayer)\b", text):
            selected = cutoff if match.group(0) == "hoy" else cutoff - timedelta(days=1)
            label = "último día con ventas" if match.group(0) == "hoy" else "día anterior al corte"
            relative_days.append((match.start(), _day_period(selected, label)))
    if relative_days:
        return tuple(period for _, period in sorted(relative_days))

    day_only = re.search(r"\b(?:dia|fecha)\s+(\d{1,2})\b", text)
    if day_only:
        if cutoff is None:
            raise ValueError("missing_cutoff")
        years = {int(value) for value in re.findall(r"\b(20\d{2})\b", text)}
        if len(years) > 1:
            raise ValueError("multiple_years")
        year = next(iter(years), cutoff.year)
        return (_day_period(date(year, cutoff.month, int(day_only.group(1)))),)
    return None


def parse_sales_product_ranking_request(
    message: str,
    *,
    sales_cutoff: date | str | None,
    inherited_limit: int | None = None,
    inherited_metric: str | None = None,
) -> SalesProductRankingRequest | None:
    """Parse a product ranking into exact dates or independently ranked months."""
    text = _normalize(message)
    cutoff = parse_cutoff(sales_cutoff)
    intent = (
        _RANKING_TERMS.search(text) is not None
        and (_PRODUCT_TERMS.search(text) is not None or "mas vendid" in text)
        and "compr" not in text
    )
    has_followup_date = (
        _FOLLOWUP_DATE_TERMS.search(text) is not None
        or _ISO_DATE.search(text) is not None
        or _NUMERIC_DATE.search(text) is not None
    )
    followup = (
        inherited_limit is not None
        and has_followup_date
        and (
            _RANKING_TERMS.search(text) is not None
            or _FOLLOWUP_RANKING_ELLIPSIS.fullmatch(text.strip(" ?!.")) is not None
        )
    )
    if not intent and not followup:
        return None

    metric = "revenue" if _REVENUE_TERMS.search(text) else inherited_metric or "units"
    count = re.search(r"\btop\s+(\d{1,2})\b", text)
    if count is None:
        count = re.search(r"\b(\d{1,2})\s+(?:product\w*|sku\w*)\b", text)
    limit = max(1, min(int(count.group(1)), 20)) if count else inherited_limit or 1
    try:
        periods = _exact_periods(text, cutoff)
    except ValueError as exc:
        clarification = (
            "Indicame un solo año para las fechas solicitadas."
            if str(exc) == "multiple_years"
            else "El rango de fechas está invertido; indicame un inicio y un fin válidos."
            if str(exc) == "invalid_range"
            else "No tengo corte de ventas para resolver el día relativo; indicame una fecha."
        )
        return SalesProductRankingRequest((), metric, limit, clarification)
    if periods is None:
        periods, clarification = resolve_calendar_months(
            message, cutoff, domain_label="ventas"
        )
        if clarification:
            return SalesProductRankingRequest((), metric, limit, clarification)
    if len(periods) > 6:
        return SalesProductRankingRequest(
            (), metric, limit, "Puedo comparar hasta seis períodos por consulta."
        )
    return SalesProductRankingRequest(periods, metric, limit)
