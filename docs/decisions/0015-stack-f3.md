# ADR-0015 · Stack técnico de Fase 3 (DT-F3-1 a DT-F3-12)

- **Estado:** **Proposed** — bloquea inicio de Sprint F3-A
- **Fecha:** 2026-05-29
- **Bloquea:** F3 (los 3 sprints)
- **Decide:** Humano

## Contexto

Antes de tocar código de F3 hay 12 micro-decisiones técnicas — 8 de Gold (Track A) y 4 de PWA Dashboards (Track T). También resuelve la **decisión P5 pendiente desde F0** (BI tool principal).

---

## Track A · Gold + Workflow + BI

### DT-F3-1 · BI tool principal *(resuelve P5)*

**Contexto:** PLAN.md §16 dejó P5 pendiente desde F0: Power BI vs Databricks SQL vs ambos. F3 es donde toca decidir.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Power BI | Estándar gerencia colombiana; visual rico | Desktop solo Windows; Pro license para sharing; otra herramienta a mantener |
| B · **Databricks SQL** | Ya en el ecosistema; multiplataforma (web); incluido en Free Edition | Menos features visuales que Power BI |
| C · Ambos | Cubre todos los casos | Doble mantenimiento; duplicación de fuente de verdad |

**Recomendación: B · Databricks SQL.**

**Justificación:**
- El humano trabaja desde Mac (Power BI Desktop solo Windows).
- La PWA cubre el caso "dashboard mobile para gerencia en movimiento" — Databricks SQL cubre el caso "deep dive desktop".
- Si en F6 gerencia pide Power BI específicamente para reportes regulatorios, se suma como **ADR aparte sin re-arquitectura**.
- Free Edition incluye SQL Warehouse Serverless (ya configurado para F1).

**Consecuencias:**
- Dashboard ejecutivo se crea en Databricks SQL UI.
- Exportable como JSON para versionar en `notebooks/gold/dashboard_ejecutivo.json`.
- Power BI queda como ADR-F6+ si surge necesidad.

---

### DT-F3-2 · Patrón de escritura idempotente en Gold

**Contexto:** mismo problema que silver, pero ahora la clave puede ser `business_date` (marts diarios) o `business_month` (marts mensuales).

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `CREATE OR REPLACE TABLE` | Simple | Pierde particiones; no idempotente |
| B · **`INSERT INTO ... DELETE+INSERT ... REPLACE WHERE`** | Idempotente; coherente con silver | Verbose |
| C · `MERGE INTO` por PK | Fila a fila | Sobrecosto cuando se reemplaza partición entera |

**Recomendación: B** — mismo patrón de silver (DT-F2-1), consistencia.

**Consecuencias:** los 5 marts usan este patrón. Re-correr el workflow es seguro.

---

### DT-F3-3 · Particionado gold

**Contexto:** marts gold tienen distinta granularidad temporal.

**Recomendación:**

| Mart | Particionado | Razón |
|------|--------------|-------|
| `mart_ventas_diarias_sku` | `business_date` | Queries por día son comunes |
| `mart_inventario_actual` | sin partición | Es snapshot del día actual |
| `mart_rotacion_abc` | `business_month` | Mensual; recálculo full por mes |
| `mart_cohortes_clientes` | `business_month` | Mensual |
| `mart_productos_dormidos` | sin partición | Snapshot del día actual |

**Consecuencias:** menos archivos pequeños en Delta; queries eficientes.

---

### DT-F3-4 · Naming convention

**Opciones**

| | Pros |
|---|------|
| A · **`mart_*`** | Kimball clásico; coherente con dim_/fact_ de silver |
| B · `gold_fact_*` | Más explícito | Redundante con esquema `gold` |

**Recomendación: A · `mart_*`.**

**Consecuencias:** todas las tablas en `motoshop.gold.mart_<nombre>`.

---

### DT-F3-5 · Workflow programación

**Contexto:** workflow nocturno orquesta silver → gold + reconciliación.

**Opciones**

| Hora COL | Razón |
|----------|-------|
| 01:00 | Inmediatamente después del primer schedule de dump (02:00 de bronze) — pero choca con el de bronze |
| **02:30** | Después del dump de 02:00 + ingest_bronze; cubre el caso "PC apagado a las 01:00" |
| 04:00 | Muy tarde; lag percibido por gerencia matutina |

**Recomendación: 02:30 COL.**

**Cron quartz:** `0 30 2 * * ?`.

**Consecuencias:** dashboard de la mañana siempre con datos del día anterior. Lag típico < 8 h.

---

### DT-F3-6 · SCD para `mart_cohortes_clientes`

**Contexto:** cohortes capturan comportamiento de un grupo de clientes a través del tiempo. ¿Snapshot o historia?

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · **SCD1 snapshot mensual** | Tabla chica; query simple | Pierde detalle intra-mes |
| B · SCD2 con valid_from/valid_to | Captura toda la evolución | Tabla crece; complejo |

**Recomendación: A · SCD1 snapshot mensual.**

**Justificación:** las cohortes se calculan al cierre de cada mes; un punto por (cohorte × mes_observación) es suficiente para análisis de retención clásico.

**Consecuencias:** tabla con ~12 puntos/cohorte/año.

---

### DT-F3-7 · ABC threshold

**Contexto:** segmentación ABC clásica reparte SKUs por % de ingresos.

**Opciones**

| | Tradicional | Custom |
|---|-------------|--------|
| A · **80/15/5** | Clásico Pareto; estándar | — |
| B · 70/20/10 | Más balanceado | No estándar |
| C · Parametrizable | Flexible | Decisión que evitar |

**Recomendación: A · 80/15/5 clásico.**

**Justificación:** facilita comunicación con gerencia ("regla 80/20"). Si en F4 se quiere ajustar por demanda, se reabre como ADR aparte.

**Consecuencias:** SKUs ordenados por SUM(valor_total) DESC, acumulado hasta 80% son A, hasta 95% son B, resto C.

---

### DT-F3-8 · Definición de "Producto dormido"

**Contexto:** mart_productos_dormidos lista SKUs sin venta en N días para futuras decisiones de compra/liquidación.

**Opciones**

| Umbral | Caso de uso |
|--------|-------------|
| > 30 días | Demasiado sensible (alarma constante) |
| > 60 días | Razonable para baja rotación |
| **> 90 días** | Estándar industria; trimestre completo sin venta |
| > 180 días | Muy laxo; SKU realmente muerto |

**Recomendación: > 90 días.**

**Justificación:** trimestre completo sin venta es señal clara de baja rotación; alineado con cierres trimestrales.

**Consecuencias:** notebook `mart_productos_dormidos` filtra SKUs con `MAX(business_date) < CURRENT_DATE - 90`.

---

## Track T · API + PWA Dashboards

### DT-F3-9 · Chart library en PWA

**Contexto:** dashboards necesitan line charts, bar charts, pie charts, donut charts.

**Opciones**

| | Bundle | Features | Mobile |
|---|--------|----------|--------|
| A · Chart.js | ~70KB | Bueno | OK |
| B · **Recharts** | ~12KB tree-shaken | React-first | ResponsiveContainer nativo |
| C · Visx (Airbnb) | ~30KB | D3 wrapper potente | Manual |
| D · D3 puro | ~60KB | Máximo control | Manual |

**Recomendación: B · Recharts.**

**Justificación:**
- React-first encaja con Next.js.
- Bundle más chico que Chart.js (importante para PWA).
- `ResponsiveContainer` resuelve mobile sin código extra.
- Suficientes features para F3 (line, bar, pie, donut).

**Consecuencias:** `npm install recharts`. Componentes en `components/charts/`.

---

### DT-F3-10 · Caching métricas en PWA

**Contexto:** las queries `/metrics/*` son caras (queries a Databricks SQL Warehouse). Pero los marts solo cambian nocturno.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · No cache | Datos al día | Cada navegación reabre warehouse |
| B · **SWR con `dedupingInterval=60000`** (1 min) | Reduce queries; UX fluida | Datos hasta 1 min stale |
| C · localStorage + IndexedDB | Cache largo | Complejo; invalidación delicada |

**Recomendación: B · SWR con `dedupingInterval=60000`.**

**Justificación:**
- Marts cambian solo nocturno (cada 24 h).
- 1 minuto de cache no afecta UX y reduce drasticamente las queries.
- SWR ya en stack (DT-F2-10).

**Consecuencias:** hooks `useSalesSummary()`, etc. usan SWR con dedupingInterval configurado.

---

### DT-F3-11 · Push notifications

**Contexto:** F3 prepara estructura push. F4 dispara alertas reales (quiebre stock).

**Opciones**

| | Setup | Funciona en iOS Safari |
|---|-------|------------------------|
| A · **`web-push` library + Service Worker** | Standard W3C | Desde iOS 16.4 |
| B · OneSignal / Firebase | Más fácil | Dependencia third-party |
| C · No push en F3 | Cero trabajo | Hito F4 más lejos |

**Recomendación: A · `web-push` server-side preparado, no dispara.**

**Justificación:**
- En F3 solo se prepara: SW se suscribe, API guarda subscription, botón "Activar alertas" en perfil.
- F4 reusa la infraestructura para disparar alertas de quiebre.
- Web Push API es standard; sin lock-in.

**Consecuencias:** dep `pywebpush` en API + lib client en PWA. Endpoint `POST /api/push/subscribe` placeholder.

---

### DT-F3-12 · Mobile-first layout

**Contexto:** PWA debe verse bien en celular Y en desktop/tablet.

**Opciones**

| | Mobile | Desktop |
|---|--------|---------|
| A · Solo cards verticales | OK | Desperdicia espacio |
| B · Solo grid | Apretado | OK |
| C · **Responsive: stack vertical en <640px, grid 2x3 en >=768px** | Óptimo | Óptimo |

**Recomendación: C — Tailwind responsive.**

**Implementación:**
```jsx
<div className="flex flex-col gap-4 md:grid md:grid-cols-2 lg:grid-cols-3">
  <KpiCard ... />
  <KpiCard ... />
  ...
</div>
```

**Consecuencias:** cada página dashboards usa este pattern. Probado en Chrome DevTools 360x640, 768x1024, 1280x720.

---

## Resumen ejecutivo · todas las DT en una tabla

| # | Decisión | Recomendación | Deps nuevas |
|---|----------|----------------|-------------|
| DT-F3-1 | BI tool | Databricks SQL | — |
| DT-F3-2 | Escritura gold | INSERT REPLACE WHERE | — |
| DT-F3-3 | Particionado gold | mart-by-mart (date o month) | — |
| DT-F3-4 | Naming | `mart_*` | — |
| DT-F3-5 | Workflow | Cron `0 30 2 * * ?` (02:30 COL) | — |
| DT-F3-6 | SCD cohortes | SCD1 snapshot mensual | — |
| DT-F3-7 | ABC threshold | 80/15/5 clásico | — |
| DT-F3-8 | "Producto dormido" | > 90 días sin venta | — |
| DT-F3-9 | Chart library | `recharts` | `recharts>=2` |
| DT-F3-10 | Cache métricas | SWR dedup 60s | — |
| DT-F3-11 | Push notifications | `web-push` preparado | `pywebpush` (API) |
| DT-F3-12 | Mobile layout | Responsive Tailwind stack→grid | — |

**Deps nuevas:** 2 packages (recharts en web, pywebpush en API).

---

## Aceptación

Cuando el humano confirme este ADR, el agente:
- Cambia estado a `Accepted` y le pone fecha.
- Añade D14 a la bitácora de SEGUIMIENTO.
- Marca P5 como resuelto (Databricks SQL).
- Procede con Sprint F3-A.
