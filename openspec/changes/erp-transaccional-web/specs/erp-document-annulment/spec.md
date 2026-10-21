# erp-document-annulment Specification (delta — new capability)

## Purpose

Annulment of web postable documents (invoices, receipts, cash docs) with FULL reversal parity
to `Boteliminar.cs` (code_analysis §7): ordered guards (`Veri_Anul`, `Hay_Cie_Eli`
period-lock, `Valid_EdiDocele` electronic-accepted block), permission + mandatory reason,
flag inversion (`estfven/estcue/estado/estfin`), stock recomputation from the kardex truth
(`AcInv_Eli_Anul`), `motanudoc` audit, and mirrored `app_doc_journal` state. Numbers are never
reused after annulment.

## ADDED Requirements

### Requirement: Ordered guard chain before annulment

The annulment operation MUST evaluate guards in the legacy order and fail fast with the
specific reason: (1) not already annulled (`Veri_Anul`), (2) document date not inside any
`cierresper` period (`Hay_Cie_Eli`), (3) electronic document not accepted by DIAN
(`Valid_EdiDocele` — `estfele` in {1,2} blocks), (4) actor holds the annulment permission
(legacy `N049` equivalent — web role gate), (5) a non-empty reason.

#### Scenario: Double annulment rejected

- GIVEN a document already with `estfven = 'A'`
- WHEN annulment is requested again
- THEN the response is `409` stating the document is already annulled and `motanudoc` is not duplicated

#### Scenario: Period-locked document rejected

- GIVEN the document date falls inside a `cierresper` range
- WHEN annulment is requested
- THEN the response is `409` naming the closed period, and no flags change

#### Scenario: DIAN-accepted electronic document rejected

- GIVEN an invoice whose `estfele` is `1` or `2` (accepted)
- WHEN annulment is requested
- THEN the response is `409` stating the electronic acceptance block, before any write

#### Scenario: Missing reason rejected

- GIVEN an authorized annulment request with an empty reason
- WHEN it arrives
- THEN the response is `422` requiring the reason, and no writes occur

#### Scenario: Vendedor is not authorized to annul

- GIVEN a `vendedor` JWT
- WHEN annulment is requested
- THEN the response is `403` (role gate), regardless of document state

### Requirement: Full flag reversal on annulment

Annulment MUST invert every state flag the document family wrote, within one unit-of-work:
`facventas.estfven = 'A'` (or the family's estado column), all accounting entries
`detcuentas.estcue = 'A'`, all payment rows `detapago.estado = 'A'`, and financing rows
`financiacion.estfin = 'A'` when present — for the exact document number only.

#### Scenario: Annulled invoice flips all its flags

- GIVEN a posted invoice with lines, payments, and causación
- WHEN the annulment commits
- THEN `estfven`, every `detcuentas.estcue` and every `detapago.estado` of that number are `'A'` and no other document's rows changed

#### Scenario: Annulled receipt flips payment and its entries

- GIVEN a receipt with `detapago` rows and cartera credits
- WHEN it is annulled
- THEN `detapago.estado = 'A'` and its `detcuentas` rows are `estcue = 'A'`

#### Scenario: Credit document with financing rows

- GIVEN an annulled document that had `financiacion` cuotas
- WHEN the annulment commits
- THEN all of that credit's `detfinancia`-backed rows carry `estfin = 'A'`

### Requirement: Stock recomputation from kardex after annulment

After the accounting entries are flipped, stock MUST be recomputed from `detcuentas`
(kardex truth — `Recal_Cat`/`AcInv_Eli_Anul` parity) rather than blind-adding back:
`exiprod` MUST equal the recomputation over the full movement history with the annulled
document's movements excluded.

#### Scenario: Annulled sale restores stock to kardex truth

- GIVEN `exiprod = 10`, a sale of 3 (→ 7), and the sale is annulled
- WHEN annulment commits
- THEN `exiprod` reads `10` and additionally equals the value recomputed from `detcuentas` movements alone

#### Scenario: Recompute path equals direct path

- GIVEN two independent runs — (a) flip + recompute-from-kardex, (b) previously recorded correct pre-sale stock
- WHEN the annulment completes
- THEN both runs yield the same `exiprod` for every touched product

### Requirement: Audit trail and journal mirroring

Every annulment MUST append `motanudoc` (`numdoc`, `fecanu`, `motanu` truncated to 800 chars,
`codemp`, `horanu`, `codclas`, `fecdoc`, `tipo 'A'`) and MUST set the document's
`app_doc_journal` row to `ANNULLED`. Annulment itself is idempotent: a retried annulment
(that already succeeded) returns the same outcome without a second audit row.

#### Scenario: Motivo recorded and truncated

- GIVEN an annulment reason longer than 800 characters
- WHEN the annulment commits
- THEN `motanudoc` stores the reason truncated to 800 chars with `tipo = 'A'` and the actor

#### Scenario: Idempotent replay of annulment

- GIVEN a successful annulment under Idempotency-Key `K`
- WHEN the annulment is retried with key `K`
- THEN the response is the original outcome and exactly one `motanudoc` row exists for the document

### Requirement: Coexistence — annulment under parallel desktop use

Annulment MUST operate while desktop Hermes runs: annulled web documents appear in the
desktop's annulled-document report (same `estado` vocabularies), numbers are never reused
(not even allowed into `Bus_Con_Act` heal targets), and desktop live queries see the annulled
state after commit.

#### Scenario: Desktop report shows web annulment

- GIVEN a web-posted, then web-annulled invoice
- WHEN the desktop runs its annulled/documents query afterwards
- THEN the invoice appears with `estfven = 'A'` and its number remains occupied in `contadores` (the counter does not walk back)
