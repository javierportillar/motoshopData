# Plan F5-FIX1 · Remediación post-auditoría F5

- **Fecha:** 2026-05-30
- **Origen:** Auditoría pre-review con 5 critical + 5 major issues
- **Modo:** paralelo · **2 devs** (Dev T = Frontend, Dev A = Backend/Infra)
- **Duración estimada:** ~2.5h total (~1.5h Dev T, ~1h Dev A)
- **Estado:** 🟡 ABIERTA.

---

## 1 · Issues a resolver

### Critical (bloquean producción)

| ID | Issue | Dev | Archivo(s) |
|----|-------|-----|-----------|
| C-1 | Frontend envía `?date=` pero backend espera `?date_from=&date_to=` | Dev T | `web/lib/api/alertActions.ts` |
| C-2 | Frontend espera `actions[]` pero backend retorna `items[]` | Dev T | `web/lib/api/alertActions.ts` |
| C-3 | Password `Sashita123` hardcodeado en 19 archivos de infra | Dev A | `infra/*.ps1`, `infra/*.py` |
| C-4 | Databricks PAT en handoff markdown | Dev A | docs/handoff-*.md o PENDIENTES.md |
| C-5 | JWT_SECRET de prueba en script de deploy | Dev A | `infra/start_api.ps1` |

### Major

| ID | Issue | Dev | Archivo(s) |
|----|-------|-----|-----------|
| M-1 | Offline queue sin backoff exponencial real | Dev T | `web/lib/offline/queue.ts` |
| M-2 | R14 cleanup incompleto — notebooks gold no archivados | Dev A | `notebooks/gold/`, `docs/archive/` |
| M-3 | Falta ADR-0019 (idempotency + RBAC) | Dev A | `docs/decisions/0019-idempotency-rbac.md` |
| M-4 | Filtros "Esta semana"/"Este mes" ilusorios | Dev T | `web/app/(authenticated)/acciones/page.tsx` |
| M-5 | Modal dice "queda en cola" pero no encola | Dev T | `web/components/alerts/AlertActionModal.tsx` |

---

## 2 · Distribución

### Dev T · Frontend (~1.5h)

```
C-1 + C-2 → alertActions.ts (parámetros + campos)
M-1 → queue.ts (backoff exponencial)
M-4 → acciones/page.tsx (filtros por período)
M-5 → AlertActionModal.tsx (integración offline queue)
```

### Dev A · Backend/Infra (~1h)

```
C-3 → infra/*.ps1 + infra/*.py (mover passwords a .env)
C-4 → docs/ (eliminar PAT de markdown)
C-5 → infra/start_api.ps1 (usar .env)
M-2 → R14 cleanup (archivar notebooks + README)
M-3 → ADR-0019 (documentar idempotency + RBAC)
```

---

## 3 · V-checks

| ID | Verificación | Pass criterion |
|----|-------------|----------------|
| V-F1 | "Mis acciones del día" muestra datos | Página carga con acciones reales de hoy |
| V-F2 | Filtros período funcionan | Hoy/Esta semana/Este mes devuelven subconjuntos |
| V-F3 | Offline queue con backoff | 30s → 1min → 2min → 5min → 15min → 30min (cap 6) |
| V-F4 | Passwords limpios | `grep -r "Sashita123" infra/` devuelve 0 resultados |
| V-F5 | JWT_SECRET real | `start_api.ps1` lee de .env, no hardcodea |
| V-F6 | ADR-0019 existe | `docs/decisions/0019-idempotency-rbac.md` con status Proposed |
| V-F7 | Tests pasan | `pytest` + `npm run typecheck` verdes |

---

## 4 · Workflow

```
INICIO PARALELO
│
├── Dev T: C-1 + C-2 (bugs funcionales) ← PRIORITARIO
├── Dev A: C-3 + C-4 + C-5 (seguridad) ← PRIORITARIO
│
├── Dev T: M-1 (backoff) + M-4 (filtros) + M-5 (modal)
├── Dev A: M-2 (R14) + M-3 (ADR-0019)
│
└── Revisor: Validar V-F1 a V-F7
    │
    └── Senior reviewer: Auditoría final
```
