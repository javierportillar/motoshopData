"""ERP Repository providing multi-tenant sales CRUD, cash register management, and product catalog.

Supports:
- Tenant-partitioned storage: sales, sessions, movements, and consecutives are isolated per tenant.
- Thread-safe consecutive allocation (`conres`) per document type.
- Hardened 24-hour idempotency cache: raises 422 if payload changed, prunes expired entries.
- sgHermes legacy negative stock support for exact stock restoration upon voiding.
- Complete audit trail (voided_by, void_reason, voided_at).
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException, status

from motoshop_api.erp.calculations import (
    calculate_denominations_total,
    calculate_line_item,
    calculate_sale_totals,
    round_cop,
)
from motoshop_api.erp.models import (
    CashMovementIn,
    CashMovementOut,
    CashSessionCloseIn,
    CashSessionOpenIn,
    CashSessionOut,
    DenominationCountIn,
    ProductSearchResult,
    SaleCreateIn,
    SaleItemOut,
    SaleOut,
)

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_PRODUCTS: list[dict[str, Any]] = [
    {
        "sku": "CAS-ACT-20W50",
        "name": "Aceite Castrol Actevo 20W-50 4T x 1L",
        "barcode": "7701234567890",
        "price": Decimal("28000.00"),
        "stock": Decimal("24.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Aceites y Lubricantes",
    },
    {
        "sku": "MOT-7100-10W40",
        "name": "Aceite Motul 7100 10W-40 100% Sintético x 1L",
        "barcode": "7702345678901",
        "price": Decimal("68000.00"),
        "stock": Decimal("12.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Aceites y Lubricantes",
    },
    {
        "sku": "PAS-DEL-200NS",
        "name": "Pastillas de Freno Delanteras Pulsar 200 NS / Dominar",
        "barcode": "7703456789012",
        "price": Decimal("35000.00"),
        "stock": Decimal("18.00"),
        "tax_rate": Decimal("0.00"),
        "category": "Frenos",
    },
    {
        "sku": "ARR-CAS-P200",
        "name": "Kit Arrastre Pulsar 200 NS Cassarella",
        "barcode": "7704567890123",
        "price": Decimal("145000.00"),
        "stock": Decimal("6.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Transmisión",
    },
    {
        "sku": "BUJ-NGK-CR9E",
        "name": "Bujía NGK CR9E Cobre Convencional",
        "barcode": "7705678901234",
        "price": Decimal("18000.00"),
        "stock": Decimal("35.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Encendido",
    },
    {
        "sku": "LLA-MICH-10080",
        "name": "Llanta Delantera Michelin Pilot Street 100/80-17",
        "barcode": "7706789012345",
        "price": Decimal("185000.00"),
        "stock": Decimal("4.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Llantas",
    },
    {
        "sku": "FIL-KN-138",
        "name": "Filtro de Aceite K&N KN-138",
        "barcode": "7707890123456",
        "price": Decimal("42000.00"),
        "stock": Decimal("9.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Filtros",
    },
    {
        "sku": "LIQ-MOT-DOT4",
        "name": "Líquido de Frenos Motul DOT 4 500ml",
        "barcode": "7708901234567",
        "price": Decimal("26000.00"),
        "stock": Decimal("14.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Líquidos",
    },
    {
        "sku": "CAD-DID-520VX3",
        "name": "Cadena DID 520VX3 O-Ring Reforzada",
        "barcode": "7709012345678",
        "price": Decimal("230000.00"),
        "stock": Decimal("5.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Transmisión",
    },
    {
        "sku": "CAS-SHAFT-582",
        "name": "Casco Integral Shaft Pro Series 582",
        "barcode": "7700123456789",
        "price": Decimal("320000.00"),
        "stock": Decimal("3.00"),
        "tax_rate": Decimal("19.00"),
        "category": "Accesorios y Seguridad",
    },
    {
        "sku": "PROD-7322",
        "name": "Repuesto Muestra Factura 7322",
        "barcode": "7709999997322",
        "price": Decimal("100000.00"),
        "stock": Decimal("10.00"),
        "tax_rate": Decimal("0.00"),
        "category": "Repuestos",
    },
]


class ERPRepository:
    """Thread-safe, multi-tenant ERP and POS repository."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Partitioned by tenant_id: _sales[tenant_id][sale_id]
        self._sales: dict[str, dict[str, SaleOut]] = {}
        # Consecutives partitioned by (tenant_id, doc_type)
        self._consecutives: dict[tuple[str, str], int] = {}
        # Cash sessions partitioned by tenant_id: _sessions[tenant_id][session_id]
        self._sessions: dict[str, dict[str, CashSessionOut]] = {}
        # Cash movements partitioned by tenant_id: _movements[tenant_id][session_id]
        self._movements: dict[str, dict[str, list[CashMovementOut]]] = {}
        # Products partitioned by tenant_id: _products[tenant_id][sku]
        self._products: dict[str, dict[str, ProductSearchResult]] = {}
        # Idempotency cache: idempotency_key -> (cached_at, payload_hash, SaleOut)
        self._idempotency_cache: dict[str, tuple[datetime, str, SaleOut]] = {}

    def _ensure_tenant_products(self, tenant_id: str) -> dict[str, ProductSearchResult]:
        """Seeds default product catalog if tenant catalog is empty."""
        if tenant_id not in self._products:
            catalog: dict[str, ProductSearchResult] = {}
            for p in DEFAULT_SAMPLE_PRODUCTS:
                item = ProductSearchResult(
                    sku=p["sku"],
                    name=p["name"],
                    price=p["price"],
                    stock=p["stock"],
                    tax_rate=p["tax_rate"],
                    category=p.get("category"),
                    barcode=p.get("barcode"),
                )
                catalog[item.sku] = item
            self._products[tenant_id] = catalog
        return self._products[tenant_id]

    def _allocate_consecutive(self, tenant_id: str, doc_type: str) -> tuple[int, str]:
        """Thread-safe allocation of consecutive per tenant and document type."""
        key = (tenant_id, doc_type)
        current = self._consecutives.get(key, 0) + 1
        self._consecutives[key] = current
        number = f"{doc_type}-{current:06d}"
        return current, number

    def _prune_expired_idempotency_keys(self, now: datetime) -> None:
        """Removes idempotency entries older than 24 hours to prevent memory leaks."""
        cutoff = now - timedelta(hours=24)
        expired = [
            k for k, (cached_at, _, _) in self._idempotency_cache.items()
            if cached_at < cutoff
        ]
        for k in expired:
            del self._idempotency_cache[k]

    # ─── Sales Operations ──────────────────────────────────────────

    def create_sale(
        self,
        tenant_id: str,
        sale_in: SaleCreateIn,
        cashier_user_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[SaleOut, bool]:
        """Creates a sale or returns cached one if idempotent key was seen within 24h.

        Raises 422 if same idempotency key is re-used with a different payload.
        Returns (sale_out, is_created).
        """
        now = datetime.now(timezone.utc)
        payload_hash = hashlib.sha256(sale_in.model_dump_json().encode("utf-8")).hexdigest()

        with self._lock:
            self._prune_expired_idempotency_keys(now)

            # 1. Check idempotency cache
            if idempotency_key:
                cached = self._idempotency_cache.get(idempotency_key)
                if cached:
                    cached_at, cached_hash, existing_sale = cached
                    if now - cached_at < timedelta(hours=24):
                        if cached_hash != payload_hash:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Idempotency-Key was already used with a different request payload",
                            )
                        logger.info(
                            "idempotent_sale_replayed",
                            key=idempotency_key,
                            sale_id=existing_sale.id,
                            tenant=tenant_id,
                        )
                        return existing_sale, False

            # 2. Calculate line items and totals
            calculated_items: list[SaleItemOut] = [
                calculate_line_item(item) for item in sale_in.items
            ]
            totals = calculate_sale_totals(calculated_items)

            # 3. Consecutive allocation per tenant
            consecutive, number = self._allocate_consecutive(tenant_id, sale_in.doc_type)

            # 4. Create SaleOut
            sale_id = idempotency_key or f"SALE-{uuid.uuid4().hex[:12].upper()}"
            sale_out = SaleOut(
                id=sale_id,
                number=number,
                consecutive=consecutive,
                doc_type=sale_in.doc_type,
                branch_id=sale_in.branch_id,
                warehouse_id=sale_in.warehouse_id,
                session_id=sale_in.session_id,
                client_id=sale_in.client_id,
                client_name=sale_in.client_name,
                subtotal=totals["subtotal"],
                discount_total=totals["discount_total"],
                tax_total=totals["tax_total"],
                grand_total=totals["grand_total"],
                status="issued",
                items=calculated_items,
                payments=sale_in.payments,
                cashier_user_id=cashier_user_id,
                created_at=now,
                notes=sale_in.notes,
            )

            # 5. Persist sale under tenant
            tenant_sales = self._sales.setdefault(tenant_id, {})
            tenant_sales[sale_out.id] = sale_out

            # 6. Update Cash Session if active
            tenant_sessions = self._sessions.setdefault(tenant_id, {})
            if sale_out.session_id and sale_out.session_id in tenant_sessions:
                session = tenant_sessions[sale_out.session_id]
                if session.status == "open":
                    cash_amount = sum(
                        (p.amount for p in sale_out.payments if p.method == "CASH"),
                        Decimal("0.00"),
                    )
                    session.cash_sales = round_cop(session.cash_sales + cash_amount)
                    session.expected_cash = round_cop(
                        session.opening_float + session.cash_sales + session.cash_in - session.cash_out
                    )

            # 7. Deduct stock (sgHermes legacy behavior: allows negative stock)
            prods = self._ensure_tenant_products(tenant_id)
            for item in calculated_items:
                if item.sku in prods:
                    prods[item.sku].stock = round_cop(prods[item.sku].stock - item.quantity)

            # 8. Record in idempotency cache
            if idempotency_key:
                self._idempotency_cache[idempotency_key] = (now, payload_hash, sale_out)

            return sale_out, True

    def get_sale(self, tenant_id: str, sale_id: str) -> SaleOut | None:
        """Finds sale by ID or by invoice number within tenant scope."""
        with self._lock:
            tenant_sales = self._sales.get(tenant_id, {})
            if sale_id in tenant_sales:
                return tenant_sales[sale_id]
            for s in tenant_sales.values():
                if s.number == sale_id:
                    return s
            return None

    def list_sales(
        self,
        tenant_id: str,
        status: Literal["issued", "voided"] | None = None,
        doc_type: Literal["POS", "FV", "RM"] | None = None,
        branch_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SaleOut]:
        """Lists sales matching filters for tenant, sorted descending by created_at."""
        with self._lock:
            tenant_sales = self._sales.get(tenant_id, {})
            sales = list(tenant_sales.values())

        if status:
            sales = [s for s in sales if s.status == status]
        if doc_type:
            sales = [s for s in sales if s.doc_type == doc_type]
        if branch_id:
            sales = [s for s in sales if s.branch_id == branch_id]
        if session_id:
            sales = [s for s in sales if s.session_id == session_id]

        sales.sort(key=lambda s: s.created_at, reverse=True)
        return sales[offset : offset + limit]

    def void_sale(self, tenant_id: str, sale_id: str, reason: str, voided_by: str) -> SaleOut:
        """Marks a sale as voided, audits who voided it, and restores stock exactly."""
        with self._lock:
            sale = self.get_sale(tenant_id, sale_id)
            if not sale:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sale '{sale_id}' not found for tenant '{tenant_id}'",
                )
            if sale.status == "voided":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sale is already voided",
                )

            # DIAN electronic invoice annulment guard (spec erp-dian-einvoicing / Valid_EdiDocele):
            # estfele = 1 / ACCEPTED documents cannot be voided directly; requires DIAN Credit Note handling.
            from motoshop_api.erp.dian import DianStatusEnum, get_dian_queue

            dian_queue = get_dian_queue()
            dian_doc = dian_queue.get_dian_status_for_sale(sale_id, tenant_id)
            if dian_doc and dian_doc.status == DianStatusEnum.ACCEPTED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Documento electrónico aceptado por la DIAN (estfele=1). "
                        "No se puede anular directamente, requiere Nota Crédito (DIAN Credit Note handling)."
                    ),
                )
            if dian_doc and dian_doc.status != DianStatusEnum.ACCEPTED:
                dian_queue.cancel_sale(sale_id, tenant_id)

            now = datetime.now(timezone.utc)
            sale.status = "voided"
            sale.void_reason = reason
            sale.voided_at = now
            sale.voided_by = voided_by

            # If sale was part of an open session, decrement cash sales
            tenant_sessions = self._sessions.get(tenant_id, {})
            if sale.session_id and sale.session_id in tenant_sessions:
                session = tenant_sessions[sale.session_id]
                if session.status == "open":
                    cash_amount = sum(
                        (p.amount for p in sale.payments if p.method == "CASH"),
                        Decimal("0.00"),
                    )
                    session.cash_sales = max(
                        Decimal("0.00"),
                        round_cop(session.cash_sales - cash_amount),
                    )
                    session.expected_cash = round_cop(
                        session.opening_float + session.cash_sales + session.cash_in - session.cash_out
                    )

            # Revert stock exactly (sgHermes behavior)
            prods = self._ensure_tenant_products(tenant_id)
            for item in sale.items:
                if item.sku in prods:
                    prods[item.sku].stock = round_cop(prods[item.sku].stock + item.quantity)

            return sale

    # ─── Cash Session Operations ───────────────────────────────────

    def open_session(
        self,
        tenant_id: str,
        branch_id: str,
        cashier_user_id: str,
        cashier_name: str,
        opening_float: Decimal,
    ) -> CashSessionOut:
        """Opens a new cash register session for the tenant."""
        with self._lock:
            tenant_sessions = self._sessions.setdefault(tenant_id, {})

            # Check for existing open session for this cashier within tenant
            for s in tenant_sessions.values():
                if s.cashier_user_id == cashier_user_id and s.status == "open":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cashier '{cashier_user_id}' already has active session '{s.id}' in tenant '{tenant_id}'",
                    )

            now = datetime.now(timezone.utc)
            session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
            opening = round_cop(opening_float)

            session = CashSessionOut(
                id=session_id,
                branch_id=branch_id,
                cashier_user_id=cashier_user_id,
                cashier_name=cashier_name,
                status="open",
                opened_at=now,
                opening_float=opening,
                cash_sales=Decimal("0.00"),
                cash_in=Decimal("0.00"),
                cash_out=Decimal("0.00"),
                expected_cash=opening,
            )
            tenant_sessions[session_id] = session
            tenant_movements = self._movements.setdefault(tenant_id, {})
            tenant_movements[session_id] = []
            return session

    def get_active_session_for_user(
        self,
        tenant_id: str,
        cashier_user_id: str,
    ) -> CashSessionOut | None:
        """Retrieves currently open session for the user within tenant."""
        with self._lock:
            tenant_sessions = self._sessions.get(tenant_id, {})
            for s in tenant_sessions.values():
                if s.cashier_user_id == cashier_user_id and s.status == "open":
                    return s
            return None

    def add_movement(
        self,
        tenant_id: str,
        session_id: str,
        type: Literal["IN", "OUT"],
        amount: Decimal,
        reason: str,
        performed_by: str,
    ) -> CashMovementOut:
        """Records an income/expense manual cash movement for tenant session."""
        with self._lock:
            tenant_sessions = self._sessions.get(tenant_id, {})
            if session_id not in tenant_sessions:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found in tenant '{tenant_id}'",
                )
            session = tenant_sessions[session_id]
            if session.status != "open":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot add movement to a closed session",
                )

            now = datetime.now(timezone.utc)
            mov_id = f"MOV-{uuid.uuid4().hex[:8].upper()}"
            amt = round_cop(amount)

            mov = CashMovementOut(
                id=mov_id,
                session_id=session_id,
                type=type,
                amount=amt,
                reason=reason,
                performed_by=performed_by,
                created_at=now,
            )

            if type == "IN":
                session.cash_in = round_cop(session.cash_in + amt)
            else:
                session.cash_out = round_cop(session.cash_out + amt)

            session.expected_cash = round_cop(
                session.opening_float + session.cash_sales + session.cash_in - session.cash_out
            )

            tenant_movements = self._movements.setdefault(tenant_id, {})
            tenant_movements.setdefault(session_id, []).append(mov)
            return mov

    def close_session(
        self,
        tenant_id: str,
        session_id: str,
        actual_cash: Decimal,
        closed_by: str,
        denominations: DenominationCountIn | None = None,
        notes: str | None = None,
    ) -> CashSessionOut:
        """Closes a cash session and computes cash variance."""
        with self._lock:
            tenant_sessions = self._sessions.get(tenant_id, {})
            if session_id not in tenant_sessions:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found in tenant '{tenant_id}'",
                )
            session = tenant_sessions[session_id]
            if session.status != "open":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cash session is already closed",
                )

            counted = round_cop(actual_cash)
            if denominations is not None and counted == Decimal("0.00"):
                counted = calculate_denominations_total(denominations)

            expected = round_cop(
                session.opening_float + session.cash_sales + session.cash_in - session.cash_out
            )
            variance = round_cop(counted - expected)

            session.expected_cash = expected
            session.actual_cash = counted
            session.cash_variance = variance
            session.denominations = denominations
            session.notes = notes
            session.status = "closed"
            session.closed_at = datetime.now(timezone.utc)

            return session

    # ─── Product Catalog Search ────────────────────────────────────

    def search_products(
        self,
        tenant_id: str,
        q: str = "",
        limit: int = 50,
    ) -> list[ProductSearchResult]:
        """Searches products by barcode, SKU, name, or category within tenant."""
        clean_q = q.strip().lower()
        with self._lock:
            items = list(self._ensure_tenant_products(tenant_id).values())

        if not clean_q:
            return items[:limit]

        matched: list[ProductSearchResult] = []
        for p in items:
            if (
                clean_q in p.name.lower()
                or clean_q in p.sku.lower()
                or (p.barcode and clean_q in p.barcode.lower())
                or (p.category and clean_q in p.category.lower())
            ):
                matched.append(p)
                if len(matched) >= limit:
                    break

        return matched


# Global singleton repo instance
_erp_repo: ERPRepository | None = None
_repo_lock = threading.Lock()


def get_erp_repo() -> ERPRepository:
    """Dependency provider for ERPRepository singleton."""
    global _erp_repo
    if _erp_repo is None:
        with _repo_lock:
            if _erp_repo is None:
                _erp_repo = ERPRepository()
    return _erp_repo


def reset_erp_repo() -> ERPRepository:
    """Helper to reset ERPRepository for isolated tests."""
    global _erp_repo
    with _repo_lock:
        _erp_repo = ERPRepository()
    from motoshop_api.erp.dian import reset_dian_queue

    reset_dian_queue()
    return _erp_repo
