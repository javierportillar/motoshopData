# ADR-0023 · Migrar read backend a DuckDB (reemplazo de Databricks SQL Warehouse)

- **Fecha:** 2026-06-06
- **Status:** Accepted
- **Deciders:** Revisor + Dev D (Javier) — Sprint 0→3 completados, commit `d2b8767`
- **Referencia:** [plan-v1.5-duckdb.md](../plan-v1.5-duckdb.md)

---

## 1 · Contexto

El 2026-05-31 Databricks revocó el acceso Serverless al Free Edition. Esto dejó el warehouse SQL (`43bc044eaef4cca4`) en estado intermitente: arrancaba temporalmente pero no era fiable para producción. Como resultado, 10/17 endpoints de métricas devolvían HTTP 500 por timeout.

La app MotoShop depende de los gold marts para su operación 24/7. Con Databricks caído, los dashboards del PWA y las consultas del frontend quedaban sin datos.

**Alternativas evaluadas:**

| Opción | Costo | Latencia | Disponibilidad | Complejidad |
|--------|-------|----------|----------------|-------------|
| Pagar Databricks Serverless | ~$0.70/hora ($500+/mes) | 500-3000ms | Alta | Baja (ya implementado) |
| Migrar a DuckDB local + R2 | $0/mes (R2 free tier) | 13ms avg | Alta (archivo local) | Media (port SQL) |
| PostgreSQL auto-hosted | ~$15/mes (VPS) | 50-200ms | Media | Alta (migración schema) |

---

## 2 · Decisión

✅ **Migrar el read path a DuckDB** con archivo almacenado en Cloudflare R2.

### Arquitectura

```
┌──────────────┐     ┌─────────────┐     ┌────────────┐
│ pipeline     │────▶│ Cloudflare  │────▶│ Render API │
│ run_all.py   │     │ R2 bucket   │     │ DuckDB     │
│ (Linux/Mac)  │     │ motoshop-gold│    │ read-only  │
└──────────────┘     └─────────────┘     └────────────┘
       ▲                                       │
       │                                       ▼
  MySQL bronze                          /api/metrics/*
  (Windows, Dev W)                      17 endpoints
                                        HTTP 200, 13ms
```

### Por qué DuckDB y no otro motor

1. **Zero-dependency**: archivo único `.duckdb`, sin servidor, sin daemon
2. **SQL compatibility**: `DATE_FORMAT → STRFTIME`, `ADD_MONTHS → INTERVAL`, etc. — 95% del SQL Databricks se tradujo mecánicamente
3. **Read-only en Render**: la API abre el archivo en `read_only=True`, sin locks, multi-request concurrente
4. **Bootstrap from R2**: cold start descarga automática via `boto3`, sin montaje de volumen

### Implementación (4 sprints)

| Sprint | Commit | Qué |
|--------|--------|-----|
| 0 | `9a901b4` | Spike sales_summary 0-diff, bootstrap R2 |
| 1 | `47f06f6` | Pipeline bronze→silver(7)→gold(10) cableado |
| 2 | `a072b9c` | 14 endpoints DuckDBMetricsRepo |
| 3 | `d2b8767` | Admin refresh endpoint, health DuckDB, COALESCE fix |

---

## 3 · Consecuencias

### Positivas

| Métrica | Before (Databricks) | After (DuckDB) |
|---------|---------------------|----------------|
| Latencia avg | 500ms–timeout (3s+) | **13ms** |
| Endpoints 200 | 7/17 (41%) | **16/16** (100%) |
| Costo mensual infra | $0 (Free Edition) | **$0** (R2 free tier) |
| Cold start | 0ms (warehouse siempre "on") | ~2s (download 7MB de R2) |
| Determinismo | No (CURRENT_DATE warehouse) | Sí (MAX(business_date)) |
| Refresh | No aplica (live query) | POST /api/admin/data/refresh |

### Negativas

- **Read-only**: las queries no pueden actualizar datos (pero el read path siempre fue read-only)
- **File freshness**: depende de que el pipeline corra y suba a R2. Si el pipeline se atrasa, los datos se estancan → `/health/data-freshness` monitorea esto
- **No live updates**: Databricks consultaba los marts en vivo. DuckDB lee un snapshot. El refresh es vía Scheduled Task Windows (02:00 COL) o manual (`POST /api/admin/data/refresh`)
- **Windows pipeline**: el pipeline `run_all.py` requiere Python 3.11+ + MySQL accesible. Actualmente corre en Linux/Mac con seed interino. Para producción Windows, necesita que Dev W tenga MySQL local

### Rollback

Si DuckDB falla en producción, el rollback es inmediato:
1. Cambiar `DATA_BACKEND=databricks` en Render env vars
2. Redeploy → la API vuelve a usar `RealMetricsRepo`
3. No hay migración de datos que revertir (el archivo DuckDB y los gold marts Databricks son independientes)

---

## 4 · Referencias

- [docs/plan-v1.5-duckdb.md](../plan-v1.5-duckdb.md) — plan de migración completo
- [docs/audit/raw_responses.json](../audit/raw_responses.json) — gold standard pre-V1.5 (snapshot Databricks)
- [infra/AUTO_PULL_SETUP.md](../../infra/AUTO_PULL_SETUP.md) — sección V1.5 Refresh para Dev W
- [infra/refresh_v15.ps1](../../infra/refresh_v15.ps1) — PowerShell Scheduled Task
