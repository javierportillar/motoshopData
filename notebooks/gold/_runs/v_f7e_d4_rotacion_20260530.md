# V-F7E-D4 · Rotación promedio · 2026-05-30

**Notebook:** `18_mart_rotacion_promedio.py`
**Tabla:** `gold.mart_rotacion_sku`
**Warehouse:** 43bc044eaef4cca4

---

## Resultados

| Métrica | Valor |
|---|---|
| Filas totales | 4,840 |
| SKUs únicos | 4,840 |
| SKUs con venta (90d) | 1,172 |
| SKUs con stock | 3,469 |
| Cobertura promedio | 511.9 días |

## Top 5 rotación

| SKU | Venta/día | Stock | Cobertura (días) |
|---|---|---|---|
| 12209-GB4-685S | 1.244 | 2.0 | 1.6 |
| 601325 | 1.144 | 1.0 | 0.9 |
| MOTS1297 | 1.033 | 1.0 | 1.0 |
| 91201-GBG-900S | 0.733 | 1.0 | 1.4 |
| 2038 | 0.678 | 1.0 | 1.5 |

## Columnas

```
cod_producto, nom_producto, stock_actual, venta_diaria_promedio, dias_de_cobertura, business_date
```

Nota: `stock_actual` se mapea desde `mart_inventario_actual.cantidad_actual`.
