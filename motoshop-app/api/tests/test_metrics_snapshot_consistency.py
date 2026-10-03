from __future__ import annotations

from threading import Event, Thread

import pytest
from fastapi import HTTPException

from motoshop_api.metrics import router
from motoshop_api.metrics.snapshot import get_snapshot_generation, publish_snapshot, snapshot_guard


def test_product_metric_response_retries_until_source_generation_is_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generations = iter([4, 5, 5, 5])
    calls = 0

    def current_generation(_tenant: str) -> int:
        return next(generations)

    def fetch_metrics() -> dict:
        nonlocal calls
        calls += 1
        return {"data_freshness": {"snapshot_generation": 5}, "items": [{"sku": "SKU-A"}]}

    monkeypatch.setattr(router, "get_snapshot_generation", current_generation)

    result = router._fetch_product_metrics_consistent("masvital", fetch_metrics)

    assert calls == 2
    assert result["data_freshness"]["snapshot_generation"] == 5


def test_product_metric_response_is_unavailable_if_snapshot_keeps_changing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generations = iter([1, 2, 3, 4])

    def current_generation(_tenant: str) -> int:
        return next(generations)

    monkeypatch.setattr(router, "get_snapshot_generation", current_generation)

    with pytest.raises(HTTPException) as error:
        router._fetch_product_metrics_consistent(
            "masvital",
            lambda: {"data_freshness": {"snapshot_generation": 2}},
        )

    assert error.value.status_code == 503
    assert "corte consistente" in str(error.value.detail)


def test_snapshot_publication_waits_for_a_composed_product_read() -> None:
    tenant = "snapshot-guard-regression"
    generation_before = get_snapshot_generation(tenant)
    publisher_started = Event()
    publisher_finished = Event()

    def publish() -> None:
        publisher_started.set()
        publish_snapshot(tenant)
        publisher_finished.set()

    thread = Thread(target=publish)
    with snapshot_guard(tenant):
        thread.start()
        assert publisher_started.wait(timeout=1)
        assert not publisher_finished.wait(timeout=0.05)

    assert publisher_finished.wait(timeout=1)
    thread.join(timeout=1)
    assert get_snapshot_generation(tenant) == generation_before + 1
