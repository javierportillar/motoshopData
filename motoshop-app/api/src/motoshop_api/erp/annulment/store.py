"""Legacy row access for the annulment path (slice 5).

The annulment repos talk to the legacy tables through this narrow contract so
the hermetic suite can run against the in-memory twin (``FakeAnnulmentStore``)
and the production API against real MySQL 5.0.45 (``RealAnnulmentStore``),
exactly like ``erp/cash/store.py`` and ``erp/invoicing/store.py`` do.

Tables touched (real legacy names, docs/hermes/evidence/schema_2024.sql):
``facventas`` (invoice header + ``estfele``), ``detfventas`` (invoice lines),
``detapago`` (payments — the S01 receipt IS a payment row), ``detcuentas``
(accounting journal + kardex rows), ``financiacion``/``detfinancia`` (credit
quotas), ``productos`` (``exiprod``), ``motanudoc`` (annulment audit) and
``cierresper`` (closed accounting periods).

Every write is STAGED and applied by ``commit()`` inside one ERP unit of work
(ADR-0008-03): a mid-reversal failure drops the staged operations and leaves
the legacy rows untouched — the annulment is all-or-nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# ─── legacy table names (single source of truth for the annulment slice) ──

FACVENTAS_TABLE = "facventas"
DETFVENTAS_TABLE = "detfventas"
DETAPAGO_TABLE = "detapago"
DETCUENTAS_TABLE = "detcuentas"
FINANCIACION_TABLE = "financiacion"
DETFINANCIA_TABLE = "detfinancia"
PRODUCTOS_TABLE = "productos"
MOTANUDOC_TABLE = "motanudoc"
CIERRESPER_TABLE = "cierresper"
COMPROBANTES_TABLE = "comprobantes"
CAJAARQUEO_TABLE = "cajaarqueo"

#: Tables the annulment path may write into (whitelist — the real store
#: builds SQL from these names only).
WRITABLE_TABLES = (
    FACVENTAS_TABLE,
    DETAPAGO_TABLE,
    DETCUENTAS_TABLE,
    FINANCIACION_TABLE,
    PRODUCTOS_TABLE,
    MOTANUDOC_TABLE,
    COMPROBANTES_TABLE,
    CAJAARQUEO_TABLE,
)

#: Legacy document number columns (the tables disagree: the legacy rows key
#: the document by ``numnum``/``numfven``/``numegr``/``numarq``).
NUMBER_COLUMNS = ("numnum", "numfven", "numegr", "numarq", "numfin")

ZERO = Decimal("0")


@dataclass(frozen=True)
class DocumentFamily:
    """Where the header of a document class lives and which flag reverses it.

    ``stock_direction`` is the sign of the document's stock movement when the
    document carries NO kardex posting of its own: ``-1`` a sale (stock out),
    ``+1`` a purchase (stock in), ``0`` the document does not move stock.
    """

    codclas: str
    header_table: str
    number_field: str
    state_column: str
    date_field: str
    prefix_field: str
    electronic_column: str = ""
    stock_direction: int = 0


#: The document families the web can annul. The legacy ``codclas`` decides
#: which header table and which state flag the reversal touches.
DOCUMENT_FAMILIES: dict[str, DocumentFamily] = {
    "S15": DocumentFamily(
        "S15", FACVENTAS_TABLE, "numfven", "estfven", "fecfven", "prefven",
        electronic_column="estfele", stock_direction=-1,
    ),
    "FV": DocumentFamily(
        "FV", FACVENTAS_TABLE, "numfven", "estfven", "fecfven", "prefven",
        electronic_column="estfele", stock_direction=-1,
    ),
    "S01": DocumentFamily(
        "S01", DETAPAGO_TABLE, "numnum", "estado", "fecdoc", "predoc",
    ),
    "S02": DocumentFamily(
        "S02", COMPROBANTES_TABLE, "numegr", "estegr", "fecegr", "preegr",
    ),
    "S03": DocumentFamily(
        "S03", COMPROBANTES_TABLE, "numegr", "estegr", "fecegr", "preegr",
    ),
    "S38": DocumentFamily(
        "S38", CAJAARQUEO_TABLE, "numarq", "estarq", "fecarq", "prearq",
    ),
}


def document_family(codclas: str) -> DocumentFamily | None:
    """The family of a legacy document class (``None`` when unknown)."""
    return DOCUMENT_FAMILIES.get(str(codclas or "").strip().upper())


def _as_decimal(value: object) -> Decimal:
    """Legacy numeric (str/Decimal/double) → Decimal, exact."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


def _number_of(row: dict) -> str:
    """The document number of a legacy row, whatever column carries it."""
    for column in NUMBER_COLUMNS:
        if column in row and row[column] not in (None, ""):
            return str(row[column])
    return ""


def matches_number(row: dict, number: object) -> bool:
    """Does the row belong to that document number?

    The legacy tables disagree on the key column (``detapago.numnum`` vs the
    ``detapago.numfven`` shape written by the invoice path), so the lookup
    accepts either one — the document identity is the number.
    """
    target = str(number)
    for column in NUMBER_COLUMNS:
        if (
            column in row
            and row[column] is not None
            and str(row[column]) == target
        ):
            return True
    return False


class AnnulmentStore(Protocol):
    """Read/write contract shared by the fake twin and the MySQL store."""

    # ── reads ──
    def find_document(self, codclas: str, numfven: int) -> dict | None: ...
    def locked_periods(self) -> list[dict]: ...
    def document_entries(self, codclas: str, numfven: int) -> list[dict]: ...
    def document_payments(self, codclas: str, numfven: int) -> list[dict]: ...
    def document_lines(self, codclas: str, numfven: int) -> list[dict]: ...
    def document_financing(self, codclas: str, numfven: int) -> list[dict]: ...
    def kardex_movements(self, codprod: str) -> list[dict]: ...
    def product(self, codprod: str) -> dict | None: ...

    # ── writes (staged; applied by commit()) ──
    def stage_document_state(self, codclas: str, numfven: int, state: str) -> dict: ...
    def stage_entries_state(self, codclas: str, numfven: int, state: str) -> dict: ...
    def stage_payments_state(self, codclas: str, numfven: int, state: str) -> dict: ...
    def stage_financing_state(self, codclas: str, numfven: int, state: str) -> dict: ...
    def stage_product_stock(self, codprod: str, value: Decimal) -> dict: ...
    def stage_motanudoc(self, row: dict) -> dict: ...
    def discard(self, table: str, op: dict) -> None: ...
    def commit(self) -> None: ...


class FakeAnnulmentStore:
    """In-memory twin of the legacy tables the annulment touches."""

    def __init__(self) -> None:
        self.facventas: list[dict] = []
        self.detfventas: list[dict] = []
        self.detapago: list[dict] = []
        self.detcuentas: list[dict] = []
        self.financiacion: list[dict] = []
        self.detfinancia: list[dict] = []
        self.productos: dict[str, dict] = {}
        self.motanudoc: list[dict] = []
        self.cierresper: list[dict] = []
        self.comprobantes: list[dict] = []
        self.cajaarqueo: list[dict] = []
        self.fail_table: str | None = None
        self.committed = False
        self._pending: list[dict] = []

    # ── reads ──

    def find_document(self, codclas: str, numfven: int) -> dict | None:
        family = document_family(codclas)
        if family is None:
            return None
        for row in self._rows_for(family.header_table):
            if str(row.get(family.number_field, "")) == str(numfven):
                return dict(row)
        return None

    def locked_periods(self) -> list[dict]:
        return [dict(row) for row in self.cierresper]

    def document_entries(self, codclas: str, numfven: int) -> list[dict]:
        return [dict(row) for row in self.detcuentas if matches_number(row, numfven)]

    def document_payments(self, codclas: str, numfven: int) -> list[dict]:
        return [dict(row) for row in self.detapago if matches_number(row, numfven)]

    def document_lines(self, codclas: str, numfven: int) -> list[dict]:
        return [dict(row) for row in self.detfventas if matches_number(row, numfven)]

    def document_financing(self, codclas: str, numfven: int) -> list[dict]:
        return [dict(row) for row in self.financiacion if matches_number(row, numfven)]

    def kardex_movements(self, codprod: str) -> list[dict]:
        return [
            dict(row)
            for row in self.detcuentas
            if str(row.get("codprod") or "") == str(codprod)
        ]

    def product(self, codprod: str) -> dict | None:
        row = self.productos.get(str(codprod))
        return dict(row) if row is not None else None

    # ── writes ──

    def stage_document_state(self, codclas: str, numfven: int, state: str) -> dict:
        family = document_family(codclas)
        if family is None:
            raise ValueError(f"unknown document class: {codclas}")
        return self._stage(
            "update",
            family.header_table,
            {family.number_field: str(numfven)},
            {family.state_column: state},
        )

    def stage_entries_state(self, codclas: str, numfven: int, state: str) -> dict:
        return self._stage(
            "update", DETCUENTAS_TABLE, {"numnum": str(numfven)}, {"estcue": state}
        )

    def stage_payments_state(self, codclas: str, numfven: int, state: str) -> dict:
        return self._stage(
            "update", DETAPAGO_TABLE, {"numnum": str(numfven)}, {"estado": state}
        )

    def stage_financing_state(self, codclas: str, numfven: int, state: str) -> dict:
        return self._stage(
            "update", FINANCIACION_TABLE, {"numfin": str(numfven)}, {"estfin": state}
        )

    def stage_product_stock(self, codprod: str, value: Decimal) -> dict:
        return self._stage(
            "update",
            PRODUCTOS_TABLE,
            {"codprod": str(codprod)},
            {"exiprod": value},
        )

    def stage_motanudoc(self, row: dict) -> dict:
        return self._stage("insert", MOTANUDOC_TABLE, {}, dict(row))

    def discard(self, table: str, op: dict) -> None:
        self._pending = [pending for pending in self._pending if pending is not op]

    def commit(self) -> None:
        for op in self._pending:
            table = op["table"]
            if op["kind"] == "insert":
                self._rows_for(table).append(dict(op["row"]))
                continue
            if table == PRODUCTOS_TABLE:
                codprod = str(op["key"].get("codprod") or "")
                product = self.productos.get(codprod)
                if product is not None:
                    product.update(op["values"])
                continue
            for row in self._rows_for(table):
                if all(str(row.get(k, "")) == str(v) for k, v in op["key"].items()):
                    row.update(op["values"])
        self._pending = []
        self.committed = True

    # ── internals ──

    def _stage(
        self, kind: str, table: str, key: dict, payload: dict
    ) -> dict:
        if self.fail_table and self.fail_table == table:
            raise RuntimeError(f"injected failure on {table}")
        op = {"kind": kind, "table": table, "key": key, "row": payload, "values": payload}
        self._pending.append(op)
        return op

    def _rows_for(self, table: str) -> list[dict]:
        return {
            FACVENTAS_TABLE: self.facventas,
            DETFVENTAS_TABLE: self.detfventas,
            DETAPAGO_TABLE: self.detapago,
            DETCUENTAS_TABLE: self.detcuentas,
            FINANCIACION_TABLE: self.financiacion,
            DETFINANCIA_TABLE: self.detfinancia,
            MOTANUDOC_TABLE: self.motanudoc,
            CIERRESPER_TABLE: self.cierresper,
            COMPROBANTES_TABLE: self.comprobantes,
            CAJAARQUEO_TABLE: self.cajaarqueo,
        }.get(table, [])


class RealAnnulmentStore:
    """Real MySQL store: reads through the read engine, writes buffered.

    The buffered operations are applied in ONE connection/transaction inside
    the ERP write unit of work (ADR-0008-03). The legacy tables are MyISAM,
    so a mid-reversal failure is compensated by dropping the staged operations
    (the journal is the crash detector).
    """

    def __init__(self, engine_factory: Any = None) -> None:
        self._engine_factory = engine_factory
        self._pending: list[dict] = []

    # ── engines ──

    def _read_engine(self):
        from motoshop_api.db.engine import get_engine

        return get_engine()

    def _write_engine(self):
        if self._engine_factory is not None:
            return self._engine_factory()
        from motoshop_api.db.engine import get_erp_engine

        return get_erp_engine()

    # ── reads ──

    def find_document(self, codclas: str, numfven: int) -> dict | None:
        from sqlalchemy import text

        family = document_family(codclas)
        if family is None:
            return None
        columns = [
            family.number_field,
            family.state_column,
            family.date_field,
            family.prefix_field,
        ]
        if family.electronic_column:
            columns.append(family.electronic_column)
        columns.append("codemp")
        sql = (
            f"SELECT {', '.join(columns)} FROM {family.header_table} "
            f"WHERE {family.number_field} = :n LIMIT 1"
        )
        with self._read_engine().connect() as conn:
            row = conn.execute(text(sql), {"n": str(numfven)}).fetchone()
        if row is None:
            return None
        data = dict(row._mapping)
        data.setdefault(family.electronic_column, "")
        return data

    def locked_periods(self) -> list[dict]:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT codcie, fecdes, fechas, tipcie, numaju, codclas "
                    "FROM cierresper"
                )
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def document_entries(self, codclas: str, numfven: int) -> list[dict]:
        return self._document_rows(DETCUENTAS_TABLE, numfven, kardex=True)

    def document_payments(self, codclas: str, numfven: int) -> list[dict]:
        return self._document_rows(DETAPAGO_TABLE, numfven)

    def document_lines(self, codclas: str, numfven: int) -> list[dict]:
        return self._document_rows(DETFVENTAS_TABLE, numfven)

    def document_financing(self, codclas: str, numfven: int) -> list[dict]:
        return self._document_rows(FINANCIACION_TABLE, numfven)

    def kardex_movements(self, codprod: str) -> list[dict]:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT numnum, codclas, prenum, codcue, valdeb, valhab, "
                    "estcue, codprod, candet, fecdoc FROM detcuentas "
                    "WHERE codprod = :c"
                ),
                {"c": str(codprod)},
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def product(self, codprod: str) -> dict | None:
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

    # ── writes ──

    def stage_document_state(self, codclas: str, numfven: int, state: str) -> dict:
        family = document_family(codclas)
        if family is None:
            raise ValueError(f"unknown document class: {codclas}")
        return self._stage(
            "update",
            family.header_table,
            {family.number_field: str(numfven)},
            {family.state_column: state},
        )

    def stage_entries_state(self, codclas: str, numfven: int, state: str) -> dict:
        return self._stage(
            "update", DETCUENTAS_TABLE, {"numnum": str(numfven)}, {"estcue": state}
        )

    def stage_payments_state(self, codclas: str, numfven: int, state: str) -> dict:
        return self._stage(
            "update", DETAPAGO_TABLE, {"numnum": str(numfven)}, {"estado": state}
        )

    def stage_financing_state(self, codclas: str, numfven: int, state: str) -> dict:
        return self._stage(
            "update", FINANCIACION_TABLE, {"numfin": str(numfven)}, {"estfin": state}
        )

    def stage_product_stock(self, codprod: str, value: Decimal) -> dict:
        return self._stage(
            "update",
            PRODUCTOS_TABLE,
            {"codprod": str(codprod)},
            {"exiprod": value},
        )

    def stage_motanudoc(self, row: dict) -> dict:
        return self._stage("insert", MOTANUDOC_TABLE, {}, dict(row))

    def discard(self, table: str, op: dict) -> None:
        self._pending = [pending for pending in self._pending if pending is not op]

    def commit(self) -> None:
        from sqlalchemy import text

        if not self._pending:
            return
        with self._write_engine().connect() as conn:
            for op in self._pending:
                if op["kind"] == "insert":
                    row = op["row"]
                    cols = ", ".join(row)
                    marks = ", ".join(f":{c}" for c in row)
                    conn.execute(
                        text(f"INSERT INTO {op['table']} ({cols}) VALUES ({marks})"),  # noqa: S608
                        {k: _sql_value(v) for k, v in row.items()},
                    )
                    continue
                key = op["key"]
                values = op["values"]
                sets = ", ".join(f"{c} = :{c}" for c in values)
                where = " AND ".join(f"{c} = :w_{c}" for c in key)
                params = {k: _sql_value(v) for k, v in values.items()}
                params.update({f"w_{k}": _sql_value(v) for k, v in key.items()})
                conn.execute(
                    text(f"UPDATE {op['table']} SET {sets} WHERE {where}"),  # noqa: S608
                    params,
                )
            conn.commit()
        self._pending = []

    # ── internals ──

    def _stage(self, kind: str, table: str, key: dict, payload: dict) -> dict:
        if table not in WRITABLE_TABLES:
            raise ValueError(f"table not writable by the annulment path: {table}")
        op = {"kind": kind, "table": table, "key": key, "row": payload, "values": payload}
        self._pending.append(op)
        return op

    def _document_rows(
        self, table: str, numfven: int, kardex: bool = False
    ) -> list[dict]:
        """Rows of one legacy table belonging to the document number.

        The legacy tables disagree on the key column (``detapago.numnum`` vs the
        ``numfven`` shape written by the invoice path), so the lookup accepts
        either one and falls back to the legacy column when the extra one does
        not exist in the deployed schema.
        """
        from sqlalchemy import text

        columns = "numfven, prefven, numnum, codclas, estado, estcue, estfin, " \
            "codcue, valdeb, valhab, candet, codprod, fecdoc"
        sql = (
            f"SELECT {columns} FROM {table} "  # noqa: S608 - table from the whitelist
            "WHERE numnum = :n OR numfven = :n"
        )
        try:
            with self._read_engine().connect() as conn:
                rows = conn.execute(text(sql), {"n": str(numfven)}).fetchall()
        except Exception:
            fallback = (
                f"SELECT {columns} FROM {table} WHERE numnum = :n"  # noqa: S608
            )
            with self._read_engine().connect() as conn:
                rows = conn.execute(text(fallback), {"n": str(numfven)}).fetchall()
        return [dict(r._mapping) for r in rows]


def _sql_value(value: object) -> object:
    """Legacy numeric columns are doubles/varchars — never a Python float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return "1" if value else "0"
    return value


def get_annulment_store() -> AnnulmentStore:
    """Real in prod/dev, fresh Fake under tests (settings.env == 'test')."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealAnnulmentStore()
    return FakeAnnulmentStore()


__all__ = [
    "AnnulmentStore",
    "CAJAARQUEO_TABLE",
    "COMPROBANTES_TABLE",
    "DETAPAGO_TABLE",
    "DETCUENTAS_TABLE",
    "DETFVENTAS_TABLE",
    "DETFINANCIA_TABLE",
    "DOCUMENT_FAMILIES",
    "DocumentFamily",
    "FACVENTAS_TABLE",
    "FakeAnnulmentStore",
    "FINANCIACION_TABLE",
    "MOTANUDOC_TABLE",
    "PRODUCTOS_TABLE",
    "RealAnnulmentStore",
    "WRITABLE_TABLES",
    "document_family",
    "get_annulment_store",
    "matches_number",
]
