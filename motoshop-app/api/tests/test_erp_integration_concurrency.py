"""Task 3.6 tests (CHECKPOINT): the contadores reservation against REAL MySQL.

This is the proof that the web ERP and the desktop sgHermes can share the
``contadores`` numbering without double-booking a document number:

- AN/3.6s1: N concurrent reservations (one thread per simulated POS
  terminal) return DISTINCT, contiguous numbers.
- 3.6s2: a desktop process holding ``LOCK TABLES contadores WRITE`` in its
  own session blocks the web reservation, and the bounded wait window
  raises the retryable timeout instead of handing out a number that the
  desktop may already be using.
- 3.6s3: the storage backstop (F8-003 unique index) rejects a duplicate
  ``(codclas, prefven, numfven)`` even if the application logic fails.

The suite NEVER touches the production numbering: it creates a dedicated
schema (``motoshop_erp_test``) with its own ``contadores``/``facventas``
tables, runs there and drops it afterwards. The privileged DSN comes from
the environment (``ERP_TEST_DSN``) or from the local root MySQL user; when
neither is available the suite is SKIPPED (it is a checkpoint, not a gate
for the hermetic suite).

Run it with:
    python -m pytest tests/test_erp_integration_concurrency.py -m integration
"""

from __future__ import annotations

import os
import threading

import pytest

pymysql = pytest.importorskip("pymysql")

from motoshop_api.erp.numbering import (  # noqa: E402
    CounterLockTimeout,
    RealContadoresRepo,
)

pytestmark = pytest.mark.integration

TEST_SCHEMA = "motoshop_erp_test"

_CONTADORES_DDL = """
CREATE TABLE IF NOT EXISTS contadores (
  codcon  VARCHAR(4)  NOT NULL DEFAULT '',
  descon  VARCHAR(100) NOT NULL DEFAULT '',
  numcon  INT          NOT NULL DEFAULT 0,
  numini  INT          NULL,
  numfin  INT          NULL,
  numauto VARCHAR(2)   NOT NULL DEFAULT 'SI',
  preres  VARCHAR(8)   NOT NULL DEFAULT '',
  conres  INT          NOT NULL DEFAULT 1,
  actcon  VARCHAR(1)   NOT NULL DEFAULT 'S',
  tipclas VARCHAR(4)   NOT NULL DEFAULT '',
  KEY (codcon, preres)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
"""

_FACVENTAS_DDL = """
CREATE TABLE IF NOT EXISTS facventas (
  numfven  VARCHAR(20) NOT NULL DEFAULT '',
  codclas  VARCHAR(4)  NOT NULL DEFAULT '',
  prefven  VARCHAR(8)  NOT NULL DEFAULT 'FVP',
  nitter   VARCHAR(15) NOT NULL DEFAULT '',
  totfven  DOUBLE      NOT NULL DEFAULT 0,
  UNIQUE KEY uq_facventas_doc (codclas, prefven, numfven)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
"""


def _connect(database: str | None = None):
    """Connect with the privileged local user (no password on the dev box)."""
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("ERP_TEST_MYSQL_USER", "root")
    password = os.getenv("ERP_TEST_MYSQL_PASSWORD", "")
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="latin1",
        connect_timeout=8,
    )


def _schema_ready() -> bool:
    try:
        conn = _connect()
    except Exception:
        return False
    try:
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_SCHEMA}")
        cur.execute(f"CREATE DATABASE {TEST_SCHEMA}")
        cur.execute(f"USE {TEST_SCHEMA}")
        cur.execute(_CONTADORES_DDL)
        cur.execute(_FACVENTAS_DDL)
        cur.execute("DELETE FROM contadores")
        cur.execute(
            "INSERT INTO contadores (codcon, descon, numcon, numini, numfin, "
            "numauto, preres, conres, actcon, tipclas) VALUES "
            "('S15', 'FACTURA DE VENTA POS', 15, 1, 999999, 'SI', 'FVP', "
            "500, 'S', 'S15')"
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _engine_factory():
    """SQLAlchemy engine bound to the test schema."""
    from sqlalchemy import create_engine

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("ERP_TEST_MYSQL_USER", "root")
    password = os.getenv("ERP_TEST_MYSQL_PASSWORD", "")
    url = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{TEST_SCHEMA}"
        "?charset=latin1"
    )
    return create_engine(url, pool_pre_ping=True)


@pytest.fixture(scope="function")
def _live_mysql():
    if not _schema_ready():
        pytest.skip(
            "MySQL local no disponible: define ERP_TEST_MYSQL_USER/"
            "ERP_TEST_MYSQL_PASSWORD (o MYSQL_HOST/MYSQL_PORT) para correr "
            "la suite de concurrencia contra la BD real"
        )
    yield
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_SCHEMA}")
        conn.commit()
        conn.close()
    except Exception:
        pass


# ─── 3.6s1: concurrent reservations never collide ──────────────


def test_concurrent_reservations_return_distinct_numbers(_live_mysql):
    repo = RealContadoresRepo(engine_factory=_engine_factory, lock_wait_seconds=10.0)
    results: list[int] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def _reserve() -> None:
        try:
            barrier.wait(timeout=10)
            number = repo.reserve(
                codcon="S15",
                pref="FVP",
                doc_table="facventas",
                num_field="numfven",
            )
            results.append(number)
        except Exception as exc:  # pragma: no cover - surfaced in the assert
            errors.append(exc)

    threads = [threading.Thread(target=_reserve) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    assert len(results) == 4
    assert len(set(results)) == 4, f"double-booked numbers: {sorted(results)}"
    assert sorted(results) == list(range(500, 504))


# ─── 3.6s2: the desktop holding the lock blocks the web ─────────


def test_desktop_lock_holder_blocks_the_web_reservation(_live_mysql):
    """A desktop session holding ``LOCK TABLES contadores WRITE`` blocks us.

    The web reservation must NOT silently hand out a number the desktop may
    already be using: it waits for the bounded window and then fails with
    the retryable timeout.
    """
    holder_ready = threading.Event()
    holder_release = threading.Event()
    holder_errors: list[Exception] = []

    def _hold_desktop_lock() -> None:
        try:
            conn = _connect(TEST_SCHEMA)
            cur = conn.cursor()
            cur.execute("LOCK TABLES contadores WRITE")
            holder_ready.set()
            holder_release.wait(timeout=30)
            try:
                cur.execute("UNLOCK TABLES")
                conn.commit()
            except Exception:
                pass
            conn.close()
        except Exception as exc:  # pragma: no cover
            holder_errors.append(exc)
            holder_ready.set()

    holder = threading.Thread(target=_hold_desktop_lock, daemon=True)
    holder.start()
    assert holder_ready.wait(timeout=15), "the desktop lock holder never started"
    assert not holder_errors, holder_errors

    repo = RealContadoresRepo(engine_factory=_engine_factory, lock_wait_seconds=2.0)
    try:
        with pytest.raises(CounterLockTimeout):
            repo.reserve(
                codcon="S15",
                pref="FVP",
                doc_table="facventas",
                num_field="numfven",
            )
    finally:
        holder_release.set()
        holder.join(timeout=15)

    # the counter was NOT consumed by the blocked attempt
    conn = _connect(TEST_SCHEMA)
    cur = conn.cursor()
    cur.execute("SELECT conres FROM contadores WHERE codcon='S15' AND preres='FVP'")
    conres = cur.fetchone()[0]
    conn.close()
    assert conres == 500, f"the blocked reservation consumed a number: {conres}"


# ─── 3.6s3: the storage backstop rejects a duplicate ───────────


def test_unique_index_rejects_a_duplicate_document_number(_live_mysql):
    """F8-003: the unique index is the last line of defence."""
    import pymysql as _pymysql

    conn = _connect(TEST_SCHEMA)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO facventas (numfven, codclas, prefven, nitter, totfven) "
        "VALUES ('900', 'S15', 'FVP', '222222222222', 1000)"
    )
    conn.commit()
    with pytest.raises(_pymysql.err.IntegrityError):
        cur.execute(
            "INSERT INTO facventas (numfven, codclas, prefven, nitter, totfven) "
            "VALUES ('900', 'S15', 'FVP', '222222222222', 1000)"
        )
    conn.rollback()
    conn.close()
