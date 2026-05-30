# Classifier Stockout F4-B — 20260530_113711

Fecha: 2026-05-30T11:37:25.568839+00:00
Warehouse: 43bc044eaef4cca4

---

## Split temporal (ADR-0017)

| | Train | Test |
|---|-------|------|
| Fechas | 2026-02-27 → 2026-04-01 | 2026-04-02 → 2026-05-28 |
| Filas | 1237 | 1724 |
| Quiebres | 89 | 128 |
| No leakage | ✅ | — |

> **ADR-0017**: Split estrictamente temporal. Train y test NO comparten fechas.
> `stock_actual` excluido de features para evitar target leakage.

---

## Métricas

| Métrica | Valor |
|---------|-------|
| F1 | 0.536 |
| Precision | 0.5492 |
| Recall | 0.5234 |
| Train rows | 1237 |
| Test rows | 1724 |

## Feature Importance (Top-10)

| Feature | Importance |
|---------|-----------|
| dia_semana | 2660 |
| media_movil_28d | 1268 |
| media_movil_7d | 933 |
| lag_7d | 745 |
| media_movil_14d | 708 |
| lag_14d | 660 |
| demanda_diaria | 371 |
| cat_A | 360 |
| cat_C | 270 |
| lag_28d | 146 |

## Alertas por urgencia

| Urgencia | Cantidad |
|----------|----------|
| alta | 46 |
| media | 0 |
| baja | 0 |

## Top-10 alertas más críticas

| SKU | Stock | Demanda | Días hasta quiebre | Urgencia |
|-----|-------|---------|-------------------|----------|
| 02_00002 / MF-MAGX5L | 0.0 | 1.0 | 0 | alta |
| 04Q154M | 0.0 | 1.1 | 0 | alta |
| 1703 | 1.0 | 2.1 | 0 | alta |
| 1887 | 2.0 | 4.1 | 0 | alta |
| 19SA01-CAJAX1 | 1.0 | 2.2 | 0 | alta |
| 2038 | 1.0 | 6.0 | 0 | alta |
| 21C-E3440-00 | 1.0 | 4.0 | 0 | alta |
| 278 | 1.0 | 2.4 | 0 | alta |
| 40R108 | 1.0 | 2.4 | 0 | alta |
| 55182 | 1.0 | 4.0 | 0 | alta |

## MLflow

Run ID: `aafe52359a824749ac07a08aa6ccf9e0`
Modelo: stockout_classifier
