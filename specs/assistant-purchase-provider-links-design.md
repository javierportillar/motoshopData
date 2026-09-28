# Assistant purchase and supplier links

## Goal

Make purchase documents and suppliers returned by the governed assistant navigable to tenant-scoped pages, and provide a dedicated supplier profile with actual purchase metrics and explicitly estimated sales/margin attribution.

## Requirements (EARS)

- While a user has Purchases access, when the assistant returns a verified purchase document, the system shall expose a link to the existing document page using the exact tenant, business date, document class, and document number.
- While a user has Purchases access, when the assistant returns a verified supplier with a NIT, the system shall expose a link to that supplier's profile, resolved within the active tenant.
- When an assistant message mentions a numeric document number, the system shall link it only when visible text identifies it as a document/invoice and resolves unambiguously to one document identity.
- When an assistant message mentions a supplier by name, the system shall link the name only if it is unique in the active tenant; a verified NIT may link independently.
- While an authorized user opens a supplier profile, the system shall show actual purchases and documents for a bounded date range, with pagination for document rows.
- While an authorized user is in Compras, when they search by supplier, product/SKU, or invoice number, the system shall return matching valid documents in the selected bounded date range with exact document identity and pagination.
- When an authorized user clicks any non-disclosure portion of a daily purchase-document header, the system shall navigate to that exact document's detail page.
- When the supplier profile shows sales or margin, the system shall label them as estimates attributed to the latest known supplier for each SKU, not as sales directly invoiced by that supplier.
- When a user lacks Purchases access, the system shall omit purchase/supplier entity references and reject direct page/API access.
- When stored assistant history is loaded, the system shall backfill a missing purchase/supplier reference only for assistant rows produced by an allowlisted purchase tool and only after resolving explicit document/NIT text against the active tenant; it shall not mutate stored text.

## Architecture

### Frontend

- Extend the governed assistant entity renderer with `purchase_document` and `supplier` references in the `purchases` domain.
- Validate purchase links against the existing route `/dashboards/compras/dia/{date}/documento/{documentNumber}?cod_clase={classCode}` and validate supplier links against `/dashboards/compras/proveedores/{nit}`.
- Add the supplier profile page; default to the most recent 12-month range, expose date filters, and paginate document history. Show loading, empty, invalid-NIT, and API-error states.
- Add a Compras search tab for supplier name/NIT, product name/SKU, and invoice number with a selectable bounded date range and paginated document results.
- Make the entire daily purchase-document header a link to its exact detail page; keep the expand/collapse control separate to avoid nested interactive elements.
- Keep actual purchase KPIs visually distinct from estimated revenue/margin. Display the attribution rule and selected range near the estimated metrics.
- Link each supplier document row to the existing exact purchase detail page.

### Backend

- Preserve `cod_clase` in purchase-tool results; a document identity is `(tenant_id, business_date, cod_clase, num_documento)`.
- Extract entity candidates only from structured results of known purchase tools (`get_ultima_compra`, `get_compras_recientes`, `buscar_compras_por_proveedor`, and `get_detalle_compra`). Match candidates to visible assistant text before returning them.
- Represent a purchase reference with the deterministic composite ID `business_date|cod_clase|num_documento`; construct the href from separately URL-encoded path/query components.
- Resolve documents and suppliers against the current tenant's purchase headers with parameterized SQL. Use canonical supplier names and mark names ambiguous when multiple NITs share them.
- Add an authenticated, rate-limited supplier-profile metrics endpoint scoped by tenant/NIT/date range, returning purchase aggregates, bounded paginated document rows, and estimated sales/margin using latest-valid-supplier-per-SKU attribution. Exclude canceled sales and expose cost coverage; never treat an unknown cost as zero.
- Add an authenticated, rate-limited `GET /api/metrics/compras-buscar` endpoint with parameterized literal search across invoice number, supplier name/NIT, and product code/name, bounded by date range and pagination.
- Exclude canceled purchase headers from supplier purchase aggregates. Keep document navigation identity-preserving; never resolve by document number alone.
- Revalidate references on idempotent responses and history reads. History backfill requires an explicit document/factura label and sufficient date/class/NIT context to disambiguate; otherwise no link is returned.

### Security and performance

- Enforce authentication and the existing `ventas-summary`/Purchases module server-side on both profile page data and API endpoint; frontend hiding is defense in depth only.
- Validate NIT length/character set, ISO date ranges, page and page-size bounds. Cap the maximum requested date window and use parameterized SQL.
- Restrict candidate extraction to structured purchase tools; reject arbitrary routes, malformed composite identities, canceled/missing records, cross-tenant IDs, and ambiguous matches.
- Limit supplier documents per response (default 20, hard maximum 100); return total count and next-page metadata. Aggregate product summaries server-side with a bounded top-N.
- Encode all dynamic path segments and render supplier/document labels as text, never as HTML.

## API contract

`GET /api/metrics/compras-proveedor-perfil?nit_proveedor={nit}&fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD&page=1&page_size=20`

Response groups:

- `proveedor`: canonical NIT and name.
- `periodo`: normalized start/end dates.
- `compras`: `total_compras`, `num_documentos`, `ticket_promedio`, first/last purchase, distinct SKUs, and top products.
- `ventas_estimadas`: `revenue`, `revenue_with_cost`, sales/cost-known line counts, `margen_cobertura_pct`, nullable `margen`/`margen_pct`, `skus_vendidos`, `skus_con_costo`, and a `metodo_atribucion` object with identifier/description.
- `documentos`: one page of exact `business_date`, `cod_clase`, `num_documento`, `total_factura`, and `num_items` identities.
- `paginacion`: current page, page size, total documents, and `has_more`.

`GET /api/metrics/compras-buscar?q={term}&fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD&page=1&page_size=20`

The search response returns the normalized query/range, bounded paginated document identities, supplier NIT/name, totals/item counts, match type, up to three matching product names, and pagination metadata. The query is treated as a literal substring, not a SQL/LIKE pattern.

Errors use the existing API conventions: 401 unauthenticated, 403 missing Purchases access, 404 unknown tenant supplier, 422 invalid search/NIT/date/page range, and 429 rate limit.

## Implementation plan

1. Preserve purchase identity fields in tool results and add backend purchase/supplier candidate extraction and tenant resolvers.
2. Add profile metrics query/response and endpoint with auth, validation, bounded date range, and pagination.
3. Add frontend exact route validation, prose/table mention linking, supplier profile page, and navigable document rows.
4. Add focused backend, Vitest, and Playwright coverage, including search criteria, ambiguity, numeric values, duplicate document numbers/classes, tenant isolation, access revocation, canceled purchase/sales rows, empty ranges, and estimated attribution labeling.
5. Run focused suites and production build; merge both repositories locally into `main` only after verification. Push/deploy only with separate authorization.
