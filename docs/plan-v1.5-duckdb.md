# Plan V1.5 · Migración a DuckDB-first

> **Documento canónico de la migración.** Reemplaza a `docs/plan-cierre-v1-reviewer.md` como spine del proyecto desde 2026-05-31.
>
> **Estado:** Plan aprobado por humano (2026-05-31). Ejecución pendiente de arranque.

---

## 1. Por qué existe este plan

El 2026-05-31 Databricks revocó la elegibilidad de Serverless Compute para el workspace Free Edition de MotoShop. Evidencia exacta:

```
Cannot start warehouse 'Serverless Starter Warehouse' with Serverless Compute
since workspace is no longer eligible for Serverless Compute.
```

El SQL Warehouse era la única forma de leer las gold marts. Sin él, **el 100% de los endpoints `/api/metrics/*` devuelve 500**. La app está dura desde ese momento.

Mantener Databricks gratis no es viable (Free Edition fue deprecada por Databricks unilateralmente). Pagar Databricks contradice el objetivo "MotoShop para siempre" del PO. La única salida sostenible es **sacar el read path fuera de Databricks**.

ADR pendiente: **ADR-0023 — Read backend DuckDB-first**.

---

## 2. Objetivo y restricciones duras

| Dimensión | Objetivo | Restricción |
|-----------|----------|-------------|
| Costo recurrente | $0/mes infra | No depender de gratuidad de terceros que pueden cambiar |
| Datos | Reales (no mock) | sgHermes intocable (lectura solamente desde bronze) |
| Latencia | < 200 ms por endpoint | Mejor que los 2-5 s actuales con Databricks |
| Disponibilidad | 24/7 sin warehouses que duerman | Render free + UptimeRobot ya cubre |
| Defendibilidad académica | "MotoShop usa datos reales del POS, procesados localmente" | Sigue siendo lakehouse medallion conceptual, ahora con motor adecuado al volumen |
| Skills transferibles | Stack estándar (Python + DuckDB + SQL) | Sin lock-in a Databricks |

---

## 3. Arquitectura objetivo

```
┌─────────────────────────────────────────────────────────────┐
│ WINDOWS (on-premise) — POS sgHermes + pipeline batch         │
│                                                              │
│  ┌─────────────────┐                                         │
│  │  MySQL sgHermes │ ◄── facturación en tiempo real          │
│  │  (bronze raw)   │                                         │
│  └────────┬────────┘                                         │
│           │                                                  │
│           ▼ Scheduled Task diario 02:00 COL                  │
│  ┌──────────────────────────────────────────┐                │
│  │  Python pipeline (pure-Python, no Spark) │                │
│  │  bronze → silver → gold (DuckDB + pandas)│                │
│  └────────┬─────────────────────────────────┘                │
│           │                                                  │
│           ▼  rclone push                                     │
└───────────┼──────────────────────────────────────────────────┘
            ▼
┌─────────────────────────────────┐
│ CLOUDFLARE R2 (10 GB free)      │
│ motoshop_gold.duckdb            │  ← latest
│ motoshop_gold_YYYYMMDD.duckdb   │  ← snapshots versionados
└────────┬────────────────────────┘
         │
         ▼  cold start + GET /admin/data/refresh
┌────────────────────────────────────┐
│ RENDER (Free) — FastAPI            │
│ /tmp/motoshop_gold.duckdb (local)  │
│ DuckDBMetricsRepo (lee local)      │
└────────┬───────────────────────────┘
         │ HTTPS
         ▼
┌────────────────────┐
│ VERCEL PWA         │
│ app.fragloesja.uk  │
└────────────────────┘
```

### Decisiones arquitectónicas

| Decisión | Por qué | Alternativa rechazada |
|----------|---------|------------------------|
| DuckDB embebido en API | 0 latencia de red, single binary, SQL Postgres-compatible | Postgres en Supabase (500 MB tope, latencia red) |
| Pipeline en Windows | Ya tiene MySQL local, ya tiene scheduled task, Dev W lo opera | Pipeline en GitHub Actions (necesita tunnel a MySQL, expone superficie) |
| Cloudflare R2 storage | Ya usamos Cloudflare, 10 GB gratis, zona AWS compartida con Render | Supabase Storage (1 GB tope), GitHub LFS (no apto producción) |
| Archivo en `/tmp` Render | Cold start descarga ~50 MB en 5s, UptimeRobot mantiene warm | Render Disk (Pro tier, $7/mes) |
| Snapshots versionados | "Time travel pobre pero funcional" para auditoría | Delta Lake (requiere Spark) |

---

## 4. Stack tecnológico

### Componentes nuevos (V1.5)

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| Motor de queries | **DuckDB** | Analítica columnar single-node, SQL Postgres-compatible, lee Parquet/CSV nativo, sin servidor que mantener. Latencia <100ms para datasets <10GB. |
| Storage del archivo | **Cloudflare R2** | 10 GB free forever, S3-compatible, sin egress fees a Render. Mismo dashboard que ya usás para túnel y DNS. |
| Pipeline batch | **Python + pandas + mysql-connector + duckdb** | Sin Spark, sin clusters, sin warehouses. Lee MySQL → transforma → escribe DuckDB. Corre en 2-5 min para tu volumen. |
| Sync R2 ↔ Render | **rclone** (Windows) + httpx (Render) | rclone soporta R2 nativo y es trivial de scriptear desde PowerShell. httpx maneja el download desde Render. |
| Orquestación | **Windows Scheduled Task** | Ya existe el patrón (`infra/run_*.py`), Dev W ya lo opera, no agrega dependencia nueva. |

### Componentes que se eliminan

| Componente | Por qué se elimina |
|------------|---------------------|
| Databricks SQL Warehouse | Inutilizable (Free Edition perdió Serverless) |
| `databricks-sdk` en API | Reemplazado por `duckdb` lib |
| `databricks-sql-connector` | Idem |
| Workflow Databricks (31 tasks) | Reemplazado por `python pipeline/run_all.py` en Windows |
| Notebooks Databricks (silver/gold) | Reescritos como módulos Python puros bajo `pipeline/` |

### Componentes que se mantienen

| Componente | Por qué se mantiene |
|------------|----------------------|
| MySQL sgHermes (bronze) | Es el POS productivo, intocable |
| API FastAPI on Render | Sigue, solo cambia el repo de datos |
| PWA Next.js on Vercel | Sigue igual, no se entera del cambio |
| Cloudflare Tunnel | Sigue para `api.fragloesja.uk` |
| Tablas `app_*` MySQL (F5) | Operación bidireccional sigue como está |
| Schemas Pydantic (`schemas.py`) | El contrato API↔PWA no cambia |

---

## 5. Roadmap de Sprints (Fases)

### Sprint 0 · Spike de validación (2h, bloqueante de todo)

**Objetivo:** Probar end-to-end que el patrón funciona con UN endpoint antes de invertir 11h en migración completa.

| Tarea | DoD |
|-------|-----|
| Crear bucket R2 + API token | `motoshop-gold` bucket disponible, credenciales en `.env` |
| Script `pipeline/spike_sales.py` | Lee `mart_ventas_diarias_sku` de Databricks UNA última vez (con el SDK actual roto se hace export manual) o desde MySQL via JOIN, escribe a DuckDB local |
| Upload a R2 | `motoshop_gold.duckdb` en R2, accesible vía rclone |
| `DuckDBMetricsRepo.get_sales_summary()` | Implementado en `motoshop-app/api/src/motoshop_api/metrics/repo_duckdb.py` |
| Deploy a Render preview | Branch `feat/v1.5-spike` con env `DATA_BACKEND=duckdb` |
| Validación cruzada | `curl preview/api/metrics/sales-summary` devuelve cifras iguales a `docs/audit/raw_responses.json#SALES_SUMMARY` (tolerancia 0.0) |

**Criterio salida:** Si las cifras cuadran y latencia < 500ms → seguir. Si no → revisar arquitectura.

---

### Sprint 1 · Pipeline silver/gold portado (4-5h)

**Objetivo:** Reescribir los notebooks Databricks como módulos Python puros que corren en Windows local sin Spark.

| Tarea | DoD |
|-------|-----|
| Auditar notebooks `notebooks/silver/*.py` y `notebooks/gold/*.py` | Catálogo de funciones Spark usadas (DATE_FORMAT, ADD_MONTHS, ROW_NUMBER, etc.) — todas existen en DuckDB |
| Crear `pipeline/__init__.py` con orquestador | `python pipeline/run_all.py` ejecuta bronze→silver→gold en orden y produce `out/motoshop_gold.duckdb` |
| Portar 5 silver dims + 5 silver facts | Cardinalidad de cada tabla coincide con la actual en Databricks (snapshot anterior a 2026-05-31 sirve como gold-standard) |
| Portar 5 gold marts | `mart_ventas_diarias_sku`, `mart_inventario_actual`, `mart_rotacion_abc`, `mart_cohortes_clientes`, `mart_productos_dormidos` |
| Portar tablas auxiliares | `alertas_quiebre`, `alertas_drift`, `forecast_categoria`, `mart_rotacion_promedio`, `mart_abc_xyz` |
| Tests de paridad | `tests/pipeline/test_parity.py` compara row counts y sum agregados entre DuckDB y snapshot anterior |

**Criterio salida:** Pipeline corre en < 5 min en Windows. Tests paridad PASS. Bug 4.3 (alertas urgencia media/baja) se aprovecha el porting para corregir la lógica de buckets en `gold_alertas_quiebre.py`. Bug 4.4 (alertas_drift vacío) se popula con datos reales en el porting.

---

### Sprint 2 · DuckDBMetricsRepo full (2-3h)

**Objetivo:** Reemplazar TODO `RealMetricsRepo` por `DuckDBMetricsRepo` que lee de DuckDB local.

| Tarea | DoD |
|-------|-----|
| Copiar `RealMetricsRepo` → `DuckDBMetricsRepo` | Misma interfaz `MetricsRepoProtocol` |
| Adaptar parámetros SQL | DuckDB usa `$param` posicional o `?`, no `:name`. Ajustar `_query()` |
| Factory `get_metrics_repo()` lee `DATA_BACKEND` env var | `duckdb` → DuckDBMetricsRepo, otros → error explícito |
| Bootstrap del API descarga DuckDB de R2 | Al arrancar uvicorn, si `/tmp/motoshop_gold.duckdb` no existe → download desde R2 |
| Test todos los endpoints | Local: `pytest tests/api/test_metrics_duckdb.py` 17/17 PASS |
| Performance baseline | Cada endpoint < 200ms en local |

**Criterio salida:** 17/17 endpoints HTTP 200 contra DuckDB local con cifras idénticas al snapshot.

---

### Sprint 3 · Automatización refresh (2h)

**Objetivo:** Que los datos se actualicen solos sin intervención manual.

| Tarea | DoD |
|-------|-----|
| Script `infra/refresh_v15.ps1` | PowerShell: ejecuta pipeline + rclone push + log |
| Scheduled Task Windows | Corre 02:00 COL daily, post-cierre tienda |
| Endpoint `/admin/data/refresh` (role=admin) | Re-descarga latest de R2 al `/tmp/`, recarga conexión DuckDB |
| `/health/data-freshness` adaptado | Lee fecha de generación del archivo DuckDB y la expone |
| Alerta de stale data | Si la fecha es > 24h, banner amarillo en PWA |

**Criterio salida:** Modifico un dato en MySQL a las 23:00, vuelvo a las 03:00, abro PWA → dato actualizado. Sin tocar nada.

---

### Sprint 4 · Cutover producción + decom Databricks (1h)

**Objetivo:** Apagar definitivamente el camino viejo.

| Tarea | DoD |
|-------|-----|
| Render env var `DATA_BACKEND=duckdb` en prod | Variable seteada |
| Deploy prod | Branch main → Render auto-deploy |
| Smoke 17/17 endpoints prod | Todos HTTP 200 vía `api.fragloesja.uk` |
| Marcar credentials Databricks deprecated | `.env.example` con comentario "deprecated v1.5" |
| ADR-0023 escrito y Accepted | `docs/decisions/0023-read-backend-duckdb.md` |
| SEGUIMIENTO.md cierre V1.5 | Bloque de sesión con métricas before/after |

**Criterio salida:** PWA funciona contra DuckDB. Última prueba: revoco el token de Databricks → la app sigue funcionando → "para siempre" validado.

---

### Sprint 5 · Frontend detalle + Búsqueda semántica (10-14h, post-migración)

**Objetivo:** Cerrar los bugs frontend pendientes con la latencia nueva en juego + agregar búsqueda semántica de productos (Opción 2 del roadmap IA, integrada acá porque DuckDB `vss` extension es trivial de habilitar y agrega capability concreta sin nueva infra).

#### Sub-bloque A · Bugs frontend (8-12h)

| Tarea | DoD |
|-------|-----|
| Bug 5.1 — Ventas crash incógnito (.meses undefined) | Ya commiteado en branch local, falta push |
| Bug 5.3 — ABC detalle productos por bucket | Endpoint nuevo `/api/metrics/abc-detalle?bucket=A&limit=20` + UI con lista colapsable |
| Bug 5.4 — Forecast top altos por default | UI muestra top 20 predicciones más altas sin que el usuario busque |
| Bug 5.5 — Cohortes filtrar gaps con ticket=0 | Frontend filtra entradas `num_clientes=0` o las muestra con `—` en lugar de `$0` |
| Bug 5.6 — Performance home | SWR cache TTL agresivo (5 min → ya no necesario con DuckDB), paralelizar fetches con `Promise.all` |
| Bug 4.3 ya resuelto en Sprint 1 | Validar que alertas devuelve urgencia=alta/media/baja distribuidas |
| Bug 4.4 ya resuelto en Sprint 1 | Validar que drift devuelve items con datos reales |

#### Sub-bloque B · Búsqueda semántica de productos (2h)

**Por qué se integra acá y no en V1.6:** habilitar `vss` en DuckDB son 3 líneas, embeber 4,829 SKUs cuesta $0.01 one-time, y resuelve el problema real del vendedor (buscar "filtro aire moto 150cc" y encontrar "FILT.A.CG150"). No agrega operación nueva.

| Tarea | DoD |
|-------|-----|
| Generar embeddings de los 4,829 SKUs | Script `pipeline/embeddings_skus.py` usa OpenAI `text-embedding-3-small`, escribe columna `embedding FLOAT[1536]` en tabla `dim_producto` DuckDB |
| Habilitar `vss` extension en DuckDB | `INSTALL vss; LOAD vss;` en bootstrap del API. Crear índice HNSW sobre `dim_producto.embedding` |
| Endpoint `/api/products/search-semantic?q=...` | Convierte query a embedding via OpenAI API, ejecuta cosine similarity en DuckDB, devuelve top 10 SKUs con score |
| Integrar al buscador existente en PWA | Toggle "búsqueda inteligente" en `/products`. Si activo, hit el endpoint nuevo. Si no, búsqueda tradicional por LIKE |
| Refresh de embeddings | En `pipeline/run_all.py`, regenerar embeddings SOLO para SKUs nuevos (delta). Costo recurrente: < $0.01/mes |
| Env var `OPENAI_API_KEY` en Render + Windows | Setear en Render dashboard + `.env` de Windows |

**Criterio salida:**
- Sub-bloque A: usuario revisa la PWA en producción, no tiene quejas funcionales
- Sub-bloque B: vendedor tipea "aceite sintético 4 tiempos" y aparece "MOBIL SUPER MOTO 4T 20W50" como top match

---

## 6. Risk register

| ID | Riesgo | Mitigación | Severidad |
|----|--------|------------|-----------|
| RV1 | Spark SQL incompatible con DuckDB SQL en algún notebook | Sprint 0 valida con el endpoint más complejo (cohortes con `_fill_month_gaps`) antes de invertir Sprint 1 completo | Media |
| RV2 | Pipeline tarda > 10 min en Windows | DuckDB es 2-3x más rápido que Spark en single-node con datos chicos. Si pasa → optimizar con índices DuckDB | Baja |
| RV3 | R2 + DuckDB read latency inaceptable | Resuelto por diseño: descargamos archivo a `/tmp` Render, queries son locales | Resuelta por diseño |
| RV4 | Render cold start descarga 60 MB cada vez | UptimeRobot pinguea cada 5 min → proceso queda warm → cold start raro | Baja |
| RV5 | Windows queda como SPOF del pipeline | Si Windows muere, último DuckDB en R2 sigue sirviéndose → app funciona, data se congela hasta que vuelva | Tolerable (mejor que hoy con Databricks que duerme y mata todo) |
| RV6 | Diff de cifras vs Databricks post-migration | Tests paridad en Sprint 1 + cross-check Sprint 2 | Media |
| RV7 | Snapshot inicial: cómo obtenemos el primer DuckDB sin Databricks vivo | Plan A: usar `docs/audit/raw_responses.json` ya capturado como semilla / Plan B: pipeline lee directo de MySQL (no necesita Databricks) | Baja — Plan B es trivial |

---

## 7. Equipo y handoffs

**Filosofía: entre menos devs, mejor.** El plan está diseñado para 2 devs máximo, idealmente secuenciales (Dev D termina backend → Dev F arranca frontend).

| Dev | Sprints asignados | Tiempo estimado |
|-----|-------------------|-----------------|
| **Dev D — Backend Migration** | 0, 1, 2, 3, 4 | 11-13h |
| **Dev F — Frontend Polish** | 5 | 8-12h |

Si se quiere reducir a 1 solo dev: hacer todo secuencial, ~24h totales.

Briefs detallados de cada dev en [`docs/handoffs-v1.5.md`](handoffs-v1.5.md).

### Reglas de cierre por dev

1. **Toda tarea cerrada exige curl/test contra producción** con output pegado en el commit. No se acepta "compila" sin evidencia de comportamiento.
2. **Cuadre obligatorio en Sprint 2** — cifras DuckDB vs `docs/audit/raw_responses.json` con tolerancia 0.
3. **Sprint 5 NO arranca hasta que Sprint 4 cierre.** Esto es no-negociable: no se arregla UI con backend mock.
4. **El revisor (no el ejecutor) firma el GO/NO-GO de cada sprint.** Rulebook `INICIAR_REVIEWER.md` aplica.

---

## 8. Dependency graph

```
Sprint 0 ──► Sprint 1 ──► Sprint 2 ──► Sprint 3 ──► Sprint 4 ──► Sprint 5
  Spike       Pipeline      Repo          Refresh    Cutover     Frontend
   2h         4-5h          2-3h           2h         1h         8-12h
```

Cada sprint bloquea al siguiente. **No se paraleliza nada** — el riesgo de hacerlo es altísimo (ya nos pasó en F2-V3 / F3-V6 / F4-B).

---

## 9. Definition of Done para todo V1.5

V1.5 cierra cuando:

- [ ] 17/17 endpoints producción HTTP 200 leyendo de DuckDB
- [ ] Latencia p95 < 200 ms por endpoint
- [ ] Scheduled Task Windows ejecuta diariamente sin intervención
- [ ] Databricks token puede ser revocado y la app sigue funcionando
- [ ] PWA muestra todos los dashboards sin crash en incógnito + window normal
- [ ] Performance home page < 1.5s First Contentful Paint
- [ ] Bug list de PENDIENTES.md cerrada
- [ ] ADR-0023 Accepted
- [ ] SEGUIMIENTO.md cierre V1.5 con métricas before/after
- [ ] E5 memoria final actualizada con sección "Migración V1.5"

---

## 10. Notas técnicas clave

### ¿Por qué DuckDB y no Postgres / SQLite / Polars?

| Opción | Pro | Contra | Veredicto |
|--------|-----|--------|-----------|
| **DuckDB** | Columnar (analítica), SQL Postgres-compatible, lee Parquet/CSV nativo, sin servidor | Single-node | ✓ **Elegida** — perfecta para analytics |
| Postgres (Supabase free) | Madurez, conocido | 500 MB tope, latencia de red, row-oriented (lento en agregaciones grandes) | ✗ Tope insuficiente + latencia |
| SQLite | Embebido, conocido | Row-oriented, no optimizada para analytics | ✗ Performance pobre en SUM/GROUP BY |
| Polars | Velocidad cruda, lazy evaluation | No es un motor SQL, requiere reescribir queries como DataFrames | ✗ Demasiado refactor |

### ¿Por qué Cloudflare R2 y no S3 / GCS?

- **R2**: 10 GB free, sin egress fees (clave porque Render descarga el archivo cada cold start), API S3-compatible
- **S3**: 5 GB free pero con egress fees ($0.09/GB después de límites bajos)
- **GCS**: 5 GB free, egress free para tier muy bajo
- Decisión: R2 por tamaño y porque ya está en el toolkit de Cloudflare que usás

### ¿Por qué pipeline en Windows y no en GitHub Actions?

- **Windows on-premise**:
  - ✓ Ya tiene MySQL local (cero latencia leer bronze)
  - ✓ Ya tiene Scheduled Task setup (Dev W lo opera)
  - ✓ Tu narrativa "datos de la tienda" se refuerza
  - ✗ SPOF si la PC se apaga
- **GitHub Actions**:
  - ✓ Sin SPOF
  - ✗ Necesita exponer MySQL al tunnel (superficie de ataque)
  - ✗ Latencia de red para descargar bronze
- Decisión: Windows. El SPOF está acotado (último DuckDB sigue sirviéndose, solo se congelan datos)

### ¿Cómo obtenemos el snapshot inicial sin Databricks vivo?

El pipeline lee MySQL bronze directamente. **No depende de tener Databricks operativo para producir el primer DuckDB**. Sprint 0 valida esto antes de invertir más.

---

## 11. Migración del lakehouse conceptual

| Capa | Antes (V1) | Ahora (V1.5) |
|------|------------|--------------|
| Bronze | Databricks Delta `motoshop.bronze.*` | MySQL `sgHermes.*` (ya era el origen) |
| Silver | Databricks Delta `motoshop.silver.*` | DuckDB tables `motoshop_silver_*` |
| Gold | Databricks Delta `motoshop.gold.mart_*` | DuckDB tables `motoshop_gold_mart_*` |
| ML | MLflow + LightGBM/Prophet (descartados ADR-0017) | Moving average baseline en Python (ya estaba) |
| Compute | Spark serverless | DuckDB single-node |
| Read serving | SQL Warehouse | DuckDB embebido en FastAPI |

**Lo que sigue siendo lakehouse:** la separación lógica medallion (raw → cleaned → business), la idempotencia, los gates de calidad, los snapshots históricos. El **patrón** persiste. El **motor** cambia.

Para la maestría académica esto es defendible y de hecho **superior** porque demuestra criterio de arquitecto: "elegí el motor que el problema necesita, no el motor que mi prestigio académico quería". Eso es lo opuesto de cargo-cult engineering.

---

## 12. Cuándo y cómo arrancamos

- **Trigger:** Cuando humano + revisor coordinen kickoff Sprint 0.
- **Bridge mientras migramos:** Decidir B.1 (FakeMetricsRepo con header DEMO MODE, 30 min) o B.2 (app dura 24-48h). Recomendación del revisor: B.2 — más honesto, menos código que tirar después.
- **Modo ejecución:** Sequential strict. Sprint N no arranca hasta Sprint N-1 cerrado por revisor.

---

*Documento creado: 2026-05-31*
*Última actualización: 2026-05-31*
*Aprobado por: PO (humano) — kickoff pendiente*
*Doc canónico anterior: `docs/plan-cierre-v1-reviewer.md` (deprecated)*
