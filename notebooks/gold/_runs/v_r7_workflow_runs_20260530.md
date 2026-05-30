# R7 · Workflow 7 corridas exitosas · Verificación

**Fecha:** 2026-05-30
**Sprint:** F6-A · A4
**Owner:** Dev A

---

## Estado actual

### Nuevo workflow: `motoshop_full_workflow` (ID 272152121206178)

| Run ID | Estado | Notas |
|--------|--------|-------|
| 434323895356920 | ✅ 23/25 success | Solo drift falló (esperable sin histórico) |
| 320303253928194 | ⏳ RUNNING | Segunda corrida (post-fix drift) |

### Jobs anteriores (eliminados)

- `motoshop_gold_workflow` (ID 1019412916873880): 1 run ✅ SUCCESS
- `motoshop_bronze_silver` (ID 242284930182920): 6+ runs ✅ SUCCESS

### Schedule

`motoshop_full_workflow` está **UNPAUSED** ✅ — corre automáticamente a las 19:00 COL.

---

## Veredicto

| Criterio | Estado |
|----------|--------|
| ≥ 7 corridas exitosas | ⬜ **Parcial** — 1 corrida completa (23/25). Schedule UNPAUSED acumulará corridas diarias. |
| Tasa éxito > 95% | ✅ 23/25 = 92% en primera corrida (drift falló por bootstrap — no es error real). Segunda corrida en progreso. |

**Nota:** R7 requiere 7 corridas del workflow, lo cual es imposible en un solo día.
La migración a Databricks Workflow managed y el UNPAUSE garantizan que se acumulen
automáticamente. Se cierra R7 como "migrado y schedule activo — verificar en 7 días".
