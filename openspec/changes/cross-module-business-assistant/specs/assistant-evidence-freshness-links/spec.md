# Assistant Evidence, Freshness, and Links Specification

## Purpose

Make every answer attributable, time-bounded, and safe to navigate from the assistant.

## Requirements

### Requirement: Exact response envelope

Every successful chat response SHALL contain exactly these contract fields: `status` (`complete|partial|empty|needs_clarification|unavailable`), `tenant_id`, `text`, `conversation_id`, `turn_count`, `tools_used`, `sources`, `freshness`, `entity_refs`, and `attachments`. `sources` and `freshness` MUST be arrays, and absent values MUST be represented by empty arrays rather than omitted fields.

Each source SHALL contain `source_id`, `domain`, `kind` (`duckdb|supabase|document`), `citation`, `cutoff_at`, `observed_at`, and `status` (`used|failed`); each freshness item SHALL contain `domain`, `cutoff_at`, `observed_at`, and `status` (`current|stale|unknown`).

Each attachment SHALL contain `type: report`, `format` (`excel|pdf|word`), `filename`, `download_url`, `state` (`available|expired`), `expires_at`, `date_from`, `date_to`, and `period_label`; date fields MAY be null, but `download_url` MUST be server-issued.

#### Scenario: Cross-domain evidence

- GIVEN a question combines sales, expenses, and expiry
- WHEN the answer is produced
- THEN it contains a distinct source and freshness item for each queried domain, with no single global date replacing them

### Requirement: Freshness semantics

For snapshot data, `cutoff_at` SHALL mean the latest business event included; for live data, it SHALL mean the provider query cutoff; `observed_at` SHALL mean when the source was observed. When a user asks for “today” or “current”, the assistant MUST state the available cutoff and MUST NOT claim real-time data when the status is stale or unknown.

#### Scenario: Mixed source dates

- GIVEN DuckDB and Supabase sources have different cutoffs
- WHEN the user asks for current figures
- THEN the answer reports both cutoffs and labels any stale or unknown source

### Requirement: Typed, authorized entity references

Each `entity_ref` SHALL contain `entity_type`, `entity_id`, `label`, `domain`, and a server-resolved `href`; `href` MUST come from an allowlisted route map after rechecking tenant and feature authorization. Model text, raw URLs, cross-tenant identifiers, and unauthorized destinations MUST NOT become links.

#### Scenario: Specific entity lookup

- GIVEN the user asks for a known product or alert
- WHEN the entity is returned
- THEN the response includes one authorized typed reference, or no reference if destination authorization fails

#### Scenario: Cross-tenant reference attempt

- GIVEN an identifier belongs to another tenant
- WHEN it is requested or supplied in prompt text
- THEN no entity data or link is returned and the request is treated as not found/forbidden without revealing ownership

### Requirement: Stable error contract

For rejected requests, the API SHALL return `application/problem+json` with `type`, `title`, `status`, `detail`, and `request_id`; it SHALL use `401` for missing authentication, `403` for disabled policy, `404` for inaccessible conversations/entities, `422` for invalid input, `502` for provider rejection, and `503` for transient dependency failure.

#### Scenario: Provider failure

- GIVEN the language or data provider rejects or temporarily fails
- WHEN the request cannot produce a complete answer
- THEN the API returns the corresponding `502` or `503`, a safe actionable detail, and no invented answer or attachment

## Acceptance gates

Gate: every source has citation and timestamps; every emitted `href` passes allowlist and tenant tests; unauthorized or model-generated links are rejected; RAG content remains data, not instructions.
