# Evaluación Forecasting por Categoría — 20260530

**Fecha:** 2026-05-30
**Sprint:** F6-B · Dev B
**Ejecutado en:** Databricks SQL Warehouse (43bc044eaef4cca4) + Prophet local

---

## Resumen

| Modelo | WAPE | vs Baseline-SKU (45.83%) |
|--------|------|--------------------------|
| Baseline-SKU (F4-FIX1) | **45.83%** | — (referencia) |
| Baseline-Categoría (IV2) | **34.37%** | ✅ **SUPERA** (−11.46 pp) |
| Baseline-Categoría (global) | **34.35%** | ✅ SUPERA |
| Prophet-Categoría (IV2 test) | **38.59%** | ❌ NO supera baseline-categoría |

---

## Cobertura

| Métrica | Baseline-SKU | Baseline-Categoría | Mejora |
|---------|-------------|-------------------|--------|
| Entidades totales | 4,392 SKUs | 3 categorías | — |
| Elegibles (≥90d) | 31 SKUs (0.7%) | 1 categoría (33.3%) | ⚠️ Baja cardinalidad |
| Categorías reales | — | IV2, IV4, SIN_GRUPO | Solo 3 |

---

## WAPE por Categoría (baseline)

| Categoría | Días | Ventas totales | WAPE % | Elegible? |
|-----------|------|----------------|--------|-----------|
| IV2 | 636 | 36,093 | 34.37% | ✅ (636d ≥ 90d) |
| SIN_GRUPO | 38 | 42 | 16.72% | ❌ (< 90d) |
| IV4 | 11 | 15 | 40.36% | ❌ (< 90d) |

---

## Prophet por Categoría (IV2 — única elegible)

| Métrica | Valor |
|---------|-------|
| Train | 508 días (2024-07-27 → 2026-01-08) |
| Test | 127 días (2026-01-09 → 2026-05-28) |
| WAPE Prophet (test) | 38.59% |
| WAPE Baseline (test) | 32.52% |
| Prophet supera baseline? | ❌ NO |

---

## Verificación de Hipótesis

| Hipótesis | Resultado | Evidencia |
|-----------|-----------|-----------|
| **H1:** Agregación por categoría supera baseline-SKU | ✅ **VALIDADA** | Baseline-Categoría 34.37% < Baseline-SKU 45.83% |
| **H2:** Prophet sobre agregado supera baseline | ❌ NO VALIDADA | Prophet 38.59% > Baseline 32.52% en test set |

**Implicación H1:** El forecasting a nivel categoría es superior al baseline-SKU y debe ser el modelo de producción. La mejora de ~11pp es significativa.

**Implicación H2:** Prophet no funciona para este dominio, ni siquiera a nivel agregado. La estacionalidad semanal/mensual en repuestos de moto no es lo suficientemente fuerte.

**Hallazgo adicional:** `cod_grupo` tiene solo 3 valores distintos en sgHermes (IV2, IV4, SIN_GRUPO). La categoría IV2 concentra >99% de las ventas. Para F7+ se recomienda explorar `cod_linea1` (familia) para más granularidad.

---

## Decisión

| Criterio | Estado |
|----------|--------|
| ADR-0020 | **Proposed → Accepted** |
| Forecast de producción | **Cambiar a nivel categoría** |
| Prophet | **Descartado** (no supera baseline ni a nivel agregado) |
| Próximo paso F7+ | Explorar `cod_linea1` para jerarquía categoría→familia |

---

## WAPE por Mes (Baseline-Categoría)

| Mes | WAPE % | Mes | WAPE % |
|-----|--------|-----|--------|
| 2024-07 | 27.59 | 2025-01 | 42.04 |
| 2024-08 | 33.01 | 2025-02 | 35.59 |
| 2024-09 | 38.43 | 2025-03 | 41.93 |
| 2024-10 | 44.05 | 2025-04 | 32.11 |
| 2024-11 | 36.44 | 2025-05 | 24.82 |
| 2024-12 | 45.65 | 2025-06 | 35.44 |
| 2025-07 | 29.63 | 2025-11 | 36.61 |
| 2025-08 | 30.60 | 2025-12 | 34.27 |
| 2025-09 | 35.02 | 2026-01 | 32.24 |
| 2025-10 | 30.15 | 2026-02 | 28.64 |
| 2026-03 | 34.21 | 2026-05 | 23.32 |
| 2026-04 | 39.51 | | |

---

*Generado por ejecución directa en Databricks + Prophet local · 20260530*
