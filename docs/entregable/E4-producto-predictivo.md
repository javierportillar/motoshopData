# E4 · Producto predictivo (Forecasting + Alertas de quiebre)

> **Curso:** Big Data y Transformación Digital del Negocio · UAO 2025-2  
> **Módulo cubierto:** 3 (analítica predictiva + ética IA)  
> **Estado:** 🟡 PENDIENTE cierre F4-FIX1  
> **Última actualización:** 2026-05-30

---

## 1 · Estado actual y por qué este doc está pendiente

F4 entregó arquitectura completa (Feature Store + Baseline + Prophet + LightGBM + Classifier + API + PWA + Push) pero el cierre **NO pasó la auditoría revisor fresco** (Sesión 42):

### Hallazgos bloqueantes

1. **Prophet MAPE 3,540%.** No es "peor que baseline" — es modelo/métrica roto. Probable división por cero en demanda intermitente (días con `actual=0` infla MAPE al infinito), Prophet sin `floor=0`, o entrenamiento de SKUs con < 30 puntos.
2. **Classifier F1 0.9924** sospechoso de data leakage o desbalance no manejado. El reporte F4-B no documenta target distribution, split temporal explícito ni top-10 features.

### Observaciones

3. F4-C cerró con FakeRepos en producción en lugar de validar contra Gold real.
4. R10 (PC Windows offline) "se documenta como stale" sin alertar al usuario.
5. Sin ADR del split temporal.

### Plan correctivo

F4-FIX1 abierta con 3 sprints paralelos. Ver [`docs/plan-f4-fix1.md`](../plan-f4-fix1.md).

**Este entregable se finaliza cuando F4-FIX1 cierre verde.**

---

## 2 · Lo que SÍ sabemos a hoy (anticipo)

### Decisión crítica (sustantiva, no afectada por FIX1)

**Problema de negocio:** la tienda no sabe qué SKUs van a quebrar stock antes que pase. La decisión de reabastecimiento se hace por intuición. Pérdida estimada: ventas perdidas por quiebres + capital atado en SKUs dormidos.

**Decisión:** gestionar inventario con (a) **forecasting de demanda por SKU** a horizontes 7d/14d/30d, (b) **clasificador binario de riesgo de quiebre** que dispara alertas push proactivas.

### Stack ML elegido — [ADR-0016](../decisions/0016-stack-f4.md)

| Componente | Tecnología | Por qué |
|------------|------------|---------|
| Experiment tracking | MLflow (managed Databricks) | Audit trail + comparación reproducible |
| Feature store | Notebook `19_feature_store.py` con lag/rolling/calendar | Una sola fuente para modelos |
| Baseline | Naïve (last value + moving avg) | Sanity check obligatorio |
| Modelo top | Prophet (SKUs con historia larga) | Estacionalidad explícita |
| Modelo cola larga | LightGBM con features lag + categóricos | Maneja cola larga sin sobreentrenar |
| Clasificador | LightGBM binario (quiebre Sí/No a 7d) | Alertas accionables |

### Métricas iniciales reportadas (F4-B antes de FIX1)

> ⚠️ **Estos números están bajo audit.** Se reemplazarán por las métricas honestas post-F4-FIX1.

| Modelo | MAPE | sMAPE | WAPE | SKUs evaluados |
|--------|------|-------|------|----------------|
| Prophet | 3,540.25% | 151.38% | 2,326.58% | 91 |
| LightGBM | 72.76% | 48.35% | 59.17% | 66 |
| Baseline | 43.72% | 59.98% | 45.83% | 4,343 |

Best model por SKU: Baseline 93.6% / Prophet 4.9% / LightGBM 1.5%.

**Conclusión PROVISIONAL** (a ratificar tras FIX1):

> El dataset tiene 6,339 facturas distribuidas en 6,185 SKUs (~1 venta promedio por SKU). La **cola larga no tiene historia suficiente** para forecasting confiable por SKU individual. Esto NO es una falla del enfoque — es una limitación del dato. La recomendación operacional es:
> 1. Forecasting por SKU solo para los top-100 con `≥ 30 ventas` (los que entran a Prophet/LightGBM).
> 2. **Agregación por categoría/familia** para la cola larga (extender a F6).
> 3. Clasificador de quiebre como tier prioritario — métricas válidas en cualquier caso (con audit honesto post-FIX1).

### Classifier de quiebre

- Target: `(stock_actual / venta_promedio_7d) < 7` → quiebre probable en 7d.
- Features: lag de ventas, rolling 7d/30d, stock actual, días dormido, ABC class, calendar (mes/día semana).
- Output: 69 alertas registradas en `gold.alertas_quiebre` (a re-evaluar post-FIX1).

---

## 3 · Arquitectura predictiva

```
gold.feature_store_sku (snapshot diario)
         │
         ├─→ infra/run_baseline.py       → gold.forecast_baseline_sku
         ├─→ infra/run_forecast_prophet  → gold.forecast_prophet_sku
         ├─→ infra/run_forecast_lightgbm → gold.forecast_lightgbm_sku
         ├─→ infra/run_classifier_stockout → gold.alertas_quiebre
         └─→ infra/run_evaluate_models   → gold.model_evaluation
                                                │
                                                ▼
                                  MLflow tracking + selección best model por SKU
                                                │
                                                ▼
                                  FastAPI /forecast/* + /alerts/*
                                                │
                                                ▼
                                  PWA /forecasts + /alertas + push notifications
```

---

## 4 · Cómo cumple Módulo 3 (ética IA)

### Decisiones de gobierno ML — para cubrir tras FIX1

| Aspecto | Decisión |
|---------|----------|
| Predicciones son **sugerencias revisables**, no decisiones autónomas | Regla de oro del proyecto |
| User en PWA ve recomendación + justificación + "marcar como revisada" | UI design |
| No se compra ni se reordena sin que el operador apruebe | Decisión humana en loop |
| Auditoría: cada predicción quedará registrada con `model_version` + `prediction_date` + `actual` (cuando se sepa) | Para drift monitoring |
| PII: no se entrenan modelos con datos personales de clientes — solo agregados | Habeas Data Colombia |

---

## 5 · Plan de cierre E4 (tras F4-FIX1)

Una vez F4-FIX1 cierre verde, este doc agregará:

- [ ] Métricas honestas finales (WAPE excluyendo ceros + sMAPE + cobertura por SKU)
- [ ] Tabla de SKUs evaluados con `history_length` + `% zeros`
- [ ] Reporte classifier con 3 secciones obligatorias (target dist, split temporal, top-10 features)
- [ ] [ADR-0017](../decisions/) split temporal + métricas intermitentes
- [ ] Lecciones aprendidas — el documento [`docs/predict/lecciones-aprendidas-f4.md`](../predict/lecciones-aprendidas-f4.md) (a crear por Dev A en FIX1) sustenta el mensaje académico honesto
- [ ] Capturas PWA con datos reales (no FakeRepos)
- [ ] StaleDataBanner activo cuando freshness > 24h (R10 mitigada de verdad)
- [ ] Evidencia E2E push notification recibida

---

## 6 · Defensa académica (preliminar)

### Pregunta de defensa esperada

> "¿Por qué Prophet no funcionó?"

### Respuesta honesta (anticipo, ratificación post-FIX1)

Prophet NO falló — el **dataset por SKU es insuficiente para que Prophet aprenda estacionalidad**. La cola larga del catálogo de MotoShop tiene una distribución donde ~85% de los SKUs tienen < 10 ventas en 22 meses. Un modelo que asume estacionalidad anual sobre esa esparsidad no puede aprender nada útil — su MAPE infla por división por cero en días sin venta. El insight académico es que:

1. **Forecasting por SKU** requiere granularidad de demanda densa.
2. **Para cola larga**, agregación por categoría o probabilistic forecasting (cuantiles) es la dirección correcta.
3. **Baseline ganando en 93.6%** es la métrica más honesta que podemos reportar — y refleja la realidad del negocio.

Esto se materializa formalmente en [`docs/predict/lecciones-aprendidas-f4.md`](../predict/lecciones-aprendidas-f4.md) (a crear por Dev A en FIX1).

---

## 7 · Limitaciones conscientes

- **Dataset:** 22 meses con cola larga limita modelos por SKU individual.
- **Compute Free Edition:** sin clusters, train batch nocturno.
- **PC Windows local:** R10 — predicciones potencialmente sobre datos stale si PC offline > 24h (mitigación con StaleDataBanner en FIX1).
- **Sin walk-forward validation:** split temporal único train/test — mejora futura para F6.
- **Drift monitoring no implementado:** F6.

---

## 8 · Estado pre-FIX1 (snapshot honesto)

| Componente | Estado | Notas |
|------------|--------|-------|
| Feature store | ✅ Implementado | `notebooks/gold/19_feature_store.py` |
| Baseline | ✅ Operativo | MLflow runs registrados |
| Prophet | 🔴 Métricas rotas (FIX1) | MAPE 3540% bajo audit |
| LightGBM | 🟡 Mejor que Prophet pero peor que baseline | Audit pendiente |
| Classifier | 🔴 F1 0.99 sospechoso (FIX1) | Audit pendiente |
| MLflow | ✅ 3 experimentos | Tracking funcional |
| Evaluation | 🟡 Métricas a corregir | `v_model_evaluation_20260530_013855.md` |
| API `/forecast/*` | 🟡 Con FakeRepos (FIX1) | Reemplazar por Real |
| API `/alerts/*` | 🟡 Con FakeRepos (FIX1) | Reemplazar por Real |
| PWA `/forecasts` | 🟡 Sin StaleDataBanner (FIX1) | Agregar |
| PWA `/alertas` | 🟡 Sin StaleDataBanner (FIX1) | Agregar |
| Push notifications | ✅ Sender implementado | `motoshop-app/api/.../push/` |
| Tests | ✅ 97/97 OK | Pero con Fakes — re-validar con Real |

**Veredicto del revisor:** F4 no está cerrada. F4-FIX1 abierta con plan detallado. Cuando cierre, E4 se ratifica.
