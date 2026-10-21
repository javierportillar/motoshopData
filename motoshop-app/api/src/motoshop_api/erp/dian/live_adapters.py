"""Live DIAN provider adapters (task 6.x).

Both adapters speak the provider-agnostic ``DianAdapter`` protocol:

- ``DianDataicoAdapter`` — the Dataico API (the endpoints the legacy
  ``WADataico/Enviod1/EnvioDico`` used):
  ``POST {base}/invoices``, ``POST {base}/credit_notes``,
  ``POST {base}/support_docs``, ``GET {base}/reception_events?number=…``,
  ``GET {base}/payroll-api/payroll-entries/{prefijo}/{numnum}``.
- ``DianSoftPropAdapter`` — the SoftProp Latam host the legacy
  ``WASofPropLat/EnvioSop1/EnviarSofPlat`` used (a plain HTTP POST to the
  configured base URL).

The legacy client was plain ``HttpClient`` + Newtonsoft with no TLS
pinning and no retry (the retry/backoff lives in the queue). The new
adapters keep that behaviour but add: an explicit timeout, the
``Idempotency-Key`` header and the token in the ``Authorization`` header.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from motoshop_api.erp.dian.settings import DianSettings

logger = logging.getLogger(__name__)


class _LiveDianAdapter:
    """Shared HTTP behaviour of the live providers."""

    #: The document family -> the provider endpoint segment.
    endpoint_by_family = {
        "invoice": "invoices",
        "credit_note": "credit_notes",
        "support_doc": "support_docs",
    }

    def __init__(self, settings: DianSettings) -> None:
        self.settings = settings

    def build_payload(self, doc: dict[str, Any]) -> dict[str, Any]:
        """The provider payload is the ERP document as-is (DIAN parity)."""
        return dict(doc)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.settings.api_token:
            headers["Authorization"] = f"Bearer {self.settings.api_token}"
        if self.settings.api_key:
            headers["X-Api-Key"] = self.settings.api_key
        if self.settings.api_secret:
            headers["X-Api-Secret"] = self.settings.api_secret
        return headers

    def _endpoint(self, doc: dict[str, Any]) -> str:
        family = str(doc.get("family") or "invoice")
        segment = self.endpoint_by_family.get(family, "invoices")
        return f"{self.settings.api_base.rstrip('/')}/{segment}"

    def send_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST the document to the provider and return its normalized answer."""
        url = self._endpoint(payload)
        with httpx.Client(timeout=self.settings.timeout_seconds) as client:
            response = client.post(
                url,
                json=self.build_payload(payload),
                headers=self._headers(),
            )
            response.raise_for_status()
            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError):
                data = {"raw": response.text}
        return {
            "track_id": data.get("track_id") or data.get("id") or "",
            "cufe": data.get("cufe") or data.get("cocufe") or "",
            "status": data.get("status") or "PENDING",
            "message": data.get("message") or data.get("detail") or "",
            "raw": data,
        }

    def poll_status(self, track_id: str) -> dict[str, Any]:
        """GET the reception events of a document (Dataico parity)."""
        if not track_id:
            return {"status": "PENDING", "message": "sin track_id"}
        url = (
            f"{self.settings.api_base.rstrip('/')}/reception_events"
            f"?number={track_id}"
        )
        with httpx.Client(timeout=self.settings.timeout_seconds) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError):
                data = {"raw": response.text}
        return {
            "status": data.get("status") or "PENDING",
            "cufe": data.get("cufe") or data.get("cocufe") or "",
            "message": data.get("message") or data.get("detail") or "",
            "raw": data,
        }


class DianDataicoAdapter(_LiveDianAdapter):
    """The Dataico provider (the one the legacy Hermes used by default)."""


class DianSoftPropAdapter(_LiveDianAdapter):
    """The SoftProp Latam provider (self-hosted legacy endpoint)."""
