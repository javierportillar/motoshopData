# Tasks · Sprint M1 — Backend Multi-tenant

> **Change:** `multi-tenant-m1-backend`
> **Source:** [`plan-multi-tenant.md`](../../docs/plan-multi-tenant.md) §5 · [`specs/multi-tenant-m1-backend.md`](../specs/multi-tenant-m1-backend.md) · [`designs/multi-tenant-m1-backend.md`](../designs/multi-tenant-m1-backend.md)
> **Total effort:** ~16.5 h (dev back)
> **Created:** 2026-06-13

---

## Task Dependency Graph

```
                  ┌──────────┐     ┌──────────┐
                  │  M1.1    │     │  M1.3    │
                  │ tenants  │     │ users    │
                  │ .yaml    │     │ model    │
                  └────┬─────┘     └────┬─────┘
                       │                │
                       ▼                ▼
                  ┌──────────┐     ┌──────────┐     ┌──────────┐
        ┌────────►│  M1.2    │     │  M1.4    │     │  M1.8    │
        │         │ tenants  │     │ JWT      │     │ pipeline │
        │         │ loader   │     │ claim    │     │ prefixes │
        │         └────┬─────┘     └────┬─────┘     └──────────┘
        │              │                │                │
        │              ▼                ▼                │
        │         ┌─────────────────────────┐            │
        │         │        M1.5             │            │
        │         │  get_tenant dep         │◄───────────┤ (indep.)
        │         └────┬────────────┬───────┘            │
        │              │            │                    │
        │              ▼            ▼                    │
        │     ┌──────────┐   ┌──────────┐               │
        │     │  M1.6    │   │  M1.7    │               │
        │     │ /api/me  │   │ Metrics  │               │
        │     │          │   │ Repo     │               │
        │     └──────────┘   └────┬─────┘               │
        │                         │                     │
        │                         ▼                     │
        │              ┌─────────────────────┐          │
        │              │    M1.9 + M1.10     │          │
        │              │ cache + all modules │          │
        │              └──────────┬──────────┘          │
        │                         │                     │
        │                         ▼                     │
        │              ┌─────────────────────┐          │
        │              │      M1.11          │          │
        │              │      Tests          │          │
        │              └──────────┬──────────┘          │
        │                         │                     │
        │                         ▼                     │
        │              ┌─────────────────────┐          │
        │              │      M1.12          │          │
        │              │   Deploy + smoke    │          │
        │              └─────────────────────┘          │
        │                                               │
        └───────────────────────────────────────────────┘
         M1.1 → M1.2 and M1.3 → M1.4 are parallel chains.
         M1.5 joins them. M1.8 runs independently at any time.
         M1.7 only needs M1.2 (tenants config), can start after M1.2.
         M1.9 + M1.10 need M1.7 + M1.5.
```

---

## Task Inventory

---

### M1.1 — Crear `tenants.yaml`

| Field | Value |
|-------|-------|
| **Effort** | 0.5 h |
| **Dependencies** | None |
| **Files** | `motoshop-app/api/tenants.yaml` **(NEW)** |
| **Type** | Config |

#### Acceptance Criteria
- File exists with both tenants: `motoshop` (full features) and `masvital` (descriptive-only)
- `motoshop` has `local_db_path: /tmp/motoshop_gold.duckdb`, `r2_object_key: motoshop_gold.duckdb`
- `masvital` has `local_db_path: /tmp/masvital_gold.duckdb`, `r2_object_key: masvital_gold.duckdb`
- Both have `enabled_features` per the plan §4.1
- YAML validates correctly with `TenantConfig` Pydantic model (M1.2)

---

### M1.2 — Cargar tenants en `config.py` + `tenants.py`

| Field | Value |
|-------|-------|
| **Effort** | 1 h |
| **Dependencies** | M1.1 |
| **Files to create** | `motoshop-api/src/motoshop_api/tenants.py` **(NEW)** |
| **Files to modify** | `motoshop-api/src/motoshop_api/config.py` |
| **Type** | Feature |

#### What to build

**`tenants.py`** (new):
- `TenantConfig` Pydantic model with all fields from plan §4.1 (`id`, `nombre`, `descripcion`, `color_brand`, `logo`, `r2_object_key`, `local_db_path`, `mysql_source`, `telegram_chat_id_gerente`, `enabled_features`, `briefing`)
- `BriefingConfig` Pydantic model (`activo: bool`, `hora_cron_utc: str`)
- `TenantsConfig` wrapper model with `tenants: list[TenantConfig]`
- `load_tenants(path)` → `dict[str, TenantConfig]` — loads YAML at boot, caches
- `get_tenant(tenant_id)` → `TenantConfig | None` — lookup by id
- `list_tenants()` → `list[TenantConfig]`
- Missing file → log warning, return empty

**`config.py`** (modify):
- Add `tenants_file_path: str = Field(default="tenants.yaml")` setting

#### Acceptance Criteria
- `load_tenants()` correctly parses `tenants.yaml` from M1.1
- `get_tenant("motoshop")` returns full config
- `get_tenant("masvital")` returns reduced config
- `get_tenant("nonexistent")` returns `None`
- Missing `tenants.yaml` logs warning, doesn't crash

---

### M1.3 — Agregar `tenants_allowed` al modelo `User`

| Field | Value |
|-------|-------|
| **Effort** | 0.5 h |
| **Dependencies** | None |
| **Files to modify** | `motoshop-api/src/motoshop_api/auth/users.py`, `motoshop-app/api/users.yaml` |
| **Type** | Feature |

#### What to change

**`users.py`:**
- Add `tenants_allowed: list[str] = ["motoshop"]` to `User` model (default for backward compat)

**`users.yaml`:**
- Add `tenants_allowed` field to each user:
  - `admin` → `[motoshop, masvital]`
  - `gerente1` → `[motoshop]`
  - `vendedor1` → `[motoshop]`

#### Acceptance Criteria
- `User(username="admin").tenants_allowed` defaults to `["motoshop"]`
- Loading updated `users.yaml` populates `tenants_allowed` correctly
- Existing login flow unchanged (default `["motoshop"]` is backward compatible)

---

### M1.4 — JWT payload incluye `tenants_allowed` claim

| Field | Value |
|-------|-------|
| **Effort** | 1 h |
| **Dependencies** | M1.3 |
| **Files to modify** | `motoshop-api/src/motoshop_api/auth/jwt.py`, `motoshop-api/src/motoshop_api/auth/router.py` |
| **Type** | Feature |

#### What to change

**`jwt.py`:**
- `create_access_token()` signature: add `tenants_allowed: list[str]` parameter
- Embed `"tenants_allowed"` claim in JWT payload alongside `sub`, `role`

**`auth/router.py`:**
- `POST /auth/login`: pass `user.tenants_allowed` to `create_access_token()`
- `POST /auth/refresh`: load user and pass `user.tenants_allowed` to `create_access_token()`

#### Acceptance Criteria
- Decoding JWT from `admin/FG28` login shows `tenants_allowed: ["motoshop", "masvital"]`
- Decoding JWT from `gerente1/...` login shows `tenants_allowed: ["motoshop"]`
- Refresh token also embeds the claim (re-reads from user cache)

---

### M1.5 — Dependency `get_tenant(request, user)`

| Field | Value |
|-------|-------|
| **Effort** | 1 h |
| **Dependencies** | M1.2, M1.4 |
| **Files to create** | `motoshop-api/src/motoshop_api/auth/tenant_dep.py` **(NEW)** |
| **Type** | Feature |

#### What to build

```
async def get_tenant(
    request: Request,
    user: User = Depends(get_current_user),
) -> tuple[str, TenantConfig]:
```

Logic:
1. Read `X-Tenant` header from `request.headers`
2. If absent → default `tenant_id = "motoshop"` (MT-09 backward compat)
3. Look up tenant config via `get_tenant(tenant_id)`
4. If `TenantConfig` not found → `404` with `detail="Tenant '{id}' not found"`
5. Validate `tenant_id in user.tenants_allowed` → if not, `403 Forbidden`
6. Return `(tenant_id, TenantConfig)`

#### Acceptance Criteria
- Request with `X-Tenant: masvital` and `admin` JWT → returns `("masvital", TenantConfig)`
- Request WITHOUT `X-Tenant` → returns `("motoshop", TenantConfig)` (default)
- Request with `X-Tenant: masvital` and `gerente1` JWT → **403 Forbidden**
- Request with `X-Tenant: nonexistent` → **404**
- Request with invalid/missing JWT → 401 (delegated to `get_current_user`)

---

### M1.6 — Endpoint `GET /api/me`

| Field | Value |
|-------|-------|
| **Effort** | 1 h |
| **Dependencies** | M1.5 |
| **Files to modify** | `motoshop-api/src/motoshop_api/auth/router.py`, `motoshop-api/src/motoshop_api/auth/schemas.py` |
| **Type** | Feature |

#### What to build

**`schemas.py`:**
- Add `MeResponse(BaseModel)` with:
  - `username: str`
  - `role: str`
  - `tenants_allowed: list[str]`
  - `current_tenant: str`
  - `enabled_features: list[str]`

**`auth/router.py`:**
- Add `GET /me` endpoint:
  - Uses `get_tenant()` dep and `get_current_user()` dep
  - Returns `MeResponse` populated from user + tenant config
  - No auth role restriction (any authenticated user can call it)

#### Acceptance Criteria
- `GET /api/me` with `X-Tenant: motoshop` → full feature list (products, stock, sales, etc.)
- `GET /api/me` with `X-Tenant: masvital` → reduced features (descriptive only)
- `GET /api/me` without header → defaults to motoshop features
- `GET /api/me` returns `current_tenant` matching the header

---

### M1.7 — Refactor `DuckDBMetricsRepo` para recibir `tenant`

| Field | Value |
|-------|-------|
| **Effort** | 2 h |
| **Dependencies** | M1.2 (needs `TenantConfig` for `r2_object_key` and `local_db_path`) |
| **Files to modify** | `motoshop-api/src/motoshop_api/metrics/repo_duckdb.py` |
| **Type** | Refactor |

#### What to change

This is the most critical task. The repo currently has hardcoded `motoshop_gold` everywhere:

1. **`__init__(self, tenant: str, tenant_config: TenantConfig | None = None)`**:
   - Build path: `/tmp/{tenant}_gold.duckdb` (from `TenantConfig.local_db_path` if available, else convention)
   - Remove `_DEFAULT_DB_PATH` constant (moved to tenant-specific logic)

2. **`_bootstrap_duckdb_from_r2(db_path, r2_object_key)`** — signature change:
   - Accept `r2_object_key` parameter instead of hardcoded `"motoshop_gold.duckdb"`
   - All R2 download references use the tenant's object key

3. **ALL SQL queries — strip `motoshop_` prefix from table names:**
   - `motoshop_gold_mart_*` → `gold_mart_*`
   - `motoshop_silver_fact_*` → `silver_fact_*`
   - `motoshop_gold_alertas_*` → `gold_alertas_*`
   - `motoshop_gold_forecast_*` → `gold_forecast_*`
   - `motoshop_silver_dim_*` → `silver_dim_*`

   **Full list of table renames in SQL:**
   - `motoshop_gold_mart_ventas_diarias_sku` → `gold_mart_ventas_diarias_sku`
   - `motoshop_gold_mart_inventario_actual` → `gold_mart_inventario_actual`
   - `motoshop_gold_mart_rotacion_abc` → `gold_mart_rotacion_abc`
   - `motoshop_gold_mart_productos_dormidos` → `gold_mart_productos_dormidos`
   - `motoshop_gold_mart_cohortes_clientes` → `gold_mart_cohortes_clientes`
   - `motoshop_gold_alertas_drift` → `gold_alertas_drift`
   - `motoshop_gold_alertas_quiebre` → `gold_alertas_quiebre`
   - `motoshop_gold_forecast_categoria` → `gold_forecast_categoria`
   - `motoshop_silver_fact_ventas` → `silver_fact_ventas`
   - `motoshop_silver_fact_ventas_detalle` → `silver_fact_ventas_detalle`
   - `motoshop_silver_fact_compras` → `silver_fact_compras`
   - `motoshop_silver_fact_compras_detalle` → `silver_fact_compras_detalle`
   - `motoshop_silver_fact_inventario` → `silver_fact_inventario`
   - `motoshop_silver_dim_producto` → `silver_dim_producto`
   - `motoshop_silver_dim_bodega` → `silver_dim_bodega`

4. **`get_duckdb_repo()` factory** — keep for backward compat but deprecate; new callers use `DuckDBMetricsRepo(tenant=...)`

#### Acceptance Criteria
- `DuckDBMetricsRepo(tenant="masvital")._path == "/tmp/masvital_gold.duckdb"`
- `DuckDBMetricsRepo(tenant="motoshop")._path == "/tmp/motoshop_gold.duckdb"`
- Bootstrap downloads `masvital_gold.duckdb` from R2 for masvital tenant
- All SQL queries reference unprefixed tables (e.g., `gold_mart_ventas_diarias_sku`)
- Queries against a missing DuckDB file return zeros gracefully (no crash)

---

### M1.8 — Pipeline: quitar prefijo `motoshop_` de nombres de tablas

| Field | Value |
|-------|-------|
| **Effort** | 3 h |
| **Dependencies** | None (independent of API code) |
| **Files to modify** | `pipeline/silver.py`, `pipeline/gold.py` |
| **Type** | Refactor |

#### What to change

In **`silver.py`** and **`gold.py`**, every `CREATE OR REPLACE TABLE` and `SELECT` reference uses `motoshop_silver_*` or `motoshop_gold_*` prefixes. These must be stripped:

**`silver.py`** (all table names):
- `motoshop_silver_dim_producto` → `silver_dim_producto`
- `motoshop_silver_dim_bodega` → `silver_dim_bodega`
- `motoshop_silver_fact_ventas` → `silver_fact_ventas`
- `motoshop_silver_fact_ventas_detalle` → `silver_fact_ventas_detalle`
- `motoshop_silver_fact_compras` → `silver_fact_compras`
- `motoshop_silver_fact_compras_detalle` → `silver_fact_compras_detalle`
- `motoshop_silver_fact_inventario` → `silver_fact_inventario`

**`gold.py`** (all table names):
- `motoshop_gold_mart_*` → `gold_mart_*`
- `motoshop_gold_alertas_*` → `gold_alertas_*`
- `motoshop_gold_forecast_*` → `gold_forecast_*`
- Corresponding `SELECT` FROM references to silver tables updated

#### Migration note
After this change, the next pipeline run creates unprefixed tables. The old prefixed tables remain unused. No data migration needed — the gold file is fully replaced each run.

#### Acceptance Criteria
- `silver.py` creates `silver_dim_producto`, `silver_fact_ventas`, etc. (no `motoshop_` prefix)
- `gold.py` creates `gold_mart_ventas_diarias_sku`, `gold_alertas_quiebre`, etc.
- All `SELECT` references use the new unprefixed table names
- Pipeline runs end-to-end without errors

---

### M1.9 — Cache key con tenant

| Field | Value |
|-------|-------|
| **Effort** | 1 h |
| **Dependencies** | M1.7 (needs tenant-aware repo), M1.5 (needs `get_tenant` dep) |
| **Files to modify** | `motoshop-api/src/motoshop_api/metrics/router.py` |
| **Type** | Refactor |

#### What to change

1. **`get_repo()` factory** — accept optional `tenant: str` and `tenant_config: TenantConfig`:
   ```python
   def get_repo(tenant: str, tenant_config: TenantConfig) -> MetricsRepoProtocol:
       if settings.data_backend == "duckdb":
           return DuckDBMetricsRepo(tenant=tenant, tenant_config=tenant_config)
       # ... Databricks path unchanged
   ```
   **OR** use `tenant` dep directly in each endpoint.

2. **Each endpoint cache key** — include `{tenant}` prefix:
   ```
   "sales-summary"         → "sales-summary:motoshop" / "sales-summary:masvital"
   "abc-segmentation"      → "abc-segmentation:motoshop"
   "inventory-summary"     → "inventory-summary:motoshop"
   "dormidos:1:50:..."     → "dormidos:motoshop:1:50:..."
   ```
   Pattern: `{endpoint}:{tenant}:{params}`

3. **Each endpoint signature** — add `get_tenant()` dep and pass tenant to repo creation + cache key.

#### Acceptance Criteria
- `GET /api/metrics/sales-summary` with `X-Tenant: motoshop` uses cache key `sales-summary:motoshop`
- Same request with `masvital` uses `sales-summary:masvital`
- Different tenants don't share cached data (isolation)
- Cache clear endpoint works for all tenants

---

### M1.10 — Refactor OTROS módulos que abren DuckDB

| Field | Value |
|-------|-------|
| **Effort** | 3 h |
| **Dependencies** | M1.5 (needs `get_tenant` dep), M1.7 (needs tenant-aware repo pattern) |
| **Files to modify** | See list below |
| **Type** | Refactor |

#### Modules to modify

| Module | What changes | DuckDB? |
|--------|-------------|---------|
| `products/router.py` | `_ensure_duckdb_file()` and semantic search use tenant's DuckDB path | ✅ |
| `alerts/router.py` | `get_repo()` creates `DuckDBAlertsRepo` with tenant path | ✅ |
| `alerts/repo.py` | `DuckDBAlertsRepo.__init__` accepts `tenant: str`; SQL table prefix stripped | ✅ |
| `forecast/router.py` | `get_repo()` passes tenant path (minimal — already returns 410) | ✅ |
| `llm/tools.py` | `ToolExecutor.__init__` accepts `tenant: str`, opens `{tenant}_gold.duckdb` | ✅ |
| `llm/briefing.py` | `BriefingGenerator.__init__` accepts `tenant: str` | ✅ |
| `llm/router.py` | `_get_db_path(tenant)` tenant-aware; briefing and forecast explainer pass tenant | ✅ |
| `llm/qa_chat.py` | `get_qa_chat()` accepts `tenant: str` or reads from request context | ✅ |
| `health/router.py` | `_get_db_path()` accepts optional `tenant` param | ✅ |
| `admin/router.py` | `_get_duckdb_path()` accepts `tenant`; `/data/refresh` downloads tenant's R2 file | ✅ |
| `data_catalog/router.py` | `_get_con()` uses tenant DuckDB path; `LAYER_RULES` and `data_lineage` update prefixes | ✅ |
| `stock/router.py` | **No changes** — uses MySQL, not DuckDB | ❌ |
| `sales/router.py` | **No changes** — uses MySQL, not DuckDB | ❌ |
| `pipeline_runs/repo.py` | **No changes for M1** — shared across tenants (tenant column comes in M4) | ❌ |

#### For each module that opens DuckDB

1. Replace hardcoded `/tmp/motoshop_gold.duckdb` or `settings.duckdb_path` with `{tenant}_gold.duckdb` convention (via `TenantConfig.local_db_path`)
2. Inject `get_tenant()` dependency into endpoints that need DuckDB access
3. For the DB path helpers: accept `tenant: str` parameter
4. All SQL queries: strip `motoshop_` prefix from table names (same transformation as M1.7)

#### Acceptance Criteria
- Products semantic search opens `{tenant}_gold.duckdb` based on request tenant
- Alerts repo opens correct DuckDB for tenant
- LLM tools, briefing, and Q&A chat all open tenant-specific DuckDB
- Health data-freshness reports on tenant's file
- Admin data refresh downloads tenant's R2 object
- Data catalog inspects tenant-specific tables with unprefixed names
- Stock and sales routers work unchanged (MySQL)

---

### M1.11 — Tests

| Field | Value |
|-------|-------|
| **Effort** | 2 h |
| **Dependencies** | M1.1 through M1.10 |
| **Files to modify** | `tests/` (multiple files) |
| **Type** | Testing |

#### Test scenarios

| # | Scenario | Approach |
|---|----------|----------|
| T01 | Login returns `tenants_allowed` | POST `/api/auth/login` as admin, decode JWT, assert `tenants_allowed: ["motoshop", "masvital"]` |
| T02 | `/api/me` returns features per tenant | GET `/api/me` with `X-Tenant: motoshop` → full features; with `X-Tenant: masvital` → reduced |
| T03 | Cross-tenant 403 | JWT of `gerente1` + `X-Tenant: masvital` → 403 |
| T04 | Missing DuckDB returns zeros | Mock missing `masvital_gold.duckdb`, GET abc-segmentation → zeros, no 500 |
| T05 | Default tenant | Request without `X-Tenant` → defaults to `motoshop` |
| T06 | Cache isolation | Same endpoint, different tenants → different cache keys, no collision |
| T07 | All endpoints work with both tenants | Smoke-test each endpoint with `motoshop` and `masvital` headers |
| T08 | Backward compat: no header | All existing endpoints work exactly as before without `X-Tenant` |

#### Acceptance Criteria
- All 8 scenarios pass
- No regression on existing MotoShop functionality (tested without `X-Tenant`)
- Tests can run in CI without external dependencies (mocked/missing DuckDB gracefully handled)

---

### M1.12 — Deploy Render + validar prod

| Field | Value |
|-------|-------|
| **Effort** | 0.5 h |
| **Dependencies** | M1.11 |
| **Files** | — (deploy config) |
| **Type** | Deploy |

#### Steps
1. Merge feature branch to `main`
2. Deploy to Render (automatic via Git push)
3. Smoke test: login as `admin`, call `/api/me` with both tenants
4. Smoke test: existing frontend (no `X-Tenant`) works → default `motoshop`
5. Verify pipeline ran once to create unprefixed tables (or trigger manually)

#### Acceptance Criteria
- Production `/api/me` returns correct features for both tenants
- All existing MotoShop dashboard endpoints work without header
- No 500s in Render logs post-deploy

---

## Review Workload Forecast

### Total Files Changed

| Type | Count |
|------|-------|
| **NEW** | 3 |
| **MODIFY** | 22 |
| **TOTAL** | 25 |

### Files by task

| Task | Files | Est. added lines | Est. modified lines |
|------|-------|------------------|-------------------|
| M1.1 | `tenants.yaml` (NEW) | 35 | — |
| M1.2 | `tenants.py` (NEW), `config.py` | 45 | 3 |
| M1.3 | `users.py`, `users.yaml` | — | 10 |
| M1.4 | `jwt.py`, `auth/router.py` | — | 40 |
| M1.5 | `tenant_dep.py` (NEW) | 30 | — |
| M1.6 | `auth/router.py`, `auth/schemas.py` | — | 50 |
| M1.7 | `metrics/repo_duckdb.py` | — | 180 |
| M1.8 | `pipeline/silver.py`, `pipeline/gold.py` | — | 110 |
| M1.9 | `metrics/router.py` | — | 25 |
| M1.10 | 11 modules (products, alerts, forecast, llm/*, health, admin, data_catalog) | — | 145 |
| M1.11 | `tests/` | 80 | 20 |
| M1.12 | — | — | — |
| **TOTAL** | **25 files** | **~190** | **~583** |

**Total estimated changed lines: ~773** (190 new + 583 modified)

### 400-Line Budget Check

| Criterion | Status |
|-----------|--------|
| Estimated total | **~773 lines** |
| 400-line threshold | **EXCEEDED (1.9×)** |

> **Veredicto:** Este cambio excede significativamente el límite de 400 líneas. La refactorización masiva de `repo_duckdb.py` (M1.7) y del pipeline (M1.8) representan ~290 líneas juntas. Las queries SQL están distribuidas a lo largo de un archivo de 1282 líneas; tocarlas requiere cambiar ~180 líneas de SQL.

### Chained PR Strategy — RECOMENDADA

Por la magnitud del cambio, se recomienda **dividir en 3 PRs encadenados**:

| Chain | Tasks | Estimated lines | Review focus |
|-------|-------|-----------------|--------------|
| **PR 1** — Foundation | M1.1, M1.2, M1.3, M1.4, M1.5 | ~165 | Auth: tenants config, user model, JWT, tenant dependency |
| **PR 2** — Pipeline + Repo | M1.7, M1.8 | ~290 | SQL: prefix stripping, tenant path, bootstrap |
| **PR 3** — Integration | M1.6, M1.9, M1.10, M1.11, M1.12 | ~320 | Endpoints: /api/me, cache, all modules wired, tests |

**Racional:** PR1 es puramente auth/config y no toca ni DuckDB ni endpoints de negocio. PR2 es el cambio más riesgoso (queries SQL + pipeline) y merece revisión aislada. PR3 conecta todo y añade tests.

Si no se quiere encadenar, alternativa: PR único con **revisión exhaustiva de no-cross-tenant-leak** como gate.

### Decisiones Pendientes Antes de Apply

| # | Decisión | Opciones | Recomendación |
|---|----------|----------|---------------|
| D01 | **Pipeline migration order** | (a) Run old pipeline one last time before merging, then deploy + new pipeline creates unprefixed tables | **(a)** — El pipeline sobreescribe completo el archivo DuckDB, así que correr el nuevo pipeline una vez post-deploy es suficiente |
| D02 | **Stock/sales routers** | (a) Skip (use MySQL, no DuckDB) vs (b) still add `get_tenant()` dep for consistency | **(a)** — MySQL routers no abren DuckDB; añadir tenant dep solo si se usara en M4 para logging. Postergar. |
| D03 | **Chained PRs** | (a) 3 chained PRs vs (b) single large PR | **(a)** — 773 líneas es mucho para una sola review. Dividir en foundation/pipeline/integration |
| D04 | **Default tenant removal timing** | (a) Remove in M2 vs (b) remove in M4 | **(a)** — Forzar tenant explícito después de que frontend inyecte header. MT-09 lo define así. |

> **⚠️ Se requiere decisión del PO/Reviewer antes de apply:** confirmar estrategia de PRs encadenados y orden de migración del pipeline.
