# Pendientes del humano

> Lista priorizada de tareas que tiene que ejecutar **Javier** entre sesiones del agente. Cosas que el agente **no puede hacer** (tocan sgHermes, la red local, cuentas externas, decisiones de negocio) o que requieren confirmación humana.
>
> **Convención:** cada sesión añade un bloque nuevo arriba. Los pendientes resueltos se marcan ✅ pero **no se borran** — quedan como historial. Cuando algo cambia de prioridad o se vuelve obsoleto, se reescribe y se anota el motivo.

**Leyenda:** ⬜ pendiente · 🟡 en progreso · ✅ hecho · 🔴 bloqueado · ❌ descartado

---

## Sesión 2026-05-31 (63) · F7-E-FIX1 · Workflow Databricks · 3 tasks fallando

**Estado:** F7 sustantivamente cerrada, deploys OK (Vercel + Render + Windows), 13/13 endpoints API 200, 13/13 paths PWA 200. **PERO:** 3 tasks del workflow nocturno `motoshop_full_workflow` fallan en cada corrida (06:39, 06:47, 06:54 hoy). Sin esto, **los snapshots históricos balde B NO se acumulan automáticamente** → bloquea R-V2-16 + entrega académica defendible al 100%.

**Decisión humana:** NO dejar la deuda. Arreglar antes de E5.

**Plan correctivo:** [`docs/plan-f7-e-fix1.md`](docs/plan-f7-e-fix1.md)

### 🤖 Handoff Dev W · F7-E-FIX1 (~30-45 min)

Pegá esto en el chat de Dev W en la PC Windows (puede ser el mismo chat de Ciclos 1-5 si sigue activo):

```
Hay un nuevo trabajo: F7-E-FIX1 — diagnosticar y arreglar 3 tasks
fallando en motoshop_full_workflow.

Tasks fallando (últimas 3 corridas hoy: 06:39, 06:47, 06:54):
- gold_drift (notebook 25_drift_monitor.py)
- gold_rotacion_promedio (notebook 18_mart_rotacion_promedio.py)
- gold_abc_xyz (notebook 19_mart_abc_xyz.py)

Hipótesis del Revisor: schema mismatch. Las tablas fueron creadas
manualmente por Dev D + Dev W antes del workflow, posiblemente sin
PARTITIONED BY (business_date) que el notebook espera. Cuando el
workflow corre con INSERT OVERWRITE PARTITION, falla porque la
tabla existente no está particionada.

Leer plan completo: docs/plan-f7-e-fix1.md

PASO 1 · Diagnóstico exacto (~10 min)
Para cada task fallida:
1. Databricks UI → Workflows → motoshop_full_workflow
2. Click en último Run → click en cada task fallida
3. Copiar el stacktrace COMPLETO (no resumir)
4. Reportar los 3 errores en chat al humano antes de aplicar cualquier fix

PASO 2 · Fix según diagnóstico (~15-20 min)

Si stacktraces confirman schema mismatch (Hipótesis A del plan §4):

  En Databricks SQL Editor:

  DROP TABLE IF EXISTS motoshop.gold.mart_rotacion_sku;
  DROP TABLE IF EXISTS motoshop.gold.mart_abc_xyz;
  DROP TABLE IF EXISTS motoshop.gold.alertas_drift;

  Verificar drops OK:
  SHOW TABLES IN motoshop.gold LIKE 'mart_rotacion%';
  SHOW TABLES IN motoshop.gold LIKE 'mart_abc_xyz%';
  SHOW TABLES IN motoshop.gold LIKE 'alertas_drift%';

  (Cada SHOW debe devolver 0 filas — confirma drop)

Si la causa es OTRA (Hipótesis B o C del plan §4):
- Reportar al humano antes de tocar nada
- Esperar instrucciones

PASO 3 · Re-ejecutar workflow + verificar (~10-15 min)
1. Databricks UI → motoshop_full_workflow → Run now
2. Esperar a que las 31 tasks terminen
3. Verificar que las 3 que fallaban ahora pasen verde
4. Smoke verificación tablas re-pobladas:

   SELECT COUNT(*), MIN(business_date), MAX(business_date)
   FROM motoshop.gold.mart_rotacion_sku
   WHERE business_date = CURRENT_DATE();
   -- Esperar: ~4,840 filas

   SELECT COUNT(*), MIN(business_date), MAX(business_date)
   FROM motoshop.gold.mart_abc_xyz
   WHERE business_date = CURRENT_DATE();
   -- Esperar: ~1,172 filas

   SELECT COUNT(*), MIN(week_end), MAX(week_end)
   FROM motoshop.gold.alertas_drift;
   -- Esperar: 0+ filas (depende si hay drift detectado)

5. Smoke endpoints producción siguen 200:
   - GET https://api.fragloesja.uk/metrics/drift-summary (con Bearer)
   - GET https://api.fragloesja.uk/metrics/forecast-categoria (con Bearer)
   - GET https://api.fragloesja.uk/metrics/plan-compras (con Bearer)

6. Verificar cron UNPAUSED:
   En Workflows UI: motoshop_full_workflow debe seguir UNPAUSED
   con schedule '0 0 19 * * ?' (19:00 COL)

REPORTE FINAL en SEGUIMIENTO.md:

> 🟢 [F7-E-FIX1] Workflow operativo · stacktraces previos: <hash o hipótesis confirmada> · fix aplicado: <DROP TABLES o otro> · workflow run final: 31/31 OK · smoke endpoints: drift-summary 200, forecast-categoria 200, plan-compras 200 · cron UNPAUSED · timestamp: <yyyy-MM-dd HH:mm>

Commit: chore(F7-E-FIX1): workflow fix - 3 tasks fallando resueltas

PARAR. No avanzar a otros ciclos. Esperar audit Revisor.
```

### Próximo paso del revisor (yo)

Cuando Dev W reporte 🟢 F7-E-FIX1:

1. Auditar 6 V-FIX1 (plan §6)
2. Verificar workflow run history en Databricks
3. Si PASS → cerrar F7-E-FIX1 oficialmente + actualizar SEGUIMIENTO cabecera (F7 100% sin deudas operativas)
4. Arrancar E5 memoria final con todas las capturas finales

### Pendiente humano transversal

Mientras Dev W diagnostica + aplica fix (~30-45 min), vos podés en paralelo:

- **Demo 4G (R6)** — grabar desde celular en `app.fragloesja.uk`
- **Agendar demo gerencia (R8)** — sesión con stakeholder

Ambos son independientes de F7-E-FIX1.

---

## Sesión 2026-05-30 (61) · Diagnóstico jobs Databricks — 2 tareas gold rotas

**Estado:** ✅ **Resuelto** — ADR-0022 aprobado + propuesta Dev W aceptada + job legacy eliminado

**🔴 (Histórico) Trabajo unificado `motoshop_full_workflow` — 3 corridas consecutivas FAILED (24/29 tasks pasan, 2 fallan)**

### Síntoma

Últimas 3 corridas del job fallaron con el mismo patrón:
- **gold_classifier** ❌ — `[UNRESOLVED_COLUMN]` col_name vs column_name
- **gold_drift** ❌ — `[WRONG_COLUMN_DEFAULTS_FOR_DELTA_FEATURE_NOT_ENABLED]` DEFAULT CURRENT_TIMESTAMP sin feature de Delta habilitada

El resto (bronze_ingest → 11 silver → gold marts → quality → validate → snapshots) **todo SUCCESS**.

### gold_classifier — ✅ FIX YA SUBIDO

- Causa: `22_classifier_stockout.py` usaba `col_name` en vez de `column_name`
- Fix: Dev A2 pusheó en `7bbcb96`, Dev W ya sincronizó a Workspace en Ciclo 3
- **Próxima corrida debería pasar**

### gold_drift — 🔴 NECESITA FIX DE DEV D

- `25_drift_monitor.py` línea 28: `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- El workspace Databricks Runtime no tiene habilitada `delta.feature.allowColumnDefaults`
- Fix posible:
  a) Agregar `TBLPROPERTIES('delta.feature.allowColumnDefaults' = 'supported')` al CREATE TABLE
  b) O eliminar DEFAULT y manejarlo en el INSERT
  c) O ejecutar ALTER TABLE sobre la tabla existente

### ✅ Propuesta Dev W — Aprobada vía ADR-0022

**Resultado:** ADR-0022 aprobado. Se mantiene 1 job unificado (`motoshop_full_workflow`).

**Ejecutado por Dev W:**
- ✅ Job legacy `Motoshop Bronze Ingestion` (810345190577693) eliminado
- ✅ Workflow redeployado con 31 tasks y schedule UNPAUSED 19:00 COL
- ✅ Última corrida manual en progreso — bronze→silver→gold marts→classifier ✅ todo SUCCESS

---

**Estado:** La API vive SOLO en Windows. Si la PC se apaga, la web no funciona.

**🔴 Problema arquitectónico descubierto durante smoke test:**
- Frontend en Vercel ✅ (siempre arriba)
- API en Windows + Cloudflare Tunnel ❌ (solo si la PC está encendida)
- MySQL en Windows ❌ (igual)
- Workflow Databricks ✅ (en la nube, corre igual)
- **Conclusión: la demo depende de que esta PC esté prendida. Si se apaga, `https://api.fragloesja.uk` no responde y la PWA no sirve datos.**

**Opciones para F7 (a evaluar por revisor):**

| Opción | Costo | Qué implica |
|--------|-------|-------------|
| **1. Render gratis + Databricks** | $0 | API en Render.com free tier, lee todo de Databricks SQL Warehouse (gold tables), Windows solo para workflow nocturno |
| **2. VPS ($5-10/mes)** | $5-10/mes | DigitalOcean / Hetzner, migrar MySQL 5.0→8.0, deploy API ahí |
| **3. Híbrido (recomendada)** | $0 | API en Render, catálogo/historial vía Databricks SQL, Windows solo para ingesta nocturna. Lo más práctico para demo y entrega académica. |

**Próximo paso:** Revisor evalúa opciones y decide si F7 = migración API a la nube.

---

## Sesión 2026-05-30 (51) · F7 arranca · 3 devs en paralelo + F6-D-FIX1 en paralelo

**Estado:** discovery F7 cerrado (`docs/f7/personas_kpis.md` + `dashboards_content.md` + `team_allocation.md` + `branding.md`). Branding aprobado por revisor (logo PNG real + paleta expandida con error/accent separados). **GO arranque devs.**

**5 sprints en paralelo HOY:**

| Sprint | Owner | Trabajo | Duración |
|--------|-------|---------|----------|
| F6-D-FIX1-A | Dev A backend | Fix `valor_total` MySQL query | 30 min |
| F6-D-FIX1-B | Dev T frontend | Página dormidos + formatter K/M | 45-60 min |
| F7-B | **Dev T1 NUEVO** | Design system (tokens + 8 componentes + nav + Logo) | 5-7 días |
| F7-D | **Dev A NUEVO** | 5+ endpoints + tabla `app_purchase_plans` | 7-10 días |
| F7-E | **Dev D NUEVO** | Snapshot jobs PRIORIDAD #1 + analytics | 7-10 días |

**Coordinación:**
- F6-D-FIX1 (A+T) NO comparte archivos con F7 (T1/A/D). Cero conflicto.
- F7-A Dev A es DIFERENTE de F6-D-FIX1-A Dev A. Si vos solo tenés "un Dev A", usalo primero para F6-D-FIX1-A (30 min) y después arrancalo en F7-D. O abrí 2 chats Dev A distintos en paralelo.
- Dev W (Runtime Windows) se dispara cada vez que A o D pushean (vos pegás handoff Sesión 49 conocido).

### 🖥️ Handoff · Dev W · F7-D A2-3 + A2-4 + A2-7 post-push (~10 min)

```
Soy Runtime Agent · Windows del proyecto MotoShop.
Dev A2 acaba de pushear 3 endpoints nuevos que desbloquean
a Dev T2 (frontend). Necesito aplicar todo junto.

PRE-FLIGHT:
1. cd C:\Users\MotoShop\Documents\javidevmoto
2. git pull --ff-only origin main

MI MISIÓN:
Restart API y verificar 3 endpoints: cohortes-detail, drift-summary, plan-compras.

PASO 1 · git pull + restart API
  git pull --ff-only origin main
  Stop-Process -Name python -Force 2>$null
  .\infra\start_api.ps1
  Start-Sleep 10

PASO 2 · Smoke cohortes-detail
  curl http://127.0.0.1:8000/metrics/cohortes-detail ^
    -H "Authorization: Bearer <token>"
  # 200 con cohortes: cohorte_mes, ltv_promedio, retencion, ...

PASO 3 · Smoke drift-summary
  curl http://127.0.0.1:8000/metrics/drift-summary ^
    -H "Authorization: Bearer <token>"
  # 200 con items: metric_name, detected_at, drift_magnitude, threshold, status

PASO 4 · Smoke plan-compras
  curl http://127.0.0.1:8000/metrics/plan-compras ^
    -H "Authorization: Bearer <token>"
  # 200 con items: sku, nombre, stock_actual, demanda_7d, cantidad_a_comprar, abc, urgencia, dormido, supplier

PASO 5 · Reportar en SEGUIMIENTO.md:
  > 🟢 [Dev W] Rutina post-push A2-3 + A2-4 + A2-7 aplicada · commits: efb3041 + e4eb793 + 8e216ea · API restart OK · cohortes-detail 200 · drift-summary 200 · plan-compras 200
```

### 🖥️ Handoff · Dev W · F7-D A2-1 + A2-2 post-push (~10 min)

Abrí un chat Claude Code corriendo en la PC Windows. Pegá esto:

```
Soy Runtime Agent · Windows del proyecto MotoShop.
Mi rol es operativo: aplicar cambios pendientes que Dev A2
(backend) acaba de pushear a main.

PRE-FLIGHT:
1. cd C:\Users\MotoShop\Documents\javidevmoto
2. git pull --ff-only origin main
3. Verificar que la API esté corriendo actualmente:
   Get-Process python | Where-Object {$_.CommandLine -like "*uvicorn*"}

MI MISIÓN:
Dev A2 terminó 2 endpoints nuevos. Necesito aplicar el pull y
verificar que la API los sirve correctamente.

ENTREGABLES (en orden):

PASO 1 · git pull (~1 min)
  cd C:\Users\MotoShop\Documents\javidevmoto
  git pull --ff-only origin main

PASO 2 · Restart API (~3 min)
  # Solo si el código cambió (motoshop-app/api/src/):
  Stop-Process -Name python -Force 2>$null
  .\infra\start_api.ps1
  # Esperar 10s
  Start-Sleep 10

PASO 3 · Smoke test A2-1: sales-trend (~1 min)
  curl http://127.0.0.1:8000/metrics/sales-trend?periods=6 ^
    -H "Authorization: Bearer <tu-token-jwt>"
  # Debe devolver 200 con 6 items mensuales (year, month,
  # total_ventas, num_facturas, ticket_promedio)

PASO 4 · Smoke test A2-2: vendedores-summary (~1 min)
  curl http://127.0.0.1:8000/metrics/vendedores-summary ^
    -H "Authorization: Bearer <tu-token-jwt>"
  # Debe devolver 200 con ranking de vendedores (nit_vendedor,
  # nombre_vendedor, facturas, total_ventas, ticket_promedio)

PASO 5 · Reportar (~1 min)
  Escribí en SEGUIMIENTO.md exactamente esto::
  > 🟢 [Dev W] Rutina post-push A2-1 + A2-2 aplicada · commits: ec9c30f + 26cf1d5 · API restart OK · sales-trend 200 · vendedores-summary 200

SI ALGO FALLA (401, 500, timeout, API no arranca):
  - Documentá el error exacto con curl output copiado
  - Escribí en SEGUIMIENTO.md con 🔴 [Dev W]
  - El humano lo revisa conmigo

NO TOCO:
  - Notebooks (eso es para otro handoff de Dev D)
  - Workflow Databricks
  - MySQL / sgHermes
```

---

### 🤖 Handoff #1 · Dev T1 · F7-B Design System (~5-7 días)

Pegá esto en un chat Claude Code NUEVO:

```
Soy Dev T1 · Sprint F7-B Design System del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md (rol = Dev Agent · Track T)
4. Leé docs/f7/personas_kpis.md (qué necesitan los componentes que voy a construir)
5. Leé docs/f7/branding/colors.md COMPLETO (tokens listos para copy-paste)
6. Mirá docs/f7/branding/logo.png (es el logo real, PNG 1200×470)
7. Leé docs/f7/team_allocation.md §"Dev T1" (mis dependencias y a quién bloqueo)

MI MISIÓN:
Construir design system completo para F7. Tokens, 8 componentes
base, Logo, Navigation adaptable. Habilito que Dev T2 migre 8
pages + cree 4 nuevas en F7-C.

CRITICO: yo BLOQUEO a Dev T2 — no puede arrancar sin mis
componentes mínimos (Card, Stat, Table, Badge). Avisar en
SEGUIMIENTO cuando esos 4 estén listos para liberar T2.

ENTREGABLES (en orden de prioridad para desbloquear T2):

PASO 1 · Tokens (~45 min)
1. motoshop-app/web/lib/design/tokens.ts
   - Copy-paste exacto la sección "Tokens semánticos" de
     docs/f7/branding/colors.md
   - TypeScript estricto, tipos exportados
2. motoshop-app/web/tailwind.config.ts actualizado consumiendo
   tokens (extend theme)
3. motoshop-app/web/app/globals.css con CSS variables
   (copy-paste de colors.md §"CSS variables base")

PASO 2 · Logo component (~30 min)
1. cp docs/f7/branding/logo.png motoshop-app/web/public/logo.png
2. motoshop-app/web/components/Logo.tsx con:
   - Props: variant (full/mark/text), size (sm/md/lg), theme (auto/light/dark)
   - Usa <Image> de next/image con sizes responsive
   - Fallback: wrap en surfaceDark si fondo no compatible
3. Stories en docs/f7/components/Logo.md

PASO 3 · Componentes base prioritarios (~2 h, DESBLOQUEAN T2)
Crear en motoshop-app/web/components/ui/:

a) Card.tsx — props: variant (default/elevated/outlined), padding, header opcional
b) Stat.tsx — KPI con value, label, delta opcional, sparkline opcional, icon opcional
   - Reemplaza KpiCard ad-hoc actual con uno bien diseñado
   - Usa formatMoney de lib/format/currency.ts (post-FIX1)
c) Table.tsx — responsive: desktop = tabla, mobile = card stack
   - Props: columns config, rows, empty state, loading state, onRowClick
d) Badge.tsx — variants (primary/accent/success/warning/error/neutral),
   sizes (sm/md), with icon opcional

Cada uno con stories markdown en docs/f7/components/<name>.md.

CUANDO ESTOS 4 ESTÉN LISTOS:
1. Commit con prefix: feat(F7-B-design-mvp): tokens + Logo + Card + Stat + Table + Badge
2. Actualizá SEGUIMIENTO.md sección Dev T1 con: "✅ MVP T1 listo,
   Dev T2 puede arrancar F7-C"
3. SEGUÍ con paso 4 mientras T2 arranca en paralelo

PASO 4 · Componentes base secundarios (~2 h)
e) Chart.tsx — wrapper recharts con <ResponsiveContainer> SIEMPRE
   - Props: type (line/bar/area/pie), data, colors (de chart tokens)
   - Tooltip uniforme con tokens
f) Skeleton.tsx — loading reusable (card/line/circle variants)
g) ErrorState.tsx — error reusable con CTA "Reintentar"
h) EmptyState.tsx — lista vacía con mensaje + ilustración opcional

PASO 5 · Navigation adaptable (~1 h)
motoshop-app/web/components/Navigation.tsx:
- Mobile (< 768px): bottom navigation con 4-5 items principales
- Desktop (>= 768px): sidebar left con sub-items expandibles
- Items se configuran por rol (vendedor vs gerente — leer user.role)
- Touch targets ≥ 44px en mobile

PASO 6 · Cierre (~30 min)
1. npm run typecheck → 0 errors
2. npm run build → 0 errors
3. Capturas de cada componente en docs/f7/components/_screenshots/
4. Commit final: feat(F7-B-design-complete): ...
5. SEGUIMIENTO.md sección Dev T1 con "✅ F7-B cerrado"

NO TOCO:
- motoshop-app/web/app/(authenticated)/dashboards/** (Dev T2 migra)
- motoshop-app/web/app/(authenticated)/alerts/page.tsx (Dev T2)
- motoshop-app/api/** (Dev A backend)
- notebooks/** (Dev D)
- infra/** (Dev D / Dev W)

Commits prefix: feat(F7-B-design-*):

ARRANQUE: Paso 1 (tokens). Antes de tocar componentes asegurate
que tailwind.config.ts consume bien tokens. Smoke test:
crear un <div className="bg-primary text-primaryFg p-4"> y
verificar render.
```

---

### 🤖 Handoff #2 · Dev A · F7-D Backend FastAPI (~7-10 días)

Pegá esto en un chat Claude Code NUEVO (separado del F6-D-FIX1-A si es el mismo dev):

```
Soy Dev A · Sprint F7-D Backend FastAPI del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md (rol = Dev Agent · Track A)
4. Leé docs/f7/dashboards_content.md COMPLETO (que endpoints necesita cada feature)
5. Leé docs/f7/team_allocation.md §"Dev A" (mi rol, dependencias con Dev D)
6. Mirá motoshop-app/api/src/motoshop_api/metrics/router.py + repo.py
   como referencia de patrón existente
7. Verificá que F6-D-FIX1-A esté cerrada (fix valor_total) antes de
   tocar metrics. Si no, esperá 30 min o coordiná con quien lo hace.

MI MISIÓN:
Construir 5+ endpoints nuevos que el F7-C va a consumir + tabla
nueva app_purchase_plans + binding repos. Trabajo en paralelo con
Dev D — si necesito una tabla/vista que D produce, la mockeo con
SQL temporal hasta que D pushee.

ENTREGABLES (en orden de prioridad para desbloquear T2):

PASO 1 · GET /metrics/sales-trend?periods=6 (~1.5 h) [PRIORIDAD para HG2/V1]
1. motoshop-app/api/src/motoshop_api/metrics/router.py — agregar endpoint
2. metrics/repo.py — query Databricks SQL agregando por mes:
   SELECT YEAR(business_date) AS y, MONTH(business_date) AS m,
          SUM(total_factura) AS total, COUNT(*) AS num_facturas,
          AVG(total_factura) AS ticket_promedio
   FROM motoshop.silver.fact_ventas
   WHERE business_date >= ADD_MONTHS(CURRENT_DATE(), -6)
   GROUP BY y, m ORDER BY y, m
3. metrics/schemas.py — SalesTrendResponse, SalesTrendItem
4. Tests en tests/api/test_metrics_trend.py
5. Smoke local: curl con Bearer → 200 con 6 meses

PASO 2 · GET /metrics/vendedores-summary (~1 h) [VE1-VE5]
Query:
   SELECT nit_vendedor, nombre_vendedor,
          COUNT(*) AS facturas, SUM(total_factura) AS total,
          AVG(total_factura) AS ticket_promedio
   FROM motoshop.silver.fact_ventas
   WHERE business_date >= DATE_TRUNC('MONTH', CURRENT_DATE())
   GROUP BY nit_vendedor, nombre_vendedor
   ORDER BY total DESC LIMIT 10
Schema + tests + smoke.

PASO 3 · GET /metrics/cohortes-detail (~1 h) [CO1-CO5]
Consumir gold.mart_cohortes_clientes existente.
Schema con: cohort_month, retention_by_month, ltv, total_clientes.

PASO 4 · GET /metrics/drift-summary (~1 h) [DR1-DR4]
Consumir gold.alertas_drift existente (F6-A).
Schema con: alerts, threshold, recommended_action.

PASO 5 · GET /metrics/forecast-categoria (~1 h) [F1]
Consumir gold.forecast_categoria existente (F6-B).

PASO 6 · Migration + endpoint app_purchase_plans (~1.5 h) [PC6]
1. infra/migrations/F7-001-app_purchase_plans.sql:
   CREATE TABLE app_purchase_plans (
     id BIGINT AUTO_INCREMENT PRIMARY KEY,
     created_by VARCHAR(64) NOT NULL,
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
     plan_name VARCHAR(255),
     total_skus INT,
     total_value DECIMAL(15,2),
     items JSON,
     status ENUM('draft','approved','sent','received'),
     INDEX idx_user_created (created_by, created_at)
   ) ENGINE=InnoDB;
2. Endpoints CRUD en app_writes/purchase_plans.py:
   - POST /purchase-plans (create)
   - GET /purchase-plans (list paginated)
   - GET /purchase-plans/{id}
   - PATCH /purchase-plans/{id}/status
3. Dev W debe aplicar migration en Windows después de mi push.

PASO 7 · GET /metrics/plan-compras (~2 h) [PC1-PC5]
Endpoint complejo que combina:
- gold.alertas_quiebre (urgencia)
- gold.forecast_demanda_sku (demanda predicha)
- mart_rotacion_abc (categoría ABC)
- mart_productos_dormidos (excluir o flag)
- mart_inventario_actual (stock actual)

Output: lista de SKUs con cantidad_a_comprar calculada +
recomendación supplier.

Si Dev D NO ha producido gold.mart_abc_xyz aún, mockeo el join.

PASO 8 · Cierre (~30 min)
1. pytest tests/api/ → 100% pass
2. uvicorn local smoke test
3. Commit final: feat(F7-D-backend-complete): ...
4. SEGUIMIENTO.md sección Dev A con "✅ F7-D cerrado"

NO TOCO:
- motoshop-app/web/** (Dev T1 / T2)
- notebooks/** (Dev D)
- infra/migrations/F5-* o F6-* (ya cerradas)
- Tablas sgHermes (intocable)
- users.yaml (R15 diferida)

COORDINACIÓN:
- Si necesito tabla nueva de Dev D (ej. mart_abc_xyz, snapshots):
  mockeo con SQL temporal y dejo TODO en código. Reemplazo cuando
  D pushee.
- Cada push avisa a Dev W para que reinicie API en Windows.

Commits prefix: feat(F7-D-backend-*):

ARRANQUE: Paso 1 (sales-trend) — es el endpoint que más
desbloquea a T2 (lo usan HG2 home gerente y V1 ventas page).
```

---

### 🤖 Handoff #3 · Dev D · F7-E Databricks + Snapshots (~7-10 días)

Pegá esto en un chat Claude Code NUEVO:

```
Soy Dev D · Sprint F7-E Databricks + Snapshots del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md (rol = Dev Agent · Track A · subteam analítico)
4. Leé docs/f7/dashboards_content.md §"Balde B" (mi trabajo crítico)
5. Leé docs/f7/team_allocation.md §"Dev D" (mi rol, prioridad #1)
6. Leé infra/create_full_workflow.py (estructura actual del workflow)
7. Leé notebooks/gold/19_feature_store.py + 24_forecast_categoria.py
   como referencia de patrón

MI MISIÓN:
PRIORIDAD #1: activar snapshot jobs balde B HOY MISMO. Cuanto
antes empiecen a acumular, más datos para la defensa académica
(en ~30 días). Cada día perdido = 1 día menos de historia.

Después: cálculos analíticos nuevos (rotación, cobertura, ABC×XYZ)
y soporte a endpoints de Dev A.

ENTREGABLES (PRIORIDAD ESTRICTA):

PASO 1 · Snapshot jobs balde B (DÍA 1-2 — PRIORIDAD MÁXIMA)

a) notebooks/gold/30_snapshot_abc_mensual.py:
   - Cada 1ro del mes (o trigger manual), guarda copy de
     mart_rotacion_abc en gold.mart_rotacion_abc_snapshots
   - Agrega columna snapshot_month = DATE_FORMAT(CURRENT_DATE(), 'yyyy-MM')
   - INSERT INTO snapshots ... SELECT FROM mart_rotacion_abc

b) notebooks/gold/31_snapshot_dormidos_mensual.py:
   - Mismo patrón para mart_productos_dormidos
   - Tabla destino: gold.mart_productos_dormidos_snapshots

c) notebooks/gold/32_snapshot_alertas_diario.py:
   - Snapshot diario de gold.alertas_quiebre
   - Tabla destino: gold.alertas_quiebre_snapshots
   - Agrega columna snapshot_date

d) notebooks/gold/33_archive_forecasts.py:
   - ANTES de que forecast_demanda_sku se sobrescriba, guardar
     versión actual en gold.forecast_demanda_sku_archive
   - Permite backtesting visual (F3 feature)

PASO 2 · Modificar workflow (DÍA 2)
infra/create_full_workflow.py:
- Agregar 4 tasks nuevas al workflow:
  * Snapshot ABC (mensual: solo corre si DAY(CURRENT_DATE())=1)
  * Snapshot dormidos (mensual: idem)
  * Snapshot alertas (diario: siempre)
  * Archive forecasts (diario: corre ANTES de que se sobrescriba)
- Dependencias correctas entre tasks
- Avisar a Dev W para re-deploy workflow

PASO 3 · Verificar primera corrida snapshots (DÍA 2-3)
- Disparar workflow manual desde Databricks UI
- Verificar tablas snapshots tienen al menos 1 fila
- Documentar en notebooks/gold/_runs/v_f7e_snapshots_arrancan_<ts>.md

PASO 4 · Cálculo rotación promedio (DÍA 3-4)
notebooks/gold/22_rotacion_promedio.py:
- Calcular: SUM(cantidad_vendida_ultimos_90d) / 90 = venta_diaria_promedio
- Para cada SKU: stock_actual / venta_diaria_promedio = días_de_cobertura
- Output: gold.mart_rotacion_sku
- Para I3 (inventario) e I6 (cobertura)

PASO 5 · Cálculo ABC × XYZ (DÍA 5-6)
notebooks/gold/23_abc_xyz.py:
- ABC ya existe en mart_rotacion_abc
- XYZ calcular: coeficiente de variación (CV) de ventas diarias
  por SKU últimos 90 días
  * X = CV < 0.5 (predictivo)
  * Y = 0.5 ≤ CV < 1 (medio)
  * Z = CV >= 1 (errático)
- Output: gold.mart_abc_xyz con columnas: cod_producto, abc, xyz, bucket
- Para A1 (ABC × XYZ matrix)

PASO 6 · Soporte a Dev A (DÍA 6-7)
- Si Dev A pide vistas específicas para sus endpoints, generarlas
- Validar que tablas que A consume están actualizadas
- Coordinar via SEGUIMIENTO

PASO 7 · Cierre (DÍA 7)
1. Re-correr workflow completo y verificar 0 fails
2. Documentar en notebooks/gold/_runs/v_f7e_complete_<ts>.md
3. Commit: feat(F7-E-databricks-complete): ...
4. SEGUIMIENTO.md sección Dev D con "✅ F7-E cerrado, snapshots
   acumulando, primer dato útil en 30 días"

NO TOCO:
- motoshop-app/** (Dev T / Dev A)
- notebooks/bronze|silver/** (estables)
- infra/migrations/F5-* o F6-* (cerradas)
- infra/start_*.ps1 (Dev W)

COORDINACIÓN:
- Cada push a notebooks/** → avisar a Dev W para
  upload_all_notebooks.py
- Cada modificación a create_full_workflow.py → Dev W debe
  re-deploy workflow
- Si Dev A necesita una tabla nueva mía, priorizarla

Commits prefix: feat(F7-E-databricks-*) o feat(F7-E-snapshot-*)

ARRANQUE: Paso 1 (snapshot jobs). NO empieces analytics
antes que los snapshots estén corriendo en producción.
Snapshots = prioridad #1 porque acumulan tiempo.
```

---

### Próximo paso del revisor (yo)

Cuando los devs pushen incrementalmente:

1. **Dev T1 reporta MVP listo** (Card+Stat+Table+Badge) → yo redacto handoff Dev T2
2. **Dev A pushea endpoint** → vos disparás Dev W para restart API
3. **Dev D pushea snapshot job** → vos disparás Dev W para sync notebooks + workflow re-deploy
4. **Audit incremental:** cuando cada uno cierre, yo audito
5. **E5 memoria:** empezar con capturas continuas cuando T2 vaya migrando pages

### Pendiente humano transversal

- Demo 4G (R6): grabar desde celular en `app.fragloesja.uk`
- Demo gerencia (R8): agendar 30 min con stakeholder

---

## Sesión 2026-05-30 (50) · F6-D-FIX1 hot bugs + F7 reestructuración UX

**Estado:** F6-D cerrada ✅ (audit Sesión 49 PASS). Humano hizo smoke test en `https://app.fragloesja.uk` y detectó 3 bugs visibles + pidió fase nueva de UX/mobile.

**Bugs detectados (audit revisor confirmó):**

| # | Bug | Causa raíz |
|---|-----|-----------|
| 1 | `/dashboards/dormidos` → 404 | Frontend: la ruta no existe en filesystem Next.js. Solo hay abc/, inventario/, ventas/. El endpoint `/metrics/dormidos` SÍ funciona. |
| 2 | Ticket promedio "$0.0M" con 911 facturas | Frontend formatter: API devuelve `ticket_promedio: 25813.95`. PWA divide siempre por 1M y trunca a 1 decimal → "$0.0M". |
| 3 | Valor inventario "$0.0M" | Backend real: API devuelve `valor_total: 0.0` literal. Query `inventory-summary` no hace `SUM(cantidad × costo)`. |

**Plan correctivo:** [`docs/plan-f6-d-fix1.md`](docs/plan-f6-d-fix1.md) — 2 sprints micro paralelos (~1h wall-clock).

**Fase nueva agregada al roadmap:** [`docs/plan-f7.md`](docs/plan-f7.md) — F7 · Reestructuración UX + Mobile-first. Arranca DESPUÉS de cerrar F6-D-FIX1.

### 🤖 Handoff #1 · Dev A · Sprint F6-D-FIX1-A · Backend (~30 min)

Pegá esto en un chat Claude Code nuevo en tu Mac:

```
Soy Dev A · Sprint F6-D-FIX1-A del proyecto MotoShop.

PRE-FLIGHT:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f6-d-fix1.md COMPLETO

MI MISIÓN:
Fix Bug 3: /metrics/inventory-summary devuelve valor_total = 0.0.
La query no está multiplicando cantidad × costo. Hay que arreglarla
para que retorne el valor monetario real del inventario.

ENTREGABLES:
1. Audit query en motoshop-app/api/src/motoshop_api/metrics/repo.py
2. Fix con SUM(stock_actual * COALESCE(costo_promedio, 0))
3. Verificar campo correcto en mart_inventario_actual (puede ser
   costo_promedio, ultimo_costo, costo, etc — usar lo que exista)
4. Tests pasan
5. Smoke test local: curl /metrics/inventory-summary → valor_total > 0
6. Evidencia en motoshop-app/api/_runs/v_fix_inventory_valor_<ts>.md

NO TOCO:
- motoshop-app/web/** (Dev T)
- notebooks/** (no aplica)
- infra/** (no aplica)

Commits: fix(F6-D-FIX1-A-backend): ...

ARRANQUE: Paso A1 (audit query). Si la columna costo no existe en
el mart, NO inventes — proponé en lecciones o pedí intervención
humana para definir qué campo usar.
```

### 🤖 Handoff #2 · Dev T · Sprint F6-D-FIX1-B · Frontend (~45-60 min)

Pegá esto en otro chat Claude Code nuevo:

```
Soy Dev T · Sprint F6-D-FIX1-B del proyecto MotoShop.

PRE-FLIGHT:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f6-d-fix1.md COMPLETO
4. Leé motoshop-app/web/app/(authenticated)/dashboards/ventas/page.tsx
   como referencia de estructura

MI MISIÓN:
Fix Bug 1: crear página /dashboards/dormidos (404 hoy).
Fix Bug 2: refactor formatter para que NO muestre "$0.0M" para
valores < $1M. Usar sufijo K/M según magnitud.

ENTREGABLES:
1. motoshop-app/web/app/(authenticated)/dashboards/dormidos/page.tsx
   consumiendo GET /metrics/dormidos via SWR
2. Layout consistente con ventas/inventario/abc
3. motoshop-app/web/lib/format/currency.ts con formatMoney(value):
   - >=1M → "1.2M"
   - >=1K → "1.2K"
   - <1K → "$847" con thousand separator
4. Reemplazar formateo viejo en todas las pages de dashboards
5. Tests unit del formatter
6. Smoke local (npm run dev) + smoke producción (vercel --prod)
7. Evidencia en motoshop-app/web/_runs/v_fix_dashboards_<ts>.md

NO TOCO:
- motoshop-app/api/** (Dev A)
- infra/** (no aplica)

Commits: fix(F6-D-FIX1-B-frontend): ...

ARRANQUE: Paso B1 (página dormidos). Antes de tocar el formatter,
verificá que la página dormidos carga con datos. Después refactor
formatter.
```

### Próximo paso del revisor (después de cerrar F6-D-FIX1)

Cuando Dev A y Dev T pushen final:

1. Yo audito 5 V-FIX1 (smoke test endpoints + páginas)
2. Si PASS → F6-D-FIX1 ✅ cerrada
3. **Arranco Sprint F7-A Discovery con vos** — sesión conjunta para:
   - Audit visual actual con screenshots
   - Definir personas + KPIs prioritarios
   - Branding (¿hay logo? ¿colores existentes?)
   - Cronograma F7-B/C
4. Vos decidís: ¿F7 antes o después de la defensa académica? (impacta urgencia)

### Pendiente humano antes de F7

- **Decidir cuándo va F7**: antes o después de defensa académica
- **¿Hay logo MotoShop / branding existente?** O empezamos desde cero
- **Demos R6 (4G) + R8 (gerencia)** siguen pendientes — pueden agendarse en paralelo a F6-D-FIX1

---

## Sesión 2026-05-30 (48b) · F6-D · Mitigación SPOF con Render free + UptimeRobot

**Corrección Sesión 48b:** El handoff original (48a) proponía Fly.io. Verificación posterior reveló que Fly.io ya no tiene "always free" tier (solo 7 días trial). Decisión humana revisada: **Render free + UptimeRobot** (gratis siempre, sin tarjeta).

**Estado:** Runtime Windows reportó SPOF crítico — API + MySQL solo viven en la PC, si se apaga toda la web cae. Vos decidiste mitigarlo HOY con **Render free** (gratis siempre) + **UptimeRobot** (pinga cada 5 min para evitar sleep).

**Estrategia híbrida cloud + on-premise:**

| Endpoint | Servido por | Disponibilidad |
|----------|-------------|----------------|
| `/health`, `/auth/login` | Fly.io (users.yaml en el deploy) | 24/7 ☁️ |
| `/metrics/*`, `/alerts/*`, `/forecast/*` | Fly.io (lee Databricks) | 24/7 ☁️ |
| `/products`, `/stock`, `/sales/recent` | Devuelven 503 desde Fly | Solo via Windows API |
| `/alerts/{id}/action` (write MySQL) | Devuelve 503 desde Fly | Solo via Windows API |

**Defensa académica:** "El producto predictivo (F4) está siempre disponible en cloud. El catálogo operativo depende del PC de la tienda — limitación arquitectónica conscientemente aceptada por ADR-0007 (mitigación completa en F7 post-curso)."

### 🌐 Handoff #1 · Dev T · Deploy API a Render free (~35 min)

Pegá esto en un chat Claude Code nuevo en tu Mac:

```
Soy Dev T · Track T · Sprint F6-D del proyecto MotoShop.
Mi misión es desplegar la API FastAPI a Render free como
mitigación del SPOF Windows. La API en Render solo servirá
endpoints que leen de Databricks. Endpoints MySQL devolverán
503 graceful.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo
4. Leé docs/plan-f6.md (contexto F6)
5. Leé motoshop-app/api/pyproject.toml + src/motoshop_api/config.py
6. Leé motoshop-app/api/src/motoshop_api/main.py (lifespan)

MI MISIÓN:
Deploy API analítica a Render free. Endpoints Databricks funcionan
24/7 (con UptimeRobot evitando el sleep). Endpoints MySQL devuelven
503 graceful. Setup subdomain cloud-api.fragloesja.uk para que el
humano lo configure en Cloudflare después.

CONTEXTO Render free:
- Gratis siempre (Hobby plan, sin tarjeta requerida)
- 750 horas/mes (suficiente para 1 web service 24/7 = ~744 hrs)
- Se duerme tras 15 min sin requests
- Cold start ~1 minuto cuando se duerme
- Mitigación: UptimeRobot pingea cada 5 min para mantenerla viva

ENTREGABLES (en orden):

PASO 1 · render.yaml (~10 min)
Crear motoshop-app/api/render.yaml (Infrastructure as Code):

   services:
     - type: web
       name: motoshop-cloud-api
       runtime: python
       plan: free
       region: oregon  # closest free region (Virginia/Oregon)
       buildCommand: pip install -e .
       startCommand: uvicorn motoshop_api.main:app --host 0.0.0.0 --port $PORT
       healthCheckPath: /health
       envVars:
         - key: PYTHON_VERSION
           value: 3.11.9
         - key: DATABRICKS_HOST
           sync: false  # humano lo setea en dashboard
         - key: DATABRICKS_TOKEN
           sync: false
         - key: DATABRICKS_HTTP_PATH
           value: /sql/1.0/warehouses/43bc044eaef4cca4
         - key: JWT_SECRET
           sync: false
         - key: CORS_ORIGINS
           value: https://motoshop-web-tau.vercel.app,https://app.fragloesja.uk
         - key: ENV
           value: dev

Verificar que motoshop-app/api/pyproject.toml tiene los entry points
correctos (uvicorn como dependencia).

PASO 2 · Verificar setup local (~5 min)
1. cd motoshop-app/api
2. pip install -e .
3. uvicorn motoshop_api.main:app --port 8000 → debe arrancar
4. curl http://localhost:8000/health → 200
5. Stop

PASO 3 · Render dashboard setup (~10 min)
NOTA: Render se configura desde su UI web, NO CLI.

1. Login https://dashboard.render.com (signup con GitHub)
2. New + → Web Service
3. Connect GitHub repo: javierportillar/motoshopData
4. Configurar:
   - Name: motoshop-cloud-api
   - Root Directory: motoshop-app/api
   - Runtime: Python
   - Build Command: pip install -e .
   - Start Command: uvicorn motoshop_api.main:app --host 0.0.0.0 --port $PORT
   - Plan: Free
   - Region: Oregon (o Virginia, ambos tienen free)

5. En Environment Variables (CRITICO copiar de Windows):
   - DATABRICKS_HOST = (de motoshop-app/api/.env Windows)
   - DATABRICKS_TOKEN = (de motoshop-app/api/.env Windows)
   - DATABRICKS_HTTP_PATH = /sql/1.0/warehouses/43bc044eaef4cca4
   - JWT_SECRET = (DEBE ser el mismo que Windows!)
   - CORS_ORIGINS = https://motoshop-web-tau.vercel.app,https://app.fragloesja.uk
   - ENV = dev

6. Click "Create Web Service"
7. Render deploya automáticamente desde main. ~3-5 min build + deploy.
8. Capturar URL final (ej. https://motoshop-cloud-api.onrender.com)

PASO 4 · Smoke test (~5 min)
1. curl https://motoshop-cloud-api.onrender.com/health → 200
2. Login y captura token
3. curl /alerts/stockout con Bearer → 200 con 46 alertas
4. curl /products?q=aceite con Bearer → 500/503 esperable
   (MySQL no configurado, comportamiento correcto)

PASO 5 · Setup UptimeRobot anti-sleep (~5 min)
1. Signup https://uptimerobot.com (free, sin tarjeta)
2. New Monitor:
   - Type: HTTP(s)
   - URL: https://motoshop-cloud-api.onrender.com/health
   - Interval: 5 minutes (cada 5 min)
   - Name: motoshop-cloud-api-keepalive
3. Save
4. Documentar URL + interval en evidencia

PASO 6 · Update PWA con fallback inteligente (~10 min)
Editar motoshop-app/web/lib/api/* para:
- Try Render primary
- Si 5xx en endpoints MySQL (/products, /stock, /sales, /alerts/{id}/action):
  mostrar UI fallback "Esta funcionalidad requiere el sistema
  operativo encendido. Predicciones y alertas están disponibles 24/7."
- Endpoints Databricks (/metrics, /alerts/stockout, /forecast):
  errores normales

Actualizar NEXT_PUBLIC_API_URL en Vercel:
   npx vercel env rm NEXT_PUBLIC_API_URL production
   npx vercel env add NEXT_PUBLIC_API_URL production
   → Pegar: https://motoshop-cloud-api.onrender.com
   npx vercel --prod

PASO 7 · Smoke test PWA (~5 min)
1. Abrir https://motoshop-web-tau.vercel.app
2. Login admin/FG28 → debe entrar
3. /forecast → carga
4. /alerts → 46 alertas
5. /products → UI fallback elegante
6. Documentar en motoshop-app/web/_runs/v_render_smoke_<ts>.md

PASO 8 · Documentación (~5 min)
Crear motoshop-app/api/_runs/v_render_deploy_<ts>.md con:
- URL Render producción
- Env vars configuradas (lista, NO valores)
- Region (Oregon/Virginia)
- UptimeRobot monitor URL + interval
- Resultado smoke test (200 vs 503 esperables)
- Build time
- Para humano: tiene que agregar CNAME cloud-api.fragloesja.uk
  → motoshop-cloud-api.onrender.com en Cloudflare

Commits con prefijo: feat(F6-D-cloud-api): ...

NO TOCO:
- infra/** (Runtime Windows)
- Notebooks
- DNS Cloudflare (humano)

REPORTE FINAL EN CHAT:
1. URL Render producción
2. URL UptimeRobot monitor
3. Endpoints que funcionan 200: lista
4. Endpoints que devuelven 503: lista (esperable, no son bug)
5. ¿PWA Vercel ya apunta a Render?
```

### 👤 Handoff #2 · Acción humana · CNAME `cloud-api.fragloesja.uk` (~5 min)

Después que Dev T te dé la URL Render:

1. Login `dash.cloudflare.com` → `fragloesja.uk` → DNS → Add record
2. Type: **CNAME** (Render usa hostnames, no IPs fijas)
3. Name: `cloud-api`
4. Target: `motoshop-cloud-api.onrender.com` (la URL que dio Render sin https://)
5. Proxy: **DNS only** (gris)
6. Save → esperar 1-5 min
7. `dig cloud-api.fragloesja.uk` debe apuntar a Render
8. En Render dashboard: Settings → Custom Domain → Add `cloud-api.fragloesja.uk`
9. Render valida el dominio y emite TLS Let's Encrypt automáticamente

Después actualizar PWA env var:
```
npx vercel env rm NEXT_PUBLIC_API_URL production
npx vercel env add NEXT_PUBLIC_API_URL production
→ https://cloud-api.fragloesja.uk
npx vercel --prod
```

### 🔁 Handoff #3 · Runtime Windows · NO tocar (esperar)

Runtime Windows NO necesita hacer nada en este sprint. La API Windows queda corriendo como respaldo "operativo" para cuando el dueño esté en la tienda con PC encendida.

### Próximo paso del revisor (Sesión 49)

Cuando Dev T reporte `https://motoshop-cloud-api.fly.dev/alerts/stockout` → 200:

1. Yo verifico con probe propia
2. Yo escribo:
   - **ADR-0022** (deployment híbrido cloud + on-premise)
   - **R17 actualizada**: "SPOF mitigado parcialmente. Analíticos 24/7. Operativos siguen on-premise (ADR-0007). Migración completa F7 post-curso."
3. Vos grabás demo 4G **con la PC apagada** (test REAL del SPOF mitigation)
4. Agendás demo gerencia
5. Avisás → E5 + audit cierre

---

## Sesión 2026-05-30 (47) · Diagnosis /alerts y /forecast pre-demo

**Estado:** Runtime Windows y Dev T Vercel cerraron lo suyo:
- ✅ API arriba (`/health` 200, `/auth/login` 200 con JWT válido, env=dev)
- ✅ PWA en Vercel (`motoshop-web-tau.vercel.app`) + custom domain (`app.fragloesja.uk` resolviendo, A record 76.76.21.21 ya configurado por humano)
- ✅ Workflow Databricks UNPAUSED, notebooks subidos
- ✅ CORS Vercel agregado en API
- 🟢 F6-001 partition documentado honestamente como "no aplicable MySQL 5.0, diferido F7" — decisión técnica correcta

**🔴 Bloqueante crítico para demo 4G (detectado en audit revisor Sesión 47):**

```
GET /alerts/stockout    → 500 Internal Server Error
GET /forecast/health    → 500 Internal Server Error
```

Tanto `/alerts/*` como `/forecast/*` dependen del Databricks SDK + SQL Warehouse. El smoke test de Dev T ya detectó el 500 honestamente. Causas probables:
- (a) SQL Warehouse Databricks paused (auto-stop 10 min) y warm-up tarda más que el timeout
- (b) `DATABRICKS_TOKEN` en `.env` de Windows expirado
- (c) Tabla `gold.alertas_quiebre` o `gold.forecast_demanda_sku` no accesible

Sin estos endpoints arriba, la demo 4G pierde el punto académico más fuerte (cierre del loop predicción → acción) — las páginas /alerts y /forecast van a mostrar error.

### 🖥️ Handoff · Runtime Dev · Diagnosis Databricks endpoints (~10 min)

Pegá esto en un chat Claude Code corriendo en la PC Windows:

```
Soy Runtime Dev · Windows del proyecto MotoShop.
Mi misión es diagnosticar por qué /alerts/stockout y
/forecast/* devuelven 500.

PRE-FLIGHT:
1. cd C:\Users\MotoShop\Documents\javidevmoto
2. git pull --ff-only origin main
3. Verificar API responde local:
   curl http://127.0.0.1:8000/health → 200

PASO 1 · Diagnóstico API logs (~3 min)
Mirar los logs de uvicorn para identificar la causa raíz:
   Get-Content -Path infra\logs\api.log -Tail 50
Buscar el stacktrace de las requests /alerts/stockout y
/forecast/health. Identificar cuál de las 3 causas es:
  (a) DatabricksError de auth → token expirado
  (b) Timeout HTTPError → warehouse paused (auto-stop 10 min)
  (c) Table not found / permission denied → permisos o naming

Si no hay logs útiles en api.log, reiniciar la API y reproducir:
1. Stop la instancia actual
2. Start con: $env:LOG_LEVEL="DEBUG"; .\infra\start_api.ps1
3. Esperar 30s
4. curl https://api.fragloesja.uk/alerts/stockout → 500
5. Get-Content -Path infra\logs\api.log -Tail 30

PASO 2 · Verificar SQL Warehouse activo (~3 min)
1. Abrir Databricks UI → SQL Warehouses
2. Verificar warehouse 43bc044eaef4cca4 está "Running" o "Starting"
3. Si está "Stopped", arrancarlo manualmente (botón Start)
4. Esperar 60-90s a que termine warm-up (state = Running)
5. Re-probar desde Windows local:
   $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/login" `
     -Method POST -ContentType "application/json" `
     -Body '{"username":"admin","password":"FG28"}'
   $token = $resp.access_token
   curl http://127.0.0.1:8000/alerts/stockout -H "Authorization: Bearer $token"
6. Si responde 200 con warehouse warm → la causa era (a) o (b).
   Documentar tiempo de warm-up.

PASO 3 · Verificar token Databricks (~2 min)
1. cat motoshop-app\api\.env | findstr DATABRICKS
2. Verificar que DATABRICKS_TOKEN no esté vacío ni truncado
3. Si está sospechoso:
   - Generar nuevo PAT en Databricks UI:
     User Settings → Developer → Access Tokens → Generate
   - Lifetime: 90 días
   - Comment: "motoshop-api-prod"
   - Actualizar .env con el nuevo token
   - Reiniciar API (.\infra\start_api.ps1)

PASO 4 · Verificar acceso a tablas gold (~2 min)
En Databricks SQL Editor:
   SELECT COUNT(*) FROM motoshop.gold.alertas_quiebre;
   SELECT COUNT(*) FROM motoshop.gold.forecast_demanda_sku;
Esperar:
   - alertas_quiebre: ~46 filas (segun F4-FIX1)
   - forecast_demanda_sku: ~4,436 filas
Si una tabla devuelve 0 o error: el job nocturno no corrió o falla
de permisos. Re-correr manualmente motoshop_full_workflow.

PASO 5 · Smoke test final end-to-end (~2 min)
1. Probar /forecast desde Windows local:
   curl http://127.0.0.1:8000/forecast/MOTS1297 -H "Authorization: Bearer $token"
   → debe devolver 200 con forecast
2. Repetir desde túnel:
   curl https://api.fragloesja.uk/alerts/stockout -H "Authorization: Bearer $token"
   curl https://api.fragloesja.uk/forecast/MOTS1297 -H "Authorization: Bearer $token"
   → ambos deben devolver 200

PASO 6 · Documentar (~3 min)
Crear infra/logs/diagnosis_alerts_forecast_<ts>.md con:
- Causa raíz identificada (a/b/c)
- Tiempo de warm-up del SQL Warehouse (si aplica)
- Cambios aplicados (token rotation, warehouse start, etc.)
- Output del smoke test final (200 OK con datos)
- Recomendación: ¿el warehouse paused es una deuda para F7?
  (auto-stop 10 min es agresivo para una PWA de operador
   que la usa cuando entra un cliente — tal vez 1h sería mejor)

Commit con prefijo: fix(F6-windows-diagnosis): ...

NO TOCO:
- Código fuente (eso es Dev A si hay bug)
- users.yaml (R15 diferida)
- Tablas sgHermes
- Vercel / DNS Cloudflare

ENTREGABLE FINAL EN CHAT:
1. Causa raíz (a/b/c)
2. Status final: /alerts/stockout y /forecast responden 200 desde túnel?
3. Tiempo warm-up del warehouse si era (b)
4. Si hay deuda residual (ej. SQL Warehouse auto-stop muy corto)
```

### Próximo paso del revisor (cuando termine)

Cuando Runtime Dev confirme que `https://api.fragloesja.uk/alerts/stockout` con Bearer responde **200 con datos**:

1. Yo verifico con mi propia probe
2. Vos arrancás demo 4G (R6) desde celular en `https://app.fragloesja.uk`
3. Agendás demo gerencia (R8)
4. Me avisás → arranco E5 memoria final + audit cierre del proyecto

Si la causa era (a) o (b) warehouse paused, agregamos como **R17 nuevo**: SQL Warehouse auto-stop 10 min es muy agresivo para uso interactivo desde PWA. Trigger: F7+ cuando MotoShop tenga uso real continuo, subir a 1h o pasar a serverless siempre-on.

---

## Sesión 2026-05-30 (46) · F6 completado · 🟢 demo 4G desbloqueada

**Estado:** ✅ Runtime Windows completado. ✅ PWA deployada a Vercel (Dev T). Pendiente humano: agregar A record en Cloudflare DNS para `app.fragloesja.uk`.

**Bloqueantes resueltos:**

1. ✅ **API revivida** — túnel Cloudflare operativo (`api.fragloesja.uk` → 200). API con `ENV=dev`, `CORS_ORIGINS` actualizado con Vercel.
2. ✅ **PWA deployada** — en `https://motoshop-web-tau.vercel.app` (Dev T). Falta DNS: agregar A record `app` → `76.76.21.21` en Cloudflare para el dominio custom.
3. ✅ **Workflow Databricks** — `motoshop_full_workflow` scheduleado a 19:00 COL, UNPAUSED. Corrida manual en progreso.
4. ✅ **Notebooks** — 36 notebooks subidos a Databricks Workspace.
5. ⚠️ **F6-001 partition** — MySQL 5.0 no soporta. Diferido a F7.

**Decisiones humanas tomadas (2026-05-30):**
- Hostear PWA en **Vercel + DNS A record en Cloudflare** (opción B). Subdominio: `app.fragloesja.uk`.
- Dejar `Sashita123`/`FG28`/`users.yaml` como están (R1/R2/R15 aceptadas).

**3 trabajos en paralelo para desbloquear demo:**

---

### 🖥️ Handoff #1 · Runtime Dev · PC Windows (~30 min)

Abrí un chat Claude Code corriendo en la PC Windows (o ejecutalo manual). Pegá esto:

```
Soy Runtime Dev · Windows del proyecto MotoShop.
Mi rol es operativo: aplicar cambios pendientes en la PC Windows
que es el servidor de producción.

PRE-FLIGHT obligatorio:
1. cd C:\Users\MotoShop\Documents\javidevmoto
2. git pull --ff-only origin main
3. Verificar versión MySQL local: mysql --version
4. Verificar que MotoShop_HealthCheck Scheduled Task esté ACTIVO

MI MISIÓN:
F6-A dejó cambios en código y una migration SQL que requieren
aplicarse manualmente en Windows. Adicionalmente, la API
está caída (Cloudflare 530) — hay que diagnosticar y revivir.

ENTREGABLES (en orden):

PASO 1 · Diagnóstico API caída (~5 min)
1. Get-Process | Where-Object {$_.Name -match "cloudflared|python|uvicorn"}
2. Si NO hay procesos, ejecutar:
   .\infra\start_api.ps1
   .\infra\start_tunnel.ps1
3. Esperar 30s. curl http://127.0.0.1:8000/health debe responder 200.
4. Si responde local pero el túnel no, reiniciar cloudflared.
5. Verificar https://api.fragloesja.uk/health desde fuera (200 OK).

PASO 2 · Aplicar migration F6-001 (~10 min)
1. Backup primero: mysqldump motoshop2024 app_audit_log > backup_audit_log_pre_f6.sql
2. Verificar versión MySQL soporta partitioning:
   mysql -u root motoshop2024 -e "SHOW PLUGINS;" | findstr partition
3. Si MySQL es 5.0 exacto: NO soporta partitioning real. Documentar
   en infra/migrations/_runs/f6_partition_<ts>.md como "no aplicable
   en MySQL 5.0, deuda diferida a F7".
4. Si MySQL es 5.1+: aplicar migration:
   mysql -u root motoshop2024 < infra\migrations\F6-001-app_audit_log_partition.sql
5. Verificar particiones:
   mysql -u root motoshop2024 -e "SELECT PARTITION_NAME, TABLE_ROWS FROM information_schema.PARTITIONS WHERE TABLE_NAME='app_audit_log';"
6. Documentar en infra/migrations/_runs/f6_partition_<ts>.md con
   output completo.

PASO 3 · Reiniciar API con código nuevo (~5 min)
1. Después del git pull, reiniciar la API para que tome:
   - ENV guardrail en main.py lifespan
   - Cualquier nuevo endpoint
2. Stop API actual + arrancar de nuevo con start_api.ps1
3. Verificar logs de startup: el ENV guardrail no debe rechazar
   el arranque (ENV=dev, host=localhost → OK).
4. Smoke test:
   curl https://api.fragloesja.uk/health → 200

PASO 4 · Sync notebooks a Databricks (~5 min)
1. python infra\upload_all_notebooks.py
   (sube los notebooks F6-B nuevos: 24_forecast_categoria,
    25_drift_monitor)
2. Verificar en UI Databricks que están actualizados.

PASO 5 · Workflow nuevo verificación (~5 min)
1. Verificar que motoshop_full_workflow (ID 272152121206178) esté
   UNPAUSED en Databricks UI.
2. Si la corrida nocturna 19:00 COL no arrancó, dispararla manual
   para validar end-to-end.

PASO 6 · CORS preparación (si Dev T avisa) (~3 min)
Si Dev T (Vercel) avisa que el browser tira error CORS desde el
dominio Vercel, agregar a motoshop-app/api/.env en Windows:
   CORS_ORIGINS=https://api.fragloesja.uk,https://motoshop-web.vercel.app,https://app.fragloesja.uk,http://localhost:3000
Reiniciar API.

NO TOCO:
- users.yaml (R15 diferida)
- start_api.ps1 / start_tunnel.ps1 (operativos, no modificar)
- Tablas sgHermes (intocable)
- Código fuente — solo aplicar cambios ya pusheados

CIERRE:
Cuando los 5 pasos pasen, commit + push:
- infra/migrations/_runs/f6_partition_<ts>.md (evidencia)
- Cualquier evidencia adicional en _runs/

Después actualizar PENDIENTES.md con "✅ Windows F6 aplicado".
```

---

### 🌐 Handoff #2 · Dev T · Deploy PWA a Vercel (~25 min)

**Arrancá DESPUÉS que Runtime Dev confirme `https://api.fragloesja.uk/health` = 200.**

Abrí un chat Claude Code nuevo en tu Mac y pegá esto:

```
Soy Dev T · Track T · F6-C-PWA-Deploy del proyecto MotoShop.
Mi misión es desplegar la PWA Next.js 14 a Vercel y dejarla
lista para apuntar a app.fragloesja.uk (DNS lo configura el
humano en Cloudflare).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track T)
4. Leé motoshop-app/web/package.json + next.config.mjs
5. Verificá Vercel CLI instalado: npx vercel --version
6. NO mocks ni FakeRepos — la PWA tiene que apuntar al API real
   en https://api.fragloesja.uk

MI MISIÓN:
Build production + deploy Vercel + configurar dominio custom
(app.fragloesja.uk). El CNAME en Cloudflare lo agrega el humano
después que Vercel le diga qué valor poner.

ENTREGABLES (en orden):

PASO 1 · Verificar env var en código (~5 min)
1. grep -rn "localhost:8000\|api.fragloesja" motoshop-app/web/lib/ motoshop-app/web/app/
2. Verificar que TODOS los fetches usan process.env.NEXT_PUBLIC_API_URL
3. Si hay hardcoded, arreglar: process.env.NEXT_PUBLIC_API_URL ?? 'https://api.fragloesja.uk'
4. Verificar motoshop-app/web/.env.example tenga:
   NEXT_PUBLIC_API_URL=https://api.fragloesja.uk
5. npm run build local → debe pasar sin errores

PASO 2 · Deploy inicial Vercel (~10 min)
1. cd motoshop-app/web
2. npx vercel login (si no estás)
3. Primera vez:
   npx vercel
   - Project name: motoshop-web
   - Directory: ./
   - Override settings? N (Next.js detect auto)
4. Vercel detecta Next.js, hace build, deploya a un URL .vercel.app

PASO 3 · Env var producción (~3 min)
1. npx vercel env add NEXT_PUBLIC_API_URL
   - Value: https://api.fragloesja.uk
   - Environments: Production, Preview, Development
2. Deploy producción: npx vercel --prod
3. Capturar URL producción (ej. motoshop-web.vercel.app)

PASO 4 · Agregar dominio custom en Vercel (~5 min)
1. npx vercel domains add app.fragloesja.uk
2. Vercel responde con UN CNAME target (típicamente cname.vercel-dns.com)
3. Capturar EXACTAMENTE el target que devuelve Vercel — el humano
   lo necesita para Cloudflare.

PASO 5 · Smoke test en .vercel.app (~5 min)
1. Abrir la URL .vercel.app en navegador
2. Login con admin/FG28
3. /alerts debe cargar
4. Si CORS bloquea: documentar el dominio exacto que hay que
   agregar a CORS_ORIGINS. Avisar al Runtime Dev Windows.
5. Documentar smoke test en motoshop-app/web/_runs/v_vercel_smoke_<ts>.md

PASO 6 · Documentación (~5 min)
1. motoshop-app/web/_runs/v_vercel_deploy_<ts>.md con:
   - URL .vercel.app producción
   - CNAME target a configurar en Cloudflare (paste para el humano)
   - Env vars configuradas
   - Resultado smoke test
   - Si CORS bloqueó (dominio a agregar)
2. Actualizar README.md y docs/contexto-proyecto.md mencionando
   que la URL final será app.fragloesja.uk una vez DNS configurado.

Commits con prefijo: feat(F6-C-pwa-deploy): ...

NO TOCO:
- motoshop-app/api/** (Runtime Dev maneja CORS)
- infra/** (Runtime Dev)
- DNS Cloudflare (humano)

ARRANQUE:
Paso 1 (verificar env var). NO empieces deploy sin que el build
local pase. Si npm run build falla, arreglar primero.

REPORTE FINAL EN CHAT:
1. URL .vercel.app producción
2. CNAME target a poner en Cloudflare (literal)
3. Si CORS bloqueó (y qué dominio agregar a la API)
```

---

### 👤 Handoff #3 · Acción humana · Configurar CNAME en Cloudflare (~5 min)

**No se puede delegar al agente — requiere login a dash.cloudflare.com.**

Después que Dev T te reporte el CNAME target:

1. Login a https://dash.cloudflare.com
2. Seleccioná dominio `fragloesja.uk`
3. Menú `DNS` → `Records` → `Add record`
4. Configurá:
   - **Type:** `CNAME`
   - **Name:** `app` (queda como `app.fragloesja.uk`)
   - **Target:** *el valor que dio Vercel* (típicamente `cname.vercel-dns.com`)
   - **Proxy status:** **DNS only** (nube **gris**, NO naranja). Crítico — Vercel maneja TLS; si dejás proxy ON, no puede verificar.
   - **TTL:** Auto
5. Save
6. Esperar 1-5 min para propagación DNS
7. En Vercel dashboard, el dominio cambia de "Pending" a "Valid"

Después del DNS configurado:

8. Abrir `https://app.fragloesja.uk` desde celular en 4G real
9. Si carga la PWA → demo 4G es viable, grabar el video según guion DT-F6-9 (en `docs/plan-f6.md` §3)
10. Agendar demo gerencia (R8) según DT-F6-10

---

### Orden de ejecución

1. **Runtime Dev (Windows)** primero → API arriba (~30 min)
2. **Dev T (Vercel)** después → URL .vercel.app + CNAME target (~25 min)
3. **Humano** → CNAME en Cloudflare + demo 4G + demo gerencia (~15 min DNS + 30 min demo + 1 h gerencia)
4. **Avisame al revisor** cuando todo arriba → arranco E5 memoria + audit cierre = cierre proyecto

### Audit interno F6 (Sesión 46) — para tu información

| Sprint | Resultado |
|--------|-----------|
| F6-A Dev A | 🟢 todo entregado · F1=1.0 walk-forward documentado honestamente como leak (aceptable como deuda) · R7 acumula en background |
| F6-B Dev B | 🟢 hipótesis VALIDADA: Baseline-Categoría WAPE 34.37% vs Baseline-SKU 45.83% (mejora 11pp). Prophet NO supera baseline (38.59% > 32.52%). ADR-0020 Accepted. |

R4 ✅ (workflow managed), R16 ✅ (ENV guardrail), R7 🟡 acumulando con tiempo. Veredicto F6 final cuando bloqueantes operativos cierren + E5 escrita.

---

## Sesión 2026-05-30 (45) · F5 ✅ cerrada · F6 abierta — el último sprint

**Estado:** F5 cerrada por auditoría revisor fresco (9 V-F5 PASS + F5-FIX1 interna ejecutada). F6 abierta = **último sprint del proyecto académico**. 2 devs en paralelo + revisor + humano.

**Plan F6 detallado:** [docs/plan-f6.md](docs/plan-f6.md) · ~6 h wall-clock.

### Por qué F6 es especial

F0-F5 entregaron las funcionalidades técnicas. F6 hace **dos cosas en paralelo:**
1. **Hardening operativo:** cerrar deudas que ya tienen trigger cumplido (R4 workflow, R6 demo 4G, R7 7+ corridas, R8 demo gerencia, R16 ENV guardrail) + producto predictivo robusto (forecasting por categoría — la recomendación honesta de F4-FIX1).
2. **Entrega académica:** demos capturadas + E5 memoria final + repo defendible ante jurado Maestría UAO 2025-2.

**R1/R2/R15 NO se cierran** (decisión humana 2026-05-30: dejar Sashita123 + FG28 + users.yaml como están). Se documentan en E5 §3 como deudas conscientes con mitigaciones activas.

### 🤖 Handoff Dev A · Sprint F6-A · Hardening operativo (~4-5 h)

Abrí un chat Claude nuevo y pegá esto (también en `docs/plan-f6.md` §8):

```
Soy Dev A · Track A · Sprint F6-A del proyecto MotoShop.
Trabajo en paralelo con Dev B (no nos coordinamos en código,
solo evitamos conflicto en SEGUIMIENTO.md y PENDIENTES.md).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A)
4. Leé docs/plan-f6.md COMPLETO
5. Leé docs/contexto-proyecto.md §10 (deudas R4, R7, R16)
6. Leé infra/create_gold_workflow.py (setup actual)
7. Leé motoshop-app/api/src/motoshop_api/main.py (lifespan actual)

MI MISIÓN:
Hardening operativo del último sprint del proyecto. Cerrar R4
(workflow Databricks managed), R7 (7+ corridas exitosas), R16
(ENV guardrail). Implementar drift monitoring + walk-forward
classifier como mejoras predictivas. Audit log particionado.

ENTREGABLES (en orden):
1. ENV guardrail en main.py + tests/api/test_env_guardrail.py
2. infra/create_full_workflow.py (bronze→silver→gold→drift, cron 19:00)
3. Re-correr full workflow + UNPAUSE + evidencia
4. notebooks/gold/_runs/v_r7_workflow_runs_<ts>.md (≥7 runs, >95%)
5. infra/migrations/F6-001-app_audit_log_partition.sql + evidencia
6. notebooks/gold/25_drift_monitor.py + tabla gold.alertas_drift
7. infra/run_classifier_walkforward.py + reporte F1 por semana
8. docs/decisions/0021-databricks-workflow-managed.md (Proposed)

NO TOCO:
- motoshop-app/web/** (no aplica F6-A)
- notebooks/silver/** (estables)
- users.yaml (R15 diferida sigue)
- infra/start_api.ps1, start_tunnel.ps1 (operativos)

Commits con prefijo: feat(F6-A-hardening): ...

ARRANQUE:
Paso A1 (ENV guardrail). Es lo más rápido y desbloquea cualquier
deploy a Windows con confianza. Después A2 (workflow migration)
que es lo más largo.
```

### 🤖 Handoff Dev B · Sprint F6-B · Forecasting categoría/familia (~3-4 h)

Abrí otro chat Claude nuevo y pegá esto:

```
Soy Dev B · Track A · Sprint F6-B del proyecto MotoShop.
Trabajo en paralelo con Dev A. Soy un dev nuevo en este sprint
para trabajo analítico mientras Dev A hace hardening operativo.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A · subteam analítico)
4. Leé docs/plan-f6.md COMPLETO (especial §3 DT-F6-3, DT-F6-4)
5. Leé docs/lecciones-aprendidas-f4.md (por qué F4 no funcionó)
6. Leé docs/decisions/0017-split-temporal-metricas-intermitentes.md
7. Leé notebooks/gold/19_feature_store.py (feature store)
8. Leé notebooks/silver/01_dim_producto.py (campos categoría/familia)

MI MISIÓN:
Validar la hipótesis académica de F4-FIX1: forecasting agregado
por categoría/familia supera al baseline por SKU individual.
Implementar notebook + evaluación honesta + ADR-0020.

ENTREGABLES (en orden):
1. notebooks/gold/_runs/v_categoria_schema_<ts>.md con mapping SKU→categoría
2. notebooks/gold/24_forecast_categoria.py (baseline+Prophet sobre agregado)
3. Tabla gold.forecast_categoria poblada
4. notebooks/gold/_runs/v_forecast_categoria_eval_<ts>.md con WAPE
   comparativa (vs Baseline-SKU 45.83% de F4-FIX1)
5. docs/decisions/0020-forecasting-agregado.md (Proposed → Accepted
   si hipótesis se valida)
6. docs/lecciones-aprendidas-f6.md (resumen findings)
7. tests/gold/test_forecast_categoria.py (sqlparse)

NO TOCO:
- motoshop-app/** (Dev A o no aplica)
- infra/** (Dev A)
- notebooks/bronze|silver/** (estables)
- users.yaml (R15 diferida)

HONESTIDAD ACADÉMICA:
Si la hipótesis NO se valida (Prophet-categoría no supera
Baseline-SKU), DOCUMÉNTALO igual que F4-FIX1 hizo. Es descubrimiento
técnico válido, no fracaso. La conclusión real sirve para defensa.

Commits con prefijo: feat(F6-B-analytics): ...

ARRANQUE:
Paso B1 (esquema de agregación). NO empieces el notebook sin tener
claro qué nivel usás (línea/categoría/familia) — afecta todo.
```

### 👤 Acciones humanas · Sprint F6-C (~2 h)

**Paso C1 · Demo 4G (~30 min) — celular con red 4G real:**

1. Abrir https://api.fragloesja.uk en celular
2. Login como `vendedor` → búsqueda "aceite" → ver SKU + stock
3. Logout + login como `admin` → ver dashboards (`/ventas`, `/abc`, `/dormidos`)
4. Ver `/forecast` (notar StaleDataBanner si aplica)
5. Ver `/alerts` → "Gestionar" → marcar `ordered` con cantidad
6. Ver `/acciones` → confirmar la acción nueva

Grabar video (~5 min). Subir a `motoshop-app/web/_runs/v_hito_demo_4g.mp4` (o link Drive si > 50 MB). Crear `v_hito_demo_4g.md` con red usada + modelo celular + observaciones. **Cierra R6.**

**Paso C2 · Demo gerencia (~1 h):**

Agendar 30 min con stakeholder (gerencia MotoShop o vos como dueño). Estructura: 10 min walkthrough PWA + 5 min flujo alerta→acción + 5 min dashboards + 10 min preguntas/feedback.

Capturar en `notebooks/gold/_runs/v5_stakeholder_demo.md` con: asistentes + 3 funcionó + 3 mejorar + 1 feature solicitada. **Cierra R8.**

**Paso C3 · Avisarme al revisor:**

Cuando C1 + C2 estén hechos, me avisás. Yo escribo la **E5 memoria final** (~30-50 págs siguiendo plantilla DT-F6-8) + cleanup repo + audit final + veredicto cierre F6 = **cierre del proyecto académico**.

### Próximo paso del revisor (Sesión 46)

Cuando todos los push estén arriba (Dev A + Dev B + humano notifica C1/C2):
1. Aplicar 9 checks de INICIAR_REVIEWER.md.
2. Verificar 12 V-F6.
3. Escribir E5-memoria-final.md (~30-50 págs).
4. Cleanup final repo + README público actualizado.
5. Si TODAS PASS → cierre F6 = **cierre del proyecto MotoShop**. 7/7 fases ✅.
6. Si alguna FAIL → F6-FIX1 corto (estamos contra calendario académico).

---

## Sesión 2026-05-30 (44) · F5 abierta · Operación bidireccional

**Estado:** F4 ✅ cerrada (FIX1 incluido). F5 con planificación detallada lista. 2 devs en paralelo + revisor.

**Plan detallado:** [docs/plan-f5.md](docs/plan-f5.md) · **ADR-0018 Proposed:** [docs/decisions/0018-stack-f5.md](docs/decisions/0018-stack-f5.md).

### Por qué F5 ahora

F4-FIX1 dejó las predicciones y alertas operativas en la PWA pero el operador NO puede actuar desde móvil — vuelve al PC con sgHermes. F5 cierra el loop: **alerta → acción → registro persistido** sin tocar sgHermes (escribe a tablas `app_*` InnoDB nuevas).

### Scope mínimo viable (acotado a propósito)

- 1 acción de negocio: gestionar alerta de quiebre (`ordered`/`dismissed`/`postponed`)
- 2 tablas nuevas: `app_alert_actions` + `app_audit_log` (InnoDB)
- RBAC: admin/gerente write, vendedor read
- Idempotency-key obligatorio
- Offline queue PWA con retry exponencial
- R14 cleanup (archivar Prophet/LightGBM)

Otras acciones (notas venta, follow-up clientes, ajustes inventario) → F6/F7.

### 🤖 Handoff Dev A · Sprint F5-A · Backend + R14 (~3-4 h)

Abrí un chat Claude nuevo y pegá esto (también está en `docs/plan-f5.md` §7):

```
Soy Dev A · Track A · Sprint F5-A del proyecto MotoShop.
Trabajo en paralelo con Dev T (no nos coordinamos en código,
solo evitamos conflicto en SEGUIMIENTO.md y PENDIENTES.md).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A)
4. Leé docs/plan-f5.md COMPLETO
5. Leé motoshop-app/api/src/motoshop_api/auth/deps.py (patrón JWT actual)
6. Leé motoshop-app/api/src/motoshop_api/alerts/router.py (contrato actual)
7. Verificá versión MySQL: mysql --version (debería ser 5.0)

MI MISIÓN:
Primer canal de escritura PWA → MySQL con tablas app_* en InnoDB.
Acción única: gestionar alerta (ordered/dismissed/postponed) con
idempotency + RBAC + audit log. Adicionalmente: R14 cleanup
(archivar Prophet/LightGBM).

ENTREGABLES (en orden):
1. infra/migrations/F5-001-app_alert_actions.sql (InnoDB, idempotency_key UNIQUE)
2. infra/migrations/F5-002-app_audit_log.sql
3. infra/migrations/F5-003-grant_app_writer.sql (MySQL user nuevo)
4. infra/migrations/_runs/migration_f5_<ts>.md (evidencia)
5. motoshop-app/api/src/motoshop_api/app_writes/* (models, repo, router, schemas)
6. require_role(*roles) en auth/deps.py
7. AuditMiddleware en logging.py o audit_middleware.py
8. Tests: tests/api/test_alert_actions.py (8+ casos) + tests/integration/
9. R14: git mv infra/run_forecast_*.py + notebooks/gold/2{0,1}_*
   a docs/archive/
10. docs/archive/infra/README.md explicando R14
11. Re-correr motoshop_gold_workflow y confirmar skip Prophet/LightGBM

NO TOCO:
- motoshop-app/web/** (Dev T)
- notebooks/bronze|silver/** (estables)
- Tablas sgHermes (ADR-0002)
- users.yaml (R15 diferida)

Commits con prefijo: feat(F5-A-backend): ...

ARRANQUE:
Paso A1 (Migration scripts). Verificá compatibilidad MySQL 5.0
con DECIMAL, ENUM, JSON antes de tirar schema. Adaptá si falla.
```

### 🤖 Handoff Dev T · Sprint F5-B · Frontend + Offline queue (~3-4 h)

Abrí otro chat Claude nuevo y pegá esto:

```
Soy Dev T · Track T · Sprint F5-B del proyecto MotoShop.
Trabajo en paralelo con Dev A (no nos coordinamos en código).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track T)
4. Leé docs/plan-f5.md COMPLETO (especial §3 DT-F5-5, DT-F5-10)
5. Leé motoshop-app/web/app/(authenticated)/alerts/page.tsx
6. Leé motoshop-app/web/lib/* (patrón actual)
7. Leé motoshop-app/web/components/StaleDataBanner.tsx (patrón flotante)

MI MISIÓN:
UI para gestionar alertas desde PWA: botón "Gestionar" en lista,
modal con 3 tabs (Pedir/Descartar/Posponer), offline queue,
página "Mis acciones del día". RBAC: vendedor NO ve botón.

ENTREGABLES (en orden):
1. motoshop-app/web/components/AlertActionModal.tsx (3 tabs, validación)
2. motoshop-app/web/lib/offlineQueue.ts (idb-keyval + retry 1s→6h
   con cap 6 intentos)
3. motoshop-app/web/components/OfflineQueueBadge.tsx
4. motoshop-app/web/app/(authenticated)/acciones/page.tsx
5. Modificar alerts/page.tsx para botón "Gestionar" solo si
   user.role in ['admin', 'gerente']
6. motoshop-app/web/tests/alert-action.spec.ts (5+ casos E2E)
7. motoshop-app/web/_runs/v_f5_e2e_<ts>.md con screenshots + log

NO TOCO:
- motoshop-app/api/** (Dev A)
- infra/** (Dev A)
- notebooks/** (Dev A)

DEPENDENCIA con Dev A:
El endpoint POST /alerts/{id}/action lo crea Dev A en F5-A.
Mientras Dev A trabaja, podés:
1. Hacer UI con mock local (fetch que devuelva 201 simulado)
2. Integrar cuando Dev A push el endpoint

Commits con prefijo: feat(F5-B-frontend): ...

ARRANQUE:
Paso B1 (botón Gestionar en alerts/page.tsx). Antes de tocar
offlineQueue, asegurate que el modal funciona en happy path.
```

### 🔴 REGLA DE PRODUCCIÓN — Windows es el PC de producción

⚠️ **LA PC WINDOWS ES EL SERVIDOR DE PRODUCCIÓN.** Todo lo que toque motoshop-app/api corre acá.

**Stack productivo en Windows:**
| Componente | Cómo arranca |
|---|---|
| MySQL 5.0 | Servicio Windows (`services.msc` → MySQL) |
| API (uvicorn) | `infra\start_api.ps1` — vía `Start-Process -WindowStyle Hidden`, reinicio automático desde `MotoShop_HealthCheck` (cada ~5 min via Scheduled Task) |
| Túnel Cloudflare | `infra\start_tunnel.ps1` — cloudflared→ `https://api.fragloesja.uk` |
| Health Check | Scheduled Task `\MotoShop_HealthCheck` → `check_health_wrapper.vbs` → `check_health.ps1` (auto-reinicia API si caída) |

**Dev A ejecutó en Mac las migrations y el código. En Windows hay que APLICARLO manualmente.**

**✅ Aplicado en esta sesión (2026-05-30):**
1. `.env` actualizado con `MYSQL_APP_WRITER_PASSWORD=<APP_WRITER_PASSWORD>`
2. `infra\start_api.ps1` actualizado con `$env:MYSQL_APP_WRITER_USER` y `$env:MYSQL_APP_WRITER_PASSWORD`
3. Migraciones SQL ejecutadas: F5-001 (app_alert_actions), F5-002 (app_audit_log), F5-003 (user app_writer)
4. `app_writer` verificado: conecta y ve ambas tablas

**✅ Aplicado en esta misma sesión (Windows):**
5. API reiniciada post-fix (PID 13608 → nueva instancia con `ENV=dev`)
6. `ENV=test` → `ENV=dev` corregido (antes usaba FakeAlertActionsRepo, no escribía a MySQL)
7. Test end-to-end verificado: POST 201 + idempotency 200 + datos en MySQL + audit log
8. Túnel revivido (`cloudflared` PID 12792), ruta corregida en `start_tunnel.ps1`
9. 36 notebooks subidos a Databricks Workspace
10. Workflow `motoshop_full_workflow` UNPAUSED schedule 19:00 COL
11. F6-001 documentado como no aplicable (MySQL 5.0 sin partitioning)
12. `CORS_ORIGINS` actualizado con Vercel + `app.fragloesja.uk`

**Regla para el revisor:** cuando audites F5, acordate que Windows = producción. Verificar que `start_api.ps1` y `.env` tengan las env vars de `app_writer`, y que las migrations se aplicaron en MySQL local (no solo en el repo).

### Próximo paso del revisor (Sesión 45)

Cuando ambos devs pongan push final:
1. Aplicar 9 checks de INICIAR_REVIEWER.md.
2. Verificar 9 V-F5.
3. **Check de producción (Windows):** verificar que el `.env` y `start_api.ps1` en Windows tengan `MYSQL_APP_WRITER_PASSWORD`, y que las migrations F5-001/002/003 estén aplicadas en MySQL local.
4. Especial atención a Check 4 (nuevo MySQL user `app_writer` sin password en código) y Check 9 (Real vs Fake en `app_writes/router.py`).
5. Si TODAS PASS → cerrar F5 verde + planificar F6 hardening.
6. Si alguna FAIL → F5-FIX1.

---

## Sesión 2026-05-30 (43) · F4-FIX1 Dev A completado · Pendiente Dev T + Revisor

**Estado:** F4-B/F4-C revierten a 🟡 hasta cerrar F4-FIX1. Dev A ✅ completado. Dev T 🟡 y Revisor 🟡 pendientes.

### Dev A · Sprint F4-FIX1-A ✅ Completado

**Commit:** `81d6bd5` — `fix(f4): corregir métricas forecasting y data leakage en classifier`

**Resultados clave:**

| Bloqueante | Hallazgo | Fix | Métrica antes → después |
|------------|----------|-----|------------------------|
| B1 · Prophet MAPE | MAPE 3540% por demanda intermitente + SKUs < 30 ventas | WAPE primaria + filtro SKU elegibles (>=90d + >=30 ventas) | MAPE 3540% → WAPE 864% (realista, sigue siendo malo) |
| B2 · Classifier F1 | Target leakage: `stock_actual` era feature y estaba en la fórmula del target | Sacar `stock_actual` de features + split temporal | F1 0.99 → F1 0.54 (honesto) |
| O5 · Sin ADR | No existía ADR de split temporal | ADR-0017 creado | — |

**Entregables:**
1. ✅ Diagnóstico Prophet con query real Databricks: `v_fix1_prophet_diagnostico_*.md`
2. ✅ Fix `run_evaluate_models.py`: WAPE primaria, filtro SKU, cobertura
3. ✅ Nueva evaluación: `v_model_evaluation_20260530_113116.md`
4. ✅ Classifier audit + fix: `v_classifier_stockout_20260530_113711.md`
5. ✅ ADR-0017: `docs/decisions/0017-split-temporal-metricas-intermitentes.md`
6. ✅ Lecciones: `docs/lecciones-aprendidas-f4.md`

**Métrica final post-fix:**
- Prophet WAPE 864% (inservible, gana 1.8%)
- LightGBM WAPE 57% (borderline, gana 0.3%)
- Baseline WAPE 45.83% (gana 97.9%)
- Classifier F1 0.536 (honesto)
- SKUs elegibles: 31/4392 (0.7%)

### ⬜ Próximo paso · Revisor

Auditar cambios Dev A, verificar V-FIX1-1 a V-FIX1-4. Cuando Dev T también termine, cerrar F4-FIX1.

---

## ~~Sesión 2026-05-30 (42) · F4-FIX1 abierta tras auditoría revisor fresco~~ *(histórico — reemplazado por Sesión 43)*

Abrí otro chat Claude nuevo y pegá esto:

```
Soy Dev T · Track T · Sprint F4-FIX1 del proyecto MotoShop.
Trabajo en paralelo con Dev A (no nos coordinamos en código).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track T)
4. Leé docs/plan-f4-fix1.md COMPLETO
5. Leé motoshop-app/api/src/motoshop_api/forecast/* y alerts/*
6. Leé motoshop-app/api/src/motoshop_api/health/router.py
   (contrato /health/data-freshness existente)

MI MISIÓN:
Reemplazar FakeForecastRepo y FakeAlertsRepo por Real en prod
(F4-C cerró con fakes — repite problema F3). Crear StaleDataBanner
para que la PWA alerte cuando los datos están viejos (R10).

ENTREGABLES (en orden):
1. RealForecastRepo en forecast/repo.py (Databricks SDK → gold.forecast_demanda_sku)
2. RealAlertsRepo en alerts/repo.py (→ gold.alertas_quiebre)
3. Dependency injection elige Real cuando env != 'test'
4. motoshop-app/web/_runs/v_fix1_forecast_real.md (top 10 SKUs SQL vs PWA match)
5. motoshop-app/web/_runs/v_fix1_alertas_real.md (69 alertas SQL vs PWA match)
6. motoshop-app/web/components/StaleDataBanner.tsx según DT-FIX1-6
7. Banner integrado en /forecasts y /alertas
8. motoshop-app/web/tests/forecasts.spec.ts con E2E del banner
9. motoshop-app/web/_runs/v_fix1_stale_banner.md (screenshot + log)

NO TOCO: infra/**, notebooks/**, credenciales.

COORDINACIÓN: solo SEGUIMIENTO.md/PENDIENTES.md en mi sección.
Commits con prefijo: fix(F4-FIX1-B-pwa): ...

ARRANQUE: Paso B1 (RealForecastRepo). Patrón de referencia en
motoshop-app/api/src/motoshop_api/metrics/repo.py (Sprint F3-B).
```

### Próximo paso del revisor (Sesión 43)

Cuando Dev A y Dev T pongan push, auditar las 8 V-FIX1. Si TODAS PASS → cerrar F4-FIX1 verde, F4-B/F4-C vuelven a ✅, planificar F5. Si alguna FAIL → F4-FIX2.

---

## Sesión 2026-05-30 (40) · F4-B cerrada ✅ · Prophet/LightGBM/Classifier completados

**Estado:** F4-B terminada. Todos los scripts corren, tablas gold pobladas, V-Checks implementados. Modelos ML (Prophet, LightGBM) no superan baseline — documentado como lección aprendida para feature engineering en fase siguiente.

### Resultados F4-B

| Componente | Resultado |
|------------|-----------|
| Prophet top-100 | ✅ 94 SKUs, 543 predicciones, holdout predictions guardadas en tabla |
| LightGBM global | ✅ 10.533 predicciones, 82 evaluaciones con match vs demanda real |
| Evaluación comparativa | ✅ Baseline gana 93.6% — Prophet 4.9%, LightGBM 1.5% |
| Classifier quiebre | ✅ 69 alertas, F1=0.9924 |
| `forecast_demanda_sku` | ✅ 4.642 filas, 4.343 SKUs |
| `alertas_quiebre` | ✅ 69 registros (urgencia alta) |
| MLflow | ✅ 3 runs (prophet, lightgbm, classifier) en `file:mlruns` |
| Evidencia | ✅ Prophet, LightGBM, Evaluation, Classifier |

### V-Checks F4-B

| ID | Criterio | Resultado | Nota |
|----|----------|-----------|------|
| V-M1 | Prophet < Baseline (43.7%) | ❌ 3.540% | Modelo no apto para demanda intermitente |
| V-M2 | LightGBM < Baseline (43.7%) | ❌ 72.76% | One-step MAPE 31.49% (no guardado en tabla) |
| V-M3 | Classifier F1 > 0.7 | ✅ 0.9924 | |
| V-M4 | forecast_demanda_sku ≥ 100 SKUs | ✅ 4.343 | |
| V-M5 | alertas_quiebre tiene registros | ✅ 69 alta | |
| V-M6 | Sanity (0 negativos, 0 nulls) | ✅ PASS | Fix: 100 predicted_qty negativos corregidos |
| V-M7 | Tests gold | ✅ 97/97 | |
| V-M8 | MLflow experiments | ✅ 3 runs | |

### Fixes aplicados durante la sesión

1. **Classifier**: `write_alerts_table(full_results, ...)` → `write_alerts_table(alerts, ...)` — insertaba TODOS los SKUs como alertas
2. **Classifier**: `INSERT OVERWRITE PARTITION VALUES` → `DELETE + INSERT INTO` (Databricks SQL Warehouse no soporta el patrón anterior)
3. **MLflow**: 3 scripts con tracking URI distinta → unificados a `file:mlruns`
4. **Prophet**: Holdout predictions ahora se guardan en tabla (antes solo se calculaba MAPE sin persistir)
5. **V-M6**: Implementado sanity check automatizado (negativos, nulls)
6. **Predicciones negativas**: `max(0.0, predicted)` en materialización

### Lecciones aprendidas — F4-B

**Sobre modelos para demanda intermitente:**
- **Prophet NO funciona** para autopartes con demanda irregular. MAPE 3.540% vs baseline 43.7%. La estacionalidad anual no aplica con < 2 años de datos y weekly_pattern es débil en ventas B2B con mucho 0.
- **LightGBM recursivo** pierde precisión exponencialmente. El one-step MAPE (31.49%) SÍ supera baseline, pero la predicción recursiva a 7/14/30 días degrada a 72.76%. Para la próxima fase: implementar direct multi-step (un modelo por horizonte).
- **Baseline naive** gana 93.6% de los SKUs porque la mejor predicción para demanda intermitente es el promedio histórico. No es un fracaso de los modelos ML — es que los features actuales (lags, medias móviles) no agregan señal sobre la media histórica.

**Sobre el pipeline:**
- Databricks SQL Warehouse (serverless) no soporta `INSERT OVERWRITE PARTITION VALUES`. Workaround: `DELETE FROM + INSERT INTO`.
- MODELS de Prophet exportan `yhat` que puede ser negativo para demanda baja. Forzar `max(0, predicted_qty)`.
- MLflow remote tracking vía `set_tracking_uri("databricks")` no funciona desde Mac sin Databricks Runtime. Usar `file:mlruns` local.
- El `wait_timeout` máximo de Databricks SQL Warehouse es 50s, no 60s.

**Para la próxima fase (F5):**
1. Feature engineering: incorporar features externos (estacionalidad, promociones, precio) para que los modelos ML agreguen valor sobre baseline
2. Direct multi-step: un modelo por horizonte en vez de recursivo
3. Evaluación con WAPE como métrica principal (no infla errores en demanda baja)
4. Considerar si Prophet tiene sentido en fases futuras o si se descarta definitivamente

### Pendientes para Javier

- ✅ Aprobar plan F4-B v2 (`docs/plan-f4-b.md`)
- ✅ Ejecutar `pip install prophet lightgbm` en la Mac
- ✅ Confirmar label sintético del classifier
- ⬜ Revisar feature engineering para F5: ¿qué features externos están disponibles? (promociones, precio, días de entrega proveedor)
- ⬜ Decidir si Prophet se descarta o se re-intenta con más datos en F6
- ⬜ Planificar F5: unified training dataset + direct multi-step
- ⬜ Cerrar F4 en el sistema de tracking (gh project, etc.)

---

## Sesión 2026-05-29 (39) · F4-B arrancada · 2 devs paralelos

**Estado:** ✅ F4-B cerrada. F4-A y F4-B completados. Pendiente: F5 (feature engineering + direct multi-step).

### Evidencia F4-A

| Componente | Resultado |
|------------|-----------|
| Feature store `gold.feature_store_sku` | ✅ 34,838 filas, 4,392 SKUs |
| Baseline MAPE | 43.7% (benchmark a superar) |
| MLflow | ✅ Experimento registrado, Run ID `55071d05...` |
| `forecast_baseline_sku` | ⚠️ **Tabla vacía** — SQL syntax error en INSERT OVERWRITE |
| Tests feature store | ✅ 16/16 pasan |

### Distribución de devs

| Dev | Track | Tareas | Dependencia |
|-----|-------|--------|-------------|
| Dev A | ML | A-1: Prophet top-100, A-2: LightGBM, A-3: Evaluate | feature_store_sku |
| Dev B | Data Engineering | B-1: FIX baseline (PRIORITARIO), B-2/B-3: DDLs, B-4: Classifier, B-5: Tests | B-1 primero |

### Pendientes para Javier

- ✅ Aprobar plan F4-B v2
- ✅ `pip install prophet lightgbm`
- ✅ Label sintético del classifier OK (F1=0.99)
- ⬜ Verificar que Windows PC tenga `.env` con DATABRICKS_HOST/TOKEN actualizados

---

## Sesión 2026-05-29 (36) · F3.5 ejecutada — Hardening Silver completado ✅

**Estado:** F3.5 terminada. Silver, Gold y V6 corregidos y verificados con universo completo. Libre para planificar F4.

### Resumen de ejecución

| Componente | Resultado |
|------------|-----------|
| Fix `estfven='A'` → `IN('A','B')` en 10/12 | ✅ Aplicado |
| Fix sentinel -1→99999 en 14_mart_productos_dormidos | ✅ Aplicado |
| Regla `silver_completeness` en 20_quality_run | ✅ Agregada |
| Reconciliación V3 (universo completo) | ✅ Rediseñada |
| Silver 56/56 statements | ✅ 6,339 facturas, 27,771 detalles |
| Gold 52/52 statements, 0 CRITICAL | ✅ 5 marts con datos reales |
| V6 reconfirmado post-F3.5 | ✅ 5/5 KPIs match |
| Evidencia _runs/ actualizada | ✅ 3 archivos |

### Causa raíz confirmada

Filtros `estfven = 'A'` y `estcom = 'A'` al revés. Distribución real en Bronze:
- `facventas.estfven`: 'B' = 6,325 (99.76%), 'A' = 15 (0.24%)
- `facompras.estcom`: 'B' = 746 (97.9%), 'A' = 16 (2.1%)

Fix cambia ambos a `IN ('A', 'B')`. Diferencia residual aceptada: 1 fila con fecha nula/fuera de rango.

### Volumen real post-fix

- 6,339 facturas de venta en 17 meses → ~373 facturas/mes, $23.5M/mes
- 8,039 productos dormidos (vs 50 en el run trivial)
- 198 cohortes de clientes (vs 9 en el run trivial)
- Materialmente ≠ al dataset sub-100 filas con que F3 cerró

### Verificación

- `silver.fact_ventas ≈ bronze.facventas` (6,339 vs 6,340, diff=1 documentada)
- Gold marts con órdenes de magnitud reales
- V6 PASS: 5/5 KPIs coinciden entre PWA y Databricks SQL

### GO a F4

**F3.5 cerrada con éxito.** Track A libre para planificar F4 con volumen histórico real confirmado.

### Pendientes para Javier

- ⬜ Revisar resumen de F3.5 en `SEGUIMIENTO.md` §Sesión 36.
- ⬜ Decidir si retomar F4 (ML predictivo) ahora o después de commit+PR.
- ⬜ Commit + push (incluye fixes, evidencia _runs/, V6 actualizado).

---

## Sesión 2026-05-29 (35) · F3.5 abierta · 🔴 F4 pausada por bug de universo Silver · ✅ CERRADA

**Estado:** se detectó un hallazgo crítico post-F3: Bronze contiene histórico real suficiente para F4, pero Silver estaba conservando solo una fracción mínima de ventas. **F4 queda pausada** hasta cerrar F3.5. **F3.5 ejecutada y cerrada en Sesión 36.**

### Evidencia que gatilla F3.5

| Capa | Tabla | Filas | Evidencia |
|------|-------|------:|-----------|
| Bronze | `facventas` | 6,340 | `notebooks/bronze/_runs/business_date_survey_2026-05-29.md` |
| Bronze | `detfventas` | 27,775 | `notebooks/bronze/_runs/business_date_survey_2026-05-29.md` |
| Bronze | `auxinventario` | 26,174 | `notebooks/bronze/_runs/business_date_survey_2026-05-29.md` |
| Silver | `fact_ventas` | 15 | `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md` |
| Silver | `fact_ventas_detalle` | 58 | `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md` |
| Silver | `fact_inventario` | 26,174 | `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md` |

**Lectura:** inventario conserva el universo completo, pero ventas y detalle colapsan. La hipótesis principal es un bug/filtro no documentado en `notebooks/silver/10_fact_ventas.py` y/o `notebooks/silver/11_fact_ventas_detalle.py`.

### Handoff para Dev A · F3.5 · Hardening Silver

Pegá esto en un chat nuevo de Dev A:

```md
Soy Dev A · Track A para F3.5 Hardening Silver del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé `PENDIENTES.md` §Sesión 35 y `SEGUIMIENTO.md` §Fase 3.5.
4. Leé evidencia:
   - `notebooks/bronze/_runs/business_date_survey_2026-05-29.md`
   - `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md`
5. Leé notebooks afectados:
   - `notebooks/silver/10_fact_ventas.py`
   - `notebooks/silver/11_fact_ventas_detalle.py`
   - `notebooks/silver/31_reconciliation.py`

OBJETIVO:
Corregir Silver para que `fact_ventas` y `fact_ventas_detalle` representen el universo real de Bronze, salvo filtros de negocio legítimos y documentados.

TAREAS:
1. Auditar filtros actuales de `10_fact_ventas.py`:
   - `estfven`
   - fechas inválidas/futuras
   - `fecfven`
   - cualquier cast que descarte filas silenciosamente.
2. Definir y documentar el universo válido de ventas:
   - ejemplo: `facventas WHERE estfven IN (...) AND fecfven IS NOT NULL AND fecha válida`.
   - No asumir que `estfven = 'A'` alcanza sin verificar distribución real por estado.
3. Corregir `10_fact_ventas.py` para cargar todas las facturas válidas.
4. Corregir `11_fact_ventas_detalle.py` para que el detalle cuadre contra las cabeceras válidas.
5. Reescribir `31_reconciliation.py` para validar universo completo, no solo "último mes con datos".
6. Agregar evidencia nueva en `notebooks/silver/_runs/`:
   - conteo Bronze esperado vs Silver real;
   - conteo detalle Bronze esperado vs Silver real;
   - diferencias por estado/fecha con explicación;
   - total monetario Bronze vs Silver;
   - top SKUs y clientes sobre universo corregido.
7. Ejecutar de nuevo Silver completo y tests Silver.
8. Re-ejecutar Gold completo sobre Silver corregido:
   - `notebooks/gold/10..14_*`
   - `notebooks/gold/20_quality_gold.py`
   - `notebooks/gold/30_validate_gold.py`
9. Revalidar V6 PWA↔Databricks SQL con datos corregidos.
10. Actualizar `SEGUIMIENTO.md` con resultados, conteos y veredicto GO/NO-GO a F4.

VERIFICACIÓN OBLIGATORIA:
- `COUNT(silver.fact_ventas)` debe aproximar `COUNT(bronze.facventas WHERE filtros_documentados)`.
- `COUNT(silver.fact_ventas_detalle)` debe aproximar `COUNT(bronze.detfventas JOIN cabeceras_validas)`.
- Toda diferencia debe estar explicada por estado, fecha inválida, llave huérfana o regla de negocio documentada.
- F3.5 NO cierra si la reconciliación solo compara un subset temporal pequeño.

FUERA DE SCOPE:
- No diseñar F4.
- No entrenar Prophet/LightGBM.
- No cambiar PWA salvo que V6 demuestre contrato roto.
- No tocar archivos de credenciales ni `.env`.

ENTREGA:
- Commit con prefijo `fix(F3.5-silver): ...`.
- Evidencia nueva versionada en `_runs/`.
- Resumen final con: causa raíz, conteos antes/después, filtros documentados, impacto sobre Gold y V6.
```

### Checklist F3.5 para el revisor

- ✅ **Confirmar causa raíz del colapso `6340 → 15` y `27775 → 58`.** → Causa raíz: filtros `estfven = 'A'` / `estcom = 'A'` al revés. El 99.76% de `facventas` tiene `estfven = 'B'`, el valor minoritario es `'A'`.
- ✅ **Revisar que los filtros de negocio queden explícitos y justificados.** → Fix: `estfven IN ('A', 'B')` y `estcom IN ('A', 'B')`. La diferencia residual de 1 fila es por fecha nula/fuera de rango.
- ✅ **Revisar que V3 Silver ya valide universo completo, no último mes trivial.** → `31_reconciliation.py` rediseñado para universo completo (ventas, compras, año-mes, top SKU, top clientes).
- ✅ **Revisar nueva evidencia Silver `_runs`.** → `run_silver_fix_20260529_211852.md` (56/56 OK, 6,339 facturas).
- ✅ **Revisar nueva evidencia Gold `_runs` post-fix.** → `gold_20260529_212128.md` (52/52, 0 CRITICAL).
- ✅ **Revisar V6 PWA↔Databricks SQL post-fix.** → 5/5 KPIs match, valores materialmente ≠ al run trivial.
- ✅ **Emitir nuevo veredicto: GO/NO-GO a F4.** → **GO a F4 con volumen real.**

### Decisión de planificación

- F3.5 ✅ **cerrada.** F4 puede retomarse con ~17 meses de ventas y miles de facturas.
- `docs/plan-f4.md` y `docs/decisions/0016-stack-f4.md` listos para redactar con volumen real confirmado.

---

## Sesión 2026-05-29 (34) · F3 cerrada · 🟢 GO a F4 con deudas diferidas a F6

**Estado:** F3 ✅ aprobada por el revisor en ese momento. **Superseded por Sesión 35:** F4 queda pausada hasta cerrar F3.5 por el hallazgo de universo Silver incompleto.

### Acciones humanas pendientes (post-F3, antes/durante F4)

- ⬜ **R6 (demo 4G)** — diferida a F6 hardening. Cuando se acerque E3/E5: grabar video 5 min navegando login → búsqueda → ficha SKU → dashboards desde celular en 4G real. Subir a `motoshop-app/web/_runs/v_hito_demo_4g.md`.
- ⬜ **R7 (V3 workflow 7 corridas)** — cierra sola en background. Schedule UNPAUSED en cron `0 30 2 * * ?` (02:30 COL). Acción humana: revisar tasa de éxito en F6 (`system.workflows.runs`). Si falla 3 noches seguidas → alerta inmediata.
- ⬜ **R8 (demo gerencia)** — diferida a F6. Agendar 30 min con stakeholder (gerencia o vos mismo como dueño del negocio); capturar feedback en template `notebooks/gold/_runs/v5_stakeholder_demo.md`.
- ⬜ **Revisar próxima madrugada (mañana 02:30 COL)** que el workflow gold corrió exitoso. Si la pestaña `Workflows > motoshop_gold_workflow > Run history` no muestra una corrida ✅, debug.

### Próximo paso del revisor (superseded por F3.5)

1. ~~Escribir `docs/plan-f4.md` (3 sprints ML):~~
   - F4-A: baseline naïve por SKU + métricas (MAPE, sMAPE, WAPE) + sandbox MLflow
   - F4-B: Prophet top-100 + LightGBM cola larga + clasificador quiebre con horizon 7/14/30 días
   - F4-C: endpoints `/predict/*` + dashboards predictivos en PWA + alertas web-push (recién aquí se activa `push/router.py`)
2. ~~Escribir `docs/decisions/0016-stack-f4.md` con DT F4 (MLflow tracking, `prophet`, `lightgbm`, `optuna` para HPO, riesgo R-A4 docs/errores.txt sobre compute en Free Edition para train).~~
3. ~~Decidir si F4 se hace en paralelo (Dev A entrena, Dev T integra API+PWA predictivo) o secuencial.~~

**Nuevo orden:** primero cerrar F3.5, después planificar F4 con el volumen real corregido.

### Notas de la decisión humana

- "demos el go dejando eso en detalle, aplazalo a la fase final eso, de pronto a esa fecha ya estén algunos días de registros" — apoya el racional de diferir R6/R7/R8 a F6 cuando ya haya datos reales y la demo sea más representativa.

---

## Sesión 2026-05-29 (33) · ADR-0015 Accepted · F3 arranca en paralelo

ADR-0015 aprobado · D14 a fecha · **P5 resuelta** (Databricks SQL).

**Modo: paralelo · 2 devs en el Mac.** Pegá los prompts de abajo en 2 chats Claude nuevos.

---

### 🤖 Handoff para Dev A · Track A · Sprint F3-A

Abrí un chat Claude nuevo (no este) y pegá esto:

```
Soy Dev A · Track A para la Fase 3 del proyecto MotoShop.

PRE-FLIGHT obligatorio antes de tocar nada:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (identificá mi rol = Dev Agent · Track A)
4. Leé docs/plan-f3.md §4 (Sprint F3-A · Gold + Workflow + Dashboard SQL)
5. Leé docs/decisions/0015-stack-f3.md (decisiones técnicas que rigen F3)
6. Leé SEGUIMIENTO.md cabecera + última nota de sesión

MI TRABAJO:
- 14 archivos a crear/modificar en notebooks/gold/, tests/gold/, infra/, docs/gold/
- 5 marts gold (mart_ventas_diarias_sku, mart_inventario_actual, 
  mart_rotacion_abc, mart_cohortes_clientes, mart_productos_dormidos)
- Workflow Databricks Job nocturno 02:30 COL
- Dashboard ejecutivo en Databricks SQL UI (exportar JSON)
- V1 (KPIs cuadran <0.5%), V2 (ABC estable mes a mes), V3 (workflow puntual),
  V7 (plan refresco) con evidencia en notebooks/gold/_runs/

LO QUE NO TOCO:
- motoshop-app/web/** (Dev T)
- motoshop-app/api/src/motoshop_api/metrics/** (Dev T)
- Archivos de credenciales, users.yaml, .env
- README API con FG28 (deuda R2 aceptada)

COORDINACIÓN CON DEV T:
- Cada uno actualiza solo SU sección en SEGUIMIENTO.md y PENDIENTES.md
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: feat(F3-A-gold): ...
- Acordamos el contrato JSON de los endpoints /metrics/* (Dev T los implementa
  consumiendo mis marts; los schemas Pydantic están en docs/plan-f3.md §5.2)

ARRANQUE:
Empezá por crear los 5 marts (notebooks/gold/10..14) siguiendo el patrón
canónico de docs/plan-f3.md §4.3 paso 1. Cuando termines cada notebook,
ejecutalo en Databricks SQL Warehouse y verificá conteos. Push después
de cada pieza estable.

Al terminar el sprint completo: ping al revisor en el chat principal con
hash del último commit y archivos en _runs/.
```

---

### 🤖 Handoff para Dev T · Track T · Sprint F3-B

Abrí OTRO chat Claude (un tercero) y pegá esto:

```
Soy Dev T · Track T para la Fase 3 del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (identificá mi rol = Dev Agent · Track T)
4. Leé docs/plan-f3.md §5 (Sprint F3-B · API endpoints + PWA Dashboards)
5. Leé docs/decisions/0015-stack-f3.md (decisiones técnicas)
6. Leé SEGUIMIENTO.md cabecera + última nota de sesión

MI TRABAJO:
- 5 endpoints en motoshop-app/api/src/motoshop_api/metrics/
  (/metrics/sales-summary, /metrics/inventory-summary, /metrics/abc-segmentation,
   /metrics/dormidos, /metrics/cohortes)
- Conexión a Databricks SQL Warehouse vía databricks-sql-connector
- Sección Dashboards mobile-first en PWA (motoshop-app/web/app/(authenticated)/dashboards/)
- 5 hooks SWR + 5 componentes chart (recharts ~12KB)
- Estructura push notifications (web-push, prepara solo, NO dispara)
- V4 dashboard < 5s con evidencia en motoshop-app/web/_runs/v4_dashboard_load.json
- Tests Playwright para navegación dashboards

LO QUE NO TOCO:
- notebooks/gold/** ni notebooks/silver/** (Dev A)
- Archivos de credenciales, users.yaml, .env
- README API con FG28 (deuda R2 aceptada)

COORDINACIÓN CON DEV A:
- Cada uno actualiza solo SU sección en SEGUIMIENTO.md y PENDIENTES.md  
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: feat(F3-B-pwa): ...
- Mientras Dev A construye los marts, podés MOCKEAR los datos de las
  queries Databricks para avanzar con la PWA (devolver JSON fake desde
  el API). Cuando Dev A pushee marts reales, swap a queries reales.

ARRANQUE:
Empezá por:
1. Instalar deps: cd motoshop-app/api && pip install -e ".[dev]" databricks-sql-connector
2. Instalar deps PWA: cd motoshop-app/web && npm install recharts
3. Crear módulo metrics en API con FakeMetricsRepo + schemas Pydantic (~30 min)
4. Crear app/(authenticated)/dashboards/page.tsx landing con cards (~1.5 h)

NOTA SOBRE EL API:
Como editás motoshop-app/api/src/motoshop_api/metrics/, hay que hacer pull+restart
en la PC Windows después de pushear endpoints (cuando estén estables). Avisame
cuando estés listo y coordinamos el restart.

Al terminar el sprint: ping al revisor con hash + evidencia v4_dashboard_load.json
```

---

### Lo que pasa después

Cuando ambos devs reporten "Sprint terminado":
1. Yo (revisor) audito cada track por separado (~30 min cada uno).
2. Si ambos PASS → arrancamos **Sprint F3-C** (validación cruzada + demo a gerencia + R6 bonus).
3. F3-C necesita ~3-4 h con ambos devs + vos para la demo final.
4. Cuando F3-C cierre → **GO a F4 · Predictivo (ML)**.

### Acción heredada (no bloqueante)

#### ⬜ R6 · Demo 4G

Buena oportunidad: cuando Dev T termine F3-B, la PWA tendrá login + búsqueda + ficha SKU + dashboards. Grabar todo el flujo en 4G y subir a `motoshop-app/web/_runs/v_hito_demo_4g.md`. Cierra R6 + suma evidencia para E3 académico.

---

## ~~Sesión 2026-05-29 (32) · Plan F3 + ADR-0015 listos · esperando aprobación humana~~ *(histórico — ADR Accepted)*

### Resumen
F2 cerrada en Sesión 30/31. Revisor escribió plan F3 completo (3 sprints) + ADR-0015 con 12 decisiones técnicas (DT-F3-1..12) que también **resuelve P5 pendiente desde F0** (Power BI vs Databricks SQL).

**Una sola acción humana cierra el gap y arranca Sprints F3-A y F3-B en paralelo:**

---

### 🚨 Acción humana — 1 cosa

#### ⬜ Leer ADR-0015 y aprobar (o ajustar) — ~10 min

Abrir [`docs/decisions/0015-stack-f3.md`](docs/decisions/0015-stack-f3.md).

Lectura recomendada:
- **DT-F3-1** (BI tool — resuelve P5): recomendado **Databricks SQL** porque tu Mac no corre Power BI Desktop. Si en el futuro gerencia pide Power BI específicamente, se suma en F6.
- **DT-F3-8** ("producto dormido"): umbral 90 días — ajustable si tu negocio piensa distinto.
- **DT-F3-11** (push notifications): se prepara la estructura pero NO se dispara hasta F4 alertas.

12 decisiones, 8 Gold + 4 PWA. Tabla resumen al final del ADR.

**Tres caminos:**
- **"OK todas + modo paralelo"** → marco ADR `Accepted`, D14 a fecha, P5 resuelta. Dev A y Dev T arrancan simultáneo.
- **"OK pero ajustar X"** → decime qué y ajusto.
- **"Necesito más contexto sobre Y"** → te detallo.

---

### Plan F3 a alto nivel *(para que sepas qué viene)*

| Sprint | Track | Duración | Cierra qué V/KPI |
|--------|-------|----------|-------------------|
| **F3-A · Gold + Workflow + Dashboard SQL** | A · Databricks | ~6-8 h | V1 KPIs cuadran, V2 ABC estable, V3 workflow puntual, V7 plan refresco |
| **F3-B · API endpoints + PWA Dashboards** | T · Next.js | ~5-6 h | V4 dashboard < 5s, soporta V6 |
| **F3-C · Demo + validación cruzada** | ambos + humano | ~3-4 h | V5 demo gerencia, V6 PWA=dashboard, captura R6 bonus |

**Modo serial (1 dev):** ~12 días.
**Modo paralelo (2 devs en tu Mac, recomendado):** ~6-8 días.

Detalle completo en [`docs/plan-f3.md`](docs/plan-f3.md).

---

### ¿F3 necesita PC Windows?

**Casi no.** Detalle en [plan-f3.md §12](docs/plan-f3.md):

| Pieza | Windows? |
|-------|----------|
| Notebooks gold | ❌ (Databricks cloud) |
| Dashboard SQL | ❌ (web) |
| PWA dashboards | ❌ (Mac) |
| Endpoints `/metrics/*` API | ❌ para editar; ⚠️ `git pull + restart-api` en Windows después de pushear (5 min vía RDP) |
| Demo gerencia | ❌ (cualquier dispositivo) |

**Único toque a Windows:** restart de la API después de los commits de Dev T. ~1 minuto. Si tenés script de auto-pull configurado, ni eso.

---

### Acción heredada · R6 (no bloqueante, oportunidad)

#### ⬜ R6 · Capturar demo 4G (~5 min)

Se quedó pendiente de F2. Buena oportunidad: cuando Dev T termine F3-B, vas a tener Dashboards en la PWA. Captura el flujo completo en celular 4G:
- Login admin/FG28
- Búsqueda "aceite"
- Ficha SKU con stock
- (Bonus) Dashboard

Subí screenshot/video a `motoshop-app/web/_runs/v_hito_demo_4g.md`. Cierra R6.

---

### Lo que pasa cuando aprobés el ADR

1. Revisor marca ADR-0015 `Accepted` con fecha. D14 a fecha. **P5 resuelta** (cierra una decisión pendiente desde F0).
2. Dev A arranca **Sprint F3-A** (gold marts + workflow + dashboard SQL).
3. Dev T arranca **Sprint F3-B** (endpoints `/metrics/*` + PWA dashboards).
4. Sesión 33 abre con el(los) primer(os) commit(s).

---

## ~~Sesión 2026-05-29 (31) · F2 cerrada · 🟢 GO a F3~~ *(histórico — cerrada)*

✅ Revisor auditó F2-FIX1 (commits `53f888c`..`df632c4`) en Sesión 30. Veredicto: **GO a F3 · Gold + Dashboards.**

Track A Silver:
- V1 11/11 tablas sin duplicados
- V2 0 fechas nulas/futuras + caso sintético
- V3 reconciliación 0.0%
- 19 + 15 tests passing

Track T PWA:
- V4 offline (Playwright)
- V5 sesión persiste
- V6 búsqueda p95=45 ms
- V7 roles validados
- V8 5/5 SKUs con diff 0%

### Acción humana opcional (no bloquea F3)

#### ⬜ R6 · Capturar hito demo 4G (~5 min)

Plan F2 §6.3 paso 5 pedía: "vendedor en celular real, 4G, login → búsqueda 'aceite' → ficha SKU, captura screenshot/video, total ≤ 5 s desde tap del ícono".

No bloquea F3 técnicamente, pero es importante para el entregable académico E3.

Cuando tengas 5 min con un celular:
1. Conectar a 4G (no WiFi).
2. Abrir `https://api.fragloesja.uk/demo` o la PWA si está deployada.
3. Login con `admin/FG28`.
4. Buscar "aceite".
5. Abrir un SKU.
6. Cronometrar y capturar screenshot.
7. Subir a `motoshop-app/web/_runs/v_hito_demo_4g.md`.

---

### Próximo paso · Sesión 31

Revisor escribirá `docs/plan-f3.md` + `docs/decisions/0015-stack-f3.md` con decisiones técnicas F3 (gold marts + BI tool elegida — Power BI vs Databricks SQL).

---

## ~~Sesión 2026-05-29 (30) · Entregables Dev A y Dev T completados — pendiente verificación final~~ *(histórico)*

### Resumen

Ambos devs (Track A + Track T) completaron sus entregables de F2-FIX1. Pendiente de ser verificado por un revisor externo antes del cierre de F2.

**Estado: entregado ⏳ pendiente de verificar**

### Resumen de entregables

#### Dev A · Silver Gate

| Item | Estado | Detalle |
|------|--------|---------|
| A1 · Hechos idempotentes por business_date | ✅ | `10_fact_ventas.py`–`14_fact_inventario.py` usan DELETE+INSERT |
| A2 · Dimensiones SCD1 (CREATE OR REPLACE) | ✅ | `01_dim_producto.py`–`06_dim_tiempo.py` |
| A3 · quality_run falla si CRITICAL | ✅ | `20_quality_run.py` con `assert_true` — 0 critical en ejecución real |
| A4 · V2 incluye caso sintético fecha futura | ✅ | `30_validate_silver.py` §V2 con `9999-01-01` |
| A5 · V3 incluye top 10 SKUs + diff < 0.5% | ✅ | `31_reconciliation.py` — diff 0.00%, Top 7 SKUs capturados |
| A6 · Tests sin `assert True` cosmético | ✅ | 0 ocurrencias en `tests/` |
| A7 · Evidencias sin PENDIENTE | ✅ | V1/V2/V3 actualizadas con outputs reales |

**Ejecución Databricks:** 69/69 statements OK, 15/15 assertions PASSED.
**Tests locales:** 26/26 passed.

#### Dev T · PWA Gate

| Item | Estado | Detalle |
|------|--------|---------|
| T1 · Refresh schema | ✅ | Usa `{ token: refreshToken }` |
| T2 · Ficha SKU schema real | ✅ | `sku`, `nombod`, `cantidad` |
| T3 · PWA manifest + SW | ✅ | `next-pwa` genera sw.js en build |
| T4 · Admin ping endpoint | ✅ | 200 admin / 403 vendedor / 401 sin auth |
| T5 · Offline cache | ✅ | IndexedDB via idb-keyval |
| T6 · .gitignore sw.js | ✅ | Patterns corregidos con `**/` prefix |
| T7 · Evidencias V4-V8 | ✅ | Todas actualizadas, sin PENDIENTE |
| T8 · typecheck + build + tests | ✅ | `tsc --noEmit` limpio, build exitoso, sin `test.skip` |

**Build:** First Load JS 87.3 kB, Middleware 26.6 kB.

### Hallazgos menores corregidos durante entrega

- `.gitignore` T6: patterns `public/sw.js` no ignoraban rutas anidadas (`motoshop-app/web/public/sw.js`). Corregido a `**/public/sw.js`.

### Pendiente de verificar (para revisor externo)

- [ ] Revisar ejecución Databricks: 69/69 statements, 15/15 assertions
- [ ] Revisar evidencia V1-V8 en `_runs/` de cada track
- [ ] Verificar que los entregables cumplen el gate de F2
- [ ] Emitir veredicto GO/NO-GO para cierre de F2 y avance a F3

---

## Sesión 2026-05-29 (29) · F2-FIX1 abierto — lanzar Dev A y Dev T en paralelo

### Resumen

Reviewer auditó F2-A/F2-B/F2-C y emitió **NO-GO al cierre de F2**. Hay implementación preliminar, pero no gate real: contratos rotos entre PWA/API, evidencias V4-V8 en `PENDIENTE`, hechos silver fuera de ADR-0014 y V2/V3 incompletas.

Plan correctivo completo: [`docs/plan-f2-fix1.md`](docs/plan-f2-fix1.md).

---

### Acción humana — abrir 2 sesiones de dev

#### 1 · Dev A · F2-FIX1-A Silver Gate

Prompt sugerido:

```text
Sos Dev Agent Track A. Leé INICIAR_AGENTE.md y después docs/plan-f2-fix1.md.
Ejecutá SOLO la sección 4 · Dev A · F2-FIX1-A · Silver Gate.
No toques SEGUIMIENTO.md, PENDIENTES.md ni docs/plan-f2-fix1.md.
Objetivo: cerrar V1/V2/V3 con evidencia real y corregir hechos silver para respetar ADR-0014.
Al terminar reportá commits, comandos ejecutados y paths de evidencia.
```

Checklist Dev A:

- ✅ A1 · Hechos silver idempotentes por `business_date` (DELETE+INSERT en 10–14).
- ✅ A3 · `20_quality_run.py` falla si hay reglas `CRITICAL` (assert_true, 0 critical en ejecución real).
- ✅ A4 · V2 incluye caso sintético de fecha inválida/futura (9999-01-01 en 30_validate_silver.py).
- ✅ A5 · V3 incluye top 10 SKUs + diff < 0.5% (31_reconciliation.py, diff real 0.00%).
- ✅ A6 · Tests sin `assert True` cosmético (0 ocurrencias en tests/).
- ✅ A7 · Evidencias V1/V2/V3 sin `PENDIENTE` ni `Completar` (verificadogrep 0 matches).

#### 2 · Dev T · F2-FIX1-T PWA Gate

Prompt sugerido:

```text
Sos Dev Agent Track T. Leé INICIAR_AGENTE.md y después docs/plan-f2-fix1.md.
Ejecutá SOLO la sección 5 · Dev T · F2-FIX1-T · PWA Gate.
No toques SEGUIMIENTO.md, PENDIENTES.md ni docs/plan-f2-fix1.md.
Objetivo: corregir contratos PWA/API y cerrar V4/V5/V6/V7/V8 con evidencia real.
Al terminar reportá commits, comandos ejecutados y paths de evidencia.
```

Checklist Dev T:

- ✅ T1 · Refresh manda `{ token: refreshToken }`.
- ✅ T2 · Ficha SKU usa schema real API: `sku`, `nombod`, `cantidad`.
- ✅ T4 · Endpoint `GET /api/admin/ping` creado (JWT decode, 200 admin / 403 vendedor / 401 sin token).
- ⚠️ T6 · `.gitignore` con `sw.js`/`workbox-*`; build genera PWA reproducible (se corrigió `**/` prefix faltante durante auditoría).
- ✅ T7 · Evidencias V4/V5/V6/V7/V8 actualizadas, sin `PENDIENTE`.
- ✅ T8 · `npm run typecheck`, `npm run build`, tests sin `test.skip` — todo verde.

### ⬜ LO QUE DEBE HACER EL SIGUIENTE AGENTE EN PC WINDOWS

> Para cerrar V4–V8 con datos reales. Requiere MySQL corriendo + FastAPI + Next.js.

#### PASO 0 — Prender la pila completa

```powershell
# 1. Arrancar MySQL (si no está corriendo)
net start MySQL  # o desde Services.msc

# 2. Crear .env de la API
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
copy .env.example .env
# Editar .env: poner MYSQL_USER=root (o api_read), MYSQL_PASSWORD=<real>

# 3. Activar venv y arrancar API
.\.venv\Scripts\Activate.ps1
uvicorn motoshop_api.main:app --reload --port 8000
# Debe responder en http://localhost:8000/health

# 4. Crear .env.local del frontend y arrancar
cd ..\web
copy .env.local.example .env.local
# Editar .env.local: NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
# Debe responder en http://localhost:3000
```

#### PASO 1 — V4 · Offline real

1. Build productivo: `npm run build && npm start`
2. Abrir `http://localhost:3000` en Chrome
3. Navegar a productos (llena cache de app shell + IndexedDB)
4. DevTools → Network → Offline
5. Recargar → app shell debe verse (login page)
6. Documentar en `_runs/v4_offline_demo.md`

#### PASO 2 — V5 · Sesión persiste

```powershell
# Login real
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"<real>"}' -c cookies.txt
# Abrir http://localhost:3000/products con sesión viva
# Cerrar pestaña, reabrir → debe seguir logueado
```
Documentar en `_runs/v5_session_persistence.md`.

#### PASO 3 — V6 · 50 búsquedas < 1s

```powershell
# Script de 50 búsquedas midiendo latencia vía PWA/proxy
# Ej: http://localhost:3000/api/products?q=aceite
# Calcular p50/p95/p99
# Actualizar _runs/v6_search_latency.json con valores reales
```

#### PASO 4 — V7 · Roles admin 200 / vendedor 403

```powershell
# Admin → 200
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"<real>"}' -c admin_cookies.txt
curl http://localhost:3000/api/admin/ping -b admin_cookies.txt
# → {"message":"Admin ping ok","user":"admin","role":"admin"} (200)

# Vendedor → 403
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"vendedor1","password":"<real>"}' -c vendor_cookies.txt
curl http://localhost:3000/api/admin/ping -b vendor_cookies.txt
# → {"detail":"Se requiere rol admin","user":"vendedor1","role":"vendedor"} (403)

# Sin auth → 401
curl http://localhost:3000/api/admin/ping
# → {"detail":"No autenticado"} (401)
```
Documentar curls y outputs en `_runs/v7_role_perms.md`.

#### PASO 5 — V8 · 5 SKUs PWA vs MySQL

```powershell
# Elegir 5 SKUs de la respuesta de /products
# Para cada SKU:
#   1. Abrir http://localhost:3000/products/<SKU> → anotar stock.total
#   2. MySQL: SELECT codprod, SUM(valor3) FROM auxinventario WHERE codprod='<SKU>' GROUP BY codprod
# Comparar: |PWA - MySQL| / MySQL < 0.5%
# Si todo cuadra, V8 cierra.
```
Documentar en `_runs/v8_data_match.md`.

#### PASO 6 — Commit evidencias

```powershell
git add motoshop-app/web/_runs/v4_offline_demo.md motoshop-app/web/_runs/v5_session_persistence.md motoshop-app/web/_runs/v6_search_latency.json motoshop-app/web/_runs/v7_role_perms.md motoshop-app/web/_runs/v8_data_match.md
git diff --cached | findstr /R /C:"PENDIENTE"
# → debe estar vacío
git commit -m "docs(F2-FIX1-T): evidencias V4-V8 con datos reales desde PC Windows"
git push origin main
```

#### PASO 7 — Reportar final

```
F2-FIX1-T listo. Commits: <hash>.
npm run typecheck/build/playwright: verdes.
Evidencias V4/V5/V6/V7/V8 actualizadas con datos reales.
V8 SKUs comparados: [lista de 5 SKUs con diff < 0.5%].
Listo para auditoría reviewer.
```

---

### Cuando ambos terminen

Cada dev debe reportar:

```text
F2-FIX1-<A/T> listo. Commits: <hashes>.
Pruebas: <comandos + resultado>.
Evidencias actualizadas: <paths>.
Listo para auditoría reviewer.
```

Después el Reviewer hace auditoría F2-FIX1-R y decide GO/NO-GO a F3.

---

## Sesión 2026-05-29 (23) · Plan F2 + ADR-0014 — ✅ CERRADA

✅ Humano aprobó las 16 DT en bloque + modo paralelo (2 agentes en su Mac). Discusión sobre DT-F2-1 cerrada con vista para "hoy + cierres" sin perder F4. ADR-0014 Accepted · 2026-05-29.

**Próximo paso:** Dev A y Dev T pueden arrancar Sprint F2-A y F2-B en paralelo siguiendo [`docs/plan-f2.md`](docs/plan-f2.md).

---

## ~~Sesión 2026-05-29 (23) · Plan F2 detallado + ADR-0014 esperando aprobación~~ *(histórico)*

### Resumen
F1.9 cerrada definitivamente. Revisor escribió plan F2 completo (3 sprints, ~18-22 h ejecutor, 12 días naturales) + ADR-0014 con 16 decisiones técnicas (DT-F2-1..16) para Silver y PWA.

Una sola acción humana cierra el gap y arranca Sprint F2-A:

---

### 🚨 Acción humana — 1 cosa

#### ⬜ Leer ADR-0014 y aprobar (o pedir ajustes) — ~10 min

Abrir [`docs/decisions/0014-stack-f2.md`](docs/decisions/0014-stack-f2.md).

Lectura recomendada:
- **Tabla resumen ejecutivo** al final (todas las DT en una tabla).
- Decisiones que tengan dudas (cada una con contexto + 3 opciones + recomendación).

16 decisiones, divididas en 2 bloques:

**Track A · Silver (6 decisiones):**
| # | Recomendación |
|---|----------------|
| DT-F2-1 | `INSERT REPLACE WHERE business_date` |
| DT-F2-2 | SCD Type 1 (snapshot) |
| DT-F2-3 | PySpark assert + `_quality_runs` |
| DT-F2-4 | Hechos por `business_date`, dims sin partición |
| DT-F2-5 | `fact_*` / `dim_*` |
| DT-F2-6 | `chispa` para tests Spark |

**Track T · PWA (10 decisiones):**
| # | Recomendación |
|---|----------------|
| DT-F2-7 | Next.js 14 + TS estricto (ya en F0) |
| DT-F2-8 | `httpOnly` cookie via API routes |
| DT-F2-9 | Fetch nativo + lock |
| DT-F2-10 | Zustand + SWR |
| DT-F2-11 | Tailwind raw + componentes propios |
| DT-F2-12 | `next-pwa` |
| DT-F2-13 | Workbox via `next-pwa` |
| DT-F2-14 | `idb-keyval` |
| DT-F2-15 | Stock NetworkOnly · Catálogo SWR |
| DT-F2-16 | TTL + botón manual |

**Tres caminos:**
- **"OK todas"** → marco ADR `Accepted`, D13 a fecha, ejecutor(es) arrancan.
- **"OK pero ajustar X"** → decime qué y ajusto.
- **"Necesito más contexto sobre Y"** → te detallo.

---

### Plan F2 a alto nivel *(para que sepas qué viene)*

| Sprint | Track | Duración | Cierra qué V/KPI |
|--------|-------|----------|-------------------|
| **F2-A · Silver** | A · Databricks | ~6 h | V1 duplicados, V2 fechas, V3 reconciliación < 0.5% |
| **F2-B · PWA Login + Búsqueda** | T · Next.js | ~6 h | V5 sesión persiste, V6 búsqueda < 1 s, V7 roles |
| **F2-C · PWA Stock + Offline** | T · Next.js | ~6 h | V4 offline, V8 datos cuadran, hito visible demo 4G |

**Modo serial (1 ejecutor):** ~12 días naturales, ~18-22 h ejecutor.
**Modo paralelo (2 ejecutores):** ~6-7 días naturales, mismo trabajo total. Ver §12 del plan.

Detalle completo en [`docs/plan-f2.md`](docs/plan-f2.md).

---

### ⚙️ Modo de ejecución · ¿1 ejecutor o 2 en paralelo?

F2-A (Silver) y F2-B (PWA login/búsqueda) son **completamente independientes** técnicamente. F2-C depende solo de F2-B (no de Silver). Se pueden disparar 2 agentes simultáneos:

| Agente | Sprints | Track | ~Tiempo |
|--------|---------|-------|---------|
| **Dev A** | F2-A | Track A · Databricks/PySpark | ~6 h |
| **Dev T** | F2-B → después F2-C | Track T · Next.js/TypeScript | ~12 h (6 + 6) |

Política de coordinación en archivos compartidos (SEGUIMIENTO, PENDIENTES): cada agente actualiza solo su sección, `git pull --rebase` antes de cada push. Detalle en [`docs/plan-f2.md`](docs/plan-f2.md) §12.

**Decidir en este chat (junto con aprobar el ADR):**
- ⬜ **Serial** — un solo ejecutor, ~12 días.
- ⬜ **Paralelo (recomendado si tenés ancho de banda)** — 2 ejecutores, ~6-7 días.

---

### Lo que pasa cuando aprobés ADR-0014 + decidás modo

1. Revisor marca ADR-0014 `Accepted` con fecha. D13 a fecha.
2. **Modo serial:** ejecutor único arranca Sprint F2-A.1.
3. **Modo paralelo:** Dev A arranca Sprint F2-A.1 y Dev T arranca Sprint F2-B.1 al mismo tiempo.
4. Sesión 26 abre con el(los) primer(os) commit(s).

---

## ~~Sesión 2026-05-29 (22) · Auditoría F1.9 + ADR-0013~~ — ✅ CERRADA

✅ **Humano aprobó ADR-0013 opción C** (Silver con `business_date` derivada). F1.9 cierra. F2 abierta. El bloque histórico queda como referencia.

(Verificación opcional del curl en vivo del endpoint `/health/data-freshness` queda al ejecutor cuando tenga 30 segundos — no bloquea F2.)

---

## ~~Sesión 2026-05-29 (22) · Auditoría F1.9 + ADR-0013 esperando aprobación~~ *(histórico)*

### Resumen
Revisor auditó F1.9 (commits `c9baa7e`, `75b5727`) y emitió **🟢 GO condicional**. Las 3 tareas del ejecutor están cumplidas con evidencia honesta. Sondeo reveló datos críticos que el plan no asumía bien (no existe `fecdoc` universal — cada tabla usa su propio nombre).

ADR-0013 escrito con la realidad del sondeo y publicado en estado **Proposed**. Una sola acción humana cierra F1.9 y abre F2.

---

### 🚨 Acción humana — 1 cosa

#### ⬜ Leer ADR-0013 y aprobar (o pedir ajustes) — ~5 min

Abrir [`docs/decisions/0013-fecha-tecnica-vs-negocio.md`](docs/decisions/0013-fecha-tecnica-vs-negocio.md).

Lectura recomendada:
- Sección **§Hallazgos del sondeo** (tabla con cada una de las 12 tablas y su columna real de fecha).
- Sección **§Opciones consideradas** (A, B, C con pros/contras).
- Sección **§Recomendación** (C, argumentada).
- Final: **"Para humano · qué tenés que decidir"**.

Tres caminos:
- **OK la C (recomendada)** → respondé en chat al revisor, marco ADR como `Accepted`, D12 a fecha, F2 arranca.
- **Mejor B / A / otra** → me decís cuál y por qué, ajusto ADR.
- **Necesito más contexto sobre Y** → me decís qué clarificar.

---

### Verificación menor opcional (~30 segundos)

#### ⬜ Curl al endpoint nuevo en vivo

Aprovechás que estás cerca de la API para confirmar que el endpoint que se programó en F1.9 también responde end-to-end (los tests mockeados ya cubren la lógica, esto cierra el círculo):

```powershell
curl https://api.fragloesja.uk/health/data-freshness
# Esperado: {"status":"OK","lag_hours":<N>,"last_manifest":"manifest_2026-05-29.json"}
```

Si devuelve `{"status":"ERROR","error":"..."}` → algo del wire-up necesita ajuste; reportarme el output.

Esto NO bloquea la aprobación del ADR — solo cierra evidencia de F1.9.

---

### Lo que pasa cuando aprobés el ADR

1. Revisor marca ADR-0013 `Accepted` con fecha.
2. D12 pasa a fecha de aprobación.
3. SEGUIMIENTO cabecera global: F0 ✅ / F1 ✅ / F1.5 ✅ / F1.9 ✅ / **F2 🟡 abierta**.
4. Revisor escribe `docs/plan-f2.md` + `docs/decisions/0014-stack-f2.md` (decisiones técnicas F2 con business_date ya decidida).
5. Sesión 23 abre con el plan F2 listo.

---

## Sesión 2026-05-29 (21) · F1.9 · Robustez del pipeline pre-F2

### Resumen
Sprint corto antes de F2 que blinda el pipeline contra: PC apagado, sin internet por días, horarios cambiantes. Y decide cómo separar `ingest_date` técnica vs `business_date` de negocio (ADR-0013).

**Plan completo: [`docs/plan-f1-9.md`](docs/plan-f1-9.md)** — leelo antes de actuar. Tiene implementación sugerida para cada tarea.

**Decisiones humanas tomadas en Sesión 21:**
- Frecuencia del dump: **cada 30 min**.
- Ventana operativa: **07:00 – 19:30**.
- Cómo encarar el ADR-0013: **Camino 1** (revisor escribe con 3 opciones DESPUÉS del sondeo, humano aprueba leyéndolo).

Tiempo estimado: **~3 horas del ejecutor**. Después el revisor toma el relevo con tareas 3-4.

---

### Tarea 0 ⬜ · Sondeo de columnas de fecha en BD *(~20 min)*

> **Pre-requisito del ADR-0013.** Sin esto, el ADR sería asunción.

1. PC MotoShop:
   ```powershell
   cd C:\Users\MotoShop\Documents\javidevmoto
   .\.venv-infra\Scripts\Activate.ps1
   ```

2. Crear `infra/explore_business_dates.py` con el código del plan §Tarea 0 (~50 líneas, introspección read-only de las 12 tablas core).

3. Ejecutar y capturar:
   ```powershell
   python infra\explore_business_dates.py | Tee-Object -FilePath notebooks\bronze\_runs\business_date_survey_2026-05-29.md
   ```

4. **Opcional:** añadir notas al final si encontrás algo raro (ej. "facventas tiene `fecdoc` y `fecven`, son distintas").

**Pasa si:** el `.md` muestra para cada una de las 12 tablas qué columnas de fecha tiene y sus stats (MIN, MAX, NULLs, '0000-*'). Si una tabla no tiene fechas, eso también se registra.

---

### Tarea 1 ⬜ · Lag monitor + endpoint `/health/data-freshness` *(~1 h)*

1. Crear `notebooks/bronze/06_pipeline_health.py` con el código del plan §Tarea 1.

2. En Databricks: ejecutar; debe reportar lag actual.

3. Crear módulo API:
   - `motoshop-app/api/src/motoshop_api/health/__init__.py`
   - `motoshop-app/api/src/motoshop_api/health/router.py` (código en plan §Tarea 1)

4. Wire-up en `motoshop-app/api/src/motoshop_api/main.py` (importar y `app.include_router(health_router)`).

5. Test: `motoshop-app/api/tests/test_health_freshness.py` que mockea WorkspaceClient y valida 4 status (OK/WARN/STALE/CRITICAL).

6. ```powershell
   cd motoshop-app\api
   .\.venv\Scripts\Activate.ps1
   pytest -m "not integration" -v
   ```

7. Restart API.

8. Verificar:
   ```powershell
   curl https://api.fragloesja.uk/health/data-freshness
   # → {"status":"OK","lag_hours":1.3,"last_manifest":"manifest_2026-05-29.json"}
   ```

9. Evidencia: `notebooks/api/_runs/data_freshness_check_2026-05-29.md` con salida del notebook + curl del endpoint + status.

**Pasa si:** notebook corre, endpoint responde JSON correcto, tests pasan, evidencia versionada.

---

### Tarea 2 ⬜ · Task Scheduler robusto + `--catch-up` *(~45 min)*

#### 2.1 Reconfigurar Task Scheduler (Windows UI)

Editar la tarea actual de dump. **Eliminar los 3 triggers actuales (02:00/12:00/20:00)** y crear uno nuevo:

**Trigger:**
- Tipo: Diariamente
- Hora de inicio: **07:00**
- ✅ Repetir tarea cada: **30 minutos**
- Por una duración de: **12 horas 30 minutos** (cubre 07:00 → 19:30)

**Settings:**
- ✅ "Ejecutar la tarea lo antes posible si se omite un inicio programado"
- ✅ "Si la tarea falla, reiniciar cada: **10 min**, hasta **3** intentos"
- ✅ "Detener la tarea si se ejecuta más de: **15 min**"
- ❌ "Iniciar la tarea solo si la red está disponible" — DESACTIVADO (catch-up lo maneja)

**Conditions:**
- ❌ "Iniciar solo si el equipo está inactivo" — DESACTIVADO
- ✅ "Reactivar el equipo para ejecutar esta tarea"

Capturar: `schtasks /query /tn "MotoShopDump" /v /fo LIST > infra\logs\task_scheduler_config.txt`.

#### 2.2 Flag `--catch-up` en `dump_to_cloud.py`

Añadir el código del plan §Tarea 2 — antes del bucle de extracción, escanear `_staging/` y subir Parquets pendientes.

#### 2.3 Modificar `motoshop_dump_to_cloud.ps1` para invocar con `--catch-up`

```powershell
python infra\dump_to_cloud.py --tables-core --catch-up
```

#### 2.4 (Opcional) Test de robustez

Si el humano puede dedicar 1 h:
1. Apagar módem 30 min en horario operativo.
2. Confirmar que Task Scheduler corre pero upload falla.
3. Reconectar.
4. Esperar siguiente schedule (≤30 min).
5. Verificar catch-up subió pendientes.

Evidencia opcional: `notebooks/bronze/_runs/catch_up_test_2026-05-29.md`.

**Pasa si:** Task Scheduler reconfigurado (captura anexada), `dump_to_cloud.py --catch-up` corre sin error (aunque no haya nada), `motoshop_dump_to_cloud.ps1` invoca con `--catch-up`.

---

### Tarea 3 ⬜ · Commit + push *(~10 min)*

```powershell
git add `
  infra/explore_business_dates.py `
  infra/dump_to_cloud.py `
  infra/motoshop_dump_to_cloud.ps1 `
  infra/logs/task_scheduler_config.txt `
  motoshop-app/api/src/motoshop_api/health/__init__.py `
  motoshop-app/api/src/motoshop_api/health/router.py `
  motoshop-app/api/src/motoshop_api/main.py `
  motoshop-app/api/tests/test_health_freshness.py `
  notebooks/bronze/06_pipeline_health.py `
  notebooks/bronze/_runs/business_date_survey_2026-05-29.md `
  notebooks/api/_runs/data_freshness_check_2026-05-29.md

git diff --cached | findstr /R /C:"password.*[:=].*[\"']" | findstr /V "redact_pii\|REDACTED"
# debería estar vacío

git commit -m "feat(F1.9): robustez pipeline - sondeo BD + lag monitor + Task Scheduler robusto + catch-up"
git push
```

---

### Tarea 4 ⬜ · Reportar al revisor

*"F1.9 tareas 0-2 hechas: sondeo en `business_date_survey_*.md`, lag monitor + endpoint, Task Scheduler reconfigurado. Commit `<hash>`. Listo para que escribas ADR-0013 y cierres F1.9."*

Revisor:
1. Lee evidencia del sondeo.
2. Escribe ADR-0013 con datos REALES (3 opciones desarrolladas, recomendación argumentada, estado `Proposed`).
3. Documenta **R5** en SEGUIMIENTO §Tablero de riesgos vivos.
4. Sincroniza `docs/contexto-proyecto.md`.
5. Notifica al humano para que apruebe ADR-0013.

Humano:
- Lee ADR-0013 (~5 min).
- Aprueba → revisor marca `Accepted` → **GO a F2 · Silver + PWA MVP**.

---

## Sesión 2026-05-28 (20) · F1.5 validada + arranque F2

### Resumen
Se revisó el bloque vivo de F1.5, se confirmó que la validación física en Windows ya está resuelta por evidencia, y se dejó escrito el arranque formal de Fase 2 para no seguir atados a un estado viejo.

### Evidencia ya disponible
- `pytest -m "not integration"`: 24/24 tests pasando.
- `notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md`
- `notebooks/api/_runs/r_x2_cache_2026-05-30.json`
- `docs/plan-f2.md`
- `docs/decisions/0012-stack-f2.md`

### Estado
- ✅ R3 resuelta
- ✅ R-X2 resuelta
- ✅ F1.5 cerrada
- 🟡 F2 arrancada con plan y ADR escritos

### Próximo paso
Empezar F2-A: Silver + validaciones de calidad.

## Sesión 2026-05-29 (19) · F1.5 Hardening — código commiteado, pendiente validación empírica en PC Windows

### Resumen
El agente completó la implementación de código y sincronizó docs. Commit `dac0245` empujado a `origin/main`. **Falta la ejecución física en la PC Windows** para completar las evidencias y poder entrar a Fase 2.

### ✅ Ya está en el repo (commit dac0245)
- `motoshop-app/api/pyproject.toml` → `cachetools>=5.3`
- `motoshop-app/api/src/motoshop_api/stock/repo.py` → TTLCache(200,300) + `clear_stock_cache()`
- `motoshop-app/api/tests/test_stock.py` → `test_stock_cache_hits_second_call`
- `notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md` → plantilla con `[PENDIENTE]`
- `SEGUIMIENTO.md`, `docs/contexto-proyecto.md`, `PENDIENTES.md` → actualizados

### ⬜ LO QUE DEBE HACER EL SIGUIENTE AGENTE EN PC WINDOWS

---

#### PASO 1 — Validar cache /stock (R-X2)
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -m "not integration" -v
```
**Meta:** Todos los tests pasan, incluyendo `test_stock_cache_hits_second_call`.

#### PASO 2 — Medir latencia /stock (cold + warm)
1. Reiniciar API para limpiar cache: `.\infra\start_api.ps1`
2. Pasada COLD (cache vacía): 100 requests al mismo SKU → calcular p50, p95, p99
3. Pasada WARM (cache poblada): 100 requests más → calcular p50, p95, p99
4. Actualizar `notebooks/api/_runs/r_x2_cache_2026-05-30.json`:
```json
{
  "sku": "MOTS1297",
  "requests_per_run": 100,
  "cold_run": {"p50_ms": 780, "p95_ms": 810, "p99_ms": 850},
  "warm_run": {"p50_ms": 8, "p95_ms": 12, "p99_ms": 20},
  "meta_cumplida": true,
  "nota": "Cold run ~780ms (esperado), Warm run <50ms"
}
```
**Meta:** warm p95 < 500 ms (esperado 5-50 ms).

#### PASO 3 — Kill-y-retry (R3) en ventana libre
> **Coordinar ventana fuera de schedule (02:00 / 12:00 / 20:00)**

**Preparación:**
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
.\.venv-infra\Scripts\Activate.ps1
Remove-Item -Recurse -Force _staging -ErrorAction SilentlyContinue
$TEST_DATE = "2026-05-30"
```

**Terminal A — Primera corrida (la que matarás):**
```powershell
python infra\dump_to_cloud.py --tables-core --ingest-date $TEST_DATE 2>&1 | Tee-Object _staging\kill_test_run1.log
```

**Terminal B — Esperar 7ª tabla:**
```powershell
Get-Content -Wait _staging\kill_test_run1.log
```
- Cuando veas `→ terceros: extrayendo...` → **Ctrl+C** en Terminal A

**Inspeccionar post-kill:**
```powershell
Get-ChildItem -Recurse _staging\*.parquet | Select-Object FullName, Length
python -c "
import pyarrow.parquet as pq, pathlib
for p in pathlib.Path('_staging').rglob('*.parquet'):
    try:
        t = pq.read_table(p); print(f'OK  {p.name}: {t.num_rows} filas')
    except Exception as e: print(f'BAD {p.name}: {e}')
"
```

**Terminal A — Segunda corrida (retry completo):**
```powershell
python infra\dump_to_cloud.py --tables-core --ingest-date $TEST_DATE 2>&1 | Tee-Object _staging\kill_test_run2.log
```
Dejar terminar completa.

**Ingesta a Bronze (Databricks):**
- Notebook `02_ingest_all_bronze.py` → widget `ingest_date = 2026-05-30` → Run all

**Validar V6 — SOLO DESPUÉS de la ingesta:**
- Notebook `04_check_large_tables.py` → widget `ingest_date = 2026-05-30` → Run all
- **⚠️ NO ejecutar V6 antes de la ingesta** — si no hay datos, ahora reporta `WARN: N=0` en vez de fallar, pero la validación sigue sin ser útil sin la ingesta previa

**Comparar conteos vs MySQL:**
- 12 tablas, tolerancia ±5 filas

**Completar evidencia:**
- Llenar `notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md` con valores reales

#### PASO 4 — Commit evidencias + push
```powershell
git add notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md notebooks/api/_runs/r_x2_cache_2026-05-30.json
git commit -m "docs(F1.5): evidencia R3 kill-y-retry + R-X2 cache metrics"
git push origin main
```

#### PASO 5 — Reportar al revisor
> *"F1.5 hecho: R3 cerrada (12 tablas Bronze==MySQL ±5), R-X2 cerrada (warm p95 = X ms), evidencia en _runs/, commit <hash>. Tests verdes, docs sincronizados → GO a F2."*

### Acceptance Criteria para cerrar F1.5 y abrir F2
- **R3:** 12 tablas con `bronze_rows == mysql_count` (±5)
- **R-X2:** warm p95 < 500 ms
- **Tests:** todos pasando con `pytest -m "not integration"`
- **Docs:** SEGUIMIENTO + contexto-proyecto + PENDIENTES sincronizados

### 🔑 REGLA DE ORO
NUNCA ejecutes V6 (`04_check_large_tables.py`) ANTES de completar la ingesta para la misma fecha. Orden:
1. Dump → 2. Retry completo → 3. Ingesta Bronze → 4. Validar V6 → 5. Evidencia

---

## Sesión 2026-05-28 (18) · F1.5 · Hardening pre-F2 (R3 + R-X2) — ✅ CERRADA

### Resumen
Sprint corto **proactivo** (no es FIX, nada está roto) que cierra 2 de las 5 deudas vivas antes de arrancar F2. Originado por recomendación humana 2026-05-28: *"fortalecer idempotencia + optimizar latencia /stock"*.

**Plan completo: [`docs/plan-f1-hardening.md`](docs/plan-f1-hardening.md)** — leer antes de actuar. Tiene plantillas exactas de evidencia y plan de remedio si R3 falla.

Tiempo estimado: **~2 horas** del ejecutor. Después, GO a F2.

---

### Tarea 1 ✅ · R3 · Probar idempotencia kill-y-retry (~45 min)

> **Coordinar ventana fuera del schedule 02:00 / 12:00 / 20:00** para no interferir con el dump nocturno.

1. PC MotoShop:
   ```powershell
   cd C:\Users\MotoShop\Documents\javidevmoto
   .\.venv-infra\Scripts\Activate.ps1
   Remove-Item -Recurse -Force _staging -ErrorAction SilentlyContinue
   $TEST_DATE = "2026-05-30"
   ```

2. Terminal A: `python infra\dump_to_cloud.py --tables-core --ingest-date $TEST_DATE 2>&1 | Tee-Object _staging\kill_test_run1.log`.

3. Terminal B: `Get-Content -Wait _staging\kill_test_run1.log` — esperar a que arranque la 7ª tabla (`→ terceros: extrayendo...`), entonces `Ctrl+C` en A.

4. Inspeccionar `_staging/` + UC Volume (script en plan §3.3).

5. Re-correr completo: `python infra\dump_to_cloud.py --tables-core --ingest-date $TEST_DATE`.

6. Databricks: ejecutar notebook `02_ingest_all_bronze.py` con widget `ingest_date = 2026-05-30`.

7. Comparar conteos bronze (12 tablas, partición `2026-05-30`) vs MySQL para las mismas tablas.

8. Pegar resultados en `notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md` siguiendo plantilla del plan §3 Evidencia.

**Pasa si:** las 12 tablas tienen `bronze_rows == count_mysql` (con tolerancia ±5 filas por ventas/compras nuevas entre runs).

**Si NO pasa:** aplicar patrón atomic-move en `dump_to_cloud.py` (plan §3 "Si R3 falla"), abrir ADR-0013 si el cambio es estructural.

---

### Tarea 2 ✅ · R-X2 · Cache `/stock` con TTL 5 min (~30 min)

1. PC MotoShop:
   ```powershell
   cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
   ```

2. Editar `pyproject.toml`: añadir `cachetools>=5.3` a `dependencies`.

3. Editar `src/motoshop_api/stock/repo.py` con el patrón del plan §4 Implementación sugerida (TTLCache 200 entries / 300 s + función `clear_stock_cache`).

4. Editar `tests/test_stock.py`: añadir `test_stock_cache_hits_second_call` (plantilla en plan §4).

5. Instalar + correr tests:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   pytest -m "not integration" -v
   ```

6. Reiniciar la API (`start_api.ps1`).

7. Re-medir latencia con **dos pasadas** (cold + warm), 100 requests cada una:

   ```powershell
   # Pasada cold (primer hit por SKU)
   # ... script de 100 requests ...
   # Pasada warm (segundas llamadas)
   # ... script de 100 requests ...
   ```

8. Pegar resultados en `notebooks/api/_runs/r_x2_cache_2026-05-30.json` siguiendo plantilla del plan §4 Re-medición K-1.

**Pasa si:** warm p95 < 500 ms (esperado: ~5-50 ms).

---

### Tarea 3 ✅ · Sincronizar SEGUIMIENTO + contexto-proyecto (~15 min)

- **SEGUIMIENTO §Tablero de riesgos vivos:** R3 a ✅ Resuelto, R-X2 a ✅ Resuelto con cifras warm.
- **SEGUIMIENTO §Notas de sesión:** añadir Sesión 19 con plantilla del plan §5.
- **docs/contexto-proyecto.md §10 Riesgos vivos:** sincronizar.
- **docs/contexto-proyecto.md §12.4 Métricas:** actualizar latencia `/stock` a `~50 ms warm / ~780 ms cold`.
- **docs/contexto-proyecto.md §6.2 Cronología F1:** añadir Sesión 19.
- **docs/contexto-proyecto.md §15:** actualizar (3 deudas, no 5).
- **PENDIENTES:** marcar tareas 1-3 a ✅ + bloque Sesión 19 cerrado.

---

### Tarea 4 ⬜ · Commit + push

```powershell
git add `
  motoshop-app/api/pyproject.toml `
  motoshop-app/api/src/motoshop_api/stock/repo.py `
  motoshop-app/api/tests/test_stock.py `
  notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md `
  notebooks/api/_runs/r_x2_cache_2026-05-30.json `
  SEGUIMIENTO.md PENDIENTES.md docs/contexto-proyecto.md

git diff --cached | findstr /R /C:"password.*[:=].*[\"']" | findstr /V "redact_pii\|REDACTED"
# debería estar vacío

git commit -m "feat(F1.5): hardening pre-F2 - R3 idempotencia + R-X2 cache stock"
git push
```

---

### Tarea 5 ⬜ · Reportar al revisor

*"F1.5 hardening hecho: R3 cerrada (conteos cuadran), R-X2 cerrada (warm p95 X ms), evidencia en `_runs/`, commit `<hash>`."*

Revisor audita en ≤10 min y emite **GO a F2** si todo cumple.

---

## Sesión 2026-05-28 (17) · F1-FIX2 completado y archivado

### Resumen
F1 quedó cerrada de forma limpia: las 3 evidencias faltantes ya están en `_runs/` y `SEGUIMIENTO.md` quedó sincronizado con F1 ✅ / F2 🟡.

### Cierre

- ✅ V6 archivada en `notebooks/bronze/_runs/v6_pagination_2026-05-28.md`.
- ✅ V7 archivada en `notebooks/bronze/_runs/v7_drift_2026-05-28.md`.
- ✅ C-1 archivada en `notebooks/api/_runs/c1_stock_real_2026-05-28.md`.
- ✅ SEGUIMIENTO actualizado con F1 ✅ y F2 🟡.
- ✅ El historial anterior se conserva como referencia.

---

## Sesión 2026-05-28 (16) · F1-FIX2 · Cierre limpio de F1 (3 evidencias + sync SEGUIMIENTO)

### Resumen
F1-FIX1 resolvió 11 de 13 ítems. Quedan 2 carencias menores que se cierran con este sprint. **Plan completo: [`docs/plan-f1-fix2.md`](docs/plan-f1-fix2.md)** — leer antes de actuar; tiene las plantillas exactas para pegar outputs.

**Lo que NO entra (decisión humana 2026-05-28):** las credenciales `FG28` en el README **se mantienen hasta nuevo aviso**. R2 reclasificada como deuda extendida con 4 triggers de re-evaluación (ver SEGUIMIENTO §Tablero de riesgos vivos).

---

### Tarea 1 ⬜ · Evidencia V6 (paginación)

1. Databricks → abrir `notebooks/bronze/04_check_large_tables.py`.
2. Setear widget `ingest_date = 2026-05-28`. Run all.
3. Pegar el output (totales, distinct, chunks, VEREDICTO) en `notebooks/bronze/_runs/v6_pagination_2026-05-28.md` siguiendo la plantilla del plan §2 Tarea 1.

**Pasa si:** ambas tablas con `distinct_after_pagination == total` y `total > 0`, status OK.

---

### Tarea 2 ⬜ · Evidencia V7 (schema drift con 2 fechas distintas)

> Lo más importante: que las 2 `ingest_date`s sean **distintas**. Si son iguales, V7 sigue 🔴.

1. PC Windows:
   ```powershell
   cd C:\Users\MotoShop\Documents\javidevmoto
   .\.venv-infra\Scripts\Activate.ps1
   python infra\dump_to_cloud.py --tables-core --ingest-date 2026-05-29
   ```

2. Databricks → `notebooks/bronze/02_ingest_all_bronze.py` con `ingest_date = 2026-05-29`. Run.

3. Databricks → `notebooks/bronze/05_schema_drift.py` con widgets:
   - `ingest_date_a = 2026-05-28`
   - `ingest_date_b = 2026-05-29`

4. Pegar el output en `notebooks/bronze/_runs/v7_drift_2026-05-28.md` siguiendo la plantilla del plan §2 Tarea 2.

**Pasa si:** las 12 tablas reportan `OK`, sin drift detectado. Si hay drift, documentar — no necesariamente FAIL pero requiere análisis.

---

### Tarea 3 ⬜ · Evidencia C-1 (stock real vs SQL directo)

1. PC Windows — llamar el endpoint y guardar la respuesta.
2. PC Windows — `SELECT codprod, COUNT(*), SUM(valor3) FROM auxinventario WHERE codprod='MOTS1297'`.
3. Pegar ambos outputs en `notebooks/api/_runs/c1_stock_real_2026-05-28.md` siguiendo la plantilla del plan §2 Tarea 3.

**Pasa si:** `API.total == SQL.SUM(valor3)` y ambos > 0.

> Recomendado: repetir con 1 SKU adicional para robustecer.

---

### Tarea 4 ⬜ · Sincronizar SEGUIMIENTO §F1

Detalle exacto en plan §2 Tarea 4. Resumen:

- Cabecera global: `F0 ✅ F1 ✅ F2 🟡 ...`, Fase activa: F2.
- V2 ⚠️ (R3), V4 ✅ (timing-safe), V6 ✅ (con `_runs/v6_pagination_*.md`), V7 ✅ (con `_runs/v7_drift_*.md`).
- Entregables Track A/T: ajustar a estado real (stock 🔴→✅, tests ⚠️→✅, rate limit 🔴→✅; **README con credenciales sigue 🔴 con nota de R2 deuda extendida**).
- KPIs: K-1 781ms (⚠️ no cumple, mitigación R-X2), K-2 79%, K-3 5/5.
- Bloqueadores: "Sin bloqueadores. F1 cerrada con deuda R1+R2 documentada."
- Sección **Lecciones de cierre F1** con los 4 puntos del plan §2 Tarea 4 punto 8.
- Nota de **Sesión 17 · F1 cerrada via F1-FIX2** (plantilla en plan §2 Tarea 4 punto 9).

---

### Tarea 5 ⬜ · Commit + push

```powershell
git add notebooks/bronze/_runs/v6_pagination_2026-05-28.md notebooks/bronze/_runs/v7_drift_2026-05-28.md notebooks/api/_runs/c1_stock_real_2026-05-28.md SEGUIMIENTO.md PENDIENTES.md
git commit -m "docs(F1-FIX2): cerrar F1 con evidencias V6/V7/C-1 y SEGUIMIENTO sincronizado"
git push
```

**Antes del commit:** verificar `git diff --cached | grep -iE "password\s*[:=]"` para no introducir nuevos leaks (los existentes en historial son R1/R2 ya aceptados).

---

### Tarea 6 ⬜ · Reportar al revisor

*"F1-FIX2 hecho: 3 evidencias en `_runs/`, SEGUIMIENTO actualizado, commit `<hash>`."*

Revisor audita en ≤15 min y emite **GO a F2** si todo cumple.

---

## Sesión 2026-05-28 (14) · F1-FIX1 · Remediación de auditoría — 🔴 NO-GO a F2

### Resumen
La auditoría de F1 (Sesión 14) detectó **5 hallazgos críticos**, **5 serios** y **3 KPIs sin medir**. F1 vuelve a 🟡. Plan correctivo: [`docs/plan-f1-fix1.md`](docs/plan-f1-fix1.md). Mientras no cierre, F2 no arranca.

> Por favor leé [`docs/plan-f1-fix1.md`](docs/plan-f1-fix1.md) antes de actuar — tiene los detalles, archivos exactos, criterios de aceptación y orden recomendado.

---

### 🚨 PASO 0 — Mitigación URGENTE de C-5 (humano, antes de cualquier otra cosa)

> Mientras esto no pase, la API en `https://api.fragloesja.uk/` es **vulnerable**. Cualquiera con acceso al repo puede loguearse con `admin/FG28`.

#### 0.1 ⬜ Generar 3 passwords aleatorios fuertes

PowerShell:
```powershell
1..3 | ForEach-Object { -join ((33..126) | Get-Random -Count 24 | ForEach-Object {[char]$_}) }
```
Guardar en password manager. **NO** compartir por chat, **NO** commitear, **NO** anotar en SEGUIMIENTO ni en commit messages (lección R1).

#### 0.2 ⬜ Generar hashes bcrypt
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
.\.venv\Scripts\Activate.ps1
python ..\..\infra\hash_password.py '<password admin>'
python ..\..\infra\hash_password.py '<password vendedor1>'
python ..\..\infra\hash_password.py '<password gerente1>'
```

#### 0.3 ⬜ Editar `motoshop-app/api/users.yaml` (gitignored)

Reemplazar los `hashed_password` por los nuevos. Verificar que NO se hace `git add`.

#### 0.4 ⬜ Reiniciar la API
```powershell
.\infra\start_api.ps1   # o reiniciar el servicio según tu setup
```

#### 0.5 ⬜ Verificar
```powershell
# La vieja debe fallar
curl -X POST https://api.fragloesja.uk/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"FG28"}'
# → debe devolver 401

# La nueva debe funcionar
curl -X POST https://api.fragloesja.uk/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"<new>"}'
# → debe devolver 200 con JWT
```

#### 0.6 ⬜ Reportar al revisor
*"Paso 0 hecho: vieja 401, nueva 200, API reiniciada."* — sin compartir las nuevas.

---

### Sprint F1-FIX1.A · Track A · Notebooks honestos (Ejecutor)

#### A-1 ⬜ Reescribir `04_check_large_tables` para probar paginación real

`notebooks/bronze/04_check_large_tables.py`: paginar `detfventas` (~27k) y `detcompras` (~11k) con offsets sucesivos de 5000, unir, comparar `distinct.count() == COUNT(*)`. Falla si pierde o duplica filas. Evidencia: `notebooks/bronze/_runs/v6_pagination_<fecha>.md`. Detalle: plan-f1-fix1.md §3 A-1.

#### A-2 ⬜ Reescribir `05_schema_drift` para comparar 2 `ingest_date`s

`notebooks/bronze/05_schema_drift.py`: capturar (nombre, tipo, nullable) de cada tabla en dos `ingest_date`s y diffearlas. Si hay drift, falla. Pre-requisito: 2 corridas del dump con `--ingest-date` distinto. Evidencia: `notebooks/bronze/_runs/v7_drift_<fecha>.md`. Detalle: plan-f1-fix1.md §3 A-2.

#### A-3 ⬜ Eliminar (o reparar) `databricks_workflow.json` y `create_databricks_workflow.py`

El JSON está corrupto sintácticamente (`Extra data`). El flujo real corre en Task Scheduler. **Recomendado: eliminar ambos archivos** y dejar R4 documentado. Si prefieres mantener, hay que arreglar las 2 líneas extra al final del JSON y verificar que el script lo carga sin error.

---

### Sprint F1-FIX1.B · Track T · Auth + stock real (Ejecutor)

> Prerequisito: Paso 0 completado.

#### B-1 ⬜ `/stock` debe leer `auxinventario` de verdad

Introspectar primero `DESCRIBE auxinventario;` y `SELECT * FROM auxinventario LIMIT 5;` para descubrir el nombre real de la columna de cantidad. Añadir tabla a `db/tables.py`. Reescribir `stock/repo.py` con JOIN `auxinventario ⨝ bodegas`. Evidencia: `notebooks/api/_runs/c1_stock_real_<fecha>.md` comparando la respuesta de la API contra `SELECT` directo en MySQL para un SKU concreto. Detalle: plan-f1-fix1.md §4 B-1.

#### B-2 ⬜ Refactor de tests con FakeRepos + `pytest.mark.integration`

- Mover tests que necesitan MySQL a `tests/integration/`.
- Reescribir `test_products.py` / `test_stock.py` / `test_sales.py` con `app.dependency_overrides` + `FakeRepos` que ya están en los `repo.py`.
- **Eliminar todos los `assert resp.status_code in (200, 500)`** y sus equivalentes.
- Registrar marker `integration` en `pyproject.toml`.
- Correr `pytest -m "not integration" --cov=...` y guardar el output en `notebooks/api/_runs/k2_coverage_<fecha>.md`. Meta: > 70%. Detalle: plan-f1-fix1.md §4 B-2.

#### B-3 ⬜ Limpiar credenciales del README

- Eliminar la tabla "Credenciales de prueba" de `motoshop-app/api/README.md`.
- Reemplazar por "Para credenciales, pedir al responsable del proyecto. Se gestionan en password manager interno; nunca se versionan."
- Actualizar `docs/handoff-f1.md` §3.2.
- Antes de commit: `git diff --cached | grep -iE "password\s*[:=]"` debe estar vacío.

#### B-4 ⬜ Login timing-safe (mitiga S-1)

Añadir dummy bcrypt verify cuando `user is None`. Añadir test que mida tiempos y verifique que la diferencia entre "usuario existe" y "usuario no existe" es < 50% del menor.

#### B-5 ⬜ Refresh token en body (mitiga S-2)

Cambiar `POST /auth/refresh` a body JSON `{"token": "..."}`. Actualizar tests.

#### B-6 ⬜ Rate limits al plan (mitiga S-3)

`/auth/login` y `/auth/refresh`: 10/min. `/products` y `/products/{sku}/stock` y `/sales/recent`: 60/min. Añadir test que excede el límite y verifica 429.

---

### Sprint F1-FIX1.C · KPIs medidos (Ejecutor + Humano)

#### C-K1 ⬜ Latencia `/stock` p95

100 requests secuenciales contra `/products/<sku>/stock` con un SKU real (post-B-1). Calcular p95. Evidencia: `notebooks/api/_runs/k1_stock_latency_<fecha>.md`. Meta: < 500 ms.

#### C-K2 ⬜ Cobertura > 70%

Cubierto por B-2. Confirmar que el reporte `pytest --cov` supera 70% en `auth/`, `products/`, `stock/`, `sales/`.

#### C-K3 ⬜ 5 corridas seguidas exitosas del dump

Hoy hay 2 documentadas. Necesitamos 3 más. Pueden venir naturalmente del schedule 3x diaria. Una vez haya 5 manifests con `error=null` consecutivos: `notebooks/bronze/_runs/k3_five_runs_<fecha>.md`.

---

### Cierre de F1-FIX1

Cuando todo esté hecho, ejecutor:
1. Actualiza SEGUIMIENTO §F1: V6/V7 vuelven a ✅, KPIs con cifras reales, sección F1-FIX1 cerrada.
2. Ping al revisor.
3. Revisor audita los `_runs/` nuevos + corre `pytest -m "not integration"` + verifica que README está limpio.
4. Si todo pasa: F1 ✅ y abre F2 🟡. Si no: F1-FIX2.

---

## Sesión 2026-05-28 (11) · Handoff F1 listo — sin acciones humanas pendientes

### Resumen
ADR-0011 Accepted, plan F1 detallado y aprobado, handoff doc escrito. El ejecutor (otra sesión de IA o vos en el PC) puede arrancar Sprint F1-A leyendo [`docs/handoff-f1.md`](docs/handoff-f1.md). El revisor (otra sesión Claude) auditará al cierre de cada sprint.

### Pendientes diferibles (no bloquean F1-A)
- ⬜ Conectar repo `motoshopdata` al workspace Databricks (3 min; mejora UX pero no necesario para correr notebooks importados).
- ⬜ CI básico GitHub Actions (lint + tests) — se planificará en Sprint F1-C o cierre F1.

### Próximo paso
Ejecutor arranca **Sprint F1-A · Bronze de las 12 tablas core** siguiendo [`docs/plan-f1.md`](docs/plan-f1.md) §Sprint F1-A.

---

## Sesión 2026-05-28 (10) · Aprobar stack F1 antes de arrancar F1-A

### Resumen
Plan detallado de F1 listo: [`docs/plan-f1.md`](docs/plan-f1.md) (3 sprints, archivos exactos, V1-V7 mapeadas, KPIs medibles, riesgos, backout) + [ADR-0011](docs/decisions/0011-stack-f1.md) con 10 decisiones técnicas.

**✅ Cerrado 2026-05-28:** ADR-0011 aprobado en bloque sin ajustes. Ejecutor confirmado en el mismo PC Windows (acceso directo a entorno). Push directo a `main` sin PRs. Handoff doc creado en [`docs/handoff-f1.md`](docs/handoff-f1.md).

### 1. ✅ Revisar y aprobar ADR-0011 *(bloquea Sprint F1-A)*

Abrir [`docs/decisions/0011-stack-f1.md`](docs/decisions/0011-stack-f1.md) y revisar la tabla resumen al final. 10 decisiones, cada una con su recomendación:

| # | Decisión | Recomendación |
|---|----------|----------------|
| DT-1 | Acceso MySQL desde API | **SQLAlchemy 2.0 core + pymysql** |
| DT-2 | JWT + bcrypt | **pyjwt + bcrypt** |
| DT-3 | Rate limiting | **slowapi in-memory** |
| DT-4 | Store usuarios F1 | **`users.yaml` gitignored** |
| DT-5 | Paginación | **offset + limit (50 / 200)** |
| DT-6 | Bronze idempotente | **`INSERT REPLACE WHERE`** |
| DT-7 | Manifest | **Subir al Volume `/_manifests/`** |
| DT-8 | Logging | **structlog JSON + PII redaction** |
| DT-9 | Tests API | **Repos + `pytest.mark.integration`** |
| DT-10 | Timezone | **Bronze raw → Silver UTC → API UTC `Z`** |

**Opciones de respuesta:**
- **"OK todas"** → marco D11 Accepted, ajusto el ADR a Accepted, y arranco F1-A en la próxima sesión.
- **"OK pero cambia X"** → me dices qué quieres distinto y lo refleja antes de arrancar.
- **"Necesito pensar Y"** → te dejo más opciones / contexto donde tengas duda.

### (Opcional, no bloquea F1-A) Cosas diferibles ya conocidas
- ⬜ Conectar repo `motoshopdata` al workspace Databricks (3 min, te pasé los pasos en sesiones previas).
- ⬜ CI básico GitHub Actions — lo escribo cuando lo pidas.

---

## Sesión 2026-05-28 (9) · Smoke test con datos reales + cierre F0 ✅

### Resumen
Se re-ejecutó el smoke test con `bodegas` (1 fila) y `formapago` (20 filas). Ambos pasaron validación (N > 0, conteos cuadran 1:1). Verificación #3 ✅. **F0 cerrado.**

### ✅ Fase 0 cerrada — no hay más acciones humanas pendientes
- ✅ 1. Smoke test real con `bodegas` (1 fila) y `formapago` (20 filas) — evidencia en `notebooks/bronze/_runs/smoke_test_2026-05-28.md`
- Pendientes diferibles: conectar repo a workspace Databricks, CI básico (GitHub Actions)

---

## Sesión 2026-05-28 (8) · Remediación de auditoría — 1 acción para cerrar F0

### Resumen
La auditoría detectó dos cosas en el cierre anterior: (a) el commit de cierre filtró la nueva password en su mensaje (**deuda aceptada** — no se va a corregir, ver R1 en SEGUIMIENTO), y (b) el smoke test atestó la verificación #3 con `sucursales` que tenía 0 filas, lo cual no demuestra movimiento de datos. Esta acción cierra (b).

El agente preparó: notebook SQL ejecutable en SQL Warehouse, scripts reproducibles del Volume y del Warehouse, deuda de credenciales documentada como riesgo vivo.

### 1. ✅ Re-ejecutar el smoke test con una tabla con datos *(bloquea cierre F0)*

**Por qué:** `sucursales` salió con 0 filas. El gate pide *"aunque sea con 10 filas"*. Hay que elegir una tabla pequeña pero **no vacía**. Candidatas:
- `bodegas` (~10 filas, recomendado — modelo mental directo)
- `formapago` (~20 filas — códigos de pago)
- `subproduct` (~? filas — alternativa)

**En el PC Windows:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
.\.venv-infra\Scripts\Activate.ps1

# Dump de las dos tablas pequeñas a Parquet local + UC Volume
python infra\dump_to_cloud.py --tables bodegas formapago
# El script imprime: filas, tamaño, ruta del Volume. Copiá esa salida.
```

**En Databricks (SQL Editor del SQL Warehouse):**

1. Importar/abrir [`notebooks/bronze/01_ingest_smoke_test.sql`](notebooks/bronze/01_ingest_smoke_test.sql) (o pegar las celdas en un nuevo notebook SQL).
2. Setear los widgets:
   - `table_name = bodegas`
   - `ingest_date = <la fecha del dump>` (por defecto hoy)
3. **Run all.**
4. La última celda 5 (validación) debe devolver:
   ```
   ✅ OK — conteos cuadran y N > 0 (verif. #3 cumplida)
   ```
5. Repetir el run con `table_name = formapago` para confirmar que el patrón funciona en >1 tabla.

### 2. ⬜ Capturar la evidencia en el repo *(2 minutos)*

Crear `notebooks/bronze/_runs/smoke_test_2026-05-28.md` con este contenido base (rellenar valores reales):

```markdown
# Smoke test bronze · 2026-05-28

## bodegas (ingest_date=2026-05-28)
- Dump local: N filas, X KB, Y segundos
- Subida UC Volume: ok
- COUNT(*) parquet:  N
- COUNT(*) bronze:   N
- Verdict: ✅ OK — conteos cuadran y N > 0

## formapago (ingest_date=2026-05-28)
- Dump local: N filas, X KB, Y segundos
- Subida UC Volume: ok
- COUNT(*) parquet:  N
- COUNT(*) bronze:   N
- Verdict: ✅ OK — conteos cuadran y N > 0

## DESCRIBE HISTORY motoshop.bronze.bodegas (5 últimas operaciones)
| version | timestamp | operation        | userName |
|---------|-----------|------------------|----------|
| ...     | ...       | CREATE_OR_REPLACE| ...      |
```

Commit:
```powershell
git add notebooks/bronze/_runs/smoke_test_2026-05-28.md
git commit -m "feat(F0): evidencia smoke test bronze - bodegas y formapago N>0"
git push
```

### 3. Reportar al agente
"Smoke test honesto pasó: bodegas N=X, formapago N=Y, evidencia en `notebooks/bronze/_runs/smoke_test_2026-05-28.md`." El agente marca verificación #3 a ✅, F0 cierra (con #5 como ⚠️ documentado por deuda aceptada), y abre F1.

---

### (Opcional, complementarias) Scripts reproducibles ya en el repo

Si querés re-correr el setup desde cero en otra máquina, ahora hay scripts versionados que reemplazan los clicks de la UI:

```powershell
python infra\create_uc_volume.py        # crea (o verifica) motoshop.bronze._landing
python infra\create_sql_warehouse.py    # crea (o verifica) auto_stop_mins ≤ 10
```

Ambos son idempotentes y validan permisos. La sesión 7 los hizo manualmente; estos scripts dejan el trabajo reproducible para auditoría académica y para F-F del roadmap.

---

## Sesión 2026-05-28 · Cierre estricto de F0 (auditoría)

### Resumen
Auditoría de la entrega F0 detectó **2 violaciones de gate** y **1 ⚠️ de compute** que la metodología obliga a cerrar antes de abrir F1. El agente preparó todo el código y la documentación; faltan **4 acciones humanas** en el PC para sellar el cierre.

> Si todo lo de abajo pasa ✅, F0 queda cerrado limpio y arrancamos F1.

### 1. ✅ Rotar contraseñas MySQL *(violación Regla de Oro #2)*

El `infra/create_users.sql.example` versionado tenía la contraseña real (`123450`). Aunque los 3 usuarios son `@localhost`, esto es deuda pública en GitHub. Pasos detallados en [infra/rotate_mysql_passwords.md](infra/rotate_mysql_passwords.md):

1. Generar 3 contraseñas de 24 caracteres con PowerShell (snippet en el doc).
2. Aplicar `SET PASSWORD FOR ... = PASSWORD('<nueva>')` para los 3 usuarios.
3. Actualizar `MYSQL_PASSWORD=` en los 3 `.env` locales.
4. Verificar: `pytest` en la API + `python infra/test_mysql_connectivity.py`.

**Reportar al agente:** "passwords rotados, todo verde" — sin compartir las contraseñas.

---

### 2. ✅ Crear el UC Volume de aterrizaje *(una vez)*

Pasos en [infra/setup_uc_volume.md](infra/setup_uc_volume.md). Desde el SQL Editor del workspace Databricks:

```sql
CREATE VOLUME IF NOT EXISTS motoshop.bronze._landing
  COMMENT 'Staging de Parquet subidos por dump_to_cloud.py (Track A · F1)';
```

**Reportar al agente:** confirmar que aparece en Catalog Explorer bajo `motoshop > bronze > _landing`.

---

### 3. ✅ Configurar SQL Warehouse con autoapagado 10 min *(verificación F0 #4)*

En el workspace:

1. **SQL → Warehouses → Create SQL Warehouse.**
2. Tamaño: el más pequeño disponible (en Free Edition, "Starter").
3. **Auto stop:** 10 minutos.
4. Permisos: el PAT actual debe poder ejecutarlo.

**Reportar al agente:** capturar el setting de auto-stop (screenshot o copy del valor). Eso cierra la verificación crítica #4.

---

### 4. ✅ Ejecutar el pipeline real Databricks ↔ MySQL *(verificación F0 #3)*

Esto es lo que de verdad sella la verificación #3 (la que el smoke test sintético no cumplía).

**En el PC Windows:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
python -m venv .venv-infra
.\.venv-infra\Scripts\Activate.ps1
pip install -r infra\requirements.txt

# Smoke test: 1 tabla, sin subir a Databricks
python infra\dump_to_cloud.py --tables sucursales --dry-run
# → genera _staging/sucursales/ingest_date=YYYY-MM-DD/part-0.parquet

# Smoke test completo: sube al UC Volume
python infra\dump_to_cloud.py --tables sucursales
# → sube al Volume + genera _staging/manifest_YYYY-MM-DD.json
```

**En Databricks (workspace UI):**

5. Importar `notebooks/bronze/01_ingest_smoke_test.py` (o ya está sincronizado si conectaste el repo en la tarea 5 de la sesión anterior).
6. Ejecutar el notebook con el SQL Warehouse pequeño o con serverless compute.
7. La última celda debe imprimir: `✅ Smoke test OK · verificación crítica #3 de F0 cumplida`.

**Reportar al agente:** copia del output de la celda 4 (los conteos coinciden) o screenshot del notebook completo. Esto cierra la verificación #3.

---

### 5. ⬜ (Opcional) Conectar el repo al workspace Databricks

Para que los notebooks se editen en Databricks UI y se versionen en GitHub:

1. **Workspace → User Settings → Linked accounts → GitHub.**
2. Conectar `javierportillar/motoshopData`.
3. **Repos → Add Repo → seleccionar el repo conectado.**
4. Trabajar los notebooks dentro de esa carpeta de `Repos/`.

No es bloqueante para cerrar F0 — se puede ejecutar el notebook importándolo manualmente — pero es lo "limpio".

---

### ✅ Fase 0 cerrada

Las 4 acciones se completaron en la sesión del 2026-05-28. Verificaciones #3, #4, #5 pasan a ✅. Fase 0 cerrada. Pasamos a Fase 1.

---

## Sesión 2026-05-27 · Decisiones P1–P4 aceptadas

### Resumen de esta sesión
- ✅ P1–P4 revisados y aceptados (recomendaciones confirmadas sin cambios)
- ✅ ADRs 0005–0008 actualizados a `Accepted`
- ✅ Script PowerShell `infra/backup_mysql.ps1` generado (alternativa Windows)
- ✅ SQL `infra/create_users.sql.example` generado con usuarios `analytics` y `api_read`
- ✅ Backup MySQL ejecutado (5.02MB, 7s)
- ✅ Usuarios MySQL creados: analytics, api_read, javier
- ➡️ Pendiente: cuenta Databricks, Cloudflare Tunnel, probar scaffolds

---

## Sesión 2026-05-27 · Cierre de andamiaje F0

### 1. ✅ Revisar y confirmar/ajustar P1–P4 *(bloquea F0 → F1)*

Los 4 ADRs fueron aceptados con las recomendaciones originales:
- P1 → **A** · Self-hosted dump → cloud storage
- P2 → **A** · Cloudflare Tunnel
- P3 → **A** · PC local
- P4 → **A** · Login propio (JWT + bcrypt)

---

### 2. ✅ Ejecutar el backup del MySQL *(verificación crítica #6 de F0)*

Desde PowerShell (como Administrador) en el PC donde corre `motoshop2024`:

```powershell
# Asegúrate de que mysqldump está en el PATH
# o ejecuta desde: C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\
cd C:\Users\MotoShop\Documents\javidevmoto
.\infra\backup_mysql.ps1 -BackupDir "$env:USERPROFILE\Backups\motoshop"
```

> Si `mysqldump` no está en el PATH, usa la ruta completa:
> ```powershell
> $env:PATH += ";C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin"
> .\infra\backup_mysql.ps1
> ```

**Reportar al agente:** tamaño y duración (los imprime el script al final).

---

### 3. ⬜ Probar que el scaffold corre *(opcional, valida los `⚠️` de F0)*

**API (FastAPI):**
```powershell
cd motoshop-app/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn motoshop_api.main:app --reload --port 8000
# abrir http://localhost:8000/health  →  {"status":"ok",...}
```

**Web (Next.js):**
```powershell
cd motoshop-app/web
npm install
copy .env.local.example .env.local
npm run dev
# abrir http://localhost:3000
```

**Reportar al agente:** si todo arranca, se marcan ✅ los dos entregables `⚠️` de F0. Si algo falla, pasar el error.

---

### 4. ✅ Crear usuarios MySQL read-only

Usuarios creados: `analytics`, `api_read`, `javier` (todos @localhost, password `123450`).
Verificación crítica #1 ✅ — INSERT command denied para los 3.

---

### 5. ⬜ Crear cuenta/workspace Databricks

- Crear cuenta en https://databricks.com (Free / Community tier para arrancar).
- Crear catálogo `motoshop` en Unity Catalog con esquemas `bronze`, `silver`, `gold`.
- Generar un Personal Access Token (PAT) y guardarlo en el password manager.
- Pasar al agente: **host** del workspace (URL) y confirmar que el PAT está disponible (sin enviarlo por chat).
- Después de esto, el agente podrá escribir el primer notebook bronze.

---

### 6. ⬜ Configurar el remoto GitHub para CI *(diferible)*

El repo ya está en [github.com/javierportillar/motoshopData](https://github.com/javierportillar/motoshopData). Cuando quieras meter CI:

- Decidir si se mantiene como repo público o se hace privado.
- Confirmar al agente para que escriba `.github/workflows/ci.yml` con ruff + pytest + (más adelante) lint del frontend y typecheck.

---

## Cómo se usa este archivo

- **Al inicio de cada sesión** el agente lo lee y prioriza según lo que esté ⬜.
- **Al cierre de cada sesión** el agente añade un nuevo bloque arriba con los pendientes nuevos generados y marca ✅ los que se resolvieron desde la sesión anterior.
- **Tú** marcas ✅ tú mismo cuando completes algo, o se lo dices al agente y él lo actualiza.
- **Histórico:** los bloques de sesiones pasadas no se borran. Sirven como rastro de qué se pidió y cuándo se cerró.
