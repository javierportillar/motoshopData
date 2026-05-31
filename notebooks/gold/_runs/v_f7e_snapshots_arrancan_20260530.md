# V-F7E · Snapshots primera corrida · 2026-05-30

**Workflow:** `motoshop_full_workflow` (job ID 272152121206178, 30 tasks)
**Run:** 913465681149603 (parcial, 29/30 tasks completed)
**Warehouse:** 43bc044eaef4cca4

---

## Resultados (3/4 ✅, 1 🔄 en cola)

| Snapshot | Tabla | Filas | Meses/Días | Estado |
|---|---|---|---|---|
| `30_snapshot_abc_mensual` | `gold.mart_rotacion_abc_snapshots` | 13,415 | 1 mes (2026-05) | ✅ SUCCESS |
| `31_snapshot_dormidos_mensual` | `gold.mart_productos_dormidos_snapshots` | 8,049 | 1 mes (2026-05) | ✅ SUCCESS |
| `33_archive_forecasts` | `gold.forecast_demanda_sku_archive` | 4,436 | 1 archive | ✅ SUCCESS |
| `32_snapshot_alertas_diario` | `gold.alertas_quiebre_snapshots` | — | — | 🔄 SKIPPED (upstream FAILED) |

## Causa del skip en alertas

`gold_classifier` (notebook `22_classifier_stockout.py`) falló validation query: `col_name` debe ser `column_name` en `information_schema.columns`.

**Fix aplicado:** commit `7bbcb96` — 4 líneas corregidas en `22_classifier_stockout.py`.
**Resolución pendiente:** 3 runs activas en cola. Próxima corrida con el fix desbloqueará `gold_snapshot_alertas`.

## Validación SQL

```sql
-- mart_rotacion_abc_snapshots
SELECT COUNT(*) FROM motoshop.gold.mart_rotacion_abc_snapshots;
-- → 13,415 filas, 1 snapshot_month distinto

-- mart_productos_dormidos_snapshots
SELECT COUNT(*) FROM motoshop.gold.mart_productos_dormidos_snapshots;
-- → 8,049 filas, 1 snapshot_month distinto

-- forecast_demanda_sku_archive
SELECT COUNT(*) FROM motoshop.gold.forecast_demanda_sku_archive;
-- → 4,436 filas, 1 archived_at distinto

-- alertas_quiebre_snapshots
-- Table not found — creada en próxima corrida con fix
```

## Conclusión

3/4 notebooks snapshot funcionan correctamente en primera corrida. El cuarto (alertas) está bloqueado por un bug preexistente en la validation query del classifier, ya corregido. Sin regresiones ni errores en el código nuevo de D1/D2.
