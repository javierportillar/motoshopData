# V1 · Verificación de duplicados en Silver

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Hay duplicados en silver?

## Resultado esperado

Cada tabla silver debe tener `count(*) == count(DISTINCT pk)`.

## Tablas verificadas

| Tabla | PK | Filas | Distintas | Duplicadas | Status |
|-------|-----|-------|-----------|------------|--------|
| dim_producto | cod_producto | _pendiente run_ | _pendiente_ | _pendiente_ | _pendiente_ |
| dim_bodega | cod_bodega | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| dim_tercero | nit_tercero | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| dim_sucursal | cod_sucursal | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| dim_formapago | cod_formapago | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| dim_tiempo | business_date | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_ventas | num_documento+cod_clase+business_date | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_compras | num_documento+cod_clase+business_date | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_ventas_detalle | num_documento+cod_clase+cod_producto+num_item+business_date | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_compras_detalle | num_documento+cod_clase+cod_producto+num_item+business_date | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| fact_inventario | id_inventario+business_date | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |

## Notebook ejecutado

`notebooks/silver/30_validate_silver.py` — sección V1.

## Evidencia

_Completar tras ejecutar el notebook en Databricks._
