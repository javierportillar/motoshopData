# Customer directory and profiles

## Status

Proposed — planning only; implementation has not started.

## Overview

Add a first-class customer directory and customer profile pages to the sales application. The directory ranks identified customers by invoiced sales in a selected period and highlights the sum and share of the top 10; each profile shows the customer's most-purchased products and paginated invoice history. The feature reuses existing sales data, navigation, authentication, and visual patterns rather than introducing a separate CRM.

## Current-state findings

- The frontend has a `/cohortes` view and APIs for cohort retention/LTV, but no customer directory or customer profile API.
- `ToolExecutor.get_top_clientes` in `motoshop-app/api/src/motoshop_api/llm/tools.py` is an assistant-only aggregation. It ranks by invoice total and groups by both NIT and name; it is not a frontend data contract.
- `silver_fact_ventas` contains invoice-level customer identifiers, customer names, dates, totals, and document status. `silver_fact_ventas_detalle` contains product lines.
- Sales invoice detail joins header and lines using `(num_documento, cod_clase)`. Header totals must be aggregated separately from detail rows to avoid counting one invoice total once per line.
- Sales-day detail pages already exist at `/dashboards/ventas/dia/[date]`; product profiles exist at `/dashboards/productos/[sku]`.
- Frontend route access and backend API module access are maintained separately. Sales routes use `ventas-summary`; cohort analytics use the dedicated `cohortes` feature.

## Functional requirements (EARS)

### FR-CUS-001: Customer directory

While the user has access to `ventas-summary`, when they open `/dashboards/clientes`, the system shall show a paginated, searchable customer ranking for the selected date range.

### FR-CUS-002: Ranking definition

When the customer ranking is calculated, the system shall order identified customers by the sum of valid invoice totals in the selected date range, descending by default.

### FR-CUS-003: Top-10 aggregate

While a date range is selected, the system shall show the sum of valid invoice totals for the top 10 identified customers ranked by sales, plus their share of all valid sales in that range. The aggregate shall not change when the user changes the table page, text search, or table sort.

### FR-CUS-004: Customer identity

When customer invoices are aggregated, the system shall use the normalized non-empty customer identifier as the identity key and choose a deterministic non-empty display name; name variations shall not create duplicate customer rows.

### FR-CUS-005: Unidentified sales

When an invoice has no usable customer identifier, the system shall exclude it from customer profiles and identified-customer rankings while reporting its sales and invoice count separately from the identified-customer totals.

### FR-CUS-006: Customer profile

While the user has access to `ventas-summary`, when they open `/dashboards/clientes/{customer_id}`, the system shall show the customer's sales summary, top purchased products, and paginated invoice history for the selected range.

### FR-CUS-007: Product and invoice navigation

When a customer profile displays a product with a valid SKU, the system shall link the product name to `/dashboards/productos/{encoded_sku}`. When it displays an invoice, the system shall link to its existing sales-day detail route using that invoice's business date.

### FR-CUS-008: Link affordance

When a customer, product, or invoice is navigable, the system shall make its identifying text the link target and shall not make the entire row or card a navigation target.

### FR-CUS-009: Period continuity

When the user navigates from the directory to a customer profile and returns, the system shall preserve the selected date range and directory filters where practical.

### FR-CUS-010: Assistant references

When the governed assistant returns a verified customer identifier and the user has sales access, the system shall provide a customer-profile link validated against the canonical customer route; it shall not turn arbitrary Markdown destinations or unidentified-consumer records into customer links.

### FR-CUS-011: Authorization and tenant scope

When a request is unauthenticated, lacks `ventas-summary`, or uses a customer identifier outside the active tenant, the system shall reject the request and shall not return customer data.

### FR-CUS-012: Invoice eligibility

When sales are aggregated, the system shall apply the same valid-invoice status rules as the existing sales metrics and shall exclude canceled invoices.

## UX and route design

- Directory route: `/dashboards/clientes`.
- Profile route: `/dashboards/clientes/[id]`; treat the identifier as an opaque, encoded segment rather than assuming every customer has a numeric NIT.
- Add a **Clientes** navigation entry near **Proveedores**, visible only when `ventas-summary` is enabled. Reuse existing responsive sidebar/bottom-navigation behavior.
- Default the directory to the most recent 12 months. Provide shortcuts for 3 months, 12 months, current year, and all available history; make the selected range visible and carry it into the profile URL.
- Directory summary cards: identified customers, valid sales, invoice count, average ticket, Top-10 sales sum/share, and unidentified sales. Search by customer name or identifier; sort by sales (default), invoice count, average ticket, or last purchase.
- Directory rows/cards show customer name, identifier, sales, invoice count, average ticket, and last purchase. Only the customer name/identifier link navigates.
- Profile summary: canonical customer name/identifier, sales, invoice count, average ticket, first/last purchase, and selected period.
- Profile top-products list defaults to the top 10 by units and also shows units, sales value, and invoice count. A product name is the link; amounts and surrounding cards are not.
- Profile invoice history is paginated and links to `/dashboards/ventas/dia/[date]`. The initial implementation need not introduce a new per-invoice sales page.
- Keep `/cohortes` as the cohort-retention analysis and link to it where useful; do not duplicate its aggregate retention matrix in the customer profile.
- Loading, empty, no-match, invalid-profile, and retryable API-error states shall follow existing `Card`, `Skeleton`, and error-state patterns.

## API contract proposal

All endpoints are authenticated, tenant-scoped, rate-limited, and protected by the existing `ventas-summary` module.

### `GET /api/metrics/clientes`

Query parameters:

- `fecha_inicio`, `fecha_fin`: required normalized ISO dates after default resolution; bounded to available business history.
- `q`: optional literal search over normalized customer name and identifier.
- `page`, `page_size`: bounded pagination; default page size 20, maximum 100.
- `sort_by`: `ventas | facturas | ticket_promedio | ultima_compra`; default `ventas`.
- `sort_order`: `asc | desc`; default `desc`.

Response groups:

- `periodo`: normalized start/end dates.
- `resumen`: identified customer count, all valid sales, identified sales, invoice count, average ticket, Top-10 sales sum, Top-10 share of all valid sales, unidentified sales, and unidentified invoice count.
- `items`: customer identifier, canonical display name, sales total, invoice count, average ticket, first purchase, and last purchase.
- `paginacion`: page, page size, total rows, and total pages.

The Top-10 aggregate is calculated from the full identified-customer ranking for the selected date range. It is independent of `q`, page, and `sort_by`; the response shall make this meaning explicit in field names/documentation.

### `GET /api/metrics/clientes/{customer_id}/perfil`

Query parameters: `fecha_inicio`, `fecha_fin`.

Response groups:

- `cliente`: identifier and canonical display name.
- `resumen`: sales total, valid invoice count, average ticket, first/last purchase, and units sold.
- `productos_top`: bounded top 10, with SKU, product name, units, sales value, and distinct invoice count.
- `periodo`: normalized date range.

### `GET /api/metrics/clientes/{customer_id}/facturas`

Query parameters: `fecha_inicio`, `fecha_fin`, `page`, `page_size`.

Response groups: one page of invoice identities (`business_date`, `cod_clase`, `num_documento`), total, and line count, plus pagination metadata. The endpoint must not return an invoice from another tenant or customer.

## Data and query rules

- Use `nit_cliente` (or the source's stable customer identifier) as the grouping key. Trim whitespace and treat null/empty/sentinel values such as `SIN_ASIGNAR` as unidentified; do not create a profile for them.
- Select a deterministic canonical name from non-empty source names, preferring the latest valid invoice date and using a stable tie-breaker.
- Aggregate sales amount and invoice count from invoice headers after filtering by business date and valid document status.
- Aggregate customer product units/value from `silver_fact_ventas_detalle` joined to the selected customer's invoice identities on `(num_documento, cod_clase)` and date/tenant scope. Never sum header `total_factura` after joining one-to-many detail lines.
- Use parameterized SQL for all values, including search text; treat `%` and `_` in search as literal characters unless the existing repository has an established safe literal-search helper.
- Cache keys must include tenant, normalized date range, search/filter/sort/page parameters, and customer identifier as appropriate. Avoid placing raw customer identifiers in application logs.
- Start with bounded queries over existing silver tables; add a materialized aggregate only if representative production-volume performance measurements require it.

## Non-functional requirements

### Performance

- Bound the directory page to at most 100 customer rows and product summaries to 10 rows; invoice history is paginated.
- Target p95 response time below 2 seconds for directory and profile metrics on a representative production tenant. If this target is not met, evaluate a tenant-safe customer sales mart before broad rollout.
- Apply the existing metrics rate-limit convention (30 requests/minute unless measured workload requires a different limit).

### Security and privacy

- Require authenticated access and server-side `ventas-summary` authorization for pages and every new API endpoint; frontend visibility is not an authorization boundary.
- Scope all reads and caches to the active tenant. Reject malformed/overlong identifiers and date ranges before querying.
- Do not log customer names, identifiers, or raw search terms. Escape all customer/product labels as text; never render source data as HTML.
- Customer identifiers are opaque path data and must be encoded for links. Do not reuse supplier-specific NIT validation for customer identifiers.

### Accessibility and responsive behavior

- Use semantic links for navigation and buttons for controls; do not nest interactive controls or make a whole table row/card clickable.
- Provide accessible names for sort controls and pagination, visible keyboard focus, and equivalent information on mobile and desktop.

## Acceptance criteria

### AC-CUS-001: Top-10 revenue aggregate

Given valid sales invoices for identified customers in a selected period, when the directory loads, then the Top-10 sales sum equals the sum of the ten highest customer invoice totals and its share uses all valid sales in the period as the denominator.

### AC-CUS-002: Stable customer identity

Given invoices for one identifier with different spellings of the customer's name, when the directory is queried, then it returns one customer row with a deterministic display name and the combined valid invoice totals.

### AC-CUS-003: Avoid one-to-many double counting

Given one invoice containing multiple product lines, when the customer sales summary and top products are calculated, then the invoice total is counted once in sales while each product line contributes to its own units/value aggregation.

### AC-CUS-004: Unidentified invoices

Given invoices with null, empty, or sentinel customer identifiers, when the directory loads, then those invoices contribute to unidentified-sales KPIs but do not appear as customers or have profile links.

### AC-CUS-005: Search, sorting, and pagination

Given more customers than one page, when the user searches, sorts, and changes pages, then the displayed rows match the chosen query/order/page and the Top-10 aggregate remains unchanged for that date range.

### AC-CUS-006: Customer profile links

Given a valid customer profile, when its top products and invoice history render, then product names link to their encoded SKU routes, invoices link to their sales-day detail routes, and non-identifying row/card areas are not navigation links.

### AC-CUS-007: Period continuity

Given a selected directory range and search, when the user opens a customer profile and returns, then the selected range and applicable directory filters are preserved.

### AC-CUS-008: Authorization and tenant isolation

Given a user without `ventas-summary` or a customer identifier belonging to another tenant, when they call a directory/profile API or open a protected profile directly, then the request is rejected without returning customer data.

### AC-CUS-009: Loading and failure states

Given loading, empty, no-match, unknown-customer, or API-error conditions, when the corresponding screen renders, then it shows the matching accessible state and offers retry only for retryable errors.

### AC-CUS-010: Assistant link validation

Given an assistant customer reference with a verified identifier and sales access, when the message is rendered, then its link points only to the canonical encoded customer profile route; arbitrary internal Markdown paths and unidentified customers remain unlinked.

## Error handling

| Condition | API behavior | UI behavior |
|---|---|---|
| Unauthenticated request | `401` | Existing session-expired handling |
| Missing `ventas-summary` | `403` | Hide navigation entry and show the existing access-denied behavior for direct page access |
| Unknown customer in the active tenant | `404` | Profile not-found state with a link back to the directory |
| Invalid identifier, date range, page, or sort value | `422` | Keep user on the page and show an actionable validation message |
| Rate limited | `429` | Explain that the request can be retried shortly |
| Transient repository/API failure | `5xx` | Preserve filters and provide a retry action |
| No matching customers or no sales in the range | `200` with empty data | Show a descriptive empty state, not an error |

## Implementation plan

### Backend

- [ ] Add typed customer directory/profile/invoice response schemas and repository protocol methods.
- [ ] Implement repository queries for header aggregates, canonical customer name, customer product summary, and paginated invoices in both the DuckDB implementation and test/mock repository.
- [ ] Add authenticated `/api/metrics/clientes` endpoints with query validation, tenant-scoped cache keys, rate limiting, and `ventas-summary` module mapping.
- [ ] Align `get_top_clientes` semantics with the API (stable identifier grouping and unidentified customer treatment); reuse common query logic where the repository boundaries allow it.
- [ ] Add backend tests for duplicate names/IDs, one invoice with multiple lines, canceled invoices, missing identifiers, date boundaries, search literal escaping, pagination, unknown customers, tenant isolation, and authorization.

### Frontend

- [ ] Add typed hooks for the directory, profile, and invoice history.
- [ ] Add a customer route/link helper with bounded opaque-ID validation and URL encoding.
- [ ] Add `/dashboards/clientes` and `/dashboards/clientes/[id]` pages with period controls, search/sorting/pagination, summary KPIs, top products, invoice history, and loading/empty/error states.
- [ ] Add the Clientes navigation item and frontend `PATH_RULES` using `ventas-summary`.
- [ ] Preserve selected period/search when navigating between directory and profile.
- [ ] Link customer names in sales surfaces only when the backend provides a valid identifier; link product names and invoices to existing detail routes.
- [ ] Extend assistant reference generation/rendering to the verified customer entity only after canonical ID and access checks are available.
- [ ] Add Vitest coverage for route helper, gates, links, totals and UI states; add Playwright coverage for index → profile → product/invoice and responsive behavior.

### Verification and rollout

- [ ] Run focused backend tests, the complete backend suite, frontend unit tests, typecheck, and production build.
- [ ] Measure representative tenant query latency and verify tenant-specific cache isolation before rollout.
- [ ] Deploy backend API before or atomically with frontend routes so the new pages do not target missing endpoints.

## Out of scope

- Editing customer records, contact details, or CRM notes.
- Marketing campaigns, WhatsApp/email outreach, loyalty points, or customer consent management.
- Replacing or duplicating the `/cohortes` retention analysis.
- Creating a new per-invoice sales page; invoice links target the existing sales-day detail page.
- A database migration or materialized mart unless measured query performance requires it.

## Confirmed product decision

- “Best customers” means customers ranked by valid invoiced sales in the selected period, descending by default.
- The highlighted aggregate is the sum of sales for the top 10 identified customers; participation is measured against all valid sales in the period, including unidentified sales in the denominator.
