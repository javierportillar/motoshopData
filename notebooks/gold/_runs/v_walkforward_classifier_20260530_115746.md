# Walk-forward Classifier Evaluation · 20260530_115746

**Fecha:** 2026-05-30 11:57:46
**Tipo:** Classifier (LightGBM) — walk-forward con reentrenamiento semanal
**Semanas evaluadas:** 7
**Período:** 2026-04-15 → 2026-05-30
**⚠️ Nota:** F1=1.0 por feature leak — el label depende de `stock_actual < demanda_diaria * 7`,
  y `stock_actual` es también un feature de entrada. No es un resultado realista. Refleja
  que el walk-forward pipeline funciona técnicamente; la métrica honesta requiere
  label independiente (stockout futuro, no actual).

---

## Resultados por semana

| Semana | Inicio | Fin | Train | Test | F1 | Precision | Recall | Status |
|--------|--------|-----|-------|------|----|-----------|--------|--------|
| 2026-04-15_2026-04-21 | 2026-04-15 | 2026-04-21 | 27201 | 224 | 1.0000 | 1.0000 | 1.0000 | OK |
| 2026-04-22_2026-04-28 | 2026-04-22 | 2026-04-28 | 27425 | 219 | 1.0000 | 1.0000 | 1.0000 | OK |
| 2026-04-29_2026-05-05 | 2026-04-29 | 2026-05-05 | 27644 | 202 | 1.0000 | 1.0000 | 1.0000 | OK |
| 2026-05-06_2026-05-12 | 2026-05-06 | 2026-05-12 | 27846 | 218 | 1.0000 | 1.0000 | 1.0000 | OK |
| 2026-05-13_2026-05-19 | 2026-05-13 | 2026-05-19 | 28064 | 203 | 1.0000 | 1.0000 | 1.0000 | OK |
| 2026-05-20_2026-05-26 | 2026-05-20 | 2026-05-26 | 28267 | 235 | 1.0000 | 1.0000 | 1.0000 | OK |
| 2026-05-27_2026-05-30 | 2026-05-27 | 2026-05-30 | 28502 | 64 | 1.0000 | 1.0000 | 1.0000 | OK |

## Resumen

- **F1 promedio:** 1.0000
- **F1 min:** 1.0000
- **F1 max:** 1.0000
- **F1 std:** 0.0000

### Interpretación

- Si F1 promedio ≥ 0.5: el classifier es estable a través del tiempo.
- Si F1 baja en semanas recientes: puede haber drift (el modelo se degrada).
- Si F1 sube: el modelo mejora con más datos de entrenamiento (esperable).

---

## Detalle

```json
[
  {
    "week": "2026-04-15_2026-04-21",
    "week_start": "2026-04-15",
    "week_end": "2026-04-21",
    "train_size": 27201,
    "test_size": 224,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  },
  {
    "week": "2026-04-22_2026-04-28",
    "week_start": "2026-04-22",
    "week_end": "2026-04-28",
    "train_size": 27425,
    "test_size": 219,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  },
  {
    "week": "2026-04-29_2026-05-05",
    "week_start": "2026-04-29",
    "week_end": "2026-05-05",
    "train_size": 27644,
    "test_size": 202,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  },
  {
    "week": "2026-05-06_2026-05-12",
    "week_start": "2026-05-06",
    "week_end": "2026-05-12",
    "train_size": 27846,
    "test_size": 218,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  },
  {
    "week": "2026-05-13_2026-05-19",
    "week_start": "2026-05-13",
    "week_end": "2026-05-19",
    "train_size": 28064,
    "test_size": 203,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  },
  {
    "week": "2026-05-20_2026-05-26",
    "week_start": "2026-05-20",
    "week_end": "2026-05-26",
    "train_size": 28267,
    "test_size": 235,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  },
  {
    "week": "2026-05-27_2026-05-30",
    "week_start": "2026-05-27",
    "week_end": "2026-05-30",
    "train_size": 28502,
    "test_size": 64,
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
    "status": "OK"
  }
]
```