# Apply progress: cross-module-business-assistant

## Slice
- Boundary: backend governance foundation, Phase 1 tasks 1.1–1.3 only.
- Delivery: stacked-to-main work-unit slice; no frontend, persistence, reports, migration, or PR.
- Review boundary: 398 governance implementation/test additions; rollback is a single commit revert.

## Completed
- [x] 1.1 RED — contract and registry security tests were written first.
- [x] 1.2 GREEN — typed envelope, fixed query catalog, allowlisted registry, and read-only DuckDB/Supabase adapters added; tenant context derives policy from existing enabled feature flags.
- [x] 1.3 REFACTOR — provider errors are sanitized, credentials/raw rows are redacted, filters and entity IDs are bounded, and adapters do not log payloads.
- Deviation: no new `tenants.yaml` hunk was staged; its existing `chat-ia` and module flags are the policy source, preserving intentional working-tree changes.

## TDD Cycle Evidence
| Task | Test file | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|
| 1.1 | `tests/test_assistant_contracts.py`, `tests/test_assistant_registry.py` | N/A (new) | ✅ written; collection failed before implementation | ✅ 7 passed | ✅ negative contract/security cases | ✅ focused lint |
| 1.2 | same | ✅ 27 baseline tests | ✅ written first | ✅ 7 passed | ✅ tenant binding, route and filter rejection | ✅ focused lint |
| 1.3 | same | ✅ 7 focused tests | ✅ written first | ✅ 7 passed | ✅ failure/redaction branches | ✅ focused lint |

## Verification
- Focused: `uv run pytest tests/test_assistant_contracts.py tests/test_assistant_registry.py` — 7 passed.
- Regression: auth/tenant/module, tenant, and agent tests — 44 passed, 1 pre-existing failure: report download route is absent from `ROUTE_MODULES` and is not dependency-wired.
- Quality: Ruff passed on new files and auth additions with the repository's pre-existing E501 ignored for `module_access.py`.

## Commit and remaining work
- Commits: `271280f`, `a77f900`, `57e8640`; 399 additions across the slice, only slice files staged. Existing `llm/tools.py`, `tenants.yaml`, API tests, `openspec/config.yaml`, `outputs/`, and `tmp/` changes remain untouched.
- Rollback: `git revert 57e8640 a77f900 271280f`; do not reset or discard the separate working-tree changes.
- Remaining: Phase 2 backend delivery/persistence, Phase 3 frontend parity, Phase 4 cross-repository verification.

## Slice 2
- Boundary: Phase 2 backend contract delivery, persistence metadata, report expiry, and report-route policy only; frontend and later phases remain untouched.
- Delivery: stacked-to-main work-unit slice, with existing unrelated working-tree changes preserved.
- Completed: 2.1 RED and 2.2 GREEN. The response now normalizes the exact governed envelope, blocks implicit report generation, persists freshness/entity/reference/attachment metadata, maps provider failures to RFC 7807, rejects expired indexed reports, and documents the report download route's independent authorization policy.
- Deferred: 2.3 REFACTOR remains pending for explicit 500-character, 20-turn, five-iteration, timeout, and idempotency regression verification.
- Commit: `4508841 feat(assistant): deliver governed response envelope`; the committed slice is exactly 400 changed lines and excludes unrelated `tools.py`, `tenants.yaml`, `openspec/config.yaml`, API-test, `outputs/`, and `tmp/` changes.

## TDD Cycle Evidence (cumulative)
| Task | Test file | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|
| 1.1 | `tests/test_assistant_contracts.py`, `tests/test_assistant_registry.py` | N/A (new) | ✅ written; collection failed before implementation | ✅ 7 passed | ✅ negative contract/security cases | ✅ focused lint |
| 1.2 | same | ✅ 27 baseline tests | ✅ written first | ✅ 7 passed | ✅ tenant binding, route and filter rejection | ✅ focused lint |
| 1.3 | same | ✅ 7 focused tests | ✅ written first | ✅ 7 passed | ✅ failure/redaction branches | ✅ focused lint |
| 2.1 | `tests/test_agent_chat_multitenant.py`, `tests/test_reports.py` | ✅ 35 relevant tests | ✅ written first; 6 RED tests | ✅ 6 focused tests passed | ✅ empty, clarification, duplicate, reference, provider, expiry paths | ✅ normalized contract assertions |
| 2.2 | same | ✅ 35 relevant tests | ✅ tests preceded implementation | ✅ 35 assistant/auth tests and 10 report-policy tests passed | ✅ SQLite/in-memory persistence and route policy | ✅ provider details and expired files sanitized |

## Slice 2 Verification
- Focused contract/regression: `uv run pytest tests/test_agent_chat_multitenant.py tests/test_assistant_contracts.py tests/test_assistant_registry.py tests/test_auth_modules.py` — 35 passed.
- Report policy/expiry: `uv run pytest tests/test_reports.py -k 'storage or download or not_serve'` — 10 passed.
- Relevant regression: 48 passed, 3 pre-existing data-fixture failures remain in the working-tree purchase assertions because the synchronized DuckDB now reports `2026-09-13` while those unrelated tests expect `2026-06-26`.
- Rollback: `git revert 4508841`; preserve the separate working-tree modifications and OpenSpec artifacts.

## Slice 3
- Boundary: Phase 2.3 verification/refactor only: request bounds, conversation/tool limits, provider failures, duplicate request reuse, and refreshed-data test stability. Frontend and later phases remain untouched.
- Delivery: feature-branch-chain work-unit slice on `feature/cross-module-business-assistant`; unrelated working-tree changes remain unstaged.
- Completed: 2.3 RED/GREEN/REFACTOR. Added focused boundary and failure tests, made request-id reuse work when the duplicate omits `conversation_id`, and removed volatile production dates from refreshed purchase assertions.
- Deviation: no frontend work, purchase-plan capability, or unrelated legacy-route repair was started.

## TDD Cycle Evidence (cumulative)
| Task | Test file | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|
| 1.1 | `tests/test_assistant_contracts.py`, `tests/test_assistant_registry.py` | N/A (new) | ✅ written; collection failed before implementation | ✅ 7 passed | ✅ negative contract/security cases | ✅ focused lint |
| 1.2 | same | ✅ 27 baseline tests | ✅ written first | ✅ 7 passed | ✅ tenant binding, route and filter rejection | ✅ focused lint |
| 1.3 | same | ✅ 7 focused tests | ✅ written first | ✅ 7 passed | ✅ failure/redaction branches | ✅ focused lint |
| 2.1 | `tests/test_agent_chat_multitenant.py`, `tests/test_reports.py` | ✅ 35 relevant tests | ✅ written first; 6 RED tests | ✅ 6 focused tests passed | ✅ empty, clarification, duplicate, reference, provider, expiry paths | ✅ normalized contract assertions |
| 2.2 | same | ✅ 35 assistant/auth tests and 10 report-policy tests | ✅ tests preceded implementation | ✅ 35 assistant/auth tests and 10 report-policy tests passed | ✅ SQLite/in-memory persistence and route policy | ✅ provider details and expired files sanitized |
| 2.3 | `tests/test_assistant_phase23.py`, `tests/test_reports.py` | ✅ 47 relevant tests; 3 stale-date failures identified | ✅ 2 new behavior failures before implementation | ✅ 8 focused tests passed; refreshed-data tests 23 passed | ✅ 20th-turn allowance, SQLite idempotency, transient/permanent provider paths | ✅ repository lookup, bounded assertions, focused format/lint |

## Slice 3 Verification
- Focused: `uv run pytest tests/test_assistant_phase23.py` — 8 passed.
- Relevant regression: `uv run pytest tests/test_assistant_phase23.py tests/test_agent_chat_multitenant.py tests/test_assistant_contracts.py tests/test_assistant_registry.py tests/test_reports.py` — 55 passed.
- Refreshed data: purchase tests validate ISO dates and source-derived freshness instead of hardcoding production dates.
- Quality: focused Ruff checks pass for the new Phase 2.3 test and repository changes; legacy long system-prompt/test lines remain outside this refactor.
- Rollback: revert the Phase 2.3 work-unit commit; preserve the separate `tools.py`, `tenants.yaml`, API-test, `openspec/config.yaml`, `outputs/`, and `tmp/` changes.

## Slice 4
- Boundary: Phase 3 frontend contract parity only; backend production code, Phase 4 cross-repository verification, and unrelated visual refactors remain untouched.
- Delivery: feature-branch-chain work-unit slice on `frontfambus` branch `feature/cross-module-business-assistant`; review budget remains below 400 changed lines including tests.
- Completed: 3.1 RED, 3.2 GREEN, and 3.3 REFACTOR. The frontend now normalizes the governed envelope, renders status/evidence/freshness/entity references/reports identically in the drawer and `/chat`, rejects unsafe client links, handles expired attachments, and resets/cancels tenant/user-scoped state.
- Deviation: persisted-history endpoint metadata remains optional on the frontend because the backend `MessageResponse` currently exposes only legacy fields; no backend code was changed in this slice. Phase 4 must verify history metadata round-trip before rollout.

## TDD Cycle Evidence (cumulative)
| Task | Test file | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|
| 1.1 | `tests/test_assistant_contracts.py`, `tests/test_assistant_registry.py` | N/A (new) | ✅ written; collection failed before implementation | ✅ 7 passed | ✅ negative contract/security cases | ✅ focused lint |
| 1.2 | same | ✅ 27 baseline tests | ✅ written first | ✅ 7 passed | ✅ tenant binding, route and filter rejection | ✅ focused lint |
| 1.3 | same | ✅ 7 focused tests | ✅ written first | ✅ 7 passed | ✅ failure/redaction branches | ✅ focused lint |
| 2.1 | `tests/test_agent_chat_multitenant.py`, `tests/test_reports.py` | ✅ 35 relevant tests | ✅ written first; 6 RED tests | ✅ 6 focused tests passed | ✅ empty, clarification, duplicate, reference, provider, expiry paths | ✅ normalized contract assertions |
| 2.2 | same | ✅ 35 assistant/auth tests and 10 report-policy tests | ✅ tests preceded implementation | ✅ 35 assistant/auth tests and 10 report-policy tests passed | ✅ SQLite/in-memory persistence and route policy | ✅ provider details and expired files sanitized |
| 2.3 | `tests/test_assistant_phase23.py`, `tests/test_reports.py` | ✅ 47 relevant tests; 3 stale-date failures identified | ✅ 2 new behavior failures before implementation | ✅ 8 focused tests passed; refreshed-data tests 23 passed | ✅ 20th-turn allowance, SQLite idempotency, transient/permanent provider paths | ✅ repository lookup, bounded assertions, focused format/lint |
| 3.1 | `lib/api/chat.test.ts`, `components/chat/ChatDrawer.test.tsx`, `app/(authenticated)/chat/page.test.tsx` | ✅ 101 baseline tests | ✅ tests written before frontend changes; missing contract/view helpers failed | ✅ 12 focused tests passed | ✅ all five statuses, expired/raw-link, tenant/user/cache cases | ✅ tests kept at pure-contract/view-helper layer |
| 3.2 | same | ✅ 12 focused frontend tests | ✅ written first | ✅ 12 focused tests and build passed | ✅ partial evidence, freshness, typed refs, attachments, tenant checks | ✅ shared `AssistantMessage` renderer |
| 3.3 | same | ✅ 113 unit tests | ✅ written first | ✅ 113 unit tests passed | ✅ tenant/user request rejection and server-only links | ✅ removed markdown/download fallback and added abort/reset guards |

## Slice 4 Verification
- Focused/frontend: `npm run test:unit` — 27 files, 113 tests passed.
- Type/build: `npm run typecheck` passed; `npm run build` passed.
- Lint: `npm run lint` passed with the repository's pre-existing unused-variable warnings outside the assistant slice.
- E2E: intentionally deferred to Phase 4; no cross-repository Playwright verification started.
- Rollback: revert the frontend Phase 3 work-unit commit; preserve backend source and unrelated working-tree changes. Keep this OpenSpec artifact and task marks as the apply audit trail.

## Slice 5
- Boundary: Phase 4 cross-repository verification and rollout gate only; backend history serialization and deterministic frontend Playwright integration were remediated, with no archive or independent final audit.
- Delivery: feature-branch-chain work-unit slice on `feature/cross-module-business-assistant` in both repositories; review budget is 389 changed lines including tests, router serialization, and fixtures.
- Completed: 4.1 RED, 4.2 GREEN, and 4.3 REFACTOR/GO-NO-GO. Added API integration coverage for governed-envelope history round-trip, SQLite attachment persistence, tenant isolation, safe entity refs, and frontend Playwright coverage for drawer/full-page parity, freshness, authorized report downloads, expiry, and tenant switching.
- Remediation: `MessageResponse` now exposes tenant/user ownership and persisted status, tools, sources, freshness, entity refs, and attachments; this fixes the Phase 3-deferred history contract gap without changing legacy message fields.
- Rollout decision: NO-GO for broad enablement until the later independent audit; keep `chat-ia` canary-only/disableable and keep `purchase_plans` unregistered. Migration review confirms additive metadata columns and RLS enabled; no migration or source-data changes were required in this slice.

## TDD Cycle Evidence (cumulative)
| Task | Test file | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|
| 1.1 | `tests/test_assistant_contracts.py`, `tests/test_assistant_registry.py` | N/A (new) | ✅ written; collection failed before implementation | ✅ 7 passed | ✅ negative contract/security cases | ✅ focused lint |
| 1.2 | same | ✅ 27 baseline tests | ✅ written first | ✅ 7 passed | ✅ tenant binding, route and filter rejection | ✅ focused lint |
| 1.3 | same | ✅ 7 focused tests | ✅ written first | ✅ 7 passed | ✅ failure/redaction branches | ✅ focused lint |
| 2.1 | `tests/test_agent_chat_multitenant.py`, `tests/test_reports.py` | ✅ 35 relevant tests | ✅ written first; 6 RED tests | ✅ 6 focused tests passed | ✅ empty, clarification, duplicate, reference, provider, expiry paths | ✅ normalized contract assertions |
| 2.2 | same | ✅ 35 assistant/auth tests and 10 report-policy tests | ✅ tests preceded implementation | ✅ 35 assistant/auth tests and 10 report-policy tests passed | ✅ SQLite/in-memory persistence and route policy | ✅ provider details and expired files sanitized |
| 2.3 | `tests/test_assistant_phase23.py`, `tests/test_reports.py` | ✅ 47 relevant tests; 3 stale-date failures identified | ✅ 2 new behavior failures before implementation | ✅ 8 focused tests passed; refreshed-data tests 23 passed | ✅ 20th-turn allowance, SQLite idempotency, transient/permanent provider paths | ✅ repository lookup, bounded assertions, focused format/lint |
| 3.1 | `lib/api/chat.test.ts`, `components/chat/ChatDrawer.test.tsx`, `app/(authenticated)/chat/page.test.tsx` | ✅ 101 baseline tests | ✅ tests written before frontend changes; missing contract/view helpers failed | ✅ 12 focused tests passed | ✅ all five statuses, expired/raw-link, tenant/user/cache cases | ✅ tests kept at pure-contract/view-helper layer |
| 3.2 | same | ✅ 12 focused frontend tests | ✅ written first | ✅ 12 focused tests and build passed | ✅ partial evidence, freshness, typed refs, attachments, tenant checks | ✅ shared `AssistantMessage` renderer |
| 3.3 | same | ✅ 113 unit tests | ✅ written first | ✅ 113 unit tests passed | ✅ tenant/user request rejection and server-only links | ✅ removed markdown/download fallback and added abort/reset guards |
| 4.1 | `motoshop-app/api/tests/test_assistant_integration.py`, `frontfambus/tests/assistant-chat.spec.ts` | ✅ 68 API tests / 113 unit tests | ✅ history and parity tests written before router remediation | ✅ 2 API integration tests and 2 Playwright tests passed | ✅ in-memory + SQLite, available + expired report, drawer + `/chat`, tenant switch | ✅ typed fixtures and role-based locators |
| 4.2 | same | ✅ targeted Phase 4 baseline | ✅ written first | ✅ targeted API, unit, typecheck, build, and Playwright passed | ✅ report download, freshness, safe href, cross-tenant 404 | ✅ Ruff/ESLint checks; existing warnings only |
| 4.3 | OpenSpec migration/config review plus registry/security tests | ✅ existing rollout and policy tests | ✅ gate assertions captured | ✅ canary-only/no-purchase-plan decision recorded | ✅ supported registry domains, route ownership, RLS-enabled additive migration | ✅ no source-data or flag enablement changes |

## Slice 5 Verification
- Backend targeted: `uv run pytest tests/test_assistant_integration.py tests/test_agent_chat_multitenant.py tests/test_assistant_phase23.py tests/test_assistant_contracts.py tests/test_assistant_registry.py tests/test_reports.py tests/test_auth_modules.py` — 68 passed, 1 existing Starlette/httpx deprecation warning.
- Frontend targeted: `npm run test:unit` — 27 files, 113 tests passed; `npm run typecheck` passed; `npm run lint` passed with the repository's pre-existing unused-variable warnings; `npm run build` passed.
- Cross-repository Playwright: `npx playwright test tests/assistant-chat.spec.ts --workers=1` — 2 passed. The first run was blocked by a stale local Next server on port 3000; after terminating that stale process, the deterministic suite passed.
- Full suites: root pipeline `uv run pytest` has 9 pre-existing fixture/schema/notebook failures; API `uv run pytest` has 21 pre-existing environment/data/provider failures (Docker MySQL unavailable, refreshed data/forecast/health assumptions). Frontend full Playwright has 22 unrelated failures while the 2 new assistant tests pass; failures are auth/dashboard/alert/stale-banner environment flows, not this slice.
- Quality: changed backend files pass Ruff check/format; frontend typecheck/build pass. No migration or `outputs/`/`tmp/` changes were staged.
- Rollback: backend revert the history-response serialization commit; frontend revert the assistant integration test commit. Preserve prior Phase 1–3 commits and unrelated working-tree changes.

## Remediation Slice 6
- Boundary: backend-only remediation of the five highest-confidence independent-audit blockers; frontend, source data, migration, purchase plans, and final audit remain untouched.
- Delivery: feature-branch-chain work-unit on `feature/cross-module-business-assistant`; the primary implementation commit stayed within the 400-line review boundary, with a separate one-line test cleanup follow-up.
- Completed: authenticated assistant capability context, same-tenant report owner checks, one 30-second provider deadline across retries/tool iterations, safe tool-error logging, and RFC 7807 responses for assistant validation/auth/conversation/report rejections.
- Preserved: existing `tenants.yaml`, `tools.py`, `outputs/`, `tmp/`, and unrelated fixture/config changes remain outside the remediation staging boundary.
- Commits: `be5ed07 fix(assistant): remediate audit blockers`; `5912c9c test(assistant): remove unused remediation response`.

## Remediation TDD Cycle Evidence
| Task | Test file | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|
| R1 capability authorization | `tests/test_agent_chat_multitenant.py`, `tests/test_assistant_phase23.py` | ✅ 74 relevant tests | ✅ context test failed before wiring | ✅ 81 targeted tests passed | ✅ route context + denied inventory tool | ✅ capability filtering centralized |
| R2 report ownership | `tests/test_reports.py` | ✅ 74 relevant tests | ✅ same-tenant different-user test returned 200 | ✅ ownership denial passed | ✅ tenant denial + owner success retained | ✅ unknown post-restart owner fails closed |
| R3 total provider deadline | `tests/test_assistant_phase23.py` | ✅ 74 relevant tests | ✅ retry timeout/deadline behavior absent | ✅ 12 phase tests passed | ✅ two backends + tool-loop clock tests | ✅ absolute deadline passed to provider |
| R4 safe logging | `tests/test_assistant_phase23.py` | ✅ 74 relevant tests | ✅ raw secret/argument appeared in caplog | ✅ redaction test passed | ✅ sensitive and ordinary argument values absent | ✅ structured keys/type only |
| R5 problem details | `tests/test_agent_chat_multitenant.py`, `tests/test_reports.py` | ✅ 74 relevant tests | ✅ validation/report paths returned `application/json` | ✅ 117 targeted tests passed | ✅ 422/401/404/403/502/503 paths | ✅ scoped handler preserves briefing compatibility |

## Remediation Verification
- `uv run pytest tests/test_agent_chat_multitenant.py tests/test_assistant_integration.py tests/test_assistant_phase23.py tests/test_reports.py tests/test_assistant_contracts.py tests/test_assistant_registry.py tests/test_auth_modules.py tests/test_auth_tenant_dep.py tests/test_llm_briefing_multitenant.py` — 117 passed, 1 existing Starlette/httpx deprecation warning.
- Targeted Ruff with `--ignore E501` still reports an import-order finding in `src/motoshop_api/main.py`; the repository-wide Ruff run remains non-green because of unrelated existing findings.
- Strict TDD mode remained active. No independent final audit was run.
- Rollback: `git revert 5912c9c be5ed07`; preserve all unrelated working-tree changes and generated artifacts.
- Remaining audit findings intentionally deferred: expenses/expiry active capability coverage, source-level cross-tenant/query predicate proof, entity ownership/source resolution, rendered UI scenario coverage, RLS policies, and unrelated full-suite fixture/environment failures.

## Stabilization Work Unit
- Boundary: stabilize `ToolExecutor.run` error handling and logging, keep purchase tools disabled in active tenant configuration, and add deterministic tenant fixtures; no source data or unrelated remediation changes were touched.
- Changes: `ValueError` domain/validation messages now pass through unchanged; unexpected exceptions return a generic error while logs retain only tenant, tool, argument keys, and exception type. Removed `get_ultima_compra` and `get_compras_recientes` from both active tenant `enabled_tools` lists.
- Tests: added temporary YAML and DuckDB fixtures for both tenants, including a cross-tenant negative assertion; added domain-error preservation and sanitized internal-error coverage. Updated catalog/report assertions to verify purchase tools are not registered. `uv run pytest tests/test_assistant_remediation.py tests/test_agent_chat_multitenant.py tests/test_reports.py tests/test_tenants.py -q` — 57 passed, 1 existing Starlette/httpx deprecation warning.
- Quality: `uv run ruff check --ignore E501` passed for the work-unit Python files; `uv run ruff format --check` passed. Existing `E501` findings remain outside this focused cleanup scope.
- Commit: pending; stage only `tools.py`, `tenants.yaml`, the three affected API test files, and this progress file.
- Rollback: `git revert <stabilization-commit>`; preserve the prior remediation commits, unrelated working-tree changes, `outputs/`, and `tmp/`.
- Unresolved: expenses/expiry capability implementation, source-level tenant predicates/entity ownership, rendered UI coverage, RLS policies, and unrelated full-suite fixture/environment failures remain deferred. No purchase capability is enabled.
