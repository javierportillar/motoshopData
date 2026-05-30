# F4-FIX1-B — Alerts: RealAlertsRepo vs Databricks SQL

Fecha: 2026-05-30  
Test: Validar que `GET /api/alerts` devuelve datos reales de `gold.alertas_quiebre`  
Resultado: ⏳ **PENDING — esperar a que Dev A complete Prophet + classifier**

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

| SKU | Urgencia | SQL prob | PWA prob | Match |
|-----|:--------:|:--------:|:--------:|:-----:|
| ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Evidencia cruda

```json
{
  "timestamp": "",
  "test": "F4-FIX1-B — Alerts real data match",
  "status": "PENDING"
}
```
