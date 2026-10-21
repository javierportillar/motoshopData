"""Regression tests for the legacy write path against real MySQL.

The save engine is exercised hermetically by ``test_erp_invoice_save.py``
through ``FakeInvoiceStore``, which masked three defects that only appear
against the legacy schema (found by the F8 E2E probe on masvital_clone):

- ``RealInvoiceStore`` did not expose the ``terceros``/``sellers``/
  ``productos`` mappings that ``_validate`` and the stock block consume,
  so every real save died with ``AttributeError`` before the first INSERT.
- ``app_doc_journal`` did not declare ``updated_at`` while the repository
  writes it, so ``record_number`` raised ``CompileError: Unconsumed column
  names: updated_at``.
- ``commit`` used ``exec_driver_sql`` with named placeholders, shipping
  ``:numfven`` literally to pymysql (ERROR 1064).

No database is touched here: the store is driven through a fake engine.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from motoshop_api.erp.invoicing.store import RealInvoiceStore, _LazyMasterMap


def test_real_store_exposes_the_master_mappings_the_engine_reads():
    store = RealInvoiceStore()

    assert hasattr(store, "terceros")
    assert hasattr(store, "sellers")
    assert hasattr(store, "productos")


def test_lazy_master_map_fetches_once_and_supports_membership():
    calls: list[str] = []

    def fetch(key: str) -> dict | None:
        calls.append(key)
        return {"nitter": key} if key == "A" else None

    masters = _LazyMasterMap(fetch)

    assert masters.get("A") == {"nitter": "A"}
    assert masters.get("A") == {"nitter": "A"}
    assert calls == ["A"], "a repeated key must not hit the database again"
    assert "A" in masters
    assert "B" not in masters
    assert masters.get("B", "fallback") == "fallback"


def test_journal_model_declares_the_updated_at_column():
    from motoshop_api.erp.models import app_doc_journal

    assert "updated_at" in app_doc_journal.c


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []

    def execute(self, statement, params) -> None:
        self.statements.append((str(statement), dict(params)))


class _FakeTransaction:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeConnection:
        return self._connection

    def __exit__(self, *exc_info) -> None:
        return None


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self.connection)


def test_commit_binds_parameters_instead_of_shipping_named_placeholders():
    engine = _FakeEngine()
    store = RealInvoiceStore(engine_factory=lambda: engine)
    store.stage_insert(
        "facventas", {"numfven": 501, "totfven": Decimal("11900")}
    )

    store.commit()

    assert len(engine.connection.statements) == 1
    sql, params = engine.connection.statements[0]
    assert "INSERT INTO facventas" in sql
    assert ":numfven" in sql, "named placeholders are compiled by SQLAlchemy"
    assert params == {"numfven": 501, "totfven": Decimal("11900")}
    assert store._pending == [], "the buffer is drained after the commit"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
