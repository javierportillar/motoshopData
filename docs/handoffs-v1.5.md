# Handoffs V1.5 · Briefs para devs

> **2 devs máximo. Secuenciales.** Plan canónico: [`docs/plan-v1.5-duckdb.md`](plan-v1.5-duckdb.md).
>
> Pegá el bloque correspondiente en el chat del dev. **No los uses simultáneos** — Sprint 5 NO arranca hasta que Sprints 0-4 estén firmados por revisor.

---

## 🤖 Handoff #1 · Dev D · Migración a DuckDB (Sprints 0-4)

```
Sos el Dev Backend de la migración V1.5 de MotoShop. Tu trabajo: sacar el read path de Databricks y poner DuckDB.

LECTURAS OBLIGATORIAS antes de tocar código:
1. INICIAR_AGENTE.md (rulebook del rol Dev)
2. docs/plan-v1.5-duckdb.md (este es tu spine — léelo entero)
3. docs/audit/F7-AUDIT.md (lo que se rompió en F7 y por qué)
4. docs/audit/raw_responses.json (snapshot de cifras de los 17 endpoints; tu gold-standard para validar paridad)
5. motoshop-app/api/src/motoshop_api/metrics/repo.py (RealMetricsRepo actual — tu plantilla)
6. notebooks/silver/*.py + notebooks/gold/*.py (los notebooks a portar)
7. ADR-0017 y ADR-0020 (decisiones que NO se revisan en V1.5)

CONTEXTO DURO:
- Databricks Free Edition perdió Serverless Compute (2026-05-31). Es definitivo.
- El warehouse no se puede prender → 17/17 endpoints en 500 → app dura.
- No vamos a pagar Databricks. Migramos a DuckDB-first.
- Los notebooks Databricks de silver/gold se reescriben como módulos Python en pipeline/.
- El pipeline corre en Windows (Dev W lo opera vía Scheduled Task).
- El archivo DuckDB resultante se sube a Cloudflare R2 (bucket motoshop-gold).
- El API en Render lo descarga al /tmp/ al arrancar y queda warm gracias a UptimeRobot.

ENTORNO:
- Repo: /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
- Tokens en motoshop-app/api/.env (Databricks deprecated, R2 a agregar)
- Bucket R2 a crear: motoshop-gold (Cloudflare API token está en .env como CLOUDFLARE_API_TOKEN)

ENTREGABLES POR SPRINT (en orden, no paralelos):

═══ SPRINT 0 — Spike validación (2h) ═══
1. Crear bucket R2 motoshop-gold + access key
2. Script pipeline/spike_sales.py: lee mart_ventas_diarias_sku desde MySQL bronze directo (NO Databricks), genera DuckDB local
3. Upload a R2 con rclone
4. Implementar motoshop-app/api/src/motoshop_api/metrics/repo_duckdb.py con SOLO el método get_sales_summary()
5. Factory get_metrics_repo() respeta env DATA_BACKEND=duckdb|databricks
6. Branch feat/v1.5-spike, deploy a Render preview
7. Curl preview /api/metrics/sales-summary → comparar cifras vs docs/audit/raw_responses.json#SALES_SUMMARY
8. Si cuadran (tolerancia 0) → STOP, llamar al revisor para GO Sprint 1
   Si no cuadran → STOP, diagnosticar, NO seguir

═══ SPRINT 1 — Pipeline silver+gold (4-5h) ═══
1. Auditar notebooks/silver/*.py y notebooks/gold/*.py, listar funciones Spark usadas
2. Crear pipeline/__init__.py con orquestador run_all()
3. Portar 5 silver dims + 5 silver facts (cada uno como módulo Python que lee MySQL y escribe DuckDB)
4. Portar 5 gold marts: mart_ventas_diarias_sku, mart_inventario_actual, mart_rotacion_abc, mart_cohortes_clientes, mart_productos_dormidos
5. Portar tablas auxiliares: alertas_quiebre (FIX bug 4.3 al hacerlo — agregar buckets media/baja en la lógica de urgencia), alertas_drift (FIX bug 4.4 — popular con datos reales), forecast_categoria
6. Tests de paridad tests/pipeline/test_parity.py:
   - Row counts por tabla coinciden con docs/audit/raw_responses.json totales
   - SUM(valor_total) y SUM(num_facturas) coinciden
7. python pipeline/run_all.py corre end-to-end en < 5 min en Windows

═══ SPRINT 2 — DuckDBMetricsRepo full (2-3h) ═══
1. Completar repo_duckdb.py con TODOS los métodos del RealMetricsRepo
2. Adaptar parámetros SQL: DuckDB usa ? o $1 posicional, NO :name
3. Bootstrap del API descarga DuckDB de R2 a /tmp/ si no existe
4. Tests tests/api/test_metrics_duckdb.py: 17/17 endpoints HTTP 200 con cifras idénticas al snapshot
5. Performance: cada endpoint < 200ms en local

═══ SPRINT 3 — Automatización refresh (2h) ═══
1. infra/refresh_v15.ps1 (PowerShell, Dev W lo va a programar)
2. Endpoint POST /admin/data/refresh con role=admin que recarga DuckDB desde R2
3. /health/data-freshness expone fecha de generación del archivo DuckDB
4. Documentar para Dev W cómo programar Scheduled Task 02:00 COL

═══ SPRINT 4 — Cutover producción (1h) ═══
1. Render env var DATA_BACKEND=duckdb en producción
2. Merge a main → Render auto-deploy
3. Smoke 17/17 endpoints contra api.fragloesja.uk → todos HTTP 200
4. Escribir docs/decisions/0023-read-backend-duckdb.md con estado Accepted
5. Actualizar SEGUIMIENTO.md con bloque de sesión "V1.5 cutover" y métricas before/after
6. Marcar credenciales Databricks como deprecated en .env.example
7. Última prueba: con DuckDB en producción, revocar mentalmente Databricks → confirmar 17/17 sigue 200

REGLAS DE TRABAJO:
- Cada commit lleva en el body el comando curl + output esperado de los endpoints tocados.
- Sin curl evidence → no acepto el commit.
- NO arranques Sprint N+1 sin GO escrito del revisor en Sprint N.
- Cifras vs snapshot tolerancia 0. Si hay diff, lo discutimos antes de seguir.
- Si una query DuckDB falla con sintaxis Databricks → portar a sintaxis DuckDB (ambos son ANSI SQL casi 100%).
- Mantené INICIAR_AGENTE.md reglas: monorepo, env vars, no hardcoded credentials, tests obligatorios.

CUANDO TERMINES:
Reportá al revisor con:
- Estado Sprint por Sprint (PASS/FAIL)
- 17/17 endpoints curl output en producción
- Diff cifras (debe ser 0)
- Tiempo total de pipeline en Windows
- ADR-0023 link

No reportes "listo" sin evidencia.
```

---

## 🤖 Handoff #2 · Dev F · Frontend polish (Sprint 5)

> **NO arrancar hasta que Dev D cierre Sprint 4 y revisor firme GO.**

```
Sos el Dev Frontend de V1.5 fase final. Tu trabajo: cerrar los bugs de UX/UI reportados por el PO el 2026-05-31 ahora que el backend DuckDB ya funciona estable y rápido.

LECTURAS OBLIGATORIAS antes de tocar código:
1. INICIAR_AGENTE.md (rulebook)
2. docs/plan-v1.5-duckdb.md sección "Sprint 5 — Frontend detalle"
3. docs/audit/F7-AUDIT.md (lo que se rompió en F7 y qué se arregló)
4. PENDIENTES.md sección "Sesión 2026-05-31 · V1.5 frontend pendientes"
5. motoshop-app/web/app/(authenticated)/ (las 12 páginas)

CONTEXTO DURO:
- El backend ya migró a DuckDB. Latencias bajaron de 2-5s a < 200ms.
- Algunas optimizaciones frontend (cache TTL agresivo) ya NO son necesarias.
- El PO probó la app y reportó 7 cosas concretas (lista abajo).
- No agregás dependencias nuevas sin justificar.

BUGS A CERRAR (en orden de severidad, no de comodidad):

═══ 5.1 — Ventas crash incógnito "Cannot read 'meses' of undefined" ═══
Estado: fix ya aplicado en working tree no pusheado (Array.isArray guards en renderHistorica + totalMesesHist).
Acción: verificar que el fix está y pushearlo. Reproducir en incógnito post-deploy.
DoD: incógnito + window normal → /dashboards/ventas no crashea en ningún tab.

═══ 5.3 — ABC sin detalle de productos ═══
PO dijo: "necesito que se vean los productos que están dentro de cada distribución, cantidad de productos por categoría".
Backend: agregar endpoint /api/metrics/abc-detalle?bucket=A|B|C&limit=20 que devuelve top N SKUs por bucket con cifras (cantidad_vendida, valor_total, porcentaje).
Frontend: en /dashboards/abc, agregar sección colapsable por bucket que liste productos.
DoD: PO ve los productos en cada bucket A/B/C, ordenados por valor_total desc, con paginación o "ver más".

═══ 5.4 — Forecast no muestra nada por default ═══
PO dijo: "necesito que salga por default las más altas y que me salga más información sin necesidad de que yo lo busque".
Acción: en /forecast, al entrar mostrar top 20 SKUs por demanda predicha más alta (sin buscador). El buscador queda como opcional. Plus la vista por categoría ya existe arriba.
DoD: PO entra a /forecast y ve inmediatamente las predicciones altas sin teclear nada.

═══ 5.5 — Cohortes con ticket promedio en 0 ═══
PO dijo: "veo meses con ticket promedio en 0, algo raro pasó allí".
Causa: _fill_month_gaps en el backend inyecta entradas con num_clientes=0, ticket_promedio=0, tasa_recurrencia=null. Son los huecos rellenos.
Acción: en frontend, cuando num_clientes=0, mostrar la celda como "—" en lugar de "$0". El backend no se toca (la data está bien, es presentación).
DoD: PO ve "—" en lugar de "$0" en cohortes sin datos. El bloque pedagógico explica por qué.

═══ 5.6 — Vendedor detalle "error al cargar" ═══
Causa: era por warehouse durmiendo (resuelto con DuckDB) PLUS el SQL del vendedor detail puede tener edge case.
Acción: testear contra DuckDB local. Si falla → arreglar la query. Si funciona → solo confirmar que en prod funciona.
DoD: PO oprime "Ver detalle" en cualquier vendedor → modal carga sin error.

═══ 5.7 — Performance app lenta ═══
PO dijo: "la aplicación tarda un tanto en cargar, no es óptimo el tiempo, se demora mucho, mira como mejorar eso".
Acción:
- Bajar TTL SWR a 60s (antes 5 min era para amortizar latencia Databricks, ya no necesario)
- Paralelizar los 5 hooks del home con Promise.all (ya están en paralelo por React, pero verificar)
- Lazy-load rutas no-críticas (drift, acciones)
- Lighthouse audit antes/después
DoD: home First Contentful Paint < 1.5s en 4G simulado. Lighthouse Performance > 90.

═══ Validación bugs ya resueltos por backend ═══
Verificar que estos NO requieren más fix frontend (ya los arregló Dev D):
- Alertas urgencia media/baja → debería mostrar las 3 distribuciones
- Acciones recommendations → debería mostrar acciones de alertas media y baja también
- Drift → debería mostrar detecciones reales en lugar de "no se detectaron"
- Plan compras filtros media/baja → deberían filtrar correctamente

REGLAS DE TRABAJO:
- Cada bug se cierra con: commit + screenshot pre/post + verificación en producción.
- Sin screenshot del comportamiento corregido → no acepto el commit.
- TypeScript clean (npx tsc --noEmit sin errores).
- Build local pasa (npm run build).
- Lighthouse Performance > 90, A11y > 90.

CUANDO TERMINES:
Reportá al revisor con:
- 7 bugs cerrados, cada uno con screenshot before/after
- Lighthouse before/after
- Commit hash desplegado en Vercel
- URL preview o producción donde validar

No reportes "listo" sin evidencia visual.
```

---

## 🤖 Handoff opcional · Dev W · Scheduled Task pipeline

> Solo se activa después de que Dev D cierre Sprint 3. Pegá en chat de Dev W.

```
Tarea operativa V1.5: programar Scheduled Task Windows para refresh diario del pipeline DuckDB.

PRE-REQUISITO: Dev D entregó infra/refresh_v15.ps1 funcionando.

ACCIONES:
1. Pull main en el repo Windows
2. Verificar que infra/refresh_v15.ps1 existe
3. Ejecutar manualmente UNA VEZ para validar:
   - Pipeline corre OK
   - rclone uploadea a R2 OK
   - API endpoint /admin/data/refresh recarga OK
4. Crear Scheduled Task:
   - Nombre: MotoShop_RefreshV15
   - Trigger: Daily 02:00 COL
   - Action: powershell.exe -ExecutionPolicy Bypass -File C:\path\to\repo\infra\refresh_v15.ps1
   - Settings: Run whether user is logged on or not, Highest privileges
5. Verificar log post-ejecución (debe haber un .log con timestamp)

ENTREGABLES:
- Screenshot del Task Scheduler con MotoShop_RefreshV15 creado
- Log de la primera ejecución manual
- Log de la primera ejecución automática (al día siguiente)
- Output del curl /health/data-freshness mostrando fecha actualizada

No reportes "listo" sin los 4 entregables.
```

---

## Reglas no-negociables del coordinador

1. **Secuencial estricto.** Dev D termina TODOS sus sprints antes de que Dev F arranque. Sprint N+1 espera GO del revisor en N.
2. **Evidencia > narrativa.** Cada cierre exige curl, screenshot o test concreto. Sin eso, queda abierto.
3. **Si algo se rompe → STOP.** Dev no improvisa. Levanta al revisor con el error + qué intentó.
4. **Cifras vs snapshot.** En Sprints 1-2 el revisor exige paridad 0 contra `docs/audit/raw_responses.json`. Si diff → no se cierra.
5. **Nada de "mientras tanto hago X paralelo".** El plan tiene dependencias por una razón.

---

*Documento creado: 2026-05-31*
*Doc canónico: `docs/plan-v1.5-duckdb.md`*
