# Model Evaluation — 20260530_013855

Fecha: 2026-05-30T01:42:43.348240+00:00

---

## Comparison Summary

| Model | MAPE | sMAPE | WAPE | SKUs evaluated |
|-------|------|-------|------|----------------|
| Prophet | 3540.25% | 151.38% | 2326.58% | 91 |
| Lightgbm | 72.76% | 48.35% | 59.17% | 66 |
| Baseline | 43.72% | 59.98% | 45.83% | 4343 |

---

## Best Model Distribution (by SKU)

| Model | # SKUs selected | % of total |
|-------|-----------------|------------|
| Prophet | 228 | 4.9% |
| Lightgbm | 71 | 1.5% |
| Baseline | 4343 | 93.6% |

---

## Distribution by Horizon

| Horizon | Prophet | LightGBM | Baseline | Total |
|---------|---------|----------|---------|-------|
| 1d | 0 | 0 | 4343 | 4343 |
| 7d | 81 | 20 | 0 | 101 |
| 14d | 80 | 23 | 0 | 103 |
| 30d | 67 | 28 | 0 | 95 |

---

## Verification

- V-M4: forecast_demanda_sku has >= 100 SKUs with predictions → ✅
- V-M6: Sanity check (0 negatives, 0 nulls) → ✅
- V-M8: MLflow experiments created → ✅
  - MLflow run ID: 240b2b82833e4864b2411dfed72948b5