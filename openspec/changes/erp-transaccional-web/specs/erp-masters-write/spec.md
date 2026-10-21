# erp-masters-write Specification (delta — new capability)

## Purpose

Create/edit for master data through the web API with parity to the legacy catalog save
(`BotGuarMa.cs`, code_analysis §10): third parties (`terceros` + `tercecorreo`) and products
(`productos` + `prodcodbars`, `produndmeds`, `preciosxpro` / `listapre`). Facts written into
these tables are immediately shared with desktop sgHermes (same tables); stock and cost
fields are transaction-owned and MUST NOT be editable through masters.

## ADDED Requirements

### Requirement: Third-party create and edit

The system MUST allow creating and editing third parties with their emails
(`tercecorreo`), enforcing legacy-required fields (identification `nitter` + verification
digit type, name, address/phone_required subset per legacy `BotGuarMa`), and MUST reject
duplicate identification with a clear client error.

#### Scenario: Create third party happy path

- GIVEN a `gerente` JWT and a new valid third party with one email
- WHEN the create request is saved
- THEN one `terceros` row and its `tercecorreo` rows exist, and the response returns the created record

#### Scenario: Duplicate identification rejected

- GIVEN `terceros` already contains `nitter = 900123456-7`
- WHEN a create arrives with the same `nitter`
- THEN the response is `409` identifying the field, and no rows are written

#### Scenario: Invalid identification rejected with legacy parity

- GIVEN a payload whose verification-digit checksums do not match the documented rules
- WHEN the create arrives
- THEN the response is `422` listing the offending field and the existing record set is unchanged

### Requirement: Product create and edit with units, barcodes and per-list prices

The system MUST allow creating/editing products (`productos`) with multiple barcodes
(`prodcodbars`), selling units with conversion factors (`produndmeds`: `divmul`, `facumed`,
`pventa`, `tipovc`), and per-price-list entries (`preciosxpro` over `listapre` with
`pvsini`/`pvconi`, `pvtipo` IVA-inclusive vs breakdown mode).

#### Scenario: Product with unit and price list saved together

- GIVEN a new product with a fractional unit (`caja × 12`) and a price on the default list
- WHEN the save executes in one unit-of-work
- THEN `productos`, `produndmeds`, and `preciosxpro` rows all exist or none do (journal-backed save)

#### Scenario: Uniqueness enforced on product and barcode

- GIVEN an existing product with `codbar = "7701234012345"` in `prodcodbars`
- WHEN a create/edit reuses that barcode for another product
- THEN the response is `409` on `codbar` and no partial rows persist

#### Scenario: Price with IVA consistency

- GIVEN an IVA-inclusive list price `pvtipo` marking and tax rate 19%
- WHEN the price is saved
- THEN `pvconi` and `pvsini` are stored consistent with each other (inclusive = exclusive × (1 + rate)), computed server-side with `Decimal`

### Requirement: Legacy validation parity for masters

Master writes MUST reproduce the notable legacy validity rules: required code/name/line
fields, inactive products (`actprod = 'I'`) and inactive/blocked third parties (`inater`,
`cupblo`) rejected on new transactional documents, and protection of transaction-owned
fields — `exiprod` (stock) and cost fields must not be settable via masters.

#### Scenario: Required fields enforced

- GIVEN a product create missing `codlin1` (product line)
- WHEN the save arrives
- THEN the response is `422` naming all offending fields (aggregate, not first-fail)

#### Scenario: Stock is not master-writable

- GIVEN a product edit attempt that changes `exiprod`
- WHEN the edit arrives
- THEN the response is `422` stating stock only moves through transactions (`detcuentas`-backed), and `exiprod` is unchanged

#### Scenario: Inactive master rejected downstream (cross-slice contract)

- GIVEN an inactive product (`actprod = 'I'`)
- WHEN a new invoice line references it
- THEN the invoice save is rejected `422` referencing the master state

### Requirement: Audit trail on master changes

Every master create/edit MUST append an audit record (`app_audit_log`) with actor, action,
target row key, and before/after snapshot. Legacy `motanudoc` MUST NOT be used for masters
(its contract reserved to document annulment/modification).

#### Scenario: Edit recorded with snapshots

- GIVEN an existing product priced at 10 000
- WHEN its list price is changed to 12 000
- THEN one audit row exists capturing before and after values and the acting user

### Requirement: Masters role gating

Reading masters MUST be allowed for all authenticated roles of the enabled tenant; create and
edit MUST be restricted per the access matrix (default: `admin`/`gerente` only, `vendedor`
read-only).

#### Scenario: Vendedor read-only

- GIVEN a `vendedor` JWT
- WHEN `GET` any master endpoint
- THEN data returns normally
- WHEN `POST`/`PATCH` a master
- THEN the response is `403` and nothing changes

### Requirement: Coexistence with desktop for masters

Because masters live in the legacy tables, web edits MUST take effect without any schema or
engine lock beyond single-statement duration, and MUST be immediately visible to desktop
sgHermes semantics (last write wins, same as today's desktop behavior).

#### Scenario: Desktop sees web rename immediately

- GIVEN a product renamed via the web
- WHEN the desktop product lookup selects that row afterward
- THEN the new name is visible and no stale cache remains on the write path
