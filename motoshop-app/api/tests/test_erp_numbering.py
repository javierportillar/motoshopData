"""Task 3.1 tests: contadores numbering service (SI-1s2, SI-2, SI-3).

Contract (erp-sales-invoicing spec / ADR-0008-03 φ2):
- SI-1s2: a doc type configured `numauto != 'SI'` rejects the web save with
  ManualNumberingForbidden and the counter is untouched (manual numbering is
  forbidden through the API; the desktop keeps hand-typing for S18-type docs).
- SI-2: a lagged counter heals to MAX(doc number)+1 before assigning
  (Bus_Con_Act parity): conres=501 while 501 already used → assigns 502.
- SI-3: window exhausted (numfin=500, next=501) → ResolverRangeError with an
  explicit resolver-range message and NO counter increment persists.
- Concurrency: two reservations serialize on the counter lock and return
  distinct consecutive numbers; a held lock beyond the bounded window raises
  CounterLockTimeout (the bounded 5 s lock-wait contract).
- release(): a φ2 failure walks the counter back ONLY when it still sits on
  number+1 (safe optimistic rollback; the heal job covers anything else).

Tests run hermetically against the Fake twin; the real-MySQL LOCK TABLES
path is exercised by the 3.6 integration/concurrency checkpoint suite.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from motoshop_api.erp.numbering import (
    ContadorRow,
    CounterLockTimeout,
    FakeContadoresRepo,
    ManualNumberingForbidden,
    ResolverRangeError,
)


def _row(**overrides) -> ContadorRow:
    base = dict(
        codcon="S15",
        descon="FACTURA DE VENTA POS",
        numcon=15,
        numini=1,
        numfin=100000,
        numauto="SI",
        preres="FVP",
        conres=501,
        actcon="S",
        tipclas="S15",
    )
    base.update(overrides)
    return ContadorRow(**base)


def _repo(**row_overrides) -> FakeContadoresRepo:
    repo = FakeContadoresRepo()
    repo.seed(_row(**row_overrides))
    return repo


# ─── SI-1s2: manual numbering forbidden ────────────────────────


def test_numauto_no_rejects_and_leaves_counter_untouched():
    repo = _repo(numauto="NO")
    with pytest.raises(ManualNumberingForbidden) as exc:
        repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                     num_field="numfven")
    assert "numauto" in str(exc.value)
    assert repo.read("S15", "FVP").conres == Decimal(501) or \
        repo.read("S15", "FVP").conres == 501  # counter never moved


def test_reserved_number_matches_counter_and_bumps_it():
    repo = _repo()
    number = repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                          num_field="numfven")
    assert number == 501
    assert repo.read("S15", "FVP").conres == 502


# ─── SI-2: lagged counter heals (Bus_Con_Act parity) ───────────


def test_lagged_counter_heals_to_max_plus_one():
    repo = _repo()
    repo.seed_doc_numbers("facventas", "S15", "FVP", [499, 500, 501])
    # counter lags: conres=501 but 501 is already on the doc table
    number = repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                          num_field="numfven")
    assert number == 502  # MAX+1, not the lagged 501
    assert repo.read("S15", "FVP").conres == 503  # set beyond the assigned one


def test_counter_ahead_of_docs_is_not_touched_by_heal():
    repo = _repo(conres=700)
    repo.seed_doc_numbers("facventas", "S15", "FVP", [499, 500, 501])
    number = repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                          num_field="numfven")
    assert number == 700  # no heal: counter is ahead, Bus_Con_Act is a no-op
    assert repo.read("S15", "FVP").conres == 701


# ─── SI-3: resolver window exhausted ───────────────────────────


def test_window_exhausted_rejects_with_no_increment():
    repo = _repo(numfin=500)
    repo.seed_doc_numbers("facventas", "S15", "FVP", [498, 499, 500])
    with pytest.raises(ResolverRangeError) as exc:
        repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                     num_field="numfven")
    assert "numeración final" in str(exc.value) or "numfin" in str(exc.value)
    assert repo.read("S15", "FVP").conres == 501  # no increment persists


def test_window_open_lower_bound_is_respected():
    repo = _repo(numini=600, conres=501)
    with pytest.raises(ResolverRangeError):
        repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                     num_field="numfven")
    assert repo.read("S15", "FVP").conres == 501


# ─── Concurrency: serialized, distinct, consecutive ────────────


def test_concurrent_reserves_return_distinct_consecutive_numbers():
    repo = _repo()
    results: list[int] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def _worker():
        barrier.wait()  # maximize contention
        try:
            results.append(repo.reserve(codcon="S15", pref="FVP",
                                        doc_table="facventas",
                                        num_field="numfven"))
        except Exception as exc:  # noqa: BLE001 — collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(results) == [501, 502, 503, 504]
    assert repo.read("S15", "FVP").conres == 505


def test_held_lock_beyond_bounded_window_raises_timeout():
    repo = _repo()
    repo.acquire_debug()  # simulate the desktop holding contadores WRITE
    try:
        with pytest.raises(CounterLockTimeout):
            repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                         num_field="numfven", lock_wait_seconds=0.05)
    finally:
        repo.release_debug()
    # after the desktop releases, the web save posts the next valid number
    assert repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                        num_field="numfven") == 501


# ─── φ2 failure release ─────────────────────────────────────────


def test_release_walks_back_only_when_counter_sits_on_number_plus_one():
    repo = _repo()
    number = repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                          num_field="numfven")
    assert repo.read("S15", "FVP").conres == 502
    repo.release(codcon="S15", pref="FVP", number=number)
    assert repo.read("S15", "FVP").conres == 501  # rolled back


def test_release_ignores_a_counter_that_already_advanced():
    repo = _repo()
    number = repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                          num_field="numfven")
    # another save already advanced the counter past our number+1
    repo.reserve(codcon="S15", pref="FVP", doc_table="facventas",
                 num_field="numfven")
    repo.release(codcon="S15", pref="FVP", number=number)
    assert repo.read("S15", "FVP").conres == 503  # never rewinds past others
