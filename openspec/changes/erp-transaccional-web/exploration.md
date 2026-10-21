# Exploration: erp-transaccional-web (read-only analytics → transactional web ERP)

> sdd-explore artifact · 2026-10-20 · RESEARCH ONLY — no proposal/spec written here.

## Executive summary (5 findings with evidence)

1. **A sanctioned write-path already exists and works.** `app_writes` module writes InnoDB
   `app_*` tables into the same legacy DB with a dedicated MySQL user (`app_writer`):
   `src/motoshop_api/app_writes/router.py` (`POST /api/alerts/{id}/action` with
   `Idempotency-Key` UUIDv4 replay protection), `repo.py:200-359` (RealAlertActionsRepo via
   `get_writer_engine()` from `db/engine.py:32-49`), migrations
   `infra/migrations/F5-001-app_alert_actions.sql`, `F5-002-app_audit_log.sql`,
   `F5-003-grant_app_writer.sql`. ADR-0004
   (`docs/decisions/0004-innodb-app-tables-f5.md`) already decided: new tables live
   InnoDB inside `motoshop2024`, `app_*` prefix, "sgHermes ni se entera".
2. **Cloud API cannot write to MySQL today.** `render.yaml` (Render free, oregon) declares
   NO MySQL env vars and `DATA_BACKEND=duckdb`; MySQL-dependent endpoints degrade via the
   global `OperationalError` handler returning 503 "Funcionalidad no disponible en cloud…
   Requiere el sistema operativo encendido" (`main.py:195-218`). MySQL is reachable from the
   **local API** (`MYSQL_HOST=localhost`, `infra/start_api.ps1:129`) exposed by Cloudflare
   Tunnel `motoshop-local.fragloesja.uk` (`infra/start_tunnel.ps1:21-24`, tunnel id
   91f4b0e5-…, scheduled task `MotoShopTunnelSvc`). MySQL endpoints are intentionally
   degraded on Render ("sólo Windows on-premise tiene MySQL" — `docs/audit/F7-AUDIT.md:229`).
3. **Auth/RBAC foundation is production-grade and ERP-ready.** JWT HS256 access 15 min /
   refresh 7 d (`config.py:90-93`), users from `users.yaml` merged with Supabase-managed
   users at startup (`main.py:80-95`), roles `admin/gerente/vendedor` (`users.yaml`),
   `require_role` (`auth/deps.py:58`), per-module authorization via central route/method
   matrix (`auth/module_access.py` — add new modules = add entries), multi-tenant via
   `tenants_allowed` + FE cookies `motoshop_token`/`motoshop_tenant`
   (`frontfambus/middleware.ts:16-31`).
4. **The transactional core was fully reverse-engineered with file:line evidence** —
   document dispatcher `Botones.cs` (header+detail+payments+accounting entries per doc),
   `contadores` sequence engine with `LOCK TABLES` + `Bus_Con_Act` auto-heal
   (`code_analysis.md` §3), totals formula §4, POS save flow §5, complete annulment reversal
   §7 (`motanudoc` + flag flips + stock recalc), DIAN pipeline §14 of `modules.md`
   (Dataico/SoftProp integrators, `respdocfele`/CUFE, `estfele 1/2` blocks edits), masters
   catalog §10. The new web system can replicate this pattern with one transactional save
   engine + `codcon`/`tipclas` discriminator.
5. **No schema-migration tool.** Zero Alembic/use of alembic in repo (grep across
   motoshopData: no matches). Current convention = numbered hand-run SQL files under
   `infra/migrations/` (+ Supabase SQL migrations under `infra/supabase/migrations/`).
   Legacy schema dump `docs/hermes/evidence/schema_2024.sql` contains **175 CREATE TABLE**
   statements (docs mention "166 business tables"; the dump also includes the
   post-2024 `app_*`/`app_llm_usage`/`app_pipeline_runs` tables already migrated).

## Current state

### Backend — routers/endpoints (motoshop-app/api/src/motoshop_api)

Registered in `main.py:239-260` under `/api` — 17 routers:

| Router | Endpoints | Read backend | Writes? |
|---|---|---|---|
| auth | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` | YAML+Supabase users | refresh tokens |
| admin | `POST /admin/data/refresh`, `POST /admin/pipeline/refresh`, `GET /admin/llm-cost`, `GET /admin/data` (catalog) | pipeline control | — |
| alerts (read) | `GET /alerts/stockout`, `POST /alerts/cache/clear` | DuckDB/R2 | — |
| app_writes | `POST /alerts/{id}/action` (idempotent), `GET /alerts/actions/me` | **MySQL app_* InnoDB** | ✅ INSERT + audit log |
| expiry | `GET /expiry/lots`, `GET /expiry/alerts`, `POST /expiry/receipts`, `PATCH/DELETE /expiry/lots/{id}` | **Supabase** | ✅ CRUD |
| forecast | `GET /forecast/{sku}` | DuckDB | — |
| gastos | `GET/POST /gastos`, `POST /gastos/copiar`, `PATCH/DELETE /gastos/{id}` | **Supabase** | ✅ CRUD |
| health | `GET /health/ready`, `GET /health/data-freshness` | manifest | — |
| llm + briefing | `POST /qa/chat`, conversations CRUD, explain | Supabase/DuckDB | chat rows |
| metrics | ~40 GET endpoints (ventas, compras, inventario, abc, dormidos, cohortes, drift, vendedores…) | DuckDB per-tenant files from R2 | — |
| pipeline_runs | `GET /admin/pipeline/runs[/{id}]`, `GET /admin/pipeline/summary` | pipeline_runs.duckdb | — |
| products | `GET /products`, `/products/{sku}`, `/products/{sku}/movements`, `search-semantic` | MySQL (locally) / snapshot | — |
| purchase_assessments | `GET/POST /purchase-assessments` | Supabase + LLM | ✅ |
| purchase_plans | `GET/POST /purchase-plans`, `PATCH /{id}/status` | MySQL `app_purchase_plans` (F7-001) | ✅ |
| push, reports, sales, stock | `POST /api/push/[un]subscribe`; `GET /reports/download/{id}`; `GET /sales/recent` (MySQL facventas, estfven='A'); `GET /products/{sku}/stock` (MySQL auxinventario) | DuckDB/MySQL | — |
| admin/users | `GET /api/admin/users[...] `, `POST/PATCH/DELETE /api/admin/users[/{username}]` | Supabase | ✅ |

Multi-tenant: 2 tenants today (`motoshop`, `masvital`) via `tenants.yaml` (r2_object_key,
local_db_path, mysql_source); tenant separation lives in the DuckDB read path and
Telegram routing — **legacy MySQL itself is currently a single-DB source shared by
tenants, not tenant-scoped at the schema level**. Any transactional core must decide
tenant→DB/empresa mapping (sgHermes is single-empresa per data set).

Repo pattern: SQLAlchemy Core `Table` definitions (`db/tables.py` — note: columns typed
`String` to mimic legacy weak types) + Repo class with **Fake twin + factory** for tests
(`sales/repo.py`, `app_writes/repo.py:443-458`), Protocol contracts, DuckDB shared
connection manager (`metrics/repo_duckdb.py`). Idempotency (`uq_idempotency`) and
`app_audit_log` are the established write-side patterns.

Engines: read engine (autocommit, pool 5+10) + **writer engine** (`app_writer`, pool 2+4,
autocommit; `db/engine.py`). Note: current writer keeps autocommit "per INSERT atómico" —
fine for single-row app_* rows; the ERP document saver will need real InnoDB
`BEGIN/COMMIT` units (this is a flagged gap, not a blocker).

### Frontend (../frontfambus — Next.js 14 PWA, sibling git repo)

- Auth UI: `app/login/page.tsx` (cookie `motoshop_token`), `app/select-tenant/page.tsx`
  (`motoshop_tenant`), route gating in `middleware.ts` (public: /login,/select-tenant,
  /api/auth/*). API base `NEXT_PUBLIC_API_URL`.
- Live pages under `(authenticated)`: home KPIs, `dashboards/{ventas,inventario,abc,dormidos,compras}`
  (+day drilldowns), `alerts`, `acciones` (alert actions = first write feature in UI),
  `chat` (assistant), `cohortes`, `drift`, `forecast`, `plan-compras`, `products[/{sku}]`,
  `vendedores`, `profile`, `admin/{data-catalog,pipeline}`. Vitest + Playwright configured
  (no `test:unit` script — run `npx vitest run`).
- No ERP/deposits/POS UI exists. UI layer is SWR/presentational and can reuse the
  navigation/parametrization patterns.

### ETL / pipeline relationship (Q6)

Local PC: mysqldump → bronze parquet (R2/Databricks volume originally; now
`mysql_source.py` → DuckDB per tenant) → silver → gold `{tenant}_gold.duckdb` → R2 →
Render downloads at boot (~1 min, 503 "loading" window handled in `main.py:170-191`).
Data is a **snapshot pipeline** — rebuilt per run, idempotent. Transactional tables the ERP
adds MUST NOT be lumped into gold business aggregates: today's dump exports the whole DB
(`capture_new_sales.ps1`, `infra/dump_to_cloud.py`) — post-erp it needs an explicit
include/exclude list so (a) `app_*` tables don't pollute KPIs, and (b) the transactional
doc tables (facventas/detcuentas…) DO flow into analytics coherently with desktop data.

## Approaches per fork

### Fork A — Operational store for the transactional ERP

| Option | Description | Pros | Cons | Verdict |
|---|---|---|---|---|
| A. Postgres on Render free + one-way sync from legacy | ERP operates on cloud PG, sync legacy→PG | Cloud-native, 24/7, analytics-friendly | **Broken foundation**: desktop sgHermes keeps running on MySQL (ADR-0004 context, `roadmap-v2-produccion.md` R-V2-8 assumes it on-premise); two live systems writing stock/`contadores`/CxC = dual-ledger hell; Render free Postgres is ephemeral (free PG retired; needs paid plan); sync introduces stale stock & lost sequences | ❌ ruled out for business core; MAY still be used later as read replica (sync `app_read`) if backoffice analytics needs it |
| **B. Operate directly on legacy MySQL via dedicated InnoDB write tables** | Extend ADR-0004: business docs as InnoDB tables in `motoshop2024` (either reusing legacy doc tables like facventas/detcuentas, or new `erp_*`/`app_*` prefixed ones + reconciliation), `app_writer`-style GRANT per table, API write-path hosted on the Windows PC (local API already tunnel-exposed) | One ledger shared with desktop Hermes (`contadores`, `exiprod`, `detcuentas` truth align with the company's real books); existing write+audit+idempotency pattern to build on; already proven in prod for app_* tables; no new infra cost | MySQL 5.0.45 (2006!): latin1, non-transactional MyISAM neighbors, ancient optimizer; tunnel round-trip for cloud users (~100–300 ms extra, POS tolerable); SPOF = PC uptime (already mitigated partly by tunnel watchdog `start_tunnel.ps1`); uniqueness must be enforced with real unique indexes (legacy only enforces in-app) | ✅ **recommended core** |
| C. SQLite / DuckDB as OLTP | Local SQLite file or DuckDB as the doc store | Cheap, embedded | DuckDB is an embedded *analytics* engine (single writer, no concurrent server, no WAL-client protocol) — objectively not OLTP; SQLite forks the data again (same dual-ledger problem as A) and its 5.0-era compat story adds a 3rd storage tech to an already split stack (MySQL+SQLite+DuckDB+Supabase) | ❌ ruled out |

Sub-decision inside B (defer to design): **write to legacy document tables
(facventas/detcuentas…) vs. `erp_*` shadow tables**. Evidence for reusing legacy tables:
mongoose style contadores engine is shared DESKTOP+WEB safe (`LOCK TABLES contadores WRITE`
is engine-level and works from any client; `Bus_Con_Act` heals). Evidence for caution:
desktop remains active (empresas may run both in parallel); schema constraints (latin1,
varchar numerics `String(20)` columns) could make a typed `erp_*` core + mirror job safer.
This is the #1 design question for sdd-design; both are compatible with fork B.

DIAN payload retention under B: keep `respdocfele` (CUFE/QR/estfele) plus a new
`app_dian_payloads` (JSON/TEXT, InnoDB) for full request/response audit — satisfies
the "no TLS pinning/retry" gap noted in `modules.md` §14.

### Fork B — Transactional core table map (Q3 — which of the 166/175 tables get touched)

Confirmed present in `schema_2024.sql`: `facventas`, `detfventas`, `detapago`,
`notascxccxp`, `detnotcxccxp`, `detcuentas`, `contadores`, `terceros`, `productos`,
`auxinventario`, `bodegas`, `formapago`, `empfpago`, `cajas`, `resdian`/`resolpuc`,
`respdocfele`, `provetecno`, `motanudoc`, `cierresper`, `cajaarqueo`, `detcajarq`,
`comprobantes`, `consbancab`, `financiacion`, `detfinancia`, `entsalida`,
`notabodegas`+`detbodegas`, `despachos`+`detdespachos`, `recepmerca`, `preciosxpro`,
`listapre`, `produndmeds`, `prodcodbars`, `subproduct`, `detimpuestos`, `linea1`.
(cut-sheet: `nominas`/`cajaarqueo` exist but are empty/unused in this shop per
`code_analysis.md` §8 — XS scope for ERP.)

### Fork C — Deployment topology for writes

- Transactional APIs MUST run where MySQL is: **Windows on-prem API** (already runs at
  localhost:8000, tunnel-served at `motoshop-local.fragloesja.uk`; ADR-0007 hosts API next
  to MySQL). Render cloud API stays read-only analytics (its 503 degradation policy
  `main.py:216` even lists MySQL endpoints as unavailable).
- Cashier latency: tunnel adds ~100–300 ms per call; POS save = 1 request (batch doc) —
  acceptable. Mitigation: offline-capable PWA cash drawer queue (design phase).

## Risk register (top − severity)

1. **Contadores double-booking: desktop Hermes + web ERP increment the same `conres`** —
   mitigated if numbering engine is serialized (LOCK TABLES + unique index on
   (codclas/numdoc)); risk is *behavioral*: users must not hand-type numbers
   (`numauto='NO'` for some doc types demands it) — **High**; mitigation: ERP enforces
   `numauto` and `Valid_NumFin` server-side; coordinate with business on doc-type prefixes.
2. **MySQL 5.0.45 antiques** — latin1 charset (mojibake risk for new UI text), varchar
   numerics, no CHECK/FK on MyISAM, no window functions, ancient driver quirks
   (pymysql works but old auth plugin); every new InnoDB table must declare utf8 but coexist
   with latin1 joins — **High**; mitigation: explicit charset strategy in design doc,
   typed numeric conversion at Pydantic boundary (existing `db/tables.py` String-typing).
3. **PC-Uptime SPOF for an ERP that bills** — tunnel watchdog re-heals, but PC reboot/PB
   power loss stops sales; catastrophic for POS — **High**; mitigations: local API + local
   DB on same host (latency-free for LAN cashier), offline queue in PWA, UPS, fallback
   printed manual workflow.
4. **Render free-tier cold starts** — spin-down wipes `/tmp` DuckDB (R2 re-download ~1 min,
   handled) and kills background workers (purchase_assessments worker); NOT for
   transactional writes (they don't live there) but for analytics dashboards — **Medium**.
5. **DIAN e-invoicing vendor dependency** — provider account does not exist yet (Dataico
   token or SoftProp endpoints; SoftProp endpoints are plain HTTP fixed IPs — security
   finding in `modules.md` §14); until the account exists, slice 6 ships with a stub
   adapter and legal descrépito note — **High (schedule)** / process must start Dataico
   onboarding before slice 6 build.
6. **ETL contamination** — new transactional tables flowing into bronze/gold without
   curation pollutes KPI models and increases dump size; needs dump include/exclude policy —
   **Medium**.
7. **Tenant-vs-empresa mismatch** — sgHermes DB is one empresa; `masvital` availability for
   transactional ops needs a decision (separate MySQL DB?) — design-doc item — **Medium**.

## Candidate decomposition (validated slices, ordered)

Each slice independently deployable, uses the module-access matrix to gate by role, and
follows repo pattern (router/schema/repo + Fake + tests + SQL migration file).

1. **Slice 1 — Auth/RBAC/Write-foundation hardening (enabler, largely built)**:
   reuse JWT+roles+module matrix; standardize write-foundation: per-table GRANT script
   style (F5-003 pattern), transactional unit-of-work helper (real `BEGIN/COMMIT` for doc
   writes), `app_audit_log` reuse, idempotency-key convention, migration runner script for
   `infra/migrations` (or adopt Alembic later — decision); deployable as-is.
2. **Slice 2 — Masters write**: terceros (+`tercecorreo`), productos (+`prodcodbars`,
   `produndmeds`, `preciosxpro`/`listapre`), validity rules from `BotGuarMa.cs` catalog
   (`code_analysis.md` §10). UI: master CRUD pages. Depends on slice 1.
3. **Slice 3 — Sales invoice minimal (POS-like)**: numbering engine (contadores with
   `LOCK TABLES` + unique index), invoice save (facventas+detfventas using totals formula
   §4), `detapago` payments, causación to `detcuentas` (linea1.codcue/IVA/cost/caja per §5.4),
   stock movement rule (§5.5 pattern vs. client's stock-validation policy decision — legacy
   didn't validate), print/receipt via browser PDF/P80 (no ESC/POS needed per §9),
   `Valid_EdiDocele`-aware (cash invoice is paper resolution only at this slice).
4. **Slice 4 — Collections & cash**: `detapago` receipts (duality soldeb/solcre §5.3),
   arqueo (cajaarqueo+detcajarq S38), egresos (comprobantes S02/S03),
   consbancab (`formapago.numcon`), CxC aging readback reused from metrics.
5. **Slice 5 — Annulment & accounting reversal**: replica `Boteliminar.cs` flow §7:
   `Veri_Anul`, `Hay_Cie_Eli` (cierresper guard), `motanudoc` log, flag flips
   (estfven/estcue/estado), stock recalc (`Actual_salProd`/recalcula exiprod from detcuentas),
   permission prompt (`N049`-equivalent server-side check) + reason required.
6. **Slice 6 — DIAN e-invoicing**: `provetecno` config UI, `respdocfele` persistence,
   `contadores.envfele`/`formapago.codfele`, async send queue with retries+reconciliation
   ("client Web API puro" gap fixed), CUFE/QR in receipt foot, `estfele 1/2` edit-block
   integration with slice 5. External dependency: provider account must exist (or stub).

Dependency edges: 1→2→3→(4,5)→6. Slices 4 and 5 can partially parallelize after 3.

## Recommendation

Fork **B** (operate on legacy MySQL, InnoDB write tables, write-path hosted on the Windows
API, Render stays analytical). Continue ADR-0004; document the new ADR
(legacy-table reuse vs `erp_*` shadow + mirror for the core ledger; requirement: run the
transactional module code-side in the local deployment targeting `localhost` MySQL, keep
slices deployable behind the module matrix). Start with the
validation slice 1 enabler, then masters (2), then minimal invoice (3).

## Risks
(see register above)

## Ready for Proposal
Yes. Sources cita-ready: `modules.md` (esp. §3 contadores via code_analysis, §9 fiscal,
§14 DIAN, §15 prices), `code_analysis.md` §1-§10, `data_dictionary.md`
(MySQL 5.0.45/MyISAM inventory), `schema_2024.sql` (175 CREATE TABLE), ADRs 0004/0006/0007,
live routers and write-infra files listed above.
