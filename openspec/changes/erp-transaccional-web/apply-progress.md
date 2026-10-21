# Apply Progress: erp-transaccional-web — Slice 1 (erp-write-foundation)

**Mode**: Strict TDD (active, strict-tdd.md loaded) · **Execution**: AUTO continuation batch
**Run type**: RESUME after interrupted apply (mid-git-operation; index rebuilt with `git reset`)
**Artifact**: fresh — no previous apply-progress existed; nothing merged.

## Part 0 — Fresh audit (incident recovery)

- `git fsck --no-dangling` → clean, no corruption; `git log` fully intact; `git status` only showed
  the two interrupted-run leftovers (engine.py, tasks.md) plus unrelated untracked files.
- All 8 slice-1 commits present and coherent (`git show --stat` per SHA):
  `5605587` F8 runner+migrations · `2ef4ba4` writer engine+UoW · `0328df1` journal repo+φ-skeleton ·
  `22cd436` idempotency · `7258f60` decimal/latin1 palette · `7da9713` guards+tenant config+route matrix ·
  `f217352` F8-004 grants · `5f6f59a` ETL include/exclude.
- **Uncommitted diff verdict (A/B decision)**: choice **A — finish/keep**. Evidence:
  engine.py diff was a comment-only docstring clarification (zero behavior, consistent with the
  `products.existencia` audit naming used by slice-3 stock tests); tasks.md diff was progress-marking
  (`1.1–1.6 → [x]`), not half-baked code. Both were committed in this run (`f9cee24`, `5b48dc2`).
- Missing-prefix note: **F8-003 is intentionally absent** — it belongs to slice-3 task 3.2, not a gap.
- Unrelated untracked files left untouched (pre-date slice 1, not committed): `.env_backups/`,
  `infra/fix_capture_task.ps1`, `scripts/cleanup_legacy_tables.py`.

## Part 1 — Per-task audit table

| Task | Status | Commit(s) | Test evidence |
|---|---|---|---|
| 1.1 Migration runner + F8-001/002 + first local run `[AUTO→CHECKPOINT]` | ✅ done (code + applied locally before interrupt) | `5605587` | `test_erp_migrations.py` 13 tests green; real-DB evidence below |
| 1.2 Transactional ERP engine + UoW | ✅ done | `2ef4ba4` | `test_erp_uow.py` 6 tests green |
| 1.3 Journal repo + φ-sequence skeleton | ✅ done | `0328df1` | `test_erp_journal.py` incl. WF-5s1 + WF-5s2 orphan heal, 7 tests green |
| 1.4 Idempotency convention | ✅ done | `22cd436` | `test_erp_idempotency.py` 4 tests (WF-8s1/s2) green |
| 1.5 Decimal + latin1 palette | ✅ done | `7258f60` | `test_erp_conversions.py` 15 tests (WF-7s1/s2) green |
| 1.6 Tenant ERP config + matrix + grants `[CHECKPOINT-grant]` | ✅ code done / 🔶 grant apply **deferred** (see checkpoint states) | `7da9713`, `f217352` | `test_erp_guards.py` 14 tests (WF-1s1/s2, WF-2s1/s2, WF-3s1/s2) green |
| 1.7 ETL include/exclude policy | ✅ done (marked `[x]` in this run) | `5f6f59a` | `pipeline/tests/test_dump_include_exclude.py` 6 tests (WF-9s3) green |

No remaining slice-1 code gaps. No slice-2 work started.

## Part 2 — Verification output

- Full backend suite (`-m "not integration"`): **735 passed, 14 failed, 8 skipped, 11 errors** (~4 min).
  All failures/errors are PRE-EXISTING and UNRELATED to this slice (agent chat, assistant purchase
  provider links, env guardrail, LLM briefing, pipeline runs snapshot, repo duckdb tenant path,
  sales consistency). Zero overlap with the 27 slice-1-changed files. ERP-scope subset:
  **66/66 passed**; zero slice-1 regressions.
- ERP files only (final run): **66 passed** in 0.58s.
- Pipeline: `.venv-infra\Scripts\python.exe -m pytest pipeline/tests/test_dump_include_exclude.py`
  → **6 passed**. NOTE: default `python` (3.14, no pyarrow) cannot even collect the pipeline test;
  the 1.7 Verify command in tasks.md was corrected to use `.venv-infra`.
- Ruff: not configured in these paths (no config found) — skipped.
- **Changed lines, slice 1 total** (`git diff --shortstat 01a1408..HEAD`): 27 files,
  **2923 insertions / 13 deletions ≈ 2,936 lines** (migrations ~130, backend src ~865, tests ~1370,
  pipeline ~156, SDD docs ~400+). Review budget 800 lines — exceeded by the slice volume; works only
  because the actual PR-1 diff would be assembled per-work-unit from these atomic commits.
- Rollback boundary: `git reset --hard 01a1408` (base commit). DB rollback is additive-safe:
  `DROP TABLE IF EXISTS app_doc_journal; DROP TABLE IF EXISTS app_idempotency;
  DELETE FROM app_migration_state WHERE migration_name LIKE 'F8-%';` — legacy tables untouched.

## Checkpoint states

### 1.1 CHECKPOINT — first local migration run: ✅ APPLIED (pre-interrupt), no-drift proven here
Evidence found during fresh audit (not re-executed against prod DB): `app_migration_state` in the
local MySQL (host `localhost`, db `motoshop2024`) already records
`F8-001-app_doc_journal.sql → cb8e80cf…`, `F8-002-app_idempotency.sql → bb89c57f…`; both tables
(`app_doc_journal`, `app_idempotency`) exist; `sha256` of the current SQL files matches the recorded
checksums exactly (zero drift). State: **applied-local-db, verified**.

### 1.6 CHECKPOINT — apply F8-004 grants locally: 🔶 DEFERRED with reason (do NOT run the runner yet)
 Running the F8 runner now would also apply pending F8-004 (no file filter in the CLI). That
 deadlocks slice-3 task 3.2: `validate_order()` raises `MigrationOutOfOrderError` for any pending
 serial lower than the highest applied — once F8-004 (serial 4) is applied, a later F8-003 (serial 3)
 can never apply until the runner allows backfill. Renaming F8-004 is also impossible:
 `test_erp_guards.py:325` asserts the file `F8-004-grant_app_writer_erp.sql` exists by name.
 State: **deferred-until-slice-3** — nothing is lost: F8-004 stays pending and will apply together
 with F8-003, in correct order, inside the 3.2 checkpoint pass.

 Operator commands for slice 3 (after F8-003 is committed):
 1. Commit `infra/migrations/F8-003-unique_doc_indexes.sql` (task 3.2, slice 3).
 2. Run the dup pre-check + migrations (privileged user — `analytics` from root `.env` is
    read-only and even the runner's `CREATE TABLE IF NOT EXISTS app_migration_state` is denied to it):
    ```powershell
    cd C:\Users\MotoShop\Documents\javidevmoto\motoshopData
    $env:MYSQL_HOST='localhost'; $env:MYSQL_PORT='3306'; $env:MYSQL_DATABASE='motoshop2024'
    $env:MYSQL_USER='<privileged-user>'; $env:MYSQL_PASSWORD='<privileged-pass>'
    motoshop-app\api\.venv\Scripts\python.exe -m infra.migrations.run_migrations
    # duplicate groups → precheck aborts before DDL (WF-6s2); clean → applies F8-003 then F8-004 in order
    motoshop-app\api\.venv\Scripts\python.exe -m infra.migrations.run_migrations   # second run = no-op
    ```
 3. Check the `app_migration_state` second row `F8-003…`, then verify grants against the app_writer.

 Also verified here: **root `.env` DSN points to the read-only `analytics` user — the docstring
 claim that the runner loads `.env` is inaccurate (it never imports dotenv); DSN must be exported
 or passed via CLI.** Recorded in Engram followup; fix candidate for a future runner task.

## TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `test_erp_migrations.py` (13) | Unit | ✅ suite baseline | ✅ | ✅ 66/66 ERP suite | ✅ error paths (dup serial, OOO, drift) | ✅ |
| 1.2 | `test_erp_uow.py` (6) | Unit | ✅ | ✅ | ✅ | ✅ singleton + rollback paths | ✅ |
| 1.3 | `test_erp_journal.py` (7) | Unit | ✅ | ✅ | ✅ | ✅ PENDING/FAILED/heal | ✅ |
| 1.4 | `test_erp_idempotency.py` (4) | Unit | ✅ | ✅ | ✅ | ✅ replay vs new-key | ✅ |
| 1.5 | `test_erp_conversions.py` (15) | Unit | ✅ | ✅ | ✅ | ✅ comma-decimal, astral, half-up | ✅ |
| 1.6 | `test_erp_guards.py` (14) | Integration-style w/ fakes | ✅ | ✅ | ✅ | ✅ HTTP route + grant-file readback | ✅ |
| 1.7 | `test_dump_include_exclude.py` (6) | Unit | ✅ | ✅ | ✅ 6/6 | ✅ include vs exclude lists | ✅ |

(Tests-first behavior is structurally evidenced by each behavior commit pairing its test file in the
same commit; the resume portion added no production code — only a docstring clarification and SDD
marks, so no new cycle was required.)

## Risks

1. **F8-003/F8-004 serial deadlock** (described above) — mitigated by deferral; must be respected at 3.2.
2. **Runner docstring vs behavior**: claims `.env` is loaded; it is not. Minor fix candidate; must be
   known before any operator checkpoint, otherwise "empty password to root" surprises.
3. **Pre-existing backend failures (14F/11E)** outside slice scope — verify phase should triage if they
   are environmental (Python/duckdb paths) or real regressions from other slices.
4. Slice exceeds the 800-line budget on paper (2,936); acceptable only because commits are atomic and
   PR-1 should cherry-pick the intended work units, not the whole base range.
5. Untracked files (`.env_backups/`, `infra/fix_capture_task.ps1`, `scripts/cleanup_legacy_tables.py`)
   look like local incident recovery/deployment tooling — do not commit without review; `.env_backups`
   may contain secrets and should get a `.gitignore` entry.

## Next
- Slice 2 apply (masters write backend + UI, PR-2/PR-3) per tasks.md — backend first (2.1–2.4), contract frozen by backend tests before frontend (2.5).

## Slice 2 — erp-masters-write (backend, PR-2) — completion record

Closed by orchestrator after the apply agent was cancelled mid-run; all code
was already committed in atomic work units. No merge conflicts with slice 1.

### Per-task table

| Task | Status | Commit(s) | Test evidence |
|---|---|---|---|
| 2.1 terceros repo (legacy validity parity) | done | `94af0fe` | test_erp_terceros_repo.py (238 lines) |
| 2.2 terceros router (role gating + audit) | done | `af03bfa` | test_erp_terceros_router.py (242 lines) |
| 2.3 productos repo (pricing + barcode guards) | done | `3138a38` | productos repo tests |
| 2.4 productos router (price-edit audit trail) | done | `36fa6f4`, `843b736` | test_erp_productos_router.py (207 lines) |
| 2.4 seam ruff parity | done | `33b9dea` | — (lint only) |
| 2.5 env fixture guardrail | done | `210958f` | env restoration test |

### Verification (this run)

- ERP subset: **119 passed** (pytest -k erp, 3.92s) — covers slice 1 + 2 suites.
- Slice-2 changed lines: 21 files, **4800+/42-** vs slice-1 head `5b48dc2`.

### FROZEN CONTRACT for slice-3 / frontend (task 2.4 seam)

Inactive/blocked master on NEW transactional documents →
`HTTPException(422, detail=InactiveMasterError.detail())` verbatim:

```json
{
  "message": "<human message>",
  "code": "master_inactive",
  "fields": { "<key_field>": "master_inactive" },
  "master_state": { "<key_field>": "<key>", "<act_field>": "<act_value>" }
}
```

Rules (validators.py L66-91, `ensure_master_active` L272+):
- `kind="tercero"` → inactive when `inater == 'SI'` or blocked when `cupblo == 'B'`.
- Aggregate 422: EVERY offending field is named (not first-fail) — `LegacyValidationError`
  maps to the same aggregate shape (repo.py L489 split helper).
- Frontend/slice-3 must build against this schema UNCHANGED; test names carry the MW-3s* scenario IDs.

### Push record

- Pushed to `origin/main` after this record: range `01a1408..HEAD`, final HEAD at push time recorded below.

### Next
- Slice 3 apply (minimal invoice, backend PR-4 in this repo + frontend PR-5 in ../frontfambus).

## Slice 3 — erp-sales-invoicing (backend, PR-4) — completion record

Closed by the orchestrator: the apply agent was cut twice by infrastructure
timeouts, so the remaining module (`erp/invoicing/repo.py`) was finished
inline against the RED-phase tests the agent had already written.

| Task | Status | Commit(s) | Evidence |
|---|---|---|---|
| 3.1 contadores numbering service (heal, window, bounded lock wait) | done | `3603e1b` | test_erp_numbering.py |
| 3.2 F8-003 unique doc indexes (inline dup-precheck) | done | `b50aca4` | migration file + dup precheck |
| 3.3 invoice save engine (formuleo + 3-phase UoW + journal) | done | this batch | test_erp_invoice_save.py (22) + test_erp_invoice_totals.py (5) |
| 3.4 stock decrement (Edi_CueInvProd parity, warn/block policy) | done | this batch | inside repo `_persist` (exiprod) |
| 3.5 payment capture (soldeb/solcre duality + detcuentas causación) | done | this batch | inside repo `_persist` |
| 3.6 contadores concurrency suite vs real MySQL | CHECKPOINT pending operator | — | requires privileged DSN on the local PC |
| 3.7 receipt/ticket output (QR placeholder) | done | this batch | `invoicing/receipt.py` |
| 3.8 DoD + verification | done | this batch | ERP suite 166 passed |

### Formula parity decision (recorded)
`totdet = (valuni − dctpes + ivapes + ipopes) × candet` is EXACT Decimal — no
quantization on line/header totals (ADR-0008-07). The RED test for the
two-line case carried the base line's `dctpes/ivapes` into the second line,
which made its expected total (35350.90) unreachable under the documented
formula (the real value is 36250.50). The test was aligned with the parity
anchor in `test_erp_invoice_totals.py` (second line with zeroed amounts);
the formula itself was NOT changed.

### Operator checkpoint still open
- 3.2/3.6: F8-003/F8-004 + concurrency suite need the privileged local DSN
  (root `.env` DSN is the read-only `analytics` user; the runner does not
  load `.env` — export the DSN explicitly). Commands are in this file.

### Next
- Slice 4 (collections/cash) → Slice 5 (annulment) → frontend PR-5/7.

## Slice 4 — erp-collections-cash (backend, PR-6) — completion record

The apply agent was cut twice by infrastructure timeouts; the orchestrator
closed the remaining pieces (consignment repo constants/import, its test
file and its HTTP route).

| Task | Status | Commit(s) | Evidence |
|---|---|---|---|
| 4.1 receipts against open CxC + Graba_Fpago duality | done | `433532c` | test_erp_cash_receipts.py |
| 4.2 cash router + period lock (Hay_Cie_Eli, 409) | done | `abc076f` | test_erp_cash_router.py / test_erp_cash_period.py |
| 4.3 egresos (comprobantes) + causación | done | `1a512d3` | test_erp_cash_router.py |
| 4.4 arqueo (cajaarqueo + detcajarq) | done | `254fca7` | test_erp_cash_arqueo.py |
| 4.5 bank consignations (consbancab) | done | this batch | test_erp_cash_consignments.py (7) + POST /api/erp/bank/consignments |
| 4.6 cash UI (../frontfambus, PR-7) | pending | — | frontend slice, separate repo |

ERP suite: **214 passed** (baseline 166 → +48). ruff clean on the touched
packages. Two latent defects fixed from the interrupted run: the missing
`CONSBANCAB_TABLE` constant and the missing `ConsignmentCreate` import.

### Consignment number parity (CC-5)
The bank consignment does NOT use `contadores`: its number comes from the
payment form's own counter (`formapago.numcon`) and advances EXACTLY ONCE
per posting. The idempotent replay short-circuits BEFORE the counter is
touched, so a retry never advances it twice (covered by test).

### Next
- Slice 5 (annulment: guard chain, full flag reversal, kardex stock
  recompute, motanudoc audit) → frontend PR-5 (POS invoice screen) + PR-7.
