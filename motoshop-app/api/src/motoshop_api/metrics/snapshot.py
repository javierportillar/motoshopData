"""Monotonic snapshot generations for caches backed by replaceable DuckDB files."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock

_lock = RLock()
_generations: defaultdict[str, int] = defaultdict(int)


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
    """Make a replacement visible, then best-effort purge old cache entries.

    Generation advances *before* physical cache clearing. Therefore an old
    request that finishes after the clear can only repopulate its old generation,
    which future requests will never read.
    """
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
