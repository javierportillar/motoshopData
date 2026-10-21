"""Unit and integration tests for POS & ERP transactional core.

Covers:
- Line calculation parity against Factura 7322 arithmetic (sgHermes specs).
- Denomination counting.
- Idempotent sale creation (201 on create, 200 on replay with identical body).
- Idempotency key tampering guard (422 when same key used with different payload).
- Multi-tenant isolation (sales and sessions in tenant A are invisible to tenant B).
- Cash session lifecycle: opening, movements, sales accumulation, closing & variance.
- Sale voiding with audit trail (voided_by, void_reason, voided_at) and exact stock reversal.
- Product catalog search by barcode, SKU, and text query.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.erp.calculations import (
    calculate_denominations_total,
    calculate_line_item,
    calculate_sale_totals,
)
from motoshop_api.erp.models import DenominationCountIn, POSItemIn
from motoshop_api.erp.repo import get_erp_repo, reset_erp_repo
from motoshop_api.main import app


@pytest.fixture(autouse=True)
def _clean_erp_repo():
    """Resets in-memory ERP repository between tests."""
    reset_erp_repo()
    yield


@pytest.fixture()
def auth_user() -> User:
    return User(
        username="vendedor1",
        hashed_password="test-hashed-password",
        email="vendedor1@motoshop.local",
        role="vendedor",
        tenants_allowed=["motoshop", "masvital"],
        source="legacy",
        allowed_modules=None,
    )


@pytest.fixture()
def client(auth_user: User) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: auth_user
    c = TestClient(
        app,
        raise_server_exceptions=False,
        headers={"X-Tenant": "motoshop"},
    )
    yield c
    app.dependency_overrides.pop(get_current_user, None)


# ─── 1. Factura 7322 & Line Calculation Parity Tests ─────────────

def test_factura_7322_arithmetic_parity():
    """Verifies Factura 7322 arithmetic: 100.000 COP, 1 unit, 0% VAT, 0% discount."""
    item = POSItemIn(
        product_id="PROD-7322",
        name="Repuesto Muestra Factura 7322",
        unit_price=Decimal("100000.00"),
        quantity=Decimal("1"),
        discount_pct=Decimal("0"),
        vat_pct=Decimal("0"),
        ipo_pct=Decimal("0"),
    )

    line = calculate_line_item(item)

    assert line.valuni == Decimal("100000.00")
    assert line.dctpes == Decimal("0.00")
    assert line.base == Decimal("100000.00")
    assert line.ivapes == Decimal("0.00")
    assert line.ipopes == Decimal("0.00")
    assert line.totdet == Decimal("100000.00")

    totals = calculate_sale_totals([line])
    assert totals["subtotal"] == Decimal("100000.00")
    assert totals["discount_total"] == Decimal("0.00")
    assert totals["tax_total"] == Decimal("0.00")
    assert totals["grand_total"] == Decimal("100000.00")


def test_complex_line_calculation_with_discount_and_vat():
    """Verifies line calculations with discount and VAT:

    valuni = 28000, qty = 2, discount_pct = 5%, vat_pct = 19%
    dctpes = round(28000 * 0.05, 2) = 1400.00
    base = 28000 - 1400 = 26600.00
    ivapes = round(26600 * 0.19, 2) = 5054.00
    unit_final = 28000 - 1400 + 5054 = 31654.00
    totdet = round(31654.00 * 2, 2) = 63308.00
    """
    line = calculate_line_item(
        unit_price=Decimal("28000.00"),
        quantity=Decimal("2"),
        discount_pct=Decimal("5"),
        vat_pct=Decimal("19"),
        product_id="CAS-ACT-20W50",
        name="Aceite Castrol Actevo",
    )

    assert line.valuni == Decimal("28000.00")
    assert line.dctpes == Decimal("1400.00")
    assert line.base == Decimal("26600.00")
    assert line.ivapes == Decimal("5054.00")
    assert line.ipopes == Decimal("0.00")
    assert line.totdet == Decimal("63308.00")

    totals = calculate_sale_totals([line])
    assert totals["subtotal"] == Decimal("56000.00")
    assert totals["discount_total"] == Decimal("28000.00") * Decimal("0.05") * Decimal("2")
    assert totals["vat_total"] == Decimal("10108.00")
    assert totals["grand_total"] == Decimal("63308.00")


def test_denomination_calculation():
    """Verifies cash breakdown total calculation for Colombian currency."""
    denom = DenominationCountIn(
        b_100k=2,  # 200,000
        b_50k=1,   # 50,000
        b_20k=3,   # 60,000
        c_1000=5,  # 5,000
        c_500=4,   # 2,000
    )
    total = calculate_denominations_total(denom)
    assert total == Decimal("317000.00")

    # Flexible dict format
    total_dict = calculate_denominations_total({"100000": 1, "50000": 2, "500": 2})
    assert total_dict == Decimal("201000.00")


# ─── 2. Idempotent Sale Creation & Hardened Key Guard ─────────────

def test_idempotent_sale_creation(client: TestClient):
    """Sending the same Idempotency-Key returns 201 on first call and 200 on second call with identical body."""
    key = str(uuid.uuid4())
    headers = {"Idempotency-Key": key}

    payload = {
        "branch_id": "B01",
        "warehouse_id": "WH1",
        "doc_type": "POS",
        "client_id": "222222222222",
        "client_name": "CONSUMIDOR FINAL",
        "items": [
            {
                "product_id": "CAS-ACT-20W50",
                "name": "Aceite Castrol Actevo 20W-50",
                "unit_measure": "UND",
                "quantity": 1,
                "unit_price": 28000,
                "discount_pct": 0,
                "vat_pct": 19,
                "ipo_pct": 0,
            }
        ],
        "payments": [
            {
                "method": "CASH",
                "amount": 33320,
                "tendered": 50000,
                "change": 16680,
            }
        ],
    }

    # First request -> 201 Created
    res1 = client.post("/api/erp/pos/sales", json=payload, headers=headers)
    assert res1.status_code == 201, res1.text
    body1 = res1.json()
    assert body1["id"] == key
    assert body1["status"] == "issued"
    assert body1["consecutive"] == 1
    assert body1["number"] == "POS-000001"
    assert float(body1["grand_total"]) == 33320.00
    assert body1["cashier_user_id"] == "vendedor1"

    # Second request with SAME idempotency key -> 200 OK with identical body
    res2 = client.post("/api/erp/pos/sales", json=payload, headers=headers)
    assert res2.status_code == 200, res2.text
    body2 = res2.json()
    assert body2 == body1


def test_idempotent_sale_rejects_altered_payload(client: TestClient):
    """Reusing the same Idempotency-Key with a different payload raises HTTP 422."""
    key = str(uuid.uuid4())
    headers = {"Idempotency-Key": key}

    payload = {
        "branch_id": "B01",
        "doc_type": "POS",
        "items": [
            {
                "product_id": "CAS-ACT-20W50",
                "name": "Aceite Castrol",
                "quantity": 1,
                "unit_price": 28000,
            }
        ],
    }

    res1 = client.post("/api/erp/pos/sales", json=payload, headers=headers)
    assert res1.status_code == 201

    # Re-send with modified quantity (altered payload)
    altered_payload = {
        **payload,
        "items": [
            {
                "product_id": "CAS-ACT-20W50",
                "name": "Aceite Castrol",
                "quantity": 2,
                "unit_price": 28000,
            }
        ],
    }
    res_tampered = client.post("/api/erp/pos/sales", json=altered_payload, headers=headers)
    assert res_tampered.status_code == 422
    assert "different request payload" in res_tampered.text


def test_idempotency_key_validation(client: TestClient):
    """Rejects missing or invalid UUID v4 Idempotency-Key header."""
    payload = {
        "branch_id": "B01",
        "items": [
            {
                "product_id": "CAS-ACT-20W50",
                "name": "Aceite Castrol",
                "quantity": 1,
                "unit_price": 28000,
            }
        ],
    }

    # Missing header -> 422
    res_missing = client.post("/api/erp/pos/sales", json=payload)
    assert res_missing.status_code == 422

    # Invalid UUID v4 -> 422
    res_invalid = client.post(
        "/api/erp/pos/sales",
        json=payload,
        headers={"Idempotency-Key": "not-a-uuid"},
    )
    assert res_invalid.status_code == 422


# ─── 3. Multi-Tenant Isolation ─────────────

def test_multi_tenant_sales_and_session_isolation(client: TestClient):
    """Verifies complete multi-tenant isolation between 'motoshop' and 'masvital'."""
    key_moto = str(uuid.uuid4())
    payload_moto = {
        "branch_id": "B01",
        "doc_type": "POS",
        "items": [
            {"product_id": "CAS-ACT-20W50", "name": "Castrol", "quantity": 1, "unit_price": 28000}
        ],
    }

    # 1. Create sale in motoshop
    res_m = client.post(
        "/api/erp/pos/sales",
        json=payload_moto,
        headers={"Idempotency-Key": key_moto, "X-Tenant": "motoshop"},
    )
    assert res_m.status_code == 201
    sale_moto_id = res_m.json()["id"]

    # 2. List in motoshop -> visible
    res_list_m = client.get("/api/erp/pos/sales", headers={"X-Tenant": "motoshop"})
    assert any(s["id"] == sale_moto_id for s in res_list_m.json())

    # 3. List in masvital -> NOT visible
    res_list_mv = client.get("/api/erp/pos/sales", headers={"X-Tenant": "masvital"})
    assert res_list_mv.status_code == 200
    assert not any(s["id"] == sale_moto_id for s in res_list_mv.json())

    # 4. Direct GET in masvital -> 404
    res_get_mv = client.get(f"/api/erp/pos/sales/{sale_moto_id}", headers={"X-Tenant": "masvital"})
    assert res_get_mv.status_code == 404

    # 5. Consecutive counters are isolated per tenant
    key_mv = str(uuid.uuid4())
    payload_mv = {
        "branch_id": "MV-01",
        "doc_type": "POS",
        "items": [
            {"product_id": "PROD-7322", "name": "Sample", "quantity": 1, "unit_price": 50000}
        ],
    }
    res_mv = client.post(
        "/api/erp/pos/sales",
        json=payload_mv,
        headers={"Idempotency-Key": key_mv, "X-Tenant": "masvital"},
    )
    assert res_mv.status_code == 201
    assert res_mv.json()["consecutive"] == 1
    assert res_mv.json()["number"] == "POS-000001"


# ─── 4. Cash Session Lifecycle & Sales Accumulation ─────────────

def test_cash_session_lifecycle(client: TestClient):
    """Tests register opening, movements, sales accumulation, and closing with variance."""
    # 1. Open session
    open_payload = {
        "branch_id": "B01",
        "opening_float": 150000,
    }
    res_open = client.post("/api/erp/pos/sessions/open", json=open_payload)
    assert res_open.status_code == 201, res_open.text
    session = res_open.json()
    session_id = session["id"]
    assert session["status"] == "open"
    assert session["cashier_user_id"] == "vendedor1"
    assert float(session["opening_float"]) == 150000.00
    assert float(session["expected_cash"]) == 150000.00

    # 2. Duplicate open should fail
    res_dup = client.post("/api/erp/pos/sessions/open", json=open_payload)
    assert res_dup.status_code == 400

    # 3. Get current session
    res_curr = client.get("/api/erp/pos/sessions/current")
    assert res_curr.status_code == 200
    assert res_curr.json()["id"] == session_id

    # 4. Add cash IN movement (50,000)
    mov_in_payload = {
        "type": "IN",
        "amount": 50000,
        "reason": "Base adicional de sencillo",
    }
    res_mov_in = client.post(f"/api/erp/pos/sessions/{session_id}/movements", json=mov_in_payload)
    assert res_mov_in.status_code == 201
    assert res_mov_in.json()["type"] == "IN"
    assert res_mov_in.json()["performed_by"] == "vendedor1"

    # 5. Add cash OUT movement (20,000)
    mov_out_payload = {
        "type": "OUT",
        "amount": 20000,
        "reason": "Pago servicio de mensajería",
    }
    res_mov_out = client.post(f"/api/erp/pos/sessions/{session_id}/movements", json=mov_out_payload)
    assert res_mov_out.status_code == 201

    # 6. Make a cash sale linked to this session
    sale_key = str(uuid.uuid4())
    sale_payload = {
        "branch_id": "B01",
        "session_id": session_id,
        "doc_type": "POS",
        "items": [
            {
                "product_id": "PROD-7322",
                "name": "Repuesto Factura 7322",
                "quantity": 1,
                "unit_price": 100000,
            }
        ],
        "payments": [
            {
                "method": "CASH",
                "amount": 100000,
            }
        ],
    }
    res_sale = client.post("/api/erp/pos/sales", json=sale_payload, headers={"Idempotency-Key": sale_key})
    assert res_sale.status_code == 201

    # 7. Make a card sale (should not increase cash sales)
    card_key = str(uuid.uuid4())
    card_sale_payload = {
        "branch_id": "B01",
        "session_id": session_id,
        "doc_type": "POS",
        "items": [
            {
                "product_id": "PAS-DEL-200NS",
                "name": "Pastillas de Freno",
                "quantity": 1,
                "unit_price": 35000,
            }
        ],
        "payments": [
            {
                "method": "CARD",
                "amount": 35000,
                "reference": "AUTH-9999",
            }
        ],
    }
    res_card = client.post("/api/erp/pos/sales", json=card_sale_payload, headers={"Idempotency-Key": card_key})
    assert res_card.status_code == 201

    # Verify session before closing:
    # expected = opening(150k) + in(50k) - out(20k) + cash_sales(100k) = 280,000
    res_check = client.get("/api/erp/pos/sessions/current")
    curr = res_check.json()
    assert float(curr["opening_float"]) == 150000.00
    assert float(curr["cash_in"]) == 50000.00
    assert float(curr["cash_out"]) == 20000.00
    assert float(curr["cash_sales"]) == 100000.00
    assert float(curr["expected_cash"]) == 280000.00

    # 8. Close session with counted cash = 282,000 (+2,000 variance)
    close_payload = {
        "actual_cash": 282000,
        "denominations": {
            "b_100k": 2,
            "b_50k": 1,
            "b_20k": 1,
            "b_10k": 1,
            "c_1000": 2,
        },
        "notes": "Sobrante de $2.000 por propina voluntaria",
    }
    res_close = client.post(f"/api/erp/pos/sessions/{session_id}/close", json=close_payload)
    assert res_close.status_code == 200
    closed = res_close.json()
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None
    assert float(closed["expected_cash"]) == 280000.00
    assert float(closed["actual_cash"]) == 282000.00
    assert float(closed["cash_variance"]) == 2000.00

    # Subsequent current session check -> 404
    res_after = client.get("/api/erp/pos/sessions/current")
    assert res_after.status_code == 404


# ─── 5. Voiding a Sale & Stock Reversal ─────────────

def test_void_sale_with_audit_trail_and_stock_restoration(client: TestClient):
    """Voiding a sale records voided_by and exactly reverses stock (sgHermes behavior)."""
    repo = get_erp_repo()
    prods = repo._ensure_tenant_products("motoshop")
    initial_stock = prods["CAS-ACT-20W50"].stock

    key = str(uuid.uuid4())
    payload = {
        "branch_id": "B01",
        "doc_type": "POS",
        "items": [
            {
                "product_id": "CAS-ACT-20W50",
                "name": "Aceite Castrol",
                "quantity": 2,
                "unit_price": 28000,
            }
        ],
        "payments": [{"method": "CASH", "amount": 56000}],
    }
    res_sale = client.post("/api/erp/pos/sales", json=payload, headers={"Idempotency-Key": key})
    assert res_sale.status_code == 201
    sale_id = res_sale.json()["id"]

    # Stock should be decremented by 2
    assert prods["CAS-ACT-20W50"].stock == initial_stock - Decimal("2.00")

    # Void the sale
    void_payload = {"reason": "Cliente solicitó garantía y devolución inmediata"}
    res_void = client.post(f"/api/erp/pos/sales/{sale_id}/void", json=void_payload)
    assert res_void.status_code == 200
    voided = res_void.json()
    assert voided["status"] == "voided"
    assert voided["void_reason"] == "Cliente solicitó garantía y devolución inmediata"
    assert voided["voided_at"] is not None
    assert voided["voided_by"] == "vendedor1"

    # Stock restored back exactly to initial
    assert prods["CAS-ACT-20W50"].stock == initial_stock

    # Re-voiding should return 400
    res_revoid = client.post(f"/api/erp/pos/sales/{sale_id}/void", json=void_payload)
    assert res_revoid.status_code == 400

    # Voiding unknown sale should return 404
    res_404 = client.post("/api/erp/pos/sales/unknown-id/void", json=void_payload)
    assert res_404.status_code == 404


def test_void_sale_preserves_negative_stock_exactness(client: TestClient):
    """Selling more than available stock sets stock negative and voiding restores original."""
    repo = get_erp_repo()
    prods = repo._ensure_tenant_products("motoshop")
    # Set known small stock: 2 units
    prods["PAS-DEL-200NS"].stock = Decimal("2.00")

    key = str(uuid.uuid4())
    payload = {
        "branch_id": "B01",
        "doc_type": "POS",
        "items": [
            {
                "product_id": "PAS-DEL-200NS",
                "name": "Pastillas",
                "quantity": 5,
                "unit_price": 35000,
            }
        ],
    }
    res_sale = client.post("/api/erp/pos/sales", json=payload, headers={"Idempotency-Key": key})
    assert res_sale.status_code == 201
    sale_id = res_sale.json()["id"]

    # Stock is negative: 2 - 5 = -3
    assert prods["PAS-DEL-200NS"].stock == Decimal("-3.00")

    # Void sale restores to exactly 2
    res_void = client.post(f"/api/erp/pos/sales/{sale_id}/void", json={"reason": "Cancelación"})
    assert res_void.status_code == 200
    assert prods["PAS-DEL-200NS"].stock == Decimal("2.00")


# ─── 6. Product Catalog Search Tests ─────────────

def test_product_catalog_search(client: TestClient):
    """Tests catalog search by barcode, SKU, and text query."""
    # Search by text
    res_text = client.get("/api/erp/catalog/products/search?q=Castrol")
    assert res_text.status_code == 200
    products = res_text.json()
    assert len(products) >= 1
    assert any(p["sku"] == "CAS-ACT-20W50" for p in products)

    # Search by barcode
    res_barcode = client.get("/api/erp/catalog/products/search?q=7701234567890")
    assert res_barcode.status_code == 200
    p_barcode = res_barcode.json()
    assert len(p_barcode) == 1
    assert p_barcode[0]["sku"] == "CAS-ACT-20W50"

    # Search by Factura 7322 sample item
    res_7322 = client.get("/api/erp/catalog/products/search?q=7322")
    assert res_7322.status_code == 200
    assert any(p["sku"] == "PROD-7322" for p in res_7322.json())

    # Full catalog retrieval
    res_all = client.get("/api/erp/catalog/products/search")
    assert res_all.status_code == 200
    assert len(res_all.json()) >= 10

    # Also test /api/pos/products endpoint used by the POS workstation UI
    res_pos = client.get("/api/pos/products?q=Castrol")
    assert res_pos.status_code == 200
    assert any(p["sku"] == "CAS-ACT-20W50" for p in res_pos.json())



# ─── 7. Sales Query and Detail Endpoints ─────────────

def test_list_and_get_sale(client: TestClient):
    """Tests sales listing, filtering by status, and individual sale retrieval."""
    key = str(uuid.uuid4())
    payload = {
        "branch_id": "B01",
        "doc_type": "POS",
        "items": [
            {
                "product_id": "MOT-7100-10W40",
                "name": "Aceite Motul 7100",
                "quantity": 1,
                "unit_price": 68000,
            }
        ],
    }
    res_create = client.post("/api/erp/pos/sales", json=payload, headers={"Idempotency-Key": key})
    assert res_create.status_code == 201
    sale_id = res_create.json()["id"]

    # Get single sale
    res_get = client.get(f"/api/erp/pos/sales/{sale_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == sale_id

    # List sales
    res_list = client.get("/api/erp/pos/sales?status=issued")
    assert res_list.status_code == 200
    items = res_list.json()
    assert any(s["id"] == sale_id for s in items)


def test_masvital_bulk_fractional_sale_with_decimal_quantity(client: TestClient):
    """Verifies that fractional quantities (e.g. 21.428 grams of almonds at $70 COP)
    are supported with exact Decimal precision and without integer truncation.
    """
    key = str(uuid.uuid4())
    payload = {
        "branch_id": "B01",
        "doc_type": "POS",
        "client_name": "CLIENTE MASVITAL",
        "items": [
            {
                "product_id": "OLAM001",
                "name": "Almendra Americana",
                "unit_measure": "GR",
                "quantity": "21.428",
                "unit_price": "70.00",
                "discount_pct": "0.0",
                "vat_pct": "0.0",
            }
        ],
        "payments": [
            {
                "method": "CASH",
                "amount": "1499.96",
            }
        ],
    }
    res = client.post("/api/erp/pos/sales", json=payload, headers={"Idempotency-Key": key})
    assert res.status_code == 201
    sale = res.json()
    assert Decimal(str(sale["items"][0]["quantity"])) == Decimal("21.428")
    assert Decimal(str(sale["items"][0]["valuni"])) == Decimal("70.00")
    assert Decimal(str(sale["items"][0]["totdet"])) == Decimal("1499.96")
    assert Decimal(str(sale["grand_total"])) == Decimal("1499.96")
