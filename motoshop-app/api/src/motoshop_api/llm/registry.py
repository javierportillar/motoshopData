"""Allowlisted assistant capabilities and server-side entity route policy."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

from motoshop_api.auth.tenant_dep import TenantContext
from motoshop_api.llm.contracts import EntityRef

_CAPABILITIES = {
    domain: "supabase" if domain in {"expenses", "expiry"} else "duckdb"
    for domain in (
        "sales",
        "purchases",
        "inventory",
        "abc",
        "dormant_products",
        "alerts",
        "forecasts",
        "analyses",
        "expenses",
        "expiry",
    )
}
_ROUTES = {
    "product": ("inventory", "/dashboards/productos/{entity_id}"),
    "alert": ("alerts", "/inventario/alertas/{entity_id}"),
    "purchase_document": (
        "purchases",
        "/dashboards/compras/dia/{business_date}/documento/{num_documento}"
        "?cod_clase={cod_clase}",
    ),
    "supplier": ("purchases", "/dashboards/compras/proveedores/{entity_id}"),
}
_ENTITY_SOURCES = {
    "alert": ("gold_alertas_quiebre", "sku"),
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:/-]+(?:\s+[A-Za-z0-9._:/-]+)*$")
_SAFE_SUPPLIER_NIT = re.compile(
    r"^(?:\d{6,14}|\d{1,3}(?:\.\d{3}){2,4})(?:-\d{1,2})?$"
)
_PRODUCT_CODE_TOKEN = re.compile(
    r"(?<![\w])([A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,118}[A-Za-z0-9])?)(?![\w])"
)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RAW_URL = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
_MAX_TEXT_PRODUCT_CANDIDATES = 50
_MAX_PURCHASE_HISTORY_CANDIDATES = 50
PURCHASE_REFERENCE_TOOLS = frozenset({
    "get_ultima_compra",
    "get_compras_recientes",
    "get_top_compras_periodos",
    "get_compras_periodo",
    "buscar_compras_por_proveedor",
    "get_detalle_compra",
    "get_analisis_modulo",
    "get_productos_para_reponer",
})
_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_PURCHASE_DOCUMENT_MENTION = re.compile(
    r"\b(?:factura|documento|comprobante|doc)\.?\s*(?:de\s+compra\s*)?"
    r"(?:n(?:ro|[úu]m(?:ero)?)?\.?\s*)?[:#-]?\s*"
    r"([A-Za-z0-9](?:[A-Za-z0-9._/-]{0,58}[A-Za-z0-9])?)(?![\w/-])",
    re.IGNORECASE,
)
_SUPPLIER_NIT_MENTION = re.compile(
    r"\b(?:NIT|RUT)\s*(?:[:#-]\s*)?([A-Za-z0-9][A-Za-z0-9.-]{1,28}[A-Za-z0-9]|[A-Za-z0-9]{3,30})(?![\w-])",
    re.IGNORECASE,
)
_PURCHASE_CLASS_MENTION = re.compile(
    r"\b(?:cod[_\s]*clase|clase)\s*(?:[:=]\s*|(?!de\b|del\b)\s+)"
    r"([A-Za-z0-9](?:[A-Za-z0-9._/-]{0,38}[A-Za-z0-9])?)",
    re.IGNORECASE,
)


def visible_markdown_text(text: str) -> str:
    """Remove link destinations and bare URLs before matching product mentions."""
    return _RAW_URL.sub(" ", _MARKDOWN_LINK.sub(r"\1", text))


def _business_dates_in_text(text: str) -> set[str]:
    """Parse only unambiguous ISO, numeric day-first, and Spanish long dates."""
    visible = visible_markdown_text(text)
    dates: set[str] = set()
    patterns = (
        (re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)"), "iso"),
        (re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)"), "numeric"),
        (
            re.compile(
                r"(?<!\d)(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
                r"septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(20\d{2})(?!\d)",
                re.IGNORECASE,
            ),
            "spanish",
        ),
    )
    for pattern, kind in patterns:
        for match in pattern.finditer(visible):
            try:
                if kind == "iso":
                    year, month, day = map(int, match.groups())
                elif kind == "numeric":
                    day, month, year = map(int, match.groups())
                else:
                    day_text, month_text, year_text = match.groups()
                    day, year = int(day_text), int(year_text)
                    month = _SPANISH_MONTHS[month_text.casefold()]
                dates.add(date(year, month, day).isoformat())
            except (KeyError, ValueError):
                continue
    return dates


def _purchase_ref_from_identity(business_date: str, class_code: str, document_number: str) -> EntityRef:
    entity_id = f"{business_date}|{class_code}|{document_number}"
    business_date, class_code, document_number = _parse_purchase_id(entity_id)
    return EntityRef(
        entity_type="purchase_document",
        entity_id=entity_id,
        label=document_number,
        domain="purchases",
        href=(
            f"/dashboards/compras/dia/{quote(business_date, safe='')}"
            f"/documento/{quote(document_number, safe='')}"
            f"?cod_clase={quote(class_code, safe='')}"
        ),
    )


class GovernedRegistry:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def names(self) -> set[str]:
        return {name for name in _CAPABILITIES if self.context.allows(name)}

    def get(self, domain: str) -> str | None:
        return _CAPABILITIES.get(domain) if domain in self.names() else None

    def require(self, domain: str) -> str:
        capability = self.get(domain)
        if capability is None:
            raise PermissionError("assistant_capability_denied")
        return capability


def _resolve_product_ref_batch(
    context: TenantContext, entity_ids: list[str]
) -> list[EntityRef]:
    """Resolve one bounded batch of current tenant catalog products."""
    if not context.allows("inventory") or not entity_ids:
        return []
    codes = list(dict.fromkeys(
        code.strip() for code in entity_ids
        if isinstance(code, str) and code.strip() and _SAFE_ID.fullmatch(code.strip())
        and "://" not in code
    ))[:50]
    if not codes:
        return []

    from motoshop_api.metrics.repo_duckdb import _make_db_path, get_shared_connection

    placeholders = ",".join("?" for _ in codes)
    parameters = [code.upper() for code in codes]
    masvital = context.tenant_id.casefold() == "masvital"
    snapshot_filter = (
        "AND snapshot_date = (SELECT MAX(snapshot_date) FROM silver_dim_producto)"
        if masvital else ""
    )
    catalog_order = (
        "COALESCE(existencia, 0) DESC, "
        "COALESCE(NULLIF(TRIM(nombre_producto), ''), cod_producto) ASC"
        if masvital else "COALESCE(NULLIF(TRIM(nombre_producto), ''), cod_producto) ASC"
    )
    catalog_sql = f"""
        SELECT TRIM(cod_producto, ' \r\n\t') AS cod_producto,
               COALESCE(NULLIF(TRIM(nombre_producto), ''), TRIM(cod_producto, ' \r\n\t')) AS label
        FROM (
            SELECT cod_producto, nombre_producto,
                   ROW_NUMBER() OVER (
                       PARTITION BY TRIM(cod_producto, ' \r\n\t') ORDER BY {catalog_order}
                   ) AS product_row
            FROM silver_dim_producto
            WHERE UPPER(TRIM(cod_producto, ' \r\n\t')) IN ({placeholders}) {snapshot_filter}
        ) AS ranked
        WHERE product_row = 1
        ORDER BY UPPER(cod_producto)
    """
    connection = None
    cursor = None
    try:
        connection = get_shared_connection(_make_db_path(context.tenant_id))
        is_duckdb = type(connection).__name__ == "DuckDBPyConnection"
        if is_duckdb:
            cursor = connection.cursor()
            products = cursor.execute(catalog_sql, parameters).fetchall()
        else:
            result = connection.execute(catalog_sql, parameters)
            products = result.fetchall() if hasattr(result, "fetchall") else result
    except Exception:
        return []
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            cursor.close()
    if not products:
        return []

    labels = list(dict.fromkeys(str(row[1]).strip().casefold() for row in products))
    label_placeholders = ",".join("?" for _ in labels)
    label_sql = f"""
        SELECT LOWER(TRIM(COALESCE(NULLIF(TRIM(nombre_producto), ''), cod_producto))) AS label,
               COUNT(DISTINCT cod_producto) AS sku_count
        FROM silver_dim_producto
        WHERE LOWER(TRIM(COALESCE(NULLIF(TRIM(nombre_producto), ''), cod_producto)))
              IN ({label_placeholders}) {snapshot_filter}
        GROUP BY 1
    """
    cursor = None
    try:
        assert connection is not None
        if is_duckdb:
            cursor = connection.cursor()
            rows = cursor.execute(label_sql, labels).fetchall()
        else:
            result = connection.execute(label_sql, labels)
            rows = result.fetchall() if hasattr(result, "fetchall") else result
        label_counts = {str(row[0]).casefold(): int(row[1]) for row in rows}
    except Exception:
        # If uniqueness cannot be verified, SKU links remain safe but names
        # must not be treated as unambiguous by the UI.
        label_counts = {}
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            cursor.close()

    refs = []
    for entity_id, raw_label in products:
        label = str(raw_label).strip()
        clean_entity_id = str(entity_id).strip()
        refs.append(EntityRef(
            entity_type="product",
            entity_id=clean_entity_id,
            label=label,
            domain="inventory",
            href=f"/dashboards/productos/{quote(clean_entity_id, safe='')}",
            label_is_unique=label_counts.get(label.casefold(), 0) == 1,
        ))
    return refs


def is_valid_supplier_nit(value: str) -> bool:
    return isinstance(value, str) and bool(_SAFE_SUPPLIER_NIT.fullmatch(value))


def resolve_product_refs(
    context: TenantContext, entity_ids: list[str], *, batch_size: int = 50
) -> list[EntityRef]:
    """Resolve many product entities without one catalog lookup per SKU."""
    batch_size = max(1, min(int(batch_size), 50))
    codes = list(dict.fromkeys(
        str(code).strip() for code in entity_ids
        if isinstance(code, str) and code.strip()
    ))
    refs_by_id: dict[str, EntityRef] = {}
    for offset in range(0, len(codes), batch_size):
        for ref in _resolve_product_ref_batch(context, codes[offset:offset + batch_size]):
            refs_by_id.setdefault(ref.entity_id.casefold(), ref)
    return list(refs_by_id.values())


def _purchase_connection(context: TenantContext):
    from motoshop_api.metrics.repo_duckdb import _make_db_path, get_shared_connection

    return get_shared_connection(_make_db_path(context.tenant_id))


def _purchase_cursor_rows(context: TenantContext, sql: str, parameters: list) -> list[tuple]:
    cursor = None
    try:
        cursor = _purchase_connection(context).cursor()
        return cursor.execute(sql, parameters).fetchall()
    except Exception as exc:
        raise LookupError("entity_not_found") from exc
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            cursor.close()


def _parse_purchase_id(entity_id: str) -> tuple[str, str, str]:
    if not isinstance(entity_id, str) or entity_id.count("|") != 2:
        raise ValueError("invalid_entity_reference")
    business_date, class_code, document_number = entity_id.split("|")
    try:
        parsed_date = date.fromisoformat(business_date)
    except ValueError as exc:
        raise ValueError("invalid_entity_reference") from exc
    if (
        parsed_date.isoformat() != business_date
        or not class_code
        or len(class_code) > 40
        or not document_number
        or len(document_number) > 120
        or any(part in {".", ".."} for part in document_number.split("/"))
        or any(character.isspace() for character in class_code)
        or any(character.isspace() for character in document_number)
    ):
        raise ValueError("invalid_entity_reference")
    return business_date, class_code, document_number


def resolve_purchase_document_ref(context: TenantContext, entity_id: str) -> EntityRef:
    """Resolve an exact valid purchase identity in the active tenant."""
    if not context.allows("purchases"):
        raise PermissionError("entity_destination_denied")
    _parse_purchase_id(entity_id)
    for ref in resolve_purchase_document_refs(context, [entity_id]):
        if ref.entity_id == entity_id:
            return ref
    raise LookupError("entity_not_found")


def resolve_purchase_document_refs(
    context: TenantContext, entity_ids: list[str]
) -> list[EntityRef]:
    """Resolve up to 50 exact purchase identities in one tenant-scoped query."""
    if not context.allows("purchases") or not entity_ids:
        return []
    identities: list[tuple[str, str, str]] = []
    for entity_id in entity_ids:
        try:
            identity = _parse_purchase_id(entity_id)
        except ValueError:
            continue
        if identity not in identities:
            identities.append(identity)
        if len(identities) >= 50:
            break
    if not identities:
        return []
    clauses = [
        "(CAST(business_date AS VARCHAR) = ? AND cod_clase = ? AND num_documento = ?)"
        for _ in identities
    ]
    parameters = [value for identity in identities for value in identity]
    try:
        rows = _purchase_cursor_rows(
            context,
            f"""
            SELECT CAST(business_date AS VARCHAR), cod_clase, num_documento, COUNT(*) AS exact_rows
            FROM silver_fact_compras
            WHERE ({" OR ".join(clauses)})
              AND UPPER(TRIM(COALESCE(estado_documento, ''))) != 'A'
            GROUP BY 1, 2, 3
            """,
            parameters,
        )
    except LookupError:
        return []
    refs = []
    for raw_date, raw_class, raw_number, exact_rows in rows:
        if int(exact_rows) != 1:
            continue
        refs.append(_purchase_ref_from_identity(str(raw_date), str(raw_class), str(raw_number)))
    return refs


def resolve_supplier_refs(context: TenantContext, nits: list[str]) -> list[EntityRef]:
    """Resolve canonical tenant supplier names and name uniqueness in one bounded query."""
    if not context.allows("purchases") or not nits:
        return []
    normalized_nits = list(dict.fromkeys(
        nit.strip() for nit in nits
        if isinstance(nit, str) and is_valid_supplier_nit(nit.strip())
    ))[:50]
    if not normalized_nits:
        return []
    placeholders = ",".join("?" for _ in normalized_nits)
    try:
        rows = _purchase_cursor_rows(
            context,
            f"""
            SELECT TRIM(nit_proveedor) AS nit,
                   COALESCE(
                       ARG_MAX(NULLIF(TRIM(nombre_proveedor), ''), business_date),
                       TRIM(nit_proveedor)
                   ) AS nombre
            FROM silver_fact_compras
            WHERE TRIM(nit_proveedor) IN ({placeholders})
            GROUP BY TRIM(nit_proveedor)
            ORDER BY nit
            """,
            normalized_nits,
        )
    except LookupError:
        return []
    if not rows:
        return []

    labels = list(dict.fromkeys(str(row[1]).strip().casefold() for row in rows))
    label_placeholders = ",".join("?" for _ in labels)
    try:
        name_counts = {
            str(row[0]).casefold(): int(row[1])
            for row in _purchase_cursor_rows(
                context,
                f"""
                SELECT LOWER(TRIM(COALESCE(
                           NULLIF(TRIM(nombre_proveedor), ''), TRIM(nit_proveedor)
                       ))) AS nombre,
                       COUNT(DISTINCT TRIM(nit_proveedor)) AS nit_count
                FROM silver_fact_compras
                WHERE nit_proveedor IS NOT NULL AND TRIM(nit_proveedor) != ''
                  AND LOWER(TRIM(COALESCE(
                           NULLIF(TRIM(nombre_proveedor), ''), TRIM(nit_proveedor)
                       ))) IN ({label_placeholders})
                GROUP BY 1
                """,
                labels,
            )
        }
    except LookupError:
        name_counts = {}
    return [
        EntityRef(
            entity_type="supplier",
            entity_id=str(row[0]),
            label=str(row[1]),
            label_is_unique=name_counts.get(str(row[1]).strip().casefold(), 0) == 1,
            domain="purchases",
            href=f"/dashboards/compras/proveedores/{quote(str(row[0]), safe='')}",
        )
        for row in rows
    ]


def purchase_document_ref_mentioned(
    context: TenantContext,
    text: str,
    entity_id: str,
    *,
    candidate_ids: list[str] | None = None,
) -> bool:
    """Require an explicit document label and disambiguate reused numbers visibly."""
    if not text or not context.allows("purchases"):
        return False
    try:
        business_date, class_code, document_number = _parse_purchase_id(entity_id)
    except ValueError:
        return False
    text = visible_markdown_text(text)
    number_pattern = rf"(?<![\w]){re.escape(document_number)}(?![\w])"
    document_number_mention = re.compile(
        rf"\b(?:factura|documento|comprobante|doc)\.?"
        rf"\s*(?:de\s+compra\s+)?"
        rf"(?:(?:n(?:ro|[úu]m(?:ero)?)?|n[º°])\.?\s*|#\s*)?[:#-]?\s*"
        rf"{number_pattern}",
        re.IGNORECASE,
    )
    mention_contexts = [
        line for line in text.splitlines()
        if document_number_mention.search(line)
    ]
    mention_contexts.extend(_purchase_document_table_contexts(text, document_number))
    mention_contexts = list(dict.fromkeys(mention_contexts))
    if not mention_contexts:
        return False

    identities: list[tuple[str, str, str]] = []
    if candidate_ids is not None:
        for candidate_id in candidate_ids:
            try:
                identity = _parse_purchase_id(candidate_id)
            except ValueError:
                continue
            if identity[2] == document_number and identity not in identities:
                identities.append(identity)
    else:
        try:
            rows = _purchase_cursor_rows(
                context,
                """
                SELECT DISTINCT CAST(business_date AS VARCHAR), cod_clase, num_documento
                FROM silver_fact_compras
                WHERE num_documento = ?
                  AND UPPER(TRIM(COALESCE(estado_documento, ''))) != 'A'
                ORDER BY CAST(business_date AS VARCHAR) DESC, cod_clase
                """,
                [document_number],
            )
        except LookupError:
            return False
        identities = [(str(row[0]), str(row[1]), str(row[2])) for row in rows]
    if len(identities) == 1:
        return identities[0] == (business_date, class_code, document_number)
    for mention_context in mention_contexts:
        visible_dates = _business_dates_in_text(mention_context)
        visible_classes = {
            match.group(1).casefold()
            for match in _PURCHASE_CLASS_MENTION.finditer(mention_context)
        }
        if not visible_dates and not visible_classes:
            continue
        matches = [
            identity
            for identity in identities
            if (not visible_dates or identity[0] in visible_dates)
            and (not visible_classes or identity[1].casefold() in visible_classes)
        ]
        if len(matches) == 1 and matches[0] == (business_date, class_code, document_number):
            return True
    return False


def _purchase_document_table_contexts(text: str, document_number: str) -> list[str]:
    """Return row-local evidence only when the number occupies a document column."""
    lines = text.splitlines()
    contexts: list[str] = []
    index = 0
    document_header = re.compile(r"\b(?:factura|documento|comprobante|doc)\b", re.IGNORECASE)
    while index + 2 < len(lines):
        header_line = lines[index].strip()
        separator_line = lines[index + 1].strip()
        if (
            not header_line.startswith("|")
            or not separator_line.startswith("|")
            or not re.fullmatch(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?", separator_line)
        ):
            index += 1
            continue
        headers = [cell.strip() for cell in header_line.strip("|").split("|")]
        document_columns = [
            column for column, header in enumerate(headers)
            if document_header.search(header)
        ]
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            if any(
                column < len(cells)
                and cells[column].strip("`*_ ") == document_number
                for column in document_columns
            ):
                contexts.append(" | ".join(
                    f"{header}: {cells[column]}"
                    for column, header in enumerate(headers)
                    if column < len(cells)
                ))
            index += 1
    return contexts


def resolve_purchase_refs_in_messages(
    context: TenantContext, texts: list[str], *, limit: int = 50
) -> dict[int, list[EntityRef]]:
    """Backfill explicitly labelled purchase/NIT mentions with bounded tenant queries."""
    if not context.allows("purchases") or not texts:
        return {}
    candidate_limit = min(max(int(limit), 0), _MAX_PURCHASE_HISTORY_CANDIDATES)
    if candidate_limit == 0:
        return {}

    document_selectors: list[tuple[int, str, str | None, str | None]] = []
    supplier_nits_by_message: dict[int, set[str]] = {}
    document_numbers: list[str] = []
    supplier_nits: list[str] = []

    for message_index, raw_text in enumerate(texts):
        text = visible_markdown_text(str(raw_text or ""))
        dates = _business_dates_in_text(text)
        classes = {match.group(1) for match in _PURCHASE_CLASS_MENTION.finditer(text)}
        business_date = next(iter(dates)) if len(dates) == 1 else None
        class_code = next(iter(classes)) if len(classes) == 1 else None
        for match in _PURCHASE_DOCUMENT_MENTION.finditer(text):
            document_number = match.group(1).rstrip("./-")
            if not document_number:
                continue
            selector = (message_index, document_number, business_date, class_code)
            if selector not in document_selectors and len(document_selectors) < candidate_limit:
                document_selectors.append(selector)
                document_numbers.append(document_number)
        for match in _SUPPLIER_NIT_MENTION.finditer(text):
            nit = match.group(1).rstrip(".-")
            if not nit or len(supplier_nits) >= candidate_limit:
                continue
            supplier_nits_by_message.setdefault(message_index, set()).add(nit)
            if nit not in supplier_nits:
                supplier_nits.append(nit)

    refs_by_message: dict[int, list[EntityRef]] = {}
    supplier_refs = {ref.entity_id: ref for ref in resolve_supplier_refs(context, supplier_nits)}
    for message_index, nits in supplier_nits_by_message.items():
        for nit in nits:
            ref = supplier_refs.get(nit)
            if ref is not None:
                refs_by_message.setdefault(message_index, []).append(ref)

    unique_numbers = list(dict.fromkeys(document_numbers))
    if not unique_numbers:
        return refs_by_message
    placeholders = ",".join("?" for _ in unique_numbers)
    try:
        rows = _purchase_cursor_rows(
            context,
            f"""
            SELECT DISTINCT CAST(business_date AS VARCHAR), cod_clase, num_documento
            FROM silver_fact_compras
            WHERE num_documento IN ({placeholders})
              AND UPPER(TRIM(COALESCE(estado_documento, ''))) != 'A'
            ORDER BY CAST(business_date AS VARCHAR) DESC, cod_clase, num_documento
            LIMIT 5001
            """,
            unique_numbers,
        )
    except LookupError:
        return refs_by_message
    if len(rows) > 5000:
        return refs_by_message

    identities_by_number: dict[str, list[tuple[str, str, str]]] = {}
    for raw_date, raw_class, raw_number in rows:
        identity = (str(raw_date), str(raw_class), str(raw_number))
        identities_by_number.setdefault(identity[2], []).append(identity)

    for message_index, document_number, business_date, class_code in document_selectors:
        matches = [
            identity
            for identity in identities_by_number.get(document_number, [])
            if (business_date is None or identity[0] == business_date)
            and (class_code is None or identity[1].casefold() == class_code.casefold())
        ]
        if len(matches) != 1:
            continue
        refs_by_message.setdefault(message_index, []).append(
            _purchase_ref_from_identity(*matches[0])
        )

    for message_index, refs in refs_by_message.items():
        deduplicated = {
            (ref.entity_type, ref.entity_id, ref.domain): ref
            for ref in refs
        }
        refs_by_message[message_index] = list(deduplicated.values())
    return refs_by_message


def supplier_ref_mentioned(text: str, ref: EntityRef) -> bool:
    """A supplier links by an explicit NIT or by its unique canonical name."""
    if not text:
        return False
    text = visible_markdown_text(text)
    nit = re.escape(ref.entity_id)
    if re.search(rf"\b(?:NIT|RUT)\s*(?:[:#-]\s*)?{nit}(?![\w])", text, re.IGNORECASE):
        return True
    if re.search(r"\b(?:NIT|RUT)\b", text, re.IGNORECASE) and re.search(rf"\(\s*{nit}\s*\)", text):
        return True
    return bool(
        ref.label_is_unique
        and re.search(rf"(?<![\w]){re.escape(ref.label)}(?![\w])", text, re.IGNORECASE)
    )


def resolve_entity_ref(
    context: TenantContext,
    *,
    entity_type: str,
    entity_id: str,
    label: str,
    domain: str,
    route_key: str,
) -> EntityRef:
    """Resolve a route only when the entity exists in the tenant's source.

    The connection is always derived from the tenant context to prevent
    cross-tenant entity reference bypass via an externally supplied connection.
    """
    if not context.allows(domain):
        raise PermissionError("entity_destination_denied")
    if entity_type == "purchase_document":
        if domain != "purchases" or route_key != "purchase_document":
            raise ValueError("invalid_entity_reference")
        return resolve_purchase_document_ref(context, entity_id)
    if entity_type == "supplier":
        if domain != "purchases" or route_key != "supplier":
            raise ValueError("invalid_entity_reference")
        for ref in resolve_supplier_refs(context, [entity_id]):
            if ref.entity_id == entity_id:
                return ref
        raise LookupError("entity_not_found")
    route_domain, template = _ROUTES.get(route_key, ("", ""))
    if (
        route_domain != domain
        or entity_type not in {"product", *_ENTITY_SOURCES}
        or not _SAFE_ID.fullmatch(entity_id)
        or "://" in entity_id
    ):
        raise ValueError("invalid_entity_reference")

    if entity_type == "product":
        for ref in resolve_product_refs(context, [entity_id]):
            if ref.entity_id.casefold() == entity_id.casefold():
                return ref
        raise LookupError("entity_not_found")

    source = _ENTITY_SOURCES[entity_type]
    from motoshop_api.metrics.repo_duckdb import _make_db_path, get_shared_connection

    connection = get_shared_connection(_make_db_path(context.tenant_id))
    table, column = source
    cursor = None
    try:
        cursor = connection.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", [entity_id]
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError("entity_not_found")
    except LookupError:
        raise
    except Exception as exc:
        raise LookupError("entity_not_found") from exc
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            cursor.close()
    return EntityRef(
        entity_type=entity_type,
        entity_id=entity_id,
        label=label,
        domain=domain,
        href=template.format(entity_id=quote(entity_id, safe="")),
    )


def resolve_product_refs_in_text(
    context: TenantContext, text: str, *, limit: int = 30
) -> list[EntityRef]:
    """Resolve a bounded number of exact SKU tokens in old assistant text."""
    if not context.allows("inventory") or not text:
        return []
    candidate_limit = min(max(int(limit), 0), _MAX_TEXT_PRODUCT_CANDIDATES)
    if candidate_limit == 0:
        return []
    text = visible_markdown_text(text)

    codes: list[str] = []
    seen: set[str] = set()
    for match in _PRODUCT_CODE_TOKEN.finditer(text):
        code = match.group(1)
        key = code.casefold()
        if len(code) < 2 or key in seen:
            continue
        seen.add(key)
        codes.append(code)
        if len(codes) >= candidate_limit:
            break
    if not codes:
        return []
    return resolve_product_refs(context, codes, batch_size=_MAX_TEXT_PRODUCT_CANDIDATES)


def product_ref_mentioned(text: str, ref: EntityRef) -> bool:
    """Check whether an old message contains this exact SKU or unique product name."""
    if not text:
        return False
    text = visible_markdown_text(text)
    for match in _PRODUCT_CODE_TOKEN.finditer(text):
        if match.group(1).casefold() != ref.entity_id.casefold():
            continue
        if not ref.entity_id.isdigit():
            return True
        # A numeric SKU can also be an amount or invoice number in prose.
        # Check if it has SKU label or product name in the line/table.
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start:] if line_end < 0 else text[line_start:line_end]
        if re.search(rf"\b(?:SKU|c[oó]digo|cod|EAN)\b", line, re.IGNORECASE):
            return True
        if re.search(rf"(?<![\w]){re.escape(ref.label)}(?![\w])", line, re.IGNORECASE):
            return True
        tokens = [
            re.escape(tok) for tok in re.findall(r"\b[A-Za-z0-9áéíóúñÁÉÍÓÚÑ]{4,}\b", ref.label)
            if tok.lower() not in {"para", "cada", "unos", "unas", "como"}
        ]
        if len(tokens) >= 2:
            matched = sum(1 for tok in tokens if re.search(rf"\b{tok}\b", line, re.IGNORECASE))
            if matched >= 2 and matched >= min(len(tokens), 3):
                return True
    return bool(
        ref.label_is_unique
        and re.search(rf"(?<![\w]){re.escape(ref.label)}(?![\w])", text, re.IGNORECASE)
    )
