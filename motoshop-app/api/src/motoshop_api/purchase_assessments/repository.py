"""Service-role-only Supabase persistence and atomic assessment claims."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

import httpx

from motoshop_api.config import settings

logger = logging.getLogger(__name__)

TABLE = "purchase_assessments"
CURSOR_TABLE = "purchase_assessment_scan_cursors"
CONFLICT_COLUMNS = "tenant_id,business_date,cod_clase,num_documento,assessment_fingerprint"
CLAIM_LEASE = timedelta(minutes=10)
RETRY_BASE_DELAY = timedelta(minutes=1)
RETRY_MAX_DELAY = timedelta(hours=1)
ScanCursor = tuple[str, str, str] | None


class PurchaseAssessmentRepositoryError(RuntimeError):
    """Safe storage error with no response body or credential values."""


class PurchaseAssessmentRepository(Protocol):
    def get_scan_cursor(self, tenant_id: str) -> ScanCursor: ...
    def advance_scan_cursor(
        self, tenant_id: str, expected: ScanCursor, next_cursor: ScanCursor
    ) -> bool: ...
    def reset_scan_cursor(self, tenant_id: str) -> None: ...
    def insert_pending(self, rows: list[dict[str, Any]]) -> int: ...
    def list_claimable(self, tenant_id: str, limit: int) -> list[dict[str, Any]]: ...
    def claim(self, row: dict[str, Any]) -> dict[str, Any] | None: ...
    def complete(
        self, tenant_id: str, row_id: str, claim_token: str, result: dict[str, Any]
    ) -> bool: ...
    def fail(
        self,
        tenant_id: str,
        row_id: str,
        claim_token: str,
        error_code: str,
        attempt_count: int,
    ) -> bool: ...
    def get_invoice(
        self, tenant_id: str, business_date: str, cod_clase: str,
        num_documento: str, nit_proveedor: str | None = None,
    ) -> dict[str, Any] | None: ...
    def list_assessments(
        self, tenant_id: str, date_from: str, date_to: str,
        nit_proveedor: str | None, limit: int,
    ) -> list[dict[str, Any]]: ...


def _client() -> httpx.Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise PurchaseAssessmentRepositoryError("Supabase service-role settings are missing")
    try:
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
    except (httpx.InvalidURL, ValueError) as exc:
        raise PurchaseAssessmentRepositoryError("Supabase service URL is invalid") from exc


def _eq_filter(value: str) -> str:
    """Build an equality filter; the HTTP client URL-encodes the scalar value."""
    return f"eq.{value}"


def _request(
    client: httpx.Client,
    method: str,
    params: dict[str, str] | None = None,
    json_body: Any = None,
    prefer: str | None = None,
    table: str = TABLE,
) -> list[dict[str, Any]]:
    headers = {"Prefer": prefer} if prefer else None
    try:
        response = client.request(
            method,
            f"/{table}",
            params=params,
            json=json_body,
            headers=headers,
        )
    except httpx.RequestError as exc:
        logger.warning("Purchase assessment storage unavailable error_type=%s", type(exc).__name__)
        raise PurchaseAssessmentRepositoryError("Purchase assessment storage unavailable") from exc
    if response.status_code >= 400:
        # Do not log Supabase error bodies; they may include persisted invoice values.
        logger.error(
            "Purchase assessment storage rejected action status=%s",
            response.status_code,
        )
        raise PurchaseAssessmentRepositoryError(
            f"Purchase assessment storage rejected request ({response.status_code})"
        )
    if response.status_code == 204:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


class SupabasePurchaseAssessmentRepository:
    """PostgREST repository; every read and write carries a tenant predicate."""

    def __init__(self, client_factory: Any = _client) -> None:
        self._client_factory = client_factory

    def _ensure_scan_cursor(self, tenant_id: str) -> None:
        with self._client_factory() as client:
            _request(
                client,
                "POST",
                params={"on_conflict": "tenant_id"},
                json_body={"tenant_id": tenant_id},
                prefer="resolution=ignore-duplicates,return=minimal",
                table=CURSOR_TABLE,
            )

    def get_scan_cursor(self, tenant_id: str) -> ScanCursor:
        self._ensure_scan_cursor(tenant_id)
        with self._client_factory() as client:
            rows = _request(
                client,
                "GET",
                params={
                    "select": "cursor_business_date,cursor_cod_clase,cursor_num_documento",
                    "tenant_id": _eq_filter(tenant_id),
                    "limit": "1",
                },
                table=CURSOR_TABLE,
            )
        if not rows:
            return None
        row = rows[0]
        values = (
            str(row.get("cursor_business_date") or "")[:10],
            str(row.get("cursor_cod_clase") or ""),
            str(row.get("cursor_num_documento") or ""),
        )
        return values if all(values) else None

    def advance_scan_cursor(
        self,
        tenant_id: str,
        expected: ScanCursor,
        next_cursor: ScanCursor,
    ) -> bool:
        self._ensure_scan_cursor(tenant_id)
        params = {"tenant_id": _eq_filter(tenant_id)}
        cursor_columns = (
            "cursor_business_date",
            "cursor_cod_clase",
            "cursor_num_documento",
        )
        expected_values = expected or (None, None, None)
        for column, value in zip(cursor_columns, expected_values, strict=True):
            params[column] = "is.null" if value is None else _eq_filter(value)
        next_values = next_cursor or (None, None, None)
        patch = {
            **dict(zip(cursor_columns, next_values, strict=True)),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        with self._client_factory() as client:
            rows = _request(
                client,
                "PATCH",
                params=params,
                json_body=patch,
                table=CURSOR_TABLE,
            )
        return bool(rows)

    def reset_scan_cursor(self, tenant_id: str) -> None:
        self._ensure_scan_cursor(tenant_id)
        with self._client_factory() as client:
            _request(
                client,
                "PATCH",
                params={"tenant_id": _eq_filter(tenant_id)},
                json_body={
                    "cursor_business_date": None,
                    "cursor_cod_clase": None,
                    "cursor_num_documento": None,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                table=CURSOR_TABLE,
            )

    def insert_pending(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self._client_factory() as client:
            inserted = _request(
                client,
                "POST",
                params={"on_conflict": CONFLICT_COLUMNS, "select": "id"},
                json_body=rows,
                prefer="resolution=ignore-duplicates,return=representation",
            )
        return len(inserted)

    def list_claimable(self, tenant_id: str, limit: int) -> list[dict[str, Any]]:
        bound = max(1, min(int(limit), 100))
        fields = (
            "id,tenant_id,business_date,cod_clase,num_documento,content_fingerprint,status,"
            "attempt_count,claimed_at,claim_token,next_retry_at,deterministic_metrics"
        )
        due: list[dict[str, Any]] = []
        with self._client_factory() as client:
            due.extend(_request(
                client,
                "GET",
                params={
                    "select": fields,
                    "tenant_id": _eq_filter(tenant_id),
                    "status": _eq_filter("pending"),
                    "order": "business_date.asc,created_at.asc",
                    "limit": str(bound),
                },
            ))
            if len(due) < bound:
                retry_cutoff = datetime.now(UTC).isoformat()
                due.extend(_request(
                    client,
                    "GET",
                    params={
                        "select": fields,
                        "tenant_id": _eq_filter(tenant_id),
                        "status": _eq_filter("failed"),
                        "or": (
                            f"(next_retry_at.is.null,next_retry_at.lte.{retry_cutoff})"
                        ),
                        "order": "next_retry_at.asc,business_date.asc,created_at.asc",
                        "limit": str(bound - len(due)),
                    },
                ))
            if len(due) < bound:
                lease_cutoff = (datetime.now(UTC) - CLAIM_LEASE).isoformat()
                due.extend(_request(
                    client,
                    "GET",
                    params={
                        "select": fields,
                        "tenant_id": _eq_filter(tenant_id),
                        "status": _eq_filter("processing"),
                        "claimed_at": f"lt.{lease_cutoff}",
                        "order": "claimed_at.asc",
                        "limit": str(bound - len(due)),
                    },
                ))
        return due[:bound]

    def claim(self, row: dict[str, Any]) -> dict[str, Any] | None:
        status_value = str(row.get("status") or "")
        row_id = str(row.get("id") or "")
        if not row_id or status_value not in {"pending", "failed", "processing"}:
            return None
        now = datetime.now(UTC)
        claim_token = str(uuid4())
        params = {"id": _eq_filter(row_id), "status": _eq_filter(status_value)}
        tenant_id = str(row.get("tenant_id") or "")
        if not tenant_id:
            return None
        params["tenant_id"] = _eq_filter(tenant_id)
        if status_value == "processing":
            old_claim = row.get("claimed_at")
            if not old_claim:
                return None
            params["claimed_at"] = f"lt.{(now - CLAIM_LEASE).isoformat()}"
        elif status_value == "failed":
            retry_at = row.get("next_retry_at")
            params["next_retry_at"] = (
                "is.null" if not retry_at else _eq_filter(str(retry_at))
            )
        patch = {
            "status": "processing",
            "claim_token": claim_token,
            "claimed_at": now.isoformat(),
            "attempt_count": int(row.get("attempt_count") or 0) + 1,
            "updated_at": now.isoformat(),
            "last_error_code": None,
        }
        with self._client_factory() as client:
            claimed = _request(
                client,
                "PATCH",
                params=params,
                json_body=patch,
                prefer="return=representation",
            )
        return claimed[0] if claimed else None

    def complete(
        self,
        tenant_id: str,
        row_id: str,
        claim_token: str,
        result: dict[str, Any],
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        patch = {
            "status": (
                "fallback"
                if result["generation_mode"] == "deterministic_fallback"
                else "completed"
            ),
            "markdown": result["markdown"],
            "generation_mode": result["generation_mode"],
            "provider": result.get("provider"),
            "model": result.get("model"),
            "completed_at": now,
            "updated_at": now,
            "claim_token": None,
            "claimed_at": None,
            "next_retry_at": None,
            "last_error_code": None,
        }
        with self._client_factory() as client:
            rows = _request(
                client,
                "PATCH",
                params={
                    "id": _eq_filter(row_id),
                    "tenant_id": _eq_filter(tenant_id),
                    "claim_token": _eq_filter(claim_token),
                    "status": _eq_filter("processing"),
                },
                json_body=patch,
            )
        return bool(rows)

    def fail(
        self,
        tenant_id: str,
        row_id: str,
        claim_token: str,
        error_code: str,
        attempt_count: int,
    ) -> bool:
        now = datetime.now(UTC)
        exponent = max(0, min(int(attempt_count) - 1, 10))
        retry_delay = min(RETRY_BASE_DELAY * (2**exponent), RETRY_MAX_DELAY)
        retry_at = (now + retry_delay).isoformat()
        now_iso = now.isoformat()
        safe_code = "".join(char for char in error_code if char.isalnum() or char in "_-")[:80]
        with self._client_factory() as client:
            rows = _request(
                client,
                "PATCH",
                params={
                    "id": _eq_filter(row_id),
                    "tenant_id": _eq_filter(tenant_id),
                    "claim_token": _eq_filter(claim_token),
                    "status": _eq_filter("processing"),
                },
                json_body={
                    "status": "failed",
                    "last_error_code": safe_code or "processing_error",
                    "next_retry_at": retry_at,
                    "updated_at": now_iso,
                    "claim_token": None,
                    "claimed_at": None,
                },
            )
        return bool(rows)

    def get_invoice(
        self,
        tenant_id: str,
        business_date: str,
        cod_clase: str,
        num_documento: str,
        nit_proveedor: str | None = None,
    ) -> dict[str, Any] | None:
        params = {
            "tenant_id": _eq_filter(tenant_id),
            "business_date": _eq_filter(business_date),
            "cod_clase": _eq_filter(cod_clase),
            "num_documento": _eq_filter(num_documento),
            "order": "created_at.desc,id.desc",
            "limit": "1",
        }
        if nit_proveedor:
            params["nit_proveedor"] = _eq_filter(nit_proveedor)
        with self._client_factory() as client:
            rows = _request(client, "GET", params=params)
        return rows[0] if rows else None

    def list_assessments(
        self,
        tenant_id: str,
        date_from: str,
        date_to: str,
        nit_proveedor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        params = {
            "tenant_id": _eq_filter(tenant_id),
            "and": f"(business_date.gte.{date_from},business_date.lte.{date_to})",
            "order": "business_date.desc,created_at.desc,id.desc",
            "limit": str(min(500, max(1, int(limit)) * 5)),
        }
        if nit_proveedor:
            params["nit_proveedor"] = _eq_filter(nit_proveedor)
        with self._client_factory() as client:
            rows = _request(client, "GET", params=params)
        latest: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            identity = (
                str(row.get("business_date", "")),
                str(row.get("cod_clase", "")),
                str(row.get("num_documento", "")),
            )
            if identity in seen:
                continue
            latest.append(row)
            seen.add(identity)
            if len(latest) >= max(1, min(int(limit), 100)):
                break
        return latest


def get_purchase_assessment_repository() -> PurchaseAssessmentRepository:
    return SupabasePurchaseAssessmentRepository()
