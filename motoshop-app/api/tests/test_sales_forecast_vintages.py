"""Persistence and immutability tests for monthly sales forecast vintages."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from motoshop_api.metrics.forecast_vintages import (
    SalesForecastRepositoryError,
    SupabaseSalesForecastVintageStore,
    apply_persisted_current_vintage,
    evaluation_metrics,
    persist_backtest_samples,
    persist_current_vintage,
)


class MemoryVintageStore:
    def __init__(self) -> None:
        self.vintages: dict[tuple[str, str], dict[str, Any]] = {}
        self.evaluations: dict[tuple[str, str], dict[str, Any]] = {}
        self.training_samples: list[dict[str, Any]] = []

    def get_vintage(self, tenant_id: str, forecast_month: str) -> dict[str, Any] | None:
        return self.vintages.get((tenant_id, forecast_month[:7]))

    def save_vintage(
        self, tenant_id: str, vintage: dict[str, Any]
    ) -> dict[str, Any] | None:
        key = (tenant_id, str(vintage["forecast_month"])[:7])
        if key not in self.vintages:
            self.vintages[key] = {**vintage, "id": f"vintage-{key[0]}-{key[1]}"}
        return self.vintages[key]

    def save_evaluation(
        self,
        tenant_id: str,
        vintage_id: str,
        sales_cutoff: str,
        actual_daily: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> None:
        self.evaluations.setdefault((tenant_id, vintage_id), {
            "sales_cutoff": sales_cutoff,
            "actual_daily": actual_daily,
            "metrics": metrics,
        })

    def list_training_samples(
        self, tenant_id: str, before_month: str, limit: int = 36
    ) -> list[dict[str, Any]]:
        if self.training_samples:
            return self.training_samples[:limit]
        samples = []
        for (saved_tenant, month), vintage in self.vintages.items():
            if saved_tenant != tenant_id or month >= before_month[:7]:
                continue
            evaluation = self.evaluations.get((tenant_id, str(vintage["id"])))
            if evaluation is None:
                continue
            forecast = vintage["daily_forecast"]
            actual_by_date = {
                row["date"]: row["amount"] for row in evaluation["actual_daily"]
            }
            samples.append({
                "month": month,
                "dates": [date.fromisoformat(row["date"]) for row in forecast],
                "forecast_daily": [row["amount"] for row in forecast],
                "actual_daily": [actual_by_date[row["date"]] for row in forecast],
                "forecast_total": sum(row["amount"] for row in forecast),
                "actual_total": sum(actual_by_date.values()),
            })
        return sorted(samples, key=lambda sample: sample["month"])[-limit:]


def _current_month_payload(amount: float = 10.0) -> dict[str, Any]:
    dates = [date(2026, 7, day) for day in range(1, 32)]
    daily_series = [
        {
            "date": day,
            "actual_amount": 0.0 if day.day == 1 else None,
            "base_projected_amount": amount,
            "revised_projected_amount": None if day.day == 1 else amount,
            "stock_adjusted_projected_amount": None,
        }
        for day in dates
    ]
    return {
        "current_month": {
            "month": "2026-07",
            "observed_amount": 0.0,
            "projected_amount": amount * 31,
            "initial_forecast_amount": amount * 31,
            "remaining_forecast_amount": amount * 30,
            "forecast_origin_date": date(2026, 6, 30),
            "forecast_status": "reconstructed",
        },
        "daily_series": daily_series,
        "source_cutoffs": {"sales_date": date(2026, 6, 30)},
        "calibration": {
            "status": "baseline_retained",
            "last_training_month": "2026-05",
        },
        "model_version": "weekday_week_of_month_v1",
    }


def test_daily_evaluation_uses_wape_mae_and_signed_bias_not_mape() -> None:
    forecast = [
        {"date": "2026-06-01", "amount": 100.0},
        {"date": "2026-06-02", "amount": 50.0},
    ]
    actual = [
        {"date": "2026-06-01", "amount": 0.0},
        {"date": "2026-06-02", "amount": 50.0},
    ]

    metrics = evaluation_metrics(forecast, actual)

    assert metrics == {
        "days": 2,
        "actual_total": 50.0,
        "forecast_total": 150.0,
        "wape_pct": 200.0,
        "mae": 50.0,
        "signed_bias_pct": 200.0,
        "scorable": True,
    }
    zero_sales = evaluation_metrics(forecast, [
        {"date": "2026-06-01", "amount": 0.0},
        {"date": "2026-06-02", "amount": 0.0},
    ])
    assert zero_sales["wape_pct"] is None
    assert zero_sales["signed_bias_pct"] is None
    assert zero_sales["scorable"] is False


def test_first_saved_current_vintage_is_reused_after_recalculation() -> None:
    store = MemoryVintageStore()
    original = _current_month_payload(amount=10.0)
    changed = _current_month_payload(amount=20.0)

    saved = persist_current_vintage(original, "tenant-a", store)
    repeated = persist_current_vintage(changed, "tenant-a", store)
    response = apply_persisted_current_vintage(changed, repeated)

    assert saved is not None
    assert repeated == saved
    assert response["current_month"]["vintage_persisted"] is True
    assert response["current_month"]["initial_forecast_amount"] == 310.0
    assert response["daily_series"][0]["base_projected_amount"] == 10.0
    # Actuals and current re-estimates remain separate from the immutable base line.
    assert response["daily_series"][0]["actual_amount"] == 0.0
    assert response["daily_series"][1]["revised_projected_amount"] == 20.0


def test_current_vintage_is_not_saved_when_daily_curve_is_incomplete() -> None:
    store = MemoryVintageStore()
    payload = _current_month_payload()
    payload["daily_series"].pop()

    assert persist_current_vintage(payload, "tenant-a", store) is None
    assert store.vintages == {}


def test_backtest_samples_save_immutable_vintage_and_evaluation() -> None:
    store = MemoryVintageStore()
    payload = {
        "_backtest_samples": [{
            "month": "2026-06",
            "dates": [date(2026, 6, 1), date(2026, 6, 2)],
            "forecast_daily": [100.0, 50.0],
            "actual_daily": [0.0, 50.0],
            "forecast_total": 150.0,
            "actual_total": 50.0,
        }],
    }

    assert persist_backtest_samples(payload, "tenant-a", store) == 1
    assert persist_backtest_samples(payload, "tenant-a", store) == 1
    assert len(store.vintages) == 1
    assert len(store.evaluations) == 1
    vintage = next(iter(store.vintages.values()))
    evaluation = next(iter(store.evaluations.values()))
    assert vintage["run_kind"] == "reconstructed"
    assert vintage["forecast_origin_date"] == "2026-05-31"
    assert evaluation["sales_cutoff"] == "2026-06-02"
    assert evaluation["metrics"]["wape_pct"] == 200.0


def test_backtest_evaluates_the_canonical_vintage_not_a_losing_candidate() -> None:
    store = MemoryVintageStore()
    store.save_vintage("tenant-a", {
        "forecast_month": "2026-06-01",
        "forecast_origin_date": "2026-05-31",
        "run_kind": "issued",
        "model_version": "first-writer-model",
        "calibration_version": "first-calibration",
        "source_cutoffs": {},
        "daily_forecast": [
            {"date": "2026-06-01", "amount": 10.0},
            {"date": "2026-06-02", "amount": 10.0},
        ],
        "monthly_base_amount": 20.0,
    })
    payload = {
        "_backtest_samples": [{
            "month": "2026-06",
            "dates": [date(2026, 6, 1), date(2026, 6, 2)],
            "forecast_daily": [100.0, 50.0],
            "actual_daily": [8.0, 0.0],
            "forecast_total": 150.0,
            "actual_total": 8.0,
        }],
    }

    assert persist_backtest_samples(payload, "tenant-a", store) == 1
    evaluation = next(iter(store.evaluations.values()))
    assert evaluation["metrics"]["forecast_total"] == 20.0
    assert evaluation["metrics"]["wape_pct"] == 150.0


def test_supabase_writes_include_tenant_and_conflict_on_vintage_identity() -> None:
    class Response:
        status_code = 201

        def json(self) -> list[dict[str, Any]]:
            return [{"id": "stored-vintage", "tenant_id": "tenant-a"}]

    class Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def request(self, method: str, url: str, **kwargs: Any) -> Response:
            self.calls.append({"method": method, "url": url, **kwargs})
            return Response()

    client = Client()
    store = SupabaseSalesForecastVintageStore(lambda: client)  # type: ignore[arg-type]
    saved = store.save_vintage("tenant-a", {
        "forecast_month": "2026-07-25",
        "forecast_origin_date": "2026-06-30",
        "run_kind": "reconstructed",
        "model_version": "model-v1",
        "calibration_version": "baseline-v1",
        "source_cutoffs": {},
        "daily_forecast": [{"date": "2026-07-01", "amount": 10}],
        "monthly_base_amount": 10,
    })

    call = client.calls[0]
    assert saved == {"id": "stored-vintage", "tenant_id": "tenant-a"}
    assert call["url"].endswith("/sales_forecast_vintages")
    assert call["params"]["on_conflict"] == "tenant_id,forecast_month"
    assert call["json"]["tenant_id"] == "tenant-a"
    assert call["json"]["forecast_month"] == "2026-07-01"
    assert call["headers"]["Prefer"] == "resolution=ignore-duplicates,return=representation"


def test_concurrent_vintage_insert_returns_the_database_canonical_row() -> None:
    requests: list[dict[str, Any]] = []
    canonical = {
        "id": "canonical-vintage",
        "tenant_id": "tenant-a",
        "forecast_month": "2026-07-01",
        "model_version": "first-writer-model",
        "daily_forecast": [{"date": "2026-07-01", "amount": 10.0}],
    }

    class Response:
        def __init__(self, status_code: int, body: list[dict[str, Any]]) -> None:
            self.status_code = status_code
            self.body = body

        def json(self) -> list[dict[str, Any]]:
            return self.body

    class Client:
        def __init__(self) -> None:
            self.responses = [Response(201, []), Response(200, [canonical])]

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def request(self, method: str, url: str, **kwargs: Any) -> Response:
            requests.append({"method": method, "url": url, **kwargs})
            return self.responses.pop(0)

    client = Client()
    store = SupabaseSalesForecastVintageStore(lambda: client)  # type: ignore[arg-type]
    candidate = {
        "forecast_month": "2026-07-01",
        "forecast_origin_date": "2026-06-30",
        "run_kind": "reconstructed",
        "model_version": "racing-model",
        "calibration_version": "racing-calibration",
        "source_cutoffs": {},
        "daily_forecast": [{"date": "2026-07-01", "amount": 99.0}],
        "monthly_base_amount": 99.0,
    }

    saved = store.save_vintage("tenant-a", candidate)

    assert saved == canonical
    assert requests[0]["params"]["on_conflict"] == "tenant_id,forecast_month"
    assert requests[1]["params"]["tenant_id"] == "eq.tenant-a"
    assert requests[1]["params"]["forecast_month"] == "eq.2026-07-01"


def test_training_samples_are_joined_and_tenant_scoped() -> None:
    vintage_id = str(uuid4())
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200

        def __init__(self, body: list[dict[str, Any]]) -> None:
            self.body = body

        def json(self) -> list[dict[str, Any]]:
            return self.body

    class Client:
        def __init__(self) -> None:
            self.responses = [
                Response([{
                    "vintage_id": vintage_id,
                    "actual_daily": [
                        {"date": "2026-06-01", "amount": 8.0},
                        {"date": "2026-06-02", "amount": 0.0},
                    ],
                    "evaluated_at": "2026-07-01T00:00:00Z",
                }]),
                Response([{
                    "id": vintage_id,
                    "tenant_id": "tenant-a",
                    "forecast_month": "2026-06-01",
                    "forecast_origin_date": "2026-05-31",
                    "model_version": "baseline-v1",
                    "daily_forecast": [
                        {"date": "2026-06-01", "amount": 10.0},
                        {"date": "2026-06-02", "amount": 12.0},
                    ],
                    "monthly_base_amount": 22.0,
                }]),
            ]

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def request(self, method: str, url: str, **kwargs: Any) -> Response:
            requests.append({"method": method, "url": url, **kwargs})
            return self.responses.pop(0)

    store = SupabaseSalesForecastVintageStore(lambda: Client())  # type: ignore[arg-type]
    samples = store.list_training_samples("tenant-a", "2026-07-01")

    assert len(samples) == 1
    assert samples[0]["month"] == "2026-06"
    assert samples[0]["forecast_daily"] == [10.0, 12.0]
    assert samples[0]["actual_daily"] == [8.0, 0.0]
    assert all(call["params"]["tenant_id"] == "eq.tenant-a" for call in requests)
    assert requests[0]["params"]["sales_cutoff"] == "lt.2026-07-01"
    assert requests[1]["params"]["forecast_month"] == "lt.2026-07-01"


def test_forecast_calibration_uses_persisted_evaluations_after_backfill() -> None:
    from motoshop_api.metrics.router import _fetch_sales_forecast_payload

    store = MemoryVintageStore()
    sample = {
        "month": "2026-06",
        "dates": [date(2026, 6, 1), date(2026, 6, 2)],
        "forecast_daily": [100.0, 50.0],
        "actual_daily": [0.0, 50.0],
        "forecast_total": 150.0,
        "actual_total": 50.0,
    }

    class Repo:
        def __init__(self) -> None:
            self.calibration_inputs: list[list[dict[str, Any]] | None] = []

        def get_sales_forecast_monthly(
            self,
            *,
            as_of_date: date | None = None,
            calibration_samples: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            self.calibration_inputs.append(calibration_samples)
            return {"_backtest_samples": [sample], "current_month": {"month": "2026-10"}}

    repo = Repo()

    payload = _fetch_sales_forecast_payload(repo, "tenant-a", store)  # type: ignore[arg-type]

    assert payload["_vintage_storage_available"] is True
    assert len(repo.calibration_inputs) == 2
    assert repo.calibration_inputs[0] is None
    assert repo.calibration_inputs[1] is not None
    assert repo.calibration_inputs[1][0]["month"] == "2026-06"


def test_forecast_remains_available_but_not_frozen_when_storage_is_unavailable() -> None:
    from motoshop_api.metrics.router import _fetch_sales_forecast_payload

    class BrokenStore(MemoryVintageStore):
        def list_training_samples(
            self, tenant_id: str, before_month: str, limit: int = 36
        ) -> list[dict[str, Any]]:
            raise SalesForecastRepositoryError("offline")

    class Repo:
        def get_sales_forecast_monthly(
            self,
            *,
            as_of_date: date | None = None,
            calibration_samples: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            assert calibration_samples == []
            return _current_month_payload()

    result = _fetch_sales_forecast_payload(Repo(), "tenant-a", BrokenStore())  # type: ignore[arg-type]
    result = apply_persisted_current_vintage(result, None)

    assert result["_vintage_storage_available"] is False
    assert result["current_month"]["forecast_status"] == "provisional"
    assert result["current_month"]["vintage_persisted"] is False


def test_supabase_failures_do_not_expose_upstream_response_body() -> None:
    class Response:
        status_code = 500

        def json(self) -> dict[str, str]:
            return {"message": "private tenant row contents"}

    class Client:
        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def request(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    store = SupabaseSalesForecastVintageStore(lambda: Client())  # type: ignore[arg-type]

    with pytest.raises(SalesForecastRepositoryError) as error:
        store.get_vintage("tenant-a", "2026-07")

    assert "private tenant" not in str(error.value)
