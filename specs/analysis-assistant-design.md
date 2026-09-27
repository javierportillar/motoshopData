# Feature: Explain the Analysis Dashboard

## Requirements (EARS)

- When an authorized user asks about one or more Analysis sections, the assistant shall retrieve the canonical dashboard metrics for the selected tenant and date range.
- When the user requests a full Analysis overview, the assistant shall summarize Balance, Products, Suppliers, Peak Hours, Operating Expenses, and Monthly Projection in one bounded response.
- When operating-expense data cannot be read, the assistant shall mark net profit as unavailable and shall not describe missing expenses as zero.
- When inventory or sales data has a cutoff, the assistant shall include the cutoff and identify incomplete periods.
- When the monthly forecast has fewer than four valid backtest months or a median absolute percentage error above 30%, the assistant shall label its confidence low.
- When the assistant reports purchase value ratios, Pareto, or forecast revenue, it shall not describe those measures as SKU-level physical rotation or SKU demand unless the corresponding per-SKU data supports that claim.
- When a quantity report contains different units of measure, the assistant shall keep totals separated by unit.
- While a user is authenticated, the system shall authorize Analysis context retrieval using the existing `analisis` module for both MotoShop and MasVital.
- The system shall keep per-SKU forecasting and other forecast-only routes behind the existing `forecast` permission.

## Architecture

### Frontend
- Keep the six existing Analysis tabs as the source of visible calculations.
- Make the monthly sales-projection tab available to users with `analisis`; retain access for users with `forecast`.
- Display the forecast backtest sample size, median absolute error, and calibrated confidence explanation.

### Backend
- Add one bounded `get_analisis_modulo` assistant tool that composes existing `DuckDBMetricsRepo` methods for Balance, Products, Suppliers, Peak Hours/Heatmap, and Monthly Projection.
- Query Supabase expenses once per request. Return `available`, `available_empty`, or `unavailable`; only `available_empty` means no expenses were recorded.
- Reuse the canonical 90-day complete-window revenue forecast. Calibrate confidence from non-zero actual backtest months and return the accuracy statistics with the forecast.
- Preserve tenant-specific inventory handling already used by purchase analysis: MotoShop uses its Gold inventory snapshot; MasVital uses validated `silver_dim_producto.existencia`.
- Bound product and supplier rows and reduce daily/heatmap series to summaries so the tool response fits the assistant context.

### Security
- The analysis tool is scoped to the authenticated request's tenant and is exposed only when the caller has the `analisis` domain.
- Tool date filters are parsed as dates and all database queries remain parameterized.
- No raw credentials, SQL errors, or unscoped Supabase data are returned.
- If expenses are unavailable, the response carries an explicit partial/data-quality status and suppresses net-profit claims.

## Acceptance Criteria

1. Given a MotoShop or MasVital user authorized for `analisis`, when they ask for the whole Analysis module, then the assistant returns the six sections using that tenant's data and includes separate sales, purchase, expense, and inventory cutoffs.
2. Given Supabase has no expense rows for the selected range, when Balance is explained, then operating expenses are reported as zero with a successful/empty source status.
3. Given Supabase is unconfigured or unreachable, when Balance is explained, then net profit is marked unavailable and is not copied from gross profit.
4. Given a tenant has fewer than four valid forecast backtest months or median absolute error above 30%, when projection is explained, then confidence is low and the sample/error are shown.
5. Given a caller has `analisis` but not `forecast`, when they open Analysis, then the monthly Projection tab and endpoint are accessible while per-SKU forecast routes remain unavailable.
6. Given a caller lacks `analisis`, when they invoke the assistant Analysis tool, then the tool is not exposed and cannot be invoked.
7. Given both tenants return data with different units of measure, when quantities are summarized, then no cross-unit total is presented.

## Failure Handling

| Condition | Behavior |
|---|---|
| Tenant has no sales rows | Return an empty section with source freshness; do not infer forecast demand. |
| Expense service unavailable | Mark expenses and net profit unavailable; retain revenue, cost, and gross profit. |
| Backtest sample too small | Confidence low; state insufficient validation history. |
| Forecast endpoint unavailable | Return other Analysis sections with partial status and the forecast failure recorded. |
| One dashboard section errors | Preserve other sections and identify the failed section rather than failing the whole request. |

## Implementation Plan

- [x] Run baseline backend and frontend tests for Analysis and forecast.
- [x] Implement the consolidated assistant Analysis tool with per-section metadata and expense availability state.
- [x] Calibrate forecast confidence from backtest error and add response-schema fields.
- [x] Allow Analysis users to see the monthly projection tab/endpoint without enabling forecast-only endpoints.
- [x] Update assistant instructions to explain units, ratios, periods, and failure states.
- [x] Add backend unit/integration and frontend permission/render tests for both tenants.
- [ ] Verify tenant isolation and run production smoke tests for API and browser UI.
