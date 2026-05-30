# F7 · Runbook operativo · Paso a paso por dev + handshakes

- **Fecha:** 2026-05-30 (Sesión 51)
- **Audiencia:** Dev T1, Dev T2 (después), Dev A1, Dev A2, Dev D, Dev T, Dev W, Humano (Javier), Revisor (Claude)
- **Para qué sirve:** cada dev sabe (a) qué hace, (b) qué reporta al terminar cada paso, (c) cuándo esperar a otros, (d) cómo señalizar handoffs al humano

---

## 0 · Cómo funciona el ciclo de trabajo

```
Humano (Javier) ────── orquestador centralizado
   │
   ├──→ pega prompt en chat de cada Dev (uno por vez según runbook)
   │
   ├──→ Dev trabaja, hace commits con prefix específico
   │       └──→ Dev termina un paso o sprint
   │              └──→ Dev escribe linea status en SEGUIMIENTO.md sección suya
   │                     └──→ Dev push final
   │
   ├──→ Humano ve commit en GitHub
   │       └──→ Si aplica: humano abre chat Dev W (Windows) y dispara rutina
   │       └──→ Si aplica: humano avisa al Revisor (Claude en este chat)
   │
   └──→ Revisor: te paso el siguiente prompt cuando corresponda
```

**Regla de oro:** ningún dev se comunica directamente con otro. **El humano es el único puente.** Los devs reportan en SEGUIMIENTO + commits → humano decide qué disparar después.

---

## 1 · Convención de status que cada dev DEBE escribir

Al cerrar un paso o sprint, cada dev escribe en `SEGUIMIENTO.md` una línea status así:

```
> 🟢 [F7-X-dev-Y] Paso N terminado · <descripción> · commit: <hash> · siguiente paso: <Z> · bloqueo si lo hay: <Q>
```

Ejemplos:

```
> 🟢 [F7-B-T1] Paso 1 terminado · tokens.ts + tailwind.config + globals.css · commit: abc123 · siguiente paso: Logo component · sin bloqueo
> 🟢 [F7-B-T1] Paso 3 MVP terminado · Card+Stat+Table+Badge listos · commit: def456 · siguiente paso: componentes secundarios · LIBERA a Dev T2 — humano puede arrancar T2 ahora
> 🟡 [F7-E-D] Paso 4 en pausa · esperando que Dev A pushee endpoint plan-compras antes de seguir con mart_abc_xyz · commit: ghi789
> 🔴 [F7-D-A2] Paso 7 bloqueado · necesito gold.mart_abc_xyz de Dev D · mock SQL temporal en línea 142 de plan_compras_repo.py · revisar tras push de Dev D
```

**Símbolos:**
- 🟢 = paso terminado y desbloqueador
- 🟡 = pausa (esperando algo que NO bloquea totalmente, puedo seguir con otra cosa)
- 🔴 = bloqueado (no puedo seguir hasta resolver)

Esto le da al humano un dashboard en `SEGUIMIENTO.md` para saber qué disparar después.

---

## 2 · Dev D · F7-E Databricks + Snapshots (~7-10 días)

**Por qué arranca primero:** snapshots acumulan tiempo. Cada día perdido = 1 día menos de historia para defensa.

### Paso D1 · Notebooks snapshot jobs (~3 h, día 1)

**Inputs requeridos:**
- `notebooks/gold/19_feature_store.py` y `24_forecast_categoria.py` como referencia
- Schema actual de `mart_rotacion_abc`, `mart_productos_dormidos`, `gold.alertas_quiebre`, `forecast_demanda_sku`

**Trabajo:**
1. Crear `notebooks/gold/30_snapshot_abc_mensual.py` (snapshot mensual `mart_rotacion_abc` → `gold.mart_rotacion_abc_snapshots`)
2. Crear `notebooks/gold/31_snapshot_dormidos_mensual.py` (idem para dormidos)
3. Crear `notebooks/gold/32_snapshot_alertas_diario.py` (snapshot DIARIO alertas)
4. Crear `notebooks/gold/33_archive_forecasts.py` (archive ANTES de overwrite)

**Outputs producidos:**
- 4 notebooks nuevos en `notebooks/gold/`
- 4 tablas nuevas en `gold.*_snapshots` (auto-creadas en primer run)

**Commit prefix:** `feat(F7-E-snapshot):`

**Cuando terminás D1, escribís en SEGUIMIENTO.md:**
```
> 🟢 [F7-E-D] Paso D1 terminado · 4 notebooks snapshot creados · commit: <hash> · siguiente paso: D2 modificar workflow · ACCIÓN HUMANO: avisar Dev W para upload_all_notebooks.py
```

**Sin bloqueo previo. Bloquea a:** Dev W (debe sync notebooks).

### Paso D2 · Modificar workflow (~1 h, día 2)

**Esperar a Dev W** que confirme que notebooks D1 están en Workspace.

**Trabajo:**
1. Editar `infra/create_full_workflow.py` para agregar 4 tasks nuevas (las 4 del paso D1)
2. Dependencias correctas: archive_forecasts ANTES de forecast_demanda_sku update; snapshots después de marts originales

**Outputs:**
- `create_full_workflow.py` modificado
- Documentación inline de cuándo corre cada snapshot

**Commit prefix:** `feat(F7-E-workflow):`

**Cuando terminás D2:**
```
> 🟢 [F7-E-D] Paso D2 terminado · workflow modificado con 4 tasks · commit: <hash> · siguiente paso: D3 verificar primera corrida · ACCIÓN HUMANO: avisar Dev W para create_full_workflow.py + verificar UNPAUSED
```

### Paso D3 · Verificar primera corrida snapshots (~30 min, día 2-3)

**Esperar a Dev W** que confirme workflow re-deployado y UNPAUSED.

**Trabajo:**
1. Disparar workflow manual desde Databricks UI
2. Verificar las 4 tablas snapshots tienen al menos 1 fila
3. Documentar en `notebooks/gold/_runs/v_f7e_snapshots_arrancan_<ts>.md`

**Cuando terminás D3:**
```
> 🟢 [F7-E-D] Paso D3 terminado · snapshots arrancando OK · commit: <hash> · siguiente paso: D4 rotación promedio · sin bloqueo
```

### Paso D4 · Cálculo rotación promedio (~2 h, día 3-4)

**Trabajo:**
1. `notebooks/gold/22_rotacion_promedio.py`
2. Output: `gold.mart_rotacion_sku` con columnas (cod_producto, venta_diaria_promedio, dias_de_cobertura)

**Commit:** `feat(F7-E-databricks): rotacion promedio mart`

**Cuando terminás D4:**
```
> 🟢 [F7-E-D] Paso D4 terminado · gold.mart_rotacion_sku poblada · commit: <hash> · siguiente paso: D5 ABC×XYZ · ACCIÓN HUMANO: avisar Dev W + LIBERA a Dev A2 paso 7 (necesita esta tabla)
```

### Paso D5 · Cálculo ABC × XYZ (~2 h, día 5-6)

**Trabajo:**
1. `notebooks/gold/23_abc_xyz.py`
2. Output: `gold.mart_abc_xyz` con columnas (cod_producto, abc, xyz, bucket)

**Cuando terminás D5:**
```
> 🟢 [F7-E-D] Paso D5 terminado · gold.mart_abc_xyz poblada · commit: <hash> · siguiente paso: D6 soporte Dev A · ACCIÓN HUMANO: avisar Dev W
```

### Paso D6 · Soporte a Dev A (~1-2 días, según necesidad)

**Trabajo iterativo:** si Dev A2 escribe en SEGUIMIENTO "necesito vista X", D6 la genera.

**Cuando todo cierre:**
```
> 🟢 [F7-E-D] F7-E COMPLETO · todos los snapshots corriendo, analytics listos, soporte a Dev A entregado · commit: <hash> · sprint cerrado · ACCIÓN HUMANO: avisar al Revisor para audit F7-E
```

---

## 3 · Dev A1 · F6-D-FIX1-A Backend bug (~30 min)

### Paso A1-1 · Audit query inventory-summary (~10 min)

**Trabajo:** leer `metrics/repo.py` función `get_inventory_summary`. Identificar por qué `valor_total = 0.0`.

**Cuando terminás A1-1:**
```
> 🟡 [F6-D-FIX1-A] Paso A1-1 diagnóstico · causa raíz: <columna que falta o JOIN incompleto> · siguiente paso: A1-2 aplicar fix
```

### Paso A1-2 · Aplicar fix (~15 min)

**Trabajo:** ajustar query con `SUM(stock_actual * COALESCE(costo_promedio, 0))` o equivalente según campo correcto del mart.

**Smoke test local:** `curl /metrics/inventory-summary` → `valor_total > 0`.

**Commit:** `fix(F6-D-FIX1-A-backend): inventory-summary valor_total con cantidad*costo`

**Cuando terminás A1-2:**
```
> 🟢 [F6-D-FIX1-A] F6-D-FIX1-A COMPLETO · valor_total funciona · commit: <hash> · sprint cerrado · ACCIÓN HUMANO: avisar Dev W para restart API + smoke test producción + avisar Revisor para audit FIX1
```

---

## 4 · Dev A2 · F7-D Backend endpoints (~7-10 días)

### Paso A2-1 · GET /metrics/sales-trend?periods=6 (~1.5 h, día 1) [URGENTE: desbloquea T2]

**Inputs:** ninguno (consume `silver.fact_ventas` existente)

**Trabajo:**
1. `metrics/router.py` — agregar endpoint
2. `metrics/repo.py` — query Databricks SQL agregando por mes (ver código en `PENDIENTES.md` Sesión 51 Handoff #2 paso 1)
3. `metrics/schemas.py` — `SalesTrendResponse`, `SalesTrendItem`
4. `tests/api/test_metrics_trend.py`
5. Smoke local con Bearer

**Commit:** `feat(F7-D-backend): GET metrics/sales-trend`

**Cuando terminás A2-1:**
```
> 🟢 [F7-D-A2] Paso A2-1 terminado · sales-trend operativo · commit: <hash> · siguiente paso: A2-2 vendedores-summary · ACCIÓN HUMANO: avisar Dev W para restart API + LIBERA a Dev T2 para usar endpoint en HG2 + V1
```

### Paso A2-2 · GET /metrics/vendedores-summary (~1 h, día 2)

**Cuando terminás A2-2:**
```
> 🟢 [F7-D-A2] Paso A2-2 terminado · vendedores-summary operativo · commit: <hash> · siguiente paso: A2-3 cohortes-detail · ACCIÓN HUMANO: avisar Dev W
```

### Paso A2-3 · GET /metrics/cohortes-detail (~1 h, día 3)

**Inputs:** `gold.mart_cohortes_clientes` (existe ya)

**Cuando terminás A2-3:**
```
> 🟢 [F7-D-A2] Paso A2-3 terminado · cohortes-detail operativo · commit: <hash> · siguiente paso: A2-4 drift-summary · ACCIÓN HUMANO: avisar Dev W
```

### Paso A2-4 · GET /metrics/drift-summary (~1 h, día 3)

**Inputs:** `gold.alertas_drift` (existe de F6-A)

**Cuando terminás A2-4:**
```
> 🟢 [F7-D-A2] Paso A2-4 terminado · drift-summary operativo · commit: <hash> · siguiente paso: A2-5 forecast-categoria · ACCIÓN HUMANO: avisar Dev W
```

### Paso A2-5 · GET /metrics/forecast-categoria (~1 h, día 4)

**Inputs:** `gold.forecast_categoria` (existe de F6-B)

**Cuando terminás A2-5:**
```
> 🟢 [F7-D-A2] Paso A2-5 terminado · forecast-categoria operativo · commit: <hash> · siguiente paso: A2-6 migration purchase_plans · ACCIÓN HUMANO: avisar Dev W
```

### Paso A2-6 · Migration + endpoints purchase_plans (~2 h, día 5)

**Trabajo:**
1. `infra/migrations/F7-001-app_purchase_plans.sql` (CREATE TABLE)
2. `app_writes/purchase_plans/router.py` con CRUD: POST, GET (list), GET (one), PATCH (status)
3. Tests integración

**Commit:** `feat(F7-D-backend): app_purchase_plans CRUD + migration F7-001`

**Cuando terminás A2-6:**
```
> 🟢 [F7-D-A2] Paso A2-6 terminado · purchase_plans CRUD listo · commit: <hash> · siguiente paso: A2-7 plan-compras endpoint · ACCIÓN HUMANO: avisar Dev W para restart API + APLICAR MIGRATION F7-001 EN WINDOWS
```

### Paso A2-7 · GET /metrics/plan-compras (~2 h, día 6-7)

**Inputs:** `gold.alertas_quiebre` (existe), `gold.forecast_demanda_sku` (existe), `gold.mart_rotacion_abc` (existe), `gold.mart_productos_dormidos` (existe), `gold.mart_inventario_actual` (existe). **Opcionalmente:** `gold.mart_abc_xyz` (Dev D paso D5).

**Si Dev D NO ha pusheado mart_abc_xyz, mockear con SQL temporal:**
```python
# TODO(F7-E-D5): reemplazar con JOIN a gold.mart_abc_xyz cuando esté
abc_xyz_mock = "SELECT cod_producto, 'AY' AS bucket FROM gold.mart_rotacion_abc LIMIT 0"
```

**Cuando terminás A2-7:**
```
> 🟢 [F7-D-A2] Paso A2-7 terminado · plan-compras endpoint operativo · commit: <hash> · siguiente paso: cierre F7-D · ACCIÓN HUMANO: avisar Dev W
```

### Paso A2-8 · Cierre (~30 min)

```
> 🟢 [F7-D-A2] F7-D COMPLETO · 6+ endpoints + purchase_plans + plan-compras · commit: <hash> · sprint cerrado · ACCIÓN HUMANO: avisar Revisor para audit F7-D
```

---

## 5 · Dev T1 · F7-B Design System (~5-7 días)

### Paso T1-1 · Tokens + Tailwind (~45 min, día 1)

**Inputs:** `docs/f7/branding/colors.md` (copy-paste exacto sección "Tokens semánticos")

**Trabajo:**
1. `motoshop-app/web/lib/design/tokens.ts`
2. `motoshop-app/web/tailwind.config.ts`
3. `motoshop-app/web/app/globals.css`

**Smoke:** crear `<div className="bg-primary text-primaryFg p-4">` y verificar render con colores reales (rojo `#C83828`).

**Commit:** `feat(F7-B-design): tokens + tailwind + globals`

**Cuando terminás T1-1:**
```
> 🟢 [F7-B-T1] Paso T1-1 terminado · tokens operativos · commit: <hash> · siguiente paso: T1-2 Logo · sin bloqueo
```

### Paso T1-2 · Logo component (~30 min, día 1)

**Trabajo:**
1. `cp docs/f7/branding/logo.png motoshop-app/web/public/logo.png`
2. `motoshop-app/web/components/Logo.tsx`
3. Stories en `docs/f7/components/Logo.md`

**Cuando terminás T1-2:**
```
> 🟢 [F7-B-T1] Paso T1-2 terminado · Logo component listo · commit: <hash> · siguiente paso: T1-3 componentes MVP · sin bloqueo
```

### Paso T1-3 · MVP componentes [DESBLOQUEA Dev T2] (~2 h, día 2-3)

**Trabajo:** crear `Card.tsx`, `Stat.tsx`, `Table.tsx`, `Badge.tsx` en `components/ui/`.

**Cuando terminás T1-3 (HITO CRÍTICO):**
```
> 🟢 [F7-B-T1] Paso T1-3 MVP COMPLETO · 4 componentes base + tokens + Logo listos · commit: <hash> · siguiente paso: T1-4 componentes secundarios · LIBERA a Dev T2 — humano puede arrancar T2 AHORA
```

### Paso T1-4 · Componentes secundarios (~2 h, día 3-4)

**Trabajo:** `Chart.tsx`, `Skeleton.tsx`, `ErrorState.tsx`, `EmptyState.tsx`

**Cuando terminás T1-4:**
```
> 🟢 [F7-B-T1] Paso T1-4 terminado · 4 componentes secundarios listos · commit: <hash> · siguiente paso: T1-5 Navigation · sin bloqueo
```

### Paso T1-5 · Navigation adaptable (~1 h, día 4-5)

**Trabajo:** `Navigation.tsx` con bottom nav mobile + sidebar desktop según viewport.

**Cuando terminás T1-5:**
```
> 🟢 [F7-B-T1] Paso T1-5 terminado · Navigation lista · commit: <hash> · siguiente paso: T1-6 cierre · sin bloqueo
```

### Paso T1-6 · Cierre (~30 min)

**Trabajo:**
1. `npm run typecheck` → 0 errors
2. `npm run build` → 0 errors
3. Capturas en `docs/f7/components/_screenshots/`
4. Commit final

```
> 🟢 [F7-B-T1] F7-B COMPLETO · design system listo · commit: <hash> · sprint cerrado · ACCIÓN HUMANO: avisar Revisor para audit F7-B
```

---

## 6 · Dev T · F6-D-FIX1-B Frontend bugs (~45-60 min)

### Paso T-1 · Página dormidos (~25 min)

**Cuando terminás T-1:**
```
> 🟢 [F6-D-FIX1-B] Paso T-1 terminado · página dormidos creada · commit: <hash> · siguiente paso: T-2 formatter
```

### Paso T-2 · Formatter K/M (~20 min)

**Cuando terminás T-2:**
```
> 🟢 [F6-D-FIX1-B] Paso T-2 terminado · formatMoney K/M operativo · commit: <hash> · siguiente paso: T-3 smoke
```

### Paso T-3 · Smoke + deploy (~10 min)

```
> 🟢 [F6-D-FIX1-B] F6-D-FIX1-B COMPLETO · bugs frontend cerrados · commit: <hash> · Vercel auto-deploya · ACCIÓN HUMANO: avisar Revisor para audit FIX1
```

---

## 7 · Dev T2 · F7-C Pages Implementation (~10-15 días)

**NO ARRANCA HOY.** Espera reporte de Dev T1 paso T1-3 (MVP componentes listo).

Cuando Dev T1 reporte MVP listo, **humano dispara Dev T2** con handoff que yo (revisor) le voy a redactar.

---

## 8 · Dev W · Runtime Windows (transversal, ~3 h distribuidas)

### Disparado manualmente por humano cuando:

| Trigger | Acción Dev W |
|---------|--------------|
| `fix(F6-D-FIX1-A-backend)` push | `git pull` + restart API + smoke /metrics/inventory-summary |
| `feat(F7-D-backend)` push | `git pull` + restart API + smoke endpoint nuevo |
| Migration SQL `F7-001-app_purchase_plans.sql` | Backup + `mysql -u root motoshop2024 < ...` + verificar tabla |
| `feat(F7-E-snapshot)` push | `git pull` + `python infra\upload_all_notebooks.py` |
| `feat(F7-E-workflow)` push | `git pull` + `python infra\upload_all_notebooks.py` + `python infra\create_full_workflow.py` + verificar UNPAUSED |
| `feat(F7-E-databricks)` push (mart nuevo) | `git pull` + `python infra\upload_all_notebooks.py` |

**Cuando terminás cada rutina, escribís en SEGUIMIENTO:**
```
> 🟢 [Dev W] Rutina post-push aplicada · commits aplicados: <list> · API restart OK / notebooks sync OK / workflow redeploy OK
```

---

## 9 · Revisor (Claude en chat humano) · Audits incrementales

### Cuando reciba aviso de cierre de un sprint, ejecuto:

1. Pull último estado
2. Smoke test endpoints / probar PWA
3. Audit con 9 checks de `INICIAR_REVIEWER.md`
4. Veredicto + observaciones

### Para E5 memoria final:

- Empezar a redactar cuando Dev T2 vaya cerrando pages
- Capturar screenshots de cada page migrada
- Documentar lecciones aprendidas F7

---

## 10 · Cronograma con handshakes (linea de tiempo)

```
HOY (T+0)
│
├──→ Humano dispara Dev D (PRIORIDAD #1)
│       │
│       └──> Dev D paso D1 (notebooks snapshots) ────┐
│              │ ~3 h                                  │
│              └──→ commit + status SEGUIMIENTO       │
│                     └──→ ACCIÓN: humano dispara W   │
│                                                      │
├──→ Humano dispara Dev A1 (FIX1-A)                   │
│       │ ~30 min                                       │
│       └──→ commit + status SEGUIMIENTO              │
│              └──→ ACCIÓN: humano dispara W (restart)│
│                                                      │
├──→ Humano dispara Dev A2 (paso A2-1 sales-trend)    │
│       │ ~1.5 h                                        │
│       └──→ commit + status SEGUIMIENTO              │
│              └──→ ACCIÓN: humano dispara W (restart)│
│                                                      │
├──→ Humano dispara Dev T1 (paso T1-1 tokens)         │
│       │ ~45 min                                       │
│       └──→ commit + status SEGUIMIENTO              │
│              (Vercel autodeploy, no requiere W)     │
│                                                      │
└──→ Humano dispara Dev T (FIX1-B)                    │
        │ ~45-60 min                                    │
        └──→ commit + status SEGUIMIENTO              │
               (Vercel autodeploy)                    │
                                                       │
T+1 día                                                │
│                                                      │
├──→ Dev D paso D2 (workflow) ←── W confirmó D1       │
├──→ Dev D paso D3 (verificar snapshots)              │
├──→ Dev A2 paso A2-2 (vendedores-summary)            │
├──→ Dev T1 paso T1-2 (Logo) → T1-3 (MVP componentes) │
│                                                      ▼
T+2-3 días                                       MVP T1 reporta
│                                                      │
├──→ Humano me avisa → yo redacto handoff Dev T2 ────┤
├──→ Humano dispara Dev T2 (arranca pages)            │
│                                                      │
├──→ Dev D pasos D4-D5 (rotación + ABC×XYZ)           │
├──→ Dev A2 pasos A2-3, A2-4, A2-5 (endpoints)        │
│                                                      │
T+5-7 días                                             │
│                                                      │
├──→ Dev T1 cierra F7-B → audit Revisor               │
├──→ Dev D cierra F7-E → audit Revisor                │
├──→ Dev A2 cierra F7-D → audit Revisor               │
│                                                      │
T+10-15 días                                           │
│                                                      │
├──→ Dev T2 cierra migración 8 pages                  │
├──→ Dev T2 crea 4 dashboards nuevos                  │
├──→ Yo empiezo E5 memoria con capturas continuas     │
│                                                      │
T+15-21 días                                           │
│                                                      │
├──→ F7-C cierra → audit Revisor                      │
├──→ E5 memoria primera versión                       │
│                                                      │
T+21-50 días                                           │
│                                                      │
└──→ Esperar snapshots balde B (30 días)              │
        │                                              │
        └──→ Audit cierre proyecto + DEFENSA ───────→ FIN
```

---

## 11 · Checklist para humano (Javier)

### Cosas que yo (Claude) hago, NO vos:

- ✅ Redactar prompts de cada dev (te los paso por chat)
- ✅ Auditar cada sprint cuando cierre
- ✅ Decidir qué dev disparar después
- ✅ Escribir ADRs nuevos
- ✅ Escribir E5 memoria

### Cosas que SOLO vos hacés:

- 🔴 Abrir chats nuevos y pegar prompts (yo no puedo)
- 🔴 Disparar Dev W después de cada commit relevante (yo te aviso cuándo)
- 🔴 Decirme cuando un dev cerró (yo veo commits pero no chats privados)
- 🔴 Demo 4G grabada (R6)
- 🔴 Agendar demo gerencia (R8)
- 🔴 Subir branding (ya hiciste ✅)
- 🔴 Aceptar / rechazar mi audit
- 🔴 Defensa académica en sí misma

### Reglas operativas:

1. **Después de cada commit que veas en GitHub, fijate si requiere Dev W.** Si es backend o Databricks → sí. Si es frontend → no (Vercel autodeploy).
2. **Cuando un dev reporte status 🟢 SPRINT COMPLETO, avisame en este chat.** Yo audito.
3. **Cuando vos mismo cierres una acción humana (demo 4G, demo gerencia), avisame.** Yo documento en E5.
4. **Si algo se rompe, avisame de inmediato.** Yo investigo y propongo fix.

---

## 12 · ¿Y si un dev se traba?

### Si Dev se queda esperando algo que NO llega:

El dev escribe en SEGUIMIENTO:
```
> 🔴 [F7-X-dev] Paso N BLOQUEADO · necesito <Y> de <quien> · NO puedo avanzar
```

**Acciones del humano:**
1. Avisarme en este chat
2. Yo diagnostico:
   - ¿El bloqueo es real o evitable con workaround?
   - ¿Qué dev tiene que destrabar?
3. Yo te paso instrucción para el dev bloqueante o para el dev bloqueado

### Si Dev encuentra un bug que no estaba previsto:

El dev escribe en SEGUIMIENTO:
```
> 🟡 [F7-X-dev] Detecté bug inesperado: <descripción> · severidad: <alta/media/baja> · ¿continúo o paro?
```

**Acciones del humano:** avisarme. Yo decido si abre F7-Z-FIX1 o si se ignora hasta el final.

---

## 13 · Final state

Cuando todo cierre y los 30 días de snapshots hayan pasado:

```
> 🟢 [F7] COMPLETO · 5 sprints cerrados + balde B con datos reales · 
  proyecto académico MotoShop listo para defensa Maestría UAO 2025-2
```

Yo escribo E5 memoria final. Vos defendés.
