"""Server-side Supabase facade for manual MasVital expiry lots."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from datetime import date
from typing import Any, Protocol
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from motoshop_api.config import settings
from motoshop_api.expiry.schemas import LotAdjustmentCreate, ReceiptCreate

logger = logging.getLogger(__name__)

_TABLE = "app_inventory_lots"


class ExpiryLotsRepo(Protocol):
    """Persistence contract for expiry lots."""

    def list_lots(
        self,
        *,
        tenant: str,
        product_sku: str | None,
        expires_before: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]: ...

    def list_alerts(self, *, tenant: str, expires_before: date) -> list[dict[str, Any]]: ...

    def create_receipt(
        self,
        *,
        tenant: str,
        actor: str,
        payload: ReceiptCreate,
        idempotency_key: UUID,
    ) -> dict[str, Any]: ...

    def adjust_lot(
        self,
        *,
        tenant: str,
        lot_id: UUID,
        actor: str,
        payload: LotAdjustmentCreate,
        idempotency_key: UUID,
    ) -> dict[str, Any]: ...


def idempotency_fingerprint(operation: str, data: dict[str, Any]) -> str:
    """Hash normalized immutable request data before it reaches Supabase.

    The fingerprint includes the operation name, server-derived actor and exact
    request fields. A reused key therefore cannot silently replay another write.
    """
    canonical = json.dumps(
        {"operation": operation, **data}, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _client() -> httpx.Client:
    """Build a server-only PostgREST client using the service-role credential."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase no está configurado para caducidad.",
        )
    return httpx.Client(
        base_url=f"{settings.supabase_url.rstrip('/')}/rest/v1",
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        timeout=15.0,
    )


def _raise_for_response(response: httpx.Response, action: str) -> None:
    """Translate PostgREST errors without leaking provider details."""
    if response.status_code < 400:
        return
    logger.warning("supabase_expiry_%s_failed status=%s", action, response.status_code)
    error_code = ""
    with suppress(TypeError, ValueError, json.JSONDecodeError):
        error_code = str(response.json().get("code", ""))
    if error_code == "P0002":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lote de inventario no encontrado."
        )
    if response.status_code in {400, 409, 422}:
        raise HTTPException(status_code=422, detail="La operación de caducidad no es válida.")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="No fue posible completar la operación de caducidad.",
    )


class SupabaseExpiryLotsRepo:
    """Supabase implementation. All calls include a validated tenant predicate."""

    def list_lots(
        self,
        *,
        tenant: str,
        product_sku: str | None,
        expires_before: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, str] = {
            "tenant": f"eq.{tenant}",
            "order": "expires_on.asc,id.asc",
            "limit": str(limit),
            "offset": str(offset),
        }
        if product_sku:
            params["product_sku"] = f"eq.{product_sku}"
        if expires_before:
            params["expires_on"] = f"lte.{expires_before.isoformat()}"

        with _client() as client:
            response = client.get(f"/{_TABLE}", params=params, headers={"Prefer": "count=exact"})
        _raise_for_response(response, "list_lots")
        content_range = response.headers.get("content-range", "*/0")
        try:
            total = int(content_range.rsplit("/", maxsplit=1)[1])
        except (IndexError, ValueError):
            total = len(response.json())
        return response.json(), total

    def list_alerts(self, *, tenant: str, expires_before: date) -> list[dict[str, Any]]:
        params = {
            "tenant": f"eq.{tenant}",
            "remaining_quantity": "gt.0",
            "expires_on": f"lte.{expires_before.isoformat()}",
            "order": "expires_on.asc,id.asc",
        }
        with _client() as client:
            response = client.get(f"/{_TABLE}", params=params)
        _raise_for_response(response, "list_alerts")
        return response.json()

    def create_receipt(
        self,
        *,
        tenant: str,
        actor: str,
        payload: ReceiptCreate,
        idempotency_key: UUID,
    ) -> dict[str, Any]:
        body = {
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
        body["p_request_fingerprint"] = idempotency_fingerprint("receipt", body)
        return self._rpc("app_inventory_lot_receipt", body, "create_receipt")

    def adjust_lot(
        self,
        *,
        tenant: str,
        lot_id: UUID,
        actor: str,
        payload: LotAdjustmentCreate,
        idempotency_key: UUID,
    ) -> dict[str, Any]:
        body = {
            "p_tenant": tenant,
            "p_lot_id": str(lot_id),
            "p_quantity_delta": str(payload.quantity_delta),
            "p_reason": payload.reason,
            "p_created_by": actor,
            "p_idempotency_key": str(idempotency_key),
        }
        body["p_request_fingerprint"] = idempotency_fingerprint("adjustment", body)
        return self._rpc("app_inventory_lot_adjustment", body, "adjust_lot")

    @staticmethod
    def _rpc(function: str, body: dict[str, Any], action: str) -> dict[str, Any]:
        with _client() as client:
            response = client.post(f"/rpc/{function}", json=body)
        _raise_for_response(response, action)
        data = response.json()
        if not isinstance(data, dict) or "lot" not in data:
            logger.error("supabase_expiry_%s_invalid_response", action)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Supabase devolvió una respuesta inválida para caducidad.",
            )
        return data


_repo: ExpiryLotsRepo | None = None


def get_expiry_lots_repo() -> ExpiryLotsRepo:
    """FastAPI dependency for the production expiry-lot facade."""
    global _repo
    if _repo is None:
        _repo = SupabaseExpiryLotsRepo()
    return _repo
