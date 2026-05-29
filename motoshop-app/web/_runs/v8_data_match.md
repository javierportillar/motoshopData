# V8 · Reconciliación PWA vs MySQL — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿La PWA muestra el dato correcto?
- **Resultado:** ✅ Schema corregido — pendiente de comparación con datos reales

## Fix aplicado (T2)

Schema stock alineado con la respuesta real de la API:

| Campo PWA (antes) | Campo API real | Cambio |
|---|---|---|
| `codprod` | `sku` | `StockResponse.codprod` → `sku` |
| `nom_bodega` | `nombod` | `StockItem.nom_bodega` → `nombod` |
| `stock` | `cantidad` | `StockItem.stock` → `cantidad` |

## Flujo de datos stock

```
PWA [sku].tsx → useStock(sku) → GET /api/products/{sku}/stock
                                 → proxy [...path] → FastAPI → MySQL
                                 → respuesta: { sku, total, by_bodega: [{ codbod, nombod, cantidad }] }
```

## Cómo validar con 5 SKUs reales

1. Login en PWA
2. Buscar y abrir 5 SKUs diferentes
3. Anotar `stock.total` que muestra la PWA
4. Ejecutar query directa en MySQL:

```sql
SELECT codprod, SUM(valor3) AS stock_mysql
FROM auxinventario
WHERE codprod IN ('<SKU1>', '<SKU2>', '<SKU3>', '<SKU4>', '<SKU5>')
GROUP BY codprod;
```

5. Comparar totales — tolerancia < 0.5%

### Tabla de comparación

| SKU | PWA stock | MySQL (SUM valor3) | Diff | PASS/FAIL |
|---|---|---|---|---|
| (pendiente) | | | | |

> Nota: La comparación requiere API real operativa con datos en MySQL. El schema del response está verificado y alineado con `hooks.ts`.
