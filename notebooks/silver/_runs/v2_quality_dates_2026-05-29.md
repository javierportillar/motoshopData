# V2 · Verificación de fechas inválidas en Silver

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Las fechas inválidas se descartan o paran el pipeline?

## Resultado esperado

No debe haber `business_date` nulas ni futuras en tablas de hechos.

## Caso conocido

`fecfven` con año 9876 detectado en sondeo de fechas (Sesión 22). Debe filtrarse en silver.

## Tablas verificadas

| Tabla | business_date nulas | business_date futuras | Status |
|-------|---------------------|----------------------|--------|
| fact_ventas | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_ventas_detalle | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_compras | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_compras_detalle | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_inventario | _pendiente_ | _pendiente_ | _pendiente_ |

## Filtros aplicados

```python
WHERE business_date >= '2020-01-01'
  AND business_date <= CURRENT_DATE()
```

## Notebook ejecutado

`notebooks/silver/30_validate_silver.py` — sección V2.

## Evidencia

_Completar tras ejecutar el notebook en Databricks._
