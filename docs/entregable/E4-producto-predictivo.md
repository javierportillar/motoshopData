# E4 · Producto predictivo (Forecasting + Alertas de quiebre)

> **Curso:** Big Data y Transformación Digital del Negocio · UAO 2025-2  
> **Módulo cubierto:** 3 (analítica predictiva + ética IA)  
> **Estado:** ✅ Listo (cerrado con F4-FIX1 — Sesión 43)  
> **Última actualización:** 2026-05-30

---

## 1 · Resumen ejecutivo

F4 implementó arquitectura completa de forecasting de demanda + clasificador binario de quiebre + API + PWA + push notifications. La auditoría revisor fresco (F4-FIX1) corrigió métricas engañosas y target leakage. **Conclusión académica final, honesta:**

> El dataset de MotoShop (6,339 facturas / 6,185 SKUs con cola larga) **es insuficiente para forecasting por SKU individual**. El baseline (media móvil) supera a Prophet y LightGBM en el **97.9%** de los SKUs. Esto NO es una falla del enfoque ML — es la limitación del dato. La recomendación operativa concreta es **agregación por categoría/familia** en F5/F6, no por SKU individual.

Esta conclusión NO es una decepción: es **descubrimiento técnico válido** que el proyecto entrega con evidencia versionada.

---

## 2 · Decisión crítica (Módulo 3)

**Problema de negocio:** la tienda no sabe qué SKUs van a quebrar antes de que pase. La decisión de reabastecimiento se hace por intuición.

**Decisión técnica original:** 
- (a) forecasting de demanda por SKU a horizontes 7d/14d/30d con Prophet (top SKUs) + LightGBM (cola larga);
- (b) clasificador binario de quiebre que dispara alertas push proactivas.

**Decisión técnica final post-FIX1:**
- (a) **Baseline (media móvil)** como modelo de producción en el 97.9% de los SKUs. Prophet y LightGBM se mantienen en el pipeline solo como benchmark (R14 los remueve en F5).
- (b) **Classifier binario de quiebre con F1 = 0.536** (sin target leakage) — útil para priorizar atención del operador, no para reemplazar su criterio.

---

## 3 · Stack ML — [ADR-0016](../decisions/0016-stack-f4.md) + [ADR-0017](../decisions/0017-split-temporal-metricas-intermitentes.md)

| Componente | Tecnología | Estado |
|------------|------------|--------|
| Experiment tracking | MLflow (managed Databricks) | ✅ 3+ runs registrados |
| Feature store | `notebooks/gold/19_feature_store.py` con lag/rolling/calendar | ✅ 4,392 SKUs |
| Baseline | Naïve (media móvil) | ✅ Champion 97.9% SKUs |
| Forecasting top | Prophet (SKUs ≥ 90d historia + ≥ 30 ventas) | 🟡 31 SKUs elegibles, WAPE 864% — **no recomendado** (R14) |
| Forecasting cola larga | LightGBM con features lag + categóricos | 🟡 Mejor que Prophet pero peor que baseline (R14) |
| Clasificador | LightGBM binario | ✅ F1 = 0.536 con split temporal limpio |
| API serving | FastAPI `/forecast/*` + `/alerts/*` | ✅ RealRepos contra Databricks SQL |
| PWA | Páginas predicciones + alertas + StaleDataBanner | ✅ Match 100% contra Databricks |
| Push | VAPID + suscripciones IndexedDB | ✅ Sender implementado |

---

## 4 · Métricas finales auditadas (post-F4-FIX1)

### 4.1 · Forecasting (WAPE como primaria — ADR-0017)

| Modelo | MAPE | sMAPE | **WAPE (primaria)** | SKUs evaluados | Best model |
|--------|------|-------|---------------------|----------------|-----------|
| **Baseline** | **43.72%** | **59.98%** | **🏆 45.83%** | **4,343 (todos)** | **97.9%** |
| Prophet | 1,325.03% | 114.69% | 864.69% | 31 elegibles | 1.8% |
| LightGBM | 101.55% | 61.16% | 57.13% | 11 evaluados | 0.3% |

**Cobertura del filtro de elegibilidad (DT-F4-FIX1-2):**
- Total SKUs feature store: **4,392**
- SKUs elegibles (≥ 90d + ≥ 30 ventas): **31 (0.7%)**
- SKUs con predicción evaluada: **4,343 (98.9%)** → baseline cubre el resto.

**Distribución por horizonte:**

| Horizon | Prophet | LightGBM | Baseline | Total |
|---------|---------|----------|----------|-------|
| 1d | 0 | 0 | 4,343 | 4,343 |
| 7d | 26 | 5 | 0 | 31 |
| 14d | 27 | 4 | 0 | 31 |
| 30d | 28 | 3 | 0 | 31 |

Evidencia: [`v_model_evaluation_20260530_113116.md`](../../notebooks/gold/_runs/v_model_evaluation_20260530_113116.md) · MLflow run `eb210cc82a614a06a1406d141c4f8c18`.

### 4.2 · Classifier de quiebre (split temporal — ADR-0017)

| Métrica | Valor |
|---------|-------|
| **F1** | **0.536** |
| Precision | 0.5492 |
| Recall | 0.5234 |
| Train rows | 1,237 (89 quiebres = 7.2%) |
| Test rows | 1,724 (128 quiebres = 7.4%) |

**Split temporal estricto (ADR-0017):**
- Train: 2026-02-27 → 2026-04-01
- Test: 2026-04-02 → 2026-05-28
- **0 días de overlap.** No data leakage.

**Top-10 feature importances (sin `stock_actual` para evitar target leak):**

| # | Feature | Importance |
|---|---------|-----------|
| 1 | dia_semana | 2,660 |
| 2 | media_movil_28d | 1,268 |
| 3 | media_movil_7d | 933 |
| 4 | lag_7d | 745 |
| 5 | media_movil_14d | 708 |
| 6 | lag_14d | 660 |
| 7 | demanda_diaria | 371 |
| 8 | cat_A | 360 |
| 9 | cat_C | 270 |
| 10 | lag_28d | 146 |

**Alertas generadas:** 46 con urgencia "alta" (0 "media", 0 "baja"). Match 10/10 SKUs entre Databricks SQL y PWA.

Evidencia: [`v_classifier_stockout_20260530_113711.md`](../../notebooks/gold/_runs/v_classifier_stockout_20260530_113711.md) · MLflow run `aafe52359a824749ac07a08aa6ccf9e0`.

---

## 5 · El "antes vs después" de F4-FIX1 — defensa académica

| Métrica | F4-B (reportado mal) | F4-FIX1 (honesto) | Causa raíz |
|---------|----------------------|-------------------|------------|
| Prophet MAPE | 3,540% | 1,325% MAPE + WAPE 864% (primaria) | MAPE divide por `actual` individual → infla en demanda intermitente |
| LightGBM MAPE | 72.76% | 101.55% / WAPE 57.13% | Mismo problema MAPE |
| Classifier F1 | 0.9924 | 0.536 | Target leakage: `stock_actual` era feature Y definía el target |
| Cobertura modelo ML | 4,343 SKUs evaluados | 31 elegibles | Sin filtro: SKUs con 1-3 ventas se "evaluaban" |
| Split | Random stratified | Temporal estricto | Random mezcla mismas fechas en train/test |
| Conclusión académica | "Modelos no superan baseline" (vago) | "Dataset insuficiente para forecasting por SKU; baseline gana 97.9%; recomendación: agregar a F6" (accionable) | Investigar causa raíz, no aceptarla |

---

## 6 · Cómo cumple Módulo 3 (ética IA)

| Aspecto | Implementación |
|---------|----------------|
| Predicciones son **sugerencias revisables**, no decisiones autónomas | Regla de oro del proyecto. Operador siempre tiene la última palabra. |
| PWA muestra recomendación + justificación (urgencia + días estimados) | Implementado en `/alerts` |
| StaleDataBanner alerta al usuario si datos > 24h viejos | Implementado (R13 ✅) |
| No se reordena ni se compra sin que el operador apruebe | Decisión de diseño UI |
| Auditoría: cada predicción queda registrada con `model_version` + `prediction_date` | Tabla `gold.forecast_demanda_sku` |
| PII: modelos entrenan SOLO sobre agregados, no datos personales | Habeas Data Colombia |
| Modelos no recomendados (Prophet, LightGBM) documentados como tales | ADR-0017 + lecciones |
| Honestidad metodológica: métricas reales, no infladas | ADR-0017 + auditoría revisor fresco |

---

## 7 · Lecciones aprendidas (Módulo 3 — pensamiento crítico)

Sintetizadas de [`docs/lecciones-aprendidas-f4.md`](../lecciones-aprendidas-f4.md):

1. **MAPE miente en demanda intermitente.** WAPE es la métrica correcta.
2. **No evaluar modelos en SKUs que no deberían tener modelo.** Filtro de elegibilidad obligatorio.
3. **Target leakage destruye la evaluación del clasificador.** Si features pueden expresar el target con una operación aritmética, el modelo memoriza la fórmula.
4. **Split aleatorio en datos temporales es leakage.** Siempre split temporal.
5. **Prophet no sirve para este dataset.** Demanda intermitente sin estacionalidad regular.
6. **Métricas honestas (feas) son mejores que métricas lindas.** F1=0.54 con metodología limpia > F1=0.99 con leak.

**Lección de proceso (no solo técnica):** un mismo agente como ejecutor + revisor sin contexto fresco pierde adversarialidad. La auditoría F4-FIX1 con contexto independiente detectó lo que el cierre F4-B aceptó. Esto se materializa en `INICIAR_REVIEWER.md` §3.2 Checks 7-9 (silver↔bronze, sniff test ML, Real vs Fake).

---

## 8 · Limitaciones conscientes (declaradas para defensa)

- **Dataset:** 22 meses de histórico (2024-07 → 2026-05), 6,185 SKUs con cola larga (~85% con < 10 ventas). Insuficiente para forecasting por SKU.
- **Compute Free Edition:** sin clusters; train batch nocturno.
- **PC Windows local:** R10 — predicciones potencialmente stale; mitigado con StaleDataBanner en PWA.
- **Sin walk-forward validation:** split temporal único; mejora futura para F6.
- **Drift monitoring no implementado:** F6.
- **Prophet/LightGBM siguen en el pipeline pese a no superar baseline:** R14 los remueve en F5.

---

## 9 · Evidencia versionada (V-FIX1 completas)

| V | Evidencia | Resultado |
|---|-----------|-----------|
| **V-FIX1-1** | [`v_fix1_prophet_diagnostico_20260530_112831.md`](../../notebooks/gold/_runs/v_fix1_prophet_diagnostico_20260530_112831.md) + [`v_model_evaluation_20260530_113116.md`](../../notebooks/gold/_runs/v_model_evaluation_20260530_113116.md) | ✅ WAPE/sMAPE + filtro 90d+30 ventas |
| **V-FIX1-2** | [`v_classifier_stockout_20260530_113711.md`](../../notebooks/gold/_runs/v_classifier_stockout_20260530_113711.md) | ✅ 3 secciones obligatorias |
| **V-FIX1-3** | Tabla §4 + [`lecciones-aprendidas-f4.md`](../lecciones-aprendidas-f4.md) | ✅ Métricas honestas + conclusión |
| **V-FIX1-4** | [`docs/decisions/0017-split-temporal-metricas-intermitentes.md`](../decisions/0017-split-temporal-metricas-intermitentes.md) | ✅ Accepted |
| **V-FIX1-5** | [`v_fix1_forecast_real.md`](../../motoshop-app/web/_runs/v_fix1_forecast_real.md) | ✅ Match SQL↔PWA |
| **V-FIX1-6** | [`v_fix1_alertas_real.md`](../../motoshop-app/web/_runs/v_fix1_alertas_real.md) | ✅ 46 alertas match |
| **V-FIX1-7** | [`v_fix1_stale_banner.md`](../../motoshop-app/web/_runs/v_fix1_stale_banner.md) | ✅ 4/4 E2E |
| **V-FIX1-8** | [`INICIAR_REVIEWER.md`](../../INICIAR_REVIEWER.md) §3.2 Checks 7-9 | ✅ |

---

## 10 · Riesgos / deudas remanentes hacia F5/F6

- **R14** Prophet/LightGBM en el pipeline pese a no superar baseline → trigger remover en F5 (primer sprint).
- **R15** `users.yaml` con `FG28` propagada → trigger F6 hardening (rotación + cleanup).
- **Drift monitoring** → F6.
- **Walk-forward validation** → F6.
- **Forecasting por categoría/familia** → F6+ (recomendación académica concreta).
