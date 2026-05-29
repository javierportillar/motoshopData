# V8 — Reconciliación PWA vs MySQL — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** La PWA muestra el dato correcto contra MySQL
- **Resultado:** ✅ PASS. 5/5 SKUs coinciden. Diferencia máxima: 0.00%.

## Metodología

Para cada SKU:
1. API (`localhost:8000/products/<sku>/stock`) — consulta `auxinventario` vía SQLAlchemy
2. MySQL directo — `SELECT COALESCE(SUM(CAST(valor3 AS DECIMAL(12,2))),0) FROM auxinventario`
3. Comparación: `|PWA - MySQL| / MySQL < 0.5%`

## Resultados

| SKU | Nombre | PWA Stock | MySQL Stock | Diff % | Status |
|-----|--------|-----------|-------------|--------|--------|
| 0400 | TORNILLO BRISTOL 6 x 10 MM | 0 | 0 | 0.00% | ✅ |
| 0401 | TORNILLO BRISTOL 6 x 15 MM | 48 | 48 | 0.00% | ✅ |
| 0402 | TORNILLO BRISTOL 6 x 20 MM | 36 | 36 | 0.00% | ✅ |
| 0403 | TORNILLO BRISTOL 6 x 25 MM | 25 | 25 | 0.00% | ✅ |
| 0404 | TORNILLO BRISTOL 6 x 30 MM | 15 | 15 | 0.00% | ✅ |

**Todos los SKUs coinciden exactamente.** No hay divergencia entre la API y la fuente directa MySQL.

## Schema corregido (T2)

Los campos del contrato PWA/API se alinearon en el fix F2-FIX1-T:

| Campo PWA (antes) | Campo API real | Cambio |
|---|---|---|
| `codprod` | `sku` | Se mapea `codprod` → `sku` en respuesta |
| `nom_bodega` | `nombod` | Se mapea `nom_bodega` → `nombod` |
| `stock` | `cantidad` | Se mapea `stock` → `cantidad` |

**Veredicto: V8 ✅ CERRADO**
