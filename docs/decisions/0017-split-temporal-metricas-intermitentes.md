# ADR-0017: Split temporal y métricas para demanda intermitente

**Status**: Accepted  
**Date**: 2026-05-30  
**Deciders**: F4 Team (Auditoría FIX1)  
**Sprint**: F4-FIX1  

---

## Context

El sprint F4 implementó modelos de forecasting (Prophet, LightGBM) y un clasificador de quiebre de stock. Durante la revisión FIX1 con contexto independiente se detectaron dos bloqueantes:

1. **Prophet MAPE 3540%**: Al evaluar Prophet sobre TODOS los SKUs (incluyendo aquellos con < 90 días de historia o < 30 ventas totales), MAPE se dispara porque:
   - SKUs con 1-3 ventas en todo su historial generan divisiones por valores pequeños → MAPE infinito.
   - La métrica MAPE no está diseñada para demanda intermitente donde `actual = 1` y `pred = 36` produce 3500% de error aunque el error absoluto sea pequeño.
   
2. **Classifier F1 = 0.9924**: El clasificador de quiebre reporta precisión casi perfecta porque:
   - El target se define como `stock_actual < media_movil_7d * 0.5` (proxy lingüístico).
   - El feature set incluye `stock_actual` y `media_movil_7d` → el modelo aprende una REGLA ARITMÉTICA, no un patrón predictivo.
   - El split es random stratified (no temporal) → las mismas fechas aparecen en train y test.

---

## Decision

### 1. WAPE como métrica primaria para forecasting

**WAPE** (Weighted Absolute Percentage Error) reemplaza a MAPE como métrica principal para comparación y selección de modelos.

```
WAPE = Σ|actual_i - pred_i| / Σ actual_i
```

**Rationale**:
- MAPE divide por cada `actual` individual. Cuando `actual = 1` y `pred = 36`, MAPE = 3500% aunque el error absoluto sea 35 unidades.
- WAPE suma todos los errores absolutos y divide por la suma de todos los reales → una predicción mala no domina el agregado.
- WAPE es la métrica recomendada por la literatura para demanda intermitente (ver Makridakis, Hyndman).

MAPE y sMAPE se mantienen como métricas secundarias para trazabilidad.

### 2. Filtro de elegibilidad por SKU

Solo SKUs con **≥ 90 días de historia** Y **≥ 30 ventas totales** son evaluados con Prophet/LightGBM. SKUs no elegibles reciben baseline.

**Rationale**:
- Prophet necesita ≥ 2 ciclos estacionales completos para estimar componentes. Con < 90 días, las predicciones son ruido.
- SKUs con < 30 ventas totales en el período son esencialmente demanda esporádica; Prophet no puede modelar ceros estructurales.
- Baseline (media móvil simple) funciona igual o mejor en este régimen.

### 3. Split temporal para clasificador

El clasificador de quiebre usa split temporal estricto:
- **Train**: datos hasta `'2026-03-31'` (inclusive)
- **Test**: datos desde `'2026-04-01'`
- NO se mezclan fechas entre train y test.
- NO se usa random stratified split.

**Rationale**:
- El clasificador debe predecir quiebres FUTUROS. Evaluar con random split contamina train con datos futuros → métricas irreales.
- El split temporal da una estimación honesta de performance en producción.

### 4. Target proxy y feature hygiene

El target `quiebre = stock_actual < media_movil_7d * 0.5` se mantiene como proxy pero con hygiene:
- `stock_actual` NO se incluye como feature del modelo (evita target leakage).
- `media_movil_7d` sí se mantiene (es información legítima de demanda histórica).
- Split temporal evita data leakage entre SKUs.

**Trade-off**: Sacar `stock_actual` puede bajar F1, pero el F1 anterior (0.99) era artificial. Preferimos métricas honestas.

---

## Consequences

### Positive
- ✅ Prophet evaluado solo en SKUs donde tiene chance de funcionar → métricas realistas
- ✅ WAPE evita falsos positivos donde MAPE se dispara por pocas ventas
- ✅ Classifier con split temporal → sabemos si realmente sirve para predecir el futuro
- ✅ Feature hygiene evita que el clasificador "haga trampa" viendo el target

### Negative
- ❌ Prophet cubre solo 31 de 4392 SKUs (0.7%) → el modelo Prophet es esencialmente inservible
- ❌ LightGBM forecasting cubre 31 SKUs y gana solo 12 predicciones (0.3%) → no hay evidencia de que mejore baseline
- ❌ Baseline domina 97.9% de las predicciones → el effort de Prophet/LightGBM no se justifica

### Technical debt created
- El split temporal del clasificador se implementa con filtro SQL, no con validación walk-forward
- El target proxy no ha sido validado contra quiebres reales (stock = 0 + demanda > 0)

---

## Alternatives considered

### 1. MASE como métrica
**Descartado**. MASE requiere serie de entrenamiento para escalar, y nuestra feature store no tiene histórico completo por SKU. WAPE es más simple y aplica directamente.

### 2. Walk-forward validation
**Aplazado a F6**. Walk-forward es más robusto que un solo split temporal, pero requiere re-entrenar N veces. Para F4-B un split temporal fijo es suficiente.

### 3. Quiebre real como target
**Aplazado**. `stock_actual = 0 AND demanda_diaria > 0` es el target ideal pero puede tener muy pocas ocurrencias para entrenar. Se investiga en F5.

### 4. Quitar Prophet completamente
**Aceptado parcialmente**. Prophet se mantiene en el pipeline (el código existe) pero con WAPE 864% en SKUs elegibles, no se recomienda su uso en producción. Se deja para no romper el pipeline pero se documenta su inutilidad.

---

## Related artifacts

- [Prophet diagnosis](../../notebooks/gold/_runs/v_fix1_prophet_diagnostico_20260530_112831.md)
- [Model evaluation (post-fix)](../../notebooks/gold/_runs/v_model_evaluation_20260530_113116.md)
- [Classifier evidence (pre-fix)](../../notebooks/gold/_runs/v_classifier_stockout_20260530_013301.md)
- [Plan F4-FIX1](../../docs/plan-f4-fix1.md)
