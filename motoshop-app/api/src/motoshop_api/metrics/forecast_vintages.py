"""Tenant-scoped persistence for immutable monthly sales forecast vintages."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from typing import Any, Protocol
from uuid import UUID

import httpx

from motoshop_api.config import settings

logger = logging.getLogger(__name__)

VINTAGE_TABLE = "sales_forecast_vintages"
EVALUATION_TABLE = "sales_forecast_evaluations"
_VINTAGE_CONFLICT_COLUMNS = "tenant_id,forecast_month"


class SalesForecastRepositoryError(RuntimeError):
    """Safe persistence error that does not expose Supabase response bodies."""


class SalesForecastVintageStore(Protocol):
    """Persistence contract used by the metrics route."""

    def get_vintage(self, tenant_id: str, forecast_month: str) -> dict[str, Any] | None: ...

    def save_vintage(
        self, tenant_id: str, vintage: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def save_evaluation(
        self,
        tenant_id: str,
        vintage_id: str,
        sales_cutoff: str,
        actual_daily: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> None: ...

    def list_training_samples(
        self, tenant_id: str, before_month: str, limit: int = 36
    ) -> list[dict[str, Any]]: ...


def _client() -> httpx.Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise SalesForecastRepositoryError("Supabase service-role settings are missing")
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
        raise SalesForecastRepositoryError("Supabase service URL is invalid") from exc


def _request(
    client: httpx.Client,
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    json_body: Any = None,
    prefer: str | None = None,
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
        logger.warning("Sales forecast storage unavailable error_type=%s", type(exc).__name__)
        raise SalesForecastRepositoryError("Sales forecast storage unavailable") from exc
    if response.status_code >= 400:
        logger.error("Sales forecast storage rejected request status=%s", response.status_code)
        raise SalesForecastRepositoryError(
            f"Sales forecast storage rejected request ({response.status_code})"
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


def _month_start(value: str) -> date:
    normalized = value[:7] + "-01" if len(value) == 7 else value[:10]
    parsed = date.fromisoformat(normalized)
    return parsed.replace(day=1)


def _daily_records(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    records: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict) or item.get("date") is None:
            continue
        try:
            business_date = date.fromisoformat(str(item["date"])[:10])
            amount = round(float(item["amount"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        records.append({"date": business_date.isoformat(), "amount": amount})
    return records


def evaluation_metrics(
    forecast_daily: list[dict[str, Any]], actual_daily: list[dict[str, Any]]
) -> dict[str, Any]:
    """Calculate daily WAPE, MAE, and signed bias without undefined daily MAPE."""
    forecast_by_date = {item["date"]: float(item["amount"]) for item in forecast_daily}
    actual_by_date = {item["date"]: float(item["amount"]) for item in actual_daily}
    dates = sorted(set(forecast_by_date) | set(actual_by_date))
    errors = [
        forecast_by_date.get(day, 0.0) - actual_by_date.get(day, 0.0)
        for day in dates
    ]
    actual_total = sum(actual_by_date.values())
    absolute_error = sum(abs(error) for error in errors)
    signed_error = sum(errors)
    return {
        "days": len(dates),
        "actual_total": round(actual_total, 2),
        "forecast_total": round(sum(forecast_by_date.values()), 2),
        "wape_pct": round(absolute_error / actual_total * 100, 2)
        if actual_total > 0
        else None,
        "mae": round(absolute_error / len(dates), 2) if dates else None,
        "signed_bias_pct": round(signed_error / actual_total * 100, 2)
        if actual_total > 0
        else None,
        "scorable": actual_total > 0 and bool(dates),
    }


class SupabaseSalesForecastVintageStore:
    """PostgREST repository; all reads and writes are explicitly tenant-filtered."""

    def __init__(self, client_factory: Any = _client) -> None:
        self._client_factory = client_factory

    def get_vintage(self, tenant_id: str, forecast_month: str) -> dict[str, Any] | None:
        month = _month_start(forecast_month).isoformat()
        with self._client_factory() as client:
            rows = _request(
                client,
                "GET",
                VINTAGE_TABLE,
                params={
                    "select": "*",
                    "tenant_id": f"eq.{tenant_id}",
                    "forecast_month": f"eq.{month}",
                    "order": "created_at.asc",
                    "limit": "1",
                },
            )
        return rows[0] if rows else None

    def save_vintage(
        self, tenant_id: str, vintage: dict[str, Any]
    ) -> dict[str, Any] | None:
        month = _month_start(str(vintage["forecast_month"]))
        origin = date.fromisoformat(str(vintage["forecast_origin_date"])[:10])
        if origin >= month:
            raise ValueError("Forecast origin must precede the forecast month")
        body = {
            **vintage,
            "tenant_id": tenant_id,
            "forecast_month": month.isoformat(),
            "forecast_origin_date": origin.isoformat(),
        }
        with self._client_factory() as client:
            rows = _request(
                client,
                "POST",
                VINTAGE_TABLE,
                params={"on_conflict": _VINTAGE_CONFLICT_COLUMNS},
                json_body=body,
                prefer="resolution=ignore-duplicates,return=representation",
            )
        # The database's (tenant_id, forecast_month) unique constraint is the
        # atomic winner election. A concurrent request with different model
        # metadata must return the same canonical row, not its candidate curve.
        return rows[0] if rows else self.get_vintage(tenant_id, month.isoformat())

    def save_evaluation(
        self,
        tenant_id: str,
        vintage_id: str,
        sales_cutoff: str,
        actual_daily: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> None:
        normalized_id = str(UUID(vintage_id))
        records = _daily_records(actual_daily)
        fingerprint_source = json.dumps(
            records, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        body = {
            "tenant_id": tenant_id,
            "vintage_id": normalized_id,
            "sales_cutoff": date.fromisoformat(sales_cutoff[:10]).isoformat(),
            "actual_fingerprint": hashlib.sha256(fingerprint_source).hexdigest(),
            "actual_daily": records,
            "metrics": metrics,
        }
        with self._client_factory() as client:
            _request(
                client,
                "POST",
                EVALUATION_TABLE,
                params={"on_conflict": "vintage_id,actual_fingerprint"},
                json_body=body,
                prefer="resolution=ignore-duplicates,return=minimal",
            )

    def list_training_samples(
        self, tenant_id: str, before_month: str, limit: int = 36
    ) -> list[dict[str, Any]]:
        boundary = _month_start(before_month).isoformat()
        safe_limit = max(1, min(int(limit), 120))
        with self._client_factory() as client:
            evaluations = _request(
                client,
                "GET",
                EVALUATION_TABLE,
                params={
                    "select": "vintage_id,actual_daily,evaluated_at",
                    "tenant_id": f"eq.{tenant_id}",
                    "sales_cutoff": f"lt.{boundary}",
                    "order": "evaluated_at.desc",
                    "limit": str(safe_limit * 4),
                },
            )
            evaluation_by_vintage: dict[str, dict[str, Any]] = {}
            for evaluation in evaluations:
                try:
                    vintage_id = str(UUID(str(evaluation.get("vintage_id"))))
                except (ValueError, TypeError, AttributeError):
                    continue
                evaluation_by_vintage.setdefault(vintage_id, evaluation)
            if not evaluation_by_vintage:
                return []
            ids = ",".join(evaluation_by_vintage)
            vintages = _request(
                client,
                "GET",
                VINTAGE_TABLE,
                params={
                    "select": (
                        "id,tenant_id,forecast_month,forecast_origin_date,model_version,"
                        "daily_forecast,monthly_base_amount,created_at"
                    ),
                    "tenant_id": f"eq.{tenant_id}",
                    "forecast_month": f"lt.{boundary}",
                    "id": f"in.({ids})",
                    "order": "forecast_month.desc,created_at.desc",
                    "limit": str(safe_limit * 4),
                },
            )

        samples: list[dict[str, Any]] = []
        included_months: set[str] = set()
        for vintage in vintages:
            month = str(vintage.get("forecast_month", ""))[:7]
            if not month or month in included_months:
                continue
            try:
                vintage_id = str(UUID(str(vintage.get("id"))))
            except (ValueError, TypeError, AttributeError):
                continue
            evaluation = evaluation_by_vintage.get(vintage_id)
            if evaluation is None:
                continue
            forecast_records = _daily_records(vintage.get("daily_forecast"))
            actual_records = _daily_records(evaluation.get("actual_daily"))
            actual_by_date = {item["date"]: item["amount"] for item in actual_records}
            if not forecast_records or set(actual_by_date) != {
                item["date"] for item in forecast_records
            }:
                continue
            forecast_records.sort(key=lambda item: item["date"])
            dates = [date.fromisoformat(item["date"]) for item in forecast_records]
            samples.append({
                "month": month,
                "dates": dates,
                "forecast_daily": [item["amount"] for item in forecast_records],
                "actual_daily": [actual_by_date[item["date"]] for item in forecast_records],
                "forecast_total": sum(item["amount"] for item in forecast_records),
                "actual_total": sum(actual_by_date.values()),
            })
            included_months.add(month)
            if len(samples) >= safe_limit:
                break
        return sorted(samples, key=lambda sample: sample["month"])


def persist_backtest_samples(
    payload: dict[str, Any], tenant_id: str, store: SalesForecastVintageStore
) -> int:
    """Persist walk-forward vintages and evaluations emitted by the DuckDB repo."""
    raw_samples = payload.get("_backtest_samples", [])
    if not isinstance(raw_samples, list):
        return 0
    persisted = 0
    for sample in raw_samples:
        dates = sample.get("dates", [])
        forecast_values = sample.get("forecast_daily", [])
        actual_values = sample.get("actual_daily", [])
        if not dates or len(dates) != len(forecast_values) or len(dates) != len(actual_values):
            continue
        month_start = _month_start(str(sample["month"]) + "-01")
        origin = month_start - timedelta(days=1)
        forecast_daily = [
            {"date": day.isoformat(), "amount": round(float(amount), 2)}
            for day, amount in zip(dates, forecast_values, strict=True)
        ]
        actual_daily = [
            {"date": day.isoformat(), "amount": round(float(amount), 2)}
            for day, amount in zip(dates, actual_values, strict=True)
        ]
        vintage = store.save_vintage(tenant_id, {
            "forecast_month": month_start.isoformat(),
            "forecast_origin_date": origin.isoformat(),
            "run_kind": "reconstructed",
            "model_version": "weekday_week_of_month_v1_backtest",
            "calibration_version": "baseline-v1",
            "source_cutoffs": {"sales_date": origin.isoformat()},
            "daily_forecast": forecast_daily,
            "monthly_base_amount": round(sum(item["amount"] for item in forecast_daily), 2),
        })
        if vintage is None or not vintage.get("id"):
            continue
        stored_forecast = _daily_records(vintage.get("daily_forecast"))
        expected_dates = {item["date"] for item in forecast_daily}
        if {item["date"] for item in stored_forecast} != expected_dates:
            continue
        cutoff = dates[-1].isoformat()
        store.save_evaluation(
            tenant_id,
            str(vintage["id"]),
            cutoff,
            actual_daily,
            evaluation_metrics(stored_forecast, actual_daily),
        )
        persisted += 1
    return persisted


def persist_current_vintage(
    payload: dict[str, Any], tenant_id: str, store: SalesForecastVintageStore
) -> dict[str, Any] | None:
    """Get or immutably create the current month's original daily forecast."""
    current = payload.get("current_month")
    if not isinstance(current, dict):
        return None
    month = str(current.get("month", ""))
    month_start = _month_start(month + "-01")
    existing = store.get_vintage(tenant_id, month_start.isoformat())
    if existing is not None:
        return existing

    daily_series = payload.get("daily_series", [])
    month_text = month_start.strftime("%Y-%m")
    current_points = [
        point for point in daily_series
        if isinstance(point, dict) and str(point.get("date", ""))[:7] == month_text
    ]
    current_points.sort(key=lambda point: str(point.get("date")))
    next_month_start = (month_start + timedelta(days=32)).replace(day=1)
    expected_days = (next_month_start - month_start).days
    if len(current_points) != expected_days or any(
        point.get("base_projected_amount") is None for point in current_points
    ):
        return None
    origin_value = current.get("forecast_origin_date") or month_start - timedelta(days=1)
    origin = date.fromisoformat(str(origin_value)[:10])
    run_kind = current.get("forecast_status")
    if run_kind not in {"issued", "reconstructed"}:
        run_kind = "reconstructed"
    calibration = payload.get("calibration") or {}
    model_version = str(payload.get("model_version") or "weekday_week_of_month_v1")
    calibration_version = str(payload.get("calibration_version") or (
        f"daily-calibration-v1-{calibration.get('status', 'unknown')}-"
        f"{calibration.get('last_training_month') or 'none'}"
    ))
    sales_cutoff = (payload.get("source_cutoffs") or {}).get("sales_date")
    if sales_cutoff is not None:
        sales_cutoff = min(date.fromisoformat(str(sales_cutoff)[:10]), origin).isoformat()
    vintage = store.save_vintage(tenant_id, {
        "forecast_month": month_start.isoformat(),
        "forecast_origin_date": origin.isoformat(),
        "run_kind": run_kind,
        "model_version": model_version,
        "calibration_version": calibration_version,
        # The base forecast uses sales data only; the inventory scenario is not
        # an input to this immutable training vintage.
        "source_cutoffs": {
            "sales_date": sales_cutoff,
            "inventory_date": None,
            "purchases_date": None,
        },
        "daily_forecast": [
            {
                "date": str(point["date"])[:10],
                "amount": round(float(point["base_projected_amount"]), 2),
            }
            for point in current_points
        ],
        "monthly_base_amount": round(
            sum(float(point["base_projected_amount"]) for point in current_points), 2
        ),
        "calibration": calibration,
    })
    return vintage


def apply_persisted_current_vintage(
    payload: dict[str, Any], vintage: dict[str, Any] | None
) -> dict[str, Any]:
    """Replace the current-month curve with the stored immutable vintage."""
    current = payload.get("current_month")
    if not isinstance(current, dict):
        return payload
    if vintage is None:
        current["forecast_status"] = "provisional"
        current["vintage_persisted"] = False
        current["forecast_model_version"] = payload.get("model_version")
        return payload

    forecast = _daily_records(vintage.get("daily_forecast"))
    forecast_by_date = {item["date"]: item["amount"] for item in forecast}
    month = str(current.get("month", ""))
    points = [
        point for point in payload.get("daily_series", [])
        if isinstance(point, dict) and str(point.get("date", ""))[:7] == month
    ]
    if len(points) != len(forecast_by_date) or any(
        str(point.get("date", ""))[:10] not in forecast_by_date for point in points
    ):
        return apply_persisted_current_vintage(payload, None)
    for point in points:
        point["base_projected_amount"] = forecast_by_date[str(point["date"])[:10]]
    current.update({
        "initial_forecast_amount": float(vintage.get("monthly_base_amount") or 0.0),
        "forecast_origin_date": vintage.get("forecast_origin_date"),
        "forecast_status": vintage.get("run_kind"),
        "vintage_persisted": True,
        "forecast_model_version": vintage.get("model_version"),
        "calibration_version": vintage.get("calibration_version"),
    })
    return payload


def mark_current_vintage_unavailable(payload: dict[str, Any]) -> dict[str, Any]:
    """Avoid claiming an issued/frozen curve when durable storage cannot be read."""
    current = payload.get("current_month")
    if isinstance(current, dict):
        current["forecast_status"] = "provisional"
        current["vintage_persisted"] = False
        current["forecast_model_version"] = payload.get("model_version")
        current["calibration_version"] = payload.get("calibration_version")
    return payload
