"""Unit of Work: one request, one BEGIN/COMMIT on the ERP engine (ADR-0008-03).

The legacy doc tables are MyISAM (no rollback). This UoW is only the *first*
half of all-or-nothing semantics: InnoDB companions (app_doc_journal,
app_idempotency) run inside it, and MyISAM legacy rows written inside the
same unit are compensated on failure by the save engine's cleanup step (φ3
failure path — see erp/engine.py and ADR-0008-03).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

ConnectionT = object  # SQLAlchemy Connection at runtime; typed loosely for fake twins


@contextmanager
def erp_write_uow(engine=None) -> Iterator[ConnectionT]:
    """Yield a single transactional connection and commit/rollback it.

    - commits on success (COMMIT),
    - rolls back and re-raises on any exception (rollback of InnoDB rows;
      legacy MyISAM cleanup is the save engine's φ3 compensating path),
    - closes the connection either way.

    The connection starts an implicit transaction on the first statement
    because ``connect_args={"autocommit": False}`` is forced on the engine —
    no explicit ``BEGIN`` is issued (MySQL 5.0.45 + pymysql are happiest with
    the implicit form at the start of a unit).
    """
    if engine is None:
        from motoshop_api.db.engine import get_erp_engine

        engine = get_erp_engine()

    conn = engine.connect()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()
