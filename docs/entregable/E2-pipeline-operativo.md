# E2 · Pipeline operativo end-to-end

> **Curso:** Big Data y Transformación Digital del Negocio · UAO 2025-2  
> **Módulos cubiertos:** 2 (escalabilidad, calidad, seguridad), 5 (gobernanza)  
> **Estado:** ✅ Listo  
> **Última actualización:** 2026-05-30

---

## 1 · Qué entregamos

Un **pipeline operativo end-to-end** que:

1. Extrae datos cada 30 min de sgHermes MySQL local.
2. Los persiste en Delta Lake bronze de Databricks (UC Volume + Delta).
3. Los transforma a silver con `business_date` derivada y validaciones de calidad.
4. Expone una API HTTPS desde el PC local vía Cloudflare Tunnel.
5. Sirve una PWA Next.js con búsqueda de productos, ficha SKU, stock y ventas recientes.

**Disponible públicamente HOY:**
- API: https://api.fragloesja.uk
- Repo: https://github.com/javierportillar/motoshopData

---

## 2 · Fases que cubre este entregable

| Fase | Qué entregó |
|------|-------------|
| **F0 · Cimientos** | Workspace Databricks, catálogo `motoshop`, usuarios MySQL, túnel Cloudflare, hello world MySQL→UC Volume→Delta |
| **F1 · Bronze + API + PWA scaffold** | Pipeline diario MySQL→Bronze idempotente (12 tablas), FastAPI con `/auth`, `/products`, `/stock`, `/sales/recent`, PWA scaffold con login JWT |
| **F1.5 · Hardening pre-F2** | INICIAR_AGENTE/REVIEWER, CI smoke, evidencia consolidada |
| **F1.9 · Pipeline resiliente** | Task Scheduler cada 30 min (07:00-19:30), retry + catch-up flag, `/health/data-freshness` |
| **F2 · Silver + PWA MVP** | 5 dims SCD1 + 5 facts particionados por business_date, PWA con search/ficha SKU/stock, refresh token, idb-keyval cache |
| **F3.5 · Hardening Silver** | Fix `estfven/estcom` recuperó 6,324 facturas perdidas — sin esto el dataset analítico era trivial |

---

## 3 · Arquitectura de ingesta

### Patrón de ingesta (cada 30 min, ventana 07:00-19:30 COL)

```
1. Task Scheduler Windows dispara dump.bat cada 30 min
2. mysqldump motoshop2024 → parquet_writer.py
3. Parquet files → upload a UC Volume motoshop.bronze._landing
4. Notebook CREATE OR REPLACE TABLE FROM parquet (idempotente)
5. Bronze actualizado con ingest_date partition
```

**Características clave:**
- **Idempotente:** kill-y-retry validado (R3 ✅), evidencia en [`notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md`](../../notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md)
- **Resiliente a PC apagado:** Task Scheduler retry + catch-up flag procesa ventanas perdidas al volver
- **Monitoreado:** `GET /health/data-freshness` reporta lag en horas

### Patrón Bronze → Silver

Decisión clave: **`business_date` derivada en silver (no en bronze)** — [ADR-0013](../decisions/0013-fecha-tecnica-vs-negocio.md).

```sql
-- Patrón canónico (ADR-0014 DT-F2-1): INSERT REPLACE WHERE business_date
DELETE FROM silver.fact_ventas WHERE business_date IN (
  SELECT DISTINCT CAST(fecfven AS DATE)
  FROM bronze.facventas
  WHERE estfven IN ('A', 'B')
    AND fecfven IS NOT NULL
    AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
    AND CAST(fecfven AS DATE) <= CURRENT_DATE()
);

INSERT INTO silver.fact_ventas SELECT ... FROM bronze.facventas WHERE ...;
```

**Lecciones aprendidas:**
- F3.5 expuso que el filtro original `estfven='A'` descartaba el 99.76% de las facturas (6,325 facturas con `estfven='B'` perdidas). El fix `IN ('A','B')` recuperó 6,324. Esto está documentado en [F3.5 §10](../archive/plan-f3-5.md) y propagado como check bloqueante en [`INICIAR_REVIEWER.md`](../../INICIAR_REVIEWER.md) §3.2 Check 7.

---

## 4 · API operativa

**Endpoint base:** `https://api.fragloesja.uk`

| Endpoint | Método | Propósito | Auth |
|----------|--------|-----------|------|
| `/health` | GET | Salud del servicio | Público |
| `/health/data-freshness` | GET | Lag de datos en horas | Público |
| `/demo` | GET | Página interactiva mobile | Público |
| `/auth/login` | POST | Login con username + password → JWT | Público |
| `/auth/refresh` | POST | Refresh token | Cookie |
| `/products` | GET | Lista paginada con búsqueda | Bearer |
| `/products/{sku}` | GET | Ficha SKU | Bearer |
| `/products/{sku}/stock` | GET | Stock por bodega + TTL cache | Bearer |
| `/sales/recent` | GET | Últimas facturas | Bearer |
| `/metrics/sales-summary` | GET | KPIs ventas (gold) | Bearer |
| `/metrics/inventory-summary` | GET | KPIs inventario (gold) | Bearer |
| `/metrics/abc-segmentation` | GET | Segmentación ABC (gold) | Bearer |
| `/metrics/dormidos` | GET | Productos dormidos (gold) | Bearer |
| `/metrics/cohortes` | GET | Cohortes clientes (gold) | Bearer |
| `/docs` | GET | Swagger interactivo | Público |

**Características:**
- Rate limiting con slowapi (10 req/s por IP)
- CORS configurado por env (`cors_origins_list`)
- Structlog con PII redaction (Habeas Data Col)
- TTL cache en `/stock` (maxsize=200, ttl=300) — p95 warm < 50 ms
- Request ID middleware para tracing

---

## 5 · PWA

**Stack:** Next.js 14 App Router + TypeScript estricto + Tailwind raw + SWR + Zustand + next-pwa + idb-keyval + recharts.

**Funcionalidades:**
- Login persistente con httpOnly cookies (no JWT en localStorage)
- Catálogo: búsqueda en tiempo real con SWR (revalidación cada 60s)
- Ficha SKU: detalle completo + stock por bodega
- Stock con NetworkOnly (no cachear) + Catálogo con SWR + TTL manual
- Dashboards F3: ventas, inventario, ABC, dormidos (recharts lazy)
- Instalable como PWA (Workbox service worker)

**Métricas medidas (F3):**
- First Load JS: 104-210 KB
- Lighthouse PWA: pasable
- FCP dashboards: < 5 s en localhost (4G real pendiente — R6 diferida F6)

---

## 6 · Cómo cumple criterios del Módulo 2 + 5

### Módulo 2 — Calidad de datos

- **`_quality_runs` table** registra validaciones por corrida con `severity` (CRITICAL/WARNING).
- 14+ reglas de calidad: PKs únicas, no nulls en PKs, no totales negativos, no fechas futuras, `silver_completeness` (universo silver ≈ universo bronze ±1%).
- Evidencia: [`notebooks/silver/20_quality_run.py`](../../notebooks/silver/20_quality_run.py).

### Módulo 2 — Seguridad

- Usuarios MySQL `analytics` (read-only) y `api_read` (read-only sobre subset).
- JWT con bcrypt (`users.yaml` gitignored, hashes bcrypt en runtime).
- PII redaction en logs (`structlog` processors).
- Cloudflare Tunnel (no puertos expuestos).
- **Deudas conscientes documentadas:** R1 (passwords MySQL en historial Git), R2 (`FG28` en README) — aceptadas por decisión humana, ver [`docs/contexto-proyecto.md`](../contexto-proyecto.md) §10.

### Módulo 5 — Gobernanza

- 16 ADRs en [`docs/decisions/`](../decisions/) con status Proposed/Accepted/Superseded.
- Política de commits: convencionales, sin AI attribution, sin secretos.
- Política de cambios destructivos: nunca sin confirmación humana explícita.
- Audit trail completo en [`SEGUIMIENTO.md`](../../SEGUIMIENTO.md) §Notas de sesión (42 sesiones documentadas).

---

## 7 · Evidencia versionada (V críticas cerradas)

### F0 — Cimientos

- ✅ Hello world MySQL → UC Volume → Delta con N>0 — [`notebooks/bronze/_runs/full_run_2026-05-28.md`](../../notebooks/bronze/_runs/full_run_2026-05-28.md)

### F1 — Pipeline + API + PWA

- ✅ V1-V7 cerradas tras F1-FIX1+FIX2 — ver historial en [`SEGUIMIENTO.md`](../../SEGUIMIENTO.md) Sesiones 12-17
- ✅ Idempotencia kill-y-retry — [`r3_idempotency_kill_retry_2026-05-30.md`](../../notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md)
- ✅ Cache `/stock` — [`r_x2_cache_2026-05-30.json`](../../notebooks/api/_runs/r_x2_cache_2026-05-30.json) (si existe)

### F1.9 — Pipeline resiliente

- ✅ Lag monitor operativo en `/health/data-freshness`
- ✅ Task Scheduler config documentada en [`infra/setup_*.md`](../../infra/)

### F2 — Silver

- ✅ V1 (PK únicas, sin duplicados) — [`v1_no_duplicates_2026-05-29.md`](../../notebooks/silver/_runs/v1_no_duplicates_2026-05-29.md)
- ✅ V2 (calidad fechas) — [`v2_quality_dates_2026-05-29.md`](../../notebooks/silver/_runs/v2_quality_dates_2026-05-29.md)
- ✅ V3 reconciliación (post-F3.5) — [`v3_reconciliation_2026-05-29.md`](../../notebooks/silver/_runs/v3_reconciliation_2026-05-29.md)

### F3.5 — Silver hardening

- ✅ Fix silver universo completo — [`run_silver_fix_20260529_211852.md`](../../notebooks/silver/_runs/run_silver_fix_20260529_211852.md): fact_ventas 15→6,339, fact_ventas_detalle 58→27,771, fact_compras 16→762, fact_compras_detalle 733→11,623.

---

## 8 · Limitaciones conscientes

- **Hito demo 4G no capturado** (R6, diferida a F6 hardening).
- **Workflow Databricks postergado a F6** (R4) — hoy corre en Windows Task Scheduler.
- **Single PC point of failure** (R10) — mitigado con catch-up, no eliminado.
