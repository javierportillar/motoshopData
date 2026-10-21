"""Invoice save repo — POS sale persistence (tasks 3.3/3.4/3.5).

The save follows the 3-phase sequence of ADR-0008-03:

    φ1  journal PENDING (InnoDB, autocommitted)  ← write-ahead intent
    φ2  numbering: contadores reservation (LOCK TABLES contadores WRITE,
        bounded wait, Bus_Con_Act heal, Valid_NumFin window)
    φ3  legacy rows: facventas → detfventas → detapago → detcuentas
    φ4  journal COMMITTED + idempotency snapshot

``LOCK TABLES`` implicitly commits in MySQL 5.0.45, so φ2 CANNOT be nested
inside φ3: the phases serialize and the journal is the crash detector
(orphan PENDING entries are healed by ``heal_stale_pending``).

Legacy parity (docs/hermes):
- totdet = (valuni − dctpes + ivapes + ipopes) × candet, exact Decimal
  (invoicing/totals.py, ADR-0008-07).
- The client never owns ``totdet`` nor the header totals: a client snapshot
  that disagrees with the server formuleo is rejected 422 naming the field
  (SI-5s2) and NOTHING is written.
- Master state is checked through the FROZEN slice-2 seam
  (``ensure_master_active`` → ``InactiveMasterError``) before any write.
- Stock is decremented with ``Edi_CueInvProd`` parity (warning only on
  negative stock, ``stock_negative_policy`` decides the final word).
- Payments are written with the ``Graba_Fpago`` duality (soldeb/solcre by
  ``tipclas``) and the accounting causación lands in ``detcuentas``.

Because the legacy tables are MyISAM (no atomic multi-table transaction),
a mid-save failure is compensated row by row (``discard``) and the journal
is marked FAILED, so the retry contract is a clean retryable 503.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.idempotency import IdempotencyRepo
from motoshop_api.erp.invoicing.schemas import InvoiceCreate
from motoshop_api.erp.invoicing.totals import header_totals, line_totals
from motoshop_api.erp.journal import JournalRepo
from motoshop_api.erp.masters.validators import (
    InactiveMasterError,
    LegacyValidationError,
    ensure_master_active,
)
from motoshop_api.erp.numbering import ContadoresRepo, FakeContadoresRepo

logger = logging.getLogger(__name__)

#: `contadores.codcon` of the POS sale document type (numcon=15).
INVOICE_CODCON = "S15"
#: Journal/audit document type of the POS sale.
INVOICE_DOC_TYPE = "factura_venta"
#: Legacy table holding the invoice header.
INVOICE_HEADER_TABLE = "facventas"
#: Legacy table holding the invoice lines.
INVOICE_LINES_TABLE = "detfventas"
#: Legacy table holding the payments.
INVOICE_PAYMENTS_TABLE = "detapago"
#: Legacy table holding the accounting causación.
INVOICE_JOURNAL_TABLE = "detcuentas"
#: Number field of the header table.
INVOICE_NUM_FIELD = "numfven"

# ─── Legacy MasVital conventions (measured on the 3,554 historical rows) ───
#: `facventas.codemp` carries the OPERATOR NIT, not the company code: the
#: constant 59312669 on every historical row, while `empcod` is empty.
LEGACY_OPERATOR_NIT = "59312669"
#: The cash register of the legacy POS (`facventas.codcaj` = C1, never 01).
LEGACY_CASH_REGISTER = "C1"
#: PUC accounts observed in the legacy `detcuentas` causación.
LEGACY_ACCOUNT_CASH = "11050501"     # Caja general / efectivo
LEGACY_ACCOUNT_BANK = "11100501"     # Bancos
LEGACY_ACCOUNT_RECEIVABLE = "13050501"  # Clientes nacionales / cartera
LEGACY_ACCOUNT_INCOME = "41359501"   # Ingreso comercio
LEGACY_ACCOUNT_IVA = "24080102"      # IVA generado
LEGACY_ACCOUNT_COST = "61359501"     # Costo de ventas
LEGACY_ACCOUNT_INVENTORY = "14350101"  # Inventario

#: Payment forms that settle into cash / the register.
LEGACY_CASH_FORMS = frozenset({"F01", "F08", "CASH", "EFECTIVO"})
#: Payment forms that leave a receivable instead of money.
LEGACY_CREDIT_FORMS = frozenset({"F10", "CREDIT", "CREDITO", "CRÉDITO"})


def legacy_debit_account(codpag: str | None) -> str:
    """PUC account that receives the debit for a payment form.

    Cash and register forms hit caja; credit forms leave a receivable; every
    other form (card, transfer, cheque, bank consignment) goes through bancos.
    """
    code = str(codpag or "").strip().upper()
    if code in LEGACY_CASH_FORMS:
        return LEGACY_ACCOUNT_CASH
    if code in LEGACY_CREDIT_FORMS:
        return LEGACY_ACCOUNT_RECEIVABLE
    return LEGACY_ACCOUNT_BANK

ZERO = Decimal("0")


class InvoiceStore(Protocol):
    """Row-level persistence contract (fake twin + real MySQL writer)."""

    def stage_insert(self, table: str, row: dict) -> None: ...

    def discard(self, table: str, row: dict) -> None: ...

    def stage_update(self, table: str, key: dict, values: dict) -> None: ...

    def stage_stock_decrement(self, codprod: str, qty: Decimal) -> None: ...

    def commit(self) -> None: ...


@dataclass
class FakeInvoiceStore:
    """In-memory twin of the legacy invoice tables."""

    facventas: list[dict] = field(default_factory=list)
    detfventas: list[dict] = field(default_factory=list)
    detapago: list[dict] = field(default_factory=list)
    detcuentas: list[dict] = field(default_factory=list)
    ubiprodbod: list[dict] = field(default_factory=list)
    fail_table: str | None = None
    committed: bool = False

    def __post_init__(self) -> None:
        self.terceros: dict[str, dict] = {
            "222222222222": {
                "nitter": "222222222222",
                "nomter": "CLIENTE DEMO",
                "inater": "NO",
                "cupblo": "R",
            },
            "900123456": {
                "nitter": "900123456",
                "nomter": "MOTOSHOP CALI",
                "inater": "NO",
                "cupblo": "R",
                "emppro": "SI",
            },
        }
        self.productos: dict[str, dict] = {
            "PROD1": {
                "codprod": "PROD1",
                "nomprod": "BUJA NGK",
                "actprod": "A",
                "exiprod": Decimal("120"),
            },
            "PROD2": {
                "codprod": "PROD2",
                "nomprod": "FILTRO ACEITE",
                "actprod": "A",
                "exiprod": Decimal("80"),
            },
        }
        self.sellers: dict[str, dict] = {
            "VEN01": {"nitvend": "VEN01", "nombre": "MOTOSHOP CALI"},
            "900123456": {"nitvend": "900123456", "nombre": "MOTOSHOP CALI"},
        }
        self.numbering: FakeContadoresRepo = FakeContadoresRepo()
        self.numbering.seed(
            _contador_row(conres=501, numini=1, numfin=99999)
        )
    # ─── staged writes ────────────────────────────────────────────

    def company_nit(self) -> str:
        """The company's own NIT (the seller) - legacy ``emppro = 'SI'``."""
        for nitter, row in self.terceros.items():
            if row.get("emppro") == "SI":
                return nitter
        return ""

    def stage_insert(self, table: str, row: dict) -> None:
        if self.fail_table and self.fail_table == table:
            raise RuntimeError(f"injected failure on {table}")
        rows = self._rows_for(table)
        rows.append(row)

    def discard(self, table: str, row: dict) -> None:
        rows = self._rows_for(table)
        if row in rows:
            rows.remove(row)

    def stage_update(self, table: str, key: dict, values: dict) -> None:
        if self.fail_table and self.fail_table == table:
            raise RuntimeError(f"injected failure on {table}")
        for row in self._rows_for(table):
            if all(row.get(k) == v for k, v in key.items()):
                row.update(values)

    def stage_stock_decrement(self, codprod: str, qty: Decimal) -> None:
        """Mirror the real writer: decrement the in-memory product stock."""
        row = self.productos.get(codprod)
        if row is None:
            return
        row["exiprod"] = Decimal(str(row.get("exiprod", ZERO))) - Decimal(str(qty))

    def commit(self) -> None:
        self.committed = True

    def _rows_for(self, table: str) -> list[dict]:
        return {
            INVOICE_HEADER_TABLE: self.facventas,
            INVOICE_LINES_TABLE: self.detfventas,
            INVOICE_PAYMENTS_TABLE: self.detapago,
            INVOICE_JOURNAL_TABLE: self.detcuentas,
            "ubiprodbod": self.ubiprodbod,
        }[table]


def _contador_row(
    *, conres: int, numini: int | None, numfin: int | None
) -> Any:
    from motoshop_api.erp.numbering import ContadorRow

    return ContadorRow(
        codcon=INVOICE_CODCON,
        descon="FACTURA DE VENTA POS",
        numcon=15,
        numini=numini,
        numfin=numfin,
        numauto="SI",
        preres="FVP",
        conres=conres,
        actcon="S",
        tipclas="S15",
    )


class InvoicesRepo(Protocol):
    """Contract shared by the fake twin and the real MySQL repo."""

    def create(
        self,
        body: InvoiceCreate,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict: ...


class _BaseInvoicesRepo:
    """Shared save sequence for the fake and the real repo."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
        stock_policy: str = "warn",
    ) -> None:
        self.store = store
        self.journal = journal
        self.idempotency = idempotency
        self.numbering = numbering
        self.stock_policy = stock_policy

    # ─── public API ───────────────────────────────────────────────

    def create(
        self,
        body: InvoiceCreate,
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

        pref = self.numbering.resolve_prefix(INVOICE_CODCON)
        entry = self.journal.open_pending(
            codclas=INVOICE_CODCON,
            pref=pref,
            doc_type=INVOICE_DOC_TYPE,
            tenant=tenant,
            empresa=empresa,
            actor=actor,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        entry_id = entry.id or 0

        try:
            number = self.numbering.reserve(
                codcon=INVOICE_CODCON,
                pref=pref,
                doc_table=INVOICE_HEADER_TABLE,
                num_field=INVOICE_NUM_FIELD,
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
                f"La venta no pudo guardarse: {exc}",
                docnum=number,
                retryable=True,
            ) from exc

        self.store.commit()
        self.journal.mark_committed(entry_id, number)

        response = {
            "numfven": number,
            "prefven": pref,
            "totals": computed["totals"],
            "lines": computed["lines"],
        }
        if idempotency_key:
            self.idempotency.store(
                idempotency_key,
                doc_type=INVOICE_DOC_TYPE,
                tenant=tenant,
                actor=actor,
                request_id=request_id,
                response=response,
            )
        return response

    # ─── receipt (task 3.7) ──────────────────────────────────────

    def receipt(self, numfven: int) -> dict | None:
        """Assemble the printable receipt of a saved invoice.

        Returns ``None`` when the invoice does not exist. The DIAN QR slot
        stays a placeholder until the document is accepted (``estfele``);
        the official catalogue URL is used once the CUFE is known.
        """
        from motoshop_api.erp.invoicing.receipt import build_receipt

        header = next(
            (row for row in self.store.facventas if row.get("numfven") == numfven),
            None,
        )
        if header is None:
            return None
        lines = [
            row
            for row in self.store.detfventas
            if row.get("numfven") == numfven
        ]
        payments = [
            row
            for row in self.store.detapago
            if row.get("numfven") == numfven
        ]
        totals = {
            "subfven": header.get("subfven", ZERO),
            "totdct": header.get("totdct", ZERO),
            "totiva": header.get("totiva", ZERO),
            "totipo": header.get("totipo", ZERO),
            "totfven": header.get("totfven", ZERO),
        }
        return build_receipt(
            header=header,
            resolution={"empresa": "", "caja": header.get("codcaj", "")},
            lines=lines,
            payments=payments,
            totals=totals,
        )

    # ─── validation (before φ1: nothing is reserved) ──────────────

    def _validate(self, body: InvoiceCreate) -> dict:
        fields: dict[str, str] = {}

        if not body.lines:
            fields["lines"] = "La factura debe tener al menos una línea"

        client = self.store.terceros.get(body.nitter)
        if client is None:
            fields["nitter"] = "El tercero no existe"
        else:
            try:
                ensure_master_active(client, "tercero")
            except InactiveMasterError:
                raise

        if body.nitvend not in self.store.sellers:
            fields["nitvend"] = "El vendedor no existe"

        lines: list[dict] = []
        for index, line in enumerate(body.lines):
            product = self.store.productos.get(line.codprod)
            if product is None:
                fields[f"lines[{index}].codprod"] = "El producto no existe"
                continue
            try:
                ensure_master_active(product, "producto")
            except InactiveMasterError:
                raise
            if line.candet <= ZERO:
                fields[f"lines[{index}].candet"] = "La cantidad debe ser mayor que cero"
            computed_line = line_totals(line)
            if computed_line["totdet"] < ZERO:
                fields[f"lines[{index}].totdet"] = "El total de la línea no puede ser negativo"
            lines.append(computed_line)

        totals = header_totals(body.lines)
        if totals["totfven"] < ZERO:
            fields["totfven"] = "El total de la factura no puede ser negativo"

        client_totals = body.client_totals
        if client_totals is not None:
            for name in ("subfven", "totdct", "totiva", "totipo", "totfven"):
                client_value = getattr(client_totals, name)
                if client_value is None:
                    continue
                if client_value != totals[name]:
                    fields[f"client_totals.{name}"] = (
                        "El total enviado por el cliente no coincide con el "
                        "cálculo del servidor"
                    )

        paid = sum((p.amount for p in body.payments), ZERO)
        if body.payments and paid != totals["totfven"]:
            fields["payments"] = (
                "La suma de los pagos no coincide con el total de la factura"
            )
        for index, payment in enumerate(body.payments):
            if payment.amount <= ZERO:
                fields[f"payments[{index}].amount"] = (
                    "El valor del pago debe ser mayor que cero"
                )

        if fields:
            raise LegacyValidationError(fields)

        return {"totals": totals, "lines": lines}

    # ─── persistence (φ3) ─────────────────────────────────────────

    def _persist(
        self,
        body: InvoiceCreate,
        computed: dict,
        number: int,
        pref: str,
        actor: str,
        empresa: str,
        written: list[tuple[str, dict]],
    ) -> None:
        """Write the legacy rows using the REAL MySQL 5.0.45 column names.

        The legacy schema does not match the POS payload field names, so the
        mapping is explicit here:

        - ``facventas`` has no ``actor``/``empresa``. The web operator is
          audited in ``app_doc_journal``/``app_idempotency``; the header keeps
          the legacy conventions instead: ``codemp`` = operator NIT,
          ``empcod`` empty, ``codcaj`` = ``C1`` and ``nomuso`` blank.
        - ``detfventas`` has no ``prefven``/``numlin``: the correlative is
          ``numite``.
        - ``detapago`` numbers with ``numnum``/``predoc`` and keeps the
          reference in ``numpag``.
        - ``detcuentas`` books the legacy PUC chart, numbered by
          ``numnum``/``prenum``: the debit follows the payment form
          (caja / bancos / cartera), then income, IVA and the cost pair.
        - ``productos.exiprod`` is decremented by ``candet`` in the same
          unit of work, as a delta.

        Values are clipped to the real column widths because the server runs
        with STRICT_TRANS_TABLES: an oversized value is a 1406 error, not a
        silent truncation.
        """
        totals = computed["totals"]
        doc_class = getattr(body, "codclas", None) or INVOICE_CODCON
        # The payload defaults codcaj to the placeholder "01"; the legacy
        # register is C1, so a real code only wins when it is not the default.
        raw_caja = str(body.codcaj or "").strip()
        caja_code = LEGACY_CASH_REGISTER if raw_caja in ("", "01") else raw_caja[:4]
        # facventas.codpag is NOT NULL without a default: mirror the first
        # payment's form ("01" when the sale has no payment rows).
        header_pag = str(body.payments[0].codpag if body.payments else "01")[:4]
        now_dt = datetime.now()

        header = {
            "numfven": number,
            "codclas": doc_class,
            "nomdoc": "FACTURA DE VENTA",
            "prefven": pref,
            "fecfven": now_dt,
            "nitter": body.nitter,
            "clifven": (body.nomclien or "")[:120],
            "nitvend": body.nitvend or "",
            "codcaj": caja_code,
            "nomuso": "",
            "obsfven": body.obsfven or "",
            "subfven": totals["subfven"],
            "totdct": totals["totdct"],
            "totiva": totals["totiva"],
            "totipo": totals["totipo"],
            "totfven": totals["totfven"],
            "estfven": "B",
            "codemp": LEGACY_OPERATOR_NIT,
            "empcod": "",
            "estfele": "N",
            "codpag": header_pag,
        }
        self.store.stage_insert(INVOICE_HEADER_TABLE, header)
        written.append((INVOICE_HEADER_TABLE, header))

        line_costs: list[tuple[Decimal, str]] = []
        for index, line in enumerate(body.lines):
            # detfventas.codmed is a real unit code from the legacy master
            # ('001' in 6,450 of 7,840 lines); the POS payload defaults to the
            # placeholder 'UND', which legacy only ever stored once.
            product = self.store.productos.get(line.codprod) or {}
            unit = str(product.get("codmed") or "").strip()
            if not unit or unit.upper() == "UND":
                unit = str(line.codmed or "").strip()
            if not unit or unit.upper() == "UND":
                unit = "001"
            # detfventas.cosprod snapshots the unit cost at sale time; the
            # legacy causación books cost from this column, not from the
            # product master (cosulc drifts: 10588.96 vs 10550.00 on 3554).
            unit_cost = Decimal(str(product.get("cosulc") or ZERO))
            line_costs.append(
                ((line.candet * unit_cost).quantize(Decimal("0.01")), (line.nomdet or "")[:150])
            )
            line_row = {
                "numfven": number,
                "codclas": doc_class,
                "numite": index + 1,
                "codprod": line.codprod,
                "nomdet": (line.nomdet or "")[:300],
                "candet": line.candet,
                "valuni": line.valuni,
                "dctpes": line.dctpes,
                "ivapes": line.ivapes,
                "ipopes": line.ipopes,
                "dctpor": line.dctpor,
                "ivapor": line.ivapor,
                "ipopor": line.ipopor,
                "codbod": (line.codbod or "01")[:4],
                "codmed": unit[:3],
                "facumed": line.facumed or Decimal("1"),
                "cosprod": unit_cost,
                "totdet": computed["lines"][index]["totdet"],
            }
            self.store.stage_insert(INVOICE_LINES_TABLE, line_row)
            written.append((INVOICE_LINES_TABLE, line_row))

        for index, payment in enumerate(body.payments):
            payment_row = {
                "numnum": number,
                "codclas": doc_class,
                "predoc": pref,
                "numite": index + 1,
                "fecdoc": now_dt,
                "codpag": str(payment.codpag or "01")[:4],
                "valpag": payment.amount,
                "valefe": payment.amount,
                # Legacy leaves despag empty (2,820 of 2,821 rows); the bank
                # name is free text the POS never sends. Do not invent a
                # description from the form code.
                "despag": (getattr(payment, "despag", "") or "")[:100],
                "numpag": (payment.referencia or "")[:20],
                "soldeb": ZERO,
                "solcre": payment.amount,
                "codemp": LEGACY_OPERATOR_NIT,
                "codcaj": caja_code,
                "estado": "B",
            }
            self.store.stage_insert(INVOICE_PAYMENTS_TABLE, payment_row)
            written.append((INVOICE_PAYMENTS_TABLE, payment_row))

        # Accounting causación (detcuentas) with the legacy PUC chart:
        #   one DEBIT per payment, on the account its form settles into
        #     (caja 11050501 / bancos 11100501 / cartera 13050501);
        #   41359501 Ingreso comercio  CREDIT base (total - IVA)
        #   24080102 IVA generado      CREDIT IVA desglosado
        #   61359501 Costo de ventas   DEBIT  candet * cosprod, per line
        #   14350101 Inventario        CREDIT the same amount
        # The income credit absorbs any impoconsumo (totipo) so the entry always
        # balances; the observed legacy chart has no separate IPO account.
        entries: list[tuple[str, str, Decimal, Decimal]] = []
        if body.payments:
            for payment in body.payments:
                entries.append(
                    (
                        legacy_debit_account(payment.codpag),
                        "Factura de Venta",
                        payment.amount,
                        ZERO,
                    )
                )
        else:
            entries.append(
                (LEGACY_ACCOUNT_CASH, "Factura de Venta", totals["totfven"], ZERO)
            )
        base = totals["totfven"] - totals["totiva"]
        entries.append((LEGACY_ACCOUNT_INCOME, "Ventas Comercio", ZERO, base))
        entries.append(
            (LEGACY_ACCOUNT_IVA, "IVA generado excluido", ZERO, totals["totiva"])
        )
        for line_cost, label in line_costs:
            if line_cost <= ZERO:
                continue
            entries.append((LEGACY_ACCOUNT_COST, label, line_cost, ZERO))
            entries.append((LEGACY_ACCOUNT_INVENTORY, label, ZERO, line_cost))

        for item_index, (account, label, debit_value, credit_value) in enumerate(
            entries, start=1
        ):
            entry = {
                "numnum": number,
                "codclas": doc_class,
                "prenum": pref,
                "numite": item_index,
                "codcue": account,
                "detcue": label,
                "valdeb": debit_value,
                "valhab": credit_value,
                "fecdoc": now_dt,
                "nitter": body.nitter,
                "codemp": LEGACY_OPERATOR_NIT,
                "empcod": "",
                "estcue": "B",
            }
            self.store.stage_insert(INVOICE_JOURNAL_TABLE, entry)
            written.append((INVOICE_JOURNAL_TABLE, entry))

        # Stock decrement (Edi_CueInvProd parity): warning only when the
        # balance goes negative unless the policy says "block". The decrement
        # is staged as a delta so a concurrent legacy sale cannot be lost.
        for index, line in enumerate(body.lines):
            product = self.store.productos.get(line.codprod)
            if product is None:
                continue
            available = Decimal(str(product.get("exiprod", ZERO)))
            remaining = available - line.candet
            if remaining < ZERO and self.stock_policy == "block":
                raise LegacyValidationError(
                    {
                        f"lines[{index}].candet": (
                            "No hay existencias suficientes del producto "
                            f"{line.codprod}"
                        )
                    }
                )
            self.store.stage_stock_decrement(line.codprod, line.candet)


class FakeInvoicesRepo(_BaseInvoicesRepo):
    """In-memory twin used by the hermetic test suite."""

    def __init__(
        self,
        *,
        store: FakeInvoiceStore | None = None,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo | None = None,
        stock_policy: str = "warn",
    ) -> None:
        store = store or FakeInvoiceStore()
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering or store.numbering,
            stock_policy=stock_policy,
        )


class RealInvoicesRepo(_BaseInvoicesRepo):
    """Real MySQL writer (same sequence, InnoDB journal + MyISAM rows)."""

    def __init__(
        self,
        *,
        store: Any,
        journal: JournalRepo,
        idempotency: IdempotencyRepo,
        numbering: ContadoresRepo,
        stock_policy: str = "warn",
    ) -> None:
        super().__init__(
            store=store,
            journal=journal,
            idempotency=idempotency,
            numbering=numbering,
            stock_policy=stock_policy,
        )


def get_invoices_repo() -> InvoicesRepo:
    """FastAPI dependency: the real MySQL-backed repo."""
    from motoshop_api.erp.idempotency import get_idempotency_repo
    from motoshop_api.erp.invoicing.store import get_invoice_store
    from motoshop_api.erp.journal import get_journal_repo
    from motoshop_api.erp.numbering import get_contadores_repo

    return RealInvoicesRepo(
        store=get_invoice_store(),
        journal=get_journal_repo(),
        idempotency=get_idempotency_repo(),
        numbering=get_contadores_repo(),
    )
