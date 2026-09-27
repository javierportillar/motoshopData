"""Allowlisted assistant capabilities and server-side entity route policy."""

from __future__ import annotations

import re
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
}
_ENTITY_SOURCES = {
    "alert": ("gold_alertas_quiebre", "sku"),
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,120}$")
_PRODUCT_CODE_TOKEN = re.compile(
    r"(?<![\w])([A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,118}[A-Za-z0-9])?)(?![\w])"
)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RAW_URL = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
_MAX_TEXT_PRODUCT_CANDIDATES = 50


def visible_markdown_text(text: str) -> str:
    """Remove link destinations and bare URLs before matching product mentions."""
    return _RAW_URL.sub(" ", _MARKDOWN_LINK.sub(r"\1", text))


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
        SELECT cod_producto,
               COALESCE(NULLIF(TRIM(nombre_producto), ''), cod_producto) AS label
        FROM (
            SELECT cod_producto, nombre_producto,
                   ROW_NUMBER() OVER (
                       PARTITION BY cod_producto ORDER BY {catalog_order}
                   ) AS product_row
            FROM silver_dim_producto
            WHERE UPPER(cod_producto) IN ({placeholders}) {snapshot_filter}
        ) AS ranked
        WHERE product_row = 1
        ORDER BY UPPER(cod_producto)
    """
    connection = None
    cursor = None
    try:
        connection = get_shared_connection(_make_db_path(context.tenant_id))
        cursor = connection.execute(catalog_sql, parameters)
        products = cursor.fetchall()
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
        cursor = connection.execute(label_sql, labels)
        label_counts = {str(row[0]).casefold(): int(row[1]) for row in cursor.fetchall()}
    except Exception:
        # If uniqueness cannot be verified, SKU links remain safe but names
        # must not be treated as unambiguous by the UI.
        label_counts = {}
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            cursor.close()

    refs = []
    for entity_id, raw_label in products:
        label = str(raw_label)
        refs.append(EntityRef(
            entity_type="product",
            entity_id=str(entity_id),
            label=label,
            domain="inventory",
            href=f"/dashboards/productos/{quote(str(entity_id), safe='')}",
            label_is_unique=label_counts.get(label.casefold(), 0) == 1,
        ))
    return refs


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
        # Require its canonical product name in the same line before linking it.
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start:] if line_end < 0 else text[line_start:line_end]
        if re.search(rf"(?<![\w]){re.escape(ref.label)}(?![\w])", line, re.IGNORECASE):
            return True
    return bool(
        ref.label_is_unique
        and re.search(rf"(?<![\w]){re.escape(ref.label)}(?![\w])", text, re.IGNORECASE)
    )
