"""Transactional / in-memory DIAN queue manager (Slice 6, spec erp-dian-einvoicing).

Provides:
- Thread-safe, multi-tenant isolated DIAN document queue.
- Asynchronous retry processing with exponential backoff (1s, 5s, 30s) up to 5 attempts.
- Idempotency guard: retrying an already accepted sale returns existing CUFE without re-issuing.
- Audit simulation for `respdocfele` and `app_dian_payloads`.
- Annulment coordination: marks pending items as CANCELLED.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from motoshop_api.erp.dian.adapter import DianAdapter, DianStubAdapter
from motoshop_api.erp.dian.models import DianDocOut, DianStatusEnum

logger = logging.getLogger(__name__)

BACKOFF_DELAYS = [1, 5, 30, 30, 30]
MAX_RETRIES = 5


class DianQueue:
    """Manages electronic document queues, retries, and persistence per tenant."""

    def __init__(self, adapter: DianAdapter | None = None) -> None:
        self._lock = threading.RLock()
        self.adapter: DianAdapter = adapter or DianStubAdapter()
        # Storage: tenant_id -> {sale_id: DianDocOut}
        self._tenant_documents: dict[str, dict[str, DianDocOut]] = {}
        # Payload cache: tenant_id -> {sale_id: payload dict}
        self._tenant_payloads: dict[str, dict[str, dict[str, Any]]] = {}
        # Backoff timing: tenant_id -> {sale_id: datetime}
        self._next_retry_at: dict[str, dict[str, datetime]] = {}
        # Simulation of respdocfele: tenant_id -> {sale_id: respdocfele record}
        self._respdocfele: dict[str, dict[str, dict[str, Any]]] = {}
        # Simulation of app_dian_payloads: tenant_id -> list of payload logs
        self._payload_audit: dict[str, list[dict[str, Any]]] = {}

    def reset(self) -> None:
        """Resets all queue states across all tenants (for test isolation)."""
        with self._lock:
            self._tenant_documents.clear()
            self._tenant_payloads.clear()
            self._next_retry_at.clear()
            self._respdocfele.clear()
            self._payload_audit.clear()
            if isinstance(self.adapter, DianStubAdapter):
                self.adapter.reset_simulation()

    def _ensure_tenant(self, tenant_id: str) -> None:
        if tenant_id not in self._tenant_documents:
            self._tenant_documents[tenant_id] = {}
        if tenant_id not in self._tenant_payloads:
            self._tenant_payloads[tenant_id] = {}
        if tenant_id not in self._next_retry_at:
            self._next_retry_at[tenant_id] = {}
        if tenant_id not in self._respdocfele:
            self._respdocfele[tenant_id] = {}
        if tenant_id not in self._payload_audit:
            self._payload_audit[tenant_id] = []

    def enqueue_sale(
        self,
        sale: Any,
        tenant_id: str,
        tenant_nit: str = "900123456",
    ) -> DianDocOut:
        """Enqueues an issued sale for DIAN transmission.

        Maintains idempotency: if sale is already ACCEPTED, returns existing doc.
        """
        with self._lock:
            self._ensure_tenant(tenant_id)
            sale_id = str(getattr(sale, "id", None) or (sale.get("id") if isinstance(sale, dict) else ""))
            if not sale_id:
                raise ValueError("Sale must have an 'id'")

            # Idempotency check: if already accepted, return existing without re-issuing
            existing = self._tenant_documents[tenant_id].get(sale_id)
            if existing and existing.status == DianStatusEnum.ACCEPTED:
                return existing
            if existing and existing.status == DianStatusEnum.SENDING:
                return existing

            # Convert sale to dict payload format
            if hasattr(sale, "model_dump"):
                sale_data = sale.model_dump()
            elif isinstance(sale, dict):
                sale_data = dict(sale)
            else:
                sale_data = {"id": sale_id, "number": getattr(sale, "number", sale_id)}

            sale_data["tenant_nit"] = tenant_nit
            payload = self.adapter.build_payload(sale_data)

            doc_number = str(sale_data.get("number") or sale_data.get("doc_number") or sale_id)
            doc = DianDocOut(
                sale_id=sale_id,
                doc_number=doc_number,
                cufe=payload.get("cufe"),
                qr_url=payload.get("qr_url"),
                status=DianStatusEnum.PENDING,
                sent_at=None,
                accepted_at=None,
                error_message=None,
                retry_count=existing.retry_count if existing else 0,
                track_id=None,
                estfele=None,
            )

            self._tenant_documents[tenant_id][sale_id] = doc
            self._tenant_payloads[tenant_id][sale_id] = payload
            return doc

    def process_queue(
        self,
        tenant_id: str | None = None,
        ignore_backoff: bool = False,
    ) -> list[DianDocOut]:
        """Processes pending items in the queue with backoff logic and max 5 retries.

        If tenant_id is provided, processes only for that tenant.
        If ignore_backoff is True, processes pending items immediately regardless of scheduled delay.
        """
        processed: list[DianDocOut] = []
        now = datetime.now(UTC)

        with self._lock:
            tenants = [tenant_id] if tenant_id is not None else list(self._tenant_documents.keys())

            for tid in tenants:
                self._ensure_tenant(tid)
                # Work on a copy of items to avoid mutation issues
                items = list(self._tenant_documents[tid].values())
                for doc in items:
                    if doc.status != DianStatusEnum.PENDING:
                        continue

                    # Check backoff schedule
                    scheduled_time = self._next_retry_at[tid].get(doc.sale_id)
                    if not ignore_backoff and scheduled_time and now < scheduled_time:
                        continue

                    payload = self._tenant_payloads[tid].get(doc.sale_id)
                    if not payload:
                        continue

                    # Transition to SENDING
                    doc.status = DianStatusEnum.SENDING
                    doc.sent_at = now

                    # Audit request payload (app_dian_payloads)
                    self._payload_audit[tid].append({
                        "sale_id": doc.sale_id,
                        "doc_number": doc.doc_number,
                        "attempt": doc.retry_count + 1,
                        "sent_at": now.isoformat(),
                        "payload": payload,
                    })

                    # Call adapter
                    result = self.adapter.send_invoice(payload)
                    res_status = result.get("status")

                    if res_status == "ACCEPTED":
                        doc.status = DianStatusEnum.ACCEPTED
                        doc.accepted_at = datetime.now(UTC)
                        doc.cufe = result.get("cufe") or doc.cufe
                        doc.qr_url = result.get("qr_url") or doc.qr_url
                        doc.track_id = result.get("track_id")
                        doc.estfele = result.get("estfele", 1)
                        doc.error_message = None
                        self._next_retry_at[tid].pop(doc.sale_id, None)

                        # Persist in respdocfele once
                        self._respdocfele[tid][doc.sale_id] = {
                            "numnum": doc.doc_number,
                            "codclas": "FV",
                            "cocufe": doc.cufe,
                            "cuuid": doc.track_id,
                            "qrcode": doc.qr_url,
                            "respcod": result.get("respcod", "00"),
                            "estfele": doc.estfele,
                            "resptxt": result.get("resptxt", "Procesado Correctamente"),
                            "codpro": "DIAN_STUB",
                        }

                    elif res_status == "REJECTED":
                        doc.status = DianStatusEnum.REJECTED
                        doc.estfele = 3
                        doc.error_message = result.get("error_message") or result.get("resptxt")
                        self._next_retry_at[tid].pop(doc.sale_id, None)

                        self._respdocfele[tid][doc.sale_id] = {
                            "numnum": doc.doc_number,
                            "codclas": "FV",
                            "cocufe": doc.cufe,
                            "cuuid": None,
                            "qrcode": None,
                            "respcod": result.get("respcod", "99"),
                            "estfele": doc.estfele,
                            "resptxt": doc.error_message,
                            "codpro": "DIAN_STUB",
                        }

                    else:
                        # Transient failure
                        doc.retry_count += 1
                        doc.error_message = result.get("error_message") or "Transient transmission failure"

                        if doc.retry_count >= MAX_RETRIES:
                            doc.status = DianStatusEnum.FAILED
                            doc.estfele = 0
                            self._next_retry_at[tid].pop(doc.sale_id, None)
                        else:
                            doc.status = DianStatusEnum.PENDING
                            delay_secs = BACKOFF_DELAYS[min(doc.retry_count - 1, len(BACKOFF_DELAYS) - 1)]
                            self._next_retry_at[tid][doc.sale_id] = now + timedelta(seconds=delay_secs)

                    processed.append(doc)

        return processed

    def retry_sale(
        self,
        sale_id: str,
        tenant_id: str,
        force: bool = False,
    ) -> DianDocOut:
        """Triggers manual retry for a failed or pending DIAN document.

        If already accepted, returns existing doc (idempotent).
        """
        with self._lock:
            self._ensure_tenant(tenant_id)
            doc = self._tenant_documents[tenant_id].get(sale_id)
            if not doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"DIAN document for sale '{sale_id}' not found in tenant '{tenant_id}'",
                )

            # Idempotency check: if accepted, do not re-send or modify
            if doc.status == DianStatusEnum.ACCEPTED:
                return doc

            if doc.status == DianStatusEnum.CANCELLED and not force:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot retry a cancelled electronic document",
                )

            # Reset status to PENDING and clear backoff timer
            doc.status = DianStatusEnum.PENDING
            if force:
                doc.retry_count = 0
            self._next_retry_at[tenant_id].pop(sale_id, None)

            # Process immediately
            self.process_queue(tenant_id=tenant_id, ignore_backoff=True)
            return self._tenant_documents[tenant_id][sale_id]

    def get_dian_status_for_sale(self, sale_id: str, tenant_id: str) -> DianDocOut | None:
        """Returns the DIAN transmission status for a sale within active tenant."""
        with self._lock:
            self._ensure_tenant(tenant_id)
            return self._tenant_documents[tenant_id].get(sale_id)

    def list_dian_documents(
        self,
        tenant_id: str,
        status: DianStatusEnum | None = None,
    ) -> list[DianDocOut]:
        """Lists all DIAN documents for active tenant, optionally filtered by status."""
        with self._lock:
            self._ensure_tenant(tenant_id)
            docs = list(self._tenant_documents[tenant_id].values())
            if status is not None:
                docs = [d for d in docs if d.status == status]
            return docs

    def cancel_sale(self, sale_id: str, tenant_id: str) -> bool:
        """Marks a pending or failed document as CANCELLED when the sale is voided.

        Returns True if cancelled, False if document was already ACCEPTED or not found.
        """
        with self._lock:
            self._ensure_tenant(tenant_id)
            doc = self._tenant_documents[tenant_id].get(sale_id)
            if doc and doc.status != DianStatusEnum.ACCEPTED:
                doc.status = DianStatusEnum.CANCELLED
                self._next_retry_at[tenant_id].pop(sale_id, None)
                return True
            return False


# Singleton instance
_dian_queue: DianQueue | None = None
_dian_queue_lock = threading.Lock()


def get_dian_queue() -> DianQueue:
    """Returns the singleton DianQueue instance."""
    global _dian_queue
    with _dian_queue_lock:
        if _dian_queue is None:
            _dian_queue = DianQueue()
        return _dian_queue


def reset_dian_queue() -> DianQueue:
    """Resets the singleton DianQueue instance (for test isolation)."""
    global _dian_queue
    with _dian_queue_lock:
        _dian_queue = DianQueue()
        return _dian_queue
