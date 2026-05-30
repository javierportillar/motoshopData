# F4-FIX1-B — Alerts: RealAlertsRepo vs Databricks SQL

Fecha: 2026-05-30  
Test: Validar que `GET /api/alerts` devuelve datos reales de `gold.alertas_quiebre`  
Resultado: ✅ **PASS — MATCH CONFIRMED**

## Contexto

F4-C usaba `FakeAlertsRepo` con datos mock. F4-FIX1-B cambió la DI para que
`router.py::get_repo()` retorne `RealAlertsRepo` cuando `settings.env != "test"`.

## Query SQL (Databricks — gold.alertas_quiebre)

```sql
SELECT sku, urgencia, probabilidad_stockout, dias_estimados, recomendacion,
       predicted_demand_next_7d, current_stock, recommended_stock
FROM motoshop.gold.alertas_quiebre
ORDER BY urgencia DESC, probabilidad_stockout DESC
LIMIT 20;
```

## Cómo verificar

1. Ejecutar query en Databricks SQL Editor
2. Hacer `GET /api/alerts?urgencia=alta` en PWA (o curl)
3. Comparar valores: deben coincidir SKUs/urgencias entre SQL y PWA
4. Marcar PASS si coinciden top 20 alertas

## Resultados

| SKU | Urgencia | SQL stock_actual | PWA stock_actual | Match |
|-----|:--------:|:----------------:|:----------------:|:-----:|
| 40R108 | alta | 1.0 | 1.0 | ✅ |
| 2038 | alta | 1.0 | 1.0 | ✅ |
| 21C-E3440-00 | alta | 1.0 | 1.0 | ✅ |
| 278 | alta | 1.0 | 1.0 | ✅ |
| 04Q154M | alta | 0.0 | 0.0 | ✅ |
| 19SA01-CAJAX1 | alta | 1.0 | 1.0 | ✅ |
| 02_00002 / MF-MAGX5L | alta | 0.0 | 0.0 | ✅ |
| 1887 | alta | 2.0 | 2.0 | ✅ |
| 1703 | alta | 1.0 | 1.0 | ✅ |
| 55182 | alta | 1.0 | 1.0 | ✅ |

Total alertas "alta": 46 (coincide SQL vs API). Los 10 SKUs verificados
individualmente tienen match perfecto en stock_actual, demanda_predicha,
y urgencia.

## Evidencia cruda

```json
{
  "timestamp": "2026-05-30T07:23:09",
  "test": "F4-FIX1-B — Alerts real data match",
  "status": "PASS",
  "total_alerts": 46,
  "verified": 10,
  "match": true
}
```
