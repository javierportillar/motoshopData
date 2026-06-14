# Multi-Tenant — Sprint M1 (Backend) Specification

## Purpose

Convert the API from single-tenant (`motoshop`) to multi-tenant: accept `X-Tenant` header, route to the correct DuckDB file, validate via JWT claims, keep MotoShop frontend working unchanged.

## Functional Requirements

| ID | Requirement | Task |
|----|------------|------|
| F01 | `tenants.yaml` declares tenants with `id`, `nombre`, `enabled_features[]`, `local_db_path`, `r2_object_key`. | M1.1 |
| F02 | A loader SHALL parse `tenants.yaml` at boot and expose `get_tenant(id)` / `list_tenants()`. Missing file logs a warning. | M1.2 |
| F03 | `User` SHALL include `tenants_allowed: list[str]`. `users.yaml` SHALL include the field. | M1.3 |
| F04 | `create_access_token()` SHALL embed `tenants_allowed` claim from the User model. | M1.4 |
| F05 | A dependency `get_tenant(request, user)` SHALL read `X-Tenant`, default `motoshop`, verify user access, reject 403 if not allowed. | M1.5 |
| F06 | `GET /api/me` SHALL return `{username, role, tenants_allowed, current_tenant, enabled_features}`. | M1.6 |
| F07 | `DuckDBMetricsRepo(tenant)` SHALL open `{tenant}_gold.duckdb`. Bootstrap from R2 downloads `{tenant}_gold.duckdb`. | M1.7 |
| F08 | All SQL in repo_duckdb.py SHALL drop the `motoshop_` prefix from table names. Pipeline SHALL create tables without it. | M1.8 |
| F09 | `_cached_or_fetch()` key SHALL include `{tenant}` (e.g. `sales-summary:motoshop`). | M1.9 |
| F10 | `products`, `stock`, `sales`, `alerts`, `forecast`, `llm/tools.py` SHALL accept `tenant` and open `{tenant}_gold.duckdb`. | M1.10 |

## Non-Functional Requirements

| ID | Requirement |
|----|------------|
| N01 | Requests WITHOUT `X-Tenant` SHALL default to `motoshop`. Existing frontend unchanged. |
| N02 | Missing DuckDB file SHALL NOT crash — return empty data (ABC → `bucket_a: 0`, etc.). |
| N03 | Cross-tenant data leak SHALL be impossible — each request opens the tenant's own file. |

## Scenarios

### S01: Login returns tenants_allowed
GIVEN user `admin` with `tenants_allowed: [motoshop, masvital]` — WHEN `POST /api/auth/login` — THEN JWT payload SHALL contain `tenants_allowed: ["motoshop", "masvital"]`.

### S02: /api/me returns features per tenant
GIVEN valid JWT + `X-Tenant: masvital` — WHEN `GET /api/me` — THEN response SHALL include `current_tenant: "masvital"` and `enabled_features` matching MasVital's list (descriptive only).

### S03: Cross-tenant 403
GIVEN JWT with `tenants_allowed: [motoshop]` — WHEN request with `X-Tenant: masvital` — THEN `403 Forbidden`.

### S04: Missing DuckDB returns zeros
GIVEN no `masvital_gold.duckdb` — WHEN `GET /api/metrics/abc-segmentation` with `X-Tenant: masvital` — THEN response has `bucket_a.num_skus=0` etc., not 500.

### S05: Default tenant
GIVEN valid JWT, no `X-Tenant` header — WHEN any endpoint — THEN `current_tenant` defaults to `motoshop`.

### S06: Cache isolation
GIVEN cached `sales-summary:motoshop` — WHEN request for `masvital` — THEN cache key `sales-summary:masvital` SHALL NOT collide.

## Acceptance Criteria per Task

| Task | AC |
|------|----|
| M1.1 | `tenants.yaml` exists with both tenants (motoshop full features, masvital descriptive). |
| M1.2 | `config.py` loads YAML; `get_tenant()` handles missing file. |
| M1.3 | `User` model has `tenants_allowed`; `users.yaml` updated for admin, gerente1, vendedor1. |
| M1.4 | JWT decode shows `tenants_allowed` claim. |
| M1.5 | Unallowed tenant → 403; no header → motoshop. |
| M1.6 | `/api/me` returns correct features for both tenants. |
| M1.7 | `DuckDBMetricsRepo(tenant="masvital")` opens `/tmp/masvital_gold.duckdb`. |
| M1.8 | All queries use un-prefixed gold/silver table names. |
| M1.9 | Cache key format `{endpoint}:{tenant}:{params}`. |
| M1.10 | All six modules accept tenant param and open correct DuckDB. |
| M1.11 | Tests pass: same endpoints work with and without `X-Tenant: motoshop`. |
| M1.12 | Deployed to Render; smoke test `/api/me` with MotoShop returns full features. |
