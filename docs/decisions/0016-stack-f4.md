# ADR-0016: Stack F4 — Predictivo ML

## Status
Proposed · 2026-05-29

## Context

F3 cerrada con 5 marts gold funcionales, 24,374 filas diarias-SKU, 29 meses de historia. F4 debe cumplir el Módulo 3: forecasting de demanda + alertas de quiebre.

**Constraint principal:** Databricks Free Edition no tiene clusters. Compute limitado a serverless notebooks (tiempo mensual limitado) o training local en Mac.

**Constraint de datos:** MySQL `motoshop2024` (sgHermes) está en PC Windows que no siempre está encendido. F4 NO necesita MySQL en tiempo real — training y serving leen de Gold tables en Databricks. Pero la freshness de los datos depende de que el PC haya corrido el dump recientemente.

**Stack heredado:** FastAPI + Next.js + Databricks SQL + Delta Lake. MLflow disponible en workspace Databricks.

---

## Decisiones

### DT-F4-1 · Compute para training

**Decisión:** Local Mac + MLflow remote tracking.

**Alternativas:**
- Serverless notebooks Databricks: tiempo limitado, hard de debug
- Clusters Databricks: no disponibles en Free Edition
- Google Colab: separa compute del repo, קשה de integrar

**Consecuencias:**
- (+) Control total del environment, debug inmediato, sin costo
- (+) MLflow tracking sigue en Databricks workspace
- (-) Requiere instalar prophet/lightgbm en Mac
- (-) Si el dataset crece mucho, puede quedarse corto

---

### DT-F4-2 · Framework de forecasting

**Decisión:** Prophet (top-100 SKUs) + LightGBM (global cola larga).

**Alternativas:**
- ARIMA/SARIMA: no maneja bien múltiples estacionalidades
- statsforecast: más rápido pero menos features
- NeuralProphet: más complejo, poco maduro
- Solo LightGBM: pierde estacionalidad temporal

**Consecuencias:**
- (+) Prophet captura estacionalidad + feriados COL nativamente
- (+) LightGBM captura features cross-SKU (categoría, bodega, rotación)
- (-) Dos frameworks = más dependencias y mantenimiento
- (-) Prophet puede ser lento con >500 SKUs

---

### DT-F4-3 · HPO (hyperparameter optimization)

**Decisión:** Optuna.

**Alternativas:**
- GridSearchCV: exponencial en #params
- RandomSearch: no bayesiano, menos eficiente
- Ray Tune: más pesado, overkill para este volumen

**Consecuencias:**
- (+) Bayesiano, eficiente en tiempo compute
- (+) Integrado con MLflow (mlflow.optuna)
- (-) Una dependencia más

---

### DT-F4-4 · Feature store

**Decisión:** Gold table `gold.feature_store_sku`.

**Alternativas:**
- Feast: overkill para un proyecto de esta escala
- Databricks Feature Store: no disponible en Free
- Features on-the-fly en training: no reutilizable, lento

**Consecuencias:**
- (+) Simple, Delta table, refreshable por workflow
- (+) Reutilizable por Prophet, LightGBM, y classifier
- (-) Manual feature engineering (no auto-features)

---

### DT-F4-5 · Serving de predicciones

**Decisión:** Pre-computed en gold + API lee gold.

**Alternativas:**
- Real-time inference en API: latencia alta, necesita modelo cargado
- Modelo embebido en API: complejidad de deployment
- Databricks Serving: no disponible en Free

**Consecuencias:**
- (+) Latencia < 100ms (query a Delta table)
- (+) Sin dependencia de compute en serving
- (-) Predicciones stale hasta próximo refresh
- (-) No permite inferencia bajo demanda

---

### DT-F4-6 · Clasificador de quiebre

**Decisión:** LightGBM classifier con features de inventario + ventas.

**Alternativas:**
- Reglas estáticas (stock < X): no se adapta por SKU
- Logistic Regression: menos preciso con features no lineales
- Random Forest: más lento, menos interpretable

**Consecuencias:**
- (+) Maneja features no lineales (rotación + stock + tendencia)
- (+) F1 > 0.7 es realista con las features disponibles
- (-) Necesita labeled data (quiebres históricos)

---

### DT-F4-7 · Alertas push

**Decisión:** `pywebpush` en API + service worker existente.

**Alternativas:**
- OneSignal: dependencia externa, costo
- Firebase Cloud Messaging: requiere proyecto Google
- Email only: no es push real

**Consecuencias:**
- (+) Ya hay infra placeholder (API + PWA)
- (+) Sin dependencia externa
- (-) Requiere VAPID keys
- (-) Sin analytics de entrega

---

### DT-F4-8 · Backtest strategy

**Decisión:** Walk-forward validation (train months 1-N, test N+1).

**Alternativas:**
- K-fold random: rompe estructura temporal, data leakage
- Time-series split simple: menos robusto
- Expanding window: más datos de train pero más lento

**Consecuencias:**
- (+) Respeta estructura temporal
- (+) Sin data leakage
- (-) Más lento que k-fold simple

---

### DT-F4-9 · Métricas de evaluación

**Decisión:** MAPE, sMAPE, WAPE por SKU + promedio ponderado.

**Alternativas:**
- MAE: dependiente de escala, no interpretable como porcentaje
- RMSE: penaliza outliers fuertemente
- Solo MAPE: falla cuando valores reales ~ 0

**Consecuencias:**
- (+) MAPE interpretable para negocio
- (+) sMAPE maneja valores cercanos a cero
- (+) WAPE pondera por volumen (SKUs grandes pesan más)

---

### DT-F4-10 · Umbral de quiebre

**Decisión:** `stock_actual < media_demanda_diaria × horizon_días`.

**Alternativas:**
- Stock = 0: tarde demásiado para actuar
- Percentil 10 de distribución: hard de calibrar
- Fixed threshold por categoría: no se adapta por SKU

**Consecuencias:**
- (+) Se adapta a la rotación de cada SKU
- (+) Simple de calcular y explicar
- (-) No cuenta estacionalidad (mejorable en F6)

---

## Consequences Summary

| Aspecto | Impacto |
|---------|---------|
| Compute | Local Mac, sin costo, limitado a ~24K filas |
| Modelos | Prophet + LightGBM (dual framework) |
| Serving | Pre-computed, latencia baja, stale hasta refresh |
| Tracking | MLflow en Databricks workspace |
| Push | pywebpush, sin dependencia externa |
| Testing | Walk-forward, MAPE/sMAPE/WAPE |

## References

- [PLAN.md](../PLAN.md) §Stack — "scikit-learn, lightgbm, prophet, statsforecast + MLflow"
- [ADR-0010](0010-compute-databricks-free.md) — Free Edition limitations
- [ADR-0015](0015-stack-f3.md) — Stack F3 (base para F4)
- [SEGUIMIENTO.md](../SEGUIMIENTO.md) §Fase 4 — Definition of Done
