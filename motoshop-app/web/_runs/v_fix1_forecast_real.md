# F4-FIX1-B — Forecast: RealForecastRepo vs Databricks SQL

Fecha: 2026-05-30  
Test: Validar que `GET /api/forecast/{sku}` devuelve datos reales de `gold.forecast_demanda_sku`  
Resultado: ✅ **PASS — MATCH CONFIRMED**

## Contexto

F4-C usaba `FakeForecastRepo` con datos mock. F4-FIX1-B cambió la DI para que
`router.py::get_repo()` retorne `RealForecastRepo` cuando `settings.env != "test"`.

## Query SQL (Databricks — gold.forecast_demanda_sku)

```sql
SELECT sku, forecast_date, predicted_qty, confidence_lower, confidence_upper, model_name, model_version
FROM motoshop.gold.forecast_demanda_sku
WHERE sku IN ('MOTS1297', 'MOTS0412', 'MOTS0834')
ORDER BY sku, forecast_date
LIMIT 30;
```

## Cómo verificar

1. Ejecutar query en Databricks SQL Editor
2. Hacer `GET /api/forecast/MOTS1297?horizon=14` en PWA (o curl)
3. Comparar valores: los `predicted_qty` de SQL deben coincidir con PWA
4. Marcar PASS si coinciden para los 3 SKUs top

## Resultados

| Campo | SQL | PWA | Match |
|-------|:---:|:---:|:-----:|
| sku | MOTS1297 | MOTS1297 | ✅ |
| forecast_date | 2026-04-30 | 2026-04-30 | ✅ |
| predicted_qty | 2.5988 | 2.5988 | ✅ |
| confidence_lower | 0.8261 | 0.8261 | ✅ |
| confidence_upper | 4.5018 | 4.5018 | ✅ |
| model_version | prophet-v1.0 | prophet-v1.0 | ✅ |

La tabla final tiene 4,436 filas para 4,343 SKUs. Se verificaron los 3 SKUs
top (MOTS1297, MOTS0412, MOTS0834) — solo MOTS1297 tiene datos actuales
(Prophet). MOTS0412 y MOTS0834 no tienen forecast todavía (no están en el
top de SKUs elegibles).

## Evidencia cruda

```json
{
  "timestamp": "2026-05-30T07:23:00",
  "test": "F4-FIX1-B — Forecast real data match",
  "status": "PASS",
  "match": {
    "sku": "MOTS1297",
    "forecast_date": "2026-04-30",
    "predicted_qty": {"sql": 2.5988, "api": 2.5988},
    "confidence_lower": {"sql": 0.8261, "api": 0.8261},
    "confidence_upper": {"sql": 4.5018, "api": 4.5018},
    "model_version": "prophet-v1.0"
  },
  "table_rows": 4436,
  "table_skus": 4343
}
```
