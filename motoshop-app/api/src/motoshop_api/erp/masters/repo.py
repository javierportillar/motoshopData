"""Masters repositories: terceros (task 2.1) on the slice-1 save engine.

Masters writes reuse the φ0..φ4 engine (ADR-0008-03) with ``numbering_fn=None``
— catalogs carry no contadores document number, but they still journal
PENDING → COMMITTED (the first legacy insert runs inside the same UoW).

Contract per repo (Fake + Real twins):
- ``create(body, *, tenant, empresa, actor, request_id, idempotency_key)``
- ``update(key, body, *, tenant, empresa, actor, request_id)``
- ``get(key)`` / ``list(...)`` readers for the router.

Error mapping: ``LegacyValidationError`` → 422 aggregate,
``DuplicateMasterError`` → 409, ``ErpSaveFailed`` → 503 retryable,
``LookupError`` → 404.

The Fake twins mirror the legacy transaction reality: one UoW = one staged
batch applied on commit; a simulated mid-save failure leaves already-inserted
MyISAM-style rows for the engine's compensating cleanup (φ3 → cleanup_fn),
exactly like a real MySQL 5.0.45 unit.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from motoshop_api.erp.engine import ErpSaveRequest, save_document
from motoshop_api.erp.masters.schemas import (
    ProductCreate,
    ProductPriceEntry,
    ProductUpdate,
    TerceroCreate,
    TerceroUpdate,
)
from motoshop_api.erp.masters.validators import (
    DuplicateMasterError,
    LegacyValidationError,
    recompute_porutil,
    split_price,
    validate_product_create,
    validate_tercero_create,
    validate_tercero_update,
    validate_transaction_owned_fields,
)

_DICT_TABLES = {"terceros": "nitter", "productos": "codprod"}
_SUFFIX_TABLES = ("tercecorreo", "produndmeds", "preciosxpro", "prodcodbars")


class FakeMastersStore:
    """In-memory legacy tables shared by all masters fakes in one scenario."""

    def __init__(self) -> None:
        self.terceros: dict[str, dict] = {}
        self.tercecorreo: list[dict] = []
        self.productos: dict[str, dict] = {}
        self.produktdmeds: list[dict] = []  # slice 2: productos' produndmeds
        self.preciosxpro: list[dict] = []
        self.prodcodbars: list[dict] = []
        self.fail_table: str | None = None  # inject a simulated insert failure

    def tables(self) -> dict[str, dict | list]:
        return {
            "terceros": self.terceros,
            "tercecorreo": self.tercecorreo,
            "productos": self.productos,
            "produndmeds": self.produktdmeds,
            "preciosxpro": self.preciosxpro,
            "prodcodbars": self.prodcodbars,
        }

    def apply(self, op: str, table: str, payload: dict) -> None:
        """One staged write lands (MyISAM mimic: rows land immediately)."""
        if op == "upsert":
            if table in _DICT_TABLES:
                self.tables()[table][payload[_DICT_TABLES[table]]] = dict(payload)
            else:
                self.tables()[table].append(dict(payload))
            return
        if op == "delete":
            key_field, key_value = payload["field"], payload["value"]
            rows = self.tables()[table]
            rows[:] = [row for row in rows if row.get(key_field) != key_value]
            return
        raise ValueError(f"unsupported op {op}")

    def purge_key(self, kind: str, key: str) -> None:
        """Compensating cleanup for a failed create: drop rows owned by `key`."""
        if kind == "tercero":
            self.terceros.pop(key, None)
            self.tercecorreo = [e for e in self.tercecorreo if e["nitter"] != key]
            return
        if kind == "producto":
            self.productos.pop(key, None)
            for table in _SUFFIX_TABLES[1:]:
                rows = self.tables()[table]
                rows[:] = [row for row in rows if row.get("codprod") != key]
            return
        raise ValueError(f"unknown master kind: {kind}")


class SimulatedDbFailure(ValueError):
    """Injected inside a staged commit to exercise the φ3 failure path."""


class _FakeMastersConn:
    """Fake twin connection: stages writes, applies the batch on commit."""

    def __init__(self, store: FakeMastersStore) -> None:
        self._store = store
        self._staged: list[tuple[str, str, dict]] = []

    def stage_upsert(self, table: str, values: dict) -> None:
        self._staged.append(("upsert", table, values))

    def stage_delete(self, table: str, field: str, value: str) -> None:
        self._staged.append(("delete", table, {"field": field, "value": value}))

    def commit(self) -> None:
        """Apply the staged batch; a simulated failure leaves earlier rows."""
        for i, (op, table, payload) in enumerate(self._staged):
            if self._store.fail_table == table:
                for prior in self._staged[:i]:
                    self._store.apply(*prior)
                self._staged = []
                raise SimulatedDbFailure(f"simulated insert failure on {table}")
            self._store.apply(op, table, payload)
        self._staged = []

    def rollback(self) -> None:
        self._staged = []

    def close(self) -> None:
        self._staged = []


class FakeMastersEngine:
    """Fake twin engine: connect() yields a fresh staged connection."""

    def __init__(self, store: FakeMastersStore) -> None:
        self.store = store

    def connect(self) -> _FakeMastersConn:
        return _FakeMastersConn(self.store)

    def dispose(self) -> None:
        pass


def save_master_document(
    *,
    journal: Any,
    idempotency: Any,
    doc_type: str,
    tenant: str,
    empresa: str,
    actor: str,
    request_id: str,
    idempotency_key: str | None,
    engine: Any,
    write_fn: Callable[[Any], dict],
    cleanup_fn: Callable[[int], None] | None = None,
) -> dict:
    """Run the φ-sequence for a catalog write (no contadores numbering)."""
    codclas = "TER" if doc_type == "tercero" else "PRO"
    request = ErpSaveRequest(
        codclas=codclas,
        pref="",
        doc_type=doc_type,
        tenant=tenant,
        empresa=empresa,
        actor=actor,
        request_id=request_id,
        idempotency_key=idempotency_key or "",
        save_fn=lambda conn, _number: write_fn(conn),
        numbering_fn=None,
        cleanup_fn=cleanup_fn,
        engine=engine,
    )
    return save_document(request, journal=journal, idempotency=idempotency)


def _store_emails(store: FakeMastersStore, nitter: str) -> list[str]:
    return [e["corele"] for e in store.tercecorreo if e["nitter"] == nitter]


def _with_emails(store: FakeMastersStore, row: dict, emails: list[str] | None = None) -> dict:
    return {**row, "emails": row.get("emails") if emails is None else list(emails)}


# ════════════════════════════ Terceros ═══════════════════════════════════


class FakeTercerosRepo:
    """In-memory twin of the terceros write path (validation parity included)."""

    def __init__(self, store: FakeMastersStore, journal=None, idempotency=None):
        self.store = store
        self.journal = journal
        self.idempotency = idempotency
        self.engine = FakeMastersEngine(store) if journal is not None else None

    # ── read side ──
    def get(self, nitter: str) -> dict | None:
        row = self.store.terceros.get(nitter)
        return _with_emails(self.store, dict(row)) if row else None

    def list(self, search: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        rows = [
            _with_emails(self.store, dict(row))
            for key, row in self.store.terceros.items()
            if search.lower() in key or search.lower() in str(row.get("nomcom", "")).lower()
        ]
        return rows[offset : offset + limit]

    # ── write side ──
    def create(
        self, body: TerceroCreate, *, tenant: str, empresa: str, actor: str,
        request_id: str, idempotency_key: str,
    ) -> dict:
        # φ0 hoisted before validation (app_writes convention): replay wins
        stored = self.idempotency.get(idempotency_key) if self.idempotency else None
        if stored is not None:
            return stored

        row = validate_tercero_create(body.model_dump())
        nitter = row["nitter"].strip()
        if nitter in self.store.terceros:
            raise DuplicateMasterError("nitter", nitter)
        emails = list(row["emails"])

        def _write(conn) -> dict:
            core = {k: v for k, v in row.items() if k != "emails"}
            core["nitter"] = nitter
            conn.stage_upsert("terceros", core)
            for email in emails:
                conn.stage_upsert("tercecorreo", {"nitter": nitter, "corele": email})
            return _with_emails(self.store, core, emails)

        def _cleanup(_number) -> None:
            self.store.purge_key("tercero", nitter)

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,
            doc_type="tercero",
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
            engine=self.engine,
            write_fn=_write,
            cleanup_fn=_cleanup,
        )

    def update(
        self, nitter: str, body: TerceroUpdate, *, tenant: str, empresa: str,
        actor: str, request_id: str,
    ) -> dict:
        existing = self.store.terceros.get(nitter)
        if existing is None:
            raise LookupError(nitter)
        validate_tercero_update(body.model_dump(exclude_none=True))

        changes = body.model_dump(exclude_none=True)
        changes.pop("emails", None)
        changes["nitter"] = nitter  # identity immutable; key echo only
        emails = (
            list(body.emails)
            if body.emails is not None
            else _store_emails(self.store, nitter)
        )

        def _write(conn) -> dict:
            if body.emails is not None:
                conn.stage_delete("tercecorreo", "nitter", nitter)
                for email in emails:
                    conn.stage_upsert("tercecorreo", {"nitter": nitter, "corele": email})
            merged = dict(existing)
            merged.update(changes)
            conn.stage_upsert("terceros", merged)
            return _with_emails(self.store, merged, emails)

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,  # edits never read the replay cache
            doc_type="tercero",
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=None,
            engine=self.engine,
            write_fn=_write,
        )


class RealTercerosRepo:
    """Legacy MySQL writes (app_writer engine, single-statement per op)."""

    _INSERT_TER = (
        "INSERT INTO terceros (nitter, tipnit, digter, perjur, apeter, apeter2, "
        "nomter, nomter2, razsoc, nomcom, dirter, telter, movter, codciu, codzon, "
        "codlis, cupblo, inater, regven, feccrea) VALUES "
        "(:nitter, :tipnit, :digter, :perjur, :apeter, :apeter2, :nomter, "
        ":nomter2, :razsoc, :nomcom, :dirter, :telter, :movter, :codciu, :codzon, "
        ":codlis, :cupblo, :inater, 'S', CURDATE())"
    )
    _TER_COLUMNS = (
        "nitter", "tipnit", "digter", "perjur", "apeter", "apeter2", "nomter",
        "nomter2", "razsoc", "nomcom", "dirter", "telter", "movter", "codciu",
        "codzon", "codlis", "cupblo", "inater",
    )

    def __init__(self, journal=None, idempotency=None):
        from motoshop_api.db.engine import get_erp_engine
        from motoshop_api.erp.idempotency import get_idempotency_repo
        from motoshop_api.erp.journal import get_journal_repo

        self.journal = journal or get_journal_repo()
        self.idempotency = idempotency or get_idempotency_repo()
        self.engine_factory = get_erp_engine

    # ── read side ──
    def get(self, nitter: str) -> dict | None:
        from sqlalchemy import text

        from motoshop_api.db.engine import get_engine

        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT nitter, tipnit, digter, perjur, nomter, nomter2, "
                    "apeter, apeter2, razsoc, nomcom, dirter, telter, movter, "
                    "codciu, codzon, codlis, cupblo, inater FROM terceros "
                    "WHERE nitter = :nitter"
                ),
                {"nitter": nitter},
            ).fetchone()
        if row is None:
            return None
        emails = [
            {"nitter": nitter, "corele": e["corele"]}
            for e in self._email_rows(nitter)
        ]
        return {**dict(row._mapping), "emails": emails}

    def list(self, search: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        from sqlalchemy import text

        from motoshop_api.db.engine import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT nitter, tipnit, nomcom, dirter, telter, cupblo, inater "
                    "FROM terceros WHERE (:s = '' OR CONCAT(nitter, ' ', nomcom) "
                    "LIKE CONCAT('%', :s, '%')) ORDER BY nitter LIMIT :l OFFSET :o"
                ),
                {"s": search, "l": limit, "o": offset},
            ).fetchall()
        return [dict(r._mapping) | {"emails": []} for r in rows]

    def _email_rows(self, nitter: str) -> list[dict]:
        from sqlalchemy import text

        from motoshop_api.db.engine import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT nitter, corele FROM tercecorreo WHERE nitter = :n"),
                {"n": nitter},
            ).fetchall()
        return [
            dict(zip(("nitter", "corele"), r, strict=False)) for r in rows
        ]

    # ── write side ──
    def create(self, body: TerceroCreate, **context) -> dict:
        row = validate_tercero_create(body.model_dump())
        nitter = row["nitter"].strip()
        if self.get(nitter) is not None:
            raise DuplicateMasterError("nitter", nitter)
        insert_values = {
            col: (str(row.get(col) or "") if row.get(col) is not None else "")
            for col in self._TER_COLUMNS
        }
        emails = list(row["emails"])

        def _write(conn) -> dict:
            from sqlalchemy import text

            conn.execute(text(self._INSERT_TER), insert_values)
            for email in emails:
                conn.execute(
                    text("INSERT INTO tercecorreo (nitter, corele) VALUES (:n, :e)"),
                    {"n": nitter, "e": email},
                )
            return {**insert_values, "emails": emails}

        def _cleanup(_number) -> None:
            from sqlalchemy import text

            with self.engine_factory().connect() as conn:
                conn.execute(
                    text("DELETE FROM tercecorreo WHERE nitter = :n"), {"n": nitter}
                )
                conn.execute(
                    text("DELETE FROM terceros WHERE nitter = :n"), {"n": nitter}
                )
                conn.commit()

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,
            doc_type="tercero",
            tenant=context["tenant"],
            empresa=context["empresa"],
            actor=context["actor"],
            request_id=context["request_id"],
            idempotency_key=context["idempotency_key"],
            engine=None,
            write_fn=_write,
            cleanup_fn=_cleanup,
        )

    def update(self, nitter: str, body: TerceroUpdate, **context) -> dict:
        current = self.get(nitter)
        if current is None:
            raise LookupError(nitter)
        validate_tercero_update(body.model_dump(exclude_none=True))

        changes = body.model_dump(exclude_none=True)
        changes.pop("emails", None)
        emails = (
            list(body.emails)
            if body.emails is not None
            else [e["corele"] for e in self._email_rows(nitter)]
        )

        def _write(conn) -> dict:
            from sqlalchemy import text

            if changes:
                sets = ", ".join(f"{col} = :{col}" for col in changes)
                conn.execute(
                    text(f"UPDATE terceros SET {sets} WHERE nitter = :n"),
                    {**changes, "n": nitter},
                )
            if body.emails is not None:
                conn.execute(
                    text("DELETE FROM tercecorreo WHERE nitter = :n"), {"n": nitter}
                )
                for email in emails:
                    conn.execute(
                        text("INSERT INTO tercecorreo (nitter, corele) VALUES (:n, :e)"),
                        {"n": nitter, "e": email},
                    )
            return {**current, **changes, "emails": emails}

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,
            doc_type="tercero",
            tenant=context["tenant"],
            empresa=context["empresa"],
            actor=context["actor"],
            request_id=context["request_id"],
            idempotency_key=None,
            engine=None,
            write_fn=_write,
        )


# ════════════════════════════ Productos ══════════════════════════════════

_MONEY_Q = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_Q, rounding=ROUND_HALF_UP)


def _normalize_price(
    entry: ProductPriceEntry, index: int, base_cost: Decimal
) -> dict:
    """Split one price level server-side, fields prefixed for the 422 aggregate.

    Returns the ``preciosxpro`` payload (spec MW-2s3 + modules.md §15):
    ``venprod`` exclusive, ``veniva`` = inclusive − exclusive, ``porutil``
    recomputed from the transaction-owned cost base (0 when no cost yet).
    """
    try:
        exclusive, inclusive, veniva = split_price(
            entry.pvtipo, entry.pvsini, entry.pvconi, entry.iva_rate
        )
    except LegacyValidationError as exc:
        prefixed = {f"prices[{index}].{k}": v for k, v in exc.fields.items()}
        raise LegacyValidationError(prefixed, exc.message) from exc
    return {
        "codlis": str(entry.codlis),
        "pvtipo": entry.pvtipo,
        "pvsini": exclusive,
        "pvconi": inclusive,
        "iva_rate": entry.iva_rate,
        "venprod": _money(exclusive),
        "veniva": veniva,
        "porutil": recompute_porutil(exclusive, base_cost),
        "actupr": "S",  # legacy last-update flag (active list price)
    }


def _registered_barcodes(store: FakeMastersStore, skip: str | None = None) -> set[str]:
    """Every `codbar` legacy knows: `prodcodbars` rows plus `productos.codbar`.

    ``skip`` drops the rows owned by one `codprod` (its own replacement batch).
    """
    bars = {
        row["codbar"]
        for row in store.prodcodbars
        if row["codprod"] != skip
    }
    bars |= {
        str(row.get("codbar") or "").strip()
        for key, row in store.productos.items()
        if key != skip and str(row.get("codbar") or "").strip()
    }
    return bars


def _first_dup(values: list[str]) -> str | None:
    return next((v for v in values if values.count(v) > 1), None)


def _price_view(price: dict) -> dict:
    """Legacy-column projection of a normalized price payload."""
    return {
        k: price[k]
        for k in ("codlis", "pvtipo", "venprod", "veniva", "porutil", "actupr")
    }


def _producto_core_row(body_dump: dict, prices: list[dict]) -> dict:
    """`productos` core row — the first price level seeds pvsini/pvconi/pvtipo."""
    core = {
        k: v
        for k, v in body_dump.items()
        if k not in ("units", "barcodes", "prices", "exiprod")
    }
    if prices:
        first = prices[0]
        core["pvsini"] = _money(first["pvsini"])
        core["pvconi"] = _money(first["pvconi"])
        core["pvtipo"] = first["pvtipo"]
    else:
        core["pvsini"] = Decimal("0.00")
        core["pvconi"] = Decimal("0.00")
        core["pvtipo"] = "1"
    return core


class FakeProductosRepo:
    """In-memory twin of the productos write path (spec MW-2 / MW-3)."""

    def __init__(self, store: FakeMastersStore, journal=None, idempotency=None):
        self.store = store
        self.journal = journal
        self.idempotency = idempotency
        self.engine = FakeMastersEngine(store) if journal is not None else None

    # ── read side ──
    def get(self, codprod: str) -> dict | None:
        row = self.store.productos.get(codprod)
        if row is None:
            return None
        view = dict(row)
        view["units"] = [
            dict(u) for u in self.store.produktdmeds if u["codprod"] == codprod
        ]
        view["barcodes"] = [
            dict(b) for b in self.store.prodcodbars if b["codprod"] == codprod
        ]
        view["prices"] = [
            dict(p) for p in self.store.preciosxpro if p["codprod"] == codprod
        ]
        return view

    def list(self, search: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        needle = search.lower()
        rows = [
            self.get(key)  # type: ignore[arg-type] — cannot be None here
            for key in self.store.productos
            if needle in key.lower()
            or needle in str(self.store.productos[key].get("nomprod", "")).lower()
        ]
        return rows[offset : offset + limit]

    # ── write side ──
    def create(
        self, body: ProductCreate, *, tenant: str, empresa: str, actor: str,
        request_id: str, idempotency_key: str,
    ) -> dict:
        # φ0 hoisted before validation (app_writes convention): replay wins
        stored = self.idempotency.get(idempotency_key) if self.idempotency else None
        if stored is not None:
            return stored

        dump = body.model_dump()
        row = validate_product_create(dump)
        codprod = str(row["codprod"]).strip()
        if codprod in self.store.productos:
            raise DuplicateMasterError("codprod", codprod)

        bars = [str(e.codbar) for e in body.barcodes]
        if body.codbar:
            bars = [str(body.codbar), *bars]
        registered = _registered_barcodes(self.store)
        collision = next(iter(registered & set(bars)), None)
        if collision is None:
            collision = _first_dup(bars)
        if collision:
            raise DuplicateMasterError("codbar", collision)

        prices = [
            _normalize_price(entry, i, Decimal("0"))  # no cost yet on creation
            for i, entry in enumerate(body.prices)
        ]
        units = [u.model_dump() for u in body.units]
        core = _producto_core_row(dump, prices)

        def _write(conn) -> dict:
            conn.stage_upsert("productos", core)
            for unit in units:
                conn.stage_upsert("produndmeds", {"codprod": codprod, **unit})
            for barcode in bars:
                conn.stage_upsert(
                    "prodcodbars", {"codprod": codprod, "codbar": barcode}
                )
            for price in prices:
                conn.stage_upsert("preciosxpro", {
                    "codprod": codprod,
                    "codlis": price["codlis"],
                    "pvtipo": price["pvtipo"],
                    "venprod": price["venprod"],
                    "veniva": price["veniva"],
                    "porutil": price["porutil"],
                    "actupr": price["actupr"],
                })
            return {
                **core,
                "units": [{"codprod": codprod, **u} for u in units],
                "barcodes": [{"codprod": codprod, "codbar": b} for b in bars],
                "prices": [{"codprod": codprod, **p} for p in prices],
            }

        def _cleanup(_number) -> None:
            self.store.purge_key("producto", codprod)

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,
            doc_type="producto",
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
            engine=self.engine,
            write_fn=_write,
            cleanup_fn=_cleanup,
        )

    def update(
        self, codprod: str, body: ProductUpdate, *, tenant: str, empresa: str,
        actor: str, request_id: str,
    ) -> dict:
        existing = self.store.productos.get(codprod)
        if existing is None:
            raise LookupError(codprod)
        changes = body.model_dump(exclude_none=True)
        validate_transaction_owned_fields(changes)  # MW-3s2, aggregate 422

        prices = (
            [
                _normalize_price(
                    entry, i, Decimal(str(existing.get("cosprod") or 0))
                )
                for i, entry in enumerate(body.prices)  # type: ignore[union-attr]
            ]
            if body.prices is not None
            else None
        )
        units = (
            [u.model_dump() for u in body.units]  # type: ignore[union-attr]
            if body.units is not None
            else None
        )
        bars = (
            [str(b.codbar) for b in body.barcodes]  # type: ignore[union-attr]
            if body.barcodes is not None
            else None
        )
        if bars is not None:
            registered = _registered_barcodes(self.store, skip=codprod)
            if body.codbar:
                bars = [str(body.codbar), *bars]
            collision = next(iter(registered & set(bars)), None)
            if collision is None:
                collision = _first_dup(bars)
            if collision:
                raise DuplicateMasterError("codbar", collision)

        merged = dict(existing)
        merged.update({
            k: v for k, v in changes.items() if k not in ("units", "barcodes", "prices")
        })
        if prices:
            merged["pvsini"] = _money(prices[0]["pvsini"])
            merged["pvconi"] = _money(prices[0]["pvconi"])
            merged["pvtipo"] = prices[0]["pvtipo"]

        def _write(conn) -> dict:
            if prices is not None:
                conn.stage_delete("preciosxpro", "codprod", codprod)
                for price in prices:
                    conn.stage_upsert("preciosxpro", {
                        "codprod": codprod,
                        "codlis": price["codlis"],
                        "pvtipo": price["pvtipo"],
                        "venprod": price["venprod"],
                        "veniva": price["veniva"],
                        "porutil": price["porutil"],
                        "actupr": price["actupr"],
                    })
            if units is not None:
                conn.stage_delete("produndmeds", "codprod", codprod)
                for unit in units:
                    conn.stage_upsert("produndmeds", {"codprod": codprod, **unit})
            if bars is not None:
                conn.stage_delete("prodcodbars", "codprod", codprod)
                for barcode in bars:
                    conn.stage_upsert(
                        "prodcodbars", {"codprod": codprod, "codbar": barcode}
                    )
            conn.stage_upsert("productos", merged)
            prior = self.get(codprod) or {}
            return {
                **merged,
                "units": (
                    [{"codprod": codprod, **u} for u in units]
                    if units is not None else prior.get("units", [])
                ),
                "barcodes": (
                    [{"codprod": codprod, "codbar": b} for b in bars]
                    if bars is not None else prior.get("barcodes", [])
                ),
                "prices": (
                    [{"codprod": codprod, **p} for p in prices]
                    if prices is not None else prior.get("prices", [])
                ),
            }

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,  # edits never read the replay cache
            doc_type="producto",
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=None,
            engine=self.engine,
            write_fn=_write,
        )


class RealProductosRepo:
    """Legacy MySQL writes for productos + `produndmeds` + `preciosxpro`
    + `prodcodbars` (app_writer engine, single-statement per op)."""

    _PRO_COLUMNS = (
        "codprod", "nomprod", "codbar", "codmed", "valmed", "codlin1",
        "actprod", "stockmin", "stockmax", "desprod", "pvsini", "pvconi",
        "pvtipo",
    )
    _INSERT_PRO = (
        "INSERT INTO productos (codprod, nomprod, codbar, codmed, valmed, "
        "codlin1, actprod, stockmin, stockmax, desprod, pvsini, pvconi, "
        "pvtipo) VALUES (:codprod, :nomprod, :codbar, :codmed, :valmed, "
        ":codlin1, :actprod, :stockmin, :stockmax, :desprod, :pvsini, "
        ":pvconi, :pvtipo)"
    )

    def __init__(self, journal=None, idempotency=None):
        from motoshop_api.db.engine import get_erp_engine
        from motoshop_api.erp.idempotency import get_idempotency_repo
        from motoshop_api.erp.journal import get_journal_repo

        self.journal = journal or get_journal_repo()
        self.idempotency = idempotency or get_idempotency_repo()
        self.engine_factory = get_erp_engine

    # ── read side ──
    def get(self, codprod: str) -> dict | None:
        from sqlalchemy import text

        from motoshop_api.db.engine import get_engine

        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT codprod, nomprod, codbar, codmed, valmed, codlin1, "
                    "actprod, stockmin, stockmax, desprod, pvsini, pvconi, "
                    "pvtipo FROM productos WHERE codprod = :c"
                ),
                {"c": codprod},
            ).fetchone()
        if row is None:
            return None
        view = dict(row._mapping)
        view["units"] = [
            dict(zip(
                ("codprod", "codmed", "divmul", "facumed", "pventa", "tipovc"),
                r,
                strict=False,
            ))
            for r in conn.execute(
                text(
                    "SELECT codprod, codmed, divmul, facumed, pventa, tipovc "
                    "FROM produndmeds WHERE codprod = :c"
                ),
                {"c": codprod},
            ).fetchall()
        ]
        view["barcodes"] = [
            dict(zip(("codprod", "codbar"), r, strict=False))
            for r in conn.execute(
                text(
                    "SELECT codprod, codbar FROM prodcodbars WHERE codprod = :c"
                ),
                {"c": codprod},
            ).fetchall()
        ]
        view["prices"] = [
            dict(zip(
                ("codprod", "codlis", "pvtipo", "venprod", "veniva", "porutil", "actupr"),
                r,
                strict=False,
            ))
            for r in conn.execute(
                text(
                    "SELECT codprod, codlis, pvtipo, venprod, veniva, porutil, "
                    "actupr FROM preciosxpro WHERE codprod = :c"
                ),
                {"c": codprod},
            ).fetchall()
        ]
        return view

    def list(self, search: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        from sqlalchemy import text

        from motoshop_api.db.engine import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT codprod, nomprod, codmed, codlin1, actprod, "
                    "pvsini, pvconi, pvtipo FROM productos "
                    "WHERE (:s = '' OR CONCAT(codprod, ' ', nomprod) "
                    "LIKE CONCAT('%', :s, '%')) ORDER BY codprod "
                    "LIMIT :l OFFSET :o"
                ),
                {"s": search, "l": limit, "o": offset},
            ).fetchall()
        return [
            dict(r._mapping)
            | {"units": [], "barcodes": [], "prices": []}
            for r in rows
        ]

    def _registered_barcodes(self, skip: str | None = None) -> set[str]:
        from sqlalchemy import text

        from motoshop_api.db.engine import get_engine

        with get_engine().connect() as conn:
            bars = conn.execute(
                text("SELECT codbar FROM prodcodbars"), {}
            ).fetchall()
            products = conn.execute(
                text("SELECT codprod, codbar FROM productos"), {}
            ).fetchall()
        owned = {
            r[0]
            for r in products
            if r[0] != skip and str(r[1] or "").strip()
        }
        return {row[0] for row in bars} | owned

    # ── write side ──
    def create(self, body: ProductCreate, **context) -> dict:
        dump = body.model_dump()
        row = validate_product_create(dump)
        codprod = str(row["codprod"]).strip()
        if self.get(codprod) is not None:
            raise DuplicateMasterError("codprod", codprod)
        registered = self._registered_barcodes()
        bars = [str(e.codbar) for e in body.barcodes]
        if body.codbar:
            bars = [str(body.codbar), *bars]
        collision = next(iter(registered & set(bars)), None)
        if collision is None:
            collision = _first_dup(bars)
        if collision:
            raise DuplicateMasterError("codbar", collision)
        prices = [
            _normalize_price(entry, i, Decimal("0"))
            for i, entry in enumerate(body.prices)
        ]
        core = _producto_core_row(dump, prices)
        insert_values = {
            col: (str(core[col]) if core.get(col) is not None else "")
            for col in self._PRO_COLUMNS
        }
        units = [{**u.model_dump(), "codprod": codprod} for u in body.units]
        price_rows = [
            {
                "codprod": codprod,
                "codlis": p["codlis"],
                "pvtipo": p["pvtipo"],
                "venprod": str(p["venprod"]),
                "veniva": str(p["veniva"]),
                "porutil": str(p["porutil"]),
                "actupr": p["actupr"],
            }
            for p in prices
        ]

        def _write(conn) -> dict:
            from sqlalchemy import text

            conn.execute(text(self._INSERT_PRO), insert_values)
            for unit in units:
                conn.execute(
                    text(
                        "INSERT INTO produndmeds (codprod, codmed, divmul, "
                        "facumed, pventa, tipovc) VALUES (:codprod, :codmed, "
                        ":divmul, :facumed, :pventa, :tipovc)"
                    ),
                    {k: str(v) for k, v in unit.items()},
                )
            for barcode in bars:
                conn.execute(
                    text(
                        "INSERT INTO prodcodbars (codprod, codbar) "
                        "VALUES (:codprod, :codbar)"
                    ),
                    {"codprod": codprod, "codbar": barcode},
                )
            for price_row in price_rows:
                conn.execute(
                    text(
                        "INSERT INTO preciosxpro (codprod, codlis, pvtipo, "
                        "venprod, veniva, porutil, actupr) VALUES (:codprod, "
                        ":codlis, :pvtipo, :venprod, :veniva, :porutil, :actupr)"
                    ),
                    price_row,
                )
            return {
                **insert_values,
                "units": units,
                "barcodes": [{"codprod": codprod, "codbar": b} for b in bars],
                "prices": price_rows,
            }

        def _cleanup(_number) -> None:
            from sqlalchemy import text

            with self.engine_factory().connect() as conn:
                for table in ("preciosxpro", "prodcodbars", "produndmeds", "productos"):
                    conn.execute(
                        text(f"DELETE FROM {table} WHERE codprod = :c"),
                        {"c": codprod},
                    )
                conn.commit()

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,
            doc_type="producto",
            tenant=context["tenant"],
            empresa=context["empresa"],
            actor=context["actor"],
            request_id=context["request_id"],
            idempotency_key=context["idempotency_key"],
            engine=None,
            write_fn=_write,
            cleanup_fn=_cleanup,
        )

    def update(self, codprod: str, body: ProductUpdate, **context) -> dict:
        current = self.get(codprod)
        if current is None:
            raise LookupError(codprod)
        changes = body.model_dump(exclude_none=True)
        validate_transaction_owned_fields(changes)  # MW-3s2, aggregate 422

        changes_flat = {
            k: v
            for k, v in changes.items()
            if k not in ("units", "barcodes", "prices")
        }
        prices = None
        if body.prices is not None:
            base_cost = Decimal(str(current.get("cosprod") or 0))
            prices = [
                _normalize_price(entry, i, base_cost)
                for i, entry in enumerate(body.prices)
            ]
            changes_flat["pvsini"] = str(_money(prices[0]["pvsini"]))
            changes_flat["pvconi"] = str(_money(prices[0]["pvconi"]))
            changes_flat["pvtipo"] = prices[0]["pvtipo"]

        def _write(conn) -> dict:
            from sqlalchemy import text

            if changes_flat:
                sets = ", ".join(f"{col} = :{col}" for col in changes_flat)
                params = {
                    col: (str(val) if val is not None else "")
                    for col, val in changes_flat.items()
                }
                conn.execute(
                    text(f"UPDATE productos SET {sets} WHERE codprod = :c"),
                    {**params, "c": codprod},
                )
            if body.units is not None:
                conn.execute(
                    text("DELETE FROM produndmeds WHERE codprod = :c"),
                    {"c": codprod},
                )
                for unit in body.units:
                    values = {"codprod": codprod, **unit.model_dump()}
                    conn.execute(
                        text(
                            "INSERT INTO produndmeds (codprod, codmed, divmul, "
                            "facumed, pventa, tipovc) VALUES (:codprod, :codmed, "
                            ":divmul, :facumed, :pventa, :tipovc)"
                        ),
                        {k: str(v) for k, v in values.items()},
                    )
            if body.barcodes is not None:
                conn.execute(
                    text("DELETE FROM prodcodbars WHERE codprod = :c"),
                    {"c": codprod},
                )
                for barcode in body.barcodes:
                    conn.execute(
                        text(
                            "INSERT INTO prodcodbars (codprod, codbar) "
                            "VALUES (:codprod, :codbar)"
                        ),
                        {"codprod": codprod, "codbar": str(barcode.codbar)},
                    )
            if prices is not None:
                conn.execute(
                    text("DELETE FROM preciosxpro WHERE codprod = :c"),
                    {"c": codprod},
                )
                for price in prices:
                    conn.execute(
                        text(
                            "INSERT INTO preciosxpro (codprod, codlis, pvtipo, "
                            "venprod, veniva, porutil, actupr) VALUES (:codprod, "
                            ":codlis, :pvtipo, :venprod, :veniva, :porutil, :actupr)"
                        ),
                        {
                            "codprod": codprod,
                            "codlis": price["codlis"],
                            "pvtipo": price["pvtipo"],
                            "venprod": str(price["venprod"]),
                            "veniva": str(price["veniva"]),
                            "porutil": str(price["porutil"]),
                            "actupr": price["actupr"],
                        },
                    )
            return {
                **current,
                **changes_flat,
                "prices": (
                    [{"codprod": codprod, **_price_view(p)} for p in prices]
                    if prices is not None else current.get("prices", [])
                ),
            }

        return save_master_document(
            journal=self.journal,
            idempotency=self.idempotency,
            doc_type="producto",
            tenant=context["tenant"],
            empresa=context["empresa"],
            actor=context["actor"],
            request_id=context["request_id"],
            idempotency_key=None,
            engine=None,
            write_fn=_write,
        )


# ════════════════════════════ Factory ════════════════════════════════════


def get_terceros_repo() -> FakeTercerosRepo | RealTercerosRepo:
    """Real in prod/dev, fresh Fake under tests (settings.env == 'test')."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealTercerosRepo()
    return FakeTercerosRepo(FakeMastersStore())


def get_productos_repo() -> FakeProductosRepo | RealProductosRepo:
    """Real in prod/dev, fresh Fake under tests (settings.env == 'test')."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealProductosRepo()
    return FakeProductosRepo(FakeMastersStore())
