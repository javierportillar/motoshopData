# Data Freshness Check · 2026-05-29

## Tests (unit, mockeados)

```
tests/test_health_freshness.py::TestDataFreshness::test_ok_status PASSED
tests/test_health_freshness.py::TestDataFreshness::test_warn_status PASSED
tests/test_health_freshness.py::TestDataFreshness::test_stale_status PASSED
tests/test_health_freshness.py::TestDataFreshness::test_critical_status PASSED
tests/test_health_freshness.py::TestDataFreshness::test_no_manifests PASSED
tests/test_health_freshness.py::TestDataFreshness::test_no_databricks_config PASSED
tests/test_health_freshness.py::TestDataFreshness::test_databricks_error PASSED

7 passed in 0.11s
```

## Suite completa (sin integración)

```
31 passed in 15.50s
```

## Archivos creados/modificados

| Archivo | Cambio |
|---------|--------|
| `motoshop-app/api/src/motoshop_api/health/__init__.py` | Nuevo módulo |
| `motoshop-app/api/src/motoshop_api/health/router.py` | Endpoint `GET /health/data-freshness` |
| `motoshop-app/api/src/motoshop_api/config.py` | +3 campos: `databricks_host`, `databricks_token`, `databricks_volume_path` |
| `motoshop-app/api/src/motoshop_api/main.py` | Wire-up del health router |
| `motoshop-app/api/pyproject.toml` | +`databricks-sdk>=0.30` |
| `motoshop-app/api/tests/test_health_freshness.py` | 7 tests mockeados |
| `notebooks/bronze/06_pipeline_health.py` | Notebook Databricks de lag monitor |

## Endpoint status logic

| Lag | Status |
|-----|--------|
| < 2 h | OK |
| 2-6 h | WARN |
| 6-24 h | STALE |
| > 24 h | CRITICAL |
| Sin manifests | CRITICAL |
| Sin credenciales Databricks | ERROR |
| Excepción Databricks | ERROR |
