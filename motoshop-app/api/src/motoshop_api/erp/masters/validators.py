"""Legacy validation parity for masters writes (spec erp-masters-write).

Pure functions — no I/O — so the routers/repos stay thin and the parity rules
are directly testable:

- ``nit_verification_digit``  CheckSum DV (mod 11 weights 3…71) for `digter`.
- ``validate_tercero_create`` legacy-required aggregate for BotGuarMa parity.
- ``validate_product_create`` required code/name/line aggregate (MW-3s1) and
  transaction-owned field rejection (MW-3s2: `exiprod`, cost).
- ``split_price``             pvsini/pvconi inclusive↔exclusive × (1+rate)
                              server-side Decimal (MW-2s3).
- ``recompute_porutil``       porutil objective-utility parity (modules.md §15
                              ModPrecio recomputo) from the transaction-owned
                              cost base.
- ``ensure_master_active``    THE FROZEN cross-slice seam (task 2.4): slice-3
                              invoice endpoints call this before φ1 and map
                              ``InactiveMasterError`` to the documented 422
                              master-state contract (see apply-progress).

Error shape convention for 4xx bodies:
    HTTPException(422, detail={"message": str, "fields": dict[str, str]})
    HTTPException(409, detail={"message": str, "field": str})
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# ═══ Domain exceptions mapped by the routers ═════════════════════════════


class LegacyValidationError(Exception):
    """Aggregate 422: every offending field is named (not first-fail)."""

    def __init__(self, fields: dict[str, str], message: str = "Datos no válidos"):
        super().__init__(message)
        self.fields = fields
        self.message = message

    def detail(self) -> dict:
        return {"message": self.message, "fields": self.fields}


class DuplicateMasterError(Exception):
    """409: the natural key already exists; the message names the field."""

    def __init__(self, field: str, value: str):
        super().__init__(f"El campo '{field}' ya existe: {value}")
        self.field = field
        self.value = value

    def detail(self) -> dict:
        return {
            "message": f"Ya existe un registro con {self.field} = '{self.value}'",
            "field": self.field,
        }


class MasterSaveFailed(Exception):
    """Non-retryable wrapped failure (Never used by default; φ3 raises
    ErpSaveFailed directly, retryable 503 contract)."""


class InactiveMasterError(Exception):
    """The frozen master-state 422 contract for transactional documents.

    Raised by :func:`ensure_master_active`; routers map ``detail()`` into
    ``HTTPException(422, detail=...)`` verbatim.
    """

    def __init__(
        self, kind: str, key_field: str, key: str, act_field: str,
        act_value: str, message: str,
    ):
        super().__init__(message)
        self.kind = kind
        self.key_field = key_field
        self.key = key
        self.act_field = act_field
        self.act_value = act_value
        self.message = message

    def detail(self) -> dict:
        return {
            "message": self.message,
            "code": "master_inactive",
            "fields": {self.key_field: "master_inactive"},
            "master_state": {self.key_field: self.key, self.act_field: self.act_value},
        }


# ═══ Verification digit (CheckSum) ═══════════════════════════════════════

_DV_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71, 73)


def nit_verification_digit(nitter: str) -> str:
    """Colombian NIT check digit (legacy `digter` parity).

    SUM = Σ digit_i × weight_i over the digits right-to-left
    (weights cycle 3,7,13,…,73). rem = SUM mod 11; DV = 0 (rem 0),
    1 (rem 1), else 11 − rem. NIT 900123456 → DV 8.
    """
    digits = [int(ch) for ch in nitter if ch.isdigit()]
    total = sum(d * w for d, w in zip(reversed(digits), _DV_WEIGHTS, strict=False))
    rem = total % 11
    if rem == 0:
        return "0"
    if rem == 1:
        return "1"
    return str(11 - rem)


# ═══ Tercero validation (BotGuarMa parity, MW-1) ═════════════════════════


def _compose_nomcom(body: Mapping[str, Any]) -> str:
    razsoc = (body.get("razsoc") or "").strip()
    if razsoc:
        return razsoc
    parts = [
        p
        for p in (
            body.get("nomter"), body.get("nomter2"),
            body.get("apeter"), body.get("apeter2"),
        ) if p
    ]
    return " ".join(str(p).strip() for p in parts)


def validate_tercero_create(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize + aggregate-validate a TerceroCreate dump; raises 422-fields."""
    errors: dict[str, str] = {}

    nitter = str(row.get("nitter") or "").strip()
    if not nitter:
        errors["nitter"] = "Identificación (nitter) requerida"
    elif (row.get("tipnit") or "").strip() == "N":
        supplied = (row.get("digter") or "").strip()
        expected = nit_verification_digit(nitter)
        if supplied != expected:
            errors["digter"] = (
                f"Dígito de verificación inválido para {nitter}: "
                f"esperado {expected}, recibido '{supplied or 'vacío'}'"
            )
    if not any([(row.get("nomter") or "").strip(), (row.get("razsoc") or "").strip()]):
        errors["nomter"] = "Nombre (o razón social) requerido por el maestro heredado"
    if not str(row.get("dirter") or "").strip():
        errors["dirter"] = "Dirección requerida por el maestro heredado"
    if not str(row.get("telter") or "").strip():
        errors["telter"] = "Teléfono requerido por el maestro heredado"

    if errors:
        raise LegacyValidationError(errors, "Tercero con datos no válidos")

    return {
        **row,
        "nomcom": (row.get("nomcom") or "").strip() or _compose_nomcom(row),
        "regven": "S",  # legacy default for active registrations
        "feccrea": row.get("feccrea", ""),  # real repo stamps the server date
    }


def validate_tercero_update(update: Mapping[str, Any]) -> None:
    """Aggregate guard for partial edits (identity fields are immutable)."""
    errors: dict[str, str] = {}
    if update.get("dirter") is not None and not str(update["dirter"]).strip():
        errors["dirter"] = "Dirección no puede quedar vacía"
    if update.get("telter") is not None and not str(update["telter"]).strip():
        errors["telter"] = "Teléfono no puede quedar vacío"
    if errors:
        raise LegacyValidationError(errors, "Tercero con datos no válidos")


# ═══ Product validation (MW-3s1 / MW-3s2) ════════════════════════════════

_TRANSACTION_OWNED_MSG = (
    "El stock y el costo solo se mueven por transacciones (detcuentas); "
    "no son editables por maestros"
)


def validate_transaction_owned_fields(row: Mapping[str, Any]) -> None:
    """`exiprod`/cost are transaction-owned: masters may never set them."""
    errors: dict[str, str] = {}
    if row.get("exiprod") is not None:
        errors["exiprod"] = _TRANSACTION_OWNED_MSG
    for cost_field in ("cosprod", "cosman", "cosulc", "cosant", "coskar"):
        if row.get(cost_field) is not None:
            errors[cost_field] = _TRANSACTION_OWNED_MSG
    if errors:
        raise LegacyValidationError(errors, "Campos de transacción no editables por maestros")


def validate_product_create(row: Mapping[str, Any]) -> dict[str, Any]:
    """Required code/name/line aggregate (MW-3s1) + transaction-owned guard."""
    validate_transaction_owned_fields(row)
    errors: dict[str, str] = {}
    if not str(row.get("codprod") or "").strip():
        errors["codprod"] = "Código de producto requerido"
    if not str(row.get("nomprod") or "").strip():
        errors["nomprod"] = "Nombre de producto requerido"
    if not str(row.get("codlin1") or "").strip():
        errors["codlin1"] = "Línea de producto (codlin1) requerida"
    if not str(row.get("codmed") or "").strip():
        errors["codmed"] = "Unidad base (codmed) requerida"
    if errors:
        raise LegacyValidationError(errors, "Producto con datos no válidos")

    return {**row, "actprod": row.get("actprod") or "A"}


# ═══ Pricing parity (MW-2s3, modules.md §15) ═════════════════════════════

_TWO_PLACES = Decimal("0.01")


def _half_up(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def split_price(
    pvtipo: str, pvsini: Decimal | None, pvconi: Decimal | None, iva_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (pvsini, pvconi, veniva) consistent: inclusive = exclusive × (1+rate).

    The supplied side is authoritative; the other is derived with exact
    Decimal and derived-normalized half-up quantization (ADR-0008-07).
    ``veniva`` (preciosxpro) = the IVA amount amount = pvconi − pvsini.
    """
    factor = Decimal("1") + (iva_rate / Decimal("100"))
    if pvsini is not None and pvconi is not None:
        derived = _half_up(pvsini * factor)
        if pvconi != derived:
            raise LegacyValidationError(
                {"pvconi": f"Inconsistente con pvsini × (1+{iva_rate}%): esperado {derived}"},
                "Precio inconsistente",
            )
        exclusive, inclusive = pvsini, pvconi
    elif pvsini is not None:
        exclusive = pvsini
        inclusive = _half_up(exclusive * factor)
    elif pvconi is not None:
        inclusive = pvconi
        exclusive = _half_up(inclusive / factor)
    else:
        raise LegacyValidationError(
            {"pvsini": "Se requiere pvsini (exclusivo) o pvconi (incluido)"},
            "Precio requerido",
        )
    return exclusive, inclusive, inclusive - exclusive


def recompute_porutil(price: Decimal, base_cost: Decimal) -> Decimal:
    """porutil = ((price − cost) / cost) × 100 — utilities objective parity.

    Legacy `ModPrecio` recomputes per-list utilities from the stored
    transaction-owned cost; 0 when no cost exists yet. Derived-normalized
    half-up to 2 dp (ADR-0008-07).
    """
    if base_cost <= Decimal("0"):
        return Decimal("0")
    return _half_up((price - base_cost) / base_cost * Decimal("100"))


# ═══ FROZEN cross-slice seam (task 2.4) ══════════════════════════════════


def ensure_master_active(row: Mapping[str, Any], kind: str) -> None:
    """Reject inactive/blocked masters on NEW transactional documents (MW-3s3).

    Contract consumed by slice-3 invoice endpoints (and offers the exact
    422 schema copied into apply-progress.md). ``kind``:
    - ``"producto"`` → `actprod != 'A'` rejects.
    - ``"tercero"``  → `inater == 'SI'` (inactive) or `cupblo == 'B'`
      (credit-blocked, `cupblo`) rejects.
    """
    if kind == "producto":
        act = str(row.get("actprod") or "A")
        if act != "A":
            raise InactiveMasterError(
                kind, "codprod", str(row.get("codprod")), "actprod", act,
                f"Producto '{row.get('codprod')}' inactivo (actprod='{act}')",
            )
        return
    if kind == "tercero":
        inater = str(row.get("inater") or "NO").upper()
        if inater == "SI":
            raise InactiveMasterError(
                kind, "nitter", str(row.get("nitter")), "inater", inater,
                f"Tercero '{row.get('nitter')}' inactivo (inater='{inater}')",
            )
        cupblo = str(row.get("cupblo") or "R").upper()
        if cupblo == "B":
            raise InactiveMasterError(
                kind, "nitter", str(row.get("nitter")), "cupblo", cupblo,
                f"Tercero '{row.get('nitter')}' bloqueado por cartera (cupblo='B')",
            )
        return
    raise ValueError(f"unknown master kind: {kind}")
