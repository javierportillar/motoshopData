# Model Evaluation — 20260530_003717

Fecha: 2026-05-30T00:41:51.808337+00:00

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
- V-M8: MLflow experiments created → ✅
  - MLflow run ID: af854e0e241e4a87bd3057d7e71929f1