# E3 · Producto descriptivo (Dashboards + KPIs)

> **Curso:** Big Data y Transformación Digital del Negocio · UAO 2025-2  
> **Módulos cubiertos:** 3 (analítica descriptiva), 4 (demo gerencial)  
> **Estado:** ✅ Listo  
> **Última actualización:** 2026-05-30

---

## 1 · Qué entregamos

5 marts gold con KPIs operativos + un dashboard Databricks SQL + 4 dashboards en PWA + 5 endpoints `/metrics/*` que conectan ambos.

**Decisión crítica:** [ADR-0015](../decisions/0015-stack-f3.md) — usar **Databricks SQL UI** como BI tool (Power BI diferido a F6 porque requiere Windows; queríamos solución Mac-friendly).

---

## 2 · Los 5 marts gold

| Mart | Propósito | Filas | Granularidad |
|------|-----------|-------|--------------|
| `mart_ventas_diarias_sku` | Ventas agregadas por día × SKU × bodega | ~57k+ post-F3.5 | día / SKU / bodega |
| `mart_inventario_actual` | Snapshot stock actual por SKU | 4,829 | SKU |
| `mart_rotacion_abc` | Segmentación ABC (80/15/5) por contribución a ventas | ~6,185 | SKU |
| `mart_cohortes_clientes` | Cohortes por mes de primera compra | 198 (post-F3.5) | mes_cohorte / cohorte |
| `mart_productos_dormidos` | SKUs sin venta > 90 días | 8,039 (post-F3.5) | SKU |

**Patrón de refresh:**
- Workflow Databricks Job `motoshop_gold_workflow` UNPAUSED.
- Schedule cron `0 30 2 * * ?` (02:30 COL nocturno).
- Idempotente: `DELETE WHERE business_date IN (X)` + `INSERT INTO` por particiones.
- Audit: cada corrida queda en `system.workflows.runs`.

**ADR técnico:** [0015](../decisions/0015-stack-f3.md) con 12 DT (DT-F3-1..12).

---

## 3 · KPIs medidos (post-F3.5 con dataset real)

**Periodo evaluado:** marzo-mayo 2026 (datos reales de la tienda).

| KPI | Valor | Fuente |
|-----|-------|--------|
| Ventas mes mayo 2026 | $23.5 M COP | `mart_ventas_diarias_sku` |
| Facturas / mes | 151 (mayo) - 364 (enero) | `silver.fact_ventas` |
| Unidades vendidas / mes | ~3-5k | `mart_ventas_diarias_sku` |
| SKUs en catálogo activo | 4,829 con stock + 8,039 dormidos | `mart_inventario_actual` + `mart_productos_dormidos` |
| Distribución ABC | A: ~80% revenue / B: ~15% / C: ~5% | `mart_rotacion_abc` |
| Cohortes de clientes | 198 (post-F3.5) | `mart_cohortes_clientes` |
| Top SKU por ventas | MOTS1297 ACEITE CASTROL — 850 facturas / $28.2M | `silver.fact_ventas_detalle` |
| Top cliente | CONSUMIDOR FINAL — 5,885 facturas / $556M | `silver.fact_ventas` |

**Honestidad metodológica:** estos números reemplazan los reportados en F3 inicial (que eran $99,200/mes con 7 productos únicos) porque F3.5 expuso que silver tenía 99.76% de las facturas perdidas por bug. Los números actuales son los reales.

---

## 4 · Dashboards entregados

### 4.1 · Databricks SQL UI

Dashboard ejecutivo con KPIs principales + tendencias temporales + drill-down por SKU. JSON exportado en [`notebooks/gold/dashboard_ejecutivo.json`](../../notebooks/gold/dashboard_ejecutivo.json).

### 4.2 · PWA (Next.js)

4 páginas de dashboards mobile-first con recharts (lazy-loaded):

| Página | Endpoint API | KPI principal |
|--------|--------------|---------------|
| `/dashboards/ventas` | `/metrics/sales-summary` | Tendencia mensual + top SKUs |
| `/dashboards/inventario` | `/metrics/inventory-summary` | Stock total + dormidos |
| `/dashboards/abc` | `/metrics/abc-segmentation` | Distribución 80/15/5 |
| `/dashboards/dormidos` | `/metrics/dormidos` | Lista SKUs sin venta > 90d |

**Performance medido:**
- First Load JS: 104-210 KB por página
- recharts cargados solo en subpages (no en landing)
- SWR con dedup 60s (evita request storms)

---

## 5 · V críticas cerradas (post-F3.5)

| V | Pregunta | Pass criterion | Resultado | Evidencia |
|---|----------|---------------|-----------|-----------|
| V1 | KPIs cuadran con sgHermes < 0.5% | `(sgHermes - silver) / sgHermes < 0.005` | ✅ 0.0% | [`v3_reconciliation_2026-05-29.md`](../../notebooks/silver/_runs/v3_reconciliation_2026-05-29.md) |
| V2 | ABC estable mes a mes < 30% migración | Comparación mes N vs N-1 | 🟡 Limitada por dataset (1-2 meses analíticamente útiles) — limitación reconocida |
| V3 | Workflow 7 corridas exitosas > 95% | Conteo en `system.workflows.runs` | 🟡 Diferida a F6 (R7) — schedule UNPAUSED, cierra sola con tiempo |
| V4 | Dashboard FCP < 5 s | Lighthouse / DevTools | ✅ Localhost OK | [`v4_dashboard_load.json`](../../motoshop-app/web/_runs/v4_dashboard_load.json) |
| V5 | Demo a stakeholder con feedback | Sesión registrada | 🟡 Diferida a F6 (R8) — humano agenda |
| V6 | PWA == Databricks SQL 0% diff | 5 KPIs comparados | ✅ Post-F3.5 con datos reales | [`v6_pwa_dashboard_match.md`](../../motoshop-app/web/_runs/v6_pwa_dashboard_match.md) |
| V7 | Plan de refresco documentado | Archivo en `_runs/` | ✅ | [`refresh_plan.md`](../archive/gold/refresh_plan.md) |

**Veredicto académico E3:** sustancia técnica completa. Las V diferidas (V3, V5) son de proceso/medición, no de funcionalidad — el workflow corre y el dataset está cuadrado.

---

## 6 · Cómo cumple Módulo 3 (analítica descriptiva)

| Componente | Cómo se cubre |
|------------|---------------|
| Modelado dimensional | Kimball: 5 dims + 5 facts + 5 marts en gold con naming convention `dim_*`, `fact_*`, `mart_*` |
| Granularidades adecuadas | Diaria + SKU + bodega — agregable up/down sin pérdida |
| Métricas de negocio | Ventas, rotación, dormidos, cohortes, ABC — alineadas con decisiones operativas |
| Visualización | Dashboards en Databricks SQL + recharts en PWA — consumidos por roles distintos (analista vs operador) |
| Storytelling | Dashboard ejecutivo + dashboards drill-down — pirámide de detalle |

---

## 7 · Cómo cumple Módulo 4 (demo gerencial)

🟡 **Parcialmente.** La PWA + dashboards están funcionales, pero:

- **V5 (demo a gerencia con feedback)** está diferida a F6 (R8) por decisión humana 2026-05-29. Razón: dejar que el workflow acumule días para que la demo sea más representativa.
- **R6 demo 4G** también diferida — necesita captura desde celular en red 4G real.

Cuando se cierre F6, este entregable incorporará el video/screenshots y el feedback estructurado.

---

## 8 · Limitaciones conscientes

- **Dataset analíticamente útil:** ~22 meses pero muchos SKUs con baja frecuencia → forecasting (E4) trabaja sobre eso.
- **V2 estabilidad ABC < 30% migración:** demostrable sobre ventana corta — requiere más histórico cuando F6 hardening.
- **Dashboards no autenticados por rol fino:** todos los usuarios JWT ven todo. Refinamiento de RBAC diferido a F5/F6.

---

## 9 · Evidencia versionada

- **Marts gold:** [`notebooks/gold/10_mart_ventas_diarias_sku.py`](../../notebooks/gold/10_mart_ventas_diarias_sku.py) y siguientes (10..14).
- **Quality gold:** [`notebooks/gold/20_quality_gold.py`](../../notebooks/gold/20_quality_gold.py).
- **Validación gold:** [`notebooks/gold/30_validate_gold.py`](../../notebooks/gold/30_validate_gold.py).
- **Runs verificados:** [`notebooks/gold/_runs/`](../../notebooks/gold/_runs/) — `run_gold_20260529_212128.md` (post-F3.5).
- **Tests SQL:** [`tests/gold/test_marts.py`](../../tests/gold/test_marts.py) — 52 tests con sqlparse validan estructura SQL real (INSERT OVERWRITE, UUID, particionado, JOINs, MONTHS_BETWEEN).
- **API endpoints:** [`motoshop-app/api/src/motoshop_api/metrics/`](../../motoshop-app/api/src/motoshop_api/metrics/).
- **PWA dashboards:** [`motoshop-app/web/app/(authenticated)/dashboards/`](../../motoshop-app/web/app/).
