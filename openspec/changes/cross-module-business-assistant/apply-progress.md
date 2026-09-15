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
