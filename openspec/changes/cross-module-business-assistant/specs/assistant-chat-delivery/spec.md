# Assistant Chat Delivery Specification

## Purpose

Expose one response contract consistently in persisted history, the drawer, and the full-page chat.

## Requirements

### Requirement: API and history parity

The chat request SHALL accept `message` (1–500 characters), optional `conversation_id`, and optional `request_id` (maximum 80 characters). POST `/api/llm/qa/chat` and persisted assistant messages SHALL expose the same envelope fields and metadata, including sources, freshness, entity references, and attachments.

#### Scenario: Drawer and full-page parity

- GIVEN the same authorized tenant and answer
- WHEN the reply is rendered in the drawer and `/chat`
- THEN both views show the same text, per-source evidence, freshness labels, entity links, attachment state, and status

### Requirement: Safe rendering states

The frontend SHALL render loading, complete, partial, empty, clarification, unavailable, and expired-attachment states distinctly; it MUST render server-provided links as links/cards, never raw model URLs or markdown download links.

#### Scenario: Partial and empty results

- GIVEN the response status is `partial` or `empty`
- WHEN either chat surface renders it
- THEN it shows the status explanation, preserves available citations/timestamps, and does not display missing values as zero

#### Scenario: Expired report

- GIVEN an attachment has passed `expires_at`
- WHEN its history message is opened
- THEN the UI disables download, marks it expired, and tells the user to request it again

### Requirement: Tenant-safe client state

When the active tenant or authenticated user changes, the frontend SHALL discard in-flight and displayed assistant state before accepting new results; cached conversations and messages MUST be keyed by tenant and user.

#### Scenario: Tenant switch during request

- GIVEN a chat request is pending for tenant A
- WHEN the user switches to tenant B
- THEN the tenant-A response is not rendered in tenant B and the UI starts with tenant-B history

## Non-functional requirements

- Responsiveness: the UI MUST show a loading state immediately; backend execution MUST remain bounded by the contract's five-tool-iteration and 30-second provider limits.
- Accessibility: both surfaces MUST expose status and error text to assistive technology and keep input, cancel, navigation, links, and downloads keyboard usable.
- Consistency: persisted metadata MUST be sufficient to reproduce the rendered evidence, freshness, link, and attachment state without trusting message markdown.

## Acceptance gates

Gate: contract tests cover request validation and history round-trip; drawer and full-page component tests cover every status; Playwright verifies tenant switching, authorized links, and expired reports before rollout.
