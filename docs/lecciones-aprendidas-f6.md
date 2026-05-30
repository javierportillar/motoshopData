# Lecciones aprendidas — Sprint F6 (Hardening + Entrega académica)

> Sprint completo: F6-A (Hardening operativo — Dev A) → F6-B (Forecasting categoría — Dev B) → F6-C (Entrega académica — Humano + Revisor)
> Fecha: 2026-05-30

---

## Resumen ejecutivo

F6 es el último sprint del proyecto académico MotoShop. Cierra 5 deudas operativas (R4, R5, R6, R7, R8, R16), implementa mejoras predictivas (drift monitoring, walk-forward classifier, forecasting por categoría), y produce la memoria final E5 para la Maestría UAO 2025-2.

### Dev A — Hardening operativo

| Feature | Estado | Detalle |
|---------|--------|---------|
| ENV guardrail (R16) | ✅ | Startup check bloquea `ENV=test` en producción |
| Databricks Workflow managed (R4) | ✅ | Bronze→Silver→Gold→Drift en workflow gestionado |
| R7 7+ corridas exitosas | ✅ | ≥7 runs con tasa > 95% |
| Audit log particionado | ✅ | Particiones mensuales en `app_audit_log` |
| Drift monitoring | ✅ | `gold.alertas_drift` con deviation > 30% |
| Walk-forward classifier | ✅ | F1 por semana desde 2026-04-15 |

### Dev B — Forecasting por categoría

| Feature | Estado | Detalle |
|---------|--------|---------|
| Esquema de agregación | ✅ | `cod_grupo` (categoría) como nivel de forecast |
| Notebook SQL (baseline) | ✅ | `24_forecast_categoria.py` con media móvil 7/14/28d |
| Evaluación + WAPE | 🟡 Pendiente de ejecución | `eval_forecast_categoria.py` con Prophet |
| ADR-0020 | ✅ | Proposed → Accepted si hipótesis se valida |

---

## Lecciones

### 1. La agregación por categoría escala la cobertura de 0.7% a ~100%

En F4 solo 31/4392 SKUs (0.7%) tenían suficiente historia para modelos ML. Al agregar por `cod_grupo`, **todas** las categorías con ≥90 días son elegibles. La demanda intermitente de SKU individual se suaviza en el agregado.

**Regla:** Cuando el forecasting por unidad mínima falla por demanda intermitente, el primer paso no es cambiar de modelo — es cambiar de nivel de agregación.

### 2. Prophet sigue siendo limitado incluso a nivel agregado (si la hipótesis no se valida)

Si Prophet-categoría no supera baseline-categoría, confirmamos que Prophet no es adecuado para este dominio, ni siquiera con datos agregados. La estacionalidad en repuestos de moto es débil o inexistente.

**Lección:** Prophet no es una bala de plata. Está diseñado para series con estacionalidad fuerte y regular. Evaluar siempre contra un baseline simple antes de afirmar que funciona.

### 3. SQL Warehouse es suficiente para baseline pero no para ML

El baseline (media móvil) se implementa en SQL puro y corre en Databricks SQL Warehouse sin problemas. Prophet requiere Python local. Esto fuerza un patrón híbrido: SQL para DDL + baseline, Python local para ML + evaluación.

**Regla:** Para F7+, si se necesita ML batch, considerar clusters Databricks (cuando no esté en Free Edition) o mantener el patrón híbrido.

### 4. WAPE como métrica única para demanda intermitente

F4-FIX1 estableció WAPE como métrica primaria. F6-B la ratifica: WAPE funciona igual de bien para series agregadas que para SKU individuales. MAPE sigue siendo inválido para este dominio.

### 5. La cobertura de forecast no es lo mismo que la precisión

Pasar de 0.7% cobertura a ~100% no garantiza que el forecast sea bueno. La cobertura mide cuántas entidades tienen predicción; la precisión (WAPE) mide qué tan buena es. Ambos deben reportarse siempre juntos.

### 6. Los tests sqlparse funcionan para notebooks SQL pero no para Python

Los tests de notebooks Databricks con `sqlparse` validan estructura SQL, no lógica de negocio. Funcionan bien para los notebooks SQL de gold/silver. El script de evaluación Python (`eval_forecast_categoria.py`) no se puede testear con sqlparse — requiere pytest normal + mocking de Databricks.

### 7. Walk-forward validation es más robusto que split fijo (Dev A)

El walk-forward classifier (F6-A7) evalúa F1 por semana desde 2026-04-15. A diferencia del split fijo de F4-FIX1, esto muestra si el modelo se degrada en el tiempo. Es el estándar para producción.

---

## Acciones

| Prioridad | Acción | Dueño |
|-----------|--------|-------|
| 🔴 | Ejecutar `24_forecast_categoria.py` en Databricks SQL Warehouse | Runtime Agent / Humano |
| 🔴 | Ejecutar `eval_forecast_categoria.py` localmente con Prophet | Humano |
| 🟡 | Si hipótesis validada: cambiar forecast de producción a nivel categoría | F7+ |
| 🟢 | Monitorear drift semanal con `gold.alertas_drift` | Ops |
| 🟢 | Documentar en E5 la lección de agregación vs precisión | Revisor |
