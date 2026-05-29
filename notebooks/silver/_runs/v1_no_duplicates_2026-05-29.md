# V1 · Verificación de duplicados en Silver

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Hay duplicados en silver?

## Resultado esperado

Cada tabla silver debe tener `count(*) == count(DISTINCT pk)`.

## Resultado real

| Tabla | Filas | Distintas | Duplicadas | Status |
|-------|-------|-----------|------------|--------|
| fact_ventas | 15 | 15 | 0 | ✅ PASS |
| fact_ventas_detalle | 58 | 58 | 0 | ✅ PASS |
| fact_compras | 16 | 16 | 0 | ✅ PASS |
| fact_compras_detalle | 733 | 733 | 0 | ✅ PASS |
| fact_inventario | 26,174 | 26,174 | 0 | ✅ PASS |
| dim_producto | 6,185 | 6,185 | 0 | ✅ PASS |
| dim_bodega | 1 | 1 | 0 | ✅ PASS |
| dim_tercero | 161 | 161 | 0 | ✅ PASS |
| dim_sucursal | 0 | 0 | 0 | ✅ PASS |
| dim_formapago | 20 | 20 | 0 | ✅ PASS |
| dim_tiempo | 2,706 | 2,706 | 0 | ✅ PASS |

**Veredicto: PASS — 11/11 tablas sin duplicados**

## Patrón idempotente

Hechos usan `DELETE + INSERT` por `business_date` (no `CREATE OR REPLACE TABLE`). Verificar ejecutando dos veces el mismo notebook — el conteo no cambia.

## Notebook ejecutado

`notebooks/silver/30_validate_silver.py` — sección V1.

## Query de evidencia

```sql
SELECT 'fact_ventas' AS tabla, COUNT(*) AS filas,
  COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS distintas,
  COUNT(*) - COUNT(DISTINCT STRUCT(num_documento, cod_clase, business_date)) AS duplicadas
FROM motoshop.silver.fact_ventas
```

Ejecutado vía SQL Warehouse `43bc044eaef4cca4` (Serverless Starter Warehouse).
