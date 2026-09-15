# Tasks: Cross-module business assistant

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 900–1,300 across two repositories, including tests and migration |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 backend governance/contracts → PR 2 backend chat/persistence → PR 3 frontend parity → PR 4 cross-repo E2E |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No — resolved by the current session decision.
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Boundary | Commit/rollback |
|---|---|---|
| 1 | `motoshopData`: contracts, registry, adapters, policy | `feat(assistant): add governed sources`; revert without touching data |
| 2 | `motoshopData`: API orchestration, persistence, reports, migration | `feat(assistant): deliver evidence envelope`; disable flag/revert migration consumer |
| 3 | `frontfambus`: typed client and both surfaces | `feat(chat): render governed assistant`; revert frontend only |
| 4 | Both repos: integration/E2E and canary gates | `test(chat): verify tenant-safe delivery`; revert tests/wiring only |

Preserve existing backend modifications in `llm/tools.py`, `tenants.yaml`, API tests, and `openspec/config.yaml`; never stage or edit `outputs/` or `tmp/`.

## Phase 1: Backend governance foundation (RED → GREEN → REFACTOR)

- [x] 1.1 RED: Add `motoshop-app/api/tests/test_assistant_contracts.py` and `motoshop-app/api/tests/test_assistant_registry.py` for exact envelope, typed inputs/refs, allowlists, no `purchase_plans`, RFC 7807, redaction, and fail-closed tenant policy (governed-business-assistant, evidence-freshness-links, multi-tenant-m1-backend).
- [x] 1.2 GREEN: Create `llm/contracts.py`, `registry.py`, `catalog.py`, `sources.py`; modify `auth/tenant_dep.py`, `auth/module_access.py`, and `tenants.yaml` for tenant-injected, bounded, parameterized DuckDB/Supabase capabilities and server-resolved links.
- [x] 1.3 REFACTOR: Keep adapters provider-isolated and logs free of prompts/secrets/raw rows; run the focused contract/security tests.

## Phase 2: Backend delivery and persistence (RED → GREEN → REFACTOR)

- [x] 2.1 RED: Extend `tests/test_agent_chat_multitenant.py` and `tests/test_reports.py` for partial/empty/clarification states, duplicate `request_id`, 502/503 mapping, explicit-only files, expiry, history ownership, and per-source timestamps.
- [x] 2.2 GREEN: Modify `llm/qa_chat.py`, `llm/router.py`, `llm/tools.py`, `llm/conversations/repository.py`, `reports/router.py`, `reports/storage.py`, and `infra/supabase/migrations/20260914_001_agent_chat.sql` to normalize, persist, and re-authorize the envelope atomically.
- [x] 2.3 REFACTOR: Verify 500-character, 20-turn, five-iteration, timeout, and idempotency bounds without changing unrelated working-tree behavior.

## Phase 3: Frontend contract parity (RED → GREEN → REFACTOR)

- [ ] 3.1 RED: Add `lib/api/chat.test.ts`, `components/chat/ChatDrawer.test.tsx`, and `app/(authenticated)/chat/page.test.tsx` for every status, empty arrays, server links only, expired attachments, accessibility, and tenant/user cache isolation (assistant-chat-delivery).
- [ ] 3.2 GREEN: Modify `lib/api/chat.ts`, `lib/api/hooks.ts`, `components/chat/ChatDrawer.tsx`, `app/(authenticated)/chat/page.tsx`, `lib/auth/access.ts`, and `app/(authenticated)/layout.tsx` to share the typed envelope and identical evidence/freshness/link/report rendering.
- [ ] 3.3 REFACTOR: Remove markdown/raw URL fallbacks, cancel stale requests on tenant changes, and run `npm run test:unit`, `npm run typecheck`, and `npm run lint`.

## Phase 4: Cross-repository verification and rollout gate

- [ ] 4.1 RED: Add `frontfambus/tests/assistant-chat.spec.ts` and `motoshop-app/api/tests/test_assistant_integration.py` for drawer/full-page parity, tenant switching, authorized links, partial results, expired reports, and cross-tenant source/report isolation.
- [ ] 4.2 GREEN: Complete fixtures and wiring, then run targeted tests before `uv run pytest`, API pytest, `npx playwright test`, and `npm run build`.
- [ ] 4.3 REFACTOR/GO-NO-GO: confirm 100% supported-tool cross-tenant coverage, disabled `chat-ia` rollback, migration/RLS review, and canary-only enablement; do not enable purchase-plan tools.
