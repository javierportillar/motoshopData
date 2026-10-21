"""Collections & cash save repos (slice 4 — tasks 4.1–4.5).

Legacy parity (docs/hermes):
- **Graba_Fpago duality** (code_analysis §5.3): the payment row carries
  ``soldeb`` for normal payment documents (S01 receipts, S02/S03 cash docs…)
  and ``solcre`` for the note-type classes (S14/S21) — never both non-zero.
- **Live CxC balance**: the open balance of a receivable is the truth
  ``SUM(detcuentas.valdeb − valhab)`` on the cartera account of that
  document. A receipt NEVER over-applies (CC-1) and NEVER targets an annulled
  document (``estfven='A'``).
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

from motoshop_api.erp.cash.schemas import ReceiptCreate
from motoshop_api.erp.cash.store import (
    DETAPAGO_TABLE,
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
#: Cartera account (CxC) — the account the receivable balance lives on.
CARTERA_CUENTA = "1305"
#: Default cash account when the payment form does not carry one.
CASH_CUENTA = "1105"

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
    cartera account — the receipt's own credit rows land on the same document,
    so the balance always reflects what has actually been collected.
    """
    total = ZERO
    for row in store.ledger_rows(str(numfven), codcue):
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


class _BaseReceiptsRepo:
    """Shared save sequence for the fake and the real receipt repo."""

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
        self.store = store
        self.journal = journal
        self.idempotency = idempotency
        self.numbering = numbering
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
        if idempotency_key:
            stored = self.idempotency.get(idempotency_key)
            if stored is not None:
                return stored

        computed = self._validate(body)

        pref = self.numbering.resolve_prefix(RECEIPT_CODCON)
        entry = self.journal.open_pending(
            codclas=RECEIPT_CODCON,
            pref=pref,
            doc_type=RECEIPT_DOC_TYPE,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        entry_id = entry.id or 0

        try:
            number = self.numbering.reserve(
                codcon=RECEIPT_CODCON,
                pref=pref,
                doc_table=DETAPAGO_TABLE,
                num_field="numnum",
                prefix_column="predoc",
            )
        except Exception as exc:
            self.journal.mark_failed(entry_id, str(exc))
            raise

        self.journal.record_number(entry_id, number)

        written: list[tuple[str, dict]] = []
        try:
            self._persist(body, computed, number, pref, actor, empresa, written)
        except Exception as exc:
            for table, row in reversed(written):
                self.store.discard(table, row)
            self.journal.mark_failed(entry_id, str(exc))
            raise ErpSaveFailed(
                f"El recibo no pudo guardarse: {exc}",
                docnum=number,
                retryable=True,
            ) from exc

        self.store.commit()
        self.journal.mark_committed(entry_id, number)

        response = {
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
        if idempotency_key:
            self.idempotency.store(
                idempotency_key,
                doc_type=RECEIPT_DOC_TYPE,
                tenant=tenant,
                actor=actor,
                request_id=request_id,
                response=response,
            )
        return response

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
            "numpag": body.referencia or "",
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
        # lands on the cash/bank account of the payment form.
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


__all__ = [
    "AnnulledDocumentError",
    "CARTERA_CUENTA",
    "CASH_CUENTA",
    "FakeReceiptsRepo",
    "PAYMENT_TIPCLAS",
    "RECEIPT_CODCON",
    "RECEIPT_DOC_TYPE",
    "RealReceiptsRepo",
    "ReceiptOverpaymentError",
    "ReceiptsRepo",
    "SOLCRE_TIPCLAS",
    "get_receipts_repo",
    "open_balance",
    "payment_duality",
]
