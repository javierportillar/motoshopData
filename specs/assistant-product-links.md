# Assistant product links

## Goal

Make product names and SKUs mentioned by the assistant navigable to the existing product detail page, including products listed in prose or Markdown tables.

## Design

- The backend derives candidate product references only from structured results of product-related tools.
- Before returning a reference, it resolves the SKU against the active tenant's `silver_dim_producto` catalog and uses the canonical product name. It builds only the allowlisted `/dashboards/productos/{sku}` route and URL-encodes the SKU as one path segment.
- `QAChat` returns and persists references only when the assistant's answer actually mentions the SKU or its unique canonical name. Name uniqueness is checked against the active catalog, not only against products present in one answer; ambiguous footer references include the SKU.
- Numeric-only SKUs are linkable only when the canonical product name appears in the same line/cell, preventing an invoice amount or count from becoming a product link.
- Historical assistant messages without references are enriched read-only in batched catalog queries when fetched. Numeric-only SKU tokens require their canonical name in the same line/cell to avoid linking amounts or invoice numbers.
- The frontend turns validated SKU and unique-name mentions into links in paragraphs, lists, and Markdown table cells. Explicit Markdown links require a matching server-issued entity reference. Links show only for users authorized for Inventory; the product-detail page/API enforce that permission again.
- MasVital's product detail metrics use `silver_dim_producto.existencia`, the validated current-stock source used by purchase analysis, rather than estimating current stock from all-time purchases minus sales.

## Requirements

- When a product-related assistant tool returns a product that the final answer mentions, the system shall include a tenant-resolved product entity reference.
- When an assistant message contains a validated product reference, the frontend shall make unambiguous SKU and name mentions clickable in prose and tables.
- When a product name maps to multiple SKUs anywhere in the active catalog, the system shall link the SKU and disambiguate the reference chip with its code, but shall not arbitrarily link the ambiguous name.
- When the user lacks Inventory access, the assistant shall not expose a product link; direct navigation and product-detail API requests shall remain protected.
- When a stored assistant message predates product references, the message endpoint shall only add references after exact tenant-catalog SKU validation; it shall not modify stored message text.
- When the linked product is opened for MasVital, the product detail shall report current stock from `silver_dim_producto.existencia`.

## Acceptance criteria

1. Given the September purchase-audit response, when a user with Inventory access clicks `BONNAT001` or its unique product name, then the matching product detail page opens for the active tenant.
2. Given an answer containing product prose and a Markdown table, when it includes validated references, then SKU and unique-name mentions are clickable in both formats.
3. Given two SKUs share the same canonical name, when the answer mentions both, then each SKU links to its own detail and the shared name is not linked ambiguously.
4. Given a user without Inventory access or a product ID absent from that tenant's catalog, then no usable product link is returned or rendered.
5. Given an older stored assistant answer containing an exact valid SKU, when history is loaded, then the UI may link it without changing the persisted text; unknown SKU-looking tokens remain plain text.
6. Given a MasVital product detail request, when current stock is displayed, then it matches the catalog's validated `existencia` value.

## Verification checklist

- [x] Backend resolver, tool-result extraction, deterministic answer, latest-snapshot, and batched history enrichment tests.
- [x] Frontend prose/table, duplicate-name, unsafe-path, and authorization tests.
- [x] Playwright navigation test for both MotoShop and MasVital product details.
- [x] Backend and frontend targeted suites, typecheck, build, and E2E pass.
