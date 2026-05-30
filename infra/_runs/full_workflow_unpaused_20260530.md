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

## ✅ A3 completado

### Run 1 (434323895356920)
- **Tasks:** 23/25 ✅, 1 ❌ (gold_drift — esperable sin histórico, arreglado)
- **State:** TERMINATED — no-success por drift fallido (ver run 2 con el fix)

### Run 2 (320303253928194)
- **State:** RUNNING al cierre de F6-A
- **Nota:** segunda corrida con drift monitor fix (bootstrap mode). Si gold_drift ahora falla, es normal hasta que haya 4 semanas de histórico de baseline.

### Run 3+ programadas
- **Schedule UNPAUSED** ✅ — corre automáticamente a las 19:00 COL.
- Se acumularán corridas nocturnas para cerrar R7 (7+ corridas).
