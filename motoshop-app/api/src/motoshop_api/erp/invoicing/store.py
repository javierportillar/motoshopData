"""Legacy invoice tables store (tasks 3.3) — real MySQL writer + fake twin.

The real store reads the legacy tables through the READ engine and buffers
the writes until the repo commits them inside the ERP write unit of work
(ADR-0008-03). The legacy tables are MyISAM: a mid-save failure is
compensated row by row by the repo (``discard``), and the journal is the
crash detector.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

#: Legacy table holding the invoice header.
INVOICE_HEADER_TABLE = "facventas"
#: Legacy table holding the invoice lines.
INVOICE_LINES_TABLE = "detfventas"
#: Legacy table holding the payments.
INVOICE_PAYMENTS_TABLE = "detapago"
#: Legacy table holding the accounting causación.
INVOICE_JOURNAL_TABLE = "detcuentas"


class _LazyMasterMap:
    """Read-through, per-instance cache over a legacy master table.

    The save engine consumes the masters as mappings (``.get(key)`` and
    ``key in store.sellers``), while the real store must not load the whole
    7.8k-product catalog on every request. One query per distinct key,
    memoized for the lifetime of the request.

    Iteration is deliberately unsupported: the invoice path only does keyed
    lookups, and a silent full-table scan here would be a latency trap.
    """

    __slots__ = ("_fetch", "_rows")

    def __init__(self, fetch: Any) -> None:
        self._fetch = fetch
        self._rows: dict[str, dict | None] = {}

    def get(self, key: Any, default: Any = None) -> dict | None:
        skey = str(key)
        if skey not in self._rows:
            self._rows[skey] = self._fetch(skey)
        row = self._rows[skey]
        return default if row is None else row

    def __contains__(self, key: Any) -> bool:
        return self.get(key) is not None

    def __getitem__(self, key: Any) -> dict:
        row = self.get(key)
        if row is None:
            raise KeyError(key)
        return row


class RealInvoiceStore:
    """Real MySQL store: reads through the read engine, writes buffered."""

    def __init__(self, engine_factory: Any = None) -> None:
        self._engine_factory = engine_factory
        self._pending: list[tuple[str, dict]] = []
        self._pending_stock: list[tuple[str, Decimal]] = []
        # Mirrors FakeInvoiceStore's mapping surface: `_validate` and the stock
        # block read the masters as dicts, so the real store must expose them.
        self.terceros = _LazyMasterMap(self.find_tercero)
        self.sellers = _LazyMasterMap(self.find_seller)
        self.productos = _LazyMasterMap(self.find_producto)

    def _read_engine(self):
        from motoshop_api.db.engine import get_engine

        return get_engine()

    def _write_engine(self):
        if self._engine_factory is not None:
            return self._engine_factory()
        from motoshop_api.db.engine import get_erp_engine

        return get_erp_engine()

    # ─── reads ───────────────────────────────────────────────────

    def find_tercero(self, nitter: str) -> dict | None:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT nitter, nomter, inater, cupblo FROM terceros "
                    "WHERE nitter = :n LIMIT 1"
                ),
                {"n": str(nitter)},
            ).fetchone()
        return dict(row._mapping) if row is not None else None

    def find_producto(self, codprod: str) -> dict | None:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT codprod, nomprod, actprod, exiprod, codmed FROM productos "
                    "WHERE codprod = :c LIMIT 1"
                ),
                {"c": str(codprod)},
            ).fetchone()
        return dict(row._mapping) if row is not None else None

    def find_seller(self, nitvend: str) -> dict | None:
        """The seller (the company) - legacy parity: the company is a third
        party with ``emppro = 'SI'`` (the legacy SofP_CreaLatam1 read the
        seller's NIT from there; there is no ``venfven`` table)."""
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT nitter, nomter FROM terceros "
                    "WHERE nitter = :n AND emppro = 'SI' LIMIT 1"
                ),
                {"n": str(nitvend)},
            ).fetchone()
        return dict(row._mapping) if row is not None else None

    def company_nit(self) -> str:
        """The company's own NIT (the seller of the POS sales)."""
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text("SELECT nitter FROM terceros WHERE emppro = 'SI' LIMIT 1")
            ).fetchone()
        return str(row[0]) if row is not None else ""

    # ─── writes ──────────────────────────────────────────────────

    def stage_insert(self, table: str, row: dict) -> None:
        self._pending.append((table, dict(row)))

    def discard(self, table: str, row: dict) -> None:
        for index, (pending_table, pending_row) in enumerate(self._pending):
            if pending_table == table and pending_row == row:
                del self._pending[index]
                return

    def stage_update(self, table: str, key: dict, values: dict) -> None:
        self._pending.append((table, {**key, **values}))

    def stage_stock_decrement(self, codprod: str, qty: Decimal) -> None:
        """Queue a stock delta applied with the invoice writes.

        A delta (``exiprod = exiprod - qty``) instead of an absolute value so a
        concurrent legacy sale between our read and our write is not lost.
        Rounded to 3 decimals: the legacy ``productos.exiprod`` carries grams
        (``1268.002``) and the column is a double, so an unrounded subtraction
        accumulates binary noise across sales.
        """
        self._pending_stock.append((str(codprod), Decimal(str(qty))))

    def commit(self) -> None:
        """Apply the buffered writes in order inside the ERP write UoW."""
        from sqlalchemy import text

        if not self._pending and not self._pending_stock:
            return
        engine = self._write_engine()
        with engine.begin() as conn:
            for table, row in self._pending:
                columns = ", ".join(row.keys())
                placeholders = ", ".join(f":{key}" for key in row)
                # ``text()`` lets SQLAlchemy compile the named placeholders to
                # the dialect's paramstyle; ``exec_driver_sql`` would ship
                # ``:col`` literally to pymysql (ERROR 1064).
                conn.execute(
                    text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"),
                    row,
                )
            for codprod, qty in self._pending_stock:
                conn.execute(
                    text(
                        "UPDATE productos "
                        "SET exiprod = ROUND(exiprod - :qty, 3) "
                        "WHERE codprod = :codprod"
                    ),
                    {"qty": qty, "codprod": codprod},
                )
        self._pending.clear()
        self._pending_stock.clear()


def get_invoice_store() -> Any:
    """Real in prod/dev; the fake twin lives in ``invoicing.repo``."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealInvoiceStore()
    from motoshop_api.erp.invoicing.repo import FakeInvoiceStore

    return FakeInvoiceStore()
