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

> Las queries existen en `31_reconciliation.py` §4 (Top 10 SKUs) y §5 (Top 5 clientes).
> Para capturar el output real, ejecutar el notebook en Databricks SQL Warehouse:

```sql
-- Query de Top 10 SKUs (ya en 31_reconciliation.py §4)
WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
)
SELECT d.cod_producto, pr.nombre_producto,
  COUNT(DISTINCT d.num_documento) AS facturas,
  SUM(d.cantidad) AS cantidad_total,
  SUM(d.total_detalle) AS total_ventas
FROM motoshop.silver.fact_ventas_detalle d
INNER JOIN motoshop.silver.fact_ventas h
  ON d.num_documento = h.num_documento AND d.cod_clase = h.cod_clase
LEFT JOIN motoshop.silver.dim_producto pr ON d.cod_producto = pr.cod_producto, last_month lm
WHERE h.business_date >= lm.ms AND h.business_date <= lm.me
GROUP BY d.cod_producto, pr.nombre_producto
ORDER BY total_ventas DESC
LIMIT 10;
```

**Status:** Query lista en notebook. Pendiente ejecución en Databricks SQL Warehouse para capturar output real.

## Top 5 clientes por compras

```sql
-- Query de Top 5 clientes (ya en 31_reconciliation.py §5)
WITH last_month AS (
  SELECT DATE_TRUNC('MONTH', MAX(fecfven)) AS ms, LAST_DAY(MAX(fecfven)) AS me
  FROM motoshop.bronze.facventas WHERE estfven = 'A'
)
SELECT h.nit_cliente, tc.nombre_completo,
  COUNT(*) AS facturas,
  SUM(h.total_factura) AS total_compras
FROM motoshop.silver.fact_ventas h
LEFT JOIN motoshop.silver.dim_tercero tc ON h.nit_cliente = tc.nit_tercero, last_month lm
WHERE h.business_date >= lm.ms AND h.business_date <= lm.me
GROUP BY h.nit_cliente, tc.nombre_completo
ORDER BY total_compras DESC
LIMIT 5;
```

**Status:** Query lista en notebook. Pendiente ejecución en Databricks SQL Warehouse para capturar output real.

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
