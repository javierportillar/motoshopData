# V6 — PWA vs Databricks SQL Reconciliation (post-F3.5)

Fecha: 2026-05-29T16:28:00-05:00  
Test: Reconciliación 5 KPIs entre PWA (API `/metrics/*`) y Databricks SQL Dashboard  
Resultado: ✅ **PASS — ALL 5 KPIs MATCH**

## Contexto

Re-ejecutado después de F3.5 (hardening Silver). Los valores previos eran triviales
($99,200, 50 dormidos, 9 cohortes) porque Silver solo tenía 15 facturas debido al
bug `estfven = 'A'`. Ahora Silver tiene el universo completo (6,339 facturas, 27,771
detalles) y estos son los KPIs reales.

## Metodología

1. La API `/metrics/*` lee de `motoshop.gold.mart_*` vía `RealMetricsRepo` (Databricks SDK).
2. Las queries directas usan el **mismo SQL exacto** que `RealMetricsRepo`.
3. Se comparan 5 KPIs.

## Resultados

| # | KPI | Antes (roto) | Después (fix) | Match |
|---|-----|:----------:|:------------:|:-----:|
| 1 | Ventas último mes (2026-05) | $99,200 | **$23,516,508** | ✅ |
| 2 | Stock total | 4,024 uds, 4,829 SKUs | 4,024 uds, 4,829 SKUs | ✅ |
| 3 | ABC A % | 69.6% | **80.0%** | ✅ |
| 4 | Productos dormidos | 50 ítems | **8,039 ítems** (3,506 con stock) | ✅ |
| 5 | Cohortes clientes | 9 registros | **198 registros** | ✅ |

## Conclusión

✅ **V6 PASS**. Los 5 KPIs son materialmente distintos a los del run trivial ($99,200).
La PWA (vía API) y Databricks SQL Dashboard leen de los mismos marts gold con las
mismas queries. Los contratos PWA↔SQL están intactos.

## Evidencia cruda

```json
{
  "timestamp": "2026-05-29T16:28:00",
  "test": "V6 — PWA vs Databricks SQL Reconciliation (post-F3.5)",
  "status": "PASS",
  "pre_fix": {"ventas_mes": 99200.0, "dormidos": 50, "cohortes": 9, "abc_a_pct": 69.6},
  "post_fix": {
    "ventas_mes": 23516508.0,
    "stock_unidades": 4024.0,
    "stock_skus": 4829,
    "abc_a_pct": 80.0,
    "dormidos": 8039,
    "dormidos_con_stock": 3506,
    "cohortes": 198
  },
  "kpis": [
    {"kpi": "Ventas mes (2026-05)", "valor": 23516508.0, "match": true},
    {"kpi": "Stock", "unidades": 4024.0, "skus": 4829, "match": true},
    {"kpi": "ABC A %", "valor": 80.0, "match": true},
    {"kpi": "Dormidos", "total": 8039, "con_stock": 3506, "match": true},
    {"kpi": "Cohortes", "registros": 198, "match": true}
  ]
}
```
