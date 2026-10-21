# erp-collections-cash Specification (delta — new capability)

## Purpose

Web collections and cash: receipts applied to open CxC (`detapago` rows + `detcuentas`
cartera credits, §5.3), deprecated-but-real cash concepts and egresses (`comprobantes`, S02/S03
via `concepingegr` concepts), minimal cash arqueo (`cajaarqueo` + `detcajarq`, tiparq
1=billetes/2=monedas/3=otros, code_analysis §8), and bank consignments (`consbancab` with its
own counter in `formapago.numcon`). All cash docs share the contadores engine and inherit the
period-lock rule (`Hay_Cie_Eli`) at creation time.

## ADDED Requirements

### Requirement: Payments applied to open CxC

The system MUST allow receipts (S01-type payment documents) that apply an amount against a
specific open invoice balance, where the open balance is the live truth
`SUM(detcuentas.valdeb − valhab)` for that document's cartera account. A receipt MUST NOT
over-apply beyond the open balance and MUST NOT target annulled documents.

#### Scenario: Full payment closes the balance

- GIVEN an open invoice with balance 150 000
- WHEN a receipt of 150 000 is posted
- THEN `detcuentas` gains a credit of 150 000 against the cartera account and the invoice balance reads `0`, (with the app_doc_journal `COMMITTED`)

#### Scenario: Partial payment leaves open balance

- GIVEN a balance of 300 000
- WHEN a receipt of 100 000 posts
- THEN the balance reads `200 000` afterwards

#### Scenario: Over-payment rejected

- GIVEN a balance of 50 000
- WHEN a receipt of 60 000 is attempted
- THEN the response is `422` with the remaining available balance in the error detail, and no rows persist

#### Scenario: Annulled target rejected

- GIVEN an invoice with `estfven = 'A'`
- WHEN a receipt targets it
- THEN the response is `409` with the annulled-document reason

### Requirement: Formapago duality parity (soldeb/solcre)

Payment rows MUST keep the legacy débito/crédito duality driven by the document tipclas:
normal receipts/cash docs write `soldeb`, reversed note-type docs write `solcre` — never both
non-zero on the same row — replicating `Graba_Fpago`.

#### Scenario: Receipt rows carry soldeb

- GIVEN a standard S01 receipt for 40 000
- WHEN it posts
- THEN its `detapago` row has `soldeb = 40000.0` and `solcre = 0`

#### Scenario: Note-type doc rows carry solcre

- GIVEN a credit-note-type payment document (tipclas in the solcre set)
- WHEN it posts
- THEN its rows carry `solcre` with `soldeb = 0`

### Requirement: Cash concepts and egress documents

The system MUST support income/expense cash concepts (`concepingegr`) posted as egress-type
documents (`comprobantes`) with their counter via contadores and causación into `detcuentas`
(debit to the concept's expense account / credit to the cash or bank account), with
`totegr`-style totals computed server-side.

#### Scenario: Egress with expense concept balances

- GIVEN an approved expense concept mapped to an expense account
- WHEN an egress document of 90 000 posts
- THEN `detcuentas` contains a 90 000 debit to the expense account and a 90 000 credit to the cash account, and debits equal credits

### Requirement: Minimal cash arqueo with invariants

The system MUST support cash counting (arqueo) writing `cajaarqueo` (header with `salcaj`,
`tiparq`, `estarq 'B'`) and `detcajarq` denomination rows (tiparq 1/2/3). Invariants MUST be
enforced server-side: the header amount equals `Σ(cantden × denomination value)` across rows,
and each row belongs to exactly one tiparq class.

#### Scenario: Arqueo totals equal denomination sum

- GIVEN denomination rows for bills (tiparq 1) summing 300 000 and coins (tiparq 2) summing 12 500
- WHEN the arqueo posts with header `salcaj`
- THEN the header reads exactly `312500.0` and the rows are stored with their tiparq classes

#### Scenario: Inconsistent arqueo rejected

- GIVEN a payload whose `salcaj` does not match the denomination sum
- WHEN it arrives
- THEN the response is `422` naming the difference, and nothing persists

### Requirement: Bank consignments with their own counter

Consignments MUST be captured in `consbancab` and, when a payment form of bank-consignment
type (`tippag = 2`, `afepag = 22`) is used, MUST reserve their number from
`formapago.numcon` exactly once per posting.

#### Scenario: Consignment increments its bank counter once

- GIVEN the bank consignment form's current `numcon`
- WHEN a consignment of 200 000 posts and the save completes
- THEN `consbancab` has one row for the consignment and `formapago.numcon` advanced by exactly one
- AND a retry with the same Idempotency-Key does not advance the counter a second time

### Requirement: Period lock applies at creation for dated cash documents

Cash documents dated inside any closed accounting period (`cierresper` rows of type P/M/A)
MUST be rejected at creation time — the same `Hay_Cie_Eli` truth the annulment path uses.

#### Scenario: Backdated receipt into closed period rejected

- GIVEN `cierresper` covers 2025-01-01..2025-01-31
- WHEN a receipt dated 2025-01-15 is attempted
- THEN the response is `409` with the period-lock reason and no ledger rows are written

### Requirement: Coexistence — one cash drawer truth for desktop and web

Because web cash docs write the same legacy tables, the daily cash reconciliation used by
desktop (`SUM(detapago.valpag)` by form) MUST count web receipts identical to desktop ones,
and cash document numbering MUST go through the shared contadores engine.

#### Scenario: Web receipts count in the daily cash report

- GIVEN desktop and web both posting receipts during the day
- WHEN the day's cash reconciliation aggregates `detapago` for the drawer
- THEN web and desktop receipts are both counted exactly once each, with no duplicates from numbering conflicts
