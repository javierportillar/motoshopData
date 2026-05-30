# B1 · Esquema de agregación — Forecasting por categoría

**Fecha:** 2026-05-30
**Sprint:** F6-B (Dev B · Track A)
**Hipótesis:** Agregar ventas por categoría supera baseline por SKU individual (WAPE < 45.83%)

---

## Decisión de esquema

**Nivel de agregación:** `cod_grupo` (categoría)

| Atributo | Valor |
|----------|-------|
| Campo | `dim_producto.cod_grupo` (originado de `bronze.productos.codpor`) |
| Descripción | Código de grupo de producto en sgHermes |
| Cardinalidad esperada | ~50 grupos |
| Nivel alternativo | `cod_linea1` (familia) — descartado porque fragmentaría demasiado |

**Justificación:**
1. **Densidad de datos:** ~50 categorías agrupan 4,392 SKUs → ~88 SKUs/categoría promedio. Las ventas intermitentes de SKU individual se suavizan al sumar.
2. **Cobertura temporal:** Las categorías con ~90 días de historia tienen alta probabilidad (~100%) porque agregan múltiples SKUs. En F4 solo 0.7% de SKUs individuales pasaban este filtro.
3. **Estacionalidad perceptible:** Al agregar, la serie temporal gana regularidad → Prophet puede aprender patrones semanales/mensuales.
4. **Alineación con plan:** DT-F6-3 menciona "~50 categorías con alta frecuencia".

---

## Mapping SKU → Categoría

```sql
SELECT DISTINCT
    mvd.cod_producto,
    dp.cod_grupo
FROM motoshop.gold.mart_ventas_diarias_sku mvd
LEFT JOIN motoshop.silver.dim_producto dp
    ON mvd.cod_producto = dp.cod_producto
```

Nota: SKUs sin `cod_grupo` agrupados como `'SIN_GRUPO'`.

---

## Estructura de la tabla target

```sql
CREATE TABLE motoshop.gold.forecast_categoria (
    cod_grupo STRING,
    business_date DATE,
    demanda_real DOUBLE,
    demanda_predicha_baseline DOUBLE,
    metodo_baseline STRING,
    demanda_predicha_prophet DOUBLE
) USING DELTA PARTITIONED BY (business_date);
```

---

## Métrica de evaluación

**WAPE** (Weighted Absolute Percentage Error), misma métrica que ADR-0017:

```
WAPE = Σ|actual - pred| / Σ actual
```

Referencia baseline-SKU: **45.83%** (registrado en F4-FIX1 v_model_evaluation_20260530_113116.md)

**Criterio de éxito:** Prophet-categoría WAPE < Baseline-categoría WAPE < 45.83%

---

## Riesgos documentados

| Riesgo | Mitigación |
|--------|-----------|
| `cod_grupo` tiene valores NULL o vacíos | Agrupar como `'SIN_GRUPO'`, reportar cobertura |
| Alguna categoría domina el agregado (~80% ventas) | Reportar WAPE por categoría además del global |
| Prophet no encuentra estacionalidad en el agregado | Documentar honestamente (misma regla que F4-FIX1) |
