# ADR-0020: Forecasting agregado por categoría

**Status**: Proposed → **Accepted** (si hipótesis se valida: baseline-categoría WAPE < 45.83%)
**Date**: 2026-05-30
**Deciders**: F6 Team (Dev B · Track A · Analítica Robusta)
**Sprint**: F6-B

---

## Context

F4-FIX1 demostró que el forecasting por SKU individual no funciona para el dataset de MotoShop:

- Solo 31/4392 SKUs (0.7%) son elegibles para modelos ML.
- Baseline gana 97.9% de las predicciones (WAPE 45.83%).
- Prophet WAPE 864%, LightGBM WAPE 57% — ninguno supera baseline.
- **Causa raíz:** demanda intermitente + cola larga de SKUs con baja frecuencia.

La **recomendación** explícita de F4-FIX1 (documentada en ADR-0017 y lecciones-aprendidas-f4.md) fue:

> "La solución futura es agregación por categoría/familia."

Este ADR materializa esa recomendación: agregar ventas a nivel `cod_grupo` (categoría) y evaluar si el forecasting a ese nivel supera al baseline por SKU individual.

---

## Decision

### 1. Forecast a nivel categoría como modelo de producción

A partir de F6, el forecasting opera a nivel `cod_grupo` (agregación de SKUs por categoría):

| Aspecto | Decisión |
|---------|----------|
| Nivel de forecast | `cod_grupo` (alias `dim_producto.cod_grupo`, del campo bronze `productos.codpor`) |
| Tabla gold | `gold.forecast_categoria` |
| Baseline | Media móvil 7/14/28d sobre serie agregada |
| Modelo ML | Prophet sobre serie agregada (evaluación comparativa) |
| Métrica primaria | WAPE (misma que ADR-0017) |
| Referencia a superar | Baseline-SKU WAPE 45.83% |

**Rationale**:

1. **Reducción de intermitencia:** ~50 categorías agrupan 4,392 SKUs. La demanda intermitente de SKU individual se suaviza al sumar.
2. **Cobertura universal:** Todas las categorías con ≥90 días de historia son elegibles (vs 0.7% en SKU individual).
3. **Estacionalidad detectable:** La serie agregada tiene suficiente densidad para que Prophet pueda aprender patrones semanales.
4. **Operacionalización:** Si el forecast a nivel categoría es mejor, la reconciliación a SKU es un paso post-proceso (F7+).

### 2. Forecast jerárquico diferido a F7+

El forecast jerárquico (categoría + reconciliación a SKU con método "top-down" o "bottom-up") no se implementa en F6:

- **Decisión:** Diferir a F7+ si el negocio lo requiere.
- **Razón:** Validar primero que la agregación mejora el forecast. Una vez confirmado, la reconciliación es un paso de post-procesamiento.
- **Alternativa considerada:** "Middle-out" con reconciliación MinT (Wickramasuriya et al., 2019) — requiere más datos y validación.

---

## Consequences

### Positive

- ✅ Cobertura de forecasting: de 0.7% (31 SKUs) a ~100% de categorías.
- ✅ Demanda más regular → mejor señal para baseline y Prophet.
- ✅ Operación más simple: ~50 forecasts vs 4,392.
- ✅ Trazabilidad: tabla gold particionada con método documentado.

### Negative

- ❌ Se pierde granularidad SKU → las predicciones son por categoría, no por producto individual.
- ❌ La reconciliación a SKU requiere un paso adicional (F7+).
- ❌ Si la hipótesis no se valida, este enfoque tampoco funciona.

### Technical debt created

- La reconciliación categoría → SKU no está implementada. Si el negocio necesita forecast por SKU, hay que agregar un paso de prorrateo.
- Prophet requiere entrenamiento local (no corre en Databricks SQL Warehouse). El baseline de medias móviles es 100% SQL y corre en el warehouse.

---

## Alternatives considered

### 1. Forecast por familia (`cod_linea1`)
**Descartado para F6.** `cod_linea1` es más granular (~200-300 valores) pero algunas familias podrían tener poca densidad de datos. Si `cod_grupo` funciona, se puede bajar a familia en F7+.

### 2. Forecast jerárquico completo (categoría → familia → SKU)
**Diferido a F7+.** Requiere reconciliación estadística (MinT, OLS) que agrega complejidad sin validar primero el beneficio de la agregación.

### 3. Mantener baseline-SKU como producción
**Descartado.** Baseline-SKU WAPE 45.83% es la referencia, pero F4-FIX1 recomendó explícitamente explorar agregación. Si la categoría no supera, se mantiene baseline-SKU (documentado en lecciones).

### 4. LightGBM sobre categoría
**Descartado para F6.** Si baseline-categoría + Prophet no funcionan, LightGBM agregado tampoco tendría señal. LightGBM fue archivado por R14 y no se reimplementa.

---

## Related artifacts

- [Schema de agregación](../../notebooks/gold/_runs/v_categoria_schema_20260530.md)
- [Evaluación forecasting categoría](../../notebooks/gold/_runs/v_forecast_categoria_eval_20260530.md) (poblado tras ejecución)
- [Notebook 24 — Forecast Categoría](../../notebooks/gold/24_forecast_categoria.py)
- [Lecciones F6](../../docs/lecciones-aprendidas-f6.md)
- [ADR-0017 — Split temporal y métricas para demanda intermitente](0017-split-temporal-metricas-intermitentes.md)
- [Lecciones F4 — Por qué Prophet por SKU no funcionó](../../docs/lecciones-aprendidas-f4.md)
