"""ERP guard chain: role gates + tenant enablement + route matrix.

Server-side authorization decided here; the frontend only hides controls
(spec erp-write-foundation, ADR-0008-06):
- WF-1s1  JWT (via get_current_user, HTTPBearer) → 401 without a token.
- WF-1s2  annulments: admin/gerente only (parity with the legacy formuleo).
- WF-1s3  collections: admin/gerente (vendedor read-only there).
- WF-2s1  route matrix deny happens BEFORE business validation; the ERP
          entries live here until slice 2 mounts the routers, so the
          production-route audit in test_auth_modules stays untouched.
- WF-3s1  tenant gate: only tenants with erp.enabled=true reach the engine;
          masvital → 403 "no está habilitado".
- WF-3s2  the write scope (empresa) is resolved server-side from
          tenants.yaml — the client never supplies it.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.tenants import Tenant, TenantErpConfig

__all__ = [
    "ERP_ROUTE_MODULES",
    "ERP_WRITE_ROLES",
    "TenantErpConfig",
    "require_erp_annul",
    "require_erp_collections_write",
    "require_erp_masters_write",
    "require_erp_tenant",
    "require_erp_write",
]


# ERP routes are policy-declared here from slice 1 so routers in slices 2+ inherit
# the matrix automatically via route_modules(). They are NOT part of
# module_access.ROUTE_MODULES: that dict mirrors routes mounted in the
# production app and an audit test enforces the exact 1:1 (adding unmounted
# entries there would break test_auth_modules until slice 2 ships them).
ERP_ROUTE_MODULES: dict[tuple[str, str], tuple[str, ...]] = {
    ("GET", "/api/erp/terceros"): ("erp-masters",),
    ("GET", "/api/erp/terceros/{id}"): ("erp-masters",),
    ("POST", "/api/erp/terceros"): ("erp-masters-write",),
    ("PATCH", "/api/erp/terceros/{id}"): ("erp-masters-write",),
    ("GET", "/api/erp/productos"): ("erp-masters",),
    ("GET", "/api/erp/productos/{id}"): ("erp-masters",),
    ("POST", "/api/erp/productos"): ("erp-masters-write",),
    ("PATCH", "/api/erp/productos/{id}"): ("erp-masters-write",),
    ("GET", "/api/erp/marcas"): ("erp-masters",),
    ("GET", "/api/erp/bodegas"): ("erp-masters",),
    ("POST", "/api/erp/invoices"): ("erp-invoicing",),
    ("GET", "/api/erp/invoices/{numfven}/receipt"): ("erp-invoicing",),
    ("POST", "/api/erp/receipts"): ("erp-cash",),
    ("POST", "/api/erp/documents/{codclas}/{numfven}/annulment"): ("erp-anulaciones",),
}

# Roles allowed to WRITE documents (WF-1s1): same population as the legacy
# permisosfac flow. Annulments/collections are admin+gerente only.
ERP_WRITE_ROLES = frozenset({"admin", "gerente", "vendedor"})
ERP_ERP_MANAGEMENT_ROLES = frozenset({"admin", "gerente"})


# ─── role gates ────────────────────────────────────────────────


async def require_erp_write(user: User = Depends(get_current_user)) -> User:
    """Document-creating/routing roles (WF-1s1)."""
    if user.role not in ERP_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol '{user.role}' no tiene permiso de escritura",
        )
    return user


async def require_erp_masters_write(user: User = Depends(get_current_user)) -> User:
    """Masters write guard (MW-5): legacy parity reserves create/edit to
    admin/gerente — a matrix grant can never widen the role population."""
    if user.role not in ERP_ERP_MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol '{user.role}' no tiene permiso de escritura de maestros",
        )
    return user


async def require_erp_annul(user: User = Depends(get_current_user)) -> User:
    """Annulment guard (WF-1s2): legacy parity reserves this to admin/gerente."""
    if user.role not in ERP_ERP_MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol '{user.role}' no tiene permiso de anulación",
        )
    return user


async def require_erp_collections_write(
    user: User = Depends(get_current_user),
) -> User:
    """Collections/consignments guard (WF-1s3) — admin/gerente only."""
    if user.role not in ERP_ERP_MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol '{user.role}' no tiene permiso de escribir recaudos/cargos",
        )
    return user


# ─── tenant gate ───────────────────────────────────────────────


async def require_erp_tenant(tenant_id: str = Depends(get_tenant)) -> Tenant:
    """Only tenants with erp.enabled=true reach the engine (WF-3s1)."""
    config = _erp_configs().get(tenant_id)
    if config is None or not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"El tenant '{tenant_id}' no está habilitado para escrituras "
            "transaccionales ERP",
        )
    return _tenant_model(tenant_id)


def _erp_configs() -> dict[str, TenantErpConfig]:
    from motoshop_api.tenants import get_all_tenants

    return {tid: tenant.erp for tid, tenant in get_all_tenants().items()}


def _tenant_model(tenant_id: str) -> Tenant:
    from motoshop_api.tenants import get_tenant_config

    tenant = get_tenant_config(tenant_id)
    if tenant is None:  # get_tenant already validated existence; defensive
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")
    return tenant
