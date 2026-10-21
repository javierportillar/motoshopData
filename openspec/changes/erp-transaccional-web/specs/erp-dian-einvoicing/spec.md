# erp-dian-einvoicing Specification (delta — new capability)

## Purpose

DIAN electronic invoicing foundation, provider-agnostic: an adapter interface with a stub
implementation until a provider account exists (Dataico/SoftProp onboarding is a schedule
risk, not a slice blocker), `respdocfele` persistence for CUFE/QR/status, `estfele` gating
integrated with the annulment `Valid_EdiDocele` block, an asynchronous send queue with
retries and idempotency, a full request/response audit in `app_dian_payloads`, and receipt
QR/CUFE rendering (official DIAN searchqr fallback). Desktop `contadores.envfele` behaviors
remain desktop-owned; the web only sends documents it posted.

## ADDED Requirements

### Requirement: Provider-agnostic adapter interface with stub

The system MUST define a single provider adapter interface (build payload → send → normalized
accepted/rejected response) so Dataico, SoftProp, or any other provider can be swapped behind
it. Until a provider account exists, a stub adapter MUST be the default: it returns a
simulated ACCEPT with a deterministic pseudo-CUFE and records everything as if sent, clearly
marked as non-fiscal.

#### Scenario: Stub adapter behaves as the contract

- GIVEN no provider credentials configured
- WHEN an invoice is queued for electronic send
- THEN the stub adapter produces a normalized ACCEPT response and the contract test set (same for any future adapter) passes unchanged

#### Scenario: Adapter swap requires no caller changes

- GIVEN any adapter implementation passing the contract test suite
- WHEN it is configured as active provider
- THEN queue, persistence, and gating behaviors run identically

### Requirement: respdocfele persistence and payload audit

After each send attempt the system MUST persist the provider response in `respdocfele`
(`numnum`, `codclas`, `cocufe`, `cuuid`, `qrcode`, `respcod`, `estfele`, `resptxt`,
`codpro`) and the full raw request/response in `app_dian_payloads` (InnoDB audit). Repeated
sends of the same document MUST NOT duplicate `respdocfele` rows.

#### Scenario: Accepted response persisted once

- GIVEN an invoice sent and accepted
- WHEN the response arrives
- THEN exactly one `respdocfele` row for the document carries the CUFE, QR string, and `estfele`, and the raw payload/request+response exist in `app_dian_payloads`

#### Scenario: Retried send stays idempotent

- GIVEN a transient network failure after the provider accepted the first attempt
- WHEN the queue retries the same document
- THEN no second `respdocfele` row and no second accepted send occur

### Requirement: Async send queue with retries and backoff

Sends MUST run asynchronously (not inside the invoice save unit-of-work) through a persistent
queue with retry/backoff, a maximum attempt count, and a durable FAILED state — repairing the
legacy "client without retries" gap.

#### Scenario: Transient failure retried with backoff

- GIVEN the provider responds with a transient error
- WHEN the queue worker processes the item
- THEN it retries with growing delay up to the max attempts, then marks the send `FAILED` with the last error, without touching the invoice's saved data

#### Scenario: Crash recovery does not lose or duplicate

- GIVEN a worker crash between send and response persistence
- WHEN the queue restarts
- THEN the item is re-driven to a safe terminal state (accepted persisted or sent once more without double issue per CUFE)

### Requirement: estfele gating integrated with annulment

The `estfele` state persisted in `respdocfele` MUST be the single numeric truth for the
edit-block: values `1`/`2` (accepted) MUST make edit and annulment of the document impossible
(`Valid_EdiDocele` parity — enforced again server-side in the annulment chain), while
stub/pending/failed states MUST allow normal annulment.

#### Scenario: Accepted electronic invoice blocks annulment

- GIVEN an invoice with `estfele = 1`
- WHEN annulment is requested
- THEN it is rejected by the electronica guard (annulment capability scenario)

#### Scenario: Stub-state invoice remains annulable

- GIVEN an invoice in stub/pending electronic state (`estfele` not accepted)
- WHEN annulment is requested with valid role and reason
- THEN it succeeds and the DIAN queue marks the canceled item `CANCELLED` without sending

### Requirement: QR/CUFE rendering on receipts

Receipt rendering MUST include the QR/CUFE element: the official DIAN searchqr URL built from
the document's CUFE
(`https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=<CUFE>`) once accepted, and
a clearly-labeled placeholder before acceptance.

#### Scenario: Receipt shows QR after acceptance

- GIVEN an accepted electronic invoice (CUFE present)
- WHEN the receipt is rendered
- THEN the footer carries the DIAN searchqr URL with the CUFE

#### Scenario: Placeholder before acceptance

- GIVEN an invoice posted but not yet accepted
- WHEN the receipt is rendered
- THEN the QR element is a placeholder (no fake CUFE displayed)

### Requirement: Coexistence — desktop electronic documents untouched

The web DIAN pipeline MUST only send documents posted by the web (scoped by journal/actor
origin), MUST NOT interfere with desktop `contadores.envfele`-flagged sequences or desktop
re-sends, and MUST reconcile doc numbers against the shared counter set.

#### Scenario: Web queue ignores desktop-originated documents

- GIVEN an invoice posted by desktop Hermes with `envfele = 'S'`
- WHEN the web send queue scans for sendable documents
- THEN the desktop-originated document is not sent or modified by the web queue
