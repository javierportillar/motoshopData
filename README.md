# MotoShop · Plataforma digital para una motopartes

Proyecto que nació como entrega de la materia **Big Data y Transformación Digital del Negocio** (Maestría UAO 2025-2) y terminó siendo una plataforma de operación real para una tienda de repuestos de moto en Cali. Lakehouse medallion + PWA mobile-first + ML aplicado al inventario.

> **Estado vivo:** [SEGUIMIENTO.md](SEGUIMIENTO.md) · **Plan canónico actual:** [docs/plan-v1.5-duckdb.md](docs/plan-v1.5-duckdb.md) · **Índice maestro:** [docs/MASTER.md](docs/MASTER.md)

---

## Visión General

Transformar el flujo de información de una tienda de repuestos de moto que opera con **sgHermes** (POS legacy en MySQL 5.0) en una plataforma analítica + operativa moderna sin tocar el sistema productivo. Dos tracks paralelos en un monorepo:

- **Track A · Analítico** — Lakehouse medallion (bronze → silver → gold) + modelos ML aplicados a inventario y demanda.
- **Track T · Transaccional** — FastAPI + PWA Next.js para que el vendedor consulte stock, el gerente vea KPIs, y ambos puedan accionar sobre alertas en tiempo real.

**Horizonte:** V1 (entrega académica) → V1.5 (sostenibilidad gratuita "para siempre", arquitectura actual) → V2 (producción seria, post-curso).

---

## Roles del Proyecto

| Rol | Responsable | Responsabilidad |
|-----|-------------|-----------------|
| **Product Owner (PO)** | Javier (humano) | Define visión, prioriza backlog, valida entregables, demos a stakeholders |
| **Arquitecto / Revisor** | Agente IA (rol reviewer) | Decisiones arquitectónicas, ADRs, auditoría de fases, GO/NO-GO |
| **Dev Backend (Track A / Track T API)** | Agente IA (rol dev) | Implementa pipeline, repos, endpoints. Sin decisiones arquitectónicas autónomas |
| **Dev Frontend (Track T PWA)** | Agente IA (rol dev) | Implementa UI/UX, dashboards, integración API. Sin decisiones arquitectónicas autónomas |
| **Dev W (Operación Windows)** | Agente IA (rol dev) | Pull main, restart API, scheduled tasks, sync notebooks, pipeline batch |

Las reglas de cada rol están en [INICIAR_AGENTE.md](INICIAR_AGENTE.md) y [INICIAR_REVIEWER.md](INICIAR_REVIEWER.md).

---

## Stack Tecnológico

### Lenguajes y Frameworks

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| **API backend** | FastAPI + Pydantic v2 | Tipado fuerte, OpenAPI nativo, async-friendly. Render lo deploya con `uvicorn` y auto-deploy desde GitHub. |
| **PWA frontend** | Next.js 14 (App Router) + TypeScript | SSR + service worker out-of-the-box. Vercel lo deploya con auto-deploy. Mobile-first con offline queue. |
| **Charts** | Recharts | React-native (no Canvas), accesible, suficiente para los 12 dashboards. |
| **Estado cliente** | Zustand + SWR | Zustand para auth (persist localStorage), SWR para data fetching con cache + revalidation. |
| **Auth** | JWT + bcrypt propio | ADR-0008. RBAC por claim `role` (admin/gerente/vendedor). Sin OAuth (alcance docente). |
| **Motor de queries (V1.5)** | **DuckDB embebido** | Migración 2026-05-31 desde Databricks SQL Warehouse. Single-node, SQL Postgres-compatible, lee Parquet nativo. Latencia < 200ms vs 2-5s Databricks. Cero infra que mantener. ADR-0023. |
| **Pipeline batch (V1.5)** | Python + pandas + mysql-connector + duckdb | Reemplaza notebooks Databricks. Corre en Windows como Scheduled Task. |
| **Storage del archivo gold** | Cloudflare R2 (S3-compatible) | 10 GB free forever, sin egress fees a Render, mismo dashboard que ya usás para túnel y DNS. |
| **MySQL bronze** | MySQL 5.0 (sgHermes legacy) | INTOCABLE. Solo lectura. Tablas `app_*` en InnoDB para escritura desde la PWA. |
| **Reverse proxy + DNS** | Cloudflare Tunnel + Cloudflare DNS | `api.fragloesja.uk` → Render. PWA en `app.fragloesja.uk` → Vercel. ADR-0006. |
| **Hosting API** | Render Free | Auto-deploy desde main, UptimeRobot keep-warm cada 5 min. |
| **Hosting PWA** | Vercel Free | Auto-deploy desde main, edge functions para API proxy. |
| **Tests Python** | pytest + ruff | Mínimo de cobertura en transformaciones críticas. |
| **Tests frontend** | Playwright | 71 tests en F7-C. Smoke producción + accesibilidad. |
| **ML (descartado V1)** | — | ADR-0017 + ADR-0020: forecasting por SKU no superó baseline. Forecasting por categoría con moving average sostenido. |

### Por qué este stack y no otro

- **DuckDB sobre Databricks**: 50 MB de gold no justifican Spark + cluster + serverless. DuckDB es 10-30x más rápido y $0/mes para siempre. Ver `docs/plan-v1.5-duckdb.md` §10 para el reasoning completo.
- **Next.js sobre React puro**: SSR mejora First Contentful Paint en 4G (escenario real del vendedor). Service worker built-in para offline queue.
- **Render + Vercel sobre AWS propio**: gratis, auto-deploy desde GitHub, sin DevOps que mantener. Trade-off aceptado: SPOF en Render free, mitigado con UptimeRobot.
- **MySQL sobre Postgres**: viene de fábrica con sgHermes. Tocar el POS no es opción.

---

## Arquitectura del Sistema (V1.5)

```
┌────────────────────────────────────────────────────────────────┐
│ WINDOWS (on-premise) — POS y pipeline batch                     │
│                                                                 │
│  sgHermes MySQL 5.0                                             │
│  └─ bronze raw (12 tablas core)                                 │
│         │                                                       │
│         │ Scheduled Task daily 02:00 COL                        │
│         ▼                                                       │
│  pipeline/ (Python puro, sin Spark)                             │
│  bronze → silver (5 dims + 5 facts) → gold (5 marts + auxs)     │
│         │                                                       │
│         │ rclone                                                │
│         ▼                                                       │
└─────────┼───────────────────────────────────────────────────────┘
          ▼
┌────────────────────────────────────────────┐
│ CLOUDFLARE R2 (10 GB free)                  │
│  motoshop_gold.duckdb        (latest)       │
│  motoshop_gold_YYYYMMDD.duckdb (snapshots)  │
└─────────┬───────────────────────────────────┘
          │
          │ cold start o POST /admin/data/refresh
          ▼
┌─────────────────────────────────────────────┐
│ RENDER (Free) — FastAPI                      │
│  /tmp/motoshop_gold.duckdb (local cache)     │
│  DuckDBMetricsRepo (queries locales)         │
│  Cloudflare Tunnel → api.fragloesja.uk       │
└─────────┬───────────────────────────────────┘
          │ HTTPS + JWT
          ▼
┌─────────────────────────────────────────────┐
│ VERCEL — Next.js PWA                         │
│  app.fragloesja.uk                           │
│  Service worker + offline queue              │
│  12 dashboards · 2 personas (vendedor/gerente)│
└─────────────────────────────────────────────┘
```

### Por qué arquitectura híbrida (cloud + on-premise)

1. **Bronze es sgHermes.** El POS no se toca, no se migra, no se replica completo a la nube. La fuente de verdad sigue donde está.
2. **Pipeline cerca de los datos.** Procesar 600K registros leyendo MySQL local toma 2-5 min. Por tunnel desde nube tomaría 30+ min y expondría superficie.
3. **Read serving cerca del usuario.** La PWA pega Render (latencia <100ms desde Colombia). DuckDB embebido = cero latencia a "DB".
4. **Storage en el medio.** R2 es el punto de sincronización. Es barato, replicado, y sirve como audit trail (snapshots por fecha).

### Por qué Cloudflare en todo

- Ya usábamos Cloudflare Tunnel para exponer la API desde Windows (ADR-0006)
- DNS ya está en Cloudflare (`fragloesja.uk`)
- Free tier alcanza para el tráfico real
- Mismo dashboard para todo

---

## Capas del Lakehouse Conceptual

Aunque el motor cambió de Spark a DuckDB en V1.5, la arquitectura medallion (ADR-0001) **se mantiene**.

| Capa | Qué hay | Dónde vive (V1.5) |
|------|---------|---------------------|
| **Bronze** | 12 tablas raw de sgHermes, sin transformación | MySQL `sgHermes.*` en Windows |
| **Silver** | 5 dimensiones (SCD1) + 5 facts particionados por `business_date` derivada (ADR-0013) | Tablas DuckDB `motoshop_silver_*` |
| **Gold** | 5 marts de negocio + tablas auxiliares (alertas, forecast, drift) | Tablas DuckDB `motoshop_gold_*` |
| **App (operativo)** | `app_alert_actions`, `app_audit_log`, `app_purchase_plans` — escritura desde PWA | MySQL InnoDB en Windows (ADR-0004) |

Los 5 marts gold cubren las preguntas de negocio:

- **mart_ventas_diarias_sku** — qué se vendió, cuándo, a quién
- **mart_inventario_actual** — qué hay en bodega ahora
- **mart_rotacion_abc** — clasificación Pareto por ingreso (A=80% / B=15% / C=5%)
- **mart_cohortes_clientes** — quién vuelve a comprar
- **mart_productos_dormidos** — qué no se mueve hace 90+ días

---

## Personas y dashboards (F7-A discovery)

| Persona | Contexto | Dashboards principales |
|---------|----------|--------------------------|
| **Vendedor mobile** | Atiende cliente con celular en mano, 4G inestable | Búsqueda rápida SKU, alertas, dormidos para liquidar, acciones del día |
| **Gerente desktop** | Revisa números del mes, toma decisiones de compra | Ventas (diaria/mensual/histórica), inventario, ABC, forecast por categoría, cohortes, vendedores, drift, plan compras |

12 dashboards en total. Branding: logo propio + paleta rojo `#C83828` / accent cyan `#0EA5E9` / neutros 50-950.

Detalle en `docs/f7/personas_kpis.md` y `docs/f7/dashboards_content.md`.

---

## Pipeline de datos (V1.5)

### Refresh diario

```
02:00 COL · Scheduled Task Windows ejecuta refresh_v15.ps1
   ├─ python pipeline/run_all.py
   │     ├─ bronze (sgHermes MySQL → DataFrame pandas)
   │     ├─ silver (transformaciones + business_date derivada)
   │     └─ gold (marts + alertas + forecast por categoría)
   ├─ rclone copy out/motoshop_gold.duckdb r2:motoshop-gold/
   ├─ rclone copy out/motoshop_gold.duckdb r2:motoshop-gold/motoshop_gold_YYYYMMDD.duckdb
   └─ curl POST api.fragloesja.uk/admin/data/refresh (admin token)
        └─ API descarga nuevo DuckDB y recarga conexión sin downtime

03:00 COL · UptimeRobot ping confirma /health/data-freshness < 60 min
```

### Por qué Scheduled Task en Windows y no GitHub Actions

- MySQL bronze está en Windows local → leer ahí es instantáneo
- Pipeline en GHA requeriría exponer MySQL al tunnel → superficie de ataque mayor
- Trade-off: Windows es SPOF para refresh, pero el último DuckDB en R2 sigue sirviéndose → la app NO se cae si Windows se apaga, solo los datos se congelan hasta que vuelva

---

## Pruebas

| Tipo | Herramienta | Qué probamos |
|------|-------------|--------------|
| **Unitarias backend** | pytest | Transformaciones silver/gold, schemas Pydantic, repos DuckDB |
| **Paridad de datos** | pytest custom | Cifras DuckDB vs `docs/audit/raw_responses.json` (snapshot) — tolerancia 0 |
| **Integration API** | pytest + httpx | 17 endpoints autenticados, 200 + esquema correcto |
| **E2E PWA** | Playwright | 71 tests · smoke producción + accesibilidad |
| **Smoke producción** | Script Python con curl | 17 endpoints contra `api.fragloesja.uk` post-deploy |

Regla del proyecto: **toda corrección que cierra un bug exige curl/test/screenshot con evidencia pegada en el commit**. Sin esto, queda abierta. Ver `INICIAR_REVIEWER.md` §9 checks.

---

## Despliegue

### Infraestructura productiva actual

| Plataforma | URL | Auto-deploy | Plan |
|------------|-----|-------------|------|
| Vercel (PWA) | `app.fragloesja.uk` | ✅ webhook GitHub main | Free |
| Render (API cloud) | `api.fragloesja.uk` | ✅ webhook GitHub main | Free + UptimeRobot keep-warm |
| Windows (pipeline) | — | 🟡 pull manual + Scheduled Task | On-premise |
| Cloudflare R2 (storage) | — | rclone push desde Windows | Free 10 GB |
| MySQL sgHermes (POS) | Windows local | — | On-premise |

### Cómo correr local

```bash
# Track A — Pipeline (cuando sea Windows)
cd pipeline
uv sync
python run_all.py        # genera out/motoshop_gold.duckdb

# Track T — API
cd motoshop-app/api
uv sync
cp .env.example .env     # rellenar R2 credentials
DATA_BACKEND=duckdb uvicorn motoshop_api.main:app --reload --port 8000

# Track T — Web
cd motoshop-app/web
npm install
cp .env.local.example .env.local
npm run dev
```

---

## Roadmap de Fases

```
F0 ✅ Cimientos — MySQL, Databricks, túnel, backups, hello world
F1 ✅ Ingesta — Bronze 12 tablas + API endpoints base + PWA scaffold
F2 ✅ Silver + PWA MVP — 5 dims + 5 facts + búsqueda SKU
F3 ✅ Gold + Dashboards — 5 marts + 4 dashboards + workflow nocturno
F4 ✅ Predictivo — Feature store + forecasting (categoría) + alertas quiebre
F5 ✅ Escritura — PWA → app_* tables + RBAC + idempotency
F6 ✅ Hardening + cloud — PWA Vercel + API Render + auto-deploy
F7 ✅ Reestructuración UX — 12 dashboards + branding + 71 tests Playwright
─────────────────────────────────────────────────
V1.5 🟡 Migración DuckDB — Spike → Pipeline → Repo → Refresh → Cutover → Frontend+SemanticSearch
─────────────────────────────────────────────────
V1.6 ⬜ IA aplicada (LLM) — Briefing diario gerente → Forecast narrativa → Q&A chat
─────────────────────────────────────────────────
V2  ⬜ Producción seria — 40 deudas V1 mapeadas en docs/roadmap-v2-produccion.md
```

**Por qué V1.5 existe:** Databricks Free Edition perdió Serverless Compute el 2026-05-31. App al 100% rota. Migración a DuckDB es la única vía sostenible $0/mes. Plan completo en [`docs/plan-v1.5-duckdb.md`](docs/plan-v1.5-duckdb.md).

**Por qué V1.6 existe:** Una vez sostenible, agregamos capa de IA aplicada al negocio: briefing diario en lenguaje natural al gerente (vía Telegram), narrativa explicativa del forecast, y chat conversacional con tool use sobre DuckDB. Costo proyectado <$3/año. Plan completo en [`docs/plan-v1.6-llm.md`](docs/plan-v1.6-llm.md).

---

## Reglas que no negocio

1. **sgHermes es intocable** — no se modifican esquemas, datos ni permisos del MySQL productivo.
2. **Credenciales fuera de Git** — siempre `.env`, nunca hardcodeadas.
3. **Toda cifra en pantalla debe cuadrar con sgHermes** con tolerancia documentada.
4. **Modelo que no supera al baseline no se libera** — prefiero el promedio histórico conocido (ADR-0017).
5. **Predicciones son sugerencias revisables**, no decisiones autónomas (hasta V2).
6. **Toda tarea cerrada exige evidencia ejecutada** (curl/test/screenshot). Sin eso, queda abierta.
7. **Revisor firma GO por fase.** El ejecutor no cierra su propio trabajo.

---

## Decisiones técnicas (ADRs)

22 ADRs aceptados. Las más relevantes:

| # | Decisión | Por qué importa |
|---|----------|-----------------|
| [0001](docs/decisions/0001-medallion-architecture.md) | Medallion estándar bronze→silver→gold | Spine de la arquitectura |
| [0007](docs/decisions/0007-api-hosting.md) | API hosteada en PC local | Origen del SPOF luego mitigado con Render (F6-D) |
| [0008](docs/decisions/0008-auth-provider.md) | JWT + bcrypt propio | Sin terceros para auth |
| [0013](docs/decisions/0013-fecha-tecnica-vs-negocio.md) | `business_date` derivada en silver | Universo de ventas correcto |
| [0017](docs/decisions/0017-forecasting-honest-metrics.md) | Split temporal + WAPE para demanda intermitente | Métricas ML honestas |
| [0020](docs/decisions/0020-forecasting-aggregated-categoria.md) | Forecasting por categoría, no por SKU | Dataset insuficiente para SKU |
| [0022](docs/decisions/0022-workflow-databricks-unificado.md) | Workflow Databricks unificado | (deprecated en V1.5) |
| **0023** _(pendiente)_ | Read backend DuckDB-first | Reemplazo de Databricks SQL Warehouse |

Lista completa en [`docs/MASTER.md`](docs/MASTER.md) §5.

---

## Cómo navegar este repo

| Vengo a... | Empiezo por |
|------------|-------------|
| Entender el proyecto en 5 min | Este `README.md` |
| Saber qué pasa hoy | [`SEGUIMIENTO.md`](SEGUIMIENTO.md) cabecera + última nota |
| Ver el plan activo | [`docs/plan-v1.5-duckdb.md`](docs/plan-v1.5-duckdb.md) |
| Saber qué tengo que hacer yo (humano) | [`PENDIENTES.md`](PENDIENTES.md) |
| Ejecutar como dev | [`INICIAR_AGENTE.md`](INICIAR_AGENTE.md) + handoffs en `docs/handoffs-v1.5.md` |
| Auditar como revisor | [`INICIAR_REVIEWER.md`](INICIAR_REVIEWER.md) |
| Defender Maestría | `docs/entregable/E1..E5` |
| Ver decisiones técnicas | `docs/decisions/` |
| Ver el audit forensic del 2026-05-31 | `docs/audit/F7-AUDIT.md` |
| Setup técnico de infra | `infra/*.md` |

---

## Lo que aprendimos (la lista honesta)

Cosas que mejoraron al equipo y van como advertencia para V2:

1. **El cuadre trivial te miente.** F2-V3 y F3-V6 pasaron verdes con 0% diff porque las queries comparaban subsets reducidos por el propio bug. → Test paridad SIEMPRE contra row count total + suma agregada.
2. **MAPE en demanda intermitente es inválido.** F4-B reportaba Prophet MAPE 3,540% — era división por cero, no modelo malo. → ADR-0017 fijó split temporal + WAPE.
3. **Data leakage destruye la evaluación.** F4-B Classifier F1=0.99 era leak (stock_actual era feature Y definía el target). → Ahora F1=0.54 honesto.
4. **FakeRepos en producción es trampa.** F4-C cerró con repos mock; F4-FIX1 los reemplazó por Real validados.
5. **El revisor + ejecutor mismo agente pierde adversarialidad.** Por eso introdujimos auditorías con contexto fresco.
6. **El dataset es lo que es.** 6,185 SKUs en cola larga → Prophet/LightGBM no superan baseline. → ADR-0020 agregación por categoría.
7. **Vendor lock-in en Free tier es ilusión.** Databricks Free perdió Serverless de un día para otro. → V1.5 migra a DuckDB self-hosted.
8. **Commits "feat: X funcionando" sin curl evidence son fraude operativo.** F7 cerró 31 commits sin verificar producción. → Regla nueva: curl + output en cada commit.

---

## Entregables académicos (Maestría UAO 2025-2)

| ID | Título | Estado |
|----|--------|--------|
| **E1** | Diagnóstico + Arquitectura | ✅ Listo |
| **E2** | Pipeline operativo | ✅ Listo (revisión V1.5 pendiente) |
| **E3** | Producto descriptivo | ✅ Listo |
| **E4** | Producto predictivo | ✅ Listo |
| **E5** | Memoria final | ⬜ Pendiente cierre V1.5 |

Documentos en `docs/entregable/`.

---

## Links rápidos

| Qué | Dónde |
|-----|-------|
| Plan activo | [`docs/plan-v1.5-duckdb.md`](docs/plan-v1.5-duckdb.md) |
| Handoffs devs | [`docs/handoffs-v1.5.md`](docs/handoffs-v1.5.md) |
| Estado vivo | [`SEGUIMIENTO.md`](SEGUIMIENTO.md) |
| Pendientes humano | [`PENDIENTES.md`](PENDIENTES.md) |
| Índice maestro | [`docs/MASTER.md`](docs/MASTER.md) |
| **PWA producción** | [app.fragloesja.uk](https://app.fragloesja.uk) |
| **API producción** | [api.fragloesja.uk](https://api.fragloesja.uk) |
| Roadmap V2 | [`docs/roadmap-v2-produccion.md`](docs/roadmap-v2-produccion.md) |
| Audit F7 forensic | [`docs/audit/F7-AUDIT.md`](docs/audit/F7-AUDIT.md) |

---

*Última actualización: 2026-05-31 · V1.5 plan aprobado, ejecución pendiente de kickoff.*
