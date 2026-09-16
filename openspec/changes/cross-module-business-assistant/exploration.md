## Exploration: Cross-module business assistant

### Current State
MotoShop already has a tenant-aware Q&A pipeline in `llm/qa_chat.py`: it loads a tenant profile, resolves the tenant-specific DuckDB through `ToolExecutor`, limits the conversation to 20 turns and five tool iterations, persists conversations in Supabase, and returns `sources`, `data_as_of`, and report `attachments`. The current tool registry is useful but narrow: it covers sales KPIs, top/dormant products, stockout alerts, seller performance, inventory value, period comparison, ABC, forecast, freshness, recent purchases, RAG search, and explicit report generation.

The requested cross-module coverage is split across different sources. Sales, purchases, inventory, ABC, dormant products, alerts, forecasts, and most analyses are DuckDB-backed. Operating expenses come from tenant-filtered Supabase `gastos_operativos`; expiry lots come from tenant-filtered Supabase `app_inventory_lots` and are MasVital-only; and CRUD `purchase_plans` currently uses a process-global in-memory repository without a tenant dependency, so it is not yet a safe authoritative assistant source. Product/search routes also have inconsistent tenant/path handling: product movement analytics is tenant-aware, while several legacy product/stock routes resolve through MySQL without an explicit tenant dependency.

Freshness is not yet a single contract. DuckDB snapshots refresh from R2 per tenant and metrics caches include snapshot generation, but `get_data_freshness()` only reports three tables and the prompt receives one overall latest date. Live Supabase domains need their own `observed_at`/cutoff semantics. The frontend `ChatDrawer` already renders sources and report cards, but the full-page `/chat` still uses a reduced message model; persisted message responses do not expose attachments or a domain freshness object. Report downloads are authenticated and tenant-checked, while application deep links still need a constrained, route-aware reference contract.

### Affected Areas
- `motoshop-app/api/src/motoshop_api/llm/tools.py` — extend the governed tool surface and return structured evidence, freshness, and entity references rather than permitting arbitrary SQL.
- `motoshop-app/api/src/motoshop_api/llm/qa_chat.py` — preserve grounding and explicit-file rules while adding cross-domain cutoff context and normalized response metadata.
- `motoshop-app/api/src/motoshop_api/llm/router.py` — expose the response contract consistently for chat and persisted message retrieval.
- `motoshop-app/api/src/motoshop_api/metrics/repo_duckdb.py` and `metrics/router.py` — reuse canonical DuckDB queries and standardize tenant-specific snapshot/path resolution.
- `motoshop-app/api/src/motoshop_api/gastos/` — adapter for live tenant-scoped operating expenses and its failure/freshness behavior.
- `motoshop-app/api/src/motoshop_api/expiry/` — read-only assistant boundary for MasVital expiry lots; do not expose mutation operations through chat.
- `motoshop-app/api/src/motoshop_api/purchase_plans/` — resolve the current non-tenant-scoped repository before treating saved plans as assistant-readable business data.
- `motoshop-app/api/src/motoshop_api/auth/tenant_dep.py` and `tenants.yaml` — enforce tenant and feature/tool authorization for every new capability.
- `motoshop-app/api/src/motoshop_api/reports/` — retain explicit-only generation, TTL, and tenant-checked downloads.
- `infra/supabase/migrations/20260914_001_agent_chat.sql` — persist any new structured sources, freshness, or attachment metadata if history must reproduce it.
- `frontfambus/lib/api/chat.ts`, `components/chat/ChatDrawer.tsx`, and `app/(authenticated)/chat/page.tsx` — consume one response model and render authorized deep links, freshness/cutoff labels, sources, and attachments consistently.
- `frontfambus/lib/auth/access.ts` and `app/(authenticated)/layout.tsx` — reuse the existing route/module matrix; UI visibility is not a substitute for API authorization.

### Approaches
1. **Governed domain tools with a shared evidence contract** — add narrowly scoped read-only tools/adapters per business capability, backed by canonical repositories or explicitly approved live-source adapters. Each result includes domain, tenant, cutoff/observed timestamp, source tables or documents, and typed entity references resolved against an allowlisted route map.
   - Pros: strongest tenant/security boundary; deterministic calculations; clear freshness semantics; easy to test with existing fakes and DuckDB/Supabase fixtures; avoids exposing schema or SQL to the model.
   - Cons: more tool and adapter code; requires resolving source ownership and the purchase-plan gap before claiming full coverage.
   - Effort: Medium

2. **Generic read-only semantic catalog and SQL tool** — expose approved table/schema metadata and let the model compose read-only queries for arbitrary cross-module questions.
   - Pros: broad coverage with fewer hand-written tools; useful for exploratory admin analytics.
   - Cons: difficult to guarantee correct joins, business definitions, date cutoffs, tenant isolation, row/column protection, and safe links; model-generated SQL can silently produce plausible but wrong answers.
   - Effort: High

3. **Internal calls to existing REST endpoints** — have the assistant call the same backend endpoints used by the UI and summarize their JSON responses.
   - Pros: reuses existing response schemas and authorization intent; minimizes duplicate query logic initially.
   - Cons: adds request/auth/cache coupling and inconsistent freshness metadata; several endpoints are legacy or not tenant-aware; responses are UI-shaped and do not provide a stable cross-domain evidence model.
   - Effort: Medium

### Recommendation
Use approach 1, with a small shared governance layer rather than a generic SQL interface. Keep business calculations in canonical repositories/queries, add read-only domain adapters for expenses and expiry, and block saved purchase-plan data until its tenant scope and persistence model are corrected. Standardize a response envelope containing tenant, answer data, per-source cutoff/observed time, source citation, and typed `entity_ref` values; resolve those references server-side against an allowlist of existing frontend routes and enforce the same tenant/module policy at the destination. Preserve `generate_report` as an explicit user-intent operation, and make report metadata a first-class attachment instead of relying on a markdown download URL for history.

The first proposal should define the authoritative-source matrix and supported capability matrix before implementation. It should also explicitly decide whether this change includes the full-page `/chat` parity, persisted attachment/freshness schema changes, and repair of legacy tenant/path inconsistencies, or scopes those into separate reviewable work units.

### Risks
- A single global `latest_date` can misrepresent freshness when DuckDB, Supabase expenses, and live expiry data have different cutoffs.
- `settings.duckdb_path` and legacy MySQL routes can bypass the tenant-specific path convention if reused without an adapter boundary.
- Treating `purchase_plans` as authoritative currently risks cross-user/cross-tenant leakage because its fake repository is process-global and the route has no tenant dependency.
- RAG documents are tenant-filtered, but retrieved document text must remain data rather than instructions and citations must be preserved.
- Raw URLs or model-generated paths could link users to unauthorized modules or another tenant; references must be typed and server-validated.
- Report files are temporary (24-hour TTL) and downloads require authentication; persisted chat history must handle expired attachments explicitly.
- Existing full-page chat and drawer have different frontend contracts, increasing regression risk unless unified.
- Cross-repository backend/frontend changes may exceed the 400-line review budget and should be split into independently verifiable work units if the proposal confirms both sides.

### Ready for Proposal
Yes. Proceed to `sdd-propose` after confirming scope boundaries: the proposal should prioritize governed domain tools plus the shared evidence/link contract, and call out purchase-plan tenant scoping, freshness-source normalization, and frontend chat contract parity as explicit dependencies or separately reviewable work units.
