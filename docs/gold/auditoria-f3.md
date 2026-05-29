# Auditoría F3 — Hallazgos post-implementación

> Generada: 2026-05-29
> Próximo paso: resolver todos los puntos y entregar al revisor master

---

## 🔴 CRÍTICOS

| ID | Archivo | Problema | Solución |
|----|---------|----------|----------|
| C1 | `gold/13_mart_cohortes_clientes.py:73` | `meses_desde_cohorte` usa `DATEDIFF(días)/31` truncado → valores incorrectos | Cambiar a `DATEDIFF(MONTH, mes_cohorte, vm.business_month)` |
| C2 | `repo.py:286` | Errores Databricks silenciados: `_query` devuelve `[]` sin log → fallback silencioso a FakeMetricsRepo | Agregar `logger.error()` y no caer a fake en error |
| C3 | `gold/20_quality_gold.py:21` | Race condition: DELETE por `DATE(timestamp) = CURRENT_DATE()` falla si el run cruza medianoche | Usar UUID como `run_id` y filtrar por `run_id` |
| C4 | `repo.py:290` | `_query` solo lee chunk 0 → datos truncados si > 10MB | Iterar `total_chunk_count` |

## 🟠 IMPORTANTES

| ID | Archivo | Problema | Solución |
|----|---------|----------|----------|
| M1 | Todos los marts gold | `DELETE+INSERT` sin transacción: si INSERT falla, mart vacío | Envolver en `BEGIN...COMMIT` o usar `INSERT OVERWRITE` |
| M2 | `30_validate_gold.py:72-96` | V3 compara `valor_total` (suma líneas) vs `total_factura` (cabecera con posible IVA) | Comparar contra agregación equivalente en silver |
| M3 | `gold/12_mart_rotacion_abc.py:65` | `ROW_NUMBER` sin tiebreaker → orden arbitrario en empates | `ORDER BY valor_total DESC, cod_producto` |
| M4 | `gold/14_mart_productos_dormidos.py:77` | `dias_sin_venta` NULL si producto nunca se vendió | `COALESCE(DATEDIFF(...), -1)` |
| M5 | `tests/gold/test_marts.py` | Tests validan keywords en strings, no lógica SQL | Parsear SQL con `sqlparse` o verificar AST |
| M6 | `router.py` | Endpoints `async` envuelven I/O bloqueante (HTTP Databricks) | Hacerlos síncronos o usar `run_in_executor` |
| M7 | `router.py:35` | Rate limit por IP detrás de proxy (todos mismo bucket) | Usar `X-Forwarded-For` o JWT username como key |
| M8 | `dashboards/page.tsx` | Error states no manejados: API falla → usuario ve "—" sin saber | Agregar `if (error) return <ErrorState/>` |
| M9 | `hooks.ts:42` | `apiFetchJson` no incluye URL/body en el error | Agregar `resp.text()` al mensaje |
| M10 | `hooks.ts:27` | 401 redirect con `window.location.href` puede causar loop | Usar `router.push()` de Next.js |
| M11 | `repo.py:211` | `valor_total=0.0` hardcodeado en inventario | Agregar query para calcular valor_total real |
| M12 | `create_gold_workflow.py:109` | `w.jobs.list()` sin filtro itera todos los jobs del workspace | Usar `w.jobs.list(name=JOB_NAME)` |

## 🔵 MENORES

| ID | Archivo | Problema | Solución |
|----|---------|----------|----------|
| m1 | `13_mart_cohortes_clientes.py` | `es_activo` con threshold `>= 2` facturas sin documentar | Agregar comentario con regla de negocio |
| m2 | `20_quality_gold.py:33` | `run_id` con `RAND()*10000` → colisiones improbables pero posibles | Usar `UUID()` |
| m3 | `repo.py:40` | `FakeMetricsRepo._LAST_MONTH = "2026-04"` hardcodeado | Calcular dinámicamente |
| m4 | `page.tsx:119` | "Productos Dormidos" href apunta a `/dashboards/abc` | Cambiar a `/dashboards/dormidos` |
| m5 | `ventas/page.tsx:41` | Trend data hardcodeado (nunca se actualiza) | Quitar mock o servirlo desde API |
| m6 | `router.py:65` | `_clear_metrics_cache()` definida pero nunca llamada | Exponer endpoint de invalidación o quitarla |
| m7 | `router.py:39` | `_workspace_client` singleton sin refresh de token | Agregar refresh o recreación periódica |
| m8 | `30_validate_gold.py:96` | `CROSS JOIN` implícito (`FROM a, b`) | Usar `CROSS JOIN` explícito |
| m9 | `11_mart_inventario_actual.py:59` | `costo_promedio` no es promedio, es último costo | Renombrar a `ultimo_costo` o `costo_unitario_actual` |
| m10 | `hooks.ts` | `useMetrics` no expone `mutate` de SWR | Agregar `mutate` al return type |
