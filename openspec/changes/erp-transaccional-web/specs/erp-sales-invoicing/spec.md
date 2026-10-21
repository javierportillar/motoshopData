# erp-sales-invoicing Specification (delta — new capability)

## Purpose

Minimal POS-like sales invoice from the web: legacy parity for the numbering engine
(`contadores` with `LOCK TABLES` + `Bus_Con_Act` heal + `Valid_NumFin` window), line totals
formuleo (`totdet = (valuni − dctpes + ivapes + ipopes) × candet`, code_analysis §4), stock
decrement (`Edi_CueInvProd` parity), payment capture for efectivo/transferencia
(`detapago`, `Graba_Fpago` §5.3), accounting causación to `detcuentas` (§5.4), and a
browser-printed receipt (P80/ticket layout with DIAN QR placeholder). The server is the
single source of numbering while desktop Hermes keeps running on the same counters.

## ADDED Requirements

### Requirement: Server-side numbering reservation via contadores

The system MUST reserve the invoice number inside the save's unit-of-work by serializing on
`contadores` (`LOCK TABLES contadores WRITE` bounded to the counter window), reading
`conres`/`preres` for the doc type, taking `conres` as the number, and bumping `conres`. A
unique index MUST back the legacy doc table so double-booking is impossible at storage level.

#### Scenario: Two concurrent web saves get distinct numbers

- GIVEN two invoice saves racing to the same doc type
- WHEN both commit
- THEN their numbers differ and are consecutive-from-counter, and the doc table holds two distinct rows

#### Scenario: Manual numbering is forbidden for automatic doc types

- GIVEN a doc type configured with automatic numbering (`numauto`)
- WHEN a client submits an invoice with a client-supplied number
- THEN the response is `422` and `contadores` is untouched

### Requirement: Lagged counter auto-heal (Bus_Con_Act parity)

On each reservation the system MUST verify the counter is not lagging: if the next counter
value has already been used by an existing document, it MUST auto-correct to
`MAX(number)+1` before assigning, replicating `Bus_Con_Act`.

#### Scenario: Lagged counter corrected on save

- GIVEN `contadores.conres = 501` while the doc table already holds number `501`
- WHEN an invoice is saved
- THEN the assigned number is `502` and the counter is set beyond it

### Requirement: Numbering range window (Valid_NumFin parity)

The system MUST refuse to issue a number outside the resolution window (`numini ≤ n ≤
numfin`) and MUST surface the business reason to the operator.

#### Scenario: Window exhausted blocks the save

- GIVEN the resolution window's `numfin` is 500 and the next counter is 501
- WHEN the save arrives
- THEN it is rejected with an explicit resolver-range message, no document and no counter increment persists

### Requirement: Desktop coexistence for numbering

Web numbering MUST be exclusive through the shared `contadores` table: while desktop Hermes
is running (percentile of real-life concurrency), web posting MUST NOT reuse, skip, or
hand-type numbers, and web-posted invoices MUST be visible in desktop reports.

#### Scenario: Desktop lock at save time

- GIVEN the desktop process holds `contadores WRITE` when the web save starts
- WHEN the web save runs
- THEN it waits the bounded lock window and posts with the next counter value — no duplicate number lands

#### Scenario: One ledger readback

- GIVEN a web-posted invoice
- WHEN desktop Hermes lists the day's sales afterwards
- THEN the invoice appears with its real number, totals, and state — indistinguishable from a desktop posting

### Requirement: Server-authoritative totals (formuleo parity)

Line and header totals MUST be computed server-side with `Decimal` using the legacy formula:
`totdet = (valuni − dctpes + ivapes + ipopes) × candet`; header totals aggregate the lines
(`subfven = Σ valuni×candet`, `totdct/totiva/totipo` per-unit-amount × qty, `totfven = subfven
− totdct + totiva + totipo`). Values are per-unit amounts; percents live in `dctpor/ivapor/
ipopor`. Any client-sent totals MUST be ignored or rejected on mismatch.

#### Scenario: Line formula exactness

- GIVEN a line with `valuni = 10000.50`, `dctpes = 500.25`, `ivapes = 950.05`, `ipopes = 0`,
  `candet = 3`
- WHEN the invoice is saved
- THEN the stored `totdet` equals `Decimal("31350.90")` (10000.50 − 500.25 + 950.05 + 0) × 3

#### Scenario: Client/authority totals mismatch rejected

- GIVEN an invoice whose client-computed header total differs from the server computation
- WHEN the save arrives
- THEN the response is `422` naming the mismatch field, and no rows are written

### Requirement: Pre-save validation parity (desktop Validar)

The save MUST validate parity rules from the POS form: existing and active client, credit
block (`cupblo`), seller validity, non-negative total, and non-empty lines.

#### Scenario: Credit-blocked client rejected

- GIVEN a third party with `cupblo` set
- WHEN an invoice is attempted for it
- THEN the response is `422` identifying the credit block

#### Scenario: Empty or negative invoice rejected

- GIVEN an invoice with zero lines or a negative computed total
- WHEN the save arrives
- THEN the response is `422` and nothing is reserved

### Requirement: Stock decrement on sale (Edi_CueInvProd parity)

Posting a sale MUST decrement `exiprod` by each line's quantity (negative movement, sale
quantity converted by `facumed` when a non-base unit is used). The web writer MUST NOT block
on negative resulting stock (legacy parity: stock is a cached balance recomputed from
`detcuentas`), but the save response SHOULD surface a per-line stockout warning.

#### Scenario: Stock decremented per line

- GIVEN a product with `exiprod = 10` and an invoice line of `candet = 3`
- WHEN the invoice posts
- THEN `exiprod` reads `7` after commit

#### Scenario: Backordered sale permitted with warning

- GIVEN a line for quantity 5 of a product with `exiprod = 2`
- WHEN the invoice posts
- THEN it succeeds, `exiprod` becomes `-3`, and the response flags the line as negative-stock

### Requirement: Payment capture (detapago, efectivo/transferencia minimal)

For the minimal POS slice, payments MUST be captured as `detapago` rows per payment form
(`codpag`, `afepag`, `tippag`), each carrying `soldeb`/`solcre` per the tipclas duality, with
`estado 'B'`, and the total cash (`valefe`) applying to the cash forms. The sum of payment
rows MUST equal `totfven` exactly (no partial payment in the minimal slice).

#### Scenario: Cash invoice payment row

- GIVEN a cash (efectivo) invoice of total 77 500
- WHEN it posts
- THEN one `detapago` row exists with `valpag = 77500.0`, `estado = 'B'`, and `soldeb = 77500.0`

#### Scenario: Mixed payments balance to the total

- GIVEN an invoice paid partly efectivo and partly transferencia (with reference)
- WHEN it posts
- THEN `Σ valpag = totfven` exactly, the transferencia row stores its reference, and mismatched sums are rejected `422`

### Requirement: Accounting causación to detcuentas (Grab_NueCausa parity)

Each invoice MUST post accounting entries into `detcuentas`: per-line revenue account
(`linea1.codcue`) and IVA account from the tax catalog, debit to the inventory account with
the line cost, and per-payment-form accounts (`formapago.codcue`). The document's entries
MUST balance: `Σ valdeb = Σ valcre`. An unbalanced causación MUST abort the save.

#### Scenario: Balanced causación for a cash sale

- GIVEN an invoice with IVA lines selling from a single product line
- WHEN it posts
- THEN `detcuentas` holds line revenue entries, IVA, cost-of-sale/inventory, and the caja entry, and their debits equal their credits

#### Scenario: Unbalanced accounting aborts the save

- GIVEN an injected bad account mapping making debits ≠ credits
- WHEN the save executes
- THEN the whole unit-of-work fails, `journal` is `FAILED`, and no legacy rows persist

### Requirement: Receipt / POS print output

The system MUST produce a browser-renderable receipt payload (ticket / P80 layout) containing
the resolution header, lines with quantities and amounts, totals and payment lines, and a DIAN
QR placeholder element in the footer. Rendering MUST NOT be inside the save unit-of-work.

#### Scenario: Receipt payload for a posted invoice

- GIVEN a posted invoice
- WHEN the receipt endpoint for its number is called
- THEN the payload contains header, resolution, line, total, payment, and an explicit QR placeholder element

#### Scenario: Accented content renders correctly

- GIVEN a line whose product name contains accents
- WHEN the receipt payload is rendered
- THEN the name appears without mojibake
