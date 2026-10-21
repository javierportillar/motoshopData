"""Contadores numbering service — the φ2 reservation hook (ADR-0008-03).

Legacy parity (code_analysis §3, sgHermes `Conta_ResFV` / `Bus_Con_Act` /
`Valid_NumFin`):

1. Serialize on the shared counter: the desktop uses ``LOCK TABLES contadores
   WRITE``; the web reservation takes the same exclusive latch (bounded
   lock-wait window, default 5 s — a desktop lock holder delays the web save,
   it never double-books a number).
2. ``Bus_Con_Act`` heal: if the counter lags behind the doc table
   (``conres <= MAX(number)``), it is auto-corrected to ``MAX+1`` before
   assigning — a crashed web/desktop save never re-issues a used number.
3. ``Valid_NumFin`` window: the assigned number must satisfy
   ``numini <= n <= numfin``; outside the range the save is rejected with an
   explicit resolver-range message and NO counter increment persists.
4. ``numauto != 'SI'`` doc types are hand-numbered on the desktop; the web
   API MUST NOT hand out numbers for them (SI-1s2, 422 at the router).

MySQL 5.0.45 constraint: ``LOCK TABLES`` implicitly commits and cannot be
nested inside the φ3 unit — numbering serializes BEFORE the document unit
(ADR-0008-03). The ``conres+1`` write is autocommitted inside the latch; a
φ3 crash is healed by ``release()`` (optimistic walk-back) or the watchdog
heal job (``Bus_Con_Act`` redoes MAX+1).
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol


class ManualNumberingForbidden(Exception):
    """The doc type is hand-numbered on the desktop (`numauto != 'SI'`)."""


class ResolverRangeError(Exception):
    """The next number falls outside the resolution window (Valid_NumFin)."""


class CounterLockTimeout(Exception):
    """The bounded contadores lock-wait window expired (retryable, 503)."""


@dataclass(frozen=True)
class ContadorRow:
    """`contadores` row (blueprint §3.1, verified columns)."""

    codcon: str
    descon: str = ""
    numcon: int = 0
    numini: int | None = None
    numfin: int | None = None
    numauto: str = "SI"
    preres: str = ""
    conres: int = 1
    actcon: str = "S"
    tipclas: str = ""


class ContadoresRepo(Protocol):
    """Contract shared by the Fake twin and the real MySQL repo."""

    def reserve(
        self, *, codcon: str, pref: str, doc_table: str, num_field: str,
        lock_wait_seconds: float = 5.0,
    ) -> int: ...

    def release(self, *, codcon: str, pref: str, number: int) -> None: ...

    def resolve_prefix(self, codcon: str) -> str:
        """The `preres` prefix configured for a doc type (legacy parity).

        The desktop reads the prefix FROM the counter row
        (`Conta_ResFV`: `SELECT conres, preres … WHERE codcon = …`), so the
        web writer never hard-codes it.
        """
        ...


def _as_int(value: object) -> int:
    """Legacy varchar numerics → int (counters/numbers are whole values)."""
    if isinstance(value, int):
        return value
    try:
        return int(Decimal(str(value).strip().replace(" ", "") or "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"unparseable legacy numeric: {value!r}") from exc


def _validate_window(row: ContadorRow, number: int) -> None:
    """Valid_NumFin parity: numini <= number <= numfin (blueprint §3.1)."""
    low = _as_int(row.numini) if row.numini is not None else None
    high = _as_int(row.numfin) if row.numfin is not None else None
    if low is not None and number < low:
        raise ResolverRangeError(
            f"El número {number} es menor que la numeración inicial "
            f"(numini={low}) para {row.codcon}/{row.preres}"
        )
    if high is not None and number > high:
        raise ResolverRangeError(
            f"El nuevo número de documento {number} es mayor que la "
            f"numeración final (numfin={high}), debe ampliar la numeración "
            f"final para {row.codcon}/{row.preres}"
        )


# ════════════════════════════ Fake (tests) ══════════════════════════════


@dataclass
class FakeContadoresRepo:
    """In-memory contadores twin; thread-safe serialized reservations.

    ``acquire_debug()``/``release_debug()`` simulate a desktop process
    holding the ``contadores WRITE`` latch so the bounded-wait contract is
    testable without MySQL (real-MySQL variant lives in the 3.6 suite).
    """

    rows: dict[tuple[str, str], ContadorRow] = field(default_factory=dict)
    doc_numbers: dict[tuple[str, str, str], list[int]] = field(
        default_factory=dict
    )
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _debug_held: bool = field(default=False, repr=False)

    def seed(self, row: ContadorRow) -> None:
        self.rows[(row.codcon, row.preres)] = row

    def seed_doc_numbers(
        self, doc_table: str, codcon: str, pref: str, numbers: list[int]
    ) -> None:
        self.doc_numbers[(doc_table, codcon, pref)] = list(numbers)

    def read(self, codcon: str, pref: str) -> ContadorRow:
        key = (codcon, pref)
        if key not in self.rows:
            raise LookupError(f"contadores row not seeded: {key}")
        return self.rows[key]

    def resolve_prefix(self, codcon: str) -> str:
        """The prefix configured for a doc type (the counter row owns it)."""
        for (row_codcon, preres) in self.rows:
            if row_codcon == codcon:
                return preres
        raise LookupError(f"contadores row not seeded: codcon={codcon}")

    def acquire_debug(self) -> None:
        """Hold the latch from a foreign thread (desktop lock simulation).

        The holder thread owns the RLock, mirroring a desktop process that
        acquired ``LOCK TABLES contadores WRITE`` in its own session.
        """
        self._holder_ready = threading.Event()
        self._holder_release = threading.Event()

        def _hold() -> None:
            self._lock.acquire()
            self._holder_ready.set()
            self._holder_release.wait()
            self._lock.release()

        threading.Thread(target=_hold, daemon=True).start()
        self._holder_ready.wait(timeout=5)
        self._debug_held = True

    def release_debug(self) -> None:
        self._holder_release.set()
        self._debug_held = False

    def _max_used(self, codcon: str, pref: str, doc_table: str) -> int:
        numbers = self.doc_numbers.get((doc_table, codcon, pref), [])
        return max(numbers) if numbers else 0

    def reserve(
        self, *, codcon: str, pref: str, doc_table: str, num_field: str,
        lock_wait_seconds: float = 5.0,
    ) -> int:
        key = (codcon, pref)
        locked = False
        if self._debug_held:
            locked = self._lock.acquire(timeout=lock_wait_seconds)
            if not locked:
                raise CounterLockTimeout(
                    "contadores latch held beyond the bounded lock-wait window"
                )
        try:
            with self._lock:
                row = self.rows[key]
                if str(row.numauto).upper() != "SI":
                    raise ManualNumberingForbidden(
                        f"El tipo de documento {codcon}/{pref} no es de "
                        f"numeración automática (numauto='{row.numauto}'); "
                        "el web no puede numerar manualmente"
                    )
                # Bus_Con_Act heal: never re-issue an already-used number
                max_used = self._max_used(codcon, pref, doc_table)
                conres = _as_int(row.conres)
                if conres <= max_used:
                    conres = max_used + 1
                    self.rows[key] = ContadorRow(
                        **{**row.__dict__, "conres": conres}
                    )
                _validate_window(self.rows[key], conres)
                # optimistic switch guard (legacy: WHERE conres <= anterior)
                self.rows[key] = ContadorRow(
                    **{**self.rows[key].__dict__, "conres": conres + 1}
                )
                return conres
        finally:
            if locked:
                self._lock.release()

    def release(self, *, codcon: str, pref: str, number: int) -> None:
        with self._lock:
            row = self.rows[(codcon, pref)]
            if _as_int(row.conres) == number + 1:
                self.rows[(codcon, pref)] = ContadorRow(
                    **{**row.__dict__, "conres": number}
                )


# ════════════════════════════ Real (MySQL) ══════════════════════════════


class RealContadoresRepo:
    """``LOCK TABLES contadores WRITE`` reservation against MySQL 5.0.45.

    Runs on its own autocommitted connection (LOCK TABLES implicitly commits
    in 5.0 and cannot live inside the φ3 unit). The bounded lock-wait window
    is enforced client-side: the ``LOCK TABLES`` statement runs on a worker
    thread and a watchdog closes the connection if the latch is not granted
    within ``lock_wait_seconds`` (desktop lock holder → retryable timeout,
    never a silent double-book).
    """

    def __init__(
        self, engine_factory: object | None = None,
        lock_wait_seconds: float = 5.0,
    ):
        self._engine_factory = engine_factory
        self._lock_wait_seconds = lock_wait_seconds

    def _connect(self):
        if self._engine_factory is not None:
            return self._engine_factory().connect()
        from motoshop_api.db.engine import get_erp_engine

        return get_erp_engine().connect()

    def _read_row(self, cur, codcon: str, pref: str) -> ContadorRow:
        cur.execute(
            "SELECT codcon, descon, numcon, numini, numfin, numauto, preres, "
            "conres, actcon, tipclas FROM contadores "
            "WHERE codcon = %s AND preres = %s",
            (codcon, pref),
        )
        raw = cur.fetchone()
        if raw is None:
            raise LookupError(
                f"contadores row not found: codcon={codcon} preres={pref}"
            )
        return ContadorRow(
            codcon=raw[0], descon=raw[1] or "", numcon=_as_int(raw[2]),
            numini=None if raw[3] in (None, "") else _as_int(raw[3]),
            numfin=None if raw[4] in (None, "") else _as_int(raw[4]),
            numauto=raw[5] or "SI", preres=raw[6] or "",
            conres=_as_int(raw[7]), actcon=raw[8] or "S", tipclas=raw[9] or "",
        )

    def _max_used(
        self, cur, doc_table: str, codcon: str, pref: str, num_field: str
    ) -> int:
        """Bus_Con_Act: MAX(doc number) for the (codclas, prefix) pair.

        Doc numbers are legacy varchar numerics: MAX(CAST(... AS SIGNED))
        keeps the ordering numeric (MySQL 5.0-compatible, no window fns).
        """
        cur.execute(
            f"SELECT MAX(CAST({num_field} AS SIGNED)) FROM {doc_table} "  # noqa: S608
            "WHERE codclas = %s AND prefven = %s",
            (codcon, pref),
        )
        raw = cur.fetchone()
        return _as_int(raw[0]) if raw and raw[0] is not None else 0

    def reserve(
        self, *, codcon: str, pref: str, doc_table: str, num_field: str,
        lock_wait_seconds: float | None = None,
    ) -> int:
        wait = self._lock_wait_seconds if lock_wait_seconds is None \
            else lock_wait_seconds
        conn = self._connect()

        granted = threading.Event()
        failure: list[Exception] = []

        def _latch() -> None:
            try:
                cur = conn.cursor()
                cur.execute(
                    f"LOCK TABLES contadores WRITE, {doc_table} READ"  # noqa: S608
                )
                granted.set()
            except Exception as exc:  # noqa: BLE001 — surfaced to the caller
                failure.append(exc)
                granted.set()

        worker = threading.Thread(target=_latch, daemon=True)
        worker.start()
        if not worker.join(timeout=wait) or (
            not granted.wait(timeout=0) and worker.is_alive()
        ):
            # Watchdog: close the connection so the blocked LOCK TABLES
            # aborts server-side and the session releases any partial latch.
            with contextlib.suppress(Exception):
                conn.close()
            raise CounterLockTimeout(
                f"LOCK TABLES contadores no concedido en {wait:.0f}s "
                "(ventana de espera acotada agotada)"
            )
        if failure:
            with contextlib.suppress(Exception):
                conn.close()
            raise failure[0]

        try:
            cur = conn.cursor()
            row = self._read_row(cur, codcon, pref)
            if str(row.numauto).upper() != "SI":
                raise ManualNumberingForbidden(
                    f"El tipo de documento {codcon}/{pref} no es de "
                    f"numeración automática (numauto='{row.numauto}'); "
                    "el web no puede numerar manualmente"
                )
            conres = _as_int(row.conres)
            max_used = self._max_used(
                cur, doc_table, codcon, pref, num_field
            )
            if conres <= max_used:
                conres = max_used + 1
            _validate_window(row, conres)
            cur.execute(
                "UPDATE contadores SET conres = %s "
                "WHERE codcon = %s AND preres = %s AND conres = %s",
                (conres + 1, codcon, pref, _as_int(row.conres)),
            )
            if cur.rowcount == 0:
                raise CounterLockTimeout(
                    "conres cambió durante la reserva (switch guard); reintente"
                )
            conn.commit()
            return conres
        finally:
            with contextlib.suppress(Exception):
                cur2 = conn.cursor()
                cur2.execute("UNLOCK TABLES")
                conn.commit()
            with contextlib.suppress(Exception):
                conn.close()

    def release(self, *, codcon: str, pref: str, number: int) -> None:
        """φ2 failure: walk the counter back ONLY if it still sits on n+1."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE contadores SET conres = %s "
                "WHERE codcon = %s AND preres = %s AND conres = %s",
                (number, codcon, pref, number + 1),
            )
            conn.commit()
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    def resolve_prefix(self, codcon: str) -> str:
        """The prefix (`preres`) configured for a doc type (legacy parity)."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT preres FROM contadores WHERE codcon = %s LIMIT 1",
                (codcon,),
            )
            raw = cur.fetchone()
        finally:
            with contextlib.suppress(Exception):
                conn.close()
        if raw is None or not str(raw[0] or "").strip():
            raise LookupError(f"contadores row not found: codcon={codcon}")
        return str(raw[0]).strip()
