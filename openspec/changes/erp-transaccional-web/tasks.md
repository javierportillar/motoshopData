# Tasks: erp-transaccional-web — Transactional Web ERP on Legacy MySQL

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,050 (backend ~700 in motoshopData, frontend ~350 in ../frontfambus) |
| Review budget | 800 lines → **over budget by ~30%** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | auto-forecast — chained PRs confirmed direction; one PR per slice, cross-repo slices split into two PRs |
| Chain strategy | pending — stacked-to-main vs feature-branch-chain (user choice) |

```text
Decision needed before apply: Yes (chain strategy: stacked-to-main vs feature-branch-chain)
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

**Execution mode note**: apply runs in AUTO batches. Tasks tagged `[AUTO]` are batched hands-off. Tasks tagged `[CHECKPOINT]` touch the local MySQL (migrations, integration/concurrency suites, dup pre-checks) and pause for the operator.

### Suggested Work Units (PR map)

| PR | Slice | Repo | Scope | Est. lines |
|---|---|---|---|---|
| PR-1 | 1 | motoshopData | Write foundation (engine, journal, idempotency, grants, ETL policy) | ~140 |
| PR-2 | 2 | motoshopData | Masters write backend (terceros, productos) | ~140 |
| PR-3 | 2 | ../frontfambus | Masters UI pages | ~60 |
| PR-4 | 3 | motoshopData | Sales invoice backend (numbering, save engine, receipt API) | ~200 |
| PR-5 | 3 | ../frontfambus | POS page + receipt print view | ~80 |
| PR-6 | 4 | motoshopData | Collections & cash backend | ~110 |
| PR-7 | 4 | ../frontfambus | Collections & cash UI | ~50 |
| PR-8 | 5 | motoshopData | Annulment & reversal | ~150 |
| PR-9 | 6 | motoshopData | DIAN foundation backend (adapter, queue, gating) | ~90 |
| PR-10 | 6 | ../frontfambus | DIAN console UI | ~30 |

DAG: 1 → 2 → 3 → (4 ∥ 5) → 6. Cross-repo frontend PRs base on their backend PR being merged (API contract frozen by backend tests).

Requirement ID map: `WF`=erp-write-foundation, `MW`=erp-masters-write, `SI`=erp-sales-invoicing, `CC`=erp-collections-cash, `AN`=erp-document-annulment, `DI`=erp-dian-einvoicing (`R#s#` = requirement #, scenario #).

---

## Slice 1 — Write Foundation (PR-1, motoshopData, ~140 lines)

> Slice-0 note honored: F8 migrations run via `infra/migrations/run_migrations.py` on the local MySQL — task 1.1 executes the first local run with the dup pre-check behavior verified.

- [x] 1.1 `[AUTO→CHECKPOINT]` **Migration runner + F8-001/002 + first local run** `[WF-6s1, WF-5]`
  - RED: `motoshop-app/api/tests/test_erp_migrations.py` — runner applies each SQL file exactly once; second run is a no-op with recorded state in `app_migration_state`; out-of-order/missing file errors.
  - GREEN: `infra/migrations/run_migrations.py` (stdlib+pymysql), `infra/migrations/F8-001-app_doc_journal.sql`, `infra/migrations/F8-002-app_idempotency.sql` (InnoDB, utf8, TIMESTAMP defaults, F5 style).
  - CHECKPOINT: run against local MySQL — `motoshop-app\api\.venv\Scripts\python.exe -m infra.migrations.run_migrations` twice from repo root; assert second run no-op. Dup pre-check helper (scan target table for duplicates before any DDL) ships here and is exercised in 3.2.
  - Depends: none.

- [x] 1.2 `[AUTO]` **Transactional ERP engine + UoW** `[WF-4, WF-7]`
  - RED: `motoshop-app/api/tests/test_erp_uow.py` — Fake twin commits on success, rolls back on exception; engine kwargs assert `autocommit=False`, latin1 charset, pool 2+4, app_writer user.
  - GREEN: `motoshop-app/api/src/motoshop_api/db/engine.py` (+`get_erp_engine()`, `reset_erp_engine()`), `src/motoshop_api/erp/uow.py` (`erp_write_uow` context manager), `src/motoshop_api/erp/__init__.py`.
  - Verify: `motoshop-app\api\.venv\Scripts\python.exe -m pytest tests/test_erp_uow.py -m "not integration"` (cwd `motoshop-app/api`).
  - Depends: 1.1.

- [x] 1.3 `[AUTO]` **Journal repo + φ-sequence skeleton** `[WF-5s1, WF-4s1]`
  - RED: `motoshop-app/api/tests/test_erp_journal.py` (InnoDB contract fixtures) — PENDING row exists before any legacy insert; flips COMMITTED with final number; failure path → FAILED(error).
  - GREEN: `src/motoshop_api/erp/journal.py`, `src/motoshop_api/erp/engine.py` (φ0 precheck → φ1 journal → φ2 numbering hook → φ3 unit → φ4 commit skeleton).
  - Verify: pytest `tests/test_erp_journal.py -m "not integration"`.
  - Depends: 1.2.

- [x] 1.4 `[AUTO]` **Idempotency convention** `[WF-8s1, WF-8s2]`
  - RED: `motoshop-app/api/tests/test_erp_idempotency.py` — replay under same UUIDv4 key returns stored response, no counter advance, exactly one doc; new key → new document.
  - GREEN: `src/motoshop_api/erp/idempotency.py` (F5-001 pattern over `app_idempotency`), wire φ0 in `erp/engine.py`.
  - Verify: pytest `tests/test_erp_idempotency.py tests/test_erp_journal.py`.
  - Depends: 1.3.

- [x] 1.5 `[AUTO]` **Decimal + latin1 conversion palette** `[WF-7s1, WF-7s2]` (parallel with 1.3–1.4)
  - RED: `motoshop-app/api/tests/test_erp_conversions.py` — `19990.625` exact round-trip, no float drift; `"Bujía NGK Ñ-P"` latin1 round-trip without mojibake; comma-decimal legacy rows (`PuntX_Coma`); astral-plane codepoint rejected at Pydantic boundary; ROUND_HALF_UP quantize only for derived normalized amounts.
  - GREEN: `src/motoshop_api/erp/common/conversions.py` (`to_legacy_num`/`from_legacy_num`, ConstrainedDecimal money/qty types).
  - Verify: pytest `tests/test_erp_conversions.py`.
  - Depends: 1.2.

- [x] 1.6 `[AUTO]` **Tenant ERP config + module matrix + grants** `[WF-1s1, WF-1s2, WF-2s1, WF-2s2, WF-3s1, WF-3s2]`
  - RED: `motoshop-app/api/tests/test_erp_guards.py` — no JWT → 401 and zero row changes; vendedor annulment → 403; masvital write → 403 "tenant not enabled"; module-disabled → 403 explicit reason; matrix denies POST → 403 before business validation; tenant isolation on writes.
  - GREEN: `tenants.yaml`+`tenants.py`+`config.py` (`erp: {enabled, empresa, stock_negative_policy, dian_provider}`; masvital `enabled=false`), `src/motoshop_api/auth/module_access.py` (erp module entries, default off), `infra/migrations/F8-004-grant_app_writer_erp.sql` (F5-003 per-table pattern).
  - Verify: pytest `tests/test_erp_guards.py`; CHECKPOINT: apply F8-004 locally.
  - Depends: 1.2.

- [x] 1.7 `[AUTO]` **ETL include/exclude policy** `[WF-9s3]` (parallel)
  - RED: `pipeline/tests/test_dump_include_exclude.py` — `app_*` excluded from gold aggregates; legacy doc tables (`facventas`, `detcuentas`, …) included.
  - GREEN: `infra/dump_to_cloud.py` explicit include/exclude lists.
  - Verify: `.venv-infra\Scripts\python.exe -m pytest pipeline/tests/test_dump_include_exclude.py` (repo root — the default interpreter lacks the pipeline venv's pyarrow).
  - Depends: none.

**Slice 1 DoD**: journal-first φ-sequence saves against local MySQL; idempotent replay; masvital 403; F8-001/002/004 applied locally; ETL policy green; all new routers registered but matrix-gated OFF.
**Verification suite**: `motoshop-app\api\.venv\Scripts\python.exe -m pytest -m "not integration"` + `python -m pytest pipeline/tests/test_dump_include_exclude.py`.
**Deploy gate**: migrations applied locally; module matrix entry present but disabled; Render untouched (503 policy intact — new engine is additive).
**Rollback boundary**: drop `app_doc_journal`/`app_idempotency`; revert `db/engine.py` addition; legacy tables untouched.

---

## Slice 2 — Masters Write (PR-2 backend + PR-3 frontend, ~200 lines)

- [ ] 2.1 `[AUTO]` **Terceros repo + validity parity** `[MW-1s1, MW-1s2, MW-1s3]`
  - RED: `motoshop-app/api/tests/test_erp_terceros_repo.py` — create with one email → `terceros`+`tercecorreo` rows (MW-1s1); duplicate `nitter` → 409 field-identified, zero writes (MW-1s2); verification-digit checksum failure → 422 aggregate fields (MW-1s3).
  - GREEN: `src/motoshop_api/erp/masters/repo.py` (TercerosRepo + Fake), `schemas.py`.
  - Verify: pytest `tests/test_erp_terceros_repo.py -m "not integration"`.
  - Depends: 1.3, 1.5.

- [ ] 2.2 `[AUTO]` **Terceros router + role gate + audit** `[MW-5, MW-4]`
  - RED: `motoshop-app/api/tests/test_erp_terceros_router.py` — vendedor GET ok / POST-PATCH 403 (MW-5); audit row with before/after snapshot in `app_audit_log`, `motanudoc` NOT used (MW-4).
  - GREEN: `src/motoshop_api/erp/masters/router.py` (`POST/PATCH /api/erp/terceros`), `main.py` registration, matrix entries.
  - Verify: pytest `tests/test_erp_terceros_router.py`.
  - Depends: 2.1, 1.6.

- [ ] 2.3 `[AUTO]` **Productos repo (units, barcodes, prices)** `[MW-2s1, MW-2s2, MW-2s3, MW-3s1, MW-3s2]`
  - RED: `motoshop-app/api/tests/test_erp_productos_repo.py` — product+`produndmeds`(caja×12)+`preciosxpro` atomic all-or-none via journal (MW-2s1); barcode reuse → 409, no partial rows (MW-2s2); `pvsini`/`pvconi` inclusive↔exclusive ×(1+rate) server-side Decimal (MW-2s3); missing `codlin1` → 422 aggregate (MW-3s1); `exiprod` edit → 422 "stock moves through transactions" (MW-3s2).
  - GREEN: `src/motoshop_api/erp/masters/repo.py` (ProductosRepo + Fake), `schemas.py` extensions.
  - Verify: pytest `tests/test_erp_productos_repo.py`.
  - Depends: 2.1.

- [ ] 2.4 `[AUTO]` **Productos router + cross-slice inactive contract** `[MW-3s3, MW-4]`
  - RED: `motoshop-app/api/tests/test_erp_productos_router.py` — inactive `actprod='I'` product referenced by invoice line → 422 master-state (contract seam consumed later by 3.3); price edit 10000→12000 audit snapshot (MW-4).
  - GREEN: `erp/masters/router.py` productos endpoints.
  - Verify: pytest `tests/test_erp_productos_router.py`.
  - Depends: 2.3.

- [ ] 2.5 `[AUTO]` **Masters UI (../frontfambus — PR-3)** `[MW-1, MW-2, MW-5, MW-6]`
  - RED (vitest): `../frontfambus/app/(authenticated)/maestros/terceros/__tests__/terceros-form.test.tsx`, `../frontfambus/app/(authenticated)/maestros/productos/__tests__/productos-form.test.tsx` — required-field aggregate errors; write controls hidden for vendedor (MW-5 UI); SWR adapter posts to `/api/erp/terceros|productos` without client totals.
  - GREEN: `maestros/terceros/page.tsx`, `maestros/productos/page.tsx`, `lib/api/erp-masters.ts`.
  - Verify: `npx vitest run` (cwd `../frontfambus`).
  - Depends: 2.2, 2.4 (API contract).

**Slice 2 DoD**: masters CRUD live behind matrix (admin/gerente write, vendedor read); audit snapshots; atomic multi-table product save; desktop sees web rename immediately (single-statement writes, no locks beyond statement — MW-6 verified by 2.4 integration readback).
**Verification suite**: backend pytest full `-m "not integration"`; frontend `npx vitest run`.
**Deploy gate**: local API restart + frontfambus deploy; matrix flag per role.
**Rollback boundary**: matrix flag off → endpoints refuse; no legacy schema change.

---

## Slice 3 — Sales Invoice Minimal (PR-4 backend + PR-5 frontend, ~280 lines)

- [ ] 3.1 `[AUTO]` **Numbering engine (contadores)** `[SI-1s2, SI-2, SI-3]`
  - RED: `motoshop-app/api/tests/test_erp_numbering.py` — client-supplied number on `numauto` doc → 422, contadores untouched (SI-1s2); lagged counter healed to MAX+1 → assigns 502 (SI-2); window exhausted (`numfin` 500, next 501) → explicit resolver-range rejection, no increment (SI-3).
  - GREEN: `src/motoshop_api/erp/numbering.py` (LOCK TABLES contadores WRITE → Bus_Con_Act heal → Valid_NumFin → read conres → UPDATE conres+1 → UNLOCK; bounded 5 s lock wait).
  - Verify: pytest `tests/test_erp_numbering.py -m "not integration"`.
  - Depends: 1.3.

- [ ] 3.2 `[CHECKPOINT]` **F8-003 unique doc indexes + dup pre-check local run** `[WF-6s2, SI-1s1]`
  - RED: extend `tests/test_erp_migrations.py` — duplicate (prefix, number) pairs present → migration aborts BEFORE DDL, reports duplicate rows, no index created (WF-6s2).
  - GREEN: `infra/migrations/F8-003-unique_doc_indexes.sql` (UNIQUE on `(codclas-classified)(pref, numdoc)` per doc table).
  - CHECKPOINT: run on local MySQL (dup pre-check first); record state.
  - Depends: 1.1, 3.1.

- [ ] 3.3 `[AUTO]` **Invoice save engine — formuleo + pre-save validation** `[SI-5s1, SI-5s2, SI-6s1, SI-6s2, WF-4s2, WF-5s1]`
  - RED: `tests/test_erp_invoice_totals.py` — line `(10000.50 − 500.25 + 950.05 + 0) × 3 = 31350.90` exact (SI-5s1); header `totfven = subfven − totdct + totiva + totipo`; client-mismatch → 422 naming field, zero rows (SI-5s2). `tests/test_erp_invoice_save.py` — journal PENDING before first legacy insert (WF-5s1); injected failure between detail and payment insert → zero legacy rows, journal FAILED, 503 retryable (WF-4s2); credit-blocked `cupblo` client → 422 (SI-6s1); empty/negative invoice → 422, nothing reserved (SI-6s2).
  - GREEN: `src/motoshop_api/erp/invoicing/schemas.py`, `repo.py` (facventas→detfventas fixed order inside `erp_write_uow`), `engine.py` φ3 wiring.
  - Verify: pytest both files `-m "not integration"`.
  - Depends: 3.1, 1.4, 1.5, 2.4.

- [ ] 3.4 `[AUTO]` **Payments + causación + stock** `[SI-8s1, SI-8s2, SI-9s1, SI-9s2, SI-7s1, SI-7s2]`
  - RED: `tests/test_erp_invoice_payments.py` — cash 77 500 → one `detapago` row `valpag=77500.0, estado='B', soldeb=77500.0` (SI-8s1); mixed efectivo+transferencia Σvalpag=totfven exact, reference stored; mismatch → 422 (SI-8s2). `tests/test_erp_invoice_causacion.py` — balanced entries (line revenue `linea1.codcue`, IVA, inventory cost, caja per `formapago.codcue`), Σvaldeb=Σvalcre (SI-9s1); injected bad mapping → whole UoW fails, journal FAILED, no legacy rows (SI-9s2). `tests/test_erp_invoice_stock.py` — `exiprod` 10→7 (SI-7s1); backorder 5 vs 2 → posts, `-3`, per-line stockout warning per ADR-0008-02 warn policy (SI-7s2).
  - GREEN: `erp/invoicing/repo.py` (detapago, detcuentas, exiprod/ubiprodbod steps), `guards.py` (balance assertion).
  - Verify: pytest the three files.
  - Depends: 3.3.

- [ ] 3.5 `[AUTO]` **Invoice router + receipt endpoint** `[WF-8s1, SI-10s1, SI-10s2, WF-1]`
  - RED: `tests/test_erp_invoice_router.py` — `POST /api/erp/invoices` 201 `{numfven, prefven, totals, warnings[stockout]}`; Idempotency-Key replay identical, contadores advanced once (WF-8s1); `GET /api/erp/invoices/{num}/receipt` payload has header/resolution/lines/totals/payments + QR placeholder, render outside UoW (SI-10s1); accented product name mojibake-free (SI-10s2); vendedor may create, role matrix enforced (WF-1).
  - GREEN: `erp/invoicing/router.py`, `main.py` registration, matrix entries.
  - Verify: pytest `tests/test_erp_invoice_router.py`.
  - Depends: 3.4.

- [ ] 3.6 `[CHECKPOINT]` **Integration + contadores concurrency suite (on-prem only)** `[SI-1s1, SI-4s1, SI-4s2, WF-9s1, WF-9s2]`
  - RED: `tests/test_erp_integration_concurrency.py` (`-m integration`, skipped on cloud) — two concurrent web saves → distinct consecutive numbers, two doc rows (SI-1s1); desktop-simulated lock holder on contadores → web waits bounded window, posts next valid number, no duplicate lands (WF-9s2, SI-4s1); web-posted invoice visible in desktop-style day-sales readback indistinguishable from desktop posting (SI-4s2, WF-9s1 one-ledger).
  - GREEN: fixes only — no new production code expected.
  - CHECKPOINT verify: `motoshop-app\api\.venv\Scripts\python.exe -m pytest tests/test_erp_integration_concurrency.py -m integration` against local MySQL 5.0.45.
  - Depends: 3.2, 3.5.

- [ ] 3.7 `[AUTO]` **POS page (../frontfambus — PR-5)** `[SI-5, SI-6, SI-8]`
  - RED (vitest): `../frontfambus/app/(authenticated)/pos/__tests__/pos-page.test.tsx` — cart lines compute display totals client-side but NEVER send totals (server-authoritative, SI-5); payment editor enforces Σ=totfven before submit (SI-8); client inactive/credit-block errors surfaced (SI-6).
  - GREEN: `pos/page.tsx`, `lib/api/erp-invoicing.ts`, cart/payment components.
  - Verify: `npx vitest run`.
  - Depends: 3.5 (contract).

- [ ] 3.8 `[AUTO]` **Receipt print view (../frontfambus — PR-5)** `[SI-10]`
  - RED (vitest): `../frontfambus/app/(authenticated)/pos/[numfven]/recibo/__tests__/recibo.test.tsx` — P80 ticket layout renders payload lines/totals/payments; QR placeholder element present; accents render correctly.
  - GREEN: `pos/[numfven]/recibo/page.tsx` + print CSS.
  - Verify: `npx vitest run`.
  - Depends: 3.7.

**Slice 3 DoD**: end-to-end invoice on LAN from PWA → legacy tables; zero duplicate numbers under concurrency (unique index proof); receipt prints; tunnel smoke test passed.
**Verification suite**: backend pytest (unit+contract `-m "not integration"`, then `-m integration` on-prem); frontend `npx vitest run`.
**Deploy gate**: end-to-end invoice on LAN; tunnel smoke test; printed receipt verified.
**Rollback boundary**: stop invoicing router + matrix flag off; posted test docs annulled via slice-5 flow (never deleted); legacy tables never ALTERed destructively.

---

## Slice 4 — Collections & Cash (PR-6 backend + PR-7 frontend, ~160 lines)

- [ ] 4.1 `[AUTO]` **Receipts against open CxC + duality** `[CC-1s1..s4, CC-2s1, CC-2s2]`
  - RED: `tests/test_erp_receipts.py` — full payment 150 000 closes balance to 0, journal COMMITTED (CC-1s1); partial 100 000 of 300 000 → 200 000 (CC-1s2); overpay 60 000 vs 50 000 → 422 with remaining balance, no rows (CC-1s3); target `estfven='A'` → 409 (CC-1s4); S01 row `soldeb=40000.0, solcre=0` (CC-2s1); note-type tipclas rows carry `solcre`, `soldeb=0` (CC-2s2). Open balance = live `SUM(detcuentas.valdeb − valhab)`.
  - GREEN: `src/motoshop_api/erp/cash/repo.py` (ReceiptsRepo + Fake), `schemas.py`.
  - Verify: pytest `tests/test_erp_receipts.py -m "not integration"`.
  - Depends: 3.4 (detcuentas/detapago writers).

- [ ] 4.2 `[AUTO]` **Cash router + period lock at creation** `[CC-6, WF-1s3, WF-2s1]`
  - RED: `tests/test_erp_cash_period.py` — receipt dated 2025-01-15 inside `cierresper` P/M/A range → 409 period-lock, no ledger rows (CC-6). `tests/test_erp_cash_router.py` — gerente creates receipt, audit records actor+role+operation (WF-1s3); collections module disabled in matrix → 403 explicit reason (WF-2s1).
  - GREEN: `erp/cash/router.py` (`POST /api/erp/receipts`), `Hay_Cie_Eli` guard in `guards.py` shared with slice 5, matrix entries.
  - Verify: pytest both files.
  - Depends: 4.1, 1.6.

- [ ] 4.3 `[AUTO]` **Egresos (comprobantes)** `[CC-3]`
  - RED: `tests/test_erp_egresos.py` — egress 90 000 with expense concept → detcuentas 90 000 debit expense / 90 000 credit cash, balanced; `totegr` server-side.
  - GREEN: `erp/cash/repo.py` (egress path), router `POST /api/erp/cash/egresos`.
  - Verify: pytest `tests/test_erp_egresos.py`.
  - Depends: 4.2.

- [ ] 4.4 `[AUTO]` **Arqueo (cajaarqueo + detcajarq)** `[CC-4s1, CC-4s2]`
  - RED: `tests/test_erp_arqueo.py` — bills 300 000 + coins 12 500 → header `salcaj=312500.0`, tiparq 1/2 classes stored (CC-4s1); mismatched `salcaj` → 422 naming the difference, nothing persists (CC-4s2).
  - GREEN: `erp/cash/repo.py` arqueo path, router `POST /api/erp/cash/arqueo`.
  - Verify: pytest `tests/test_erp_arqueo.py`.
  - Depends: 4.2.

- [ ] 4.5 `[AUTO]` **Bank consignments (consbancab)** `[CC-5]`
  - RED: `tests/test_erp_consignments.py` — consignment 200 000 posts → one `consbancab` row, `formapago.numcon` advanced exactly once; same Idempotency-Key retry does NOT advance counter again (CC-5).
  - GREEN: `erp/cash/repo.py` consignment path (`tippag=2, afepag=22`), router `POST /api/erp/bank/consignments`.
  - Verify: pytest `tests/test_erp_consignments.py`.
  - Depends: 4.2.

- [ ] 4.6 `[AUTO]` **Cash UI (../frontfambus — PR-7)** `[CC-1, CC-4, CC-7]`
  - RED (vitest): `../frontfambus/app/(authenticated)/cxc/cobros/__tests__/cobros-page.test.tsx` — open balance display, overpay blocked client-side before submit (CC-1); arqueo form denomination-sum live check (CC-4).
  - GREEN: `cxc/cobros/page.tsx`, cash form components, `lib/api/erp-cash.ts`.
  - Verify: `npx vitest run`.
  - Depends: 4.2–4.5 (contract).

**Slice 4 DoD**: receipts/egresos/arqueo/consignments live; desktop+web receipts both counted exactly once in daily `SUM(detapago.valpag)` reconciliation (CC-7 — asserted in 4.2 integration readback).
**Verification suite**: backend pytest; frontend `npx vitest run`.
**Deploy gate**: cash desk pilot with parallel desktop run.
**Rollback boundary**: matrix flag off per cash module; annul posted docs via slice-5 flow.

---

## Slice 5 — Annulment & Reversal (PR-8, motoshopData, ~150 lines)

- [ ] 5.1 `[AUTO]` **Ordered guard chain** `[AN-1s1..s5]`
  - RED: `tests/test_erp_annulment_guards.py` — fail-fast legacy order: already annulled → 409, no `motanudoc` dup (AN-1s1); date in `cierresper` → 409 naming period (AN-1s2); `estfele` in {1,2} → 409 electronic block before any write (AN-1s3, seam for 6.4); empty reason → 422 (AN-1s4); vendedor → 403 regardless of state (AN-1s5).
  - GREEN: `src/motoshop_api/erp/annulment/guards.py` (`Veri_Anul` → `Hay_Cie_Eli` → `Valid_EdiDocele` → role → reason), `router.py` (`POST /api/erp/documents/{codclas}/{num}/annulment`).
  - Verify: pytest `tests/test_erp_annulment_guards.py`.
  - Depends: 4.2 (shared `Hay_Cie_Eli` guard).

- [ ] 5.2 `[AUTO]` **Full flag reversal in one UoW** `[AN-2s1, AN-2s2, AN-2s3]`
  - RED: `tests/test_erp_annulment_reversal.py` — annulled invoice flips `estfven`, every `detcuentas.estcue`, every `detapago.estado` to 'A' for that number only (AN-2s1); receipt flips payment + cartera entries (AN-2s2); `financiacion`/detfinancia-backed rows `estfin='A'` (AN-2s3).
  - GREEN: `erp/annulment/repo.py` (ordered flag flips inside `erp_write_uow`).
  - Verify: pytest `tests/test_erp_annulment_reversal.py`.
  - Depends: 5.1.

- [ ] 5.3 `[AUTO]` **Stock recompute from kardex** `[AN-3s1, AN-3s2]`
  - RED: `tests/test_erp_annulment_stock.py` — 10 → sale 3 → 7 → annul → `exiprod=10` AND equals recompute from `detcuentas` movements with annulled doc excluded (AN-3s1); recompute path == direct pre-sale record path for every touched product (AN-3s2) — `AcInv_Eli_Anul`/`Recal_Cat` parity.
  - GREEN: `erp/annulment/repo.py` recompute step after flag flips.
  - Verify: pytest `tests/test_erp_annulment_stock.py`.
  - Depends: 5.2.

- [ ] 5.4 `[AUTO→CHECKPOINT]` **motanudoc audit + journal mirror + idempotent replay + coexistence** `[AN-4s1, AN-4s2, AN-5s1]`
  - RED: `tests/test_erp_annulment_audit.py` — reason >800 chars stored truncated to 800, `tipo='A'`, actor (AN-4s1); retry under same Idempotency-Key → same outcome, exactly one `motanudoc` row (AN-4s2); journal row → ANNULLED. `tests/test_erp_annulment_integration.py` (`-m integration`) — web-posted then web-annulled invoice appears in desktop-style annulled query with `estfven='A'`, counter does NOT walk back (number stays occupied, never a Bus_Con_Act heal target) (AN-5s1).
  - GREEN: `erp/annulment/repo.py` audit+journal mirroring; router wiring complete.
  - CHECKPOINT verify: `-m integration` on local MySQL.
  - Depends: 5.3.

**Slice 5 DoD**: annulment drill on test docs passes full §7 parity (guards → flags → stock → audit → journal) before production use.
**Verification suite**: backend pytest (unit+contract + `-m integration` on-prem).
**Deploy gate**: annulment drill on test documents completed successfully.
**Rollback boundary**: matrix flag off; annulment is itself the rollback tool for slices 3–4 posted docs.

---

## Slice 6 — DIAN E-Invoicing (PR-9 backend + PR-10 frontend, ~120 lines)

- [ ] 6.1 `[AUTO]` **DianAdapter Protocol + stub** `[DI-1s1, DI-1s2]`
  - RED: `tests/test_erp_dian_adapter.py` — contract suite (build_payload→send→poll) passes against `DianStubAdapter` unchanged (DI-1s1); same suite parameterized proves any adapter swaps with zero caller changes (DI-1s2); deterministic pseudo-CUFE, simulated ACCEPT, marked non-fiscal.
  - GREEN: `src/motoshop_api/erp/dian/adapter.py` (Protocol + `DianStubAdapter`), feature flag `dian_provider: stub|dataico|softprop`.
  - Verify: pytest `tests/test_erp_dian_adapter.py`.
  - Depends: 3.5 (ErpDocument).

- [ ] 6.2 `[AUTO→CHECKPOINT]` **respdocfele + app_dian_payloads persistence (F8-005)** `[DI-2s1, DI-2s2]`
  - RED: `tests/test_erp_dian_persistence.py` — accepted send → exactly one `respdocfele` row (CUFE, QR, estfele) + raw request/response in `app_dian_payloads` (DI-2s1); retried send after transient failure → no second respdocfele row, no second accepted send (DI-2s2, CUFE idempotency).
  - GREEN: `infra/migrations/F8-005-dian_audit.sql` + config rows; `erp/dian/repo.py`.
  - CHECKPOINT: apply F8-005 locally.
  - Depends: 6.1.

- [ ] 6.3 `[AUTO]` **Async send queue with retries/backoff** `[DI-3s1, DI-3s2, DI-6s1]`
  - RED: `tests/test_erp_dian_queue.py` — transient error → growing-delay retries up to max attempts then durable FAILED with last error, invoice data untouched (DI-3s1); worker crash between send and persistence → restart re-drives to safe terminal state without double issue (DI-3s2); queue scans ONLY journal-origin=web docs — desktop `envfele='S'` invoice ignored untouched (DI-6s1).
  - GREEN: `erp/dian/queue.py` (APScheduler worker on local API only).
  - Verify: pytest `tests/test_erp_dian_queue.py`.
  - Depends: 6.2.

- [ ] 6.4 `[AUTO]` **estfele gating + receipt QR/CUFE** `[DI-4s1, DI-4s2, DI-5s1, DI-5s2]`
  - RED: `tests/test_erp_dian_gating.py` — `estfele=1` invoice annulment → rejected by electronica guard (consumes 5.1 seam, AN-1s3) (DI-4s1); stub/pending state → annulment succeeds and queue item marked CANCELLED without sending (DI-4s2). `tests/test_erp_dian_receipt.py` — accepted → receipt footer carries `https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=<CUFE>` (DI-5s1); pre-acceptance → labeled placeholder, no fake CUFE (DI-5s2).
  - GREEN: `erp/dian/gating.py` + receipt payload extension in `erp/invoicing/router.py`.
  - Verify: pytest both files.
  - Depends: 6.3, 5.1.

- [ ] 6.5 `[AUTO]` **DIAN console endpoints + UI (PR-9 + PR-10)** `[DI-2, DI-3]`
  - RED: `tests/test_erp_dian_router.py` — `POST /api/erp/dian/queue`, `GET /api/erp/dian/status` retrieval contract. Vitest: `../frontfambus/app/(authenticated)/dian/consola/__tests__/consola.test.tsx` — status list, retry action hidden for vendedor.
  - GREEN: `erp/dian/router.py`, `main.py` registration; `dian/consola/page.tsx`, `lib/api/erp-dian.ts`.
  - Verify: pytest + `npx vitest run`.
  - Depends: 6.4.

**Slice 6 DoD**: stub adapter ships with full contract suite; queue retries durable; estfele gating integrated with annulment; QR placeholder offline. **Provider account = external blocker for real adapter (schedule risk, not slice blocker).**
**Verification suite**: backend pytest; frontend `npx vitest run`.
**Deploy gate**: stub-only deploy allowed; real provider gated on account + onboarding.
**Rollback boundary**: matrix flag off; `app_dian_payloads`/`respdocfele` web rows droppable; desktop `contadores.envfele` sequences untouched.

---

## Review Workload Forecast (final)

| Slice | Est. lines | PR(s) | Budget check (≤ ~300/PR) |
|---|---|---|---|
| 1 Foundation | ~140 | PR-1 | OK |
| 2 Masters | ~200 (140+60) | PR-2, PR-3 | OK |
| 3 Invoice | ~280 (200+80) | PR-4, PR-5 | OK |
| 4 Cash | ~160 (110+50) | PR-6, PR-7 | OK |
| 5 Annulment | ~150 | PR-8 | OK |
| 6 DIAN | ~120 (90+30) | PR-9, PR-10 | OK |
| **Total** | **~1,050** | 10 PRs | vs 800 budget → **over ~30%** |

- Verdict: **over the 800-line review budget** → chained PRs mandatory; every individual PR stays ≤ ~200 lines (inside the 400-line per-PR guidance).
- Chained PRs recommended: Yes
- Decision needed before apply: Yes (chain strategy: stacked-to-main vs feature-branch-chain)
- Execution-mode note: apply runs in AUTO batches; `[CHECKPOINT]` tasks (1.1, 1.6-grant, 3.2, 3.6, 5.4-integration, 6.2) pause for local-MySQL operator action.
