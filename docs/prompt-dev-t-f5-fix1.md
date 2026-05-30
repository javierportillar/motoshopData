# Prompt Dev T · F5-FIX1 · Frontend Fixes

```
Soy Dev T · Track T para F5-FIX1 del proyecto MotoShop.

PRE-FLIGHT:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f5-fix1.md

MI MISIÓN:
Corregir 2 bugs funcionales + 3 mejoras en el frontend de F5.

TAREAS (en orden de prioridad):

### C-1 + C-2: Fix alertActions.ts (PRIORITARIO)

Archivo: motoshop-app/web/lib/api/alertActions.ts

PROBLEMA 1: fetchMyActions envía ?date= pero el backend espera ?date_from=&date_to=
FIX: Cambiar params.set("date", date) por:
  params.set("date_from", date)
  params.set("date_to", date)

PROBLEMA 2: MyActionsResponse espera campo "actions" pero backend retorna "items"
FIX: Cambiar la interfaz:
  interface MyActionsResponse {
    items: MyActionItem[];  // era "actions"
    total: number;
  }
Y actualizar el mapeo en fetchMyActions para leer resp.items en vez de resp.actions.

### M-1: Backoff exponencial en offline queue

Archivo: motoshop-app/web/lib/offline/queue.ts

PROBLEMA: setInterval fijo de 30s sin backoff.
FIX:
- Cada item en la cola tiene un campo next_retry_at
- Backoff: 1s → 5s → 30s → 5min → 30min → 6h (cap 6 reintentos)
- flushQueue() solo procesa items donde next_retry_at <= Date.now()
- Al enqueue: next_retry_at = Date.now() + BACKOFF_DELAYS[attempt]
- Al fallar: incrementar attempt, recalcular next_retry_at

### M-4: Filtros período en acciones

Archivo: motoshop-app/web/app/(authenticated)/acciones/page.tsx

PROBLEMA: "Esta semana" y "Este mes" envían dateParam=undefined (no filtran).
FIX:
- "Hoy": date_from = today, date_to = today
- "Esta semana": date_from = lunes de esta semana, date_to = hoy
- "Este mes": date_from = primer día del mes, date_to = hoy
- Calcular fechas con Date arithmetic (sin librería externa)

### M-5: Modal integra offline queue

Archivo: motoshop-app/web/components/alerts/AlertActionModal.tsx

PROBLEMA: Cuando el submit falla, el modal muestra error pero no encola.
FIX: En el catch, llamar a enqueueAction() con los datos de la acción.
El mensaje "queda en cola" solo mostrar si la cola está activa.

VERIFICACIÓN:
- Página "Mis acciones del día" muestra datos reales (V-F1)
- Filtros período devuelven subconjuntos (V-F2)
- Offline queue usa backoff exponencial (V-F3)
- npm run typecheck pasa

LO QUE NO TOCO:
- infra/** (Dev A)
- API backend (Dev A)
- Credenciales / .env

COMMITS:
- prefijo: fix(F5-fix1): ...
```
