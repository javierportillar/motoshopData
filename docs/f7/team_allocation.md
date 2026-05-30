# F7 · Team Allocation y dependencias

- **Fecha:** 2026-05-30 (Sesión 50)
- **Status:** ✅ Approved (humano confirmó 5 devs sin auto-deploy)
- **Total devs:** 5 + humano + revisor
- **Camino crítico documentado** para evitar bloqueos accidentales

---

## 1 · Roles y responsabilidades

### Dev T1 · Design System Frontend

**Sprint:** F7-B · ~5-7 días

**Trabajo:**
- `motoshop-app/web/lib/design/tokens.ts` (colors, spacing, typography, radius, shadow, breakpoints)
- `motoshop-app/web/tailwind.config.ts` actualizado consumiendo tokens
- 8 componentes base en `motoshop-app/web/components/ui/`:
  - `Card.tsx`, `Stat.tsx`, `Table.tsx`, `Badge.tsx`, `Chart.tsx`, `Skeleton.tsx`, `ErrorState.tsx`, `EmptyState.tsx`
- `motoshop-app/web/components/Logo.tsx` (consume branding real o placeholder)
- `motoshop-app/web/components/Navigation.tsx` adaptable (bottom mobile + sidebar desktop)
- Stories markdown en `docs/f7/components/<name>.md` con ejemplos
- Tests unit de componentes base

**Puede arrancar:** HOY (con placeholder branding si humano tarda > 24h)

**Bloqueado por:**
- 🟡 Humano sube branding (`docs/f7/branding/logo.svg` + `colors.md`) — si tarda > 24h, arranca con placeholder indigo+neutros (ver `docs/f7/branding.md` §6)

**Bloquea a:**
- 🔴 Dev T2 — sin componentes mínimos (Card + Stat + Table + Badge), no puede migrar pages

**Commits prefix:** `feat(F7-B-design):`

---

### Dev T2 · Pages Implementation Frontend

**Sprint:** F7-C · ~10-15 días

**Trabajo:**
- Home diferenciado por rol en `motoshop-app/web/app/(authenticated)/page.tsx`
- Migrar 8 pages existentes al nuevo design system:
  - `/dashboards/` (landing gerente)
  - `/dashboards/ventas` (fix bug semántico "tendencia")
  - `/dashboards/inventario`
  - `/dashboards/abc`
  - `/dashboards/dormidos`
  - `/forecast`
  - `/alerts`
  - `/acciones`
- Crear 4 dashboards NUEVOS:
  - `/plan-compras` (decision-oriented combinando alertas+forecast+ABC+dormidos)
  - `/cohortes` (mart_cohortes_clientes — existe pero no expuesto)
  - `/vendedores` (NUEVO usando nit_vendedor de fact_ventas)
  - `/drift` (gold.alertas_drift de F6-A)
- Mobile-first responsive con breakpoints sm/md/lg/xl + touch targets ≥ 44px
- Tests E2E Playwright en 3 viewports (375/768/1280px)
- Lighthouse Mobile > 85, A11y > 90

**Puede arrancar:** Día 3-5 (cuando T1 tenga Card + Stat + Table + Badge como mínimo)

**Bloqueado por:**
- 🔴 Dev T1 — necesita componentes base mínimos
- 🟡 Dev A — endpoints nuevos para 4 dashboards nuevos (pero puede MOCKEAR con datos hardcoded temporales)
- 🟡 Dev D — algunos endpoints de A necesitan tablas que D produce (pero A puede mockear contra Dev D)
- 🟡 F6-D-FIX1 — formatter `lib/format/currency.ts` debe estar fixed antes que migre `/ventas`

**Bloquea a:**
- 🔴 Revisor (yo) — E5 memoria final necesita capturas de pages post-F7
- 🔴 Audit cierre proyecto

**Estrategia anti-bloqueo:**
- Migra primero pages CON endpoint estable (ventas, inventario, abc, dormidos, alerts, forecast, acciones)
- Deja las 4 nuevas (plan-compras, cohortes, vendedores, drift) para el final
- Si Dev A o D se atrasan, mockea con datos hardcoded

**Commits prefix:** `feat(F7-C-pages):`

---

### Dev A · Backend FastAPI Endpoints

**Sprint:** F7-D · ~7-10 días

**Trabajo:**
- 5+ endpoints nuevos en `motoshop-app/api/src/motoshop_api/`:
  - `GET /metrics/sales-trend?periods=6` (para V1, HG2)
  - `GET /metrics/plan-compras` (para PC1-PC6)
  - `GET /metrics/cohortes-detail` (para CO1-CO5)
  - `GET /metrics/vendedores-summary` (para VE1-VE5)
  - `GET /metrics/drift-summary` (para DR1-DR4)
  - `GET /metrics/forecast-categoria` (para F1)
- Posibles endpoints adicionales según necesidad de T2
- Tabla nueva `app_purchase_plans` con schema + endpoints CRUD (para PC6)
- Migration SQL `infra/migrations/F7-001-app_purchase_plans.sql`
- Tests unit con FakeRepos
- Smoke tests integración

**Puede arrancar:** HOY (en paralelo, sin bloqueos previos)

**Bloqueado por:**
- 🟡 Dev D parcialmente — si endpoint consume tabla nueva que D produce (ej. `mart_abc_xyz`, snapshots), A puede usar MOCK SQL temporalmente y reemplazar después

**Bloquea a:**
- 🟡 Dev T2 — los 4 dashboards nuevos necesitan estos endpoints (pero T2 puede mockear)
- 🔴 Dev W — debe restartear API después de cada push para que los endpoints lleguen a producción

**Commits prefix:** `feat(F7-D-backend):`

---

### Dev D · Databricks Notebooks + Snapshots + Analytics

**Sprint:** F7-E · ~7-10 días

**Trabajo:**

**PRIORIDAD #1 (Día 1-2):** Snapshot jobs balde B activados cuanto antes:
- Modificar `infra/create_full_workflow.py` para incluir:
  - Snapshot mensual `mart_rotacion_abc` → tabla nueva `gold.mart_rotacion_abc_snapshots` (para A2)
  - Snapshot mensual `mart_productos_dormidos` → `gold.mart_productos_dormidos_snapshots` (para D5)
  - Snapshot diario `gold.alertas_quiebre` → `gold.alertas_quiebre_snapshots` (para AL5)
  - Retención de forecasts viejos → guardar versión anterior antes de overwrite (para F3 backtesting)
- Modificar schedule del workflow para que estos jobs corran apropiadamente

**Prioridad #2 (Día 3-5):** Cálculos analíticos nuevos:
- Cálculo de **rotación promedio** (días en stock antes de venderse) → mart o vista
- Cálculo de **cobertura de stock** (cuántos días aguanta cada SKU dadas las predicciones) → mart o vista
- **ABC × XYZ matrix** (frecuencia × valor) → nueva tabla `gold.mart_abc_xyz`

**Prioridad #3 (Día 6-7):** Soporte a Dev A:
- Si Dev A pide vistas o cálculos específicos para endpoints, generarlas

**Puede arrancar:** HOY (paralelo total, sin bloqueos)

**Bloqueado por:** nada

**Bloquea a:**
- 🟡 Dev A — endpoints que consumen tablas nuevas (pero A puede mockear hasta que D pushee)
- 🔴 Balde B histórico — sin snapshot jobs corriendo, no se acumulan datos para los dashboards de tendencia
- 🔴 Dev W — debe sync notebooks + re-deploy workflow después de cada push de D

**Commits prefix:** `feat(F7-E-databricks):` o `feat(F7-E-snapshot):`

---

### Dev W · Runtime Windows (NUEVO 5to rol)

**Sprint:** Transversal · ~2-3 horas distribuidas en 3-4 semanas

**Trabajo recurrente:** cada vez que Dev A o Dev D pushean cambios infra, Dev W debe aplicar a producción:

| Disparador | Acción Dev W |
|------------|--------------|
| Dev A pushea con prefix `feat(F7-D-backend):` | `git pull` + restart API (`.\infra\start_api.ps1`) + smoke test local del endpoint nuevo |
| Dev A crea migration SQL (ej. `F7-001-app_purchase_plans.sql`) | Backup + ejecutar `mysql -u root motoshop2024 < migration.sql` + verificar tabla |
| Dev D pushea notebook nuevo o modificado | `python infra\upload_all_notebooks.py` (sync a Databricks Workspace) |
| Dev D modifica `create_full_workflow.py` | `python infra\create_full_workflow.py` (re-deploy workflow) + verificar UNPAUSED en Databricks UI |
| Dev D activa snapshot jobs | Verificar primera corrida exitosa en `system.workflows.runs` |
| Dev T2 reporta CORS error desde dominio nuevo (improbable) | Update CORS en `.env` + restart API |
| Render deployment falla por env var nueva | Sync env vars Windows → Render dashboard manualmente |

**Puede arrancar:** cuando hay algo que aplicar (HOY si F6-D-FIX1 sigue abierto o Dev A/D ya pushearon)

**Bloqueado por:**
- Push de Dev A (sin push no hay nada que pullear)
- Push de Dev D (idem)

**Bloquea a:**
- 🔴 **Producción API actualizada** — la PWA en Vercel NO ve los cambios de A si Windows no reinicia
- 🔴 **Workflow nocturno** — si D modifica workflow y W no re-deploya, Databricks corre el viejo
- 🔴 **Snapshots balde B** — si D activa jobs y W no verifica que arrancaron, no se acumula data

**Modo de operación:** **MANUAL.** No hay auto-deploy. Cuando el humano (Javier) ve que Dev A o D pushearon, abre el chat de Dev W y le pega "hay cambios A/D, ejecutá tu rutina post-push".

**Tiempo por ciclo:** 10-15 min. Estimado 6-10 ciclos durante F7 = ~2-3 horas total.

**Commits prefix (cuando aplique):** `chore(F7-W-windows):`

---

## 2 · Camino crítico (dependencias en orden)

```
DÍA 1 (HOY)
│
├─ Humano: sube branding (15 min) ────────────┐
│                                              ▼
├─ Dev T1: arranca Design System (5-7 días)   │
│                                              │
├─ Dev D: snapshot jobs PRIORIDAD #1 (1-2d)   │
│       └─ Dev W: aplica workflow modificado  │
│              └─ Snapshots empiezan acumular │
│                                              │
├─ Dev A: arranca endpoints simples (7-10 d)  │
│                                              │
├─ Humano: pega handoffs F6-D-FIX1 (2 min)    │
│       └─ Bugs producción cerrados (1 día)   │
│                                              │
└─ Humano: demo 4G (R6) + agenda demo R8      │
                                               │
DÍA 3-5                                        ▼
│
├─ Dev T1: cierra parcialmente (4 componentes base mínimos)
│       └─ Dev T2: arranca migración pages
│
├─ Dev D: cierra snapshots → arranca analytics (rotación, cobertura, ABC×XYZ)
│       └─ Dev W: sync notebooks
│              └─ Dev A: endpoints que consumen vistas nuevas
│                     └─ Dev W: restart API
│
DÍA 7-15
│
├─ Dev T1: cierra completo
├─ Dev D: cierra completo
├─ Dev A: cierra completo
│       └─ Dev W: aplica último restart + migration SQL
│
├─ Dev T2: continúa migrando pages + crea 4 dashboards nuevos
│
├─ Revisor (yo): audit incremental cada cierre + ADRs nuevos + E5 capturas continuas
│
DÍA 15-21
│
├─ Dev T2: cierra completo
├─ Revisor: E5 memoria final con capturas
│
DÍA 21-50
│
├─ Esperar snapshots balde B (mínimo 30 días)
├─ Humano: ensaya defensa
│
DÍA 50-60
│
└─ Audit cierre proyecto + DEFENSA
```

---

## 3 · Matriz de bloqueos (quién espera a quién)

| Si esto se retrasa... | Bloquea a... | Cuánto crítico |
|----------------------|--------------|----------------|
| Humano no sube branding | Dev T1 (workaround: placeholder) | 🟡 bajo |
| Dev T1 design system | Dev T2 (sin componentes no migra) | 🔴 alto |
| Dev D snapshot jobs | Balde B acumulando datos (cada día perdido = menos data para defensa) | 🔴 alto |
| Dev D analytics | Dev A endpoints que los consumen (workaround: mock SQL) | 🟡 medio |
| Dev A endpoints | Dev T2 dashboards nuevos (workaround: datos hardcoded) | 🟡 medio |
| Dev W no aplica push de A | Producción API queda vieja (PWA no ve cambios) | 🔴 alto |
| Dev W no aplica push de D | Workflow corre viejo, snapshots no se acumulan | 🔴 alto |
| Dev T2 migración pages | Revisor E5 memoria + audit cierre | 🔴 alto |
| Humano demos R6+R8 | E5 sección demos vacía | 🟡 medio |
| Snapshots balde B (30 días) | Defensa con datos parciales documentados | 🟡 aceptado |

---

## 4 · Disparadores manuales del humano

Vos sos el orquestador. Estos son los momentos donde tenés que actuar:

1. **HOY:**
   - Subir branding a `docs/f7/branding/`
   - Pegar handoffs Dev T1, Dev A, Dev D (3 chats nuevos)
   - Pegar handoffs F6-D-FIX1 (los 3 bugs ya pendientes)

2. **Cada vez que Dev A o Dev D pushean:**
   - Abrir chat Dev W (PC Windows) y decir "hay cambios A/D, ejecutá tu rutina post-push"

3. **Cuando Dev T1 cierre (día ~5-7):**
   - Pegar handoff Dev T2

4. **Cuando puedas (paralelo a todo):**
   - Grabar demo 4G en celular en `app.fragloesja.uk` (R6)
   - Agendar demo gerencia (R8)

5. **Cuando todo cierre (día ~21):**
   - Avisarme para que yo escriba E5 memoria final
   - Esperar 30 días para snapshots balde B
   - Ensayar defensa

---

## 5 · ¿Por qué 5 devs y no menos?

**Skills cleanly separadas** — ningún dev hace trabajo de otro:

| Skill | Quien |
|-------|-------|
| React + Tailwind + Next.js components | T1 |
| React + Next.js pages + UX responsive | T2 |
| FastAPI + SQLAlchemy + Pydantic | A |
| Databricks SQL + PySpark + Workflow management | D |
| PowerShell + MySQL CLI + Databricks SDK CLI | W |

**Si juntáramos a A + D:** un solo agente alternaría entre Python web y Databricks notebooks. Context switching alto.
**Si juntáramos a T1 + T2:** un solo agente haría sistema + uso. Sin separación = no hay sistema (terminás con componentes ad-hoc).
**Si juntáramos a Dev W con cualquiera:** Windows queda postergado, deuda silenciosa.

5 devs es el mínimo razonable para mantener pureza de roles. Cada uno tiene 0% overlap con los demás.

---

## 6 · Handoffs (a redactar cuando arranque cada sprint)

- **Dev T1 (F7-B):** redactar HOY mismo cuando humano confirme listo para empezar
- **Dev A (F7-D):** redactar HOY mismo (puede arrancar en paralelo)
- **Dev D (F7-E):** redactar HOY mismo (puede arrancar en paralelo)
- **Dev T2 (F7-C):** redactar cuando T1 reporte componentes base mínimos listos
- **Dev W (transversal):** **ya existe handoff base en sesiones anteriores** (diagnosis Sesión 47 + Sesión 49). Cuando A o D pushean, vos le decís "ejecutá rutina post-push" — no necesita handoff nuevo por cada vez.

---

## 7 · Aprobación humana

✅ 5 devs: T1, T2, A, D, W  
✅ Modo manual sin auto-deploy (humano dispara Dev W cuando ve push de A/D)  
✅ Skills sin overlap entre devs  
✅ Camino crítico identificado  
✅ Workarounds anti-bloqueo para mitigar dependencias  

**Próximo paso:** humano sube branding → yo redacto handoffs F7-B/D/E para arrancar 3 devs en paralelo HOY.
