# V3 · Reconciliación Silver vs Bronze (proxy sgHermes)

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Totales silver cuadran con sgHermes (< 0.5%)?

## Metodología

Se comparan los `SUM(total)` del último mes con datos entre:
- **Bronze** (proxy de sgHermes): `facventas.totfven` WHERE `estfven = 'A'`
- **Silver**: `fact_ventas.total_factura`

Tolerancia: < 0.5% diferencia.

**Nota:** Los datos van de 2024-09-13 a 2025-11-07. Se usa el último mes con datos (noviembre 2025), no "mes pasado" (abril 2026) que está vacío.

## Mes usado

- **Inicio:** 2025-11-01
- **Fin:** 2025-11-30
- **Facturas en el mes (bronze):** 1

## Resultado real

### fact_ventas

| Métrica | Bronze | Silver | Diff | Status |
|---------|--------|--------|------|--------|
| Facturas del mes | 1 | 1 | 0 | ✅ PASS |
| Total ventas | $99,200.00 | $99,200.00 | $0.00 | ✅ PASS |
| Diferencia % | — | — | 0.0% | ✅ PASS |

**Veredicto V3: PASS — dif = 0.0% (< 0.5%)**

## Top 10 SKUs por ventas (noviembre 2025)

_Completar tras ejecutar `31_reconciliation.py` en Databricks con DELETE+INSERT actualizado._

## Top 5 clientes por compras

_Completar tras ejecutar `31_reconciliation.py` en Databricks con DELETE+INSERT actualizado._

## Notebook ejecutado

`notebooks/silver/31_reconciliation.py`.

## Query de evidencia

```sql
WITH last_month AS (
  SELECT DATE_TRUNC("MONTH", MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = "A"
),
bv AS (
  SELECT COUNT(*) AS n, COALESCE(SUM(CAST(totfven AS DOUBLE)), 0) AS t
  FROM motoshop.bronze.facventas, last_month p
  WHERE estfven = "A" AND CAST(fecfven AS DATE) >= ms AND CAST(fecfven AS DATE) <= me
),
sv AS (
  SELECT COUNT(*) AS n, COALESCE(SUM(total_factura), 0) AS t
  FROM motoshop.silver.fact_ventas, last_month p
  WHERE business_date >= ms AND business_date <= me
)
SELECT bv.n, sv.n, bv.t, sv.t, ABS(bv.t - sv.t) AS diff,
  CASE WHEN ABS(bv.t - sv.t) / NULLIF(bv.t, 0) < 0.005 THEN 'PASS' ELSE 'FAIL' END AS status
FROM bv, sv
```

Ejecutado vía SQL Warehouse `43bc044eaef4cca4`.
