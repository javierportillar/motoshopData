# F6-D-FIX1-B · Dev T · Frontend bugs

**Fecha:** 2026-05-30  
**Commit:** `1f77e0a`  
**Build:** ✅ 0 errores

## Bug 1 — `/dashboards/dormidos` → 404 → ✅ 200

**Antes:** `curl -L https://app.fragloesja.uk/dashboards/dormidos` → `HTTP 404`

**Fix:** Creada página `dashboards/dormidos/page.tsx` usando `useDormidos()` SWR hook.
- Layout consistente con `inventario/page.tsx`
- KPI cards: Total Dormidos + Críticos (>180d)
- Lista con color coding: rojo `>180d`, naranja `90-180d`, gris `<90d`
- Campos: cod_producto, nom_producto, dias_sin_venta, stock_actual

**Después:** `HTTP 200`

## Bug 2 — Ticket promedio `$0.0M` → ✅ `$25.8K`

**Antes:** `formatMoney(v / 1_000_000)` siempre → $25,814 / 1,000,000 = $0.0M

**Fix:** Creado `lib/format/currency.ts` con `formatMoney(value: number): string`:
- `>= $1M` → `$1.2M`
- `>= $1K` → `$1.2K`
- `< $1K` → `$847` (es-CO locale)

Reemplazados 7 lugares con definiciones locales duplicadas:
- `ventas/page.tsx`, `inventario/page.tsx`, `abc/page.tsx`, `dashboards/page.tsx`
- `TopList.tsx`, `SalesTrendChart.tsx`, `forecast/page.tsx` (no money, dejado)

**Verificación:** API retorna `ticket_promedio: 25813.95` → formateado como `$25.8K`

## Bug 3 — `valor_total: 0.0`

🔴 **Dev A task** — NO resuelto. Backend retorna `valor_total: 0.0`. El formatter ahora funciona correctamente pero el dato fuente es 0.
