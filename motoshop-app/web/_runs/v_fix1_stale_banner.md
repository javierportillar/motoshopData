# F4-FIX1-B — StaleDataBanner: E2E test

Fecha: 2026-05-30  
Test: Verificar que StaleDataBanner se muestra cuando lag > 24h y se oculta cuando está fresco  
Resultado: ✅ **PASS — 4/4 tests OK**

## Contexto

R10 requería que el usuario sepa cuando los datos están desactualizados.
`StaleDataBanner.tsx` consume `GET /api/health/data-freshness` cada 5 min:

- `lag_hours > 24` (STALE/CRITICAL): banner amarillo "Predicciones basadas en datos de hace Xh"
- `lag_hours <= 24` (OK/WARN): banner oculto
- Error de red: banner rojo "No se pudo verificar frescura de datos"

## Casos verificados

| # | Escenario | Resultado esperado | Resultado |
|---|-----------|-------------------|:---------:|
| 1 | 48h lag → /forecast | Banner visible "hace 2d" | ✅ |
| 2 | 48h lag → /alerts | Banner visible "hace 2d" | ✅ |
| 3 | 2h lag (fresco) → /forecast | Banner oculto | ✅ |
| 4 | Health endpoint caído | Banner error visible | ✅ |

## Cómo ejecutar

```bash
cd motoshop-app/web
npx playwright test tests/stale-banner.spec.ts
```

## Evidencia cruda

```json
{
  "timestamp": "2026-05-30",
  "test": "F4-FIX1-B — StaleDataBanner E2E",
  "status": "PASS",
  "cases": [
    {"case": "forecast stale 48h", "expected": "banner visible hace 2d", "result": "PASS"},
    {"case": "alerts stale 48h", "expected": "banner visible hace 2d", "result": "PASS"},
    {"case": "fresh 2h", "expected": "no banner", "result": "PASS"},
    {"case": "health error", "expected": "banner error", "result": "PASS"}
  ]
}
```
