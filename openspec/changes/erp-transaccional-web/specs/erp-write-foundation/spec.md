# erp-write-foundation Specification (delta — new capability)

## Purpose

Hardened write path for the transactional web ERP operating on the legacy MySQL 5.0.45
(MyISAM) database shared with desktop sgHermes: JWT auth + role mapping onto the legacy
permission matrix, per-module route access matrix, real InnoDB unit-of-work, the
`app_doc_journal` write-ahead intent table, per-table grants for `app_writer`, a migration
runner for `infra/migrations/`, idempotency for document saves, and latin1/Decimal boundary
handling. Desktop sgHermes MUST remain unaffected outside the contadores lock window.

## ADDED Requirements

### Requirement: ERP write endpoints are JWT-authenticated and role-gated

Every transactional ERP write endpoint MUST require a valid JWT and MUST map roles
(`admin`, `gerente`, `vendedor`) onto the legacy permission model (`permisosusu` /
`permisosfac`) server-side. Authorization MUST be decided by the server; the frontend only
hides controls.

#### Scenario: Unauthenticated write request

- GIVEN no valid JWT
- WHEN any ERP write endpoint is called
- THEN the response is `401` and no row in legacy or `app_*` tables changes

#### Scenario: Role boundary reflects legacy permission parity

- GIVEN a `vendedor` JWT (invoice creation permitted, document annulment not)
- WHEN vendedor calls the annulment endpoint
- THEN the response is `403` and no write occurs

#### Scenario: Gerente may run collections

- GIVEN a `gerente` JWT with the collections module enabled
- WHEN gerente creates a cash receipt
- THEN the write succeeds and the audit log records actor, role, and operation

### Requirement: Server-side route/module access matrix

Each new ERP module (slice) MUST be registered in the central route/method access matrix
(`module_access`) and deployment gating MUST be possible per module without code deploy
(matrix flag off → endpoints refuse). Access MUST be enforced server-side per route and
method.

#### Scenario: Module disabled gate

- GIVEN the collections module is disabled in the access matrix
- WHEN any client calls a collections write endpoint with a valid role
- THEN the response is `403` with an explicit module-disabled reason and no data is touched

#### Scenario: Matrix denies an HTTP method

- GIVEN the matrix allows `GET` but not `POST` on a masters route for `vendedor`
- WHEN vendedor sends `POST`
- THEN the response is `403` before any business validation runs

### Requirement: Tenant enablement for transactional modules

Transactional ERP modules MUST be enabled per tenant via configuration. The `motoshop`
tenant is the first target; `masvital` MUST default to disabled until its tenant→empresa
mapping is decided in design. Cross-tenant data leak MUST be impossible in the write path.

#### Scenario: Masvital stays read-only by default

- GIVEN a valid `masvital` tenant JWT
- WHEN an ERP write endpoint is called
- THEN the response is `403` explicitly stating the tenant is not enabled for transactional writes

#### Scenario: Tenant isolation on writes

- GIVEN two tenants with distinct configurations
- WHEN a write is executed for tenant `motoshop`
- THEN only `motoshop`'s target database/empresa rows change and no other tenant's data is reachable

### Requirement: InnoDB unit-of-work atomic document save

Multi-table document saves MUST run inside a real `BEGIN`/`COMMIT` unit-of-work on a
transactional (non-autocommit) writer engine. Because legacy doc tables are MyISAM and cannot
roll back, the save MUST use the write-ahead journal plus compensating cleanup so the final
state is all-or-nothing: either every legacy row of the document exists, or none does.

#### Scenario: Successful invoice save is a single unit

- GIVEN a valid invoice payload and an idle system
- WHEN the save executes
- THEN the journal row is `COMMITTED` and legacy rows exist in the document, detail, payment, and accounting tables

#### Scenario: Failure mid-save leaves no partial document

- GIVEN an injected failure between the detail insert and the payment insert
- WHEN the save aborts
- THEN `SELECT` on all legacy doc tables for that document number returns zero rows, the journal row is `FAILED` with the error, and the response is `503`/`500` with a retryable contract

### Requirement: app_doc_journal write-ahead intent table

An InnoDB table `app_doc_journal` MUST record write-ahead intent per document: doc type
(`codclas`), prefix, reserved number, status (`PENDING`/`COMMITTED`/`FAILED`/`ANNULLED`),
actor, tenant, and timestamps. It MUST be created by an F8-series migration and MUST be the
first write, before document numbering or any legacy insert.

#### Scenario: Journal leads the save

- GIVEN a document save request
- WHEN numbering and legacy inserts run
- THEN a `PENDING` journal row exists before the first legacy insert and flips to `COMMITTED` with the final number after success

#### Scenario: Orphan PENDING rows are healed

- GIVEN a `PENDING` journal row older than the watchdog threshold with no legacy document rows
- WHEN the journal consistency job runs
- THEN the row is marked `FAILED` and the reserved number is released for reuse (lagged-counter heal)
- AND the nightly consistency check (doc totals vs `detcuentas`, `exiprod` audit) reports zero mismatches for healed docs

### Requirement: Migration runner and least-privilege grants

A migration runner MUST apply numbered SQL migrations from `infra/migrations/` (F8 pattern)
in order, idempotently. New grants MUST follow the F5-003 per-table pattern and the
`app_writer` user MUST only receive privileges required by the ERP slices.

#### Scenario: Runner applies migrations once

- GIVEN a pending F8 migration set
- WHEN the runner executes twice
- THEN each SQL file is applied exactly once and the second run is a no-op with recorded state

#### Scenario: Duplicate validation before unique DDL

- GIVEN existing duplicate (prefix, number) pairs in a legacy doc table
- WHEN the unique-index migration runs
- THEN it aborts before DDL, reports the duplicate rows, and no index is created

### Requirement: Character set and Decimal boundary handling

Money and quantity values MUST be handled as `Decimal` from the API boundary onward — never
float arithmetic. Legacy latin1 text MUST round-trip without mojibake, and numeric values
stored in varchar columns MUST be converted/validated at the Pydantic layer (existing
String-typing pattern).

#### Scenario: Decimal round-trip is exact

- GIVEN a line priced at `19990.625`
- WHEN the invoice is saved and re-read through the API
- THEN the returned value and the stored `totdet`/header totals are exactly `Decimal("19990.625")`-derived, with no float drift

#### Scenario: Accented text survives latin1

- GIVEN a product named with Spanish accents (`"Bujía NGK Ñ-P"`)
- WHEN the record is created and re-read (including via desktop-written latin1 rows)
- THEN the API returns the same string without mojibake

### Requirement: Idempotency convention for document saves

Document-saving write endpoints MUST accept an `Idempotency-Key` (UUIDv4) and MUST replay the
same stored response for repeated calls with the same key, without reserving an additional
document number or duplicating any rows.

#### Scenario: Replay does not double-charge

- GIVEN a successful invoice save under key `K`
- WHEN the same request is retried with key `K`
- THEN the response is identical, exactly one document exists, and `contadores` did not advance twice

#### Scenario: Different key means a new document

- GIVEN the same payload under a new key
- WHEN the save executes
- THEN a new document number is reserved and a second document exists

### Requirement: Coexistence with desktop sgHermes

The web writer MUST coordinate numbering exclusively through the shared `contadores` table
with a bounded `LOCK TABLES` scope, MUST never modify desktop-managed configuration tables,
and MUST keep `app_*` tables invisible to desktop and to analytics ETL gold aggregates (dump
include/exclude policy).

#### Scenario: Parallel desktop and web saves under load

- GIVEN desktop sgHermes and the web API both saving documents concurrently
- WHEN both number their documents
- THEN each obtains a distinct sequential number from `contadores`, no duplicate numbers reach the doc tables (enforced by unique index), and neither process deadlocks outside the bounded contadores lock window

#### Scenario: Web save coexists with a desktop lock

- GIVEN the desktop process holds `LOCK TABLES contadores WRITE` at the moment of a web save
- WHEN the web numbering step runs
- THEN the web save waits (bounded timeout), then completes with the next valid number

#### Scenario: ETL stays clean

- GIVEN the cloud dump pipeline runs after ERP tables exist
- WHEN bronze/gold is rebuilt
- THEN `app_*` tables are excluded from gold business aggregates while legacy doc tables (`facventas`, `detcuentas`, …) coherently include web postings with desktop data
