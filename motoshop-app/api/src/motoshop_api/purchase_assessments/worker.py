"""Single-threaded periodic sweeper for durable purchase-assessment jobs."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Event, Thread
from typing import Any

from motoshop_api.config import settings
from motoshop_api.purchase_assessments.repository import PurchaseAssessmentRepository
from motoshop_api.purchase_assessments.service import refresh_purchase_assessments
from motoshop_api.tenants import Tenant, get_all_tenants

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60
SHUTDOWN_JOIN_SECONDS = 5


def _tenant_snapshot_path(tenant_id: str) -> Path:
    from motoshop_api.metrics.repo_duckdb import (
        _bootstrap_duckdb_from_r2,
        _make_db_path,
    )

    db_path = Path(settings.duckdb_path or _make_db_path(tenant_id))
    if settings.env.casefold() != "test":
        _bootstrap_duckdb_from_r2(db_path, tenant_id)
    return db_path


class PeriodicPurchaseAssessmentWorker:
    """Run one bounded tenant sweep at a time on a single daemon thread."""

    def __init__(
        self,
        *,
        tenants_provider: Callable[[], Mapping[str, Tenant]] = get_all_tenants,
        db_path_for_tenant: Callable[[str], Path] = _tenant_snapshot_path,
        repository: PurchaseAssessmentRepository | None = None,
        llm_client: Any | None = None,
        interval_seconds: int = SWEEP_INTERVAL_SECONDS,
        sweep: Callable[..., dict[str, int]] = refresh_purchase_assessments,
    ) -> None:
        self._tenants_provider = tenants_provider
        self._db_path_for_tenant = db_path_for_tenant
        self._repository = repository
        self._llm_client = llm_client
        self._interval_seconds = max(1, int(interval_seconds))
        self._sweep = sweep
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="purchase-assessment-sweeper",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=SHUTDOWN_JOIN_SECONDS)
            self._thread = None

    def run_once(self) -> None:
        """Sweep one invoice page per configured tenant; safe for deterministic tests."""
        for tenant_id in sorted(self._tenants_provider()):
            if self._stop_event.is_set():
                break
            try:
                self._sweep(
                    tenant_id,
                    self._db_path_for_tenant(tenant_id),
                    repository=self._repository,
                    llm_client=self._llm_client,
                    reset_cursor=False,
                )
            except Exception as exc:
                logger.warning(
                    "Purchase assessment sweep failed tenant=%s error_type=%s",
                    tenant_id,
                    type(exc).__name__,
                )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(self._interval_seconds)


def start_purchase_assessment_worker() -> PeriodicPurchaseAssessmentWorker | None:
    """Start background recovery only where the service-role store is configured."""
    if (
        settings.env.casefold() == "test"
        or not settings.supabase_url
        or not settings.supabase_service_key
    ):
        return None
    worker = PeriodicPurchaseAssessmentWorker()
    worker.start()
    return worker
