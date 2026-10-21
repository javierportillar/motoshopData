# Proposal: erp-transaccional-web — Transactional Web ERP on Legacy MySQL

## Intent

MotoShop's web PWA is read-only analytics; billing, collections, cash and annulments still
run only on desktop sgHermes (WinForms + MySQL 5.0.45 MyISAM). We need transactional web
operations that share ONE ledger with the running desktop system — not a forked data store.
Exploration confirmed a sanctioned write path already exists (ADR-0004 `app_*` InnoDB tables,
`app_writer` user, idempotency + audit patterns) and that the transactional core is fully
reverse-engineered with file:line evidence (`docs/hermes/modules.md`, `code_analysis.md`).

## Scope

### In Scope
- Write-foundation hardening: real `BEGIN/COMMIT` unit-of-work, InnoDB `app_doc_journal`
  write-ahead intent table, per-table GRANT script (F5-003 pattern), migration runner for
  `infra/migrations/`, unique doc-number indexes on legacy doc tables.
- Masters write: `terceros`(+`tercecorreo`), `productos`(+`prodcodbars`, `produndmeds`,
  `preciosxpro`/`listapre`) with `BotGuarMa` validity rules (code_analysis §10).
- Minimal sales invoice (POS-like): contadores numbering engine (`LOCK TABLES` + unique
  index + `Bus_Con_Act` heal), `facventas`+`detfventas` with totals formula (§4), `detapago`
  payments (§5.3), causación to `detcuentas` (§5.4), stock movement (`exiprod`), browser
  PDF/P80 receipt.
- Collections & cash: receipts, minimal arqueo (`cajaarqueo`+`detcajarq`), egresos
  (`comprobantes`), `consbancab`.
- Annulment with full reversal (§7): `Veri_Anul`, `Hay_Cie_Eli` (`cierresper` guard),
  `motanudoc` audit, flag flips, stock recalc from `detcuentas`, server-side permission +
  mandatory reason.
- DIAN e-invoicing foundation: `provetecno` config, `respdocfele` persistence,
  `app_dian_payloads` audit, async send queue with retries; provider adapter behind an
  interface (stub until account exists).
- ETL include/exclude policy so `app_*` tables never pollute gold KPIs.

**Scope type**: backend-mostly (motoshopData, local on-prem API), cross-repository UI work
in `../frontfambus` (separate git repo, separate PRs). Platform-wide, affects tenant
`motoshop` first; `masvital` transactional enablement is a design-phase decision.

### Out of Scope (non-goals)
- Desktop Hermes replacement / full UI parity.
- Restaurant/hotel modules (`PedHabTarR2`, `mesas`, domiciles).
- Payroll e-invoicing (`nominas`/`detnomiele` DIAN).
- Purchases/receptions module (S18) — deferred follow-up change.
- Migrating legacy tables off MyISAM or upgrading MySQL.

## Approach (decision recommendation)

**Continue Option B**: operate directly on legacy MySQL via InnoDB `app_*` write tables
(ADR-0004), transactional API served by the Windows on-prem API through the existing
Cloudflare tunnel; Render stays read-only analytics (503 degradation policy unchanged).

**Sub-decision — legacy table reuse vs `erp_*` shadow: REUSE legacy tables for the core
ledger + InnoDB `app_*` companions.** Rationale:
1. `contadores` must remain the single numbering source either way (desktop keeps running),
   so a shadow ledger does not remove the shared-writer problem — it only adds a mirror.
2. `detcuentas` IS the company's book and the kardex source (modules §5/§6). Shadow + nightly
   mirror = dual-ledger divergence risk against an actively-running desktop.
3. The real gap is MyISAM non-transactionality, not schema typing. Mitigate with: InnoDB
   `app_doc_journal` (write-ahead intent per document), fixed write order, UNIQUE indexes on
   legacy doc tables (MyISAM supports them), `Bus_Con_Act`-style heal + nightly consistency
   check (SUM `detcuentas` vs doc totals, `exiprod` audit) instead of a mirror job.
4. latin1/varchar-numerics handled at the Pydantic boundary (existing `db/tables.py`
   String-typing pattern). Final call confirmed in design phase + new ADR.

## Slices (work units; strict TDD — tests first in every slice)

| # | Slice | Goal / Deliverables | Tests required | Deploy gate | Est. lines |
|---|---|---|---|---|---|
| 1 | Write foundation | UoW helper (`BEGIN/COMMIT`), `app_doc_journal` migration, GRANT script, migration runner, idempotency convention | pytest unit + Fake twin for UoW; journal replay test | Migration applied locally; module matrix entry; Render untouched | ~140 |
| 2 | Masters write | terceros/productos CRUD repos+routers, validity rules, minimal UI pages | pytest repo/router (Fake first), vitest form tests | Local API + frontfambus deploy; role-gated via matrix | ~200 |
| 3 | Sales invoice minimal | numbering engine, invoice save (facventas/detfventas/detapago/detcuentas), stock move, receipt render, POS page | pytest totals formula + causación + concurrency test on contadores; vitest POS page | End-to-end invoice on LAN; tunnel smoke test; printed receipt | ~280 |
| 4 | Collections & cash | receipts (soldeb/solcre duality), arqueo minimal, egresos, consbancab | pytest duality + arqueo totals; vitest cash UI | Cash desk pilot with parallel desktop run | ~160 |
| 5 | Annulment & reversal | `Veri_Anul`/`Hay_Cie_Eli` guards, `motanudoc`, flag flips, stock recalc, permission+reason | pytest full reversal parity vs §7; guard tests | Annulment drill on test docs before production use | ~150 |
| 6 | DIAN e-invoicing | provider adapter interface + stub, `respdocfele`, `app_dian_payloads`, retry queue, `estfele` edit-block | pytest queue/retry/idempotency; adapter contract tests | **Blocked on provider account**; ships stub + offline QR | ~120 |

Dependency edges: 1→2→3→(4,5)→6. Slices 4/5 partially parallelizable after 3.

## Capabilities

### New Capabilities
- `erp-write-foundation`: UoW, journal, grants, migration runner, idempotency.
- `erp-masters-write`: terceros/productos/prices write model + validity rules.
- `erp-sales-invoicing`: numbering, invoice save, causación, stock, receipt.
- `erp-collections-cash`: receipts, arqueo, egresos, bank consignments.
- `erp-document-annulment`: guarded annulment with full reversal + audit.
- `erp-dian-einvoicing`: provider adapter, CUFE/QR, send queue, edit-block.

### Modified Capabilities
- None (existing `multi-tenant-m1-backend` requirements unchanged; tenant→empresa mapping
  for transactional ops is a design-phase decision).

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `motoshop-app/api/src/motoshop_api/erp/` (new) | New | routers/repos/schemas per slice |
| `motoshop-app/api/src/motoshop_api/db/engine.py` | Modified | transactional (non-autocommit) writer engine |
| `infra/migrations/F8-*.sql` | New | app_doc_journal, unique indexes, grants |
| `auth/module_access.py` | Modified | new module entries per slice |
| `pipeline`/`infra/dump_to_cloud.py` | Modified | include/exclude dump policy |
| `../frontfambus` (separate repo) | New | masters, POS, cash, annulment UI |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Contadores double-booking desktop+web | High | serialized LOCK TABLES + unique index; server-side `numauto`/`Valid_NumFin` enforcement |
| MyISAM non-atomic multi-table save | High | InnoDB journal write-ahead + fixed order + heal/consistency job |
| PC-uptime SPOF while billing | High | LAN-local API (no tunnel for cashier), offline PWA queue, UPS, manual fallback |
| MySQL 5.0.45 antiques (latin1, varchar numerics) | High | charset strategy in design; Decimal at Pydantic boundary |
| DIAN provider account missing | High (schedule) | slice 6 stubbed; start onboarding now — not a blocker for 1–5 |
| ETL contamination of KPIs | Medium | dump include/exclude policy in slice 1 |

## Rollback Plan

All migrations additive (new `app_*` tables, new indexes — duplicates validated before
adding UNIQUE). Rollback per slice = disable module in `module_access` matrix (UI/API gate
off), stop the slice's routers, and — for posted documents — annul via slice-5 flow rather
than deleting. `app_*` tables droppable without touching desktop data. Legacy doc tables are
never ALTERed destructively.

## Dependencies

- DIAN e-invoicing provider account (Dataico or SoftProp) — **slice 6 blocked until
  acquired; schedule risk, not a blocker for slices 1–5**. Start onboarding before slice 5.
- Desktop Hermes remains the parallel system of record during pilots.

## Review Workload Forecast

- Estimated total changed lines: **~1,050** (backend ~700, frontend ~350) vs **800-line
  review budget** → over budget by ~30%.
- **Chained PRs recommended: Yes.** One PR per slice (each ≤ ~300 lines, within the 400-line
  per-PR guidance); slice 3 splits backend/frontend into two PRs across the two repos.
  Config `chained_pr_strategy: ask-always` — orchestrator to confirm chain before apply.
- **Decision needed before apply: Yes** (chained-PR confirmation + design-phase ADR on the
  legacy-vs-shadow sub-decision, per recommendation above).

## Success Criteria

- [ ] Invoice posted from PWA appears in desktop Hermes reports and `detcuentas` balance (one ledger).
- [ ] Zero duplicate document numbers under concurrent desktop+web saves (unique index proof).
- [ ] Every slice lands tests-first with green `pytest` (`motoshop-app/api`) and `npx vitest run`.
- [ ] Annulment restores stock, payments and accounting exactly (§7 parity test).
- [ ] Render analytics deployment unaffected (503 policy intact).

## Status

**ready-for-review** (pending chained-PR confirmation + design ADR on sub-decision).
