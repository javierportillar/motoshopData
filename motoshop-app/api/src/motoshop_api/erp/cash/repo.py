"""Collections & cash save repos (slice 4 — tasks 4.1–4.5).

Legacy parity (docs/hermes):
- **Graba_Fpago duality** (code_analysis §5.3): the payment row carries
  ``soldeb`` for normal payment documents (S01 receipts, S02/S03 cash docs…)
  and ``solcre`` for the note-type classes (S14/S21) — never both non-zero.
- **Live CxC balance**: the open balance of a receivable is the truth
  ``SUM(detcuentas.valdeb − valhab)`` on the cartera accounts of that
  document — the canonical ``13050501`` AND its legacy alias ``1305`` (the
  account the receipts credited before the fix). A receipt NEVER over-applies
  (CC-1) and NEVER targets an annulled document (``estfven='A'``).
- **Hay_Cie_Eli**: a document dated inside a closed accounting period
  (``cierresper`` rows of type P/M/A) is rejected at creation time (CC-6).
- **Arqueo invariants**: ``cajaarqueo.salcaj`` must equal the denomination
  sum ``Σ(cantden × denarq)`` of its ``detcajarq`` rows (CC-4).
- **Bank consignations**: the consignment number comes from the payment
  form's own counter ``formapago.numcon`` and advances exactly once per
  posting (CC-5).

Every write follows the ADR-0008-03 φ-sequence: idempotency replay (φ0) →
journal PENDING (φ1) → numbering reservation (φ2) → legacy rows (φ3) →
journal COMMITTED + response snapshot (φ4).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Protocol

from motoshop_api.erp.cash.schemas import (
    ArqueoCreate,
    CashMovementCreate,
    ConsignmentCreate,
    EgressCreate,
    ReceiptCreate,
)
from motoshop_api.erp.cash.store import (
    CAJAARQUEO_TABLE,
    COMPROBANTES_TABLE,
    DETAPAGO_TABLE,
    DETCAJARQ_TABLE,
    DETCUENTAS_TABLE,
    CashStore,
)
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import assert_causacion_balanced, assert_period_open
from motoshop_api.erp.idempotency import IdempotencyRepo
from motoshop_api.erp.journal import JournalRepo
from motoshop_api.erp.masters.validators import LegacyValidationError
from motoshop_api.erp.numbering import ContadoresRepo

logger = logging.getLogger(__name__)

#: `contadores.codcon` of the cash receipt (S01 RECIBO DE CAJA).
RECEIPT_CODCON = "S01"
#: Journal/audit document type of the receipt.
RECEIPT_DOC_TYPE = "recibo_caja"
#: Cartera account (CxC) — the CANONICAL account, the one the invoice
#: causación writes (``erp/invoicing/repo.py``). Every NEW row lands here.
CARTERA_CUENTA = "13050501"
#: Legacy aliases of the cartera account: the rows written before the fix
#: live here. They are READ (never written) — reading only the canonical
#: account would make the customers pay twice.
CARTERA_CUENTA_ALIASES: tuple[str, ...] = ("1305",)
#: Default cash account when the payment form does not carry one.
CASH_CUENTA = "1105"
#: Legacy width of ``detapago.numpag`` (varchar(20)) — the shared clip for
#: every writer of that column (cash AND invoice paths).
NUMPAG_MAX_LEN = 20

#: Document classes whose payment rows are written as a CREDIT (``solcre``).
SOLCRE_TIPCLAS = frozenset({"S14", "S21"})
#: Document classes allowed to carry payment rows.
PAYMENT_TIPCLAS = frozenset({"S01", "S02", "S03", "S14", "S21", "S26"})

ZERO = Decimal("0")


def _dec(value: object) -> Decimal:
    """Legacy numeric (str/Decimal/double) → Decimal, exact."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


def payment_duality(tipclas: str, amount: Decimal) -> tuple[Decimal, Decimal]:
    """``Graba_Fpago`` parity: the document class picks debit or credit.

    Returns ``(soldeb, solcre)``. Note-type classes (S14/S21 — returns and
    credit notes) write the payment as a CREDIT; every other payment class
    (S01 receipts, S02/S03 cash documents) writes it as a DEBIT. The two
    columns are never both non-zero on the same row (spec CC-2).
    """
    if str(tipclas).upper() in SOLCRE_TIPCLAS:
        return ZERO, amount
    return amount, ZERO


def open_balance(store: CashStore, numfven: int, codcue: str = CARTERA_CUENTA) -> Decimal:
    """The LIVE open balance of a receivable (CC-1).

    ``SUM(detcuentas.valdeb − valhab)`` over the rows of that document on the
    cartera account — the canonical one AND its legacy aliases — the
    receipt's own credit rows land on the same document, so the balance
    always reflects what has actually been collected.

    The accounts are read in ONE statement, so a row is never counted twice.
    """
    cuentas = tuple(dict.fromkeys((codcue, *CARTERA_CUENTA_ALIASES)))
    total = ZERO
    for row in store.ledger_rows_for_accounts(str(numfven), cuentas):
        total += _dec(row.get("valdeb")) - _dec(row.get("valhab"))
    return total


class AnnulledDocumentError(Exception):
    """409: the target document is annulled (``estfven='A'``) — CC-1s4."""

    def __init__(self, message: str, *, codclas: str = "", numnum: str = ""):
        super().__init__(message)
        self.message = message
        self.codclas = codclas
        self.numnum = numnum

    def detail(self) -> dict:
        return {
            "message": self.message,
            "code": "document_annulled",
            "document": {"codclas": self.codclas, "numnum": self.numnum},
        }


class ReceiptOverpaymentError(LegacyValidationError):
    """422: the receipt exceeds the open balance (CC-1s3).

    The available balance travels in the error detail so the client can show
    the customer how much is actually due.
    """

    def __init__(self, *, available: Decimal, attempted: Decimal):
        super().__init__(
            {
                "valor": (
                    f"El valor del recibo ({attempted}) supera el saldo "
                    f"disponible ({available})"
                )
            },
            "El pago supera el saldo disponible del documento",
        )
        self.available = available
        self.attempted = attempted

    def detail(self) -> dict:
        return {
            "message": self.message,
            "fields": self.fields,
            "saldo_disponible": str(self.available),
        }


class ReceiptsRepo(Protocol):
    """Contract shared by the fake twin and the real MySQL repo."""

    def create(
        self,
        body: ReceiptCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


class _CashDocumentRepo:
    """The φ0..φ4 sequence shared by every cash document (ADR-0008-03).

    φ0 idempotency replay → φ1 journal PENDING → φ2 numbering reservation →
    φ3 legacy rows (compensated row by row on failure) → φ4 journal COMMITTED
    + response snapshot for the replay.
    """

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
    ) -> None:
        self.store = store
        self.journal = journal
        self.idempotency = idempotency
        self.numbering = numbering

    def _save(
        self,
        *,
        codcon: str,
        doc_type: str,
        doc_table: str,
        num_field: str,
        prefix_column: str,
        validate,
        persist,
        response,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
        pref: str | None = None,
        reserve=None,
        release=None,
    ) -> dict:
        if idempotency_key:
            stored = self.idempotency.get(idempotency_key)
            if stored is not None:
                return stored

        computed = validate()

        if pref is None:
            pref = self.numbering.resolve_prefix(codcon)
        entry = self.journal.open_pending(
            codclas=codcon,
            pref=pref,
            doc_type=doc_type,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        entry_id = entry.id or 0

        try:
            if reserve is None:
                number = self.numbering.reserve(
                    codcon=codcon,
                    pref=pref,
                    doc_table=doc_table,
                    num_field=num_field,
                    prefix_column=prefix_column,
                )
            else:
                number = reserve()
        except Exception as exc:
            self.journal.mark_failed(entry_id, str(exc))
            raise

        self.journal.record_number(entry_id, number)

        written: list[tuple[str, dict]] = []
        try:
            persist(computed, number, pref, written)
        except Exception as exc:
            for table, row in reversed(written):
                self.store.discard(table, row)
            if release is not None:
                release(number)
            self.journal.mark_failed(entry_id, str(exc))
            raise ErpSaveFailed(
                f"El documento no pudo guardarse: {exc}",
                docnum=number,
                retryable=True,
            ) from exc

        self.store.commit()
        self.journal.mark_committed(entry_id, number)

        result = response(computed, number, pref)
        if idempotency_key:
            self.idempotency.store(
                idempotency_key,
                doc_type=doc_type,
                tenant=tenant,
                actor=actor,
                request_id=request_id,
                response=result,
            )
        return result


class _BaseReceiptsRepo(_CashDocumentRepo):
    """Receipts (S01) — a cash receipt applied to an open CxC balance."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
        cartera_cuenta: str = CARTERA_CUENTA,
        cash_cuenta: str = CASH_CUENTA,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )
        self.cartera_cuenta = cartera_cuenta
        self.cash_cuenta = cash_cuenta

    # ─── public API ───────────────────────────────────────────────

    def create(
        self,
        body: ReceiptCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        return self._save(
            codcon=RECEIPT_CODCON,
            doc_type=RECEIPT_DOC_TYPE,
            doc_table=DETAPAGO_TABLE,
            num_field="numnum",
            prefix_column="predoc",
            validate=lambda: self._validate(body),
            persist=lambda computed, number, pref, written: self._persist(
                body, computed, number, pref, actor, empresa, written
            ),
            response=lambda computed, number, pref: self._response(
                body, computed, number, pref
            ),
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )

    def _response(
        self, body: ReceiptCreate, computed: dict, number: int, pref: str
    ) -> dict:
        return {
            "numero": number,
            "pref": pref,
            "tipclas": str(body.tipclas).upper(),
            "valor": str(body.valor),
            "soldeb": str(computed["soldeb"]),
            "solcre": str(computed["solcre"]),
            "forma_pago": body.codpag,
            "documento": {"numfven": body.numfven, "prefven": body.prefven},
            "saldo_anterior": str(computed["available"]),
            "saldo_actual": str(computed["available"] - body.valor),
        }

    # ─── validation (before φ1: nothing is reserved) ──────────────

    def _validate(self, body: ReceiptCreate) -> dict:
        fields: dict[str, str] = {}

        if body.valor <= ZERO:
            fields["valor"] = "El valor del recibo debe ser mayor que cero"

        tipclas = str(body.tipclas).upper()
        if tipclas not in PAYMENT_TIPCLAS:
            fields["tipclas"] = (
                f"La clase de documento '{body.tipclas}' no emite pagos"
            )

        invoice = self.store.find_invoice(body.numfven, body.prefven)
        if invoice is None:
            fields["numfven"] = (
                f"El documento {body.prefven}-{body.numfven} no existe"
            )

        if fields:
            raise LegacyValidationError(fields)

        if str(invoice.get("estfven") or "").upper() == "A":
            raise AnnulledDocumentError(
                f"El documento {body.prefven}-{body.numfven} está anulado y "
                "no admite recaudos",
                codclas=str(invoice.get("codclas") or "S15"),
                numnum=str(body.numfven),
            )

        # Hay_Cie_Eli: a document dated inside a closed accounting period is
        # rejected at creation time (CC-6) — the same truth slice 5 uses.
        assert_period_open(
            self.store.locked_periods(),
            fecha=body.fecha,
            codclas=RECEIPT_CODCON,
            what="el recibo",
        )

        available = open_balance(self.store, body.numfven, self.cartera_cuenta)
        if available <= ZERO:
            raise LegacyValidationError(
                {
                    "numfven": (
                        f"El documento {body.prefven}-{body.numfven} no tiene "
                        "saldo en cartera"
                    )
                }
            )
        if body.valor > available:
            raise ReceiptOverpaymentError(available=available, attempted=body.valor)

        soldeb, solcre = payment_duality(tipclas, body.valor)
        return {
            "invoice": invoice,
            "available": available,
            "soldeb": soldeb,
            "solcre": solcre,
        }

    # ─── persistence (φ3) ─────────────────────────────────────────

    def _persist(
        self,
        body: ReceiptCreate,
        computed: dict,
        number: int,
        pref: str,
        actor: str,
        empresa: str,
        written: list[tuple[str, dict]],
    ) -> None:
        amount = body.valor
        soldeb = computed["soldeb"]
        solcre = computed["solcre"]
        formapago = self.store.find_formapago(body.codpag) or {}
        cash_cuenta = str(formapago.get("codcue") or self.cash_cuenta)

        payment_row = {
            "numnum": str(number),
            "codclas": RECEIPT_CODCON,
            "predoc": pref,
            "numite": 1,
            "fecdoc": body.fecha,
            "valpag": amount,
            "valefe": amount,
            "despag": body.concepto or "",
            "numpag": (body.referencia or "")[:NUMPAG_MAX_LEN],
            "fecche": body.fecha,
            "soldeb": soldeb,
            "solcre": solcre,
            "codpag": body.codpag,
            "afepag": formapago.get("afepag", 0),
            "codban": formapago.get("codban", ""),
            "estado": "B",
            "nitter": body.nitter,
            "codemp": empresa,
            "codcaj": body.codcaj,
            "turno1": "0",
            "fecven": body.fecha,
            "actor": actor,
        }
        self.store.stage_insert(DETAPAGO_TABLE, payment_row)
        written.append((DETAPAGO_TABLE, payment_row))

        # Causación: the credit lands on the RECEIVED invoice's cartera
        # account (that is what closes its balance) and the matching debit
        # lands on the cash/bank account of the payment form. The credit
        # always uses the CANONICAL cartera account — the legacy alias is
        # read only, never written.
        credit_row = {
            "numnum": str(body.numfven),
            "codclas": str(computed["invoice"].get("codclas") or "S15"),
            "prenum": body.prefven,
            "codcue": self.cartera_cuenta,
            "detcue": f"ABONO CARTERA POR RECIBO {pref}-{number}",
            "valdeb": ZERO,
            "valhab": amount,
            "fecdoc": body.fecha,
            "nitter": body.nitter,
            "estcue": "B",
            "numite": 1,
            "codemp": empresa,
        }
        debit_row = {
            "numnum": str(number),
            "codclas": RECEIPT_CODCON,
            "prenum": pref,
            "codcue": cash_cuenta,
            "detcue": f"INGRESO A CAJA POR RECIBO {pref}-{number}",
            "valdeb": amount,
            "valhab": ZERO,
            "fecdoc": body.fecha,
            "nitter": body.nitter,
            "estcue": "B",
            "numite": 1,
            "codemp": empresa,
        }
        assert_causacion_balanced([credit_row, debit_row])
        self.store.stage_insert(DETCUENTAS_TABLE, credit_row)
        written.append((DETCUENTAS_TABLE, credit_row))
        self.store.stage_insert(DETCUENTAS_TABLE, debit_row)
        written.append((DETCUENTAS_TABLE, debit_row))


class FakeReceiptsRepo(_BaseReceiptsRepo):
    """In-memory twin used by the hermetic test suite."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo | None = None,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering or store.numbering,
        )


class RealReceiptsRepo(_BaseReceiptsRepo):
    """Real MySQL writer (same sequence, InnoDB journal + MyISAM rows)."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )


def get_receipts_repo() -> ReceiptsRepo:
    """FastAPI dependency: the real MySQL-backed repo."""
    from motoshop_api.erp.cash.store import get_cash_store
    from motoshop_api.erp.idempotency import get_idempotency_repo
    from motoshop_api.erp.journal import get_journal_repo
    from motoshop_api.erp.numbering import get_contadores_repo

    return RealReceiptsRepo(
        store=get_cash_store(),
        journal=get_journal_repo(),
        idempotency=get_idempotency_repo(),
        numbering=get_contadores_repo(),
    )


# ═══════════════════════ Egresos / ingresos (task 4.3) ═══════════════════

#: `contadores.codcon` of the comprobante de egreso (S02).
EGRESS_CODCON = "S02"
#: `contadores.codcon` of the comprobante de ingreso (S03).
INGRESS_CODCON = "S03"
#: Journal/audit document types of the cash documents.
EGRESS_DOC_TYPE = "comprobante_egreso"
INGRESS_DOC_TYPE = "comprobante_ingreso"
#: Accepted `tipo` values of the cash-movement endpoint.
MOVEMENT_ENTRADA = "ENTRADA"
MOVEMENT_SALIDA = "SALIDA"


class CashMovementsRepo(Protocol):
    """Contract shared by the fake twin and the real MySQL repo."""

    def create_movement(
        self,
        body: CashMovementCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...

    def create_egress(
        self,
        body: EgressCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


class _BaseCashMovementsRepo(_CashDocumentRepo):
    """Cash movements in/out through ``concepingegr`` concepts (CC-3).

    A movement posts a ``comprobantes`` document (S02 egreso / S03 ingreso)
    caused into ``detcuentas``: the concept's account is debited (expense
    concepts) or credited (income concepts) and the cash/bank account of the
    payment form takes the counterpart. The document total (``totegr``) is
    computed server-side — the client never sends it.
    """

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
        cash_cuenta: str = CASH_CUENTA,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )
        self.cash_cuenta = cash_cuenta

    # ─── public API ───────────────────────────────────────────────

    def create_movement(
        self,
        body: CashMovementCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        tipo = str(body.tipo).upper()
        if tipo not in (MOVEMENT_ENTRADA, MOVEMENT_SALIDA):
            raise LegacyValidationError(
                {"tipo": "El tipo de movimiento debe ser ENTRADA o SALIDA"}
            )
        return self._save_movement(
            body,
            tipo,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )

    def create_egress(
        self,
        body: EgressCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        return self._save_movement(
            body,
            MOVEMENT_SALIDA,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )

    # ─── internals ────────────────────────────────────────────────

    def _save_movement(
        self,
        body: CashMovementCreate | EgressCreate,
        tipo: str,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        codcon = EGRESS_CODCON if tipo == MOVEMENT_SALIDA else INGRESS_CODCON
        doc_type = EGRESS_DOC_TYPE if tipo == MOVEMENT_SALIDA else INGRESS_DOC_TYPE

        def _validate() -> dict:
            fields: dict[str, str] = {}
            if body.valor <= ZERO:
                fields["valor"] = "El valor del comprobante debe ser mayor que cero"
            concept = self.store.find_concept(body.codcon)
            if concept is None:
                fields["codcon"] = f"El concepto '{body.codcon}' no existe"
            formapago = self.store.find_formapago(body.codpag)
            if formapago is None:
                fields["codpag"] = f"La forma de pago '{body.codpag}' no existe"
            if fields:
                raise LegacyValidationError(fields)
            # Hay_Cie_Eli: a cash document dated inside a closed period is
            # rejected at creation time (CC-6).
            assert_period_open(
                self.store.locked_periods(),
                fecha=body.fecha,
                codclas=codcon,
                what="el comprobante",
            )
            return {"concept": concept, "formapago": formapago}

        def _persist(computed: dict, number: int, pref: str, written: list) -> None:
            concept = computed["concept"]
            formapago = computed["formapago"]
            amount = body.valor
            concept_cuenta = str(concept.get("codcue") or "")
            cash_cuenta = str(formapago.get("codcue") or self.cash_cuenta)
            # `concepingegr.debcre` says the natural side of the concept:
            # 'D' (expense) is debited, 'C' (income) is credited.
            debit_concept = str(concept.get("debcre") or "D").upper() == "D"
            debit_cuenta = concept_cuenta if debit_concept else cash_cuenta
            credit_cuenta = cash_cuenta if debit_concept else concept_cuenta

            header = {
                "numegr": str(number),
                "codclas": codcon,
                "nomdoc": (
                    "COMPROBANTE DE EGRESO"
                    if tipo == MOVEMENT_SALIDA
                    else "COMPROBANTE DE INGRESO"
                ),
                "preegr": pref,
                "fecegr": body.fecha,
                "nitter": body.nitter or "",
                "digver": "",
                "codsuc": "",
                "cliegr": body.nitter or "",
                "diregr": "",
                "telegr": "",
                "codpag": body.codpag,
                "subegr": amount,
                "totdct": ZERO,
                "ajuspe": ZERO,
                "totegr": amount,  # server-side total (subegr − totdct + ajuspe)
                "obsegr": body.concepto or "",
                "estegr": "B",
                "codemp": empresa,
                "horegr": 1,
                "codres": "",
                "codcos": body.codcon,
                "empcod": "",
                "nitcob": "",
                "docext": "",
                "codcaj": body.codcaj,
                "turno1": "0",
                "numcru": "",
                "clascru": "",
                "agrupa": "",
                "actor": actor,
            }
            self.store.stage_insert(COMPROBANTES_TABLE, header)
            written.append((COMPROBANTES_TABLE, header))

            # The payment row keeps the Graba_Fpago duality (S02/S03 → soldeb)
            # so the daily cash reconciliation counts the movement once.
            soldeb, solcre = payment_duality(codcon, amount)
            payment_row = {
                "numnum": str(number),
                "codclas": codcon,
                "predoc": pref,
                "numite": 1,
                "fecdoc": body.fecha,
                "valpag": amount,
                "valefe": amount,
                "despag": body.concepto or "",
                "numpag": "",
                "fecche": body.fecha,
                "soldeb": soldeb,
                "solcre": solcre,
                "codpag": body.codpag,
                "afepag": formapago.get("afepag", 0),
                "codban": formapago.get("codban", ""),
                "estado": "B",
                "nitter": body.nitter or "",
                "codemp": empresa,
                "codcaj": body.codcaj,
                "turno1": "0",
                "fecven": body.fecha,
                "actor": actor,
            }
            self.store.stage_insert(DETAPAGO_TABLE, payment_row)
            written.append((DETAPAGO_TABLE, payment_row))

            entries = [
                {
                    "numnum": str(number),
                    "codclas": codcon,
                    "prenum": pref,
                    "codcue": debit_cuenta,
                    "detcue": f"DEBE {concept.get('nomcon') or body.codcon}",
                    "valdeb": amount,
                    "valhab": ZERO,
                    "fecdoc": body.fecha,
                    "nitter": body.nitter or "",
                    "estcue": "B",
                    "numite": 1,
                    "codemp": empresa,
                },
                {
                    "numnum": str(number),
                    "codclas": codcon,
                    "prenum": pref,
                    "codcue": credit_cuenta,
                    "detcue": f"HABER {concept.get('nomcon') or body.codcon}",
                    "valdeb": ZERO,
                    "valhab": amount,
                    "fecdoc": body.fecha,
                    "nitter": body.nitter or "",
                    "estcue": "B",
                    "numite": 1,
                    "codemp": empresa,
                },
            ]
            assert_causacion_balanced(entries)
            for entry in entries:
                self.store.stage_insert(DETCUENTAS_TABLE, entry)
                written.append((DETCUENTAS_TABLE, entry))

        def _response(computed: dict, number: int, pref: str) -> dict:
            return {
                "numero": number,
                "pref": pref,
                "codclas": codcon,
                "tipo": tipo,
                "concepto": body.codcon,
                "totegr": str(body.valor),
                "forma_pago": body.codpag,
            }

        return self._save(
            codcon=codcon,
            doc_type=doc_type,
            doc_table=COMPROBANTES_TABLE,
            num_field="numegr",
            prefix_column="preegr",
            validate=_validate,
            persist=_persist,
            response=_response,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )


class FakeCashMovementsRepo(_BaseCashMovementsRepo):
    """In-memory twin used by the hermetic test suite."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo | None = None,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering or store.numbering,
        )


class RealCashMovementsRepo(_BaseCashMovementsRepo):
    """Real MySQL writer (same sequence, InnoDB journal + MyISAM rows)."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )


def get_cash_movements_repo() -> CashMovementsRepo:
    """FastAPI dependency: the real MySQL-backed repo."""
    from motoshop_api.erp.cash.store import get_cash_store
    from motoshop_api.erp.idempotency import get_idempotency_repo
    from motoshop_api.erp.journal import get_journal_repo
    from motoshop_api.erp.numbering import get_contadores_repo

    return RealCashMovementsRepo(
        store=get_cash_store(),
        journal=get_journal_repo(),
        idempotency=get_idempotency_repo(),
        numbering=get_contadores_repo(),
    )


# ═══════════════════════ Arqueo de caja (task 4.4) ════════════════════════

#: `contadores.codcon` of the cash count (S38 ARQUEO DE CAJA).
ARQUEO_CODCON = "S38"
#: Journal/audit document type of the cash count.
ARQUEO_DOC_TYPE = "arqueo_caja"
#: `detcajarq.tiparq` classes (1=billetes, 2=monedas, 3=otros).
ARQUEO_CLASSES = (1, 2, 3)
#: Legacy table holding the bank consignment.
CONSBANCAB_TABLE = "consbancab"
#: Journal/audit document type of the bank consignment.
CONSIGNMENT_DOC_TYPE = "consignacion_bancaria"


class ArqueoRepo(Protocol):
    """Contract shared by the fake twin and the real MySQL repo."""

    def create(
        self,
        body: ArqueoCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


class _BaseArqueoRepo(_CashDocumentRepo):
    """Cash count (S38): ``cajaarqueo`` header + ``detcajarq`` rows.

    Invariants enforced server-side (CC-4):
    - the header total equals ``Σ(cantden × denarq)`` of its rows;
    - every row belongs to exactly ONE ``tiparq`` class (1/2/3).

    A declared total that disagrees with the denomination sum is a 422 that
    names the difference — nothing persists.
    """

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )

    def create(
        self,
        body: ArqueoCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        def _validate() -> dict:
            fields: dict[str, str] = {}
            total = ZERO
            for index, row in enumerate(body.rows):
                if row.tiparq not in ARQUEO_CLASSES:
                    fields[f"rows[{index}].tiparq"] = (
                        "Cada denominación debe pertenecer a una sola clase "
                        "(1 billetes, 2 monedas, 3 otros)"
                    )
                if row.cantden < 1:
                    fields[f"rows[{index}].cantden"] = (
                        "La cantidad contada debe ser mayor que cero"
                    )
                total += row.denarq * row.cantden
            if body.salcaj is not None and body.salcaj != total:
                difference = body.salcaj - total
                fields["salcaj"] = (
                    f"El total declarado ({body.salcaj}) no coincide con la suma "
                    f"de las denominaciones ({total}); diferencia: {difference}"
                )
            if fields:
                raise LegacyValidationError(fields)
            assert_period_open(
                self.store.locked_periods(),
                fecha=body.fecha,
                codclas=ARQUEO_CODCON,
                what="el arqueo",
            )
            return {"total": total}

        def _persist(computed: dict, number: int, pref: str, written: list) -> None:
            header = {
                "numarq": str(number),
                "codclas": ARQUEO_CODCON,
                "nomdoc": "ARQUEO DE CAJA",
                "prearq": pref,
                "fecarq": body.fecha,
                "nitter": body.nitter or "",
                "codcue": body.codcue,
                "salcaj": computed["total"],
                "obsarq": body.obsarq or "",
                "estarq": "B",
                "codemp": empresa,
                "empcod": "",
                "tiparq": "C",  # legacy solver tag (rows carry the real class)
                "actor": actor,
            }
            self.store.stage_insert(CAJAARQUEO_TABLE, header)
            written.append((CAJAARQUEO_TABLE, header))

            for row in body.rows:
                detail = {
                    "numarq": str(number),
                    "codclas": ARQUEO_CODCON,
                    "denarq": row.denarq,
                    "cantden": row.cantden,
                    "tipdet": row.tipdet or "",
                    "bandes": row.bandes or "",
                    "numche": row.numche or "",
                    "tiparq": str(row.tiparq),
                }
                self.store.stage_insert(DETCAJARQ_TABLE, detail)
                written.append((DETCAJARQ_TABLE, detail))

        def _response(computed: dict, number: int, pref: str) -> dict:
            return {
                "numero": number,
                "pref": pref,
                "codclas": ARQUEO_CODCON,
                "salcaj": str(computed["total"]),
                "filas": len(body.rows),
            }

        return self._save(
            codcon=ARQUEO_CODCON,
            doc_type=ARQUEO_DOC_TYPE,
            doc_table=CAJAARQUEO_TABLE,
            num_field="numarq",
            prefix_column="prearq",
            validate=_validate,
            persist=_persist,
            response=_response,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )


class FakeArqueoRepo(_BaseArqueoRepo):
    """In-memory twin used by the hermetic test suite."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo | None = None,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering or store.numbering,
        )


class RealArqueoRepo(_BaseArqueoRepo):
    """Real MySQL writer (same sequence, InnoDB journal + MyISAM rows)."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )


def get_arqueo_repo() -> ArqueoRepo:
    """FastAPI dependency: the real MySQL-backed repo."""
    from motoshop_api.erp.cash.store import get_cash_store
    from motoshop_api.erp.idempotency import get_idempotency_repo
    from motoshop_api.erp.journal import get_journal_repo
    from motoshop_api.erp.numbering import get_contadores_repo

    return RealArqueoRepo(
        store=get_cash_store(),
        journal=get_journal_repo(),
        idempotency=get_idempotency_repo(),
        numbering=get_contadores_repo(),
    )


# ═══════════════════════ Consignaciones (task 4.5) ═══════════════════════

#: `consbancab.precon` — the legacy prefix of a bank consignment.
CONSIGNMENT_PREFIX = "RC"
#: Journal/audit document type of the bank consignment.
CONSIGNMENT_DOC_TYPE = "consignacion_bancaria"
#: `consbancab.codclas` is EMPTY in the legacy rows: the consignment has no
#: `contadores` entry (it owns its counter in `formapago.numcon`).
CONSIGNMENT_CODCLAS = ""
#: `formapago.tippag` / `afepag` of a bank-consignment payment form.
CONSIGNMENT_TIPPAG = 2
CONSIGNMENT_AFEPAG = 22


class ConsignmentRepo(Protocol):
    """Contract shared by the fake twin and the real MySQL repo."""

    def create(
        self,
        body: ConsignmentCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


class _BaseConsignmentRepo(_CashDocumentRepo):
    """Bank consignment (``consbancab``) with its OWN counter (CC-5).

    The consignment does NOT go through ``contadores``: the number comes from
    the payment form's own counter (``formapago.numcon``) and advances
    EXACTLY ONCE per posting. The idempotency replay (φ0) short-circuits
    before the counter is touched, so a retry never advances it twice.
    """

    def create(
        self,
        body: ConsignmentCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        def _validate() -> dict:
            fields: dict[str, str] = {}
            if body.valor <= ZERO:
                fields["valor"] = "El valor de la consignación debe ser mayor que cero"
            formapago = self.store.find_formapago(body.codpag)
            if formapago is None:
                fields["codpag"] = f"La forma de pago '{body.codpag}' no existe"
            else:
                tippag = int(formapago.get("tippag") or 0)
                afepag = int(formapago.get("afepag") or 0)
                if tippag != CONSIGNMENT_TIPPAG or afepag != CONSIGNMENT_AFEPAG:
                    fields["codpag"] = (
                        "La forma de pago debe ser de consignación bancaria "
                        f"(tippag={CONSIGNMENT_TIPPAG}, afepag={CONSIGNMENT_AFEPAG})"
                    )
            if fields:
                raise LegacyValidationError(fields)
            assert_period_open(
                self.store.locked_periods(),
                fecha=body.fecha,
                codclas=CONSIGNMENT_CODCLAS,
                what="la consignación",
            )
            return {"formapago": formapago}

        def _reserve() -> int:
            """Take the consignment number from ``formapago.numcon`` (once)."""
            current = self.store.payment_form_counter(body.codpag)
            self.store.advance_payment_form_counter(body.codpag, current + 1)
            return current

        def _release(number: int) -> None:
            """φ3 failure: walk the bank counter back to the free number."""
            self.store.advance_payment_form_counter(body.codpag, number)

        def _persist(computed: dict, number: int, pref: str, written: list) -> None:
            formapago = computed["formapago"]
            row = {
                "numcon": str(number),
                "nomdoc": "RECIBO DE CAJA MENOR",
                "precon": pref,
                "feccon": body.fecha,
                "codcue": str(formapago.get("codcue") or CASH_CUENTA),
                "codpag": body.codpag,
                "detcon": body.detalle or "",
                "totcon": body.valor,
                "estcon": "B",
                "codemp": empresa,
                "horcaj": 1,
                "codres": "",
                "tipret": body.tipret,
                "codcos": "",
                "codclas": CONSIGNMENT_CODCLAS,
                "empcod": "",
                "cod2cos": "",
                "actor": actor,
            }
            self.store.stage_insert(CONSBANCAB_TABLE, row)
            written.append((CONSBANCAB_TABLE, row))

        def _response(computed: dict, number: int, pref: str) -> dict:
            return {
                "numero": number,
                "pref": pref,
                "codpag": body.codpag,
                "totcon": str(body.valor),
                "codcue": str(computed["formapago"].get("codcue") or CASH_CUENTA),
            }

        return self._save(
            codcon=CONSIGNMENT_CODCLAS,
            doc_type=CONSIGNMENT_DOC_TYPE,
            doc_table=CONSBANCAB_TABLE,
            num_field="numcon",
            prefix_column="precon",
            validate=_validate,
            persist=_persist,
            response=_response,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
            pref=CONSIGNMENT_PREFIX,
            reserve=_reserve,
            release=_release,
        )


class FakeConsignmentRepo(_BaseConsignmentRepo):
    """In-memory twin used by the hermetic test suite."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo | None = None,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering or store.numbering,
        )


class RealConsignmentRepo(_BaseConsignmentRepo):
    """Real MySQL writer (same sequence, InnoDB journal + MyISAM rows)."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
        )


def get_consignment_repo() -> ConsignmentRepo:
    """FastAPI dependency: the real MySQL-backed repo."""
    from motoshop_api.erp.cash.store import get_cash_store
    from motoshop_api.erp.idempotency import get_idempotency_repo
    from motoshop_api.erp.journal import get_journal_repo
    from motoshop_api.erp.numbering import get_contadores_repo

    return RealConsignmentRepo(
        store=get_cash_store(),
        journal=get_journal_repo(),
        idempotency=get_idempotency_repo(),
        numbering=get_contadores_repo(),
    )


__all__ = [
    "AnnulledDocumentError",
    "ARQUEO_CLASSES",
    "ARQUEO_CODCON",
    "ARQUEO_DOC_TYPE",
    "ArqueoRepo",
    "CARTERA_CUENTA",
    "CARTERA_CUENTA_ALIASES",
    "CASH_CUENTA",
    "CONSIGNMENT_AFEPAG",
    "CONSIGNMENT_CODCLAS",
    "CONSIGNMENT_DOC_TYPE",
    "CONSIGNMENT_PREFIX",
    "CONSIGNMENT_TIPPAG",
    "CashMovementsRepo",
    "ConsignmentRepo",
    "EGRESS_CODCON",
    "EGRESS_DOC_TYPE",
    "FakeArqueoRepo",
    "FakeCashMovementsRepo",
    "FakeConsignmentRepo",
    "FakeReceiptsRepo",
    "INGRESS_CODCON",
    "INGRESS_DOC_TYPE",
    "MOVEMENT_ENTRADA",
    "MOVEMENT_SALIDA",
    "NUMPAG_MAX_LEN",
    "PAYMENT_TIPCLAS",
    "RECEIPT_CODCON",
    "RECEIPT_DOC_TYPE",
    "RealArqueoRepo",
    "RealCashMovementsRepo",
    "RealConsignmentRepo",
    "RealReceiptsRepo",
    "ReceiptOverpaymentError",
    "ReceiptsRepo",
    "SOLCRE_TIPCLAS",
    "get_arqueo_repo",
    "get_cash_movements_repo",
    "get_consignment_repo",
    "get_receipts_repo",
    "open_balance",
    "payment_duality",
]
