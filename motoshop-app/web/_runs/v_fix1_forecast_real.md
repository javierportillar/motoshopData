# F4-FIX1-B — Forecast: RealForecastRepo vs Databricks SQL

Fecha: 2026-05-30  
Test: Validar que `GET /api/forecast/{sku}` devuelve datos reales de `gold.forecast_demanda_sku`  
Resultado: ⏳ **PENDING — esperar a que Dev A complete Prophet**

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

| SKU | Fecha | SQL predicted_qty | PWA predicted_qty | Match |
|-----|-------|------------------:|------------------:|:-----:|
| ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Evidencia cruda

```json
{
  "timestamp": "",
  "test": "F4-FIX1-B — Forecast real data match",
  "status": "PENDING"
}
```
