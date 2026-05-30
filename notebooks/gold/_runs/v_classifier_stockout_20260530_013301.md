# Classifier Stockout F4-B — 20260530_013301

Fecha: 2026-05-30T01:33:36.411587+00:00
Warehouse: 43bc044eaef4cca4

---

## Métricas

| Métrica | Valor |
|---------|-------|
| F1 | 0.9924 |
| Precision | 0.9848 |
| Recall | 1.0 |
| Train rows | 2072 |
| Test rows | 889 |

## Feature Importance (Top-10)

| Feature | Importance |
|---------|-----------|
| media_movil_7d | 1403 |
| stock_actual | 964 |
| lag_7d | 273 |
| media_movil_14d | 272 |
| dia_semana | 268 |
| media_movil_28d | 255 |
| cat_C | 216 |
| mes | 179 |
| demanda_diaria | 166 |
| lag_28d | 156 |

## Alertas por urgencia

| Urgencia | Cantidad |
|----------|----------|
| alta | 69 |
| media | 0 |
| baja | 0 |

## Top-10 alertas más críticas

| SKU | Stock | Demanda | Días hasta quiebre | Urgencia |
|-----|-------|---------|-------------------|----------|
| 02_00002 / MF-MAGX5L | 0.0 | 1.0 | 0 | alta |
| 02_00017 / MF-YT7B-B | 0.0 | 1.0 | 0 | alta |
| 0357 | 1.0 | 2.1 | 0 | alta |
| 04Q154M | 0.0 | 1.1 | 0 | alta |
| 0742 | 1.0 | 2.4 | 0 | alta |
| 11034057 | 0.0 | 1.0 | 0 | alta |
| 12209-GB4-685S | 2.0 | 4.6 | 0 | alta |
| 16914 | 0.0 | 1.0 | 0 | alta |
| 1702 | 0.0 | 2.5 | 0 | alta |
| 1703 | 1.0 | 2.1 | 0 | alta |

## MLflow

Run ID: `b945a70f0f6c4c57bf48a982c214b98e`
Modelo: stockout_classifier
