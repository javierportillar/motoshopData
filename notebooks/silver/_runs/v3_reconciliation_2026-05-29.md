# V3 · Reconciliación Silver vs Bronze (proxy sgHermes)

- **Fecha:** 2026-05-29
- **Ejecutor:** Dev A (Track A · Silver)
- **Verificación:** ¿Totales silver cuadran con sgHermes (< 0.5%)?

## Metodología

Se comparan los `SUM(total)` del mes pasado entre:
- **Bronze** (proxy de sgHermes): `facventas.totfven` / `compras.totcom`
- **Silver**: `fact_ventas.total_factura` / `fact_compras.total_compra`

Tolerancia: < 0.5% diferencia.

## Resultados

### fact_ventas

| Métrica | Bronze | Silver | Diff | Status |
|---------|--------|--------|------|--------|
| Facturas del mes | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| Total ventas | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| Diferencia % | — | — | _pendiente_ | _pendiente_ |

### fact_compras

| Métrica | Bronze | Silver | Diff | Status |
|---------|--------|--------|------|--------|
| Compras del mes | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| Total compras | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| Diferencia % | — | — | _pendiente_ | _pendiente_ |

## Top 10 SKUs mes pasado

_Completar con display(top_skus) del notebook._

## Notebook ejecutado

`notebooks/silver/31_reconciliation.py`.

## Evidencia

_Completar tras ejecutar el notebook en Databricks._
