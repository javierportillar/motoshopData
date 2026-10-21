"""Legacy invoice tables store (tasks 3.3) — real MySQL writer + fake twin.

The real store reads the legacy tables through the READ engine and buffers
the writes until the repo commits them inside the ERP write unit of work
(ADR-0008-03). The legacy tables are MyISAM: a mid-save failure is
compensated row by row by the repo (``discard``), and the journal is the
crash detector.
"""

from __future__ import annotations

import logging
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

_HEADER_COLUMNS = (
    "numfven, prefven, nitter, nitvend, codcaj, obsfven, subfven, totdct, "
    "totiva, totipo, totfven, fecfven"
)
_LINES_COLUMNS = (
    "numfven, prefven, numlin, codprod, nomdet, candet, valuni, dctpes, "
    "ivapes, ipopes, dctpor, ivapor, ipopor, codbod, codmed, facumed, totdet"
)
_PAYMENT_COLUMNS = (
    "numfven, prefven, codpag, valpag, referencia, soldeb, solcre"
)
_JOURNAL_COLUMNS = (
    "numfven, prefven, codcue, valdeb, valcre, nitope"
)


class RealInvoiceStore:
    """Real MySQL store: reads through the read engine, writes buffered."""

    def __init__(self, engine_factory: Any = None) -> None:
        self._engine_factory = engine_factory
        self._pending: list[tuple[str, dict]] = []

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
                    "SELECT codprod, nomprod, actprod, exiprod FROM productos "
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

    def commit(self) -> None:
        """Apply the buffered writes in order inside the ERP write UoW."""
        if not self._pending:
            return
        engine = self._write_engine()
        with engine.begin() as conn:
            for table, row in self._pending:
                columns = ", ".join(row.keys())
                placeholders = ", ".join(f":{key}" for key in row)
                conn.exec_driver_sql(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                    row,
                )
        self._pending.clear()


def get_invoice_store() -> Any:
    """Real in prod/dev; the fake twin lives in ``invoicing.repo``."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealInvoiceStore()
    from motoshop_api.erp.invoicing.repo import FakeInvoiceStore

    return FakeInvoiceStore()
