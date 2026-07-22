"""Central authorization policy for module-scoped API routes.

The key uses the HTTP method and FastAPI's *route template* (not the concrete
request path). Keeping the policy here makes omissions detectable in CI and
prevents a newly added authenticated endpoint from silently becoming visible to
every managed user.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import Depends, HTTPException, Request, status
from starlette.routing import Match

from motoshop_api.auth.deps import authorize_modules, get_current_user
from motoshop_api.auth.users import User

RouteKey = tuple[str, str]


def _routes(module: str, *paths: str) -> dict[RouteKey, tuple[str, ...]]:
    return {("GET", path): (module,) for path in paths}


# One route may list several modules: access is OR, matching require_module.
ROUTE_MODULES: dict[RouteKey, tuple[str, ...]] = {
    # Pipeline observability
    **_routes(
        "pipeline-observability",
        "/api/admin/pipeline/runs",
        "/api/admin/pipeline/runs/{run_id}",
        "/api/admin/pipeline/summary",
        "/api/admin/data/status",
    ),
    # Product, stock, expiry and inventory analysis
    **_routes(
        "inventario",
        "/api/products",
        "/api/products/search-semantic",
        "/api/products/{sku}",
        "/api/products/{sku}/movements",
        "/api/products/{sku}/stock",
        "/api/metrics/inventory-detail",
        "/api/metrics/inventory-discrepancies",
        "/api/metrics/inventory-summary",
        "/api/metrics/inventory-overview",
        "/api/metrics/product-analytics",
        "/api/metrics/product-detail",
        "/api/metrics/product-abc-map",
        "/api/metrics/abc-segmentation",
        "/api/metrics/abc-detalle",
        "/api/metrics/dormidos",
        "/api/metrics/productos-zombie",
        "/api/metrics/salud-catalogo",
        "/api/metrics/vendor-data-flag",
        "/api/metrics/inventario-overview",
        "/api/expiry/lots",
        "/api/expiry/alerts",
    ),
    ("POST", "/api/expiry/receipts"): ("inventario",),
    ("PATCH", "/api/expiry/lots/{lot_id}"): ("inventario",),
    ("DELETE", "/api/expiry/lots/{lot_id}"): ("inventario",),
    ("POST", "/api/expiry/lots/{lot_id}/adjustments"): ("inventario",),
    # Movements: sales and purchases share the same UI surface.
    **_routes(
        "ventas-summary",
        "/api/sales/recent",
        "/api/metrics/sales-summary",
        "/api/metrics/sales-summary-v2",
        "/api/metrics/sales-daily-month",
        "/api/metrics/sales-daily",
        "/api/metrics/sales-monthly",
        "/api/metrics/sales-historical-products",
        "/api/metrics/sales-day-detail",
        "/api/metrics/sales-month-detail",
        "/api/metrics/sales-day-invoices",
        "/api/metrics/cash-closure",
        "/api/metrics/payments-history",
        "/api/metrics/purchases-day-detail",
        "/api/metrics/sales-historical",
        "/api/metrics/sales-history-extended",
        "/api/metrics/sales-trend",
        "/api/metrics/compras-overview",
        "/api/metrics/compras-historico",
        "/api/metrics/compras-por-proveedor",
        "/api/metrics/purchases-day-grouped",
        "/api/metrics/compras-proveedor-detalle",
    ),
    # Forecast/projection
    **_routes(
        "forecast",
        "/api/metrics/sales-forecast-monthly",
        "/api/metrics/forecast-categoria",
        "/api/forecast/{sku}",
    ),
    ("POST", "/api/forecast/cache/clear"): ("forecast",),
    # Alerts, notifications and user alert actions
    **_routes("alerts", "/api/alerts/stockout", "/api/alerts/actions/me"),
    ("POST", "/api/alerts/cache/clear"): ("alerts",),
    ("POST", "/api/alerts/{alert_id}/action"): ("alerts",),
    ("POST", "/api/api/push/subscribe"): ("alerts",),
    ("POST", "/api/api/push/unsubscribe"): ("alerts",),
    # Decisions and actionable purchase planning
    **_routes("decisiones", "/api/metrics/plan-compras"),
    **_routes("acciones", "/api/purchase-plans", "/api/purchase-plans/{plan_id}"),
    ("POST", "/api/purchase-plans"): ("acciones",),
    ("PATCH", "/api/purchase-plans/{plan_id}/status"): ("acciones",),
    ("GET", "/api/metrics/recommendations"): ("decisiones", "acciones"),
    # Analysis, expenses and the general Q&A tool
    **_routes(
        "analisis",
        "/api/metrics/horas-pico",
        "/api/metrics/analisis-balance",
        "/api/metrics/heatmap-dia-hora",
        "/api/metrics/analisis-productos",
        "/api/metrics/analisis-proveedores",
        "/api/gastos/categorias",
        "/api/gastos",
    ),
    ("POST", "/api/gastos"): ("analisis",),
    ("POST", "/api/gastos/copiar"): ("analisis",),
    ("PATCH", "/api/gastos/{gasto_id}"): ("analisis",),
    ("DELETE", "/api/gastos/{gasto_id}"): ("analisis",),
    ("POST", "/api/llm/qa/chat"): ("analisis",),
    # Dedicated analysis surfaces
    **_routes("cohortes", "/api/metrics/cohortes", "/api/metrics/cohortes-detail"),
    **_routes("vendedores", "/api/metrics/vendedores-summary"),
    **_routes("drift", "/api/metrics/drift-summary"),
    # Data catalog
    **_routes(
        "data-catalog",
        "/api/admin/data/catalog",
        "/api/admin/data/catalog/{table_name}",
        "/api/admin/data/lineage",
    ),
    ("POST", "/api/llm/forecast/explain"): ("forecast",),
    # Admin-only metrics cache invalidation.
    ("POST", "/api/metrics/cache/clear"): ("pipeline-observability",),
}


# Routes intentionally outside module RBAC. They remain protected by the stated
# independent policy. This is exported so the CI coverage test audits the list.
ROUTE_MODULE_EXCEPTIONS: Mapping[RouteKey, str] = {
    ("POST", "/api/auth/login"): "public credential exchange",
    ("POST", "/api/auth/refresh"): "public refresh-token exchange",
    ("GET", "/api/auth/me"): "authenticated session/module bootstrap",
    ("GET", "/api/health/ready"): "public readiness probe",
    ("GET", "/api/health/data-freshness"): "public data freshness probe",
    ("POST", "/api/admin/data/refresh"): "admin JWT or machine refresh token",
    ("POST", "/api/admin/pipeline/refresh"): "admin JWT or machine refresh token",
    ("POST", "/api/llm/briefing/generate"): "admin JWT or machine refresh token",
    ("POST", "/api/llm/briefing/send"): "admin JWT or machine refresh token",
    ("GET", "/api/admin/llm-cost"): "admin-only operational accounting",
    ("GET", "/api/admin/users/modules"): "admin-only RBAC administration",
    ("GET", "/api/admin/users"): "admin-only RBAC administration",
    ("POST", "/api/admin/users"): "admin-only RBAC administration",
    ("PATCH", "/api/admin/users/{username}"): "admin-only RBAC administration",
    ("DELETE", "/api/admin/users/{username}"): "admin-only RBAC administration",
}


def route_modules(method: str, route_template: str) -> tuple[str, ...] | None:
    """Return the required modules for an HTTP route template."""
    return ROUTE_MODULES.get((method.upper(), route_template))


def _route_path(route: object) -> str | None:
    """Read the canonical template exposed by Starlette/FastAPI route objects."""
    for attribute in ("path_format", "path"):
        value = getattr(route, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None


def _with_root_path(root_path: str, route_path: str) -> str:
    if not root_path:
        return route_path
    return f"/{root_path.strip('/')}/{route_path.lstrip('/')}"


def request_route_template(request: Request) -> str:
    """Resolve one canonical route template from an active request.

    ``scope['route']`` is not a stable source across every FastAPI/Starlette
    combination: an included-router dependency can observe the router-local
    template (``/metrics/...``) while the application policy uses the final
    prefixed template (``/api/metrics/...``). Prefer any already-classified
    scope template, then match the concrete request against the application's
    final route table. This also recovers dynamic templates without converting
    concrete IDs into policy keys.
    """
    method = request.method.upper()
    root_path = request.scope.get("root_path", "")
    scope_route_path = _route_path(request.scope.get("route"))

    if scope_route_path:
        candidates = [scope_route_path, _with_root_path(root_path, scope_route_path)]
        if scope_route_path.startswith("/") and not scope_route_path.startswith("/api/"):
            candidates.append(f"/api{scope_route_path}")
        for candidate in candidates:
            if route_modules(method, candidate) is not None:
                return candidate

    for app_route in getattr(request.app, "routes", ()):
        methods = getattr(app_route, "methods", None)
        if methods and method not in methods:
            continue
        match, _child_scope = app_route.matches(request.scope)
        if match is not Match.FULL:
            continue
        matched_path = _route_path(app_route)
        if matched_path:
            rooted_path = _with_root_path(root_path, matched_path)
            if route_modules(method, rooted_path) is not None:
                return rooted_path
            return matched_path

    concrete_path = request.scope.get("path") or request.url.path
    if route_modules(method, concrete_path) is not None:
        return concrete_path
    return scope_route_path or concrete_path


async def require_route_module(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """Authorize the current request using :data:`ROUTE_MODULES`.

    Missing policy is a server configuration error, not an implicit allow.
    """
    route_template = request_route_template(request)
    modules = route_modules(request.method, route_template)
    if modules is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La ruta no tiene una política de módulos configurada",
        )
    return authorize_modules(user, modules)
