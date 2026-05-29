# V2 · Verificación de fechas inválidas en Silver

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Las fechas inválidas se descartan o paran el pipeline?

## Resultado esperado

No debe haber `business_date` nulas ni futuras en tablas de hechos.

## Resultado real

| Tabla | business_date nulas | business_date futuras | Status |
|-------|---------------------|----------------------|--------|
| fact_ventas | 0 | 0 | ✅ PASS |
| fact_compras | 0 | 0 | ✅ PASS |
| fact_inventario | 0 | 0 | ✅ PASS |

**Veredicto: PASS — 3/3 tablas sin fechas inválidas**

## Filtros aplicados

```sql
WHERE CAST(fecfven AS DATE) >= DATE '2020-01-01'
  AND CAST(fecfven AS DATE) <= CURRENT_DATE()
```

## Notebook ejecutado

`notebooks/silver/30_validate_silver.py` — sección V2.

## Query de evidencia

```sql
SELECT 'fact_ventas' AS tabla,
  SUM(CASE WHEN business_date IS NULL THEN 1 ELSE 0 END) AS nulas,
  SUM(CASE WHEN business_date > CURRENT_DATE() THEN 1 ELSE 0 END) AS futuras,
  CASE WHEN SUM(CASE WHEN business_date IS NULL OR business_date > CURRENT_DATE() THEN 1 ELSE 0 END) = 0
    THEN 'PASS' ELSE 'FAIL' END AS status
FROM motoshop.silver.fact_ventas
```
