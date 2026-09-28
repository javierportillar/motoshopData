# Assistant: bounded custom business queries

## Goal and safety model

Answer the requested business question over its actual date range and measure, rather
than substituting the most recent day, the last 20 invoices, or a purchase audit.
The assistant already knows the authenticated tenant and its DuckDB datasets; users
should not need to provide table names as in a warehouse-ticket investigation.

Custom means selecting a supported business query plan—not generating arbitrary SQL.
Each tool has fixed tables/columns, parameterized filters, explicit metric/dimensions,
bounded periods/results, tenant-derived connections, and current source cutoffs.

## Supported query plans

| User intent | Query tool | Semantics |
|---|---|---|
| Top products for any month or exact date | `get_top_productos_periodo` | Valid sales headers joined to detail by date/class/document; rank by units unless revenue is explicitly requested; unit rankings are partitioned by catalog measure so grams are not compared with items; separate periods and keep ties |
| Top purchases by amount, optionally to a supplier | `get_top_compras_periodos` | Calendar-month ranking of valid, unique purchase invoices; accepts supplier name/NIT filter and discloses when the requested top is capped at 20 per month |
| Purchases made during a month, supplier and total | `get_compras_periodo` | Summary or bounded paginated invoice list with exact document identity and supplier/total |
| Zero-stock products to review for replenishment | `get_productos_para_reponer` | Latest inventory snapshot plus non-canceled sales window; only zero/negative stock with positive demand receives an indicative 45-day coverage reference |

## Period and conversation rules

- “Este mes” and “hoy/ayer” use the relevant source's last valid data cutoff, not the
  server clock or another domain's maximum date.
- A named month resolves to a full calendar range for any month/year, not a rolling
  30-day range. Exact dates stay exact; empty dates never fall back to the latest day.
- If a requested range extends past the valid source cutoff, return a partial or
  unverifiable status and state the verified-through date; do not report the missing
  portion as having no sales.
- A provider filter is retained in the purchase ranking/list query. A ranking without a
  period asks which month/year instead of silently using recent invoices.
- “Detalla esas compras” may reuse only the immediately preceding user's purchase-period
  request. Ranking limits/filters may carry forward for immediate corrections; a month
  negated in the correction is excluded. Unrelated intervening turns break inheritance.
- Missing data, stale/partial ranges and source failures are surfaced; the assistant
  does not invent facts or ask the user to guess suppliers already in the selected range.

## Data rules and limitations

- Sales and purchases exclude canceled headers and join detail by exact
  `(business_date, cod_clase, num_documento)` identity; duplicate exact headers are
  excluded from navigable invoice lists.
- Replenishment uses `silver_dim_producto` stock snapshot and sales valid through the
  sales cutoff. The reference is based on average units over the requested sales window;
  it is not an order and omits lead time, supplier minimums, open orders, seasonality and
  safety stock. Products with no positive recent sales are not recommended automatically.
- Product rankings by units are partitioned by catalog measure; unknown-measure SKUs are
  listed separately and are not compared to other products. Revenue rankings can compare
  across measures because every amount is denominated in the same currency.
- Entity links are generated from structured results and revalidated in the active
  tenant. Document labels retain date, class and number; totals never become links.

## Verification

- Exercise every Spanish calendar month, multi-month period requests, exact ISO/numeric/
  relative dates including ranking follow-ups, unrelated count follow-ups, revenue-vs-units
  ordering, ties, mixed/unknown measures, empty periods and partial-cutoff notes.
- Exercise supplier-partial/NIT filters, cancelled and duplicate invoices, full monthly
  list pagination, existence summaries, immediate detail follow-ups, and stale-context
  rejection after an unrelated question.
- Exercise replenishment with zero/nonzero/unknown stock, canceled and duplicate sales,
  no-demand SKUs, supplier attribution, tenant/module denial, and bounded coverage inputs.
- Verify backend envelope/tool/source/entity references, frontend links, unit tests,
  typecheck, production build and Playwright conversation flows.
