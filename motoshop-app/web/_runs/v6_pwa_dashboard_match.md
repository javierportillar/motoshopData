# V6 — PWA vs Databricks SQL Reconciliation

Fecha: 2026-05-29T15:05:53-05:00  
Test: Reconciliación 5 KPIs entre PWA (API `/metrics/*`) y Databricks SQL Dashboard  
Resultado: ✅ **PASS — ALL 5 KPIs MATCH**

## Metodología

1. La API `/metrics/*` lee de `motoshop.gold.mart_*` vía `RealMetricsRepo` (Databricks SDK statement execution).
2. Las queries directas a Databricks SQL Warehouse usan el **mismo SQL exacto** que `RealMetricsRepo`.
3. Se comparan 5 KPIs específicos:
   - Ventas del último mes disponible
   - Stock total (unidades + SKUs)
   - % Categoría A (ABC)
   - Productos dormidos (>90 días)
   - Cohortes de clientes

## Resultados

| # | KPI | API (PWA) | Databricks SQL | Match |
|---|-----|-----------|----------------|-------|
| 1 | Ventas mes (2025-11) | $99,200 | $99,200 | ✅ |
| 2 | Stock total | 4,024 unidades, 4,829 SKUs | 4,024.0, 4,829 | ✅ |
| 3 | ABC A % | 69.6% (1 SKU, $69,000) | 69.6% | ✅ |
| 4 | Productos dormidos | 50 items | 50 items | ✅ |
| 5 | Cohortes clientes | 9 registros | 9 registros | ✅ |

## Conclusión

**V6 PASS**. La PWA (vía API) y Databricks SQL Dashboard leen de los mismos marts gold con las mismas queries. Los 5 KPIs coinciden hasta el último decimal.

Nota: Los datos gold son demo (2024-09 a 2025-11). Cuando el workflow nocturno comience a poblar gold con datos frescos, las queries se adaptan automáticamente usando `MAX(business_date)` como referencia en lugar de `CURRENT_DATE()`.

## Evidencia cruda

```json
{
  "timestamp": "2026-05-29T15:05:53",
  "test": "V6 — PWA vs Databricks SQL Reconciliation",
  "status": "PASS",
  "kpis": [
    {"kpi": "Ventas mes", "api": 99200.0, "sql": 99200.0, "match": true},
    {"kpi": "Stock", "api_stock": 4024.0, "api_productos": 4829, "sql_stock": 4024.0, "sql_productos": 4829, "match": true},
    {"kpi": "ABC A %", "api": 69.6, "sql": 69.6, "match": true},
    {"kpi": "Dormidos", "api": 50, "sql": 50, "match": true},
    {"kpi": "Cohortes", "api": 9, "sql": 9, "match": true}
  ]
}
```
