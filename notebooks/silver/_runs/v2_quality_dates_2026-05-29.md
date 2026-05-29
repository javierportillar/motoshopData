# V2 · Verificación de fechas inválidas en Silver

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Las fechas inválidas se descartan?

## Resultado esperado

No debe haber `business_date` nulas ni futuras. La política de fechas inválidas se demuestra con caso sintético.

## Resultado real (producción)

| Tabla | business_date nulas | business_date futuras | Status |
|-------|---------------------|----------------------|--------|
| fact_ventas | 0 | 0 | ✅ PASS |
| fact_compras | 0 | 0 | ✅ PASS |
| fact_inventario | 0 | 0 | ✅ PASS |

## Caso sintético (prueba controlada)

Se creó una temp view `_test_future_dates` con 4 registros:
- 2 fechas válidas (2024-06-15, 2024-01-01)
- 2 fechas futuras (9999-01-01, 2025-12-31)

Se aplicó el filtro `business_date <= CURRENT_DATE()`:
- Resultado: 2 fechas futuras detectadas, 2 filas pasan el filtro
- Status: PASS

**Veredicto: PASS — política de fechas funciona correctamente**

## Filtros aplicados en producción

```sql
WHERE CAST(fecfven AS DATE) >= DATE '2020-01-01'
  AND CAST(fecfven AS DATE) <= CURRENT_DATE()
```

## Notebook ejecutado

`notebooks/silver/30_validate_silver.py` — sección V2 con caso sintético.
