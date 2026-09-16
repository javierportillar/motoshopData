# Multi-Tenant M1 Backend Specification

## Purpose

Extend the existing tenant boundary so every assistant source, capability, conversation, report, and destination is authorized independently.

## Requirements

### Requirement: Fail-closed tenant authorization

For every assistant request, the backend SHALL derive tenant and user identity from authenticated context, verify the tenant feature policy before capability selection, and apply tenant filtering at every source and destination. Missing, invalid, or disabled policy MUST fail closed without returning data.

#### Scenario: Authorized tenant query

- GIVEN an authenticated user with an enabled assistant and domain policy
- WHEN the user asks a supported question
- THEN every selected source is scoped to that tenant and the response identifies the same `tenant_id`

#### Scenario: Cross-tenant conversation access

- GIVEN a conversation owned by another tenant or user
- WHEN it is requested by the current user
- THEN the backend returns `404` with a generic problem response and reveals no content or ownership

### Requirement: Sensitive data minimization

The assistant SHALL expose only fields permitted by tenant and role policy, aggregate sensitive operational data by default, and MUST NOT return credentials, tokens, passwords, secrets, or unredacted sensitive values in answers, citations, logs, reports, or error details.

#### Scenario: Restricted expense field

- GIVEN an expense source contains a field not allowed for the user
- WHEN the user asks for it directly or through a cross-domain question
- THEN the field is omitted or the request is refused, with no leakage through evidence or errors

### Requirement: Reports and destinations recheck authorization

When a report or entity reference is requested, the backend SHALL recheck tenant, user, domain, and destination policy at generation/download/resolve time; report URLs MUST be tenant-scoped and expire after 24 hours.

#### Scenario: Disabled destination

- GIVEN the answer identifies an entity whose module is disabled for the tenant
- WHEN the reference is resolved
- THEN `entity_refs` is empty for that entity and no navigable URL is emitted

## Deferred and acceptance gates

Deferred: making `purchase_plans` assistant-readable until its repository is tenant-scoped and authoritative. Gates: 100% supported-tool cross-tenant tests, sensitive-field redaction tests, tenant-scoped report download tests, and fail-closed policy tests must pass before canary enablement.
