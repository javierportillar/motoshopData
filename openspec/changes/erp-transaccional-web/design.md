# Design: erp-transaccional-web — Transactional Web ERP on Legacy MySQL

## Technical Approach

Continue **Option B** (proposal): ERP writes the *legacy* doc tables (`facventas`, `detfventas`,
`detapago`, `detcuentas`, …) directly, coordinated with desktop sgHermes through the shared
`contadores` engine, plus InnoDB `app_*` companions (ADR-0004) for journal, idempotency, audit
and DIAN. Write-path lives in the **on-prem Windows API** only (FastAPI, new `erp/` package);
Render stays read-only. One monolithic transactional save engine replicated per slice, built on
the existing router→schema→repo + Fake-twin + module_access matrix pattern. Implements specs:
`erp-write-foundation`, `erp-masters-write`, `erp-sales-invoicing`, `erp-collections-cash`,
`erp-document-annulment`, `erp-dian-einvoicing`.

## Architecture Decisions

### ADR-0008-01 · Reuse legacy tables (no `erp_*` shadow)

| Option | Tradeoff | Decision |
|---|---|---|
| Reuse legacy tables + `app_*` companions | One ledger, desktop sees web docs instantly; MyISAM weakness mitigated by journal | ✅ |
| `erp_*` shadow + mirror | Typed schema, but dual-ledger divergence vs a running desktop; contadores must be shared anyway | ❌ |

Confirmed per proposal; `contadores` stays the single numbering source for both systems.

### ADR-0008-02 · Stock policy: legacy parity (warn), config-flagged

`stock_negative_policy: warn|block` in the tenant ERP config; default **warn** for slice 3 —
posting never blocks, response flags negative lines. Legacy never validated stock
(`Edi_CueInvProd`, code_analysis §5.5; 5 products already negative) and stock is a cached
balance recomputed from the `detcuentas` kardex. Warn preserves "reveal character", keeps pilot
non-blocking; future `block` mode flips a config, no code change.

### ADR-0008-03 · Unit of Work = one request, one transaction, fixed order

The current writer engine is autocommit (`db/engine.py:32-49`, fine for single-row `app_*`). ERP
document saves get a **new transactional engine `get_erp_engine()`** (app_writer user,
`autocommit=False`, pool 2+4) and an `erp_write_uow` context manager.

**MySQL 5.0.45 constraint:** `LOCK TABLES` implicitly commits and forces autocommit off in 5.0;
you cannot nest `LOCK TABLES contadores` inside a multi-table `BEGIN/COMMIT` that also touches
other tables. So the save is a **fixed 3-phase sequence**, journal-first (spec
"Journal leads the save"):

```
Phase 0  Idempotency precheck (app_idempotency) ─ replay → return stored response
Phase 1  journal: INSERT app_doc_journal PENDING (autocommit, InnoDB)   ← first write
Phase 2  numbering: LOCK TABLES contadores WRITE → Bus_Con_Act heal
         (MAX+1) → Valid_NumFin window check → read conres → UPDATE conres+1
         → UNLOCK TABLES  (bounded lock wait ≤ 5 s; heartbeat UPDATE marks journal number)
Phase 3  BEGIN (autocommit=0)
           INSERT legacy doc tables (fixed order: facventas → detfventas)
           INSERT detapago (Graba_Fpago parity, soldeb/solcre duality)
           INSERT detcuentas (Grab_NueCausa parity; enforce Σvaldeb = Σvalcre)
           UPDATE exiprod / ubiprodbod stock (warn-or-block per ADR-02)
         COMMIT
Phase 4  journal PENDING → COMMITTED (+ respdocfele slot in slice 6)
Failure  φ3: compensating DELETEs for already-inserted MyISAM rows in a new
             unit, journal → FAILED(error).  φ2: journal → FAILED, heal job
             releases the number (lagged-counter Bus_Con_Act redoes MAX+1).
```

Spec's "stock → contadores inside LOCK TABLES" fixed order from the launch prompt resolves to
the φ-sequence above — MySQL 5.0 forbids holding `LOCK TABLES` across `BEGIN/COMMIT` on other
tables, so numbering serializes *before* the write unit; uniqueness is backstopped by new UNIQUE
indexes on `(codclas-classified) (pref, numdoc)` per doc table (unique-index migration aborts on
duplicates before DDL). Crash-recovery heal job (periodic + on-startup): `PENDING` rows older
than watchdog threshold with zero legacy rows → `FAILED`, number released via `Bus_Con_Act`
logic; nightly consistency check (Σ doc totals vs `detcuentas`, `exiprod` audit). Idempotency:
`app_idempotency` table keyed by UUIDv4 `Idempotency-Key` storing response snapshot (F5-001
pattern), replay short-circuits at φ0.

### ADR-0008-04 · Tenant→empresa mapping (config-driven; masvital off)

Extends `tenants.yaml` per tenant: `erp: { enabled, empresa, stock_negative_policy, dian_provider }`.
`motoshop → empresa` of `motoshop2024`; **`masvital: erp.enabled=false`** until its mapping is
decided — write endpoints return 403 "tenant not enabled" per spec. All reads/writes filter by
`empresa`/`codemp` server-side (tenant never client-supplied). One MySQL DB today; adding another
tenant DB later only extends the mapping.

### ADR-0008-05 · Offline PWA cash queue: OUT of scope (slices 1–5)

Online POS only. Offline queue (IndexedDB replay of failed saves) is deferred to a follow-up
change with its own idempotency/design work. Mitigations now: LAN-local API (cashier latency
~0), UPS, printed-manual fallback. Documented here and in proposal risk 3.

### ADR-0008-06 · DIAN provider-agnostic adapter + stub

```python
class DianAdapter(Protocol):
    def build_payload(self, doc: ErpDocument) -> DianPayload: ...
    def send(self, payload: DianPayload) -> DianResponse: ...      # idempotent per doc
    def poll(self, doc_key: str) -> DianResponse: ...
```

`DianStubAdapter` default (feature flag `dian_provider: stub|dataico|softprop`): deterministic
pseudo-CUFE, simulated ACCEPT, everything recorded to `respdocfele` + `app_dian_payloads`
marked non-fiscal. Contract-test suite runs any adapter unchanged. Async queue worker
(APScheduler on the local API only) with retry/backoff, max attempts, durable FAILED; retried
send never duplicates `respdocfele` (CUFE idempotency). Web queue scans only journal-origin=web
docs. Desktop `contadores.envfele` sequences untouched.

### ADR-0008-07 · Decimal & latin1 boundary layer

`erp/common/conversions.py`: Pydantic v2 `ConstrainedDecimal` money/qty fields → **never float**.
Values stored in legacy varchar numerics (`valuni`, `dctpes`, `ivapes`, `ipopes`, `candet`,
`totdet`, `totfven`…) go through a **to_legacy_num()/from_legacy_num() string palette** (handles
comma-decimal `Conversion.Val`/`PuntX_Coma` legacy rows). Formuleo exactness (§4):
`totdet = (valuni − dctpes + ivapes + ipopes) × candet`, per-unit amounts; percents in
`dctpor/ivapor`; header `totfven = subfven − totdct + totiva + totipo`. Rounding: arithmetic in
`Decimal` with **ROUND_HALF_UP quantized to 2 decimals only for derived normalized amounts**
(inclusive-price split `pvconi ↔ pvsini × (1+rate)`, arqueo sums stay exact); line/header totals
are exact Decimal products/sums with no extra rounding — validated against legacy formuleo values
in slice-3 parity tests. Charset: connections force **latin1** (charset=utf8/utf8mb4 does not
exist server-side in 5.0.45); Pydantic boundary validates/rejects astral-plane (surrogate)
codepoints, so latin1 round-trip is mojibake-free (spec: accents survive). `SELECT LIMIT`
semantics (5.0-compatible, no offset-without-limit tricks, no window functions) in new repos.

### ADR-0008-08 · Migration mechanics (F8 series, hand-run runner)

`F5/F6/F7` series exist; ERP uses **F8-***. New `infra/migrations/run_migrations.py` (stdlib +
pymysql): applies numbered SQL files in order, exactly once, recording state in `app_migration_state`
(idempotent re-run = no-op). Files: `F8-001-app_doc_journal.sql`, `F8-002-app_idempotency.sql`
(extensions of F5 style: InnoDB, utf8, TIMESTAMP defaults), `F8-003-unique_doc_indexes.sql`
(dup pre-check → abort before DDL), `F8-004-grant_app_writer_erp.sql` (F5-003 pattern: per-table
INSERT/UPDATE/SELECT on legacy doc tables + stock + contadores + app_*), `F8-005-dian_audit.sql`
(`app_dian_payloads`) + config rows. Deviation from Alembic confirmed (zero Alembic in repo; F5
precedent). ETL: `dump_to_cloud.py` gains explicit include/exclude — `app_*` excluded from gold
aggregates; legacy doc tables included so web postings flow into analytics with desktop data.

### ADR-0008-09 · Testing design (spec → runner mapping)

| Layer | What | Runner |
|---|---|---|
| Unit | formuleo, conversions palette, guards, duality, arqueo invariants | pytest + Fake repos (Fake-first per slice, `motoshop-app/api/tests/`) |
| Contract | journal φ-order, idempotency replay, heal job, stub adapter | pytest, InnoDB-only fixtures (`app_*` safe to create/drop) |
| Integration | full saves vs **real MySQL 5.0.45** local, fixture seeder/replayer (docs/hermes evidence data), desktop coexistence | pytest `-m integration`, run on-prem only; skipped on cloud/Render |
| Concurrency | contadores double-booking | threads hitting numbering engine + desktop-simulated lock holder; bounded 5 s lock wait assert |
| Frontend | pages/adapters | `npx vitest run` (frontfambus) |

## Data Flow

```
PWA/POS ──HTTPS──▶ local FastAPI (tunnel only for off-LAN)
  │  Idempotency-Key + JWT + X-Tenant
  │        erp/router → module_access + tenant ERP config
  ▼
erp_save_engine (φ0..φ4)
  ├─ app_idempotency / app_doc_journal / app_audit_log (InnoDB, app_writer)
  ├─ contadores (LOCK WINDOW) → legacy doc tables → detcuentas → detapago → exiprod (MyISAM)
  └─ DIAN queue worker (async, later) → adapter → respdocfele + app_dian_payloads
mysqldump ETL ─▶ include/exclude ─▶ bronze/gold (app_* out) ─▶ Render analytics (read-only)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `motoshop-app/api/src/motoshop_api/erp/` | Create | Package: `engine.py` (erp engine), `uow.py`, `conversions.py`, `numbering.py`, `journal.py`, `guards.py`, `auditoria.py`; per-slice `masters/`, `invoicing/`, `cash/`, `annulment/`, `dian/` each with router.py, schemas.py, repo.py (+ Fake) |
| `motoshop-app/api/src/motoshop_api/db/engine.py` | Modify | add `get_erp_engine()` (autocommit=False, latin1, pool 2+4) + `reset_erp_engine()` |
| `motoshop-app/api/src/motoshop_api/db/tables.py` | Modify | extend String-typed legacy Core tables (facventas, contadores, terceros, … per slice) |
| `motoshop-app/api/src/motoshop_api/main.py` | Modify | register erp routers under `/api` |
| `motoshop-app/api/src/motoshop_api/auth/module_access.py` | Modify | matrix entries per slice module/role |
| `motoshop-app/api/tenants.yaml` + `tenants.py` + config.py | Modify | per-tenant `erp:` block (enabled/empresa/policy/provider) |
| `infra/migrations/F8-001..005.sql`, `run_migrations.py` | Create | journal, idempotency, unique indexes, grants, DIAN audit; runner |
| `infra/dump_to_cloud.py` (ETL) | Modify | include/exclude dump policy |
| `motoshop-app/api/tests/test_erp_*.py` | Create | unit + contract + integration + concurrency |
| `../frontfambus/app/(authenticated)/{maestros/terceros, maestros/productos, pos, cxc/cobros, anulaciones, dian/consola}` | Create | Pages matching existing module matrix; SWR + server-validated roles; receipt print view under `pos/[numfven]/recibo` |

## Interfaces / Contracts

- `POST /api/erp/invoices` (+ `Idempotency-Key`) → `201 {numfven, prefven, totals, warnings[stockout]}`; `GET /api/erp/invoices/{num}/receipt` → P80 ticket payload incl. DPI QR placeholder.
- `POST /api/erp/terceros|productos`, `PATCH /{id}`; masters reject transaction-owned fields (`exiprod`, cost).
- `POST /api/erp/receipts`, `/cash/arqueo`, `/cash/egresos`, `/bank/consignments`; `POST /api/erp/documents/{codclas}/{num}/annulment` `{reason}`.
- `POST /api/erp/dian/queue`, `GET /api/erp/dian/status` — console retrievals.
- Errors: `401/403(roles|module|tenant)/409(dup|annulled|period|DIAN-blocked)/422(validation|window|mismatch)/503(retryable)`.
- `ErpDocument` dataclass + journal envelope `{codclas, pref, docnum, status, tenant, actor, empresa}`.

## Testing Strategy

See ADR-0008-09 matrix — every requirement scenario maps to a named pytest/vitest test inside its
slice; strict tests-first.

## Migration / Rollout

Additive F8 migrations, hand-run runner. Feature gate per slice = module matrix flag (no deploy to
disable). Rollback: stop slice routers + flip matrix → re-annul posted docs via slice-5 flow
(never delete). `app_*` droppable; legacy tables never ALTERed destructively. Latin1 engine is
additive (new engine, existing read engine untouched) — Render deployment unaffected (503 policy
intact; new routers MySQL-dependent and degrade on cloud).

## Open Questions

- None blocking. Noted assumption: legacy derived-amount rounding = half-up to 2 decimals —
  must be confirmed by slice-3 parity tests against formuleo SQL evidence; if evidence shows
  truncation, conversions palette adjusts (test-visible, non-structural).
