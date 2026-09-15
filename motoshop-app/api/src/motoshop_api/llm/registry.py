"""Allowlisted assistant capabilities and server-side entity route policy."""

from __future__ import annotations

import re

from motoshop_api.auth.tenant_dep import TenantContext
from motoshop_api.llm.contracts import EntityRef

_CAPABILITIES = {
    domain: "supabase" if domain in {"expenses", "expiry"} else "duckdb"
    for domain in (
        "sales", "purchases", "inventory", "abc", "dormant_products", "alerts", "forecasts",
        "analyses", "expenses", "expiry",
    )
}
_ROUTES = {"product": ("inventory", "/inventario/productos/{entity_id}"),
           "alert": ("alerts", "/inventario/alertas/{entity_id}")}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
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
def resolve_entity_ref(context: TenantContext, *, entity_type: str, entity_id: str, label: str,
                       domain: str, route_key: str) -> EntityRef:
    """Resolve a typed route only after tenant and destination authorization."""
    if not context.allows(domain):
        raise PermissionError("entity_destination_denied")
    route_domain, template = _ROUTES.get(route_key, ("", ""))
    if route_domain != domain or not _SAFE_ID.fullmatch(entity_id):
        raise ValueError("invalid_entity_reference")
    return EntityRef(entity_type=entity_type, entity_id=entity_id, label=label, domain=domain,
                     href=template.format(entity_id=entity_id))
