"""Task 1.2 tests: transactional ERP engine + unit-of-work (WF-4 / ADR-0008-03).

Objects under test:
- `motoshop_api.db.engine.get_erp_engine()` — app_writer user, autocommit=False,
  latin1 charset, pool 2+4 (MySQL 5.0.45 has no utf8/utf8mb4; latin1 forces
  mojibake-free round-trip of legacy data, see ADR-0008-07).
- `motoshop_api.erp.uow.erp_write_uow` — one request, one transaction:
  commit on success, rollback + re-raise on failure. The Fake twin mirrors
  commit/rollback semantics without a real MySQL.
"""

from __future__ import annotations

import pytest

from motoshop_api.config import settings
from motoshop_api.db.engine import get_erp_engine, reset_erp_engine
from motoshop_api.erp.uow import erp_write_uow


class SavePointless(Exception):
    pass


class FakeUowConn:
    """Fake twin of a SQLAlchemy connection inside a transaction."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.executed: list[str] = []

    def execute(self, statement, params=None):
        self.executed.append(str(statement))
        return "executed"

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeUowEngine:
    """Fake twin engine: connect() yields a fresh FakeUowConn per call."""

    def __init__(self):
        self.connections: list[FakeUowConn] = []

    def connect(self):
        conn = FakeUowConn()
        self.connections.append(conn)
        return conn

    def dispose(self):
        pass


@pytest.fixture(autouse=True)
def _clean_erp_engine():
    reset_erp_engine()
    yield
    reset_erp_engine()


# ─── engine kwargs (WF-4 foundation) ───────────────────────────


def test_get_erp_engine_kwarg_contract(monkeypatch):
    captured: dict = {}

    def _fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeUowEngine()

    monkeypatch.setattr("motoshop_api.db.engine.create_engine", _fake_create_engine)
    engine = get_erp_engine()

    assert isinstance(engine, FakeUowEngine)
    url = captured["url"]
    assert url.startswith("mysql+pymysql://")
    assert "app_writer" in url, "ERP engine must connect as the app_writer user"
    assert "charset=latin1" in url, "latin1 is mandatory against MySQL 5.0.45"
    kwargs = captured["kwargs"]
    assert kwargs["connect_args"] == {"autocommit": False}
    assert kwargs["pool_size"] == 2
    assert kwargs["max_overflow"] == 4
    assert kwargs["pool_pre_ping"] is True


def test_settings_erp_database_url_uses_app_writer_and_latin1():
    url = settings.erp_database_url
    assert url.startswith("mysql+pymysql://app_writer:")
    assert "charset=latin1" in url


def test_get_erp_engine_is_singleton(monkeypatch):
    monkeypatch.setattr(
        "motoshop_api.db.engine.create_engine", lambda *a, **k: FakeUowEngine()
    )
    assert get_erp_engine() is get_erp_engine()


# ─── UoW semantics (one request, one transaction) ──────────────


def test_uow_commits_on_success():
    engine = FakeUowEngine()
    with erp_write_uow(engine) as conn:
        conn.execute("INSERT INTO app_doc_journal (...) VALUES (...)")
    fake = engine.connections[0]
    assert fake.committed is True
    assert fake.rolled_back is False
    assert fake.closed is True
    assert fake.executed == ["INSERT INTO app_doc_journal (...) VALUES (...)"]


def test_uow_rolls_back_and_reraises_on_failure():
    engine = FakeUowEngine()
    with pytest.raises(SavePointless), erp_write_uow(engine) as conn:
        conn.execute("INSERT detfventas ...")
        raise SavePointless("payment insert exploded")
    fake = engine.connections[0]
    assert fake.rolled_back is True
    assert fake.committed is False
    assert fake.closed is True


def test_uow_returns_connection_value_via_broker():
    engine = FakeUowEngine()
    with erp_write_uow(engine) as conn:
        result = conn.execute("SELECT conres FROM contadores")
    assert result == "executed"
