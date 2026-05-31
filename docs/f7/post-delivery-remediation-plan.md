# F7 Post-Delivery Remediation Plan

This document is the handoff plan for the dev team after the reviewer and security checks found that the delivered dashboard work is **not ready for stakeholder QA yet**.

## Current decision

**Status: NO-GO for stakeholder QA and authenticated production testing.**

The team must first close the build, mock-data, security, and production-verification blockers listed below.

## Why this is blocked

| Area | Finding | Impact |
|------|---------|--------|
| Frontend build | `npm run build` fails because `dashboards/dormidos/page.tsx` calls a React hook conditionally. | The current HEAD cannot be trusted as deployable. |
| Mock data | Sales and sellers still include mock/TODO production paths. | Stakeholder could see invented analytics as real data. |
| Credentials | API credentials are versioned/documented. | Public API has operational write endpoints, so credential leakage is a release blocker. |
| Authorization | `purchase-plans` allows insufficient ownership checks. | Users may read or update plans that do not belong to them. |
| Dependencies | Frontend audit reports high vulnerabilities around Next/PWA dependencies. | Production risk remains until patched or explicitly risk-accepted. |
| Production verification | Public routes redirect correctly, but authenticated content was not verified. | We cannot claim the latest delivery is working in production. |

## Gate order

The fixes must be completed in this order:

1. Make the frontend build green.
2. Remove production mock data or replace it with explicit empty/error states.
3. Close security blockers.
4. Fix remaining functional data-contract issues.
5. Verify Vercel/production with authenticated smoke evidence.
6. Run final QA checklist before stakeholder demo.

---

## Phase 0 — Freeze scope

**Owner:** Tech lead / reviewer

**Goal:** Prevent new feature work from hiding blocker fixes.

### Tasks

- Create or continue a dedicated remediation branch, for example `fix/dashboard-qa-blockers`.
- Do not add new dashboard features during this remediation.
- Keep each fix in a reviewable work-unit commit.
- Include verification evidence in the handoff for each phase.

### Acceptance criteria

- Only blocker-related files change.
- Each commit can be reviewed independently.
- The final handoff references the commands run and their results.

---

## Phase 1 — Fix frontend build blocker

**Owner:** Dev Frontend 1

**Primary file:** `app/(authenticated)/dashboards/dormidos/page.tsx`

### Problem

The page calls `useMemo` conditionally after early returns, which violates React hook rules and blocks `npm run build`.

### Tasks

- Move all hooks before conditional returns.
- Preserve current loading, error, empty, and table states.
- Verify sorting still works for purchase date and days without sale.

### Acceptance criteria

The following commands must pass from the frontend workspace:

```bash
npm run typecheck
npm run lint
npm run build
```

### Suggested commit

```text
fix(dormidos): resolve conditional hook build failure
```

---

## Phase 2 — Remove production mock data

**Owners:** Dev Frontend 2 + Dev Backend 1

### Problem

Some stakeholder-facing analytics still use mocks or TODO data paths.

### Frontend tasks

#### Sales

- Remove mock data from daily sales.
- Remove mock data from historical sales.
- Use real backend responses for daily, monthly, and historical tabs.
- If data is unavailable, show a clear empty/error state instead of fake values.

#### Sellers

- Remove mock data from historical view.
- Remove mock data from six-month view.
- Remove mock data from seller detail/modal.
- Use real backend responses or show a clear unavailable state.

### Backend tasks

Expose or validate real endpoints for:

- Daily sales.
- Monthly sales.
- Historical sales.
- Monthly sellers.
- Historical sellers.
- Seller detail.

### Acceptance criteria

- No `mock`, `fake`, or TODO placeholder data is used by production dashboard routes.
- Every number shown to the stakeholder can be traced to a real API response.
- Empty states are explicit and do not look like real analytics.

### Suggested commit

```text
fix(dashboards): replace production mock data with real API states
```

---

## Phase 3 — Close security blockers

**Owners:** Dev Backend 1 + Security/DevOps

### 3.1 Rotate and remove versioned credentials

**Files to inspect:**

- `motoshop-app/api/README.md`
- `motoshop-app/api/users.yaml`

#### Tasks

- Rotate all documented/shared API users.
- Remove real passwords from README and docs.
- Remove credential-bearing files from version control or replace them with safe examples.
- Rotate `JWT_SECRET` so old tokens are invalidated.
- Document where secrets now live: environment variables or secret manager, not the repo.

#### Acceptance criteria

- No real passwords or shared secrets remain in tracked files.
- Rotated credentials work for controlled QA accounts.
- Previously issued tokens no longer authenticate.

### 3.2 Enforce purchase plan authorization

**Primary file:** `motoshop-app/api/src/motoshop_api/purchase_plans/router.py`

#### Tasks

- In `GET /purchase-plans/{plan_id}`, enforce ownership for non-admin users.
- In `PATCH /purchase-plans/{plan_id}/status`, enforce owner/role rules.
- Return `403` for authenticated users without permission.
- Add authorization tests for horizontal privilege escalation.

#### Required tests

- Seller cannot read another user's plan.
- Seller cannot update another user's plan.
- Admin/manager behavior matches the business rule.

#### Suggested commit

```text
fix(security): enforce purchase plan ownership checks
```

### 3.3 Patch vulnerable frontend dependencies

#### Tasks

- Update Next.js to a patched compatible version.
- Review whether `next-pwa` should be upgraded, replaced, or temporarily disabled.
- Regenerate the lockfile.
- Re-run dependency audit and production build.

#### Acceptance criteria

```bash
npm audit --audit-level=high
npm run build
```

If any high vulnerability remains, document why it is not exploitable in this deployment and who accepted the risk.

#### Suggested commit

```text
fix(security): patch vulnerable frontend dependencies
```

---

## Phase 4 — Fix functional data-contract issues

**Owners:** Dev Frontend 1 + Dev Backend 1

### 4.1 Exact SKU detail routing

#### Problem

`/products/{sku}` can fail or resolve the wrong product if the frontend searches broadly and uses the first result.

#### Tasks

- Use an exact SKU endpoint or exact-match mode.
- Do not select `items[0]` from a broad search for product detail.
- Show different states for:
  - product exists with stock,
  - product exists without stock,
  - product does not exist.

#### Acceptance criteria

- Known alert SKUs open the correct product detail.
- Unknown SKUs show a truthful not-found state.
- Existing SKUs without stock do not appear as missing products.

### 4.2 Dormant products: all products over 90 days

#### Problem

The requirement is to list all products with more than 90 days without sales, not a silent fixed limit.

#### Backend tasks

- Add pagination fields: `page`, `page_size`, `total`, `items`.
- Support sorting by purchase date and days without sale.
- Return separate fields for last sale, last purchase, and days without sale.

#### Frontend tasks

- Show the total dormant-product count.
- Support pagination.
- Support sorting by purchase date and days without sale.
- Display last sale and last purchase as separate values.

#### Acceptance criteria

- The UI total matches the backend total.
- There is no silent `LIMIT 50` or `LIMIT 500` presented as complete data.
- Users can navigate through all dormant products.

### 4.3 Actions as recommended actions, not only history

#### Problem

The stakeholder expects actionable recommendations derived from alerts, demand, forecast, dormant products, and purchase planning.

#### Backend tasks

- Generate recommended actions by product and period.
- Include reason, priority, SKU, product name, period, and status.
- Return actions when actionable alerts exist.

#### Frontend tasks

- Show recommended action, SKU/product, reason, priority, period, and status.
- Keep action history separate from recommended actions if both exist.

#### Acceptance criteria

- If there are actionable alerts, the Actions page is not empty.
- Users can understand why each action is recommended.

---

## Phase 5 — Verify Vercel and production

**Owners:** Reviewer + DevOps/Frontend

### Tasks

- Confirm the deployed commit SHA in Vercel matches the reviewed commit.
- Verify production environment variables point to the correct API.
- Investigate proxy anomaly: `/api/metrics/sales-summary` should return `401` without auth or `200` with valid auth, not `404`.
- Run public smoke checks without credentials.
- Run authenticated smoke checks with rotated QA credentials.

### Public smoke checks

Expected behavior without auth:

- `/login` returns `200`.
- Protected dashboard routes redirect to login.
- New routes do not return `404`.

### Authenticated smoke checks

Verify these pages load real data or truthful empty states:

- Inicio.
- Sales.
- Inventory.
- ABC.
- Dormant products.
- Forecast.
- Alerts.
- Actions.
- Cohorts.
- Sellers.
- Drift.
- Purchase plan.

### Acceptance criteria

- Production serves the expected commit.
- No protected dashboard route returns `404` for authenticated users.
- API proxy behavior is consistent.
- Evidence is captured with screenshots, command output, or logs.

---

## Phase 6 — Final QA before stakeholder

**Owner:** Reviewer QA

### Required commands

Run the relevant commands from the correct frontend/backend workspaces:

```bash
npm run typecheck
npm run lint
npm run build
npm audit --audit-level=high
python3 -m pytest tests/test_metrics.py tests/test_alerts.py tests/test_forecast.py tests/test_purchase_plans.py
```

### Functional checklist

- [ ] Inicio KPIs navigate to real detail or historical views.
- [ ] Sales daily/monthly/historical views use real data or truthful empty states.
- [ ] Inventory warehouse names are correct and not collapsed into an unexplained `SIN NOMBRE 100%` bucket.
- [ ] ABC explains what A/B/C means and what decision it supports.
- [ ] Dormant products shows all `>90 days` items through pagination.
- [ ] Forecast explains whether horizons are cumulative or interval-based.
- [ ] Alerts show high, medium, and low when data exists.
- [ ] SKU links open exact product details.
- [ ] Actions show recommendations when actionable alerts exist.
- [ ] Cohorts explain missing months and small samples.
- [ ] Sellers include real monthly/historical/detail data.
- [ ] Drift explains metric, status, percentage, and recommended action.
- [ ] Purchase plan filters work for ABC, urgency, and dormant-only.

## Definition of done

The remediation is complete only when all of the following are true:

- Frontend build is green.
- Relevant backend tests are green.
- No production route uses fake analytics.
- Credential and authorization blockers are fixed.
- High dependency vulnerabilities are fixed or explicitly risk-accepted.
- Vercel production is verified with authenticated smoke evidence.
- Reviewer gives GO for stakeholder QA.
