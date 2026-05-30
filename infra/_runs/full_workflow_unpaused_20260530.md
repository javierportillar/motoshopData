# Full Workflow Unificado · motoshop_full_workflow

**Fecha:** 2026-05-30
**Sprint:** F6-A · A2 + A3
**Job ID:** 272152121206178
**Run ID:** 434323895356920 (primera corrida manual)
**Tasks:** 25 (bronze → silver → gold → drift)
**Schedule:** `0 0 19 * * ?` (19:00 COL) — PAUSED inicialmente

---

## ✅ A2 completado

- `infra/create_full_workflow.py` creado y ejecutado.
- Jobs anteriores eliminados:
  - `motoshop_bronze_silver` (ID 242284930182920) ✅
  - `motoshop_gold_workflow` (ID 1019412916873880) ✅
- Nuevo job `motoshop_full_workflow` (ID 272152121206178) creado ✅
- 25 tareas secuenciales definidas
- Notebooks subidos: 36/36 (via `upload_all_notebooks.py`)

## ⏳ A3 en progreso

Primera corrida manual disparada. Estado al momento de este documento:

| Métrica | Valor |
|---------|-------|
| Tasks totales | 25 |
| ✅ Success | 17/25 (bronze_ingest → silver dims/facts/quality → gold marts → feature store) |
| ⏳ Running | gold_baseline |
| ⬜ Pending | gold_classifier → gold_quality → gold_validate → gold_drift |

## ⏸️ Estado del schedule

**UNPAUSED** ✅ — Schedule nocturno activo: `0 0 19 * * ?` (19:00 COL, America/Bogota).

## 📌 Pasos siguientes

1. ✅ Workflow creado y UNPAUSED.
2. ⏳ Esperar que la primera corrida complete exitosamente.
3. ⬜ Verificar R7: `system.workflows.runs` con ≥7 corridas exitosas (se acumulará con el schedule nocturno).
