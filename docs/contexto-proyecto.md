# Contexto del Proyecto MotoShop · Snapshot 2026-05-29

> **Para qué sirve este documento.** Capturar en un solo archivo todo lo que se ha hecho desde el inicio hasta hoy, el pipeline operativo actual, los archivos clave y el estado de cada deuda. Es el "estado del arte" del proyecto al cierre de Fase 1. Útil para retomar contexto, presentar al curso, o hacer auditoría externa.
>
> No reemplaza a `PLAN.md` (visión y arquitectura), `SEGUIMIENTO.md` (bitácora viva) ni `PENDIENTES.md` (tareas humanas). Los referencia.

---

## 1 · Punto de inicio (2026-05-27)

### 1.1 Realidad operativa de MotoShop

| Dimensión | Estado |
|-----------|--------|
| Negocio | Tienda de repuestos de moto. Opera con sgHermes (ERP colombiano). |
| Base de datos | **MySQL 5.0**, `motoshop2024`, ~179 tablas, motor **MyISAM** (sin transacciones ni FKs). |
| Infraestructura | **Un solo PC Windows** corriendo MySQL + sgHermes. Sin réplicas ni backups automáticos. |
| Acceso al dato | Solo desde la pantalla del PC. Sin acceso remoto. |
| Toma de decisiones | Intuición y experiencia. Cero analítica avanzada. |
| Madurez digital | Arquetipo **"Principiante"** según diagnóstico Forrester/McKinsey/MIT-Capgemini. |

### 1.2 Punto de partida del repositorio

Al iniciar (2026-05-27, antes del primer commit propio), el repo tenía:

- `PLAN.md` v1 (sketch inicial).
- `infollm.md` (guía de conexión a MySQL).
- `README.md` mínimo.
- `.gitignore` básico.
- Una captura `.heic`.

**Sin código. Sin pipeline. Sin tests. Sin notebooks. Sin CI. Sin docs estructuradas.**

### 1.3 Marco académico

Aplicación práctica del curso **Big Data y Transformación Digital del Negocio**, Maestría IA & Ciencia de Datos, UAO 2025-2.

- **Módulo 2** — Criterios técnicos y stack (escalabilidad, latencia, gobernanza, etc.).
- **Módulo 3** — Decisión crítica + modelo ML (predicción de demanda + alertas de quiebre).
- **Módulo 4** — Diagnóstico de madurez + VPC + BMC.

Entregables académicos esperados (PLAN.md §10):

| ID | Contenido | Fase de cierre |
|----|-----------|-----------------|
| **E1** | Diagnóstico + arquitectura | Fin F0 ✅ |
| **E2** | Pipeline operativo (bronze + silver) | Fin F2 |
| **E3** | Producto descriptivo (PWA + dashboard) | Fin F3 |
| **E4** | Producto predictivo (ML + alertas) | Fin F4 |
| **E5** | Memoria final | Cierre |

---

## 2 · Meta global

> Llevar a MotoShop de un negocio que **registra datos** a uno que **decide con datos y opera desde cualquier lugar**.

Cuatro saltos analíticos en el horizonte:

```
Descriptiva     →     Diagnóstica     →     Predictiva     →     Prospectiva
¿Qué pasó?            ¿Por qué pasó?         ¿Qué va a pasar?      ¿Qué debería pasar?
   F3                    F3                     F4                    F6
```

Dos tracks paralelos:

- **Track A · Analítico** — Databricks Lakehouse medallion (Bronze → Silver → Gold) + ML.
- **Track T · Transaccional** — FastAPI + PWA Next.js para consulta remota.

Sin reemplazar sgHermes: la BD operativa sigue siendo la fuente de verdad; nosotros copiamos, no escribimos (excepto en F5+ en tablas `app_*` separadas).

---

## 3 · Arquitectura objetivo

```
                    PC MotoShop (Windows)
                    ┌─────────────────────────────┐
                    │  MySQL 5.0 motoshop2024     │
                    │  • sgHermes lee/escribe     │
                    │  • [F5+] tablas InnoDB app  │
                    └──────────┬──────────────────┘
                               │ (usuarios read-only)
                ┌──────────────┼──────────────┐
                │ analytics    │ api_read     │
                ▼              │              ▼
   ┌──────────────────────┐   │   ┌───────────────────────┐
   │  TRACK A · DATABRICKS│   │   │   TRACK T · API + PWA │
   │                      │   │   │                       │
   │  Bronze→Silver→Gold  │   │   │   FastAPI (PC)        │
   │  + Unity Catalog     │   │   │   ↓ Cloudflare Tunnel │
   │  + Workflows         │   │   │   PWA Next.js (móvil) │
   │  + MLflow            │   │   │                       │
   └──────────────────────┘   │   └───────────────────────┘
              │                │
              ▼                ▼
   Power BI / Databricks SQL   Pendiente (F1 solo /demo)
```

---

## 4 · Stack tecnológico actual

| Capa | Tecnología | Estado |
|------|------------|--------|
| Origen | MySQL 5.0 MyISAM (`motoshop2024`) | Operativo, intocable |
| Backup origen | `mysqldump` → `.sql.zip` (5 MB / 7 s) | Ejecutado 2026-05-27 |
| Extracción | Python 3.11 + `mysql-connector-python` + `pyarrow` | `infra/dump_to_cloud.py` |
| Cloud storage | **Databricks Unity Catalog Volume** `motoshop.bronze._landing` | Activo |
| Subida | `databricks-sdk` Files API | Activo |
| Lakehouse | **Databricks Free Edition** (Serverless SQL Warehouse + notebooks PySpark) | Activo |
| Catálogo | Unity Catalog `motoshop` con esquemas `bronze`, `silver`, `gold` | bronze ✅, silver/gold vacíos |
| Formato | **Delta Lake** particionado por `ingest_date` | Activo |
| Orquestación | **Windows Task Scheduler** c/30 min (07:00–19:30) con catch-up y retry | Activo (F1.9) |
| API | **FastAPI** + SQLAlchemy 2.0 core + pymysql | Operativa en PC |
| Auth | JWT (HS256, pyjwt) + bcrypt + login propio | Activo |
| Logging | structlog JSON + PII redaction + request_id | Activo |
| Rate limit | slowapi in-memory (10/min login, 60/min lectura) | Activo |
| Exposición | **Cloudflare Tunnel** → `https://api.fragloesja.uk` | Activo |
| Frontend | Next.js 14 App Router + TypeScript | Scaffold (sin features de F2 todavía) |
| Tests | pytest + FakeRepos + `pytest-cov` | 23 passing, 79% cobertura |
| Versionado | Git + GitHub público | [github.com/javierportillar/motoshopData](https://github.com/javierportillar/motoshopData) |

---

## 5 · Pipeline operativo end-to-end (a hoy)

### 5.1 Diagrama de flujo

```
┌─────────────────┐
│ Task Scheduler  │  c/30 min 07:00-19:30 COL, catch-up + retry
│ (Windows)       │
└────────┬────────┘
         ▼
┌─────────────────────────────────────────┐
│ infra/run_dump.ps1                      │  wrapper PowerShell
└────────┬────────────────────────────────┘
         ▼
┌─────────────────────────────────────────┐
│ infra/dump_to_cloud.py                  │  Python local
│  • SELECT * FROM <tabla> (con filtros)  │
│  • estdoc='A' si la columna existe      │
│  • _staging/<tabla>/ingest_date=YYYY-MM-DD/part-0.parquet
└────────┬────────────────────────────────┘
         ▼
┌─────────────────────────────────────────┐
│ Databricks SDK · upload_to_volume       │
│  → /Volumes/motoshop/bronze/_landing/   │
│    <tabla>/ingest_date=YYYY-MM-DD/      │
│    part-0.parquet                       │
│  + /Volumes/.../_manifests/             │
│    manifest_YYYY-MM-DD.json             │
└────────┬────────────────────────────────┘
         ▼
┌─────────────────────────────────────────┐
│ notebooks/bronze/02_ingest_all_bronze.py│  PySpark serverless
│  • INSERT INTO motoshop.bronze.<tabla>  │
│    REPLACE WHERE ingest_date='...'      │
│    SELECT *, '...' AS ingest_date       │
│    FROM parquet.`/Volumes/.../...`      │
│  • Idempotente por día                  │
└────────┬────────────────────────────────┘
         ▼
┌─────────────────────────────────────────┐
│ notebooks/bronze/03_validate_counts.py  │
│  • Lee manifest desde Volume            │
│  • Compara rows manifest vs bronze      │
│  • Falla si hay mismatch                │
└─────────────────────────────────────────┘

Camino paralelo (solo cuando se valida F1):
04_check_large_tables.py  → V6 paginación
05_schema_drift.py        → V7 schema estable
```

```
┌──────────────────┐
│ Vendedor en 4G   │  POST /auth/login → JWT
└────────┬─────────┘
         ▼
┌──────────────────────────────────────────┐
│ https://api.fragloesja.uk/...            │
│  ↓ Cloudflare Tunnel                     │
└────────┬─────────────────────────────────┘
         ▼
┌──────────────────────────────────────────┐
│ FastAPI (PC, puerto 8000)                │
│  • Rate limit (10/60 req/min)            │
│  • JWT Bearer + roles                    │
│  • structlog request_id + PII redaction  │
└────────┬─────────────────────────────────┘
         ▼
┌──────────────────────────────────────────┐
│ SQLAlchemy 2.0 core (user api_read)      │
│  • GET /products?q=...                   │
│  • GET /products/{sku}/stock             │
│  • GET /sales/recent?since=...           │
└────────┬─────────────────────────────────┘
         ▼
┌──────────────────────────────────────────┐
│ MySQL 5.0 motoshop2024  (localhost:3306) │
└──────────────────────────────────────────┘
```

### 5.2 Periodicidad y volúmenes reales

| Pieza | Frecuencia | Duración real | Volumen |
|-------|------------|----------------|---------|
| Dump local de las 12 tablas | c/30 min (07:00–19:30) + catch-up | 30-37 s | ~80k filas, ~6 MB Parquet |
| Subida UC Volume | c/30 min (07:00–19:30) | <5 s | 12 Parquets + 1 manifest |
| Ingesta Bronze (Databricks) | A demanda (no automatizado todavía) | 1-2 min | 12 Delta tables |
| Validación V1 (conteos) | A demanda | <1 min | 12 comparaciones |
| API `/health` | Por request | ~5 ms p95 | — |
| API `/products/{sku}/stock` | Por request | Endpoint pre-cache: 781 ms p95. Repo cold con cache: 8.9 ms. Warm: 0.0 ms. Endpoint p95 con cache no re-medido — pendiente para F2 con PWA real. | — |

---

## 6 · Cronología resumida (Fase 0 + Fase 1)

### 6.1 Fase 0 · Cimientos (2026-05-27 / 2026-05-28)

**Sesiones 1–9.** Objetivo: plataforma lista, sin tocar dato real.

| Sesión | Hito |
|--------|------|
| 1 | Andamiaje del repo: monorepo, scaffolds FastAPI + Next.js, `.gitignore` reforzado. |
| 2 | Bitácora ADR (D1–D9). 9 ADRs aceptados o propuestos. |
| 3 | Backup MySQL (5 MB, 7 s) + usuarios `analytics` / `api_read` / `javier`. |
| 4 | Scaffolds probados: FastAPI `/health` + Next.js build OK. |
| 5 | Cloudflare Tunnel operativo desde 4G. ❌ Primer cierre F0 (auditoría detectó issues). |
| 6 | Auditoría F0 + remediación: ADR-0010 (compute Free Edition), `dump_to_cloud.py`, scripts reproducibles. |
| 7 | Rotación passwords MySQL `123450 → Sashita123` (con leak en commit message → R1). |
| 8 | Nueva remediación tras detectar smoke test con 0 filas. |
| 9 | **F0 cerrada definitivo:** smoke test honesto con `bodegas` (1) y `formapago` (20). |

**Resultado F0:**

- Workspace Databricks creado: `dbc-e311b140-dab8.cloud.databricks.com`.
- Catálogo `motoshop` con esquemas `bronze`, `silver`, `gold`.
- UC Volume `motoshop.bronze._landing` creado vía SDK.
- SQL Warehouse Serverless Starter con auto-stop 10 min.
- Cloudflare Tunnel `motoshop-api` → `api.fragloesja.uk`.
- 3 usuarios MySQL read-only.
- 9 ADRs en bitácora.
- **R1 documentada:** passwords MySQL en historial (acotada a `@localhost`).

### 6.2 Fase 1 · Ingesta + API (2026-05-28, 8 sesiones)

**Sesiones 10–17.** Objetivo: 12 tablas a bronze + 3 endpoints de lectura + login en celular.

| Sesión | Hito |
|--------|------|
| 10 | Plan detallado F1 (3 sprints F1-A/B/C) + ADR-0011 propuesto (DT-1..DT-10). |
| 11 | ADR-0011 aceptado en bloque + handoff doc para el ejecutor. |
| 12 | Implementación F1 por el ejecutor: bronze + auth + 3 endpoints. Cierre prematuro. |
| 13 | Automatización Task Scheduler + demo page + scripts disponibilidad. |
| 14 | **Auditoría revisor: 🔴 NO-GO a F2.** 5 críticos (stock=0, tests 500, V6/V7 relleno, FG28 README), 5 serios, 3 KPIs sin medir. Plan F1-FIX1. |
| 15 | F1-FIX1 ejecutado: 11/13 ítems resueltos. |
| 16 | Auditoría F1-FIX1: faltaban 3 evidencias + sync SEGUIMIENTO. Plan F1-FIX2. R2 (FG28) reclasificada como deuda extendida indefinida por decisión humana. |
| 17 | F1-FIX2 ejecutado: V6/V7/C-1 archivadas. **Revisor: 🟢 GO a F2.** |
| 18 | Plan F1.5 Hardening pre-F2 escrito: R3 kill-y-retry + R-X2 cache + sync docs. |
| 19 | **F1.5 ejecutado:** R3 kill-y-retry cerrada, R-X2 cache implementado (warm p95 < 50 ms). |

**Resultado F1:**

- 12 tablas core en Bronze, **79,132 filas** totales, particionadas por `ingest_date`.
- 5 endpoints API funcionales (`/health`, `/demo`, `/auth/login`, `/auth/refresh`, `/products`, `/products/{sku}/stock`, `/sales/recent`).
- 23 tests passing, **79% cobertura** (89-90% por módulo de negocio).
- Dump: 5 corridas seguidas exitosas (30-37 s c/u).
- Validaciones: V6 paginación OK, V7 schema drift OK (28 vs 29), V1 conteos OK 12/12.
- Login desde 4G en celular: funcional.
- Stock real desde `auxinventario`: `MOTS1297` API=691 == SQL=691.
- ADR-0011 (stack F1) aceptado.
- 4 deudas adicionales documentadas: **R2** (FG28 en README, extendida), **R3** (idempotencia kill-y-retry → **resuelta Sesión 19**), **R4** (Workflow Databricks eliminado), **R-X2** (latencia /stock → **resuelta Sesión 19** con cache).

---

## 7 · Resultado por verificaciones críticas

### 7.1 Fase 0 (6 verificaciones)

| # | Verificación | Estado | Evidencia |
|---|--------------|--------|-----------|
| 1 | Usuario read-only realmente read-only | ✅ | INSERT denied para los 3 usuarios |
| 2 | Túnel funciona desde red distinta | ✅ | 4G celular → `/health` 200 OK |
| 3 | Conectividad Databricks → MySQL end-to-end | ✅ | dump → Volume → bronze con `bodegas`+`formapago` N>0 |
| 4 | Cluster se apaga solo | ✅ | SQL Warehouse Serverless auto-stop 10 min |
| 5 | Credenciales fuera de Git | ⚠️ | R1 deuda residual aceptada (`@localhost`) |
| 6 | Backup MySQL | ✅ | `mysqldump` 5 MB / 7 s |

### 7.2 Fase 1 (7 verificaciones)

| # | Verificación | Estado | Evidencia |
|---|--------------|--------|-----------|
| 1 | Conteos coinciden bronze == origen | ✅ | `_runs/full_run_2026-05-28.md` |
| 2 | Ingesta es idempotente | ⚠️ | "2 runs limpios" OK; kill-y-retry no probado → R3 |
| 3 | API rechaza tokens vencidos | ✅ | `test_auth_expired_token` |
| 4 | API rechaza credenciales malas sin filtrar | ✅ | Dummy bcrypt timing-safe + `test_login_timing_is_similar` |
| 5 | Logs no exponen datos sensibles | ✅ | structlog `redact_pii` + 2 tests |
| 6 | Paginación funciona en tablas grandes | ✅ | `_runs/v6_pagination_2026-05-28.md` (27,747 + 11,623 OK) |
| 7 | Esquema bronze estable entre corridas | ✅ | `_runs/v7_drift_2026-05-28.md` (28 vs 29, 12/12 OK) |

### 7.3 KPIs F1 medidos

| KPI | Meta | Real | Estado |
|-----|------|------|--------|
| Tiempo ingesta diaria total | < 30 min | 30-37 s en 5 corridas | ✅ |
| Latencia `/products/{sku}/stock` p95 | < 500 ms | Pre-cache (S17): 781 ms endpoint. Post-cache (S19): cold 8.9 ms / warm 0.0 ms repo-level. | 🟡 Cache implementado; endpoint p95 a re-medir con PWA real en F2. |
| Tasa éxito ingesta | 100% en 5 corridas | 5/5 | ✅ |
| Cobertura tests `auth/`+`products/` | > 70% | 79% global, 89-90% por módulo | ✅ |

---

## 8 · Inventario del repo a hoy

```
121 archivos versionados · 39 commits · 12 ADRs · 22 notebooks · 27 archivos código API · 8 tests · 19 scripts infra
```

### 8.1 Documentación raíz

| Archivo | Rol |
|---------|-----|
| `README.md` | Entrada principal + tabla de docs |
| `PLAN.md` | Fuente de verdad (arquitectura, fases, KPIs, VPC/BMC) |
| `SEGUIMIENTO.md` | Bitácora viva (estado, decisiones, verificaciones, KPIs, riesgos, notas de sesión) |
| `PENDIENTES.md` | Tareas humanas entre sesiones (historial por sesión) |
| `AGENT_PROMPT.md` | Briefing del agente IA |
| `infollm.md` | Conexión MySQL + esquema general |

### 8.2 `docs/`

| Archivo | Rol |
|---------|-----|
| `contexto-proyecto.md` | Este documento. Snapshot 2026-05-28. |
| `plan-f1.md` | Plan operativo de F1 (3 sprints, archivos, V1–V7, KPIs, riesgos). |
| `plan-f1-fix1.md` | Remediación tras auditoría sesión 14 (resolvió 11/13). |
| `plan-f1-fix2.md` | Cierre limpio (3 evidencias + sync). |
| `handoff-f1.md` | Punto de entrada para el ejecutor de F1. |
| `decisions/README.md` | Índice de ADRs. |
| `decisions/0001-…0011-…` | 12 ADRs (ver tabla §9 abajo). |

### 8.3 Track A · Notebooks Databricks (`notebooks/bronze/`)

| Notebook | Rol | Estado |
|----------|-----|--------|
| `01_ingest_smoke_test.py` / `.sql` | Smoke test F0 (sucursales / bodegas) | ✅ usado en F0 |
| `02_ingest_all_bronze.py` / `.sql` | Ingesta canónica de las 12 tablas (INSERT REPLACE WHERE) | ✅ producción |
| `03_validate_counts.py` / `.sql` | Compara manifest vs bronze | ✅ |
| `04_check_large_tables.py` | Paginación real (row_number + chunks + union) | ✅ tras F1-FIX1 |
| `05_schema_drift.py` | Compara esquemas entre 2 `ingest_date`s | ✅ tras F1-FIX1 |
| `_runs/full_run_2026-05-28.md` | Conteos por tabla (V1) | Evidencia |
| `_runs/idempotency_test_2026-05-28.md` | 2 runs limpios (V2 parcial) | Evidencia |
| `_runs/k3_five_runs_2026-05-28.md` | 5 corridas seguidas (KPI K-3) | Evidencia |
| `_runs/smoke_test_2026-05-28.md` | F0 smoke con bodegas/formapago | Evidencia |
| `_runs/v6_pagination_2026-05-28.md` | V6 paginación honesta | Evidencia |
| `_runs/v7_drift_2026-05-28.md` | V7 schema drift con 2 fechas distintas | Evidencia |

### 8.4 Track A · Scripts locales (`infra/`)

| Script | Rol |
|--------|-----|
| `dump_to_cloud.py` | Extractor MySQL → Parquet → UC Volume (con manifest) |
| `run_dump.ps1` | Wrapper Task Scheduler |
| `backup_mysql.{ps1,sh}` | mysqldump comprimido |
| `create_uc_volume.py` | Crea/verifica el UC Volume vía SDK |
| `create_sql_warehouse.py` | Crea/verifica el SQL Warehouse con auto-stop 10 min |
| `setup_uc_volume.md` / `setup_sql_warehouse.md` | Docs reproducibles |
| `test_mysql_connectivity.py` | Hello world MySQL |
| `hash_password.py` | CLI bcrypt |
| `requirements.txt` | Deps del entorno `.venv-infra` |
| `start_api.ps1` / `start_tunnel.ps1` / `start_motoshop.ps1` | Disponibilidad de la API |
| `check_health.ps1` + `check_health_wrapper.vbs` | Health check sin ventana |
| `setup_cloudflare_tunnel.md` / `rotate_mysql_passwords.md` | Runbooks |
| `create_users.sql.example` | Plantilla sin secretos |

### 8.5 Track T · API (`motoshop-app/api/src/motoshop_api/`)

| Módulo | Archivos | Rol |
|--------|----------|-----|
| `auth/` | `hash.py`, `jwt.py`, `users.py`, `deps.py`, `router.py`, `schemas.py`, `__init__.py` | Login JWT + refresh + roles + timing-safe |
| `db/` | `engine.py`, `tables.py`, `__init__.py` | SQLAlchemy core (`productos`, `bodegas`, `auxinventario`, `facventas`, `detfventas`, `terceros`, `sucursales`, `formapago`) |
| `products/` | `repo.py`, `router.py`, `schemas.py` | `GET /products?q=` + `FakeProductsRepo` |
| `stock/` | `repo.py`, `router.py`, `schemas.py` | `GET /products/{sku}/stock` (lee `auxinventario.valor3`) |
| `sales/` | `repo.py`, `router.py`, `schemas.py` | `GET /sales/recent?since=&limit=` |
| `logging.py` | structlog JSON + middleware request_id + PII redaction |
| `config.py` | pydantic-settings + validador JWT_SECRET |
| `main.py` | Wire-up FastAPI, lifespan carga `users.yaml` |
| `demo.html` | Página interactiva para celular |

### 8.6 Track T · Tests (`motoshop-app/api/tests/`)

| Test | Cubre |
|------|-------|
| `test_health.py` | `/health` |
| `test_auth_login.py` | login, password mala, missing fields, expired token, invalid token, refresh, timing-safe |
| `test_auth_logging.py` | PII redaction (password, token, authorization, email, nitter) |
| `test_products.py` | FakeProductsRepo: auth, list, search, paginación, limit > 200 → 422 |
| `test_stock.py` | FakeStockRepo: auth, 200 con datos, 404 not found |
| `test_sales.py` | FakeSalesRepo: auth, 200, limit |
| `conftest.py` | Fixtures `client`, `fake_users`, `admin_token`, `vendedor_token`, rate limiter reset |

### 8.7 Track T · Frontend (`motoshop-app/web/`)

Scaffold Next.js 14 App Router. Página vacía. Sin features de F2 todavía.

### 8.8 Evidencias API (`notebooks/api/_runs/`)

| Archivo | Rol |
|---------|-----|
| `c1_stock_real_2026-05-28.md` | MOTS1297: API 691 == SQL 691 |
| `k1_stock_latency_2026-05-28.json` | 100 requests, p95 = 781 ms |
| `k2_coverage_2026-05-28.md` | Cobertura por módulo |

---

## 9 · Decisiones técnicas registradas

12 ADRs en `docs/decisions/`. Todos `Accepted` salvo donde se indique.

| # | Decisión | Decisión final |
|---|----------|-----------------|
| 0001 | Arquitectura medallion bronze→silver→gold | Adoptado, sobre Delta Lake |
| 0002 | Frontend solo lectura F1–F4 | Sí. F5 abre escritura limitada |
| 0003 | PWA Next.js vs nativa | PWA |
| 0004 | Tablas `app_*` en InnoDB cuando llegue F5 | Sí |
| 0005 | Conectividad Databricks ↔ MySQL | Opción A: self-hosted dump → UC Volume |
| 0006 | Túnel remoto | Cloudflare Tunnel |
| 0007 | Hosting API | PC local (junto a MySQL) |
| 0008 | Auth provider | Login propio JWT + bcrypt |
| 0009 | Monorepo vs dos repos | Monorepo (revisable en F6) |
| 0010 | Compute Databricks Free | Extracción local + UC Volume + Serverless SQL |
| 0011 | Stack F1 (DT-1..DT-10) | SQLAlchemy core, pyjwt, slowapi, users.yaml, offset+limit, INSERT REPLACE WHERE, manifest al Volume, structlog, repos+integration mark, bronze raw → silver UTC → API UTC |

(Próximo: ADR-0012 con las decisiones técnicas de F2.)

---

## 10 · Riesgos vivos y deudas conscientes

Cada deuda tiene un **trigger de re-evaluación obligatoria**: si se cumple, se actúa.

| ID | Riesgo | Estado | Trigger |
|----|--------|--------|---------|
| **R1** | Passwords MySQL (`123450`, `Sashita123`) en historial Git | 🟡 Aceptado | (a) MySQL pasa a `@%` o `@<ip>`; (b) puerto 3306 expuesto por túnel; (c) réplica a BD cloud |
| **R2** | Credenciales API (`FG28`) en README y en historial | 🟡 **Deuda extendida** (decisión humana 2026-05-28) | (a) red más expuesta; (b) cualquier endpoint de escritura; (c) usuarios externos al equipo; (d) tráfico sospechoso en logs Cloudflare |
| **R3** | Idempotencia kill-y-retry no probada | ✅ **Resuelto** (Sesión 19) | Kill-y-retry validado: `r3_idempotency_kill_retry_2026-05-30.md`. 12 tablas con conteos == MySQL. |
| **R4** | Workflow Databricks postergado (corre en Task Scheduler) | 🟡 Aceptado | PC se rompe / se mueve compute a Databricks (F-F) / dependencias entre tablas requieren DAG |
| **R-X2** | Latencia `/stock` 781 ms > 500 ms | ✅ **Resuelto** (Sesión 19) | TTLCache(maxsize=200, ttl=300) implementado. Warm p95 < 50 ms. Evidencia: `r_x2_cache_2026-05-30.json`. |
| **R5** | Pipeline pre-internet-estable (PC apagado / sin internet / horario cambiante) | 🟡 **Mitigada con F1.9** (Sesión 22) | (a) lag > 24 h por 3 días seguidos; (b) Silver/Gold no cuadran con sgHermes por gap diario; (c) gerencia pide alerta proactiva push/email. Mitigaciones aplicadas: dump cada 30 min ventana 07:00–19:30, Task Scheduler con retry + catch-up, lag monitor `GET /health/data-freshness`. |
| **R6** | Hito demo 4G no capturado | 🟡 Aceptado · **diferida a F6 hardening** (decisión humana 2026-05-29) | (a) E3/E5 se acerca; (b) gerencia pide ver app antes de F6. Razón del diferimiento: dejar que el workflow acumule datos reales y la demo sea más representativa. |
| **R7** | V3 workflow gold 7 corridas seguidas pendiente | 🟡 Aceptado · **diferida a F6 hardening** (decisión humana 2026-05-29) | Schedule `0 30 2 * * ?` UNPAUSED; cierra sola en background. Trigger: F6 kickoff con ≥ 7 corridas en `system.workflows.runs`. Si tasa < 95% se debug antes; si falla 3 noches seguidas, alerta inmediata. |
| **R8** | V5 demo a gerencia pendiente | 🟡 Aceptado · **diferida a F6 hardening** (decisión humana 2026-05-29) | Trigger: (a) F6 kickoff; (b) entrega académica E3. Acción: humano agenda 30 min, captura feedback en `notebooks/gold/_runs/v5_stakeholder_demo.md`. |
| **R11** | Métricas ML F4-B no auditadas (Prophet MAPE 3540% + Classifier F1 0.9924) | 🔴 Abierta hasta cierre F4-FIX1 (Sesión 42) | Auditoría revisor fresco identificó modelo Prophet roto (probable división por cero en demanda intermitente) y classifier sospechoso de data leakage o desbalance no manejado. **Trigger automático:** cierre F4-FIX1 con V-FIX1-1 a V-FIX1-4 PASS. Plan: [docs/plan-f4-fix1.md](plan-f4-fix1.md). Hasta que cierre, F4-B/F4-C son 🟡 (no se debió cerrar verde). |
| **R12** | F4-C usó FakeRepos en prod en lugar de validar contra Gold real | 🔴 Abierta hasta cierre F4-FIX1 (Sesión 42) | Mismo patrón que R9 (silver universo incompleto en F3): tests cuadran trivialmente contra fakes. **Trigger automático:** cierre F4-FIX1 con V-FIX1-5 y V-FIX1-6 PASS. |
| **R13** | R10 mitigación insuficiente: PWA no alerta al usuario datos stale | 🟡 Mitigación pendiente en F4-FIX1 | "Documentar como stale en evidencia" no alerta al usuario operacional. **Trigger automático:** cierre F4-FIX1 con V-FIX1-7 PASS (StaleDataBanner activo con freshness > 24h). |

---

## 11 · Mapeo a entregables académicos

### 11.1 Módulo 2 · Criterios técnicos y stack

| Criterio | Cómo lo cumple el proyecto |
|----------|----------------------------|
| Escalabilidad | Lakehouse Databricks + cloud storage elástico |
| Flexibilidad | Medallion separa ingesta / almacén / proc / consumo |
| Baja latencia | Hoy batch diario (3x); streaming diferido a F-E |
| Tolerancia a fallos | Delta Lake (ACID, time-travel) + backup MySQL |
| Optimización de costo | Auto-stop SQL Warehouse 10 min, Free Edition |
| Seguridad y gobernanza | Unity Catalog + usuarios read-only + structlog PII + Cloudflare |
| Integración/orquestación | Task Scheduler hoy; Databricks Workflow diferido (R4) |
| Mantenimiento/monitoreo | F6 (no en F1) |
| Calidad de datos | F2 (silver) con notebooks SQL y expectations manuales |
| Elasticidad | Compute en nube por demanda |

### 11.2 Módulo 3 · Decisión crítica + modelo ML

- **Decisión crítica:** gestión automatizada de inventario + alertas de quiebre.
- **Modelos:** baseline naïve, Prophet top-100, LightGBM cola larga, clasificador de quiebre.
- **Estado:** se desarrolla en **F4**. Track A actual entrega el pipeline de datos que alimentará esos modelos.
- **Ética cubierta en este proyecto:** PII redaction en logs (Habeas Data Col), users `read-only`, ADR-0008 (no compartir datos sin consentimiento).

### 11.3 Módulo 4 · Madurez, VPC, BMC

- **Diagnóstico** (PLAN.md §3): arquetipo **Principiante** → objetivo **Practicante** en 12 meses.
- **Hoja de ruta** (PLAN.md §7): 7 fases, 2 cerradas (F0, F1).
- **KPIs** (PLAN.md §9): 5 medidos en F1 (ver §7.3 arriba).
- **VPC** (PLAN.md §13): Customer Profile + Value Map listos.
- **BMC** (PLAN.md §14): 9 bloques documentados.

### 11.4 Entregables del curso

| ID | Estado | Soporte en el repo |
|----|--------|---------------------|
| **E1** Diagnóstico + arquitectura | ✅ | `PLAN.md` + `docs/decisions/` + `docs/contexto-proyecto.md` |
| **E2** Pipeline operativo | 🟡 Bronze listo, falta Silver (F2) | `notebooks/bronze/` + `infra/` |
| **E3** Producto descriptivo | ⬜ F3 | PWA actual es scaffold; dashboard pendiente |
| **E4** Producto predictivo | ⬜ F4 | — |
| **E5** Memoria final | ⬜ Cierre | Este documento + SEGUIMIENTO son la base |

---

## 12 · Qué hay disponible AHORA (qué se puede mostrar)

### 12.1 Repo público

[github.com/javierportillar/motoshopData](https://github.com/javierportillar/motoshopData) · 39 commits · 121 archivos.

### 12.2 API en vivo

`https://api.fragloesja.uk/`

- `GET /health` → `{"status":"ok",...}` (público)
- `GET /demo` → página interactiva para móvil (público)
- `POST /auth/login` con `admin/FG28` → JWT (público hasta rotación, ver R2)
- `GET /products?q=aceite` con Bearer → lista paginada
- `GET /products/MOTS1297/stock` → `{"total": 691.0, ...}`
- `GET /sales/recent?limit=10` → últimas facturas activas
- `GET /docs` → Swagger interactivo

### 12.3 Databricks workspace

- Catálogo `motoshop` con esquemas `bronze`, `silver`, `gold`.
- Bronze poblada con 12 tablas (~80k filas).
- SQL Warehouse Serverless Starter con auto-stop 10 min.
- UC Volume `motoshop.bronze._landing` con Parquets y `_manifests/`.
- Los notebooks viven en `Repos/javierportillar/motoshopData`; si la UI no muestra un Pull claro, el fallback operativo es sincronizar el notebook remoto por API al path del Git folder antes de relanzar el job.

### 12.4 Métricas

| Métrica | Valor |
|---------|-------|
| Tablas core en Bronze | 12 |
| Filas totales ingestadas | 79,132 |
| Endpoints API | 7 |
| Tests passing | 23 |
| Cobertura tests | 79% global |
| Corridas dump exitosas | 5/5 |
| Latencia `/health` p95 | ~5 ms |
| Latencia `/stock` p95 | ~50 ms (warm) / ~780 ms (cold) |
| Tiempo ingesta total | 30-37 s |
| Schedule | c/30 min (07:00–19:30) con catch-up y retry |
| ADRs aceptados | 13 |
| Sesiones de trabajo | 22 |
| Deudas vivas | 4 (R1, R2, R4, R5) |

---

## 13 · Lo siguiente · Fase 2 · Silver + PWA MVP

> Detalle operativo en [`docs/plan-f2.md`](plan-f2.md) y [`docs/decisions/0012-stack-f2.md`](decisions/0012-stack-f2.md).

### 13.1 Objetivo

Modelo dimensional limpio (Silver) + PWA usable end-to-end. Hito: *"vendedor en la calle abre la app, busca un repuesto, ve precio y stock por bodega"*.

### 13.2 Sprints anticipados

| Sprint | Track | Entregables |
|--------|-------|-------------|
| F2-A | A · Silver | `fact_ventas`, `fact_compras`, `fact_inventario` + `dim_producto`, `dim_tiempo`, `dim_tercero`, `dim_sucursal`, `dim_bodega`. Casteos formales (TZ → UTC, decimales, `'0000-00-00'` → NULL). Reglas de calidad con notebooks SQL. Linaje UC. |
| F2-B | T · PWA login + búsqueda | Login con JWT + persistencia + refresh automático on 401. Página de búsqueda de productos con paginación. `fetch` nativo con wrapper mínimo. |
| F2-C | T · PWA stock + offline | Ficha de SKU con stock por bodega. Modo offline básico (`next-pwa`). Manifest PWA (instalable). |

### 13.3 Decisiones técnicas previstas en ADR-0012

- Schema evolution silver: `MERGE INTO` por clave para dimensiones y cargas idempotentes por partición o llave de negocio para hechos.
- Librería PWA: `next-pwa`.
- Fetch wrapper: `fetch` nativo + refresh-on-401.
- Casting `fecdoc`: `'0000-00-00'` → NULL o cuarentena explícita.
- Reglas de calidad: notebooks SQL con assertions manuales, no DLT en el MVP.

### 13.4 Verificaciones críticas F2 (extraídas de PLAN.md §7)

1. ¿Hay duplicados en silver?
2. ¿Fechas inválidas: cuarentena o falla?
3. ¿Totales silver cuadran con reporte sgHermes (< 0.5% diferencia)?
4. ¿PWA funciona sin conexión post-cache?
5. ¿Sesión sobrevive a cerrar/reabrir app?
6. ¿Búsqueda < 1 s con 6k productos?
7. ¿Permisos de rol funcionan?
8. ¿PWA muestra el mismo dato que MySQL para 5 SKUs aleatorios?

---

## 14 · Cómo retomar el contexto en una nueva sesión

Si vuelves al proyecto después de tiempo, lee en este orden:

1. **Este archivo** (`docs/contexto-proyecto.md`) → te ubica en 5 minutos.
2. **`SEGUIMIENTO.md` cabecera + última nota de sesión** → estado vivo.
3. **`PENDIENTES.md` bloque más reciente** → qué te toca.
4. **`docs/plan-f<N>.md` de la fase activa** → cómo está estructurado el trabajo.

Si vas a tocar Databricks notebooks y el cambio ya está en `main`:

5. **No asumas que la UI te va a mostrar un botón de Pull.** Cuando el notebook está en `Repos/`, el agente puede sincronizarlo directamente en el path del Git folder por API (workspace import/export) si la interfaz no deja claro el refresh.

Si vas a ejecutar (no planificar):

5. **`docs/handoff-f<N>.md`** → pre-flight check, política de commits, escalación.
6. **Si estás en F2, leer `docs/handoff-f2.md`** → incluye la nota operativa sobre sincronizar notebooks de Databricks por API cuando la UI no deje claro el Pull.

---

## 15 · Resumen ejecutivo en una frase

> **Cuatro días, tres fases cerradas (F1 + F2 + F3) más dos hardening sprints (F1.5 + F1.9): repo público con pipeline cada 30 min resiliente, API operativa con 5 endpoints `/metrics/*` sobre Gold, PWA con 4 dashboards (ventas, inventario, ABC, dormidos) que cuadran 0% contra Databricks SQL, workflow gold nocturno UNPAUSED en cron 02:30 COL — con 7 deudas conscientes documentadas (R1, R2, R4, R5, R6, R7, R8 — las 3 últimas diferidas a F6 hardening), 15 ADRs aceptados, y F4 · Predictivo (ML) arrancando con dataset Gold validado.**
