# Forecast LightGBM — 20260529_235507

Fecha: 2026-05-30T00:00:14.774138+00:00

---

## Summary

| Métrica | Valor |
|---------|-------|
| Training rows | 25857 |
| Test rows | 4589 |
| SKUs in forecast | 3511 |
| Total predictions | 10533 |
| MAPE global (avg h7/14/30) | 72.7% |
| Test MAPE (one-step) | 31.49 |
| Residual std (CI) | 1.0615 |
| Baseline MAPE (F4-A naive) | 43.72% |

---

## Configuration

| Parámetro | Valor |
|-----------|-------|
| num_leaves | 31 |
| learning_rate | 0.05 |
| n_estimators | 500 |
| early_stopping_rounds | 50 |
| best_iteration | 119 |
| model_version | lightgbm_v1 |
| Total features | 14 |

---

## Results by Horizon

| Horizon | MAPE | sMAPE | Obs |
|---------|------|-------|-----|
| 7 | 64.66% | 50.34% | 21 |
| 14 | 66.81% | 45.09% | 20 |
| 30 | 86.64% | 50.16% | 30 |

---

## Feature Importance (Top 10)

| Feature | Importance |
|---------|-----------|
| media_movil_28d | 612 |
| media_movil_14d | 559 |
| media_movil_7d | 501 |
| mes | 330 |
| stock_actual | 328 |
| dias_sin_venta | 264 |
| lag_14d | 260 |
| lag_7d | 253 |
| lag_28d | 220 |
| dia_semana | 201 |

---

## Verification (V-M2)

❌ **LightGBM MAPE (72.7%) no es menor que 43.7% (baseline) — revisar.**

---

## MLflow

⚠️ MLflow no disponible o falló el logging.