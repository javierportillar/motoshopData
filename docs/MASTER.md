# MASTER · Índice maestro del proyecto MotoShop

> Entry point para revisar el proyecto end-to-end. Si abrís este archivo, vas a poder navegar a cualquier parte del proyecto sin tener que cazar archivos.
> Última actualización: 2026-05-31 (Sesión 66 · V1.5 migración).

---

## 1 · Estado global hoy

| Campo | Valor |
|-------|-------|
| Fase activa | **V1.5 · Migración a DuckDB-first** |
| Inicio del proyecto | 2026-05-27 |
| Próximo gate | Sprint 0 spike de validación (DuckDBMetricsRepo con 1 endpoint) |
| Avance global | F0-F7 backend cerrado · App productiva caída por revocación Databricks Serverless · V1.5 plan aprobado |
| ADRs aceptados | 22 (0023 pendiente cierre Sprint 4) |
| Riesgos vivos | RV1-RV7 documentados en `docs/plan-v1.5-duckdb.md` §6 |

```
F0 ✅  F1 ✅ (+F1.5 +F1.9)  F2 ✅  F3 ✅ (+F3.5 +F3.6)  F4 ✅ (+FIX1)  F5 ✅ (+FIX1)  F6 ✅  F7 ✅
─────────────────────────────────────────────────────────────────────────
V1.5 🟡 Sostenibilidad DuckDB — Sprints 0-4 cerrados, Sprint 5 EN CURSO (búsqueda híbrida)
─────────────────────────────────────────────────────────────────────────
V1.6 ⬜ IA aplicada — Sprints A (briefing Telegram) → B (narrativa forecast) → C (Q&A chat)
   └── Trigger: V1.5 Sprint 5 cerrado
─────────────────────────────────────────────────────────────────────────
V1.7 ⬜ Pipeline observability — Página /admin/pipeline nativa en PWA
   └── Trigger: V1.6 Sprint A en producción 7 días sin falla
─────────────────────────────────────────────────────────────────────────
V2   ⬜ Producción seria — docs/roadmap-v2-produccion.md
```

**Documento canónico de plan activo:** [`docs/plan-v1.5-duckdb.md`](plan-v1.5-duckdb.md) — arquitectura, sprints, riesgos, DoD.

**Próximos planes aprobados:**
- [`docs/plan-v1.6-llm.md`](plan-v1.6-llm.md) — capa de IA (briefing gerente, forecast narrativa, Q&A chat)
- [`docs/plan-v1.7-observability.md`](plan-v1.7-observability.md) — pipeline jobs UI nativa en PWA
- [`docs/plan-multi-tenant.md`](plan-multi-tenant.md) — **MT** plataforma multi-tenant (MotoShop + MasVital + futuros) en sprints M1-M4

**Handoffs de devs:** [`docs/handoffs-v1.5.md`](handoffs-v1.5.md) — briefs listos para pegar en chat de Dev D y Dev F. Handoff V1.6 (Dev L) se genera al activarse.

**Audit forensic 2026-05-31:** [`docs/audit/F7-AUDIT.md`](audit/F7-AUDIT.md) — 26 bugs catalogados, root causes confirmados via SQL directo.

**Documento canónico de tracking:** [`SEGUIMIENTO.md`](../SEGUIMIENTO.md) — bitácora viva por sesión + tablero de riesgos.

**Doc canónico anterior (DEPRECATED):** ~~`docs/plan-cierre-v1-reviewer.md`~~ — reemplazado por V1.5 cuando Databricks revocó Serverless.

---

## 2 · Fases en una línea cada una

| Fase | Estado | Qué entregó (1 línea) |
|------|--------|-----------------------|
| **F0 · Cimientos** | ✅ | Workspace Databricks, catálogo `motoshop`, usuarios MySQL `analytics`/`api_read`, túnel Cloudflare, hello world MySQL→UC Volume→Delta. |
| **F1 · Bronze + API + PWA scaffold** | ✅ (vía F1-FIX1+FIX2) | Pipeline diario MySQL→Bronze idempotente (12 tablas), FastAPI con `/auth`, `/products`, `/stock`, `/sales/recent` desde MySQL, PWA Next.js scaffold con login JWT. |
| **F1.5 · Hardening pre-F2** | ✅ | INICIAR_AGENTE/REVIEWER, CI smoke, evidencia consolidada de F1. |
| **F1.9 · Pipeline resiliente** | ✅ | Task Scheduler cada 30 min (07:00-19:30), retry + catch-up flag, `/health/data-freshness`, R5 mitigada. |
| **F2 · Silver + PWA MVP** | ✅ (vía F2-FIX1) | 5 dimensions + 5 facts en silver con `business_date` derivada (ADR-0013), PWA con search/ficha SKU/stock, refresh token, idb-keyval cache. |
| **F3 · Gold + Dashboards** | ✅ | 5 marts gold (ventas, inventario, ABC, cohortes, dormidos), workflow Databricks UNPAUSED cron 02:30 COL, 4 dashboards PWA con recharts, 5 endpoints `/metrics/*`. |
| **F3.5 · Hardening Silver** | ✅ | Fix `estfven/estcom` recuperó 6,324 facturas perdidas (15→6,339), V3 rediseñada para universo completo, regla CRITICAL `silver_completeness`. |
| **F3.6 · Fix quality gold** | ✅ | Sentinel `-1 → 99999` para productos nunca vendidos, regla `negative_dias_sin_venta` ajustada. |
| **F4-A · Feature store + Baseline + MLflow** | ✅ | Feature store con lag/rolling/calendar (4,392 SKUs), baseline naïve, MLflow tracking. Baseline confirmado como champion 97.9% post-FIX1. |
| **F4-B · Prophet + LightGBM + Classifier** | ✅ (con conclusión honesta) | 3 modelos entrenados. Métricas finales auditadas: Prophet WAPE 864% / LightGBM 57% / Baseline 45.83%. Classifier F1 0.536 (sin leakage). Modelos ML NO superan baseline — conclusión académica documentada. |
| **F4-C · API forecast + PWA + push** | ✅ | Endpoints `/forecast/*` + `/alerts/*` con Real repos verificados contra Databricks SQL. PWA pages + StaleDataBanner + push sender. |
| **F4-FIX1 · Remediación auditoría F4** | ✅ | 8/8 V-FIX1 PASS. R11/R12/R13 cerrados. R14 (remover Prophet/LightGBM en F5) + R15 (users.yaml diferido F6) abiertos. ADR-0017 Accepted. Plan [docs/plan-f4-fix1.md](plan-f4-fix1.md). |
| **F5 · Operación bidireccional** | ⬜ | App tables InnoDB, escritura PWA→sgHermes vía staging tables. |
| **F6 · Hardening + entrega** | 🟡 | Tunnel revive, notebooks upload, workflow UNPAUSED, PWA Vercel deploy, CORS fijo, diagnosis alerts/forecast (warehouse start + vars Databricks). Descubrimiento crítico: Windows = SPOF (API offline si PC se apaga). Demo 4G funcional con PC encendida. |

---

## 3 · Docs vivos (los que se editan en cada sesión)

| Archivo | Para qué sirve | Cuándo lo abro |
|---------|---------------|----------------|
| [`SEGUIMIENTO.md`](../SEGUIMIENTO.md) | Bitácora viva: cabecera + decisiones + checklist por fase + tablero riesgos + notas de sesión | Para entender qué pasó y qué pasa ahora |
| [`PENDIENTES.md`](../PENDIENTES.md) | Tareas humanas + handoffs Dev/Revisor entre sesiones | Para saber qué tengo que hacer yo o qué ejecutan los devs |
| [`docs/contexto-proyecto.md`](contexto-proyecto.md) | Snapshot ejecutivo: arquitectura + entregables + riesgos + resumen | Para onboarding rápido al proyecto |
| [`docs/plan-cierre-v1-reviewer.md`](plan-cierre-v1-reviewer.md) | **Plan activo de cierre V1: handoffs, gates y GO/NO-GO** | Para coordinar devs y cerrar el proyecto sin aceptar humo |
| [`docs/plan-f4-fix1.md`](plan-f4-fix1.md) | Plan de la fase activa (F4-FIX1) | Mientras esté abierta |
| [`docs/roadmap-v2-produccion.md`](roadmap-v2-produccion.md) | **⭐ CORE · V2 producción seria · deudas técnicas y cómo se cierran** | Para visión de mediano plazo post-V1.7, kick-off V2 |
| [`docs/MASTER.md`](MASTER.md) | Este archivo — índice de navegación | Como entry point cuando volvés después de tiempo |

---

## 4 · Docs de rol (cuando abrís un chat nuevo)

| Archivo | Para qué rol | Para qué sirve |
|---------|-------------|----------------|
| [`INICIAR_AGENTE.md`](../INICIAR_AGENTE.md) | Dev Agent (Track A o Track T) | Bootstrap del rol ejecutor: lecturas obligatorias, reglas, commits, evidencia |
| [`INICIAR_REVIEWER.md`](../INICIAR_REVIEWER.md) | Reviewer Agent | Bootstrap del rol auditor: los 9 checks (DoD, cuadre, tests, secretos, **silver↔bronze**, **sniff test ML**, **Real vs Fake repos**, propagación lecciones), veredictos GO/NO-GO |

---

## 5 · ADRs (decisiones técnicas)

[`docs/decisions/`](decisions/) · 16 ADRs aceptados.

| # | Fecha | Decisión |
|---|-------|----------|
| [0001](decisions/0001-medallion-architecture.md) | 2026-05-27 | Medallion estándar bronze→silver→gold |
| [0002](decisions/0002-frontend-read-only-f1-f4.md) | 2026-05-27 | Frontend solo lectura en F1-F4 |
| [0003](decisions/0003-pwa-nextjs.md) | 2026-05-27 | PWA con Next.js (no app nativa) |
| [0004](decisions/0004-innodb-app-tables-f5.md) | 2026-05-27 | Tablas `app_*` en InnoDB cuando llegue F5 |
| [0005](decisions/0005-databricks-mysql-connectivity.md) | 2026-05-27 | Conectividad self-hosted dump → UC Volume |
| [0006](decisions/0006-remote-tunnel.md) | 2026-05-27 | Cloudflare Tunnel |
| [0007](decisions/0007-api-hosting.md) | 2026-05-27 | API hosteada en PC local |
| [0008](decisions/0008-auth-provider.md) | 2026-05-27 | JWT + bcrypt propio (no OAuth) |
| [0009](decisions/0009-monorepo-vs-two-repos.md) | 2026-05-27 | Monorepo provisional |
| [0010](decisions/0010-compute-databricks-free.md) | 2026-05-28 | Free Edition + SQL Warehouse serverless |
| [0011](decisions/0011-stack-f1.md) | 2026-05-28 | Stack F1 (10 DT) |
| [0012](decisions/0012-stack-f2.md) | (superseded por 0014) | — |
| [0013](decisions/0013-fecha-tecnica-vs-negocio.md) | 2026-05-29 | `ingest_date` técnica + `business_date` derivada en silver |
| [0014](decisions/0014-stack-f2.md) | 2026-05-29 | Stack F2 (16 DT) |
| [0015](decisions/0015-stack-f3.md) | 2026-05-29 | Stack F3 (12 DT, Databricks SQL resuelve P5) |
| [0016](decisions/0016-stack-f4.md) | 2026-05-30 | Stack F4 (MLflow, Prophet, LightGBM, classifier) |
| **0017** _(pendiente)_ | 2026-05-30 | Split temporal + métricas forecasting demanda intermitente (cierre F4-FIX1) |

---

## 6 · Riesgos vivos (Tablero)

Resumen — detalle en [`SEGUIMIENTO.md`](../SEGUIMIENTO.md) §Tablero y [`docs/contexto-proyecto.md`](contexto-proyecto.md) §10.

| ID | Riesgo | Estado | Trigger |
|----|--------|--------|---------|
| **R1** | Passwords MySQL en historial Git | 🟡 Aceptada (decisión humana) | MySQL pasa a `@%`/expuesto |
| **R2** | Credenciales API `FG28` en README | 🟡 Aceptada (decisión humana) | Red más expuesta / escritura |
| **R4** | Workflow Databricks postergado | 🟡 Aceptada | PC se rompe / compute migra |
| **R5** | Pipeline pre-internet-estable | 🟡 Mitigada con F1.9 | lag > 24h por 3 días |
| **R6** | Hito demo 4G no capturado | 🟡 Diferida a F6 | E3/E5 se acerca |
| **R7** | V3 workflow 7 corridas pendiente | 🟡 Diferida a F6 | F6 kickoff o falla 3 noches |
| **R8** | V5 demo a gerencia pendiente | 🟡 Diferida a F6 | F6 kickoff o E3 |
| **R11** | Métricas ML F4-B no auditadas | ✅ Resuelto F4-FIX1 | — |
| **R12** | F4-C con FakeRepos en prod | ✅ Resuelto F4-FIX1 | — |
| **R13** | R10 sin alerta al usuario en PWA | ✅ Resuelto F4-FIX1 | — |
| **R14** | Prophet/LightGBM en pipeline inservibles | 🟡 Diferido F5 | Kickoff F5 — remover scripts |
| **R15** | `users.yaml` con FG28 propagada (gitignored pero force-added) | 🟡 Diferido F6 | F6 hardening — rotación + cleanup |
| **R16** | Windows SPOF: API offline si PC se apaga | 🔴 Descubierto en F6 | F7 — migrar API a Render/VPS |

---

## 7 · Archivo histórico

[`docs/archive/`](archive/) · planes cerrados, handoffs históricos, reportes puntuales. Útiles como audit trail. NO se actualizan.

| Categoría | Archivos |
|-----------|----------|
| Planes históricos | `plan-f1.md`, `plan-f1-fix1.md`, `plan-f1-fix2.md`, `plan-f1-hardening.md`, `plan-f1-9.md`, `plan-f2.md`, `plan-f2-fix1.md`, `plan-f3.md`, `plan-f3-5.md`, `plan-f4.md`, `plan-f4-b.md` |
| Handoffs | `handoff-f1.md`, `handoff-f2.md` |
| Prompts F4-B | `prompt-dev-a-f4b.md`, `prompt-dev-b-f4b.md` |
| Reports F3 | `gold/auditoria-f3.md`, `gold/cierre-f3.md`, `gold/refresh_plan.md` |
| Reports F4 | `v6_forecast_match.md` |
| Bootstrap legacy | `AGENT_PROMPT.md` (reemplazado por INICIAR_AGENTE.md) |

---

## 8 · Setup técnico (infra/)

[`infra/`](../infra/) · scripts + docs de setup técnico.

| Archivo | Para qué |
|---------|----------|
| [`infra/infollm.md`](../infra/infollm.md) | Guía de conexión MySQL (host, puerto, driver, JDBC URI, SQLAlchemy) |
| [`infra/rotate_mysql_passwords.md`](../infra/rotate_mysql_passwords.md) | Procedimiento de rotación de passwords MySQL |
| [`infra/setup_cloudflare_tunnel.md`](../infra/setup_cloudflare_tunnel.md) | Setup túnel Cloudflare |
| [`infra/setup_sql_warehouse.md`](../infra/setup_sql_warehouse.md) | Setup SQL Warehouse Databricks |
| [`infra/setup_uc_volume.md`](../infra/setup_uc_volume.md) | Setup UC Volume Databricks |

---

## 9 · Cómo navegar según para qué venís

| Vengo a... | Empiezo por |
|------------|-------------|
| Entender el proyecto en 5 minutos | `README.md` → `docs/contexto-proyecto.md` |
| Saber qué pasa ahora | `SEGUIMIENTO.md` cabecera + última nota |
| Saber qué tengo que hacer yo | `PENDIENTES.md` |
| Auditar la fase activa | `INICIAR_REVIEWER.md` + `docs/plan-f4-fix1.md` |
| Ejecutar como dev | `INICIAR_AGENTE.md` + `docs/plan-f4-fix1.md` §8 (handoffs) |
| Onboardear a un nuevo dev | `README.md` → `docs/contexto-proyecto.md` → `INICIAR_AGENTE.md` |
| Ver el audit trail completo | `docs/archive/` + `SEGUIMIENTO.md` §Notas de sesión |
| Conectarme a la BD | `infra/infollm.md` |
| Ver decisiones técnicas | `docs/decisions/` o §5 de este archivo |
