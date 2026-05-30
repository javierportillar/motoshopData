# Model Evaluation — 20260530_113116

Fecha: 2026-05-30T11:35:18.954926+00:00

---

## SKU Coverage

- Total SKUs in feature store: 4392
- Eligible SKUs (>= 90d history + >= 30 sales): 31
- SKUs with predictions evaluated: 4343
- Coverage rate: 98.9%

> **DT-F4-FIX1-2**: Only SKUs with >= 90 days of history and >= 30 total sales
> are evaluated with Prophet/LightGBM. Non-eligible SKUs fall back to baseline.

---

## Comparison Summary

> **WAPE is the primary metric** for intermittent demand. MAPE inflates when
> actual sales are small (e.g., actual=1, pred=36 → 3500% MAPE). WAPE avoids this
> by aggregating across all predictions before dividing.

| Model | MAPE | sMAPE | WAPE (primary) | SKUs evaluated |
|-------|------|-------|----------------|----------------|
| Prophet | 1325.03% | 114.69% | 864.69% | 31 |
| Lightgbm | 101.55% | 61.16% | 57.13% | 11 |
| Baseline | 43.72% | 59.98% | 45.83% | 4343 |

---

## Best Model Distribution (by SKU)

| Model | # SKUs selected | % of total |
|-------|-----------------|------------|
| Prophet | 81 | 1.8% |
| Lightgbm | 12 | 0.3% |
| Baseline | 4343 | 97.9% |

---

## Distribution by Horizon

| Horizon | Prophet | LightGBM | Baseline | Total |
|---------|---------|----------|---------|-------|
| 1d | 0 | 0 | 4343 | 4343 |
| 7d | 26 | 5 | 0 | 31 |
| 14d | 27 | 4 | 0 | 31 |
| 30d | 28 | 3 | 0 | 31 |

---

## Verification

- V-M4: forecast_demanda_sku has >= 100 SKUs with predictions → ✅
- V-M6: Sanity check (0 negatives, 0 nulls) → ✅
- V-M8: MLflow experiments created → ✅
  - MLflow run ID: eb210cc82a614a06a1406d141c4f8c18