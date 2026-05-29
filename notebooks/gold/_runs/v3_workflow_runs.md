# V3 — Workflow 7 corridas

Fecha: 2026-05-29  
Workflow: `motoshop_gold_workflow` (ID: 1006009768125248)  
Schedule: `0 30 2 * * ?` (02:30 COL) — **UNPAUSED**  
Tasks: 20 (bronze → silver → gold/10..14 → gold/20 → gold/30)

## Historial de corridas

| # | Fecha | Run ID | Estado | Resultado |
|---|-------|--------|--------|-----------|
| 1 | 2026-05-29 | 836539038019042 | TERMINATED | PENDING — verificar en Databricks UI |

## Notas

- El schedule nocturno está UNPAUSED desde el 2026-05-29.
- Las corridas nocturnas empezarán a acumularse a partir de las 02:30 COL del día siguiente.
- Las gold notebooks ya fueron validadas: **57/57 statements OK** en ejecución manual (ver `run_gold_20260529_191320.md`).
- El workflow orquesta la pipeline completa: bronze ingestion → silver notebooks (6 dims + 5 facts + quality) → gold marts (5) → quality → validate.
- **V3 se considerará cerrada** tras 7 corridas nocturnas consecutivas exitosas (se espera >95% tasa de éxito).
- Para acelerar, se puede forzar ejecución manual desde Databricks UI → Workflows → `motoshop_gold_workflow` → Run Now.
