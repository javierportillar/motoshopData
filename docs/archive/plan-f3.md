# Plan detallado · Fase 3 · Gold + Dashboards

> Plan operativo de F3 derivado de PLAN.md §7 y SEGUIMIENTO.md. Hito: **gerencia abre la PWA y ve el dashboard ejecutivo con KPIs operativos cuadrando con sgHermes**.
>
> Stack técnico: [ADR-0015](decisions/0015-stack-f3.md) (Proposed; bloquea inicio de F3-A).
> Fechas: silver ya usa `business_date` (ADR-0013 opción C). Gold hereda.

---

## 1 · Objetivo y hito

**Hito visible de F3:**
> Gerencia abre la PWA en su iPad o desktop, ve un tablero ejecutivo con: ventas del mes, top 10 SKUs, top clientes, stock por bodega, productos dormidos. Click en cada card lleva a una vista detallada. Datos del último cierre nocturno (lag < 24 h, KPI F2 ya garantizado).

**Objetivo Track A (Gold):** 4 marts agregados desde silver + dashboard ejecutivo en Databricks SQL + workflow nocturno orquestado.

**Objetivo Track T (PWA Dashboards):** 3 endpoints `/metrics/*` + sección "Dashboards" mobile-first en PWA con cards de KPIs + estructura push notifications.

---

## 2 · Decisiones técnicas

Resueltas en [ADR-0015 · Stack técnico F3](decisions/0015-stack-f3.md). 12 decisiones (DT-F3-1 a DT-F3-12) — 8 Gold + 4 PWA Dashboards.

| # | Decisión | Recomendación |
|---|----------|----------------|
| DT-F3-1 | BI tool principal | **Databricks SQL** (Power BI diferido a F6) |
| DT-F3-2 | Patrón escritura gold | `INSERT REPLACE WHERE business_date/business_month` (idempotente) |
| DT-F3-3 | Particionado gold | `business_month` para marts mensuales · `business_date` para diarios |
| DT-F3-4 | Naming convention | `mart_*` para marts gold (no `gold_fact_*`) |
| DT-F3-5 | Workflow programación | Databricks Job nocturno **02:30 COL** (después del dump de 02:00 + ingesta silver) |
| DT-F3-6 | SCD para `mart_cohortes_clientes` | SCD1 snapshot mensual (no SCD2) |
| DT-F3-7 | ABC threshold | Clásico 80/15/5% por ingresos acumulados |
| DT-F3-8 | "Producto dormido" definición | **> 90 días sin venta** en silver |
| DT-F3-9 | Chart library en PWA | `recharts` (~12KB, Vega/D3 alternativos) |
| DT-F3-10 | Caching métricas en PWA | SWR con `dedupingInterval=60000` (1 min) — datos cambian poco |
| DT-F3-11 | Push notifications | Estructura `web-push` server-side preparada (no se dispara hasta F4 alertas) |
| DT-F3-12 | Mobile-first layout | Cards stackeadas vertical en mobile, grid 2x3 en tablet+ |

---

## 3 · Mapa de entregables → verificaciones críticas

Las 7 verificaciones críticas de F3 (de PLAN.md §7):

| # | Verificación | Cierra con… | Sprint |
|---|--------------|--------------|--------|
| **V1** | ¿KPIs cuadran con sgHermes? (<0.5%) | Notebook `gold/40_reconciliation_kpis.py` + `_runs/v1_kpis_match_<fecha>.md` | F3-A |
| **V2** | ¿Segmentación ABC es estable mes a mes? | Notebook `gold/41_abc_stability.py` compara 2 meses + `_runs/v2_abc_stability.md` | F3-A |
| **V3** | ¿Workflow se ejecuta puntualmente sin intervención? | 7 corridas consecutivas exitosas (KPI F3) + `_runs/v3_workflow_7_runs.md` | F3-A |
| **V4** | ¿Dashboard carga rápido (< 5 s)? | Lighthouse + grabación + `_runs/v4_dashboard_load.json` | F3-B |
| **V5** | ¿Gerencia entiende lo que ve? | Demo a stakeholder real + `_runs/v5_stakeholder_demo.md` con captura de feedback | F3-C |
| **V6** | ¿PWA muestra los mismos números que el dashboard? | Comparación 5 KPIs PWA vs Databricks SQL + `_runs/v6_pwa_dashboard_match.md` | F3-C |
| **V7** | ¿Hay plan de refresco bien definido? | `docs/gold/refresh_plan.md` + workflow docs | F3-A |

**KPIs F3 (de PLAN.md §9):**

| KPI | Meta |
|-----|------|
| Automatización pipeline (% corridas exitosas sin intervención) | > 95% |
| Frescura del dato (lag venta → dashboard) | < 24 h |

---

## 4 · Sprint F3-A · Gold + Workflow + Dashboard

**Duración estimada:** 2-3 sesiones (~6-8 h) · Dev A · Track A.

### 4.1 Pre-requisitos

- ✅ F2 cerrada con silver poblado (11 tablas en `motoshop.silver.*`).
- ✅ ADR-0013 (business_date) + ADR-0014 (stack F2) aceptados.
- ⏳ ADR-0015 debe estar Accepted antes del primer commit.

### 4.2 Archivos a crear

**Track A · Notebooks Gold + Workflow + Docs:**

| Path | Rol |
|------|-----|
| `notebooks/gold/10_mart_ventas_diarias_sku.py` | Agrega `silver.fact_ventas_detalle` por (`business_date`, `cod_producto`, `cod_bodega`) con SUMs |
| `notebooks/gold/11_mart_inventario_actual.py` | Snapshot del último estado de `silver.fact_inventario` por (`cod_producto`, `cod_bodega`) + JOIN dim_producto + dim_bodega |
| `notebooks/gold/12_mart_rotacion_abc.py` | Calcula ABC por ingresos: A=80%, B=15%, C=5% acumulado. Particionado por `business_month` |
| `notebooks/gold/13_mart_cohortes_clientes.py` | Cohortes por `business_month` de primera compra: recurrencia, ticket promedio, churn. SCD1 |
| `notebooks/gold/14_mart_productos_dormidos.py` | SKUs sin venta > 90 días (DT-F3-8). Lista para "compras pendientes" en F6 |
| `notebooks/gold/40_reconciliation_kpis.py` | V1: compara `SUM(ventas)` gold vs `SUM(totfven)` bronze del mes pasado |
| `notebooks/gold/41_abc_stability.py` | V2: corre ABC sobre 2 meses distintos, compara cambios drásticos (alerta si > 30% SKUs migran de categoría) |
| `notebooks/gold/42_workflow_monitor.py` | V3: lee últimas 7 corridas del Workflow, reporta success_rate y duración |
| `tests/gold/test_marts.py` | Tests unitarios `chispa` para cada cálculo (ABC, dormidos, cohortes) |
| `infra/create_gold_workflow.py` | Script reproducible para crear el Databricks Job (`databricks-sdk`) |
| `docs/gold/refresh_plan.md` | V7: documenta refresco de cada mart (frecuencia, dependencias, runbook) |
| `notebooks/gold/_runs/v1_kpis_match_2026-05-30.md` | Evidencia V1 |
| `notebooks/gold/_runs/v2_abc_stability_2026-05-30.md` | Evidencia V2 |
| `notebooks/gold/_runs/v3_workflow_7_runs_<fecha>.md` | Evidencia V3 (capturable tras 7 noches) |

### 4.3 Tareas en orden

1. **Marts core** (~3 h):
   - Notebooks 10-14.
   - Patrón canónico (`mart_ventas_diarias_sku` ejemplo):
     ```sql
     CREATE TABLE IF NOT EXISTS motoshop.gold.mart_ventas_diarias_sku (
       business_date DATE,
       cod_producto STRING,
       nom_producto STRING,
       cod_bodega STRING,
       nom_bodega STRING,
       cantidad_total DOUBLE,
       valor_total DOUBLE,
       num_facturas INT
     ) PARTITIONED BY (business_date);

     DELETE FROM motoshop.gold.mart_ventas_diarias_sku
     WHERE business_date >= DATE'2025-01-01' AND business_date <= CURRENT_DATE();

     INSERT INTO motoshop.gold.mart_ventas_diarias_sku
     SELECT
       h.business_date,
       d.cod_producto, dp.nom_producto,
       d.cod_bodega, COALESCE(db.nom_bodega, 'SIN_BODEGA') AS nom_bodega,
       SUM(d.cantidad) AS cantidad_total,
       SUM(d.total_detalle) AS valor_total,
       COUNT(DISTINCT d.num_documento) AS num_facturas
     FROM motoshop.silver.fact_ventas_detalle d
     JOIN motoshop.silver.fact_ventas h
       ON d.num_documento = h.num_documento AND d.cod_clase = h.cod_clase
     LEFT JOIN motoshop.silver.dim_producto dp ON d.cod_producto = dp.cod_producto
     LEFT JOIN motoshop.silver.dim_bodega db ON d.cod_bodega = db.cod_bodega
     WHERE h.business_date >= DATE'2025-01-01'
     GROUP BY h.business_date, d.cod_producto, dp.nom_producto, d.cod_bodega, db.nom_bodega;
     ```
   - Validar después de cada notebook: `SELECT COUNT(*), MIN(business_date), MAX(business_date) FROM motoshop.gold.<mart>`.

2. **Reconciliación V1** (~1 h):
   - Notebook 40 con tolerancia < 0.5%.
   - Reporta diff por mes — si algún mes > 0.5%, falla.

3. **ABC Stability V2** (~1 h):
   - Notebook 41 corre ABC sobre 2 meses distintos.
   - Cuenta SKUs que migraron de A→C, B→A, etc.
   - Si > 30% migraron drásticamente: bug o cambio real de negocio → investigar.

4. **Tests unitarios** (~1 h):
   - `pytest tests/gold/test_marts.py` con `chispa` y datasets sintéticos.
   - Verificar lógica ABC con dataset conocido (10 SKUs, % calculados a mano).
   - Verificar cálculo de "dormido" con SKU sintético sin venta > 90 días.

5. **Workflow Databricks** (~1 h):
   - Crear Job vía `infra/create_gold_workflow.py` (SDK).
   - Tasks en orden: `02_ingest_bronze` → `silver/*` → `gold/10..14` → `gold/40` → `gold/41`.
   - Schedule: cron `0 30 2 * * ?` (02:30 COL todos los días).
   - Notificación por email a `motoshop@example.com` si falla (placeholder).

6. **Refresh plan** (~30 min):
   - `docs/gold/refresh_plan.md` documenta cada mart: cuándo se actualiza, qué depende de qué, runbook si falla.

7. **Dashboard ejecutivo en Databricks SQL** (~1.5 h):
   - Crear dashboard en Databricks SQL UI.
   - 6 widgets: ventas mes (line chart), top 10 SKUs (bar), top 5 clientes (table), stock por bodega (donut), productos dormidos (table), ABC distribution (pie).
   - Exportar dashboard como JSON: `notebooks/gold/dashboard_ejecutivo.json`.
   - Documentar URL en `docs/gold/dashboard.md`.

### 4.4 Definition of Done · Sprint F3-A

- 5 marts gold creados con datos.
- V1 reconciliación < 0.5% en evidencia.
- V2 estabilidad ABC documentada.
- Workflow corre nocturno con schedule.
- Tests gold verdes (cobertura > 60% sobre transformaciones).
- Dashboard ejecutivo accesible en Databricks SQL.
- `docs/gold/refresh_plan.md` escrito.
- V7 cerrada.

### 4.5 Métricas a capturar

| Métrica | Objetivo |
|---------|----------|
| Tiempo corrida gold completa | < 10 min |
| Tasa éxito workflow | > 95% (7 corridas) |
| Diff reconciliación KPI mes pasado | < 0.5% |
| Dashboard render time | < 5 s |

### 4.6 Riesgos específicos F3-A

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F3A-1 | Volumen demo bajo (15 facturas) hace que ABC sea trivial | Documentar limitación; cuando llegue dataset completo, re-correr |
| R-F3A-2 | Free Edition agota horas serverless con workflow nocturno | Auto-stop SQL Warehouse 10 min ya ayuda; monitorear consumo |
| R-F3A-3 | Workflow falla nocturno y nadie se entera | V3 KPI explícito (95% éxito) + email placeholder configurado |
| R-F3A-4 | "Productos dormidos" alerta sobre SKUs activos pero no vendidos en demo | Definición clara > 90 días; ajustable parametro `dias_umbral` |

---

## 5 · Sprint F3-B · API Endpoints + PWA Dashboards

**Duración estimada:** 2 sesiones (~5-6 h) · Dev T · Track T.

### 5.1 Pre-requisitos

- F3-A no estrictamente obligatorio (PWA puede mostrar mock data inicialmente), pero **recomendable**: los endpoints `/metrics/*` leen de `motoshop.gold.mart_*`.
- ADR-0015 Accepted (especialmente DT-F3-9, DT-F3-12).

### 5.2 Archivos a crear

**Track T · API endpoints + Frontend:**

| Path | Rol |
|------|-----|
| `motoshop-app/api/src/motoshop_api/metrics/__init__.py` | Módulo metrics |
| `motoshop-app/api/src/motoshop_api/metrics/router.py` | Endpoints `/metrics/sales-summary`, `/metrics/inventory-summary`, `/metrics/abc-segmentation`, `/metrics/dormidos`, `/metrics/cohortes` |
| `motoshop-app/api/src/motoshop_api/metrics/repo.py` | `MetricsRepo` con queries Databricks SQL Warehouse vía `databricks-sql-connector` |
| `motoshop-app/api/src/motoshop_api/metrics/schemas.py` | Pydantic schemas (KPISummary, TopSKUItem, ABCBucket, etc.) |
| `motoshop-app/api/tests/test_metrics.py` | Tests con FakeMetricsRepo + integration mark |
| `motoshop-app/api/pyproject.toml` (modificar) | +`databricks-sql-connector` |
| `motoshop-app/web/app/(authenticated)/dashboards/page.tsx` | Tab "Dashboards" — landing con cards |
| `motoshop-app/web/app/(authenticated)/dashboards/ventas/page.tsx` | Ventas detallado |
| `motoshop-app/web/app/(authenticated)/dashboards/inventario/page.tsx` | Inventario detallado |
| `motoshop-app/web/app/(authenticated)/dashboards/abc/page.tsx` | Segmentación ABC |
| `motoshop-app/web/components/KpiCard.tsx` | Card con cifra grande + delta vs mes anterior |
| `motoshop-app/web/components/TopList.tsx` | Lista rankeada (top SKUs, top clientes) |
| `motoshop-app/web/components/AbcChart.tsx` | Pie chart ABC con `recharts` |
| `motoshop-app/web/components/SalesTrendChart.tsx` | Line chart ventas últimos 12 meses |
| `motoshop-app/web/components/InventoryByBodega.tsx` | Donut chart stock por bodega |
| `motoshop-app/web/lib/api/hooks.ts` (extender) | `useSalesSummary`, `useInventorySummary`, `useABC`, `useCohortes` |
| `motoshop-app/web/lib/push/setup.ts` | Estructura `web-push` (registro SW para push, no dispara) |
| `motoshop-app/web/public/icons/push-icon.png` | Icono push notifications |
| `motoshop-app/web/tests/dashboards.spec.ts` | Playwright E2E navegación + render |
| `motoshop-app/web/_runs/v4_dashboard_load.json` | Evidencia V4 |

### 5.3 Tareas en orden

1. **Endpoints `/metrics/*` en API** (~2 h):
   - Conectar a Databricks SQL Warehouse vía `databricks-sql-connector`.
   - 5 endpoints leyendo de `motoshop.gold.mart_*`.
   - Cache server-side (LRU 5 min) — los marts solo cambian nocturno.
   - Tests con FakeMetricsRepo + integration mark.

2. **Setup chart library** (~30 min):
   - `pip install recharts` en frontend.
   - Crear componentes base reutilizables (KpiCard, TopList).

3. **Pantalla Dashboards landing** (~1.5 h):
   - `app/(authenticated)/dashboards/page.tsx` con grid de cards.
   - Cards: Ventas Mes, Top SKU, Stock Total, Productos Dormidos, ABC Distribution.
   - Mobile-first: columnas stackeadas verticales en < 640px, grid 2x3 en >= 768px.
   - Click en card → navega a vista detallada.

4. **Vistas detalladas** (~1 h):
   - 3 páginas: `/dashboards/ventas`, `/dashboards/inventario`, `/dashboards/abc`.
   - Cada una con chart correspondiente + tabla detalle.

5. **Estructura push notifications** (~30 min):
   - Subscribe service worker con `web-push`.
   - Endpoint `POST /api/push/subscribe` en API (placeholder, no dispara).
   - Botón "Activar alertas" en perfil (estructura solamente).

6. **V4 dashboard load test** (~30 min):
   - Lighthouse mobile.
   - Tiempo first contentful paint.
   - Capturar en `_runs/v4_dashboard_load.json`.

7. **Tests Playwright dashboards** (~30 min):
   - Navegación landing → detalle.
   - Verificar render de charts.

### 5.4 Definition of Done · Sprint F3-B

- 5 endpoints `/metrics/*` operativos.
- Tab "Dashboards" en PWA con landing + 3 detalles.
- V4 < 5 s capturada.
- Tests E2E pasan.
- Estructura push notifications lista (no dispara).

### 5.5 Métricas a capturar

| Métrica | Objetivo |
|---------|----------|
| Dashboard FCP (first contentful paint) | < 3 s en 4G |
| Time to interactive | < 5 s |
| Bundle size añadido por charts | < 50 KB gzipped |

### 5.6 Riesgos específicos F3-B

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F3B-1 | `databricks-sql-connector` lento desde API local | Cache LRU 5 min + considerar mover queries a vista materializada |
| R-F3B-2 | Charts rompen en mobile pequeño | Test en Chrome DevTools 360x640; usar `ResponsiveContainer` de recharts |
| R-F3B-3 | Push permissions denegadas por usuario | Solo solicitar tras feature útil (no en login); persistir estado |

---

## 6 · Sprint F3-C · Validación + Demo + Cierre F3

**Duración estimada:** 1-2 sesiones (~3-4 h) · ambos devs + humano.

### 6.1 Pre-requisitos

- F3-A y F3-B completados.

### 6.2 Tareas en orden

1. **V5 demo a gerencia** (~1 h):
   - Agendar 30 min con stakeholder (Javier mismo o tercero del negocio).
   - Mostrar Databricks SQL dashboard + PWA Dashboards.
   - Capturar feedback en `_runs/v5_stakeholder_demo.md`.
   - Si el stakeholder NO entiende lo que ve: V5 NO cierra; iterar.

2. **V6 reconciliación PWA vs dashboard** (~1 h):
   - 5 KPIs específicos (ventas mes, top 1 SKU, top 1 cliente, stock total, % ABC A).
   - Comparar PWA vs Databricks SQL: deben coincidir hasta el último decimal.
   - Capturar en `_runs/v6_pwa_dashboard_match.md`.

3. **V3 workflow 7 corridas** (~después de 7 noches):
   - Esperar 7 corridas seguidas o forzar 7 ejecuciones manuales.
   - Reportar tasa éxito (objetivo > 95%).
   - Capturar en `_runs/v3_workflow_7_runs_<fecha>.md`.

4. **Cerrar R6 (deuda heredada de F2)** (~10 min — oportunidad para humano):
   - El humano usa esta ventana para grabar la demo 4G pendiente del cierre F2.
   - Bonus: si la PWA dashboards también funciona en 4G, evidencia doble.

5. **KPIs F3 medidos** (~30 min):
   - Automatización pipeline > 95% (capturado en V3).
   - Frescura del dato < 24 h (medible vía `/health/data-freshness` ya operativo).

6. **Lecciones de cierre F3** (~30 min — revisor):
   - Añadir a SEGUIMIENTO §Lecciones cuando F3 cierre limpio.

### 6.3 Definition of Done · Sprint F3-C + cierre F3

- V1-V7 con evidencia versionada.
- KPIs F3 medidos.
- Demo a gerencia con feedback capturado.
- PWA + dashboard coinciden numéricamente.
- Workflow corriendo > 7 días con > 95% éxito.

---

## 7 · Riesgos cross-sprint

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F3-X1 | Free Edition Databricks: cuota mensual se va con workflow nocturno + queries dashboard | Monitorear consumo; auto-stop 10 min ya configurado |
| R-F3-X2 | Demo a gerencia se cancela por agenda | Hacer demo con Javier mismo como stakeholder, capturar feedback honesto |
| R-F3-X3 | `databricks-sql-connector` requiere PAT con permiso `CAN_USE` en Warehouse | Verificar al inicio F3-B |
| R-F3-X4 | Volumen bajo (demo parcial) hace que dashboards se vean vacíos | Generar datos sintéticos para demo si gerencia lo pide |

---

## 8 · KPIs F3 y cómo se miden

| KPI | Meta | Cómo se mide |
|-----|------|---------------|
| Automatización pipeline (% corridas exitosas sin intervención) | > 95% | Tabla `motoshop._meta.workflow_runs` populada por Workflow + V3 |
| Frescura del dato (lag venta → dashboard) | < 24 h | Endpoint `/health/data-freshness` existente + check en dashboard |
| Diff KPIs sgHermes vs gold mes pasado | < 0.5% | V1 reconciliación |
| Estabilidad ABC mes a mes | < 30% SKUs migran de categoría | V2 |
| Dashboard FCP en 4G | < 3 s | Lighthouse |
| Tests gold cobertura | > 60% | `pytest --cov=tests/gold` |

---

## 9 · Backout plan

| Si pasa esto… | Hacemos esto |
|----------------|--------------|
| Reconciliación V1 > 0.5% | Stop F3-A; debug; F3-FIX1 |
| Workflow falla 3 noches seguidas | Stop activación schedule; correr manual hasta debug |
| Dashboard carga > 10 s | Pre-cómputo en lugar de queries on-demand; materialized views |
| Gerencia NO entiende los gráficos en demo | Iterar; cambiar visualización; no es bug técnico pero sí gate |
| `databricks-sql-connector` rompe en API | Fallback: queries vía REST API directa al SQL Warehouse |

---

## 10 · Calendario sugerido

### 10.1 Modo paralelo *(2 devs en tu Mac, ~6-8 días)*

```
Día 0 — Revisor escribe plan + ADR-0015. Push.
Día 1 — Humano aprueba ADR-0015 (10 min).

Día 2-4 (en paralelo):
  ├── Dev A (Track A): Sprint F3-A · 5 marts + workflow + dashboard SQL
  └── Dev T (Track T): Sprint F3-B · 5 endpoints + PWA dashboards

Día 5 — Revisor audita F3-A y F3-B (por separado).

Día 5-6 — Sprint F3-C: validación + demo + V5/V6/V7.
            (R6 demo 4G se captura aquí también — ya queda)

Día 6-7 — Revisor audita F3 completo. Lecciones cierre F3. GO a F4.

Día 8-14 — Workflow corre nocturno; V3 se cierra tras 7 corridas.
            (en background — no bloquea cierre formal)
```

Trabajo total ejecutor: **~11-14 horas** (suma de ambos devs).

### 10.2 Modo serial *(1 dev, ~12 días)*

```
Día 0-1 — Plan + ADR aprobado.
Día 2-5 — F3-A completo (8 h).
Día 6 — Revisor audita F3-A.
Día 7-9 — F3-B completo (6 h).
Día 10 — Revisor audita F3-B.
Día 11 — F3-C validación.
Día 12 — Cierre F3.
Día 12-19 — Workflow 7 corridas.
```

---

## 11 · Paralelización · misma política que F2

Ver [plan-f2.md §12](plan-f2.md) — la política sigue vigente:

- Dev A toca solo `notebooks/gold/`, `infra/`, `tests/gold/`, `docs/gold/`.
- Dev T toca solo `motoshop-app/api/src/motoshop_api/metrics/`, `motoshop-app/web/`.
- Archivos compartidos (SEGUIMIENTO, PENDIENTES): cada uno actualiza su sección + `git pull --rebase`.
- Revisor audita por separado.

### Sincronización en F3

F3-A y F3-B tienen 1 punto de contacto: **el contrato JSON de los endpoints `/metrics/*`**. Acordar el schema en ADR-0015 (DT-F3 Pydantic schemas) — ambos devs respetan. Dev T puede mockear hasta que Dev A entregue marts reales.

---

## 12 · ¿Necesita Windows?

**Casi no.** Detalle:

| Pieza F3 | Dónde |
|----------|-------|
| Notebooks gold | Edit en Mac → corren en Databricks cloud |
| Workflow programado | UI Databricks o SDK desde Mac |
| Dashboard ejecutivo Databricks SQL | 100% web, sin Windows |
| Endpoints `/metrics/*` en API | Edit en Mac, después restart API en Windows (script `pull-and-restart`) |
| Sección Dashboards en PWA | 100% Mac, `npm run dev` |
| Demo gerencia | Cualquier dispositivo (Mac, tablet, celular) |

**Único toque a Windows:** restart de la API después de pushear los endpoints nuevos. ~1 minuto vía RDP/TeamViewer o script automatizado.

Si en algún momento gerencia pide Power BI Desktop → eso sí requiere Windows, pero se difiere a F6 (ADR-0015 DT-F3-1).

---

## 13 · Referencias

- Plan F2: [`plan-f2.md`](plan-f2.md).
- ADR-0013 fechas: [`decisions/0013-fecha-tecnica-vs-negocio.md`](decisions/0013-fecha-tecnica-vs-negocio.md).
- ADR-0014 stack F2: [`decisions/0014-stack-f2.md`](decisions/0014-stack-f2.md).
- **ADR-0015 stack F3 (Proposed):** [`decisions/0015-stack-f3.md`](decisions/0015-stack-f3.md).
- Snapshot del proyecto: [`contexto-proyecto.md`](contexto-proyecto.md).
- Decisión P5 (BI tool) que se resuelve en ADR-0015 DT-F3-1: PLAN.md §16.
