# Plan · Plataforma Multi-tenant (MotoShop + MasVital)

> **Estado:** propuesta aprobada · 2026-06-13
> **PO:** Javier · **Decisión arquitectónica:** Reviewer
> **Documentos relacionados:** [`MASTER.md`](MASTER.md) · [`contexto-proyecto.md`](contexto-proyecto.md) · [`plan-v1.7-observability.md`](plan-v1.7-observability.md)

---

## 1 · Objetivo en una frase

Convertir la plataforma de un solo negocio (MotoShop) a una plataforma multi-tenant (MotoShop + MasVital + futuros) **manteniendo $0/mes de infraestructura recurrente**, con trazabilidad por tenant en cada capa (datos, API, frontend, observability), y con MasVital arrancando con las features que su edad de negocio permite.

---

## 2 · Contexto de partida

| Dimensión | MotoShop | MasVital |
|---|---|---|
| Tipo de negocio | Repuestos de moto, Cali | (a definir — abierto recientemente) |
| Antigüedad de datos | 1+ año en MySQL sgHermes | Días/semanas — recién abrió |
| PC origen | PC Windows ya operativo con `infra/refresh_v15.ps1` | PC Windows nuevo, sin nada instalado |
| Volumen estimado SKUs | ~13.000 | ? (probablemente < 5.000) |
| Features aplicables | Todas | Solo descriptivas hasta acumular 30-90 días |

---

## 3 · Arquitectura objetivo

### 3.1 Mapa lógico

```
                ┌─────────────────────────────────┐
                │   PWA Next.js (Vercel)          │
                │   app.fragloesja.uk             │
                │                                 │
                │   /login → /select-tenant       │
                │   → enrutamiento con            │
                │     X-Tenant en cada request    │
                └────────────────┬────────────────┘
                                 │
                                 │ HTTPS + JWT + X-Tenant
                                 ▼
                ┌─────────────────────────────────┐
                │   FastAPI (Render)              │
                │   api.fragloesja.uk             │
                │                                 │
                │   tenants.yaml + dep get_tenant │
                │   abre /tmp/{tenant}_gold.duckdb│
                │   cache key incluye tenant      │
                └────┬────────────────────┬───────┘
                     │                    │
                     ▼                    ▼
        ┌──────────────────┐    ┌──────────────────┐
        │ R2: motoshop-gold│    │ Render local FS  │
        │ ├─ motoshop_gold │    │ /tmp/motoshop_*  │
        │ ├─ masvital_gold │    │ /tmp/masvital_*  │
        │ └─ pipeline_runs │    │ SQLite app_writes│
        └──────────────────┘    └──────────────────┘
                ▲           ▲
                │           │
   ┌────────────┘           └────────────┐
   │                                     │
┌──────────────┐                  ┌──────────────┐
│ PC Windows   │                  │ PC Windows   │
│ MotoShop     │                  │ MasVital     │
│              │                  │              │
│ MySQL sgHerm.│                  │ MySQL (?)    │
│ pipeline/    │                  │ pipeline/    │
│ refresh.ps1  │                  │ refresh.ps1  │
│ Task Sched.  │                  │ Task Sched.  │
│ TENANT=      │                  │ TENANT=      │
│ motoshop     │                  │ masvital     │
└──────────────┘                  └──────────────┘
   │                                     │
   │ git pull motoshopData               │ git pull masvitalData
   ▼                                     ▼
GitHub: motoshopData              GitHub: masvitalData
(plataforma)                      (operación PC MasVital)
```

### 3.2 Decisiones formales

| ID | Decisión | Razón | Trade-off |
|---|---|---|---|
| MT-01 | UN backend multi-tenant, no doble API | Cero duplicación, $0 sigue $0, escalable a N negocios | Backend más complejo (acotado: ~6 archivos tocados) |
| MT-02 | UN frontend con tenant picker | UX uniforme, un solo deploy | Lógica de gating en layout |
| MT-03 | `motoshopData/` = plataforma. `masvitalData/` = solo scripts PC MasVital | Cero refactor del repo grande, MasVital arranca con ~10 archivos | Pipeline duplicado (acotado, refactor a paquete cuando llegue 3er negocio) |
| MT-04 | Header `X-Tenant` + claim JWT `tenants_allowed` | Switch sin re-login, validación centralizada | Frontend debe inyectar header siempre |
| MT-05 | 1 bucket R2, N objetos | Misma credencial, menos config | Si en algún momento querés segregar permisos, hay que partir |
| MT-06 | `tenants.yaml` con `enabled_features` declaradas | Habilitar/deshabilitar dashboards por tenant sin tocar código | Necesita endpoint `/api/me` que el frontend respeta |
| MT-07 | `tenant` agregado a `pipeline_runs`, `llm_cost.jsonl`, structlog, audit | Trazabilidad operativa real, gerente ve qué pasa en cada negocio | Migración SQLite menor |
| MT-08 | Pipeline duplicado en `masvitalData/` al arrancar | Independencia operativa, cero submódulos al inicio | Cuando llegue Sprint posterior, considerar paquete `pip install -e ./pipeline` desde `motoshopData` |
| MT-09 | Default tenant = `motoshop` si llega request sin `X-Tenant` | Backward compat — no rompe el frontend actual durante M1 | Hay que sacarlo después de M2 para forzar tenant explícito |
| MT-10 | Briefing diario corre 2x (uno por tenant con briefing habilitado) | Cada gerente recibe su briefing | GitHub Actions workflow itera por tenant |

---

## 4 · Definición de tenants

### 4.1 `tenants.yaml` (vive en `motoshop-app/api/`)

```yaml
tenants:
  - id: motoshop
    nombre: "MotoShop"
    descripcion: "Repuestos de moto · Cali, Colombia"
    color_brand: "#7B1818"
    logo: "/tenants/motoshop/logo.png"
    r2_object_key: "motoshop_gold.duckdb"
    local_db_path: "/tmp/motoshop_gold.duckdb"
    mysql_source: "sgHermes"
    telegram_chat_id_gerente: "816016329"
    enabled_features:
      - products
      - stock
      - sales
      - ventas-summary
      - ventas-daily
      - ventas-monthly
      - inventario
      - abc
      - dormidos
      - cohortes
      - drift
      - forecast
      - plan-compras
      - vendedores
      - alerts
      - acciones
      - chat-ia
      - briefing-diario
      - pipeline-observability
      - data-catalog
    briefing:
      activo: true
      hora_cron_utc: "0 11 * * *"  # 06:00 COL

  - id: masvital
    nombre: "MasVital"
    descripcion: "(definir línea de negocio)"
    color_brand: "#16A34A"
    logo: "/tenants/masvital/logo.png"
    r2_object_key: "masvital_gold.duckdb"
    local_db_path: "/tmp/masvital_gold.duckdb"
    mysql_source: "masvital_pos"  # nombre lógico, real va en el PC
    telegram_chat_id_gerente: null  # se setea cuando tengamos chat
    enabled_features:
      - products
      - stock
      - sales
      - ventas-summary
      - ventas-daily
      - inventario
      - chat-ia
      - pipeline-observability
    briefing:
      activo: false  # activar cuando haya 30 días de datos
```

### 4.2 `users.yaml` extendido

```yaml
users:
  - username: admin
    hashed_password: $2b$12$...   # FG28 hasheado
    email: javier@motoshop.local
    role: admin
    tenants_allowed: [motoshop, masvital]

  - username: gerente1
    hashed_password: ...
    role: gerente
    tenants_allowed: [motoshop]

  - username: vendedor1
    hashed_password: ...
    role: vendedor
    tenants_allowed: [motoshop]
```

---

## 5 · Plan por sprints

Cuatro sprints. Cada uno con DoD claro y rollback. Pueden ejecutarse en serie o (M2 y M3 parcial) en paralelo si hay dos devs.

### 🟦 Sprint M1 — Backend multi-tenant (Dev Back)

**Goal.** Backend acepta `X-Tenant`, abre el DuckDB correcto, sin romper el frontend MotoShop actual (default tenant = motoshop si no llega header).

**Tareas (Dev Back):**

| # | Tarea | Archivos | Esfuerzo |
|---|---|---|---|
| M1.1 | Crear `tenants.yaml` con MotoShop + MasVital | `motoshop-app/api/tenants.yaml` (nuevo) | 0.5 h |
| M1.2 | Cargar tenants en `config.py` (parsear YAML al boot) | `motoshop_api/config.py`, `motoshop_api/tenants.py` (nuevo) | 1 h |
| M1.3 | Agregar `tenants_allowed` al modelo `User` (`users.py`) | `motoshop_api/auth/users.py` + `users.yaml` | 0.5 h |
| M1.4 | JWT payload incluye `tenants_allowed` claim | `motoshop_api/auth/jwt.py`, `auth/router.py` | 1 h |
| M1.5 | Dependency `get_tenant(request)` que lee `X-Tenant`, default `motoshop`, valida contra `tenants_allowed` | `motoshop_api/auth/tenant_dep.py` (nuevo) | 1 h |
| M1.6 | Endpoint `GET /api/me` devuelve `{user, role, tenants_allowed, current_tenant, enabled_features}` | `motoshop_api/auth/router.py` | 1 h |
| M1.7 | Refactor `MetricsRepo.__init__()` y `_bootstrap_duckdb_from_r2()` para recibir `tenant` y abrir `{tenant}_gold.duckdb` | `motoshop_api/metrics/repo_duckdb.py` | 2 h |
| M1.8 | Reemplazar prefijo `motoshop_silver_*` y `motoshop_gold_*` por solo `silver_*` y `gold_*` en queries del pipeline (las tablas internas del DuckDB ya no necesitan prefijo, el tenancy lo da el archivo) | `pipeline/silver.py`, `pipeline/gold.py`, `motoshop_api/metrics/repo_duckdb.py` (todas las queries) | 3 h |
| M1.9 | Cache key con tenant: `_cached_or_fetch(f"{key}:{tenant}", ...)` | `motoshop_api/metrics/router.py` | 1 h |
| M1.10 | Refactor los OTROS módulos que abren DuckDB (`products`, `stock`, `sales`, `alerts`, `forecast`, `llm/tools.py`) para recibir tenant | varios módulos | 3 h |
| M1.11 | Tests: MotoShop sin cambios sigue funcionando con `X-Tenant: motoshop` y sin header | `tests/` | 2 h |
| M1.12 | Deploy Render, validar prod | — | 0.5 h |

**Esfuerzo total Dev Back:** ~16 h (2-3 sesiones).

**DoD:**
- Login con `admin/FG28` devuelve token con `tenants_allowed: [motoshop, masvital]`
- `GET /api/me` con header `X-Tenant: motoshop` devuelve features actuales
- `GET /api/me` con header `X-Tenant: masvital` devuelve features reducidas (descriptivas)
- Frontend SIN modificar sigue funcionando para MotoShop (header ausente = tenant motoshop)
- `GET /api/metrics/abc-segmentation` con `X-Tenant: masvital` devuelve `{bucket_a: 0, bucket_b: 0, bucket_c: 0}` (porque el archivo no existe aún) sin crash
- Tests E2E del frontend siguen verdes

**Rollback:** revert el commit del refactor; el backend vuelve a single-tenant.

**Bloqueante para:** M2 puede empezar ANTES de que M1 termine (Dev Front trabaja con stubs locales del header), pero NO se mergea hasta que M1 esté en prod.

---

### 🟪 Sprint M2 — Frontend multi-tenant (Dev Front)

**Goal.** Después de login, usuario ve picker MotoShop/MasVital. Escogido un tenant, todo SWR inyecta `X-Tenant`. Sidebar muestra el tenant activo. Dashboards no habilitados están ocultos.

**Tareas (Dev Front):**

| # | Tarea | Archivos | Esfuerzo |
|---|---|---|---|
| M2.1 | Zustand store agrega `currentTenant`, `availableTenants`, `enabledFeatures`, `setTenant()`, `clearTenant()` (todos persisted) | `lib/auth/store.ts` | 1 h |
| M2.2 | Hook `useMe()` llama `/api/me` al login y popula store | `lib/api/hooks.ts` | 1 h |
| M2.3 | SWR fetcher centralizado inyecta `X-Tenant` en todos los hooks | `lib/api/hooks.ts` (refactor) | 1.5 h |
| M2.4 | Ruta `/select-tenant/page.tsx` con cards de cada tenant disponible (logo + nombre + descripcion + "Ingresar") | `app/select-tenant/page.tsx` (nueva) | 2 h |
| M2.5 | `handleSubmit` del login: tras `setUser`, llama `/api/me`, popula store, redirige a `/select-tenant` (o `/` si solo hay 1 tenant disponible) | `app/login/page.tsx` | 1 h |
| M2.6 | Middleware redirige a `/select-tenant` si autenticado pero `currentTenant` ausente (chequea cookie auxiliar) | `middleware.ts` | 1.5 h |
| M2.7 | Sidebar (`Navigation.tsx`) muestra logo + nombre del tenant activo, botón "Cambiar negocio" | `components/ui/Navigation.tsx` | 1.5 h |
| M2.8 | Layout `(authenticated)/layout.tsx` lee `enabledFeatures` del store y oculta `navItems` no habilitados | `app/(authenticated)/layout.tsx`, `components/ui/Navigation.tsx` | 1.5 h |
| M2.9 | Cada `page.tsx` de dashboard checa `enabledFeatures.includes("abc")` y renderiza empty state si falta | `(authenticated)/dashboards/*`, `cohortes`, `drift`, `forecast`, `plan-compras` | 2 h |
| M2.10 | Logos placeholder en `public/tenants/motoshop/logo.png` y `public/tenants/masvital/logo.png` | `public/tenants/` | 0.5 h |
| M2.11 | Tests Playwright multi-tenant: admin entra, escoge MotoShop, ve dashboards; cambia a MasVital, ve solo features habilitadas | `tests/` | 2 h |
| M2.12 | Deploy Vercel + smoke prod | — | 0.5 h |

**Esfuerzo total Dev Front:** ~16 h (2-3 sesiones).

**DoD:**
- Login `admin/FG28` → redirige a `/select-tenant` → cards MotoShop y MasVital
- Escojo MotoShop → home con dashboards completos
- Botón "Cambiar negocio" → vuelve al picker
- Escojo MasVital → home con dashboards descriptivos; ABC/Dormidos/Cohortes/Drift/Forecast/Plan-compras ocultos o con "Habilitando cuando haya histórico suficiente"
- Network tab: cada request al backend lleva `X-Tenant`

**Rollback:** revert del PR del frontend; el backend ya está multi-tenant, queda esperando.

---

### 🟧 Sprint M3 — Onboarding MasVital (Dev Back + Dev W)

**Goal.** Crear el repo `masvitalData` desde 0, instalar el pipeline en el PC MasVital, correr la primera ingesta, subir el primer DuckDB a R2. Validar end-to-end.

**Tareas Dev Back (preparación):**

| # | Tarea | Archivos | Esfuerzo |
|---|---|---|---|
| M3.1 | Inicializar repo `masvitalData/` en GitHub (privado) | (GitHub UI + `git init`) | 0.5 h |
| M3.2 | Estructura inicial del repo: `pipeline/`, `infra/`, `scripts/`, `.env.example`, `README.md`, `.gitignore`, `INICIAR_DEV_W.md` | `masvitalData/*` | 2 h |
| M3.3 | Copiar pipeline genérico desde motoshopData a masvitalData (parametrizar con env vars `TENANT`, `MYSQL_*`, `R2_OBJECT_KEY`) | `masvitalData/pipeline/*` | 2 h |
| M3.4 | Adaptar `pipeline/mysql_source.py` para que las tablas MySQL de MasVital se mapeen a bronze correctamente (si esquema difiere) | `masvitalData/pipeline/mysql_source.py` | depende del esquema |
| M3.5 | `infra/refresh.ps1` (wrapper PowerShell) que setea env vars MasVital y corre `python pipeline/run_all.py` + `python scripts/upload_duckdb_to_r2.py` | `masvitalData/infra/refresh.ps1` | 1 h |
| M3.6 | `infra/auto_pull_and_apply.ps1` adaptado a `masvitalData` | `masvitalData/infra/auto_pull_and_apply.ps1` | 1 h |
| M3.7 | `infra/backup_mysql.ps1` adaptado | `masvitalData/infra/backup_mysql.ps1` | 0.5 h |
| M3.8 | `INICIAR_DEV_W.md`: instructivo paso a paso para Dev W (qué instalar, cómo configurar `.env`, cómo testear, cómo prender Task Scheduler) | `masvitalData/INICIAR_DEV_W.md` | 1.5 h |
| M3.9 | `README.md` del repo `masvitalData`: rol del repo, scope, links a motoshopData | `masvitalData/README.md` | 1 h |
| M3.10 | Modificar `briefing-daily.yml` (en motoshopData) para iterar por tenants con `briefing.activo: true` | `.github/workflows/briefing-daily.yml` | 0.5 h |

**Esfuerzo Dev Back:** ~10 h (1-2 sesiones).

**Tareas Dev W (ejecución en el PC MasVital):**

| # | Tarea | Cómo |
|---|---|---|
| M3.W1 | Instalar Python 3.11+ en PC MasVital | Instalador oficial |
| M3.W2 | Instalar dependencias (`pip install -r requirements.txt` o `pip install -e .`) | desde repo |
| M3.W3 | Clonar `masvitalData` en ruta acordada (ej. `C:\Users\MasVital\Documents\masvitalData`) | git clone |
| M3.W4 | Configurar `.env` con: `TENANT=masvital`, `MYSQL_HOST=localhost`, `MYSQL_USER=api_read`, `MYSQL_PASSWORD=...`, `MYSQL_DATABASE=masvital2026` (o el real), `R2_*` (mismas creds que MotoShop), `R2_OBJECT_KEY=masvital_gold.duckdb`, `HF_API_TOKEN=...` | manual |
| M3.W5 | Crear usuario MySQL local `api_read` SELECT-only sobre la BD productiva de MasVital | `CREATE USER 'api_read'@'localhost' IDENTIFIED BY '...'; GRANT SELECT ON masvital_db.* TO 'api_read'@'localhost';` |
| M3.W6 | Probar `python pipeline/run_all.py` manual primero (verbose) | terminal |
| M3.W7 | Si OK, probar `infra/refresh.ps1` manual | PowerShell |
| M3.W8 | Verificar en R2 que `masvital_gold.duckdb` fue subido | UI R2 |
| M3.W9 | Verificar en la PWA (logueado como admin, tenant MasVital) que se ven datos | navegador |
| M3.W10 | Configurar Task Scheduler para `refresh.ps1` cada 30 min (07:00-19:30 hora local) | Task Scheduler UI |
| M3.W11 | Configurar Task Scheduler para `auto_pull_and_apply.ps1` cada 5 min | Task Scheduler UI |
| M3.W12 | Probar `auto_pull_and_apply.ps1` haciendo un commit en `masvitalData/main` y viendo que el PC lo aplica | git + observar logs |

**Esfuerzo Dev W:** ~3-5 h efectivas (depende de conectividad y de si Python ya estaba).

**DoD:**
- `masvitalData` existe en GitHub, privado, con `INICIAR_DEV_W.md` claro
- PC MasVital corre el pipeline cada 30 min, sube DuckDB a R2 con key `masvital_gold.duckdb`
- En la PWA prod, login `admin/FG28` → tenant MasVital → home muestra KPIs reales (aunque sean pocos)
- Chat IA responde sobre MasVital (tools que aplican; las que no, devuelven "sin datos suficientes")
- `auto_pull_and_apply.ps1` funcionando — el PC MasVital se actualiza solo cuando pushes a `masvitalData/main`

**Rollback:** apagar Task Scheduler en PC MasVital. Eliminar `masvital_gold.duckdb` de R2. Quitar entry `masvital` de `tenants.yaml`. PWA vuelve a single-tenant.

---

### 🟥 Sprint M4 — Trazabilidad y observability multi-tenant (Dev Back + Dev Front)

**Goal.** Toda la observability — pipeline runs, LLM cost, briefing logs, audit log de switches — cruza ambos tenants.

**Tareas Dev Back:**

| # | Tarea | Archivos | Esfuerzo |
|---|---|---|---|
| M4.1 | `pipeline_runs.duckdb` agrega columna `tenant` (migración + backfill `motoshop` para runs viejos) | `pipeline_runs_db.py`, `pipeline_runs/router.py` | 1.5 h |
| M4.2 | `llm_cost.jsonl` cada línea incluye `tenant` | `motoshop_api/llm/router.py`, `motoshop_api/admin/router.py` | 1 h |
| M4.3 | structlog `bind(tenant=...)` por cada request | middleware FastAPI | 1 h |
| M4.4 | SQLite tabla `tenant_switches(user, from_tenant, to_tenant, at)` + endpoint POST `/api/auth/switch-tenant` que registra y rota | `motoshop_api/auth/router.py`, migración SQLite | 2 h |
| M4.5 | `/health/data-freshness?tenant=X` por tenant | `motoshop_api/health/router.py` | 1 h |
| M4.6 | `briefing-daily.yml` actualizado para correr 1x por tenant con `briefing.activo: true`, cada mensaje incluye `[MotoShop]` o `[MasVital]` prefix | `.github/workflows/briefing-daily.yml`, `motoshop_api/llm/router.py` | 1 h |

**Tareas Dev Front:**

| # | Tarea | Archivos | Esfuerzo |
|---|---|---|---|
| M4.7 | `/admin/pipeline` filtrable por tenant | `app/(authenticated)/admin/pipeline/page.tsx` | 1.5 h |
| M4.8 | `/admin/llm-cost` (nuevo) muestra cost JSONL por tenant + total | nueva ruta | 1.5 h |
| M4.9 | `/admin/audit` (nuevo) muestra historial de switches de tenant por usuario | nueva ruta | 1 h |
| M4.10 | `StaleDataBanner` consulta freshness del tenant activo | `components/StaleDataBanner.tsx` | 0.5 h |

**Esfuerzo total M4:** ~11 h (Dev Back ~8 h, Dev Front ~5 h).

**DoD:**
- En `/admin/pipeline`: dropdown MotoShop/MasVital filtra runs
- En `/admin/llm-cost`: gerente ve cuánto LLM gastó cada negocio
- En `/admin/audit`: registro de cada vez que un usuario cambió de tenant
- Briefing diario a las 06:00 envía 2 mensajes a Telegram (1 por tenant, cuando ambos lo tienen activo)

---

## 6 · Mapa total de archivos tocados o creados

### Repo `motoshopData/` (existente)

| Path | Acción | Sprint |
|---|---|---|
| `motoshop-app/api/tenants.yaml` | NUEVO | M1 |
| `motoshop-app/api/users.yaml` | MODIFICAR (+ `tenants_allowed`) | M1 |
| `motoshop-app/api/src/motoshop_api/config.py` | MODIFICAR | M1 |
| `motoshop-app/api/src/motoshop_api/tenants.py` | NUEVO | M1 |
| `motoshop-app/api/src/motoshop_api/auth/users.py` | MODIFICAR | M1 |
| `motoshop-app/api/src/motoshop_api/auth/jwt.py` | MODIFICAR | M1 |
| `motoshop-app/api/src/motoshop_api/auth/router.py` | MODIFICAR (`/me`, `/switch-tenant`) | M1, M4 |
| `motoshop-app/api/src/motoshop_api/auth/tenant_dep.py` | NUEVO | M1 |
| `motoshop-app/api/src/motoshop_api/metrics/repo_duckdb.py` | MODIFICAR (queries + bootstrap) | M1 |
| `motoshop-app/api/src/motoshop_api/metrics/router.py` | MODIFICAR (cache key) | M1 |
| `motoshop-app/api/src/motoshop_api/{products,stock,sales,alerts,forecast,llm}/router.py` | MODIFICAR (inyectar tenant) | M1 |
| `motoshop-app/api/src/motoshop_api/llm/tools.py` | MODIFICAR (queries reciben tenant) | M1 |
| `motoshop-app/api/src/motoshop_api/health/router.py` | MODIFICAR | M4 |
| `motoshop-app/api/src/motoshop_api/admin/router.py` | MODIFICAR | M4 |
| `motoshop-app/api/src/motoshop_api/pipeline_runs/router.py` | MODIFICAR | M4 |
| `pipeline/silver.py`, `pipeline/gold.py`, `pipeline/run_all.py` | MODIFICAR (prefijos tablas, env vars) | M1, M3 |
| `motoshop-app/web/lib/auth/store.ts` | MODIFICAR | M2 |
| `motoshop-app/web/lib/api/hooks.ts` | MODIFICAR (fetcher con `X-Tenant`, hook `useMe`) | M2 |
| `motoshop-app/web/app/login/page.tsx` | MODIFICAR (post-login flow) | M2 |
| `motoshop-app/web/app/select-tenant/page.tsx` | NUEVO | M2 |
| `motoshop-app/web/middleware.ts` | MODIFICAR | M2 |
| `motoshop-app/web/components/ui/Navigation.tsx` | MODIFICAR | M2 |
| `motoshop-app/web/app/(authenticated)/layout.tsx` | MODIFICAR | M2 |
| `motoshop-app/web/app/(authenticated)/{dashboards/*,cohortes,drift,forecast,plan-compras}/page.tsx` | MODIFICAR (feature gating) | M2 |
| `motoshop-app/web/app/(authenticated)/admin/{llm-cost,audit}/page.tsx` | NUEVOS | M4 |
| `motoshop-app/web/public/tenants/{motoshop,masvital}/logo.png` | NUEVOS | M2 |
| `.github/workflows/briefing-daily.yml` | MODIFICAR | M4 |
| `docs/plan-multi-tenant.md` | NUEVO (este archivo) | — |
| `docs/MASTER.md` | MODIFICAR (agregar entry en roadmap) | — |

### Repo `masvitalData/` (nuevo, desde 0)

| Path | Acción | Sprint |
|---|---|---|
| `.gitignore` | NUEVO | M3 |
| `README.md` | NUEVO | M3 |
| `INICIAR_DEV_W.md` | NUEVO | M3 |
| `.env.example` | NUEVO | M3 |
| `pipeline/` | NUEVO (copia de motoshopData/pipeline parametrizada) | M3 |
| `scripts/upload_duckdb_to_r2.py` | NUEVO (copia adaptada) | M3 |
| `infra/refresh.ps1` | NUEVO | M3 |
| `infra/auto_pull_and_apply.ps1` | NUEVO | M3 |
| `infra/backup_mysql.ps1` | NUEVO | M3 |
| `infra/AUTO_PULL_SETUP.md` | NUEVO | M3 |
| `infra/logs/` | NUEVO (vacía, gitignored) | M3 |

---

## 7 · Trazabilidad — qué tenemos por capa

| Capa | Cómo se identifica el tenant | Dónde queda registrado |
|---|---|---|
| **Pipeline (PC Windows)** | Env var `TENANT` que el script PS1 setea antes de ejecutar | `pipeline_runs.duckdb` columna `tenant` + log local |
| **DuckDB en R2** | Object key (`{tenant}_gold.duckdb`) | Bucket R2 |
| **DuckDB local en Render** | Path (`/tmp/{tenant}_gold.duckdb`) | Filesystem |
| **API request** | Header `X-Tenant` + claim JWT | Cada log structlog `bind(tenant=...)` |
| **Cache TTL** | Key prefix (`{endpoint}:{tenant}`) | Memory cachetools |
| **SQLite writes** | Columna `tenant` en cada tabla que aplica (`alert_actions`, `purchase_plans`) | SQLite Render |
| **LLM cost** | Campo `tenant` por línea | `llm_cost.jsonl` |
| **Switch de tenant del usuario** | Endpoint registra evento | SQLite tabla `tenant_switches` |
| **Briefing Telegram** | Prefix `[MotoShop]`/`[MasVital]` + chat_id por tenant | Telegram + cost log |
| **PWA frontend** | Header en cada SWR + Zustand `currentTenant` | DevTools + Vercel analytics |

---

## 8 · Plan de costos (verificación $0/mes)

| Servicio | Antes (single-tenant) | Después (2 tenants) | Margen free tier |
|---|---|---|---|
| Render Free | 1 servicio, ~5 hrs/día activa | Idem (mismo servicio sirve ambos) | ✅ 750 hrs/mes free |
| Vercel Hobby | <1 GB bandwidth/mes | <1.5 GB | ✅ 100 GB free |
| R2 Free | ~50 MB + ~5k ops/mes | ~100 MB + ~10k ops/mes | ✅ 10 GB + 1M Class A + 10M Class B |
| GitHub Actions | ~60 min/mes | ~80 min/mes (briefing 2x) | ✅ 2000 min/mes |
| HF Inference | ~50 SKUs nuevos/mes | ~150 (suma 2 negocios) | ✅ generoso |
| Telegram | 1 msg/día | 2 msg/día | ✅ sin límite práctico |
| OpenCode Go | (paga el PO, no es infra) | uso x2 aprox | varía con uso, no infra recurrente |
| **Total infra** | **$0/mes** | **$0/mes** | ✅ se mantiene |

---

## 9 · Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Esquema MySQL MasVital difiere de sgHermes | Pipeline rompe en bronze→silver | M3.4 dedicado a inspección + adaptación; si el delta es chico, parametrizar; si es grande, fork del módulo `silver.py` específico |
| Backend olvida pasar tenant a algún repo y MasVital ve datos de MotoShop | **CRÍTICO** — cross-tenant leak | Tests dedicados M1.11 que validan: query `abc-detalle` con `X-Tenant: masvital` NUNCA devuelve productos de MotoShop. Default tenant en M1 sale después de M2 (forzar header explícito). |
| Frontend olvida inyectar header → backend usa default `motoshop` → usuario de MasVital ve MotoShop | Confusión, no leak | M2 hace fetcher centralizado, no se puede olvidar. M4: backend en modo strict (sin default) tras DoD M2. |
| PC MasVital tiene poca conectividad y los runs fallan | Datos no llegan a R2 | `refresh.ps1` con retry + log. Si falla, próximo run lo intenta. Igual a MotoShop. |
| Briefing diario MasVital queda raro porque hay pocos datos | UX pobre | M3.5: dejar `briefing.activo: false` para MasVital hasta tener 30 días |
| Usuarios MasVital quieren ver dormidos/forecast antes de tiempo | Feature request | `tenants.yaml` documenta los thresholds. Cuando se cumplen, agregar feature. Trazable. |
| Costo R2 si crecemos a 5+ tenants con archivos de 200MB | Aún free hasta 10 GB | Mucho margen. Si llega: lifecycle de versiones viejas. |

---

## 10 · Orden de ejecución sugerido (estilo SDD)

```
Día 1-3:  Sprint M1  (Dev Back)   ── backend multi-tenant
Día 3-5:  Sprint M2  (Dev Front)  ── frontend tenant picker
Día 5-7:  Sprint M3  (Dev Back→W) ── repo masvitalData + onboarding PC
Día 7-9:  Sprint M4  (Dev Back+F) ── trazabilidad cross-tenant
```

Total estimado: ~9 días-persona si secuencial. Paralelizable parcialmente (M2 puede arrancar antes de que M1 esté en prod si Dev Front trabaja con stubs).

---

## 11 · Definition of Done — programa completo

- [ ] Backend acepta `X-Tenant` y rutea correctamente
- [ ] Frontend muestra picker post-login funcional
- [ ] PC MasVital corre el pipeline cada 30 min y sube a R2
- [ ] `admin/FG28` puede ver dashboards de MotoShop y MasVital sin re-login
- [ ] Chat IA responde sobre el tenant activo, con tools que se degradan limpiamente si no hay datos
- [ ] Briefing diario MotoShop sigue llegando a las 06:00 sin interrupción
- [ ] Cero cross-tenant leak validado por tests
- [ ] `/admin/pipeline`, `/admin/llm-cost`, `/admin/audit` filtran por tenant
- [ ] $0/mes infra confirmado mes 1 post-deploy
- [ ] `masvitalData/INICIAR_DEV_W.md` permite a Dev W reproducir el setup en otro PC sin ayuda

---

## 12 · Quién hace qué — resumen ejecutivo

| Rol | Trabajo total estimado | Sprints |
|---|---|---|
| **Reviewer / Arquitecto** | Aprobar este plan + revisar PRs | M1-M4 |
| **Dev Back** | Backend multi-tenant + repo masvitalData + observability backend | M1, M3 (prep), M4 |
| **Dev Front** | Frontend tenant picker + feature gating + admin pages | M2, M4 |
| **Dev W (PC MotoShop)** | Nada nuevo. Sigue su flujo de auto-pull. | — |
| **Dev W (PC MasVital)** | Instalar todo desde 0 siguiendo `INICIAR_DEV_W.md` | M3 |
| **PO (Javier)** | Validar UX del picker + verificar briefing dual + decidir tenants futuros | M2, M3 |
