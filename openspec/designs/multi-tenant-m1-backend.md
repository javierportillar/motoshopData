# Design: Multi-Tenant Sprint M1 — Backend

## Technical Approach

Single FastAPI backend (MT-01) that dispatches requests by `X-Tenant` header (default `motoshop` for backward compat, MT-09). Each tenant opens its own DuckDB file at `/tmp/{tenant}_gold.duckdb`. Auth layer validates tenant access via a new JWT claim `tenants_allowed`. Cache keys are prefixed with `{tenant}:`. DuckDB table prefixes (`motoshop_gold_*`, `motoshop_silver_*`) are stripped since tenancy is now file-level, not table-level.

## Architecture Decisions

| ID | Decision | Rationale | Trade-off |
|----|----------|-----------|-----------|
| MT-04 | `X-Tenant` header + JWT `tenants_allowed` claim | Switch tenant without re-login; validating both layers prevents leaks | Frontend must inject header in every request |
| MT-06 | `tenants.yaml` with `enabled_features` | Feature gating per tenant without code changes | Frontend must respect `/api/me` response |
| MT-09 | Default tenant `motoshop` when header absent | Zero breakage for current frontend during M1 | Must remove after M2 to force explicit tenant |
| MT-01 | Single backend, file-per-tenant DuckDB | Cero duplication, $0 infra scales to N tenants | More complex routing (6 files touched) |

## Data Flow

```
Request ──→ FastAPI middleware
              │
              ├── get_current_user()     ← JWT Bearer
              ├── get_tenant()           ← X-Tenant header
              │     reads X-Tenant, validates user.tenants_allowed
              │     returns tenant id + TenantConfig
              │
              ▼
         Router endpoint
              │
              ▼
         get_repo(tenant) → DuckDBMetricsRepo(tenant)
              │     opens /tmp/{tenant}_gold.duckdb
              │     downloads from R2 if missing (r2_object_key per tenant)
              │
              ▼
         _cached_or_fetch("{endpoint}:{tenant}:{params}", ...)
              │     isolated cache per tenant
              │
              ▼
         Response
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `motoshop-app/api/tenants.yaml` | Create | Tenant registry (MotoShop + MasVital) with features, paths, R2 keys |
| `motoshop-app/api/src/motoshop_api/tenants.py` | Create | `TenantConfig` model, loader, `get_tenant()`, `list_tenants()`, feature resolver |
| `motoshop-app/api/src/motoshop_api/auth/tenant_dep.py` | Create | `get_tenant()` dependency — reads `X-Tenant`, default `motoshop`, validates against JWT `tenants_allowed`, returns `403` if denied |
| `motoshop-app/api/config.py` | Modify | Add `tenants_file_path` setting; trigger tenant loader at boot |
| `motoshop-app/api/users.yaml` | Modify | Add `tenants_allowed` field to admin (`[motoshop, masvital]`), gerente1 (`[motoshop]`), vendedor1 (`[motoshop]`) |
| `motoshop-app/api/src/motoshop_api/auth/users.py` | Modify | Add `tenants_allowed: list[str] = ["motoshop"]` to `User` model |
| `motoshop-app/api/src/motoshop_api/auth/jwt.py` | Modify | `create_access_token()` embeds `user.tenants_allowed` as claim in payload |
| `motoshop-app/api/src/motoshop_api/auth/router.py` | Modify | Add `GET /api/me` returning `{username, role, tenants_allowed, current_tenant, enabled_features}` |
| `motoshop-app/api/src/motoshop_api/auth/schemas.py` | Modify | Add `MeResponse` schema with `current_tenant` and `enabled_features` |
| `motoshop-app/api/src/motoshop_api/metrics/repo_duckdb.py` | Modify | `__init__` takes `tenant: str`, builds path `/tmp/{tenant}_gold.duckdb`; `_bootstrap_duckdb_from_r2()` uses tenant's `r2_object_key`; ALL queries strip `motoshop_` prefix from table names |
| `motoshop-app/api/src/motoshop_api/metrics/router.py` | Modify | `get_repo()` creates `DuckDBMetricsRepo(tenant)` using `get_tenant()` dep; cache keys become `{endpoint}:{tenant}:{params}` |
| `motoshop-app/api/src/motoshop_api/llm/tools.py` | Modify | `ToolExecutor.__init__` takes `tenant: str`, connects to `{tenant}_gold.duckdb`; strip table prefixes |
| `motoshop-app/api/src/motoshop_api/llm/briefing.py` | Modify | `BriefingGenerator.__init__` takes tenant; strip table prefixes |
| `motoshop-app/api/src/motoshop_api/llm/router.py` | Modify | `_get_db_path()` becomes `_get_db_path(tenant)`, piped from `get_tenant()` dep |
| `motoshop-app/api/src/motoshop_api/products/router.py` | Modify | `_ensure_duckdb_file` and semantic search use tenant's DuckDB path |
| `motoshop-app/api/src/motoshop_api/stock/router.py` | Modify | Uses MySQL, not DuckDB — no changes needed |
| `motoshop-app/api/src/motoshop_api/sales/router.py` | Modify | Same as stock — MySQL, no changes |
| `motoshop-app/api/src/motoshop_api/alerts/router.py` | Modify | `get_repo()` creates `DuckDBAlertsRepo` with tenant path; cache key tenant-prefixed |
| `motoshop-app/api/src/motoshop_api/forecast/router.py` | Modify | `get_repo()` uses tenant path (forecast per-SKU already discontinued) |
| `motoshop-app/api/src/motoshop_api/health/router.py` | Modify | `_get_db_path()` accepts optional tenant param; `/health/data-freshness` reads tenant from query param |
| `motoshop-app/api/src/motoshop_api/admin/router.py` | Modify | `_get_duckdb_path()` with tenant; `data_status` queries tenant file; `data_refresh` downloads tenant's R2 object |
| `motoshop-app/api/src/motoshop_api/data_catalog/router.py` | Modify | Uses tenant's DuckDB path; `_classify_layer()` strips `motoshop_` prefix recognition |
| `motoshop-app/api/src/motoshop_api/main.py` | Modify | Load tenants at startup alongside users; inject `TenantConfig` into app state |
| `pipeline/silver.py` | Modify | Create tables without `motoshop_` prefix |
| `pipeline/gold.py` | Modify | Create tables without `motoshop_` prefix |

## Interfaces / Contracts

### `TenantConfig` (new — `tenants.py`)

```python
class TenantConfig(BaseModel):
    id: str
    nombre: str
    descripcion: str
    color_brand: str
    logo: str
    r2_object_key: str
    local_db_path: str
    mysql_source: str
    telegram_chat_id_gerente: str | None
    enabled_features: list[str]
    briefing: BriefingConfig
```

### `User` extended (modified — `users.py`)

```python
class User(BaseModel):
    username: str
    hashed_password: str
    email: str
    role: str
    tenants_allowed: list[str] = ["motoshop"]  # NEW — default for backward compat
```

### `get_tenant` dependency (new — `tenant_dep.py`)

```python
async def get_tenant(
    request: Request,
    user: User = Depends(get_current_user),
) -> tuple[str, TenantConfig]:
    """Reads X-Tenant, defaults to 'motoshop', validates against
    user.tenants_allowed. Returns (tenant_id, config) or 403."""
```

### Cache key pattern

```
Key: "{endpoint}:{tenant}:{args}"
Example: "sales-summary:motoshop"  vs  "sales-summary:masvital"
```

## DuckDB Routing & Bootstrap

Per tenant, `DuckDBMetricsRepo.__init__(tenant)`:
1. Resolves `r2_object_key` from `TenantConfig`
2. Builds local path: `/tmp/{tenant}_gold.duckdb`
3. Calls `_bootstrap_duckdb_from_r2(path, r2_object_key)` if file missing
4. Opens in read-only mode

All SQL queries drop the `motoshop_` prefix:
```
motoshop_gold_mart_ventas_diarias_sku    → gold_mart_ventas_diarias_sku
motoshop_silver_fact_ventas              → silver_fact_ventas
motoshop_gold_alertas_quiebre            → gold_alertas_quiebre
motoshop_silver_dim_producto             → silver_dim_producto
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `get_tenant` 3 scenarios | Valid header, missing (→ default), disallowed (→ 403) |
| Unit | JWT `tenants_allowed` claim | Decode token, assert claim matches user |
| Unit | DuckDB path from tenant | `DuckDBMetricsRepo("masvital")._path` == `/tmp/masvital_gold.duckdb` |
| Unit | Cache isolation | Same key with different tenants yields different entries |
| Integration | `GET /api/me` with `X-Tenant: motoshop` | Full features; all current endpoints work |
| Integration | `GET /api/me` with `X-Tenant: masvital` | Reduced features only |
| Integration | `ABC segmentation` with masvital | Returns zeros, no crash when file missing |
| Integration | `GET /api/me` without header | Defaults to motoshop |
| Smoke | Full deploy + prod | Login admin, `/api/me` returns correct tenant |

## Migration / Rollout

**Data migration:** Pipeline must run once to recreate gold tables without `motoshop_` prefix. Run with `TENANT=motoshop` — new `silver.py`/`gold.py` create `gold_mart_*`/`silver_fact_*` tables. Old prefixed tables remain until next refresh (unused).

**Rollback:** Revert backend commit. Delete or keep `tenants.yaml`. Pipeline old version recreates `motoshop_gold_*` tables. Cache expires in 5 min.

**Cold-start:** First request for a new tenant downloads DuckDB from R2 (~50 MB, ~3-5s). `/api/me` is unaffected (reads config, not DuckDB).

**Backward compat (MT-09):** Request without `X-Tenant` defaults to `motoshop`. All existing endpoints work unchanged.

## Open Questions

- [ ] Pipeline migration order: run old pipeline one more time or force new pipeline first? **Decision: run new pipeline — gold file gets overwritten.**
- [ ] `pipeline_runs.duckdb` — shared across tenants or per tenant? **Decision: shared for M1 (tenant column in M4).**
