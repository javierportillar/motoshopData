# V8 · Reconciliación PWA vs MySQL — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿La PWA muestra el dato correcto?
- **Resultado:** PENDIENTE de prueba con API real + MySQL

## Setup implementado

- `app/(authenticated)/products/[sku]/page.tsx`: ficha SKU con stock por bodega
- `useStock(sku)` hook conecta a `GET /products/{sku}/stock`
- `StockBadge` muestra cantidad por bodega
- `SyncStatus` indica freshness de los datos

## Comparación requerida

Elegir 5 SKUs aleatorios y comparar:

| SKU | PWA stock | MySQL (`SELECT codprod, SUM(valor3) FROM auxinventario WHERE codprod = 'X'`) | ¿Cuadra? |
|---|---|---|---|
| (pendiente) | | | |

## Próximos pasos

1. Login en PWA
2. Buscar 5 SKUs diferentes
3. Abrir ficha de cada uno
4. Ejecutar query directa en MySQL para cada SKU
5. Comparar totales → tolerancia < 0.5%
6. Documentar aquí con resultados reales
