# Feature: Assistant chat and inventory reconciliation

## Overview

Repair assistant reachability on desktop/mobile, answer ABC-A catalog-list questions
from the same paginated metrics source as the catalog, and make stock/FIFO claims
explicitly match the validated inventory and movement data.

## Requirements (EARS)

- While a user is on any authenticated route with `chat-ia` access, when they activate
  the floating assistant button, the application shall open a drawer without changing
  the route.
- While a user selects the `Asistente IA` navigation item, the application shall
  navigate to the full-page `/chat` experience.
- While the full-page chat or drawer is active, the application shall keep page-level
  scrolling disabled and allow scrolling only in the active message/history region.
- When a user focuses a chat composer on a mobile browser, the application shall keep
  the composer visible without disabling the user's ability to zoom the page.
- When a user explicitly requests products classified as ABC A, the assistant shall
  return a bounded, paginated catalog list using the same 180-day ABC/stock/action
  metrics as the catalog screen.
- When product analytics and product detail are queried for the same tenant, SKU,
  window, and source generation, the system shall return the same stock, units sold,
  velocity, days of stock, ABC state, and action.
- When a purchase or sale movement cannot be joined to one unique, non-canceled
  document header, the system shall exclude it from exact movement/FIFO calculations
  or report an explicit unreconciled quantity; it shall not claim a physical lot balance.

## Architecture

### Frontend

- Mount one `ChatDrawer` in the authenticated layout and control it through layout state.
- Change the floating launcher to an accessible button that opens the drawer; retain
  the navigation link to `/chat` for the dedicated page.
- Keep both experiences in viewport-constrained flex layouts with `min-h-0`, safe-area
  handling, body-scroll locking for the drawer, and a single message scroll owner.
- Replace ancestor-scrolling `scrollIntoView` behavior with scrolling the message region
  itself; preserve the user's reading position when they have scrolled away from the end.
- Set mobile composer text to at least 16 CSS px and account for `visualViewport` resize
  while the software keyboard is open. Do not set `user-scalable=no` or remove accessible
  zoom.

### Backend

- Add a deterministic catalog-list intent/tool that delegates to
  `DuckDBMetricsRepo.get_product_analytics(window_days=180, abc='A', page, page_size)`.
- Project only the fields required for the answer: SKU, name, ABC, stock, days of stock,
  velocity, state, action, and page/total/cutoff metadata. Bound page size to 50 and
  preserve tenant-specific database resolution.
- Route explicit ABC-list requests before replenishment and analysis-summary intents;
  keep those intents separate.
- Use the same valid-header rules for purchase/sales history used by metric aggregation
  and product movement details. Include snapshot/generation metadata in product analytics
  and detail responses so mismatches can be diagnosed.
- Keep FIFO explicitly estimated unless all source movements reconcile to canonical stock.
  If they do not, return an unassigned residual and suppress exact lot-level claims.

### Security

- Continue deriving tenant identity from the authenticated `TenantContext`; never accept
  a tenant/database path from model-generated tool arguments.
- Require assistant capability for the catalog's sales/inventory data and apply the same
  permission policy as the authenticated catalog route.
- Validate ABC enum, window, page, and page size server-side. Use the existing repository
  method with parameterized values instead of generating SQL from user text.
- Return only the whitelisted metrics needed in the assistant response; generate product
  links from structured references and revalidate them against the active tenant.

## Implementation Plan

1. Add baseline tests for page/document scroll, drawer lifecycle, focus/keyboard geometry,
   ABC intent routing, same-window metric parity, and invalid/canceled/duplicate movement
   identities.
2. Fix chat route layout and wire floating drawer versus full-page navigation.
3. Fix mobile composer sizing/visual viewport behavior without restricting user zoom.
4. Add the bounded ABC-A catalog tool, direct intent routing, pagination follow-ups, and
   tenant/module permission mapping.
5. Normalize movement header validation, expose stock/snapshot metadata, and make FIFO
   reconciliation failures visible rather than assigning unsupported lot truth.
6. Run frontend unit tests/typecheck/build, backend metrics/assistant tests, desktop and
   mobile Playwright flows, and manual iOS Safari keyboard verification.
7. Verify product-analytics/detail parity for a single tenant/SKU/window/snapshot before
   production rollout; deploy only after unexplained stock differences are resolved or
   explicitly labeled as source snapshots/cache skew.

## Acceptance Criteria

- Floating assistant button opens/closes a dialog without navigation; the navigation item
  continues to open `/chat`.
- On desktop, long histories do not scroll the document; history and messages scroll
  independently and sending a new message does not steal a manually scrolled position.
- On mobile/iOS, focus does not zoom the page, the composer stays above the keyboard, and
  neither the document nor background page scrolls while the drawer is open.
- A catalog ABC-A request returns only ABC A entries from the 180-day catalog window,
  with stock/action, total count, and explicit pagination; a replenish request still uses
  the replenishment shortlist.
- For one stable snapshot, catalog and detail report equal stock/units/days/state/action.
- Canceled/duplicate/orphan purchase and sale lines cannot create FIFO stock. Any
  stock-to-movement mismatch is reported as unassigned/estimated rather than falsely
  attributed to the latest purchase.
