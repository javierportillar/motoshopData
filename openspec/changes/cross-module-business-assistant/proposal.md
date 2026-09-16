# Proposal: Cross-module business assistant

## Intent and objectives

Give every authorized tenant an assistant that explains modules/entities from attributable data, reports freshness, provides authorized links, and generates files only after explicit intent.

## Current implementation vs proposed work

- **Current:** `qa_chat.py` is tenant-aware, bounded, persistent, and returns basic sources, `data_as_of`, and attachments. `tools.py` covers core DuckDB analytics; `ChatDrawer` renders sources/reports.
- **Proposed:** governed cross-domain adapters, one evidence/freshness/link envelope, full-page/drawer parity, source ownership/failure rules, and closed tenant/path gaps.

## Scope

### In scope

- **Coverage:** read-only tools for sales, purchases, inventory, ABC, dormant products, alerts, forecasts, and analyses from DuckDB/R2; tenant-filtered Supabase adapters for expenses and MasVital expiry. `purchase_plans` stay unavailable until tenant-safe and authoritative.
- **Governance:** allowlisted tools/capabilities, tenant feature policy, typed inputs, parameterized canonical queries, bounded results, and no arbitrary SQL or model-selected tables.
- **Contract:** metadata MUST include tenant, answer, per-source evidence, source kind, cutoff/observed time, and typed `entity_ref`; the backend resolves refs via an allowlisted route map and rechecks authorization. Reports remain explicit-only, tenant-checked, TTL-bound attachments.
- **Delivery:** backend/history persistence, `frontfambus` client/drawer/`/chat` parity, tests, and tenant-flagged rollout.

### Out of scope

- Assistant mutations/CRUD, arbitrary SQL/catalog access, unrelated legacy-route repair, or treating RAG text as instructions.
- Making purchase plans readable before tenant ownership/persistence is corrected.

## User journeys and safety

1. A cross-module question returns evidence and distinct DuckDB, expense, and expiry freshness.
2. An entity answer offers a typed link only when entity, destination, and tenant are authorized.
3. Excel/PDF/Word is created only on explicit request; expired files are re-requestable.
4. Source/provider failure returns a truthful partial/unavailable result, no invented figures, and 503/502 behavior.

## Affected areas and rollout

`motoshop-app/api/src/motoshop_api/llm/{tools,qa_chat,router}.py`, metrics/gastos/expiry/purchase_plans/auth/reports, `infra/supabase/migrations/20260914_001_agent_chat.sql`, and `../frontfambus/{lib/api/chat.ts,components/chat/ChatDrawer.tsx,app/(authenticated)/chat/page.tsx,lib/auth/access.ts,app/(authenticated)/layout.tsx}`. Ship backend first, frontend parity second, tenant canaries last. Rollback disables the flag and reverts consumers without changing source data.

## Capabilities

### New

- `governed-business-assistant`: tenant-scoped read-only Q&A, failures, and explicit reports.
- `assistant-evidence-freshness-links`: evidence, cutoffs, and authorized entity refs.
- `assistant-chat-delivery`: consistent history, drawer, full-page, and attachments.

### Modified

- `multi-tenant-m1-backend`: enforce tenant/feature authorization at every assistant source and destination.

## Success criteria and review risk

- 100% of supported tools/links pass cross-tenant tests; raw/model-generated URLs are rejected.
- Every source has its own cutoff/observed timestamp; partial failures are labeled and never fabricated.
- Drawer and full-page chat share the contract; files require explicit requests.
- Combined backend, migration, and frontend work is likely **High risk for 400 lines**; tasks MUST propose independently verifiable backend/frontend slices, with chained-PR confirmation before apply.

## Dependencies and risks

Requires canonical source ownership, Supabase fixtures, route-policy coordination, and a tenant-safe purchase-plan decision. Mitigate stale mixed-source answers, path leakage, expired files, and contract drift with fixtures, tenant tests, timestamps, and fail-closed refs.
