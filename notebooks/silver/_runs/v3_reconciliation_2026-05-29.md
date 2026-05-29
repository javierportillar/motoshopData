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

**Status:** ✅ Ejecutado — ver output real abajo.

**Output real (2026-05-29):**

```
| cod_producto  | nombre_producto                   | facturas | cantidad_total | total_ventas |
|---------------|-----------------------------------|----------|---------------|--------------|
| 10091611      | BATER MEGABAT SECA/L-M MT5LB BS   | 1        | 1.0           | 69000.0      |
| 91255-ABZ-000S| RETENEDOR ACEITE 37X50X11         | 1        | 2.0           | 18000.0      |
| 171001        | TELESCOPICO PINTA 420 CC          | 1        | 1.0           | 8900.0       |
| 2867          | TUERCA PARAGUA 6 MM               | 1        | 2.0           | 1000.0       |
| TOR - 0459    | TORNILLO BRISTOL 6 X65 TORNIFRENOS| 1        | 1.0           | 1000.0       |
| 2026          | ARANDELA 8 MM (ANCHA)             | 1        | 4.0           | 800.0        |
| 275           | TORNILLO HEX. 6 x 15 MM           | 1        | 1.0           | 500.0        |
```

(7 productos únicos en el mes — el volumen de datos actual es limitado porque es una importación parcial de demo)

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

**Status:** ✅ Ejecutado — ver output real abajo.

**Output real (2026-05-29):**

```
| nit_cliente | nombre_completo  | facturas | total_compras |
|-------------|------------------|----------|--------------|
| 222222222   | CONSUMIDOR FINAL | 1        | 99200.0      |
| --          | (sin más datos)  | --       | --           |
```

(1 cliente activo en el último mes — CONSUMIDOR FINAL. Datos limitados a importación parcial de demo)

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

---

## Reporte consolidado de ejecución

**69/69 statements ejecutados — ALL GREEN ✅**

### Recuento de tablas silver

| Tabla | Rows |
|-------|------|
| fact_ventas | 15 |
| fact_ventas_detalle | 58 |
| fact_compras | 16 |
| fact_compras_detalle | 733 |
| fact_inventario | 26,174 |
| dim_producto | 6,185 |
| dim_bodega | 1 |
| dim_tercero | 161 |
| dim_sucursal | 0 |
| dim_formapago | 20 |
| dim_tiempo | 2,706 |

### Quality Run (20_quality_run.py)

- **13 reglas de calidad insertadas**
- **0 reglas CRITICAL**
- **assert_true: PASSED ✅**
- Notebook ejecutado completo con 16 statements OK

### Tests Silver (32_test_silver.py)

| # | Test | Resultado |
|---|------|-----------|
| 1 | PK única fact_ventas | ✅ |
| 2 | PK única fact_compras | ✅ |
| 3 | PK única fact_inventario | ✅ |
| 4 | PK única dim_producto | ✅ |
| 5 | PK única dim_tercero | ✅ |
| 6 | PK única dim_formapago | ✅ |
| 7 | Sin fechas futuras fact_ventas (V2) | ✅ |
| 8 | Sin fechas futuras fact_compras (V2) | ✅ |
| 9 | Sin fechas futuras fact_inventario (V2) | ✅ |
| 10 | Sin totales negativos fact_ventas | ✅ |
| 11 | Sin totales negativos fact_compras | ✅ |
| 12 | Sin cantidades negativas fact_inventario | ✅ |
| 13 | PK única dim_tiempo | ✅ |
| 14 | Reconciliación V3 bronze vs silver | ✅ |
| 15 | PK sin nulos fact_ventas | ✅ |

**15/15 assertions: ALL GREEN ✅**

### Validate Silver (30_validate_silver.py)

| Tabla | Filas | Distinct | Duplicados | Nulas | Status |
|-------|-------|----------|------------|-------|--------|
| fact_ventas | 15 | 15 | 0 | 0 | ✅ |
| dim_producto | 6,185 | 6,185 | 0 | — | ✅ |
| fact_ventas nulas V2 | — | — | — | 0 | ✅ |

### Archivos de evidencia

- **Reporte completo de ejecución:** `notebooks/silver/_runs/run_silver_20260529_131402.md`
- **Este archivo:** `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md`
