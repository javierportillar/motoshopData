# Fix Bug 3 · inventory-summary valor_total

**Fecha:** 2026-05-30
**Sprint:** F6-D-FIX1-A (Dev A)
**Bug:** `/metrics/inventory-summary` retorna `valor_total: 0.0`

---

## Causa raíz

`mart_inventario_actual` tiene `costo_promedio = 0.0` para las 4,829 filas.
La query original:

```sql
WHERE costo_promedio IS NOT NULL AND costo_promedio > 0
```

filtraba el 100% de las filas → `SUM(cantidad_actual * costo_promedio) = 0.0`.

## Fix

Reemplazar la query de valor_total con JOIN a `silver.fact_compras_detalle`
que tiene `costo_producto` real (8,797/11,623 filas con costo > 0).

Se usa `ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC)`
para obtener el último costo de compra de cada producto.

## Verificación

Query ejecutada en Databricks SQL:

```sql
WITH latest_cost AS (
    SELECT cod_producto, costo_producto,
           ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) AS rn
    FROM motoshop.silver.fact_compras_detalle
    WHERE costo_producto > 0
)
SELECT COALESCE(ROUND(SUM(i.cantidad_actual * COALESCE(lc.costo_producto, 0)), 2), 0) AS valor_total
FROM motoshop.gold.mart_inventario_actual i
LEFT JOIN latest_cost lc ON i.cod_producto = lc.cod_producto AND lc.rn = 1
```

**Resultado:** `83,128,020.24` ✅ (> 0, valor esperado ~$83M COP)

## Tests

`pytest tests/test_metrics.py` → 11/11 ✅ (sin regresiones)
