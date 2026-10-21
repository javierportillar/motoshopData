"""Annulment & full reversal repos (slice 5 — tasks 5.1–5.4).

Legacy parity (docs/hermes/code_analysis §7.8 — ``Boteliminar.cs``):

1. **The guard chain runs fail-fast in the legacy order**:
   ``Veri_Anul`` (already annulled → 409) → ``Hay_Cie_Eli`` (date inside a
   closed period → 409) → ``Valid_EdiDocele`` (electronic document already
   accepted by DIAN → 409) → the role gate (N049 → 403) → the mandatory
   reason (→ 422). Nothing is written before the chain passes.
2. **The reversal is ONE unit of work**: the header flag
   (``estfven``/``estado``/``estegr``/``estarq``), EVERY accounting entry
   (``detcuentas.estcue``), EVERY payment row (``detapago.estado``) and EVERY
   financing row (``financiacion.estfin``) of that exact document number are
   flipped to ``'A'`` together.
3. **Stock is recomputed from the kardex truth** (``detcuentas`` inventory
   postings — ``AcInv_Eli_Anul``/``Recal_Cat`` parity), never blind-added
   back: when the document posted its own kardex rows the whole movement
   history is recomputed with the annulled document excluded; when it did not
   (the web write path), the document's own movement is restored.
4. **The audit row lands in ``motanudoc``** (reason truncated to 800 chars,
   ``tipo='A'``) and the document's ``app_doc_journal`` row is mirrored to
   ``ANNULLED``. The annulment itself is idempotent: a retry under the same
   ``Idempotency-Key`` replays the stored response without a second audit row.

Numbers are NEVER released: an annulled document keeps its number occupied
(the counter does not walk back), so the number can never be re-issued.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from motoshop_api.erp.annulment.schemas import MOTANU_MAX_LEN, AnnulmentRequest
from motoshop_api.erp.annulment.store import (
    DETAPAGO_TABLE,
    DETCUENTAS_TABLE,
    DOCUMENT_FAMILIES,
    FINANCIACION_TABLE,
    MOTANUDOC_TABLE,
    PRODUCTOS_TABLE,
    document_family,
)
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import (
    ERP_ERP_MANAGEMENT_ROLES,
    assert_period_open,
)
from motoshop_api.erp.idempotency import IdempotencyRepo
from motoshop_api.erp.journal import JournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError

logger = logging.getLogger(__name__)

#: Journal/audit document type of an annulment.
ANNULMENT_DOC_TYPE = "anulacion_documento"

#: Legacy ``motanudoc.tipo`` of an annulment (``'M'`` is the modification).
MOTANUDOC_TIPO_ANULADO = "A"

#: ``estfele`` values that mean the electronic document was ACCEPTED by DIAN
#: (``Valid_EdiDocele`` — an accepted document is never modified locally).
ACCEPTED_ELECTRONIC_STATES = frozenset({"1", "2"})

#: Roles allowed to annul (legacy ``N049`` — admin/gerente only).
ANNULMENT_ROLES = frozenset(ERP_ERP_MANAGEMENT_ROLES)

ZERO = Decimal("0")


def _dec(value: object) -> Decimal:
    """Legacy numeric (str/Decimal/double) → Decimal, exact."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


# ═══════════════════════ domain errors (mapped by the router) ═══════════


class AlreadyAnnulledError(Exception):
    """409: ``Veri_Anul`` — the document is already annulled (AN-1s1)."""

    code = "document_annulled"

    def __init__(self, message: str, *, codclas: str = "", numnum: str = ""):
        super().__init__(message)
        self.message = message
        self.codclas = codclas
        self.numnum = numnum

    def detail(self) -> dict:
        return {
            "message": self.message,
            "code": self.code,
            "document": {"codclas": self.codclas, "numnum": self.numnum},
        }


class ElectronicDocumentError(Exception):
    """409: ``Valid_EdiDocele`` — DIAN already accepted the document (AN-1s3)."""

    code = "electronic_document_accepted"

    def __init__(self, message: str, *, codclas: str = "", numnum: str = ""):
        super().__init__(message)
        self.message = message
        self.codclas = codclas
        self.numnum = numnum

    def detail(self) -> dict:
        return {
            "message": self.message,
            "code": self.code,
            "document": {"codclas": self.codclas, "numnum": self.numnum},
        }


class AnnulmentForbiddenError(Exception):
    """403: the actor does not hold the annulment permission (AN-1s5)."""

    code = "forbidden"

    def __init__(self, message: str, *, role: str = ""):
        super().__init__(message)
        self.message = message
        self.role = role

    def detail(self) -> dict:
        return {"message": self.message, "code": self.code, "role": self.role}


class DocumentNotFoundError(Exception):
    """404: there is no document of that class and number."""

    code = "document_not_found"

    def __init__(self, message: str, *, codclas: str = "", numnum: str = ""):
        super().__init__(message)
        self.message = message
        self.codclas = codclas
        self.numnum = numnum

    def detail(self) -> dict:
        return {
            "message": self.message,
            "code": self.code,
            "document": {"codclas": self.codclas, "numnum": self.numnum},
        }


# ═══════════════════════ the ordered guard chain (AN-1s1..s5) ═══════════


def assert_annulment_allowed(
    *,
    document: dict,
    periods: list[dict],
    actor_role: str,
    motivo: str,
    codclas: str = "",
    numfven: object = "",
) -> None:
    """The legacy fail-fast guard chain — legacy order, one reason per guard.

    1. ``Veri_Anul``       — already annulled → :class:`AlreadyAnnulledError`.
    2. ``Hay_Cie_Eli``     — closed period → :class:`PeriodLockedError`.
    3. ``Valid_EdiDocele`` — DIAN accepted → :class:`ElectronicDocumentError`.
    4. the role gate      — → :class:`AnnulmentForbiddenError`.
    5. the mandatory reason — → :class:`LegacyValidationError` (422).

    The chain runs BEFORE any write, so a rejected annulment leaves zero
    legacy rows and no ``motanudoc`` audit row.
    """
    codclas = str(codclas or document.get("codclas") or "")
    numnum = str(numfven or document.get("numfven") or "")

    # (1) Veri_Anul
    if str(document.get("estado") or "").strip().upper() == "A":
        raise AlreadyAnnulledError(
            f"El documento {codclas}-{numnum} ya está anulado",
            codclas=codclas,
            numnum=numnum,
        )

    # (2) Hay_Cie_Eli — the same truth the cash write path enforces (CC-6).
    assert_period_open(
        periods,
        fecha=document.get("fecdoc"),
        codclas=codclas,
        numnum=numnum,
        what="el documento",
    )

    # (3) Valid_EdiDocele — an accepted electronic document is never modified.
    estfele = str(document.get("estfele") or "").strip()
    if estfele in ACCEPTED_ELECTRONIC_STATES:
        raise ElectronicDocumentError(
            f"El documento {codclas}-{numnum} es electrónico y ya fue aceptado "
            "por la DIAN; debe anularse ante la DIAN",
            codclas=codclas,
            numnum=numnum,
        )

    # (4) the role gate (legacy N049).
    if str(actor_role or "") not in ANNULMENT_ROLES:
        raise AnnulmentForbiddenError(
            f"Rol '{actor_role}' no tiene permiso de anulación",
            role=str(actor_role or ""),
        )

    # (5) the mandatory reason (legacy FrModAnuDoc).
    if not str(motivo or "").strip():
        raise LegacyValidationError(
            {"motivo": "El motivo de la anulación es obligatorio"},
            "El motivo de la anulación es obligatorio",
        )


# ═══════════════════════ stock recomputation (AN-3s1, AN-3s2) ═══════════


def signed_movement(row: dict) -> Decimal:
    """The signed stock movement of a kardex row (``detcuentas``).

    A debit on the inventory account INCREASES the stock and a credit
    DECREASES it (PUC parity); the quantity travels in ``candet``.
    """
    candet = _dec(row.get("candet"))
    valdeb = _dec(row.get("valdeb"))
    valhab = _dec(row.get("valhab"))
    if valdeb > valhab:
        return candet
    if valhab > valdeb:
        return -candet
    return candet


def recompute_exiprod(movements: list[dict], *, exclude_number: object = None) -> Decimal:
    """``Recal_Cat`` parity: the stock recomputed from the kardex truth.

    ``movements`` are the ``detcuentas`` inventory postings of ONE product.
    The annulled document's own movements are excluded (``exclude_number``)
    and every already-annulled posting (``estcue='A'``) is ignored.
    """
    total = ZERO
    for row in movements:
        if exclude_number is not None and str(
            row.get("numnum") or ""
        ) == str(exclude_number):
            continue
        if str(row.get("estcue") or "B").strip().upper() == "A":
            continue
        total += signed_movement(row)
    return total


# ═══════════════════════ the repo ═══════════════════════════════════════


class AnnulmentRepo(Protocol):
    """Contract shared by the fake twin and the real MySQL repo."""

    def annul(
        self,
        body: AnnulmentRequest,
        *,
        codclas: str,
        numfven: int,
        tenant: str,
        empresa: str,
        actor: str,
        actor_role: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


class _BaseAnnulmentRepo:
    """The φ0..φ4 sequence of an annulment (ADR-0008-03).

    φ0 idempotency replay → φ1 journal PENDING (the annulment's own entry) →
    φ2 **no numbering** (an annulled number is never released) → φ3 the
    reversal (flags + stock + audit) → φ4 journal ANNULLED + the document's
    journal row mirrored.
    """

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
    ) -> None:
        self.store = store
        self.journal = journal
        self.idempotency = idempotency

    # ─── public API ───────────────────────────────────────────────

    def annul(
        self,
        body: AnnulmentRequest,
        *,
        codclas: str,
        numfven: int,
        tenant: str,
        empresa: str,
        actor: str,
        actor_role: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        # φ0 idempotency replay — the stored response is the outcome (AN-4s2).
        if idempotency_key:
            stored = self.idempotency.get(idempotency_key)
            if stored is not None:
                return stored

        document = self._load_document(codclas, numfven)

        # The guard chain runs BEFORE any write (AN-1s1..s5).
        assert_annulment_allowed(
            document=document,
            periods=self.store.locked_periods(),
            actor_role=actor_role,
            motivo=body.motivo,
            codclas=codclas,
            numfven=numfven,
        )

        # φ1 journal-first: the annulment's own PENDING entry.
        entry = self.journal.open_pending(
            codclas=codclas,
            pref=str(document.get("pref") or ""),
            doc_type=ANNULMENT_DOC_TYPE,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        entry_id = entry.id or 0

        # φ2: NO numbering — the annulled number stays occupied forever.
        self.journal.record_number(entry_id, int(numfven))

        written: list[tuple[str, dict]] = []
        try:
            computed = self._reverse(
                codclas=codclas,
                numfven=numfven,
                document=document,
                motivo=body.motivo,
                actor=actor,
                empresa=empresa,
                written=written,
            )
        except Exception as exc:
            for table, op in reversed(written):
                self.store.discard(table, op)
            self.journal.mark_failed(entry_id, str(exc))
            raise ErpSaveFailed(
                f"La anulación no pudo guardarse: {exc}",
                docnum=int(numfven),
                retryable=True,
            ) from exc

        self.store.commit()

        # φ4: the annulment's journal entry is ANNULLED and the DOCUMENT's
        # journal row is mirrored to ANNULLED.
        self.journal.mark_annulled(entry_id, int(numfven))
        self._mirror_journal(codclas, numfven, entry_id)

        result = {
            "codclas": codclas,
            "numfven": int(numfven),
            "pref": str(document.get("pref") or ""),
            "estado": "A",
            "motivo": str(body.motivo)[:MOTANU_MAX_LEN],
            "asientos": computed["asientos"],
            "pagos": computed["pagos"],
            "financiacion": computed["financiacion"],
            "stock": computed["stock"],
            "motanudoc": computed["motanudoc"],
            "journal": "ANNULLED",
        }
        if idempotency_key:
            self.idempotency.store(
                idempotency_key,
                doc_type=ANNULMENT_DOC_TYPE,
                tenant=tenant,
                actor=actor,
                request_id=request_id,
                response=result,
            )
        return result

    # ─── internals ────────────────────────────────────────────────

    def _load_document(self, codclas: str, numfven: int) -> dict:
        """The normalized document view the guard chain reads."""
        family = document_family(codclas)
        if family is None:
            raise LegacyValidationError(
                {"codclas": f"La clase de documento '{codclas}' no se puede anular"},
                "Clase de documento no anulable",
            )
        row = self.store.find_document(codclas, numfven)
        if row is None:
            raise DocumentNotFoundError(
                f"El documento {codclas}-{numfven} no existe",
                codclas=codclas,
                numnum=str(numfven),
            )
        return {
            "codclas": codclas,
            "numfven": int(numfven),
            "pref": str(row.get(family.prefix_field) or ""),
            "estado": str(row.get(family.state_column) or ""),
            "estfele": str(row.get(family.electronic_column) or ""),
            "fecdoc": row.get(family.date_field),
            "codemp": str(row.get("codemp") or ""),
            "header_table": family.header_table,
            "state_column": family.state_column,
        }

    def _reverse(
        self,
        *,
        codclas: str,
        numfven: int,
        document: dict,
        motivo: str,
        actor: str,
        empresa: str,
        written: list[tuple[str, dict]],
    ) -> dict:
        """φ3 — the FULL reversal in one unit of work."""
        family = document_family(codclas)
        assert family is not None  # guaranteed by _load_document

        entries = self.store.document_entries(codclas, numfven)
        payments = self.store.document_payments(codclas, numfven)
        financing = self.store.document_financing(codclas, numfven)

        # The header flag (facventas.estfven / detapago.estado / ...).
        op = self.store.stage_document_state(codclas, numfven, "A")
        written.append((family.header_table, op))

        # Every accounting entry of that number.
        op = self.store.stage_entries_state(codclas, numfven, "A")
        written.append((DETCUENTAS_TABLE, op))

        # Every payment row of that number.
        op = self.store.stage_payments_state(codclas, numfven, "A")
        written.append((DETAPAGO_TABLE, op))

        # Every financing row of that number.
        op = self.store.stage_financing_state(codclas, numfven, "A")
        written.append((FINANCIACION_TABLE, op))

        # Stock recomputed from the kardex truth (AN-3s1/AN-3s2).
        stock = self._recompute_stock(codclas, numfven, family, written)

        # The audit row (AN-4s1): motivo truncated to 800 chars, tipo='A'.
        audit_row = {
            "numnum": str(numfven),
            "fecanu": date.today(),
            "motanu": str(motivo)[:MOTANU_MAX_LEN],
            "codemp": empresa,
            "horanu": datetime.now().hour or 24,
            "codclas": codclas,
            "fecdoc": document.get("fecdoc") or date.today(),
            "tipo": MOTANUDOC_TIPO_ANULADO,
        }
        op = self.store.stage_motanudoc(audit_row)
        written.append((MOTANUDOC_TABLE, op))

        return {
            "asientos": len(entries),
            "pagos": len(payments),
            "financiacion": len(financing),
            "stock": stock,
            "motanudoc": {
                "numnum": audit_row["numnum"],
                "codclas": audit_row["codclas"],
                "tipo": audit_row["tipo"],
                "fecanu": audit_row["fecanu"].isoformat(),
                "motanu": audit_row["motanu"],
            },
        }

    def _recompute_stock(
        self,
        codclas: str,
        numfven: int,
        family: Any,
        written: list[tuple[str, dict]],
    ) -> list[dict]:
        """Recompute ``exiprod`` from the kardex truth (AN-3s1/AN-3s2).

        When the document posted its own kardex rows (``detcuentas`` with
        ``codprod``), the whole movement history is recomputed with the
        annulled document excluded — the legacy ``AcInv_Eli_Anul`` behaviour.
        When it did not (the web write path posts no inventory row), the
        document's own movement is restored instead of blind-adding back.
        """
        movements = self._document_stock_movements(codclas, numfven, family)
        if not movements:
            return []
        stock: list[dict] = []
        for codprod, movement in sorted(movements.items()):
            product = self.store.product(codprod)
            if product is None:
                continue
            current = _dec(product.get("exiprod"))
            kardex = self.store.kardex_movements(codprod)
            doc_rows = [
                row for row in kardex if str(row.get("numnum") or "") == str(numfven)
            ]
            if doc_rows:
                value = recompute_exiprod(kardex, exclude_number=numfven)
                origen = "kardex"
            else:
                value = current - movement
                origen = "restauracion"
            op = self.store.stage_product_stock(codprod, value)
            written.append((PRODUCTOS_TABLE, op))
            stock.append(
                {"codprod": codprod, "exiprod": str(value), "origen": origen}
            )
        return stock

    def _document_stock_movements(
        self, codclas: str, numfven: int, family: Any
    ) -> dict[str, Decimal]:
        """The signed stock movement of the document, per product."""
        movements: dict[str, Decimal] = {}
        for row in self.store.document_entries(codclas, numfven):
            codprod = str(row.get("codprod") or "")
            if not codprod:
                continue
            movements[codprod] = movements.get(codprod, ZERO) + signed_movement(row)
        if movements:
            return movements
        # No kardex posting of its own: the document's LINES carry the
        # quantity and the family carries the direction (a sale moves stock
        # out).
        for line in self.store.document_lines(codclas, numfven):
            codprod = str(line.get("codprod") or "")
            if not codprod:
                continue
            quantity = _dec(line.get("candet")) * family.stock_direction
            movements[codprod] = movements.get(codprod, ZERO) + quantity
        return movements

    def _mirror_journal(self, codclas: str, numfven: int, entry_id: int) -> None:
        """Mirror the DOCUMENT's journal row to ``ANNULLED``.

        The annulment has its own journal entry (the write-ahead intent); the
        document's own row is the mirrored state the desktop-style queries
        read (``app_doc_journal.status = 'ANNULLED'``).
        """
        try:
            candidates = self.journal.list_document_entries(codclas, int(numfven))
        except Exception:
            logger.warning("journal mirror lookup failed", exc_info=True)
            return
        for entry in candidates:
            if entry.id == entry_id:
                continue
            if getattr(entry, "doc_type", "") == ANNULMENT_DOC_TYPE:
                continue
            if entry.status not in ("COMMITTED", "PENDING"):
                continue
            try:
                self.journal.mark_annulled(entry.id, int(numfven))
            except Exception:
                logger.warning("journal mirror update failed", exc_info=True)
            return


class FakeAnnulmentRepo(_BaseAnnulmentRepo):
    """In-memory twin used by the hermetic test suite."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
    ) -> None:
        super().__init__(store=store, journal=journal, idempotency=idempotency)


class RealAnnulmentRepo(_BaseAnnulmentRepo):
    """Real MySQL writer (same sequence, InnoDB journal + MyISAM rows)."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
    ) -> None:
        super().__init__(store=store, journal=journal, idempotency=idempotency)


def get_annulment_repo() -> AnnulmentRepo:
    """FastAPI dependency: the real MySQL-backed repo."""
    from motoshop_api.erp.annulment.store import get_annulment_store
    from motoshop_api.erp.idempotency import get_idempotency_repo
    from motoshop_api.erp.journal import get_journal_repo

    return RealAnnulmentRepo(
        store=get_annulment_store(),
        journal=get_journal_repo(),
        idempotency=get_idempotency_repo(),
    )


__all__ = [
    "ACCEPTED_ELECTRONIC_STATES",
    "ANNULMENT_DOC_TYPE",
    "ANNULMENT_ROLES",
    "AnnulmentForbiddenError",
    "AnnulmentRepo",
    "AlreadyAnnulledError",
    "DOCUMENT_FAMILIES",
    "DocumentNotFoundError",
    "ElectronicDocumentError",
    "FakeAnnulmentRepo",
    "MOTANUDOC_TIPO_ANULADO",
    "RealAnnulmentRepo",
    "assert_annulment_allowed",
    "get_annulment_repo",
    "recompute_exiprod",
    "signed_movement",
]
