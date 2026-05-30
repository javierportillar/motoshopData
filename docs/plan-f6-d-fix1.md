# Plan F6-D-FIX1 · Hot fix bugs en producción detectados post-cierre F6-D

- **Fecha apertura:** 2026-05-30 (Sesión 50)
- **Estado:** 🟡 ABIERTA
- **Origen:** humano hizo smoke test en `https://app.fragloesja.uk` tras cierre F6-D y encontró 3 bugs visibles desde la PWA.
- **Duración estimada:** Dev T 45-60 min · Dev A 30 min · Wall-clock ~1 h con paralelización.
- **Bloqueante para:** F7 (reestructuración UX no arranca hasta que los bugs operativos estén fixed) + entrega académica (no se puede defender con esos 3 errores visibles).

---

## 1 · Bugs detectados (con evidencia)

### Bug 1 · `/dashboards/dormidos` → 404

```
curl -L https://app.fragloesja.uk/dashboards/dormidos
→ HTTP 404 "This page could not be found"
```

**Causa raíz:** la ruta NO existe en el filesystem de Next.js App Router. Verificado:

```
ls motoshop-app/web/app/(authenticated)/dashboards/
→ abc/  inventario/  page.tsx  ventas/
```

Hay `abc/`, `inventario/`, `ventas/` pero falta `dormidos/`. El endpoint backend `/metrics/dormidos` sí responde 200 con datos reales.

### Bug 2 · Ticket promedio "$0.0M" con 911 facturas

**Causa raíz:** la API devuelve correctamente `ticket_promedio: 25813.95` (verificado). La PWA está formateando ese valor con sufijo **siempre `M`** (millones), entonces:
- `$25,813.95 / 1,000,000 = $0.025M` → se redondea a 1 decimal → `$0.0M`

Bug de UX en el formatter del frontend. Para valores < $1M debería usar `K` (miles) o el valor literal.

### Bug 3 · Valor inventario "$0.0M"

**Causa raíz:** la API devuelve literalmente `valor_total: 0.0` (verificado). La query SQL del `/metrics/inventory-summary` no está multiplicando `cantidad × costo`. Bug real del backend.

Respuesta actual:
```json
{
  "stock_total": 4024.0,
  "valor_total": 0.0,    ← BUG
  "num_productos": 4829,
  "por_bodega": [...]
}
```

Debería calcular `SUM(stock_actual × costo_promedio)` del mart de inventario.

---

## 2 · Scope y alcance

### Lo que SÍ entra en F6-D-FIX1

- **Bug 1:** crear página `/dashboards/dormidos` consumiendo `/metrics/dormidos` (frontend)
- **Bug 2:** refactor del formatter en `motoshop-app/web/lib/format.ts` (o equivalente) para escoger sufijo según magnitud:
  - `≥ $1M` → `1.2M`
  - `≥ $1K` → `1.2K` o `1,234`
  - `< $1K` → valor literal `$847`
- **Bug 3:** arreglar query inventory-summary en backend para incluir `cantidad × costo_promedio`

### Lo que NO entra

- Rediseño visual completo (eso es F7)
- Crear nuevos tableros (eso es F7)
- Mobile responsive deep refactor (eso es F7)
- Touch interactions / gestures (eso es F7)

---

## 3 · Sprint estructura

### Sprint F6-D-FIX1-A · Dev A · Backend bug 3 (~30 min)

**Paso A1 · Audit query (~10 min)**
- Leer `motoshop-app/api/src/motoshop_api/metrics/repo.py` función que sirve `inventory-summary`
- Identificar por qué `valor_total` devuelve 0.0 (probablemente la query no hace JOIN con costos o usa columna inexistente)
- Verificar mart `mart_inventario_actual` qué campos tiene: `stock_actual`, `costo_promedio`, `costo_ultimo`, etc.

**Paso A2 · Fix query (~15 min)**
- Ajustar query para calcular `SUM(stock_actual * COALESCE(costo_promedio, 0))`
- Si `mart_inventario_actual` no tiene `costo_promedio` directamente, hacer JOIN con `dim_producto` o mart con precios
- Verificar local con `pytest tests/api/test_metrics.py` (si existe)

**Paso A3 · Smoke test (~5 min)**
- Reiniciar API local
- `curl /metrics/inventory-summary` → `valor_total > 0`
- Documentar en `motoshop-app/api/_runs/v_fix_inventory_valor_<ts>.md`

**Commits:** `fix(F6-D-FIX1-A-backend): inventory-summary valor_total != 0 con cantidad*costo`

### Sprint F6-D-FIX1-B · Dev T · Frontend bugs 1 y 2 (~45-60 min)

**Paso B1 · Página `/dashboards/dormidos` (~25 min)**
- Crear `motoshop-app/web/app/(authenticated)/dashboards/dormidos/page.tsx`
- Consumir `GET /metrics/dormidos` con SWR
- Layout consistente con las otras 3 páginas (`ventas`, `inventario`, `abc`)
- Mostrar tabla de SKUs dormidos con: cod_producto, nom_producto, dias_sin_venta, stock_actual
- Indicador visual (color) por días dormidos: > 180d crítico, 90-180d alerta, < 90d normal

**Paso B2 · Refactor formatter (~20 min)**
- Buscar el formatter actual: `grep -rn "0\.\\d.M\|toFixed.*M\|/.*1000000" motoshop-app/web/lib/ motoshop-app/web/components/`
- Crear/refactorear `motoshop-app/web/lib/format/currency.ts`:
  ```ts
  export function formatMoney(value: number): string {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return `$${Math.round(value).toLocaleString('es-CO')}`;
  }
  ```
- Reemplazar uso en todas las páginas de dashboards
- Test unit: assertions para los 3 rangos

**Paso B3 · Smoke test PWA + deploy (~10 min)**
- `npm run dev` local → verificar las 4 páginas de dashboards
- Confirmar Bug 1: `/dashboards/dormidos` carga
- Confirmar Bug 2: ticket promedio muestra `$25.8K`, no `$0.0M`
- `npx vercel --prod` para redeploy
- Documentar en `motoshop-app/web/_runs/v_fix_dashboards_<ts>.md`

**Commits:** `fix(F6-D-FIX1-B-frontend): pagina dormidos + formatter K/M segun magnitud`

---

## 4 · V críticas

| ID | Verificación | Pass criterion | Owner |
|----|--------------|---------------|-------|
| **V-FIX1-1** | `/dashboards/dormidos` carga | HTTP 200 + lista de dormidos visible | Dev T |
| **V-FIX1-2** | Ticket promedio NO muestra "$0.0M" | UI muestra `$25.8K` o `$25,814` | Dev T |
| **V-FIX1-3** | Valor inventario > 0 | `GET /metrics/inventory-summary` retorna `valor_total > 0` | Dev A |
| **V-FIX1-4** | Otras páginas no regresionaron | `/dashboards/ventas`, `/abc`, `/inventario` siguen cargando | Dev T |
| **V-FIX1-5** | Render auto-deploy OK | `https://cloud-api.fragloesja.uk/metrics/inventory-summary` retorna `valor_total > 0` post-merge | Revisor |

**Gate de cierre F6-D-FIX1:** V-FIX1-1 a V-FIX1-5 PASS.

---

## 5 · Riesgos

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| R-FIX1-1 | `costo_promedio` no existe en mart inventario | Dev A revisa `dim_producto` o `mart_*` y usa el campo que sí tenga |
| R-FIX1-2 | Formatter refactor rompe tests existentes | Mantener export default + agregar la nueva función como named export |
| R-FIX1-3 | Página `dormidos` requiere fields que el endpoint no devuelve | Dev T extiende `/metrics/dormidos` o adapta la página |

---

## 6 · Handoffs

### 🤖 Dev A · Sprint F6-D-FIX1-A · Backend (~30 min)

```
Soy Dev A · Sprint F6-D-FIX1-A del proyecto MotoShop.

PRE-FLIGHT:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f6-d-fix1.md COMPLETO

MI MISIÓN:
Fix Bug 3: /metrics/inventory-summary devuelve valor_total = 0.0.
La query no está multiplicando cantidad × costo. Hay que arreglarla
para que retorne el valor monetario real del inventario.

ENTREGABLES:
1. Audit query en motoshop-app/api/src/motoshop_api/metrics/repo.py
2. Fix con SUM(stock_actual * COALESCE(costo_promedio, 0))
3. Verificar campo correcto en mart_inventario_actual (puede ser
   costo_promedio, ultimo_costo, costo, etc — usar lo que exista)
4. Tests pasan
5. Smoke test local: curl /metrics/inventory-summary → valor_total > 0
6. Evidencia en motoshop-app/api/_runs/v_fix_inventory_valor_<ts>.md

NO TOCO:
- motoshop-app/web/** (Dev T)
- notebooks/** (no aplica)
- infra/** (no aplica)

Commits: fix(F6-D-FIX1-A-backend): ...

ARRANQUE: Paso A1 (audit query). Si la columna costo no existe en
el mart, NO inventes — proponé en docs/lecciones o pedí intervención
humana para definir qué campo usar.
```

### 🤖 Dev T · Sprint F6-D-FIX1-B · Frontend (~45-60 min)

```
Soy Dev T · Sprint F6-D-FIX1-B del proyecto MotoShop.

PRE-FLIGHT:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f6-d-fix1.md COMPLETO
4. Leé motoshop-app/web/app/(authenticated)/dashboards/ventas/page.tsx
   como referencia de estructura

MI MISIÓN:
Fix Bug 1: crear página /dashboards/dormidos (404 hoy).
Fix Bug 2: refactor formatter para que NO muestre "$0.0M" para
valores < $1M. Usar sufijo K/M según magnitud.

ENTREGABLES:
1. motoshop-app/web/app/(authenticated)/dashboards/dormidos/page.tsx
   consumiendo GET /metrics/dormidos via SWR
2. Layout consistente con ventas/inventario/abc
3. motoshop-app/web/lib/format/currency.ts con formatMoney(value):
   - >=1M → "1.2M"
   - >=1K → "1.2K"
   - <1K → "$847" con thousand separator
4. Reemplazar formateo viejo en todas las pages de dashboards
5. Tests unit del formatter
6. Smoke local (npm run dev) + smoke producción (vercel --prod)
7. Evidencia en motoshop-app/web/_runs/v_fix_dashboards_<ts>.md

NO TOCO:
- motoshop-app/api/** (Dev A)
- infra/** (no aplica)

Commits: fix(F6-D-FIX1-B-frontend): ...

ARRANQUE: Paso B1 (página dormidos). Antes de tocar el formatter,
verificá que la página dormidos carga con datos. Después refactor
formatter.
```

---

## 7 · Cierre

Cuando Dev A y Dev T pushen final:

1. Revisor (yo) corre smoke test de las 5 V-FIX1
2. Si TODAS PASS → F6-D-FIX1 ✅ cerrado, abre F7
3. Si alguna FAIL → F6-D-FIX1-FIX2 corto

**No bloquea defensa académica si tarda.** Los bugs son visibles pero la PWA funciona en lo esencial. Sin embargo, los queremos arriba ANTES de F7 para no confundir scope.
