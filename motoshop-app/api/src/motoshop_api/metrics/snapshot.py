"""Monotonic snapshot generations for caches backed by replaceable DuckDB files."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock, RLock

_lock = RLock()
_generations: defaultdict[str, int] = defaultdict(int)
_tenant_locks: dict[str, RLock] = {}
_tenant_locks_guard = Lock()


def _tenant_lock(tenant: str) -> RLock:
    with _tenant_locks_guard:
        lock = _tenant_locks.get(tenant)
        if lock is None:
            lock = RLock()
            _tenant_locks[tenant] = lock
        return lock


@contextmanager
def snapshot_guard(tenant: str) -> Iterator[None]:
    """Serialize readers of a composed response with tenant snapshot publication."""
    with _tenant_lock(tenant):
        yield


def get_snapshot_generation(tenant: str) -> int:
    """Return the currently visible data generation for a tenant."""
    with _lock:
        return _generations[tenant]


def advance_snapshot_generation(tenant: str) -> int:
    """Publish a new tenant snapshot and return its generation."""
    with _lock:
        _generations[tenant] += 1
        return _generations[tenant]


def publish_snapshot(tenant: str) -> int:
    """Advance the visible snapshot and best-effort purge old cache entries.

    Generation advances *before* physical cache clearing. Therefore an old
    request that finishes after the clear can only repopulate its old generation,
    which future requests will never read. Callers publishing a physical file
    must hold ``snapshot_guard`` across both the file swap and this generation
    advance.
    """
    with snapshot_guard(tenant):
        generation = advance_snapshot_generation(tenant)

        # Runtime imports avoid router/repository import cycles during application
        # startup. Generation correctness does not depend on these best-effort purges.
        from motoshop_api.alerts.router import _clear_alerts_cache
        from motoshop_api.forecast.router import _clear_forecast_cache
        from motoshop_api.metrics.router import _clear_metrics_cache

        _clear_metrics_cache()
        _clear_alerts_cache()
        _clear_forecast_cache()
    return generation
