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

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

from fastapi import Depends, HTTPException, status

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.tenants import Tenant, TenantErpConfig

__all__ = [
    "CausacionUnbalanced",
    "ERP_ROUTE_MODULES",
    "ERP_WRITE_ROLES",
    "Hay_Cie_Eli",
    "PeriodLockedError",
    "TenantErpConfig",
    "assert_causacion_balanced",
    "assert_period_open",
    "hay_cie_eli",
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
    ("POST", "/api/erp/cash/movements"): ("erp-cash",),
    ("POST", "/api/erp/cash/egresos"): ("erp-cash",),
    ("POST", "/api/erp/cash/arqueo"): ("erp-cash",),
    ("POST", "/api/erp/bank/consignments"): ("erp-cash",),
    ("POST", "/api/erp/documents/{codclas}/{numfven}/annulment"): ("erp-anulaciones",),
}

# Roles allowed to WRITE documents (WF-1s1): same population as the legacy
# permisosfac flow. Annulments/collections are admin+gerente only.
ERP_WRITE_ROLES = frozenset({"admin", "gerente", "vendedor"})
ERP_ERP_MANAGEMENT_ROLES = frozenset({"admin", "gerente"})


# ─── accounting causación balance (slice 3, task 3.4) ────────────


class CausacionUnbalanced(Exception):
    """The accounting causación does not balance — the save MUST abort.

    Spec SI-9s1/SI-9s2: ``Σ valdeb = Σ valcre`` over the ``detcuentas`` rows
    of one document. ``unmapped`` names the postings whose account mapping
    was missing (a bad account mapping is the usual cause: the counterpart
    entry could not be written).
    """

    def __init__(
        self,
        total_debit: Decimal,
        total_credit: Decimal,
        unmapped: Iterable[str] = (),
    ):
        self.total_debit = total_debit
        self.total_credit = total_credit
        self.unmapped = list(unmapped)
        detail = (
            f"la causación no cuadra: Σdeb={total_debit} ≠ Σcred={total_credit}"
        )
        if self.unmapped:
            detail += "; falta la cuenta de: " + ", ".join(self.unmapped)
        super().__init__(detail)


def assert_causacion_balanced(
    entries: Iterable[Mapping[str, object]],
    *,
    unmapped: Iterable[str] = (),
) -> None:
    """Guard: the document's accounting entries MUST balance (SI-9s1).

    ``entries`` are the ``detcuentas`` rows (``valdeb``/``valhab``). The
    check runs INSIDE the save unit so an unbalanced causación rolls the
    unit back, leaves zero legacy rows and marks the journal FAILED.
    """
    rows = list(entries)
    total_debit = sum((_as_decimal(row.get("valdeb")) for row in rows), Decimal("0"))
    total_credit = sum((_as_decimal(row.get("valhab")) for row in rows), Decimal("0"))
    missing = list(unmapped)
    if missing or total_debit != total_credit:
        raise CausacionUnbalanced(total_debit, total_credit, missing)


def _as_decimal(value: object) -> Decimal:
    """Legacy numeric (str/Decimal) → Decimal, exact."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ─── period lock (Hay_Cie_Eli — shared by cash docs and slice 5) ───


class PeriodLockedError(Exception):
    """409: the document date falls inside a closed accounting period.

    Shared contract: the cash write path (CC-6) and the annulment path
    (slice 5, AN-1s2) reject the SAME truth — the ``cierresper`` closure.
    Routers map ``detail()`` into ``HTTPException(409, detail=...)``.
    """

    def __init__(self, message: str, *, period: dict | None = None):
        super().__init__(message)
        self.message = message
        self.period = period or {}

    def detail(self) -> dict:
        return {
            "message": self.message,
            "code": "period_locked",
            "period": self.period,
        }


#: `cierresper.tipcie` values that close a period (P/M/A).
LOCKED_PERIOD_TYPES = frozenset({"P", "M", "A"})


def _as_date(value: object) -> date | None:
    """Legacy date column (DATE/datetime/ISO string) → ``date``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def hay_cie_eli(
    periods: Iterable[Mapping[str, object]],
    *,
    fecha: object,
    codclas: str = "",
    numnum: str = "",
) -> dict | None:
    """``Hay_Cie_Eli`` parity: is ``fecha`` inside a closed accounting period?

    ``periods`` are the ``cierresper`` rows (``fecdes``/``fechas``/``tipcie``
    plus the optional ``codclas``/``numaju`` scope). A closure with a blank
    ``codclas``/``numaju`` locks EVERY document of the period; a closure that
    names them locks only that document. Returns the offending row or ``None``.

    At CREATION time the document number is not reserved yet, so a closure
    scoped to a single ``numaju`` cannot be matched yet — the class/date rule
    is the one enforced (the annulment path, which works on an existing
    document, matches the number too).
    """
    target = _as_date(fecha)
    if target is None:
        return None
    for row in periods:
        tipcie = str(row.get("tipcie") or "").upper()
        if tipcie not in LOCKED_PERIOD_TYPES:
            continue
        row_class = str(row.get("codclas") or "").strip()
        row_number = str(row.get("numaju") or "").strip()
        if row_class and row_class != str(codclas or "").strip():
            continue
        if row_number and row_number != str(numnum or "").strip():
            continue
        start = _as_date(row.get("fecdes"))
        end = _as_date(row.get("fechas"))
        if start is None and end is None:
            continue
        if start is not None and target < start:
            continue
        if end is not None and target > end:
            continue
        return dict(row)
    return None


#: Legacy spelling kept as an alias so the traceability is explicit.
Hay_Cie_Eli = hay_cie_eli


def assert_period_open(
    periods: Iterable[Mapping[str, object]],
    *,
    fecha: object,
    codclas: str = "",
    numnum: str = "",
    what: str = "el documento",
) -> None:
    """Raise :class:`PeriodLockedError` when the date is inside a closure."""
    locked = hay_cie_eli(periods, fecha=fecha, codclas=codclas, numnum=numnum)
    if locked is None:
        return
    raise PeriodLockedError(
        f"La fecha de {what} está dentro de un período contable cerrado "
        f"({locked.get('fecdes')} - {locked.get('fechas')})",
        period=locked,
    )


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
