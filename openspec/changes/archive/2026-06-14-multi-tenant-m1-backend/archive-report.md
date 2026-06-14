# Archive Report

**Change**: multi-tenant-m1-backend
**Archived**: 2026-06-14
**Archive path**: `openspec/changes/archive/2026-06-14-multi-tenant-m1-backend/`

## Change Summary

Convert the API from single-tenant (`motoshop`) to multi-tenant: accept `X-Tenant` header, route to the correct DuckDB file, validate via JWT claims, keep MotoShop frontend working unchanged.

## Tasks Completion

| Task | Status | Description |
|------|--------|-------------|
| M1.1 | ✅ Complete | Create `tenants.yaml` |
| M1.2 | ✅ Complete | Load tenants in `config.py` + `tenants.py` |
| M1.3 | ✅ Complete | Add `tenants_allowed` to `User` model |
| M1.4 | ✅ Complete | JWT payload includes `tenants_allowed` claim |
| M1.5 | ✅ Complete | Dependency `get_tenant(request, user)` |
| M1.6 | ✅ Complete | Endpoint `GET /api/me` |
| M1.7 | ✅ Complete | Refactor `DuckDBMetricsRepo` for tenant |
| M1.8 | ✅ Complete | Pipeline remove `motoshop_` prefix from table names |
| M1.9 | ✅ Complete | Cache key with tenant |
| M1.10 | ✅ Complete | Refactor other DuckDB modules |
| M1.11 | ✅ Complete | Tests |
| M1.12 | ✅ Complete | Deploy Render + validate prod |

**All 12 tasks: ✅ Complete**

## Verification

- **Tests**: 47/47 passing
- **Merged**: main (commit ffa5bde) — pushed

## Specs Sync

| Domain | Action | Details |
|--------|--------|---------|
| `multi-tenant-m1-backend` | Already in place (main spec) | No delta merge needed — spec IS the source of truth |

## Archive Contents

| Artifact | Path |
|----------|------|
| Spec | `openspec/changes/archive/2026-06-14-multi-tenant-m1-backend/specs/multi-tenant-m1-backend.md` |
| Design | `openspec/changes/archive/2026-06-14-multi-tenant-m1-backend/design.md` |
| Tasks | `openspec/changes/archive/2026-06-14-multi-tenant-m1-backend/tasks.md` |
| Archive Report | `openspec/changes/archive/2026-06-14-multi-tenant-m1-backend/archive-report.md` |

## Source of Truth

- `openspec/specs/multi-tenant-m1-backend.md` — reflects final state (unchanged from spec)

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
