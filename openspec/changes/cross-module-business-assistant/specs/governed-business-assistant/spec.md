# Governed Business Assistant Specification

## Purpose

Provide tenant-scoped, read-only business answers grounded in approved sources, with explicit uncertainty and controlled file generation.

## Requirements

### Requirement: Governed domain coverage

When an authorized user asks a supported business question, the assistant SHALL use only allowlisted, typed read-only capabilities for `sales`, `purchases`, `inventory`, `abc`, `dormant_products`, `alerts`, `forecasts`, `analyses`, `expenses`, and MasVital-only `expiry`; it MUST NOT execute arbitrary SQL, select model-chosen tables, or mutate data.

#### Scenario: All supported domains are available

- GIVEN a tenant has the corresponding feature flags and authoritative fixtures
- WHEN the user asks one question in each supported domain
- THEN each answer uses the matching domain capability and identifies its evidence and freshness

#### Scenario: Unsupported purchase plans are refused

- GIVEN the user asks about saved `purchase_plans`
- WHEN the capability is not tenant-safe and authoritative
- THEN the assistant states that it is unavailable and returns no plan data

### Requirement: Grounded answer intent

When a question is answerable, the assistant SHALL return a concise answer backed by returned evidence; when the request is ambiguous, it MUST ask a clarifying question without querying an unselected domain.

#### Scenario: Ambiguous report wording

- GIVEN the user says “give me a stock report” without requesting a file format
- WHEN the assistant classifies the intent
- THEN it returns the available data in chat with `status: needs_clarification`, asks for a format, and creates no attachment

### Requirement: Explicit reports only

When the user explicitly requests Excel, PDF, Word, export, download, or a file, the assistant SHALL create only a tenant-authorized report with a 24-hour expiry; otherwise `attachments` MUST be empty.

#### Scenario: Explicit file request

- GIVEN the requested domain and format are enabled for the tenant
- WHEN the user explicitly requests a downloadable file
- THEN the response includes a typed attachment with period and expiry metadata

### Requirement: Truthful failures and empty results

When one source fails, the assistant SHALL label that source and never infer missing figures; a partial answer SHALL be `200` with `status: partial`, while total transient data failure SHALL be `503` and provider rejection SHALL be `502` using RFC 7807 errors.

#### Scenario: Empty authorized query

- GIVEN all queried sources succeed but contain no matching records
- WHEN the user asks for the result
- THEN the response is `200`, `status: empty`, contains no fabricated values, and explains the scope searched

#### Scenario: One data source fails

- GIVEN a cross-domain question has one available source and one unavailable source
- WHEN the answer is assembled
- THEN the response is `200`, `status: partial`, marks the failed source, and excludes unsupported figures

## Non-functional requirements

- Security: all inputs MUST be validated; no arbitrary SQL, secrets, credentials, or raw sensitive values may reach prompts, logs, answers, or files.
- Bounded execution: a request MUST enforce the 500-character message, 20-turn conversation, five-tool-iteration, and 30-second provider timeout limits.
- Reliability: duplicate `request_id` submissions MUST return the persisted result without a second report or chargeable provider call.
- Rollout: the capability MUST be feature-flagged per tenant and disableable without modifying source data.

## Deferred capabilities and acceptance gates

Deferred: assistant mutations/CRUD, arbitrary catalog or SQL access, instruction execution from RAG text, saved `purchase_plans`, and unrelated legacy-route repair. Acceptance requires domain fixtures, cross-tenant negative tests, explicit-report tests, failure/empty tests, and contract-parity tests before tenant canary rollout.
