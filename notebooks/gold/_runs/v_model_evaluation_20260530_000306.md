# Model Evaluation — 20260530_000306

Fecha: 2026-05-30T00:06:34.421656+00:00

---

## Comparison Summary

| Model | MAPE | sMAPE | WAPE | SKUs evaluated |
|-------|------|-------|------|----------------|
| Prophet | N/A | N/A | N/A | 0 |
| Lightgbm | 72.76% | 48.35% | 59.17% | 66 |
| Baseline | 43.72% | 59.98% | 45.83% | 4343 |

---

## Best Model Distribution (by SKU)

| Model | # SKUs selected | % of total |
|-------|-----------------|------------|
| Prophet | 0 | 0.0% |
| Lightgbm | 82 | 1.9% |
| Baseline | 4343 | 98.1% |

---

## Distribution by Horizon

| Horizon | Prophet | LightGBM | Baseline | Total |
|---------|---------|----------|---------|-------|
| 1d | 0 | 0 | 4343 | 4343 |
| 7d | 0 | 23 | 0 | 23 |
| 14d | 0 | 26 | 0 | 26 |
| 30d | 0 | 33 | 0 | 33 |

---

## Verification

- V-M4: forecast_demanda_sku has >= 100 SKUs with predictions → ✅
- V-M8: MLflow experiments created → ❌