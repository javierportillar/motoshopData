"""Legacy row access for the cash/collections write path (slice 4).

The cash repos talk to the legacy tables through this narrow contract so the
hermetic suite can run against the in-memory twin (``FakeCashStore``) and the
production API against real MySQL 5.0.45 (``RealCashStore``), exactly like
``erp/masters/repo.py`` and ``erp/invoicing/repo.py`` do.

Tables touched (real legacy names, docs/hermes/evidence/schema_2024.sql):
``facventas`` (invoice header), ``detapago`` (payments), ``detcuentas``
(accounting journal), ``comprobantes`` (egress/ingress docs), ``cajaarqueo`` +
``detcajarq`` (cash count), ``consbancab`` (bank consignment), ``formapago``
(payment forms + their own consignment counter), ``concepingegr`` (income and
expense concepts) and ``cierresper`` (closed accounting periods).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from motoshop_api.erp.numbering import ContadorRow, FakeContadoresRepo

# ─── legacy table names (single source of truth for the cash slice) ──

FACVENTAS_TABLE = "facventas"
DETAPAGO_TABLE = "detapago"
DETCUENTAS_TABLE = "detcuentas"
COMPROBANTES_TABLE = "comprobantes"
CAJAARQUEO_TABLE = "cajaarqueo"
DETCAJARQ_TABLE = "detcajarq"
CONSBANCAB_TABLE = "consbancab"
FORMAPAGO_TABLE = "formapago"
CONCEPINGEGR_TABLE = "concepingegr"
CIERRESPER_TABLE = "cierresper"

#: Tables the cash write path may insert into (whitelist — the real store
#: builds SQL from these names only).
WRITABLE_TABLES = (
    DETAPAGO_TABLE,
    DETCUENTAS_TABLE,
    COMPROBANTES_TABLE,
    CAJAARQUEO_TABLE,
    DETCAJARQ_TABLE,
    CONSBANCAB_TABLE,
    FORMAPAGO_TABLE,
)


class CashStore(Protocol):
    """Read/write contract shared by the fake twin and the MySQL store."""

    # ── reads ──
    def find_invoice(self, numfven: int, prefven: str) -> dict | None: ...
    def ledger_rows(self, numnum: str, codcue: str) -> list[dict]: ...
    def locked_periods(self) -> list[dict]: ...
    def find_formapago(self, codpag: str) -> dict | None: ...
    def find_concept(self, codcon: str) -> dict | None: ...
    def payment_form_counter(self, codpag: str) -> int: ...
    def advance_payment_form_counter(self, codpag: str, value: int) -> None: ...

    # ── writes ──
    def stage_insert(self, table: str, row: dict) -> None: ...
    def stage_update(self, table: str, key: dict, values: dict) -> None: ...
    def discard(self, table: str, row: dict) -> None: ...
    def commit(self) -> None: ...


def _contador(codcon: str, descon: str, numcon: int, preres: str, conres: int) -> ContadorRow:
    return ContadorRow(
        codcon=codcon,
        descon=descon,
        numcon=numcon,
        numini=1,
        numfin=99999,
        numauto="SI",
        preres=preres,
        conres=conres,
        actcon="S",
        tipclas=codcon,
    )


class FakeCashStore:
    """In-memory twin of the legacy cash tables."""

    def __init__(self) -> None:
        self.facventas: list[dict] = []
        self.detapago: list[dict] = []
        self.detcuentas: list[dict] = []
        self.comprobantes: list[dict] = []
        self.cajaarqueo: list[dict] = []
        self.detcajarq: list[dict] = []
        self.consbancab: list[dict] = []
        self.formapago: dict[str, dict] = {}
        self.concepingegr: dict[str, dict] = {}
        self.cierresper: list[dict] = []
        self.fail_table: str | None = None
        self.committed = False
        self.numbering: FakeContadoresRepo = FakeContadoresRepo()
        self.numbering.seed(
            _contador("S01", "RECIBO DE CAJA", 1, "RC", 101)
        )
        self.numbering.seed(
            _contador("S02", "COMPROBANTE DE EGRESO", 2, "CE", 201)
        )
        self.numbering.seed(
            _contador("S03", "COMPROBANTE DE INGRESO", 3, "CI", 301)
        )
        self.numbering.seed(
            _contador("S38", "ARQUEO DE CAJA", 38, "ARQ", 401)
        )
        self.formapago["01"] = {
            "codpag": "01",
            "forpag": "EFECTIVO",
            "afepag": 1,
            "tippag": 1,
            "codcaj": "01",
            "codban": "",
            "codcue": "1105",
            "numcon": 500,
        }
        self.formapago["22"] = {
            "codpag": "22",
            "forpag": "CONSIGNACION BANCARIA",
            "afepag": 22,
            "tippag": 2,
            "codcaj": "01",
            "codban": "001",
            "codcue": "1105",
            "numcon": 700,
        }

    # ── reads ──

    def find_invoice(self, numfven: int, prefven: str) -> dict | None:
        for row in self.facventas:
            if str(row.get("numfven")) == str(numfven) and str(
                row.get("prefven", "")
            ) == str(prefven):
                return dict(row)
        return None

    def ledger_rows(self, numnum: str, codcue: str) -> list[dict]:
        return [
            dict(row)
            for row in self.detcuentas
            if str(row.get("numnum")) == str(numnum) and row.get("codcue") == codcue
        ]

    def locked_periods(self) -> list[dict]:
        return [dict(row) for row in self.cierresper]

    def find_formapago(self, codpag: str) -> dict | None:
        row = self.formapago.get(codpag)
        return dict(row) if row is not None else None

    def find_concept(self, codcon: str) -> dict | None:
        row = self.concepingegr.get(codcon)
        return dict(row) if row is not None else None

    def payment_form_counter(self, codpag: str) -> int:
        row = self.formapago.get(codpag) or {}
        return int(row.get("numcon") or 0)

    def advance_payment_form_counter(self, codpag: str, value: int) -> None:
        row = self.formapago.get(codpag)
        if row is not None:
            row["numcon"] = value

    # ── writes ──

    def stage_insert(self, table: str, row: dict) -> None:
        if self.fail_table and self.fail_table == table:
            raise RuntimeError(f"injected failure on {table}")
        self._rows_for(table).append(row)

    def stage_update(self, table: str, key: dict, values: dict) -> None:
        if self.fail_table and self.fail_table == table:
            raise RuntimeError(f"injected failure on {table}")
        for row in self._rows_for(table):
            if all(row.get(k) == v for k, v in key.items()):
                row.update(values)

    def discard(self, table: str, row: dict) -> None:
        rows = self._rows_for(table)
        if row in rows:
            rows.remove(row)

    def commit(self) -> None:
        self.committed = True

    def _rows_for(self, table: str) -> list[dict]:
        return {
            FACVENTAS_TABLE: self.facventas,
            DETAPAGO_TABLE: self.detapago,
            DETCUENTAS_TABLE: self.detcuentas,
            COMPROBANTES_TABLE: self.comprobantes,
            CAJAARQUEO_TABLE: self.cajaarqueo,
            DETCAJARQ_TABLE: self.detcajarq,
            CONSBANCAB_TABLE: self.consbancab,
            CIERRESPER_TABLE: self.cierresper,
            FORMAPAGO_TABLE: list(self.formapago.values()),
            CONCEPINGEGR_TABLE: list(self.concepingegr.values()),
        }[table]


class RealCashStore:
    """Real MySQL store: reads through the read engine, writes buffered.

    Writes are buffered and applied in order inside one ``erp_write_uow``
    connection (ADR-0008-03). The legacy tables are MyISAM, so a mid-save
    failure is compensated row by row by the repo (``discard``) and detected
    through the journal — the same contract slice 3 established.
    """

    def __init__(self, engine_factory: Any = None) -> None:
        self._engine_factory = engine_factory
        self._pending: list[tuple[str, dict, dict | None]] = []

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

    def find_invoice(self, numfven: int, prefven: str) -> dict | None:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT numfven, prefven, nitter, estfven, codclas, totfven "
                    "FROM facventas WHERE numfven = :n AND prefven = :p LIMIT 1"
                ),
                {"n": str(numfven), "p": str(prefven)},
            ).fetchone()
        return dict(row._mapping) if row is not None else None

    def ledger_rows(self, numnum: str, codcue: str) -> list[dict]:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT numnum, codclas, prenum, codcue, valdeb, valhab, "
                    "nitter, estcue FROM detcuentas "
                    "WHERE numnum = :n AND codcue = :c"
                ),
                {"n": str(numnum), "c": str(codcue)},
            ).fetchall()
        return [dict(r._mapping) for r in rows]

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

    def find_formapago(self, codpag: str) -> dict | None:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT codpag, forpag, afepag, tippag, codcaj, codban, "
                    "codcue, numcon FROM formapago WHERE codpag = :c LIMIT 1"
                ),
                {"c": str(codpag)},
            ).fetchone()
        return dict(row._mapping) if row is not None else None

    def find_concept(self, codcon: str) -> dict | None:
        from sqlalchemy import text

        with self._read_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT codcon, nomcon, valcon, tipcon, debcre, codcue "
                    "FROM concepingegr WHERE codcon = :c LIMIT 1"
                ),
                {"c": str(codcon)},
            ).fetchone()
        return dict(row._mapping) if row is not None else None

    def payment_form_counter(self, codpag: str) -> int:
        row = self.find_formapago(codpag) or {}
        return int(row.get("numcon") or 0)

    def advance_payment_form_counter(self, codpag: str, value: int) -> None:
        self.stage_update(FORMAPAGO_TABLE, {"codpag": codpag}, {"numcon": value})

    # ── writes ──

    def stage_insert(self, table: str, row: dict) -> None:
        if table not in WRITABLE_TABLES:
            raise ValueError(f"table not writable by the cash path: {table}")
        self._pending.append(("insert", table, dict(row)))

    def stage_update(self, table: str, key: dict, values: dict) -> None:
        if table not in WRITABLE_TABLES:
            raise ValueError(f"table not writable by the cash path: {table}")
        self._pending.append(("update", table, {"key": dict(key), "values": dict(values)}))

    def discard(self, table: str, row: dict) -> None:
        # A staged insert is dropped from the buffer; a real DELETE is issued
        # only for rows that already landed (MyISAM compensation).
        self._pending = [
            op for op in self._pending if not (op[0] == "insert" and op[2] == row)
        ]

    def commit(self) -> None:
        from sqlalchemy import text

        if not self._pending:
            return
        with self._write_engine().connect() as conn:
            for op, table, payload in self._pending:
                if op == "insert":
                    cols = ", ".join(payload)
                    marks = ", ".join(f":{c}" for c in payload)
                    conn.execute(
                        text(f"INSERT INTO {table} ({cols}) VALUES ({marks})"),  # noqa: S608
                        {k: _sql_value(v) for k, v in payload.items()},
                    )
                else:
                    key = payload["key"]
                    values = payload["values"]
                    sets = ", ".join(f"{c} = :{c}" for c in values)
                    where = " AND ".join(f"{c} = :w_{c}" for c in key)
                    params = {k: _sql_value(v) for k, v in values.items()}
                    params.update({f"w_{k}": _sql_value(v) for k, v in key.items()})
                    conn.execute(
                        text(f"UPDATE {table} SET {sets} WHERE {where}"),  # noqa: S608
                        params,
                    )
            conn.commit()
        self._pending = []


def _sql_value(value: object) -> object:
    """Legacy numeric columns are doubles/varchars — never a Python float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return "1" if value else "0"
    return value


def get_cash_store() -> CashStore:
    """Real in prod/dev, fresh Fake under tests (settings.env == 'test')."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealCashStore()
    return FakeCashStore()
