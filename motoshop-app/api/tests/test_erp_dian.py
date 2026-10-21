"""Comprehensive unit and integration test suite for DIAN Electronic Invoicing.

Spec: erp-dian-einvoicing (Slice 6).
Tests:
- Adapter produces valid CUFE and QR format.
- Successful submission transitions to ACCEPTED with XML stub.
- Idempotency: retry of accepted sale returns existing CUFE without re-issuing.
- Transient failure increments retry count with exponential backoff and marks FAILED after max attempts.
- Multi-tenant isolation for DIAN queue and documents.
- Annulment guard: attempting to void an invoice already reported as ACCEPTED (estfele=1)
  requires DIAN Credit Note handling.
- Role-gated retry endpoint (admin/gerente allowed, vendedor forbidden).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User
from motoshop_api.erp.dian import (
    DianDocOut,
    DianStatusEnum,
    DianStubAdapter,
    compute_pseudo_cufe,
    generate_qr_url,
    get_dian_queue,
    reset_dian_queue,
)
from motoshop_api.erp.models import POSItemIn, SaleCreateIn
from motoshop_api.erp.repo import get_erp_repo, reset_erp_repo
from motoshop_api.main import app


@pytest.fixture(autouse=True)
def _clean_environment():
    """Resets ERP repo and DIAN queue before each test."""
    reset_erp_repo()
    reset_dian_queue()
    yield
    reset_erp_repo()
    reset_dian_queue()


@pytest.fixture()
def vendedor_user() -> User:
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
def admin_user() -> User:
    return User(
        username="admin1",
        hashed_password="test-hashed-password",
        email="admin@motoshop.local",
        role="admin",
        tenants_allowed=["motoshop", "masvital"],
        source="legacy",
        allowed_modules=None,
    )


@pytest.fixture()
def client(vendedor_user: User) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: vendedor_user
    c = TestClient(
        app,
        raise_server_exceptions=False,
        headers={"X-Tenant": "motoshop"},
    )
    yield c
    app.dependency_overrides.clear()


def _create_sample_sale(client: TestClient, tenant: str = "motoshop") -> dict:
    """Helper to create a sale via API."""
    sale_payload = {
        "doc_type": "FV",
        "branch_id": "PRINCIPAL",
        "warehouse_id": "B01",
        "client_id": "123456789",
        "client_name": "CLIENTE PRUEBA DIAN",
        "items": [
            {
                "sku": "CAS-ACT-20W50",
                "name": "Aceite Castrol Actevo 20W-50",
                "quantity": "2.00",
                "unit_price": "28000.00",
                "discount_pct": "0.00",
                "vat_pct": "19.00",
                "ipo_pct": "0.00",
            }
        ],
        "payments": [
            {
                "method": "CASH",
                "amount": "66640.00",
            }
        ],
    }
    idem_key = str(uuid.uuid4())
    headers = {"X-Tenant": tenant, "Idempotency-Key": idem_key}
    res = client.post("/api/erp/pos/sales", json=sale_payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ─── 1. Adapter Contract & Deterministic Pseudo-CUFE Tests ───────


def test_dian_stub_adapter_cufe_and_qr_generation():
    """Validates that CUFE is a deterministic 96-char hex string (SHA-384) and QR URL is valid."""
    adapter = DianStubAdapter()

    cufe1 = compute_pseudo_cufe("FV-1001", "2026-10-21", "66640.00", "900123456")
    cufe2 = compute_pseudo_cufe("FV-1001", "2026-10-21", "66640.00", "900123456")
    cufe_diff = compute_pseudo_cufe("FV-1002", "2026-10-21", "66640.00", "900123456")

    # 96 hex characters for SHA-384
    assert len(cufe1) == 96
    assert all(c in "0123456789abcdef" for c in cufe1)
    # Determinism
    assert cufe1 == cufe2
    assert cufe1 != cufe_diff

    # QR format
    qr_url = generate_qr_url(cufe1)
    assert qr_url == f"https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={cufe1}"

    # Build payload
    doc = {
        "id": "sale-1",
        "number": "FV-1001",
        "created_at": "2026-10-21T10:00:00Z",
        "grand_total": Decimal("66640.00"),
        "tenant_nit": "900123456",
        "client_id": "123456789",
        "client_name": "CLIENTE PRUEBA",
    }
    payload = adapter.build_payload(doc)
    assert payload["sale_id"] == "sale-1"
    assert payload["doc_number"] == "FV-1001"
    assert payload["cufe"] == cufe1
    assert payload["qr_url"] == qr_url

    # Instant send
    response = adapter.send_invoice(payload)
    assert response["status"] == "ACCEPTED"
    assert response["estfele"] == 1
    assert response["cufe"] == cufe1
    assert response["qr_url"] == qr_url
    assert "<Invoice>" in response["xml"]
    assert f"<UUID schemeName=\"CUFE-SHA384\">{cufe1}</UUID>" in response["xml"]
    assert "<Status>ACCEPTED</Status>" in response["xml"]


# ─── 2. Successful Submission and Transitions ───────────────────


def test_successful_dian_submission(client: TestClient):
    """Enqueuing and processing a sale transitions it to ACCEPTED state."""
    sale = _create_sample_sale(client)
    sale_id = sale["id"]

    res = client.post(f"/api/erp/dian/enqueue/{sale_id}")
    assert res.status_code == 201
    data = res.json()

    assert data["sale_id"] == sale_id
    assert data["status"] == "ACCEPTED"
    assert data["estfele"] == 1
    assert len(data["cufe"]) == 96
    assert data["qr_url"].startswith("https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=")
    assert data["accepted_at"] is not None
    assert data["error_message"] is None

    # Query document endpoint
    res_doc = client.get(f"/api/erp/dian/document/{sale_id}")
    assert res_doc.status_code == 200
    doc_data = res_doc.json()
    assert doc_data["cufe"] == data["cufe"]
    assert doc_data["status"] == "ACCEPTED"


# ─── 3. Idempotency Guard Tests ─────────────────────────────────


def test_idempotent_retry_of_accepted_sale(client: TestClient):
    """Retrying or re-enqueuing an already accepted sale returns existing CUFE without re-issuing."""
    sale = _create_sample_sale(client)
    sale_id = sale["id"]

    # First enqueue -> ACCEPTED
    res1 = client.post(f"/api/erp/dian/enqueue/{sale_id}")
    assert res1.status_code == 201
    data1 = res1.json()
    cufe1 = data1["cufe"]
    accepted_at1 = data1["accepted_at"]

    # Re-enqueue same sale -> returns same accepted doc without re-issuing
    res2 = client.post(f"/api/erp/dian/enqueue/{sale_id}")
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["cufe"] == cufe1
    assert data2["accepted_at"] == accepted_at1
    assert data2["status"] == "ACCEPTED"

    # Queue retry endpoint as admin
    app.dependency_overrides[get_current_user] = lambda: User(
        username="admin1",
        email="admin@motoshop.local",
        hashed_password="pw",
        role="admin",
        tenants_allowed=["motoshop"],
        source="legacy",
    )
    res_retry = client.post(f"/api/erp/dian/retry/{sale_id}", json={"sale_id": sale_id, "force": True})
    assert res_retry.status_code == 200
    data_retry = res_retry.json()
    assert data_retry["cufe"] == cufe1
    assert data_retry["accepted_at"] == accepted_at1


# ─── 4. Transient Failures and Max Retries ────────────────────────


def test_transient_failures_increment_retry_count_and_reach_failed():
    """Transient failures increment retry count and transition to FAILED after 5 attempts."""
    queue = get_dian_queue()
    adapter = queue.adapter
    assert isinstance(adapter, DianStubAdapter)

    # Configure 5 transient failures
    adapter.configure_simulation(
        transient_failures=5,
        transient_error="DIAN HTTP 503 upstream timeout",
    )

    sale_dummy = {
        "id": "sale-transient-test",
        "number": "FV-9999",
        "grand_total": Decimal("100000.00"),
        "created_at": "2026-10-21T12:00:00Z",
    }
    doc = queue.enqueue_sale(sale_dummy, tenant_id="motoshop")
    assert doc.status == DianStatusEnum.PENDING
    assert doc.retry_count == 0

    # Attempts 1 through 4 should increment retry_count and stay PENDING
    for attempt in range(1, 5):
        queue.process_queue(tenant_id="motoshop", ignore_backoff=True)
        current = queue.get_dian_status_for_sale("sale-transient-test", "motoshop")
        assert current is not None
        assert current.status == DianStatusEnum.PENDING
        assert current.retry_count == attempt
        assert current.error_message == "DIAN HTTP 503 upstream timeout"

    # 5th attempt -> reaches MAX_RETRIES (5) and marks FAILED
    queue.process_queue(tenant_id="motoshop", ignore_backoff=True)
    final_doc = queue.get_dian_status_for_sale("sale-transient-test", "motoshop")
    assert final_doc is not None
    assert final_doc.status == DianStatusEnum.FAILED
    assert final_doc.retry_count == 5
    assert final_doc.estfele == 0
    assert "503 upstream timeout" in (final_doc.error_message or "")

    # Manual retry with force=True after adapter recovers -> transitions to ACCEPTED
    adapter.reset_simulation()
    retried_doc = queue.retry_sale("sale-transient-test", "motoshop", force=True)
    assert retried_doc.status == DianStatusEnum.ACCEPTED
    assert retried_doc.estfele == 1
    assert retried_doc.cufe is not None


# ─── 5. Multi-Tenant Isolation Tests ─────────────────────────────


def test_multi_tenant_dian_isolation(client: TestClient):
    """DIAN documents and queues are isolated per tenant."""
    # Create and enqueue a sale under tenant 'motoshop'
    sale = _create_sample_sale(client, tenant="motoshop")
    sale_id = sale["id"]
    res_enqueue = client.post(f"/api/erp/dian/enqueue/{sale_id}", headers={"X-Tenant": "motoshop"})
    assert res_enqueue.status_code == 201

    # Check status list for 'motoshop'
    res_status_moto = client.get("/api/erp/dian/status", headers={"X-Tenant": "motoshop"})
    assert res_status_moto.status_code == 200
    moto_list = res_status_moto.json()
    assert moto_list["total"] >= 1
    assert any(d["sale_id"] == sale_id for d in moto_list["documents"])

    # Check status list for tenant 'masvital' -> completely empty
    res_status_mas = client.get("/api/erp/dian/status", headers={"X-Tenant": "masvital"})
    assert res_status_mas.status_code == 200
    mas_list = res_status_mas.json()
    assert mas_list["total"] == 0
    assert len(mas_list["documents"]) == 0

    # Cross-tenant document query -> returns 404
    res_cross = client.get(f"/api/erp/dian/document/{sale_id}", headers={"X-Tenant": "masvital"})
    assert res_cross.status_code == 404


# ─── 6. Annulment Guard (estfele=1 blocks direct voiding) ─────────


def test_annulment_guard_blocks_voiding_accepted_invoice(client: TestClient):
    """An invoice accepted by DIAN (estfele=1) cannot be voided directly; requires Credit Note."""
    # Create sale
    sale = _create_sample_sale(client)
    sale_id = sale["id"]

    # Enqueue in DIAN -> becomes ACCEPTED
    res_dian = client.post(f"/api/erp/dian/enqueue/{sale_id}")
    assert res_dian.status_code == 201
    assert res_dian.json()["status"] == "ACCEPTED"

    # Attempt to void the accepted sale
    void_payload = {"reason": "Error en digitación de referencia"}
    res_void = client.post(f"/api/erp/pos/sales/{sale_id}/void", json=void_payload)

    # Must be rejected with HTTP 400 mentioning estfele=1 and Nota Crédito
    assert res_void.status_code == 400
    error_detail = res_void.json()["detail"]
    assert "estfele=1" in error_detail
    assert "Nota Crédito" in error_detail

    # Verify that the sale is NOT voided in the repository
    res_get = client.get(f"/api/erp/pos/sales/{sale_id}")
    assert res_get.status_code == 200
    assert res_get.json()["status"] == "issued"


def test_annulment_of_pending_dian_sale_cancels_queue_item(client: TestClient):
    """An invoice pending or failed in DIAN queue CAN be voided, marking queue item CANCELLED."""
    queue = get_dian_queue()
    adapter = queue.adapter
    assert isinstance(adapter, DianStubAdapter)
    adapter.configure_simulation(transient_failures=5)

    sale = _create_sample_sale(client)
    sale_id = sale["id"]

    # Enqueue -> remains PENDING due to transient failure simulation
    queue.enqueue_sale(sale, tenant_id="motoshop")
    queue.process_queue(tenant_id="motoshop", ignore_backoff=True)
    doc_before = queue.get_dian_status_for_sale(sale_id, "motoshop")
    assert doc_before is not None
    assert doc_before.status == DianStatusEnum.PENDING

    # Voiding should succeed
    void_payload = {"reason": "Cancelación antes de transmisión DIAN"}
    res_void = client.post(f"/api/erp/pos/sales/{sale_id}/void", json=void_payload)
    assert res_void.status_code == 200
    assert res_void.json()["status"] == "voided"

    # DIAN queue item should now be CANCELLED
    doc_after = queue.get_dian_status_for_sale(sale_id, "motoshop")
    assert doc_after is not None
    assert doc_after.status == DianStatusEnum.CANCELLED


# ─── 7. Role Gating on Retry Endpoint ────────────────────────────


def test_role_gating_on_retry_endpoint(client: TestClient, vendedor_user: User, admin_user: User):
    """Retry endpoint requires admin or gerente role; vendedor is forbidden."""
    sale = _create_sample_sale(client)
    sale_id = sale["id"]

    # As vendedor -> 403 Forbidden
    app.dependency_overrides[get_current_user] = lambda: vendedor_user
    res_forbidden = client.post(f"/api/erp/dian/retry/{sale_id}")
    assert res_forbidden.status_code == 403
    assert "no tiene permiso" in res_forbidden.json()["detail"]

    # As admin -> 200 OK (idempotent replay of accepted doc or retry of pending/failed)
    # First enqueue it
    client.post(f"/api/erp/dian/enqueue/{sale_id}")
    app.dependency_overrides[get_current_user] = lambda: admin_user
    res_admin = client.post(f"/api/erp/dian/retry/{sale_id}")
    assert res_admin.status_code == 200
    assert res_admin.json()["status"] == "ACCEPTED"


# ─── 8. Summary Status List Endpoint ─────────────────────────────


def test_dian_status_list_metrics(client: TestClient):
    """GET /api/erp/dian/status aggregates summary counts correctly."""
    # Create two sales
    sale1 = _create_sample_sale(client)
    sale2 = _create_sample_sale(client)

    client.post(f"/api/erp/dian/enqueue/{sale1['id']}")
    client.post(f"/api/erp/dian/enqueue/{sale2['id']}")

    res = client.get("/api/erp/dian/status")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert data["accepted"] == 2
    assert data["pending"] == 0
    assert data["failed"] == 0
    assert len(data["documents"]) == 2
