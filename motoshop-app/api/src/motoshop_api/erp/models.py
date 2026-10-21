"""ERP data contracts — union of two lineages on the same module:

- Pydantic models for POS, Cash Sessions & ERP transactions
  (Web POS and sgHermes reverse-engineering specs, origin/main POS core).
- SQLAlchemy Core table definitions for the ERP ``app_*`` companions
  (erp-transaccional-web slice 1; F8-001/F8-002 own the physical DDL).
"""

from __future__ import annotations

# ═══ POS / cash / session contracts (origin/main POS core) ════════════════

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── Denominations ───────────────────────────────────────────────

class DenominationCountIn(BaseModel):
    """Breakdown for Colombian banknotes and coins."""
    model_config = ConfigDict(populate_by_name=True)

    b_100k: int = Field(default=0, ge=0, description="Billetes $100.000")
    b_50k: int = Field(default=0, ge=0, description="Billetes $50.000")
    b_20k: int = Field(default=0, ge=0, description="Billetes $20.000")
    b_10k: int = Field(default=0, ge=0, description="Billetes $10.000")
    b_5k: int = Field(default=0, ge=0, description="Billetes $5.000")
    b_2k: int = Field(default=0, ge=0, description="Billetes $2.000")
    c_1000: int = Field(default=0, ge=0, description="Monedas $1.000")
    c_500: int = Field(default=0, ge=0, description="Monedas $500")
    c_200: int = Field(default=0, ge=0, description="Monedas $200")
    c_100: int = Field(default=0, ge=0, description="Monedas $100")
    c_50: int = Field(default=0, ge=0, description="Monedas $50")

    @model_validator(mode="before")
    @classmethod
    def parse_flexible_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        mapping = {
            "100000": "b_100k",
            "100k": "b_100k",
            "bill_100k": "b_100k",
            "50000": "b_50k",
            "50k": "b_50k",
            "bill_50k": "b_50k",
            "20000": "b_20k",
            "20k": "b_20k",
            "bill_20k": "b_20k",
            "10000": "b_10k",
            "10k": "b_10k",
            "bill_10k": "b_10k",
            "5000": "b_5k",
            "5k": "b_5k",
            "bill_5k": "b_5k",
            "2000": "b_2k",
            "2k": "b_2k",
            "bill_2k": "b_2k",
            "1000": "c_1000",
            "coin_1000": "c_1000",
            "500": "c_500",
            "coin_500": "c_500",
            "200": "c_200",
            "coin_200": "c_200",
            "100": "c_100",
            "coin_100": "c_100",
            "50": "c_50",
            "coin_50": "c_50",
        }
        normalized: dict[str, Any] = {}
        for key, val in data.items():
            str_key = str(key).strip().lower()
            target_key = mapping.get(str_key, key)
            normalized[target_key] = val
        return normalized


# ─── POS Items & Payments ───────────────────────────────────────

class POSItemIn(BaseModel):
    product_id: str | None = None
    sku: str | None = None
    name: str
    unit_measure: str = "UND"
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))
    discount_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))
    vat_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))
    ipo_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))

    @model_validator(mode="after")
    def sync_ids(self) -> Self:
        if not self.product_id and not self.sku:
            raise ValueError("product_id or sku is required")
        if not self.product_id:
            self.product_id = self.sku
        if not self.sku:
            self.sku = self.product_id
        return self


class POSPaymentIn(BaseModel):
    method: Literal["CASH", "CARD", "TRANSFER", "CREDIT"]
    amount: Decimal = Field(gt=Decimal("0"))
    tendered: Decimal | None = None
    change: Decimal | None = None
    reference: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_method(cls, data: Any) -> Any:
        if isinstance(data, dict) and "method" in data:
            m = str(data["method"]).upper().strip()
            mapping = {
                "EFECTIVO": "CASH",
                "DATAFONO": "CARD",
                "TARJETA": "CARD",
                "TRANSFERENCIA": "TRANSFER",
                "CREDITO": "CREDIT",
            }
            data["method"] = mapping.get(m, m)
        return data


class SaleCreateIn(BaseModel):
    branch_id: str
    warehouse_id: str = "WH1"
    session_id: str | None = None
    doc_type: Literal["POS", "FV", "RM"] = "POS"
    client_id: str = "222222222222"
    client_name: str = "CONSUMIDOR FINAL"
    items: list[POSItemIn] = Field(min_length=1)
    payments: list[POSPaymentIn] = Field(default_factory=list)
    notes: str | None = None


class SaleItemOut(BaseModel):
    product_id: str
    sku: str
    name: str
    unit_measure: str = "UND"
    quantity: Decimal
    unit_price: Decimal
    valuni: Decimal
    discount_pct: Decimal
    dctpes: Decimal
    base: Decimal
    vat_pct: Decimal
    ivapes: Decimal
    ipo_pct: Decimal
    ipopes: Decimal
    totdet: Decimal


class SaleOut(BaseModel):
    id: str
    number: str
    consecutive: int
    doc_type: Literal["POS", "FV", "RM"]
    branch_id: str
    warehouse_id: str
    session_id: str | None = None
    client_id: str
    client_name: str
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
    status: Literal["issued", "voided"]
    items: list[SaleItemOut]
    payments: list[POSPaymentIn]
    cashier_user_id: str
    created_at: datetime
    void_reason: str | None = None
    voided_at: datetime | None = None
    voided_by: str | None = None
    notes: str | None = None


class SaleVoidIn(BaseModel):
    reason: str = Field(min_length=1, description="Razón o motivo de anulación")


# ─── Cash Sessions ───────────────────────────────────────────────

class CashSessionOpenIn(BaseModel):
    branch_id: str
    opening_float: Decimal = Field(ge=Decimal("0"))


class CashSessionCloseIn(BaseModel):
    actual_cash: Decimal = Field(ge=Decimal("0"))
    denominations: DenominationCountIn | None = None
    notes: str | None = None


class CashMovementIn(BaseModel):
    type: Literal["IN", "OUT"]
    amount: Decimal = Field(gt=Decimal("0"))
    reason: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_type(cls, data: Any) -> Any:
        if isinstance(data, dict) and "type" in data:
            t = str(data["type"]).upper().strip()
            mapping = {
                "INGRESO": "IN",
                "EGRESO": "OUT",
            }
            data["type"] = mapping.get(t, t)
        return data


class CashMovementOut(BaseModel):
    id: str
    session_id: str
    type: Literal["IN", "OUT"]
    amount: Decimal
    reason: str
    performed_by: str
    created_at: datetime


class CashSessionOut(BaseModel):
    id: str
    branch_id: str
    cashier_user_id: str
    cashier_name: str
    status: Literal["open", "closed"]
    opened_at: datetime
    closed_at: datetime | None = None
    opening_float: Decimal
    cash_sales: Decimal
    cash_in: Decimal
    cash_out: Decimal
    expected_cash: Decimal
    actual_cash: Decimal | None = None
    cash_variance: Decimal | None = None
    denominations: DenominationCountIn | None = None
    notes: str | None = None


# ─── Product Catalog ─────────────────────────────────────────────

class ProductSearchResult(BaseModel):
    sku: str
    name: str
    price: Decimal
    stock: Decimal
    tax_rate: Decimal
    category: str | None = None
    barcode: str | None = None


# ═══ app_* companion tables (erp-transaccional-web slice 1) ═══════════════

from sqlalchemy import (  # noqa: E402
    Column,
    Enum,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)


metadata_erp = MetaData(schema=None)  # default schema (motoshop2024)

app_doc_journal = Table(
    "app_doc_journal",
    metadata_erp,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("codclas", String(4), nullable=False),
    Column("pref", String(8), default=""),
    Column("docnum", Integer, nullable=True),
    Column("status", Enum("PENDING", "COMMITTED", "FAILED", "ANNULLED"), nullable=False),
    Column("doc_type", String(32), default=""),
    Column("tenant", String(32), nullable=False),
    Column("empresa", String(15), default=""),
    Column("actor", String(64), nullable=False),
    Column("request_id", String(64), default=""),
    Column("idempotency_key", String(64), nullable=True),
    Column("error_msg", String(500), nullable=True),
    Column("created_at", TIMESTAMP, nullable=False),
    # F8-001 declares it; the journal stamps it on every state transition.
    Column("updated_at", TIMESTAMP, nullable=True),
    Index("idx_status_created", "status", "created_at"),
    Index("idx_tenant_status", "tenant", "status"),
    Index("idx_codclas_docnum", "codclas", "pref", "docnum"),
    Index("idx_idempotency", "idempotency_key"),
    extend_existing=True,
)

app_idempotency = Table(
    "app_idempotency",
    metadata_erp,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("idempotency_key", String(64), nullable=False),
    Column("doc_type", String(32), default=""),
    Column("tenant", String(32), nullable=False),
    Column("actor", String(64), default=""),
    Column("request_id", String(64), default=""),
    Column("response_json", Text, nullable=True),
    Column("created_at", TIMESTAMP, nullable=False),
    UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
    Index("idx_tenant_created", "tenant", "created_at"),
    extend_existing=True,
)
