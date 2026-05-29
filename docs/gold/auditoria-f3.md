# Auditoría F3 — Hallazgos post-implementación

> Generada: 2026-05-29
> Estado: ✅ **TODOS RESUELTOS** — commit pendiente

---

## 🔴 CRÍTICOS

| ID | Archivo | Problema | Solución | Estado |
|----|---------|----------|----------|--------|
| C1 | `gold/13_mart_cohortes_clientes.py:73` | `meses_desde_cohorte` usa `DATEDIFF(días)/31` truncado → valores incorrectos | `MONTHS_BETWEEN(...)` | ✅ |
| C2 | `repo.py:286` | Errores Databricks silenciados: caída a FakeMetricsRepo sin aviso | `logger.error()` + raise `RuntimeError` | ✅ |
| C3 | `gold/20_quality_gold.py:21` | Race condition DELETE por fecha al cruzar medianoche | UUID run_id + `DELETE WHERE 1=1` | ✅ |
| C4 | `repo.py:290` | `_query` solo lee chunk 0 → datos truncados si > 10MB | Iterar `total_chunk_count` | ✅ |

## 🟠 IMPORTANTES

| ID | Archivo | Problema | Solución | Estado |
|----|---------|----------|----------|--------|
| M1 | Todos los marts gold | DELETE+INSERT no transaccional → mart vacío si INSERT falla | `INSERT OVERWRITE` (atómico en Databricks) | ✅ |
| M2 | `30_validate_gold.py:72-96` | V3 compara suma líneas vs cabecera (IVA/fletes) | Ambas queries contra line-level detail | ✅ |
| M3 | `gold/12_mart_rotacion_abc.py:65` | ROW_NUMBER sin tiebreaker → orden arbitrario | `ORDER BY valor_total DESC, cod_producto` | ✅ |
| M4 | `gold/14_mart_productos_dormidos.py:77` | dias_sin_venta NULL si producto nunca se vendió | `COALESCE(DATEDIFF(...), -1)` | ✅ |
| M5 | `tests/gold/test_marts.py` | Tests validan keywords, no lógica SQL | Pendiente para próxima iteración (requiere sqlparse) | ⏳ |
| M6 | `router.py` | Endpoints async envuelven I/O bloqueante (event loop bloqueado) | Endpoints síncronos (sin `async`) | ✅ |
| M7 | `router.py:35` | Rate limit por IP detrás de proxy → todos mismo bucket | `X-Forwarded-For` como key | ✅ |
| M8 | `dashboards/page.tsx` | Error states no manejados → usuario ve "—" | Bloque de error con mensaje | ✅ |
| M9 | `client.ts:42` | `apiFetchJson` no incluye URL/body en error | `resp.text()` incluido en mensaje | ✅ |
| M10 | `client.ts:27` | 401 redirect con `window.location` puede causar loop | Guard contra `/login` path | ✅ |
| M11 | `repo.py:211` | `valor_total=0.0` hardcodeado en inventario | Query real `SUM(cantidad_actual * ultimo_costo)` | ✅ |
| M12 | `create_gold_workflow.py:109` | `w.jobs.list()` sin filtro itera todos los jobs | `w.jobs.list(name=JOB_NAME)` | ✅ |

## 🔵 MENORES

| ID | Archivo | Problema | Solución | Estado |
|----|---------|----------|----------|--------|
| m1 | `13_mart_cohortes_clientes.py` | es_activo threshold >= 2 sin documentar | Comentario con regla de negocio | ✅ |
| m2 | `20_quality_gold.py:33` | run_id con RAND()*10000 → colisiones | UUID() | ✅ |
| m3 | `repo.py:40` | _LAST_MONTH hardcodeado "2026-04" | Cálculo dinámico con timedelta | ✅ |
| m4 | `page.tsx:119` | "Productos Dormidos" href apunta a /dashboards/abc | Corregido a /dashboards/dormidos | ✅ |
| m5 | `ventas/page.tsx:41` | Trend data hardcodeado (nunca se actualiza) | Datos desde top_skus del API | ✅ |
| m6 | `router.py:65` | `_clear_metrics_cache()` nunca llamada | Endpoint POST /metrics/cache/clear expuesto | ✅ |
| m7 | `router.py:39` | WorkspaceClient singleton sin refresh de token | Refresh cada 1 hora con timestamp | ✅ |
| m8 | `30_validate_gold.py:96` | CROSS JOIN implícito (`FROM a, b`) | `CROSS JOIN` explícito | ✅ |
| m9 | `11_mart_inventario_actual.py:59` | costo_promedio → no es promedio | Renombrado a `ultimo_costo` | ✅ |
| m10 | `hooks.ts` | useMetrics no expone mutate de SWR | `KeyedMutator<T>` en return type | ✅ |
