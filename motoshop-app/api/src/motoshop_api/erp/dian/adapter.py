"""DIAN Electronic Invoicing Adapter Protocol and Stub Implementation.

Spec: erp-dian-einvoicing (Slice 6).
Provider-agnostic interface allowing interchangeable providers (Dataico, Facture, SoftProp)
with an in-memory testable stub adapter.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

DIAN_QR_BASE_URL = "https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey="


def compute_pseudo_cufe(doc_number: str, date_str: str, total: str | Decimal, nit: str) -> str:
    """Computes a deterministic 96-character hex SHA-384 pseudo-CUFE string.

    Per DIAN Technical Annex 1.9, CUFE is a SHA-384 cryptographic digest calculated
    over core invoice fields (NumFac + FecFac + ValFac + NitOFE).
    """
    clean_total = f"{Decimal(str(total)):.2f}"
    clean_date = date_str[:10] if len(date_str) >= 10 else date_str
    seed = f"{doc_number.strip()}|{clean_date}|{clean_total}|{nit.strip()}"
    return hashlib.sha384(seed.encode("utf-8")).hexdigest().lower()


def generate_qr_url(cufe: str) -> str:
    """Generates the official DIAN verification QR URL for a given CUFE."""
    return f"{DIAN_QR_BASE_URL}{cufe}"


@runtime_checkable
class DianAdapter(Protocol):
    """Protocol contract for DIAN electronic invoicing providers."""

    def build_payload(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Transforms ERP document data into normalized DIAN provider payload."""
        ...

    def send_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Sends electronic invoice payload to DIAN or returns normalized response."""
        ...

    def poll_status(self, track_id: str) -> dict[str, Any]:
        """Polls provider status for an asynchronous transaction track ID."""
        ...


class DianStubAdapter:
    """Provider stub for DIAN electronic invoicing.

    Returns deterministic pseudo-CUFE, official verification QR URL, and
    simulated instant ACCEPT with XML stub. Also supports testing hooks for
    simulated transient network/service failures and business rejections.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.transient_failures_remaining: int = 0
        self.transient_error_message: str = "DIAN gateway timeout (503 Service Unavailable)"
        self.simulate_rejection: bool = False
        self.rejection_reason: str = "Regla DIAN 99: NIT emisor no autorizado en catálogo VPFE"

    def configure_simulation(
        self,
        transient_failures: int = 0,
        simulate_rejection: bool = False,
        transient_error: str | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        """Configures test simulation behavior."""
        with self._lock:
            self.transient_failures_remaining = max(0, transient_failures)
            self.simulate_rejection = simulate_rejection
            if transient_error is not None:
                self.transient_error_message = transient_error
            if rejection_reason is not None:
                self.rejection_reason = rejection_reason

    def reset_simulation(self) -> None:
        """Resets simulation flags to normal instant ACCEPT behavior."""
        with self._lock:
            self.transient_failures_remaining = 0
            self.simulate_rejection = False
            self.transient_error_message = "DIAN gateway timeout (503 Service Unavailable)"
            self.rejection_reason = "Regla DIAN 99: NIT emisor no autorizado en catálogo VPFE"

    def build_payload(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Constructs a normalized DIAN invoice payload from an ERP sale dictionary."""
        sale_id = str(doc.get("id") or doc.get("sale_id", ""))
        doc_number = str(doc.get("number") or doc.get("doc_number", "DOC-0001"))
        raw_date = doc.get("created_at") or doc.get("date")
        if isinstance(raw_date, datetime):
            date_str = raw_date.strftime("%Y-%m-%d")
        else:
            date_str = str(raw_date or datetime.now(UTC).strftime("%Y-%m-%d"))

        total = doc.get("grand_total") or doc.get("total") or Decimal("0.00")
        nit = str(doc.get("tenant_nit") or doc.get("nit") or "900123456")

        cufe = compute_pseudo_cufe(doc_number, date_str, total, nit)
        qr_url = generate_qr_url(cufe)

        return {
            "sale_id": sale_id,
            "doc_number": doc_number,
            "date": date_str,
            "grand_total": str(Decimal(str(total))),
            "tenant_nit": nit,
            "cufe": cufe,
            "qr_url": qr_url,
            "client_id": str(doc.get("client_id", "222222222222")),
            "client_name": str(doc.get("client_name", "CONSUMIDOR FINAL")),
            "items_count": len(doc.get("items", [])),
        }

    def send_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Sends electronic invoice payload, handling simulations and instant ACCEPT."""
        with self._lock:
            if self.transient_failures_remaining > 0:
                self.transient_failures_remaining -= 1
                return {
                    "status": "FAILED",
                    "is_transient": True,
                    "error_message": self.transient_error_message,
                    "respcod": "503",
                    "resptxt": self.transient_error_message,
                }

            if self.simulate_rejection:
                return {
                    "status": "REJECTED",
                    "is_transient": False,
                    "error_message": self.rejection_reason,
                    "respcod": "99",
                    "resptxt": self.rejection_reason,
                    "cufe": payload.get("cufe"),
                }

            cufe = payload.get("cufe") or compute_pseudo_cufe(
                doc_number=payload.get("doc_number", "DOC-0001"),
                date_str=payload.get("date", datetime.now(UTC).strftime("%Y-%m-%d")),
                total=payload.get("grand_total", "0.00"),
                nit=payload.get("tenant_nit", "900123456"),
            )
            qr_url = payload.get("qr_url") or generate_qr_url(cufe)
            doc_number = payload.get("doc_number", "DOC-0001")
            track_id = f"track-{cufe[:16]}"

            xml_stub = (
                f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2">\n'
                f'  <Invoice>\n'
                f'    <ID>{doc_number}</ID>\n'
                f'    <UUID schemeName="CUFE-SHA384">{cufe}</UUID>\n'
                f'    <IssueDate>{datetime.now(UTC).strftime("%Y-%m-%d")}</IssueDate>\n'
                f'    <Status>ACCEPTED</Status>\n'
                f'  </Invoice>\n'
                f'</AttachedDocument>'
            )

            return {
                "status": "ACCEPTED",
                "estfele": 1,
                "cufe": cufe,
                "qr_url": qr_url,
                "track_id": track_id,
                "xml": xml_stub,
                "respcod": "00",
                "resptxt": "Procesado Correctamente",
            }

    def poll_status(self, track_id: str) -> dict[str, Any]:
        """Simulates DIAN status poll for an existing track_id."""
        return {
            "track_id": track_id,
            "status": "ACCEPTED",
            "estfele": 1,
            "respcod": "00",
            "resptxt": "Procesado Correctamente",
        }
