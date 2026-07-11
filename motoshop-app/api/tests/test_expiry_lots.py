"""Contract tests for the manual MasVital expiry-lot API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from motoshop_api.auth.hash import hash_password
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.expiry.repo import (
    _raise_for_response,
    get_expiry_lots_repo,
    idempotency_fingerprint,
)
from motoshop_api.expiry.schemas import LotAdjustmentCreate, ReceiptCreate
from motoshop_api.main import app
from motoshop_api.tenants import Tenant, _tenants_cache


class FakeExpiryLotsRepo:
    """Stateful fake that enforces the production lot invariants."""

    def __init__(self) -> None:
        self.lots: dict[UUID, dict] = {}
        self.idempotency: dict[tuple[str, UUID], tuple[str, str, dict]] = {}
        self.last_tenant: str | None = None
        self._lock = Lock()

    def clear(self) -> None:
        self.lots.clear()
        self.idempotency.clear()
        self.last_tenant = None

    def list_lots(
        self,
        *,
        tenant: str,
        product_sku: str | None,
        expires_before: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        self.last_tenant = tenant
        rows = [lot for lot in self.lots.values() if lot["tenant"] == tenant]
        if product_sku:
            rows = [lot for lot in rows if lot["product_sku"] == product_sku]
        if expires_before:
            rows = [lot for lot in rows if lot["expires_on"] <= expires_before]
        rows.sort(key=lambda lot: (lot["expires_on"], str(lot["id"])))
        return rows[offset : offset + limit], len(rows)

    def list_alerts(self, *, tenant: str, expires_before: date) -> list[dict]:
        self.last_tenant = tenant
        return sorted(
            [
                lot
                for lot in self.lots.values()
                if lot["tenant"] == tenant
                and lot["remaining_quantity"] > 0
                and lot["expires_on"] <= expires_before
            ],
            key=lambda lot: lot["expires_on"],
        )

    def create_receipt(
        self,
        *,
        tenant: str,
        actor: str,
        payload: ReceiptCreate,
        idempotency_key: UUID,
    ) -> dict:
        with self._lock:
            return self._create_receipt(
                tenant=tenant,
                actor=actor,
                payload=payload,
                idempotency_key=idempotency_key,
            )

    def _create_receipt(
        self,
        *,
        tenant: str,
        actor: str,
        payload: ReceiptCreate,
        idempotency_key: UUID,
    ) -> dict:
        self.last_tenant = tenant
        request = {
            "p_tenant": tenant,
            "p_product_sku": payload.product_sku,
            "p_purchase_order_ref": payload.purchase_order_ref,
            "p_lot_code": payload.lot_code,
            "p_expires_on": payload.expires_on.isoformat(),
            "p_received_on": payload.received_on.isoformat() if payload.received_on else None,
            "p_received_quantity": str(payload.received_quantity),
            "p_supplier": payload.supplier,
            "p_notes": payload.notes,
            "p_created_by": actor,
            "p_idempotency_key": str(idempotency_key),
        }
        fingerprint = idempotency_fingerprint("receipt", request)
        existing = self.idempotency.get((tenant, idempotency_key))
        if existing:
            operation, existing_fingerprint, lot = existing
            if operation != "receipt" or existing_fingerprint != fingerprint:
                raise HTTPException(status_code=422, detail="Idempotency key payload mismatch")
            return {"lot": lot, "replayed": True}
        now = datetime.now(UTC)
        lot = {
            "id": uuid4(),
            "tenant": tenant,
            "product_sku": payload.product_sku,
            "purchase_order_ref": payload.purchase_order_ref,
            "lot_code": payload.lot_code,
            "expires_on": payload.expires_on,
            "received_on": payload.received_on or date.today(),
            "received_quantity": payload.received_quantity,
            "remaining_quantity": payload.received_quantity,
            "supplier": payload.supplier,
            "notes": payload.notes,
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
        }
        self.lots[lot["id"]] = lot
        self.idempotency[(tenant, idempotency_key)] = ("receipt", fingerprint, lot)
        return {"lot": lot, "replayed": False}

    def adjust_lot(
        self,
        *,
        tenant: str,
        lot_id: UUID,
        actor: str,
        payload: LotAdjustmentCreate,
        idempotency_key: UUID,
    ) -> dict:
        self.last_tenant = tenant
        request = {
            "p_tenant": tenant,
            "p_lot_id": str(lot_id),
            "p_quantity_delta": str(payload.quantity_delta),
            "p_reason": payload.reason,
            "p_created_by": actor,
            "p_idempotency_key": str(idempotency_key),
        }
        fingerprint = idempotency_fingerprint("adjustment", request)
        existing = self.idempotency.get((tenant, idempotency_key))
        if existing:
            operation, existing_fingerprint, lot = existing
            if operation != "adjustment" or existing_fingerprint != fingerprint:
                raise HTTPException(status_code=422, detail="Idempotency key payload mismatch")
            return {"lot": lot, "replayed": True}
        lot = self.lots.get(lot_id)
        if lot is None or lot["tenant"] != tenant:
            raise HTTPException(status_code=404, detail="Lot not found")
        remaining = lot["remaining_quantity"] + payload.quantity_delta
        if remaining < 0:
            raise HTTPException(status_code=422, detail="Negative remaining quantity")
        lot["remaining_quantity"] = remaining
        lot["updated_at"] = datetime.now(UTC)
        self.idempotency[(tenant, idempotency_key)] = ("adjustment", fingerprint, lot)
        return {"lot": lot, "replayed": False}


@pytest.fixture(autouse=True)
def expiry_test_setup() -> FakeExpiryLotsRepo:
    """Install an isolated repo and authenticated tenant fixtures."""
    repo = FakeExpiryLotsRepo()
    _users_cache.clear()
    _users_cache.update(
        {
            "admin": User(
                username="admin",
                hashed_password=hash_password("admin123"),
                email="admin@test.com",
                role="admin",
                tenants_allowed=["masvital", "motoshop"],
            ),
            "vendedor": User(
                username="vendedor",
                hashed_password=hash_password("vend123"),
                email="vend@test.com",
                role="vendedor",
                tenants_allowed=["masvital"],
            ),
        }
    )
    _tenants_cache.clear()
    for tenant in ("motoshop", "masvital"):
        _tenants_cache[tenant] = Tenant(
            id=tenant,
            nombre=tenant,
            r2_object_key=f"{tenant}.duckdb",
            local_db_path=f"/tmp/{tenant}.duckdb",
        )
    app.dependency_overrides[get_expiry_lots_repo] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_expiry_lots_repo, None)
    _users_cache.clear()
    _tenants_cache.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _token(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, key: UUID | None = None, tenant: str = "masvital") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": tenant}
    if key:
        headers["Idempotency-Key"] = str(key)
    return headers


def _receipt_payload() -> dict[str, str | int]:
    return {
        "product_sku": "MV-001",
        "purchase_order_ref": "OC-2026-001",
        "lot_code": "L-001",
        "expires_on": (date.today() + timedelta(days=20)).isoformat(),
        "received_quantity": 10,
    }


def test_motoshop_cannot_access_expiry_module(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    response = client.get("/api/expiry/lots", headers=_headers(token, tenant="motoshop"))
    assert response.status_code == 404


def test_receipt_requires_privileged_role(client: TestClient) -> None:
    token = _token(client, "vendedor", "vend123")
    response = client.post(
        "/api/expiry/receipts",
        json=_receipt_payload(),
        headers=_headers(token, uuid4()),
    )
    assert response.status_code == 403


def test_receipt_is_tenant_scoped_actor_derived_and_idempotent(
    client: TestClient, expiry_test_setup: FakeExpiryLotsRepo
) -> None:
    token = _token(client, "admin", "admin123")
    key = uuid4()
    payload = {**_receipt_payload(), "created_by": "attacker"}
    first = client.post("/api/expiry/receipts", json=payload, headers=_headers(token, key))
    assert first.status_code == 201
    assert first.json()["replayed"] is False
    assert first.json()["lot"]["tenant"] == "masvital"
    assert first.json()["lot"]["created_by"] == "admin"
    assert expiry_test_setup.last_tenant == "masvital"

    replay = client.post(
        "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, key)
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["lot"]["id"] == first.json()["lot"]["id"]


def test_adjustment_prevents_negative_remaining_quantity(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    receipt = client.post(
        "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, uuid4())
    )
    lot_id = receipt.json()["lot"]["id"]

    response = client.post(
        f"/api/expiry/lots/{lot_id}/adjustments",
        json={"quantity_delta": -11, "reason": "conteo físico"},
        headers=_headers(token, uuid4()),
    )
    assert response.status_code == 422


def test_adjustment_rejects_zero_delta(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    receipt = client.post(
        "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, uuid4())
    )
    lot_id = receipt.json()["lot"]["id"]

    response = client.post(
        f"/api/expiry/lots/{lot_id}/adjustments",
        json={"quantity_delta": 0, "reason": "conteo físico"},
        headers=_headers(token, uuid4()),
    )
    assert response.status_code == 422


def test_alerts_only_show_nonempty_lots_in_horizon(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    receipt = client.post(
        "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, uuid4())
    )
    assert receipt.status_code == 201
    lot_id = receipt.json()["lot"]["id"]
    response = client.post(
        f"/api/expiry/lots/{lot_id}/adjustments",
        json={"quantity_delta": -10, "reason": "agotado"},
        headers=_headers(token, uuid4()),
    )
    assert response.status_code == 201

    alerts = client.get("/api/expiry/alerts?days=90", headers=_headers(token))
    assert alerts.status_code == 200
    assert alerts.json()["items"] == []


def test_concurrent_receipt_replay_is_single_write(expiry_test_setup: FakeExpiryLotsRepo) -> None:
    payload = ReceiptCreate(**_receipt_payload())
    key = uuid4()

    def write() -> dict:
        return expiry_test_setup.create_receipt(
            tenant="masvital", actor="admin", payload=payload, idempotency_key=key
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _unused: write(), range(2)))
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert len(expiry_test_setup.lots) == 1


def test_reused_receipt_key_rejects_changed_payload(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    key = uuid4()
    assert (
        client.post(
            "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, key)
        ).status_code
        == 201
    )
    changed = {**_receipt_payload(), "lot_code": "L-002"}
    response = client.post("/api/expiry/receipts", json=changed, headers=_headers(token, key))
    assert response.status_code == 422


def test_reused_key_rejects_cross_operation(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    key = uuid4()
    receipt = client.post(
        "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, key)
    )
    lot_id = receipt.json()["lot"]["id"]
    response = client.post(
        f"/api/expiry/lots/{lot_id}/adjustments",
        json={"quantity_delta": -1, "reason": "conteo físico"},
        headers=_headers(token, key),
    )
    assert response.status_code == 422


def test_postgrest_missing_lot_code_maps_to_404() -> None:
    response = httpx.Response(
        400,
        json={"code": "P0002", "message": "inventory lot not found"},
        request=httpx.Request(
            "POST", "https://example.test/rest/v1/rpc/app_inventory_lot_adjustment"
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        _raise_for_response(response, "adjust_lot")
    assert exc_info.value.status_code == 404


def test_missing_lot_returns_404(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    response = client.post(
        f"/api/expiry/lots/{uuid4()}/adjustments",
        json={"quantity_delta": -1, "reason": "conteo físico"},
        headers=_headers(token, uuid4()),
    )
    assert response.status_code == 404


def test_list_returns_explicitly_nullable_product_name(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    assert (
        client.post(
            "/api/expiry/receipts", json=_receipt_payload(), headers=_headers(token, uuid4())
        ).status_code
        == 201
    )
    response = client.get("/api/expiry/lots", headers=_headers(token))
    assert response.status_code == 200
    assert response.json()["items"][0]["product_name"] is None


def test_receipt_rejects_invalid_idempotency_key(client: TestClient) -> None:
    token = _token(client, "admin", "admin123")
    response = client.post(
        "/api/expiry/receipts",
        json=_receipt_payload(),
        headers={**_headers(token), "Idempotency-Key": "not-a-uuid"},
    )
    assert response.status_code == 422
