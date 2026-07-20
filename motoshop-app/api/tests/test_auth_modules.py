"""Authorization contract for module-scoped API surfaces."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user, require_module
from motoshop_api.auth.module_access import (
    ROUTE_MODULE_EXCEPTIONS,
    ROUTE_MODULES,
    require_route_module,
)
from motoshop_api.auth.users import User
from motoshop_api.main import app as production_app


def _client_for(user: User, *required: str) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user

    @app.get("/protected")
    def protected(_user: User = Depends(require_module(*required))) -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def _user(**overrides) -> User:
    values = {
        "username": "managed",
        "hashed_password": "hash",
        "email": "managed@test.com",
        "role": "vendedor",
        "tenants_allowed": ["motoshop"],
        "allowed_modules": [],
        "source": "supabase",
    }
    values.update(overrides)
    return User(**values)


def test_managed_user_requires_one_of_the_declared_modules() -> None:
    denied = _client_for(_user(allowed_modules=["inventario"]), "ventas-summary")
    allowed = _client_for(
        _user(allowed_modules=["inventario", "analisis"]),
        "ventas-summary",
        "analisis",
    )

    assert denied.get("/protected").status_code == 403
    assert allowed.get("/protected").status_code == 200


@pytest.mark.parametrize(
    "user",
    [
        _user(role="admin"),
        _user(source="legacy", allowed_modules=None),
    ],
)
def test_admin_and_unscoped_legacy_user_keep_compatibility(user: User) -> None:
    assert _client_for(user, "ventas-summary").get("/protected").status_code == 200


def test_managed_user_with_empty_tenants_is_not_globally_authorized() -> None:
    from motoshop_api.auth.tenant_dep import get_tenant
    from motoshop_api.tenants import Tenant, _tenants_cache

    _tenants_cache.clear()
    _tenants_cache["motoshop"] = Tenant(
        id="motoshop",
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
    )
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: _user(tenants_allowed=[])

    @app.get("/tenant")
    async def tenant(value: str = Depends(get_tenant)) -> dict[str, str]:
        return {"tenant": value}

    try:
        assert TestClient(app).get("/tenant").status_code == 403
    finally:
        _tenants_cache.clear()


def test_every_api_route_has_module_policy_or_documented_exception() -> None:
    """Fail CI when a new /api route silently omits its RBAC classification."""
    actual: dict[tuple[str, str], object] = {}
    for route in production_app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api"):
            continue
        for method in (getattr(route, "methods", set()) or set()) - {"HEAD", "OPTIONS"}:
            actual[(method, path)] = route

    assert set(actual) == set(ROUTE_MODULES) | set(ROUTE_MODULE_EXCEPTIONS)

    # data/status predates the matrix dependency but already carries an explicit
    # require_module("pipeline-observability") guard. Machine-token/admin routes
    # are deliberately listed as exceptions instead of weakening the dependency.
    direct_module_guards = {("GET", "/api/admin/data/status")}
    for key in ROUTE_MODULES:
        route = actual[key]
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        assert require_route_module in dependencies or key in direct_module_guards, key


def test_central_route_policy_denies_managed_user_before_repository_access() -> None:
    production_app.dependency_overrides[get_current_user] = lambda: _user(
        allowed_modules=["analisis"]
    )
    try:
        response = TestClient(production_app).get("/api/products")
    finally:
        production_app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403



def _request(method: str, path: str, local_template: str) -> Request:
    route = SimpleNamespace(path=local_template, path_format=local_template)
    return Request({
        "type": "http", "method": method, "path": path, "root_path": "",
        "query_string": b"", "headers": [], "app": production_app, "route": route,
    })


@pytest.mark.parametrize(
    ("path", "local_template", "module"),
    [
        ("/api/metrics/sales-summary-v2", "/metrics/sales-summary-v2", "ventas-summary"),
        ("/api/products/SKU-123/movements", "/products/{sku}/movements", "inventario"),
    ],
)
def test_route_policy_recovers_prefix_and_dynamic_template(
    path: str, local_template: str, module: str,
) -> None:
    authorized = asyncio.run(
        require_route_module(_request("GET", path, local_template), _user(allowed_modules=[module]))
    )
    assert authorized.username == "managed"


def test_route_policy_remains_fail_closed_for_unknown_request() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_route_module(
            _request("GET", "/api/not-classified", "/not-classified"),
            _user(allowed_modules=["inventario", "ventas-summary", "analisis"]),
        ))
    assert (exc_info.value.status_code, exc_info.value.detail) == (
        500, "La ruta no tiene una política de módulos configurada",
    )


def test_sales_summary_v2_reaches_handler_instead_of_missing_policy() -> None:
    from motoshop_api.auth.tenant_dep import get_tenant
    from motoshop_api.metrics.router import _clear_metrics_cache, get_repo

    class Repo:
        @staticmethod
        def get_sales_summary_v2() -> dict[str, object]:
            return {
                "business_month": "2026-07", "max_sales_date": "2026-07-20",
                "as_of_business_date": "2026-07-20", "current_month_accumulated": 100.0,
                "current_month_days_with_sales": 1,
                "previous_month_same_window": {
                    "from": "2026-06-01", "to": "2026-06-20", "amount": 90.0,
                    "delta_pct": 11.1,
                },
                "same_month_previous_years": [], "ticket_promedio": 50.0, "num_facturas": 2,
            }

    overrides = {get_current_user: lambda: _user(role="admin"),
                 get_tenant: lambda: "motoshop", get_repo: Repo}
    production_app.dependency_overrides.update(overrides)
    _clear_metrics_cache()
    try:
        response = TestClient(production_app, raise_server_exceptions=False).get(
            "/api/metrics/sales-summary-v2", headers={"X-Tenant": "motoshop"},
        )
    finally:
        for dependency in overrides:
            production_app.dependency_overrides.pop(dependency, None)
        _clear_metrics_cache()
    assert response.status_code == 200
    assert response.json()["as_of_business_date"] == "2026-07-20"
