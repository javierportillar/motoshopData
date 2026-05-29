# Plan detallado · Fase 2 · Silver + PWA MVP

> Plan operativo de F2 derivado de PLAN.md §7 y SEGUIMIENTO.md. Sirve como sprint planning real para las 3 piezas que conforman el hito: **vendedor en la calle abre la PWA, busca un repuesto, ve precio y stock por bodega**.
>
> Hito de éxito: PWA instalable en celular, login funcional desde 4G, búsqueda < 1 s, ficha de SKU con stock por bodega que cuadra con sgHermes < 0.5%.
>
> Stack técnico: [ADR-0014](decisions/0014-stack-f2.md) (Proposed; bloquea inicio Sprint F2-A).
> Fechas: [ADR-0013](decisions/0013-fecha-tecnica-vs-negocio.md) Accepted — Silver deriva `business_date` desde columnas reales (`fecfven`, `feccom`, `docfec`).

---

## 1 · Objetivo y hito

**Hito visible de F2:**
> El vendedor camina por la calle, abre la PWA instalada en su celular, hace login con su usuario, busca "aceite 20W50", la app le muestra precio y stock por bodega — todo en < 5 segundos desde el toque del ícono.

**Objetivo Track A (Silver):** modelo dimensional limpio + reglas de calidad sobre las 12 tablas core de F1.

**Objetivo Track T (PWA):** Next.js 14 instalable como PWA con login JWT persistente, búsqueda paginada y ficha de SKU con stock que consume la API de F1.

---

## 2 · Decisiones técnicas

Resueltas en [ADR-0014 · Stack técnico F2](decisions/0014-stack-f2.md) (16 decisiones DT-F2-1 a DT-F2-16). Hasta que el humano apruebe ese ADR, Sprint F2-A está en pausa.

| # | Decisión | Recomendación |
|---|----------|----------------|
| DT-F2-1 | Escritura silver idempotente | `INSERT INTO ... REPLACE WHERE business_date = '...'` |
| DT-F2-2 | SCD strategy para dimensiones | SCD Type 1 (snapshot del estado actual) |
| DT-F2-3 | Reglas de calidad silver | PySpark con `assert` + tabla `_quality_runs` |
| DT-F2-4 | Particionado silver | Hechos: por `business_date`. Dimensiones: sin partición |
| DT-F2-5 | Naming convention | `fact_*` para hechos, `dim_*` para dimensiones, `silver` schema |
| DT-F2-6 | Tests Spark | `chispa` library + datasets sintéticos pequeños |
| DT-F2-7 | Stack PWA | Next.js 14 App Router + TypeScript estricto (ya en F0/F1) |
| DT-F2-8 | Storage JWT en frontend | `httpOnly` cookie via Next.js API routes |
| DT-F2-9 | Fetch wrapper | Fetch nativo + helper con auto-refresh on 401 |
| DT-F2-10 | State management | Zustand para auth + SWR para data fetching |
| DT-F2-11 | UI library | Tailwind raw + componentes propios chicos |
| DT-F2-12 | PWA manifest + service worker | `next-pwa` package |
| DT-F2-13 | Service worker strategy | Workbox via `next-pwa` |
| DT-F2-14 | Offline cache para catálogo | IndexedDB con `idb-keyval` |
| DT-F2-15 | Network strategy | Stock = `NetworkOnly` con 5s timeout · Catálogo = `StaleWhileRevalidate` |
| DT-F2-16 | Cache invalidation | TTL 1 h para catálogo · invalidación manual con botón "Actualizar" |

---

## 3 · Mapa de entregables → verificaciones críticas

Las 8 verificaciones críticas de F2 (ya en SEGUIMIENTO.md §Fase 2):

| # | Verificación | Cierra con… | Sprint |
|---|--------------|--------------|--------|
| **V1** | ¿Hay duplicados en silver? | Notebook `silver/30_validate_silver.py` + assert `count == count(distinct)` para hechos y dimensiones | F2-A |
| **V2** | ¿Las fechas inválidas se descartan o paran el pipeline? | Notebook `silver/20_quality_run.py` con expectations + `_runs/v2_quality_dates_<fecha>.md` con casos rechazados (incluyendo `fecfven=9876-01-01` ya detectado) | F2-A |
| **V3** | ¿Totales silver cuadran con sgHermes (< 0.5%)? | Notebook `silver/31_reconciliation.py` + `_runs/v3_reconciliation_<fecha>.md` con comparación específica (ventas mes pasado, top SKUs) | F2-A |
| **V4** | ¿PWA funciona sin conexión post-cache? | Test E2E: cargar app, modo avión, navegar productos cacheados; `_runs/v4_offline_demo_<fecha>.md` con screenshots | F2-C |
| **V5** | ¿Sesión sobrevive a cerrar/reabrir? | Test E2E: login, cerrar app, reabrir antes de TTL JWT; debe seguir logueado; `_runs/v5_session_persistence.md` | F2-B |
| **V6** | ¿Búsqueda < 1 s con 6k+26k filas? | 50 búsquedas con `productos` (6k) + cruce con `auxinventario` (26k) medidas p95; `_runs/v6_search_latency.json` | F2-B |
| **V7** | ¿Permisos de rol funcionan? | Usuario rol "vendedor" intenta endpoint admin → 403; `_runs/v7_role_perms.md` con curls | F2-B |
| **V8** | ¿PWA muestra el dato correcto? | Comparación manual de 5 SKUs aleatorios: PWA stock vs `SELECT` directo MySQL; `_runs/v8_data_match.md` | F2-C |

---

## 4 · Sprint F2-A · Silver

**Duración estimada:** 2-3 sesiones del ejecutor (~6 horas total).

### 4.1 Pre-requisitos

- ✅ F1.9 cerrada (lag monitor + Task Scheduler robusto operando).
- ✅ ADR-0013 Accepted; ADR-0014 debe estar Accepted antes del primer commit del sprint.
- ✅ Bronze poblado con las 12 tablas core para varios `ingest_date` (ya hay 5+ corridas exitosas).
- ⚠️ Sondeo de fechas (Sesión 22) leído: columnas reales son `fecfven`, `feccom`, `docfec`.

### 4.2 Archivos a crear

**Track A · Notebooks Silver:**

| Path | Rol |
|------|-----|
| `notebooks/silver/01_dim_producto.py` | SCD1 snapshot desde `bronze.productos`: `codprod`, `nomprod`, `codbar`, etc. con TRIM. |
| `notebooks/silver/02_dim_bodega.py` | SCD1 desde `bronze.bodegas`. |
| `notebooks/silver/03_dim_tercero.py` | SCD1 desde `bronze.terceros`; sanitizar NIT, pseudonimizar nombres si datasets se comparten (Habeas Data Col). |
| `notebooks/silver/04_dim_sucursal.py` | SCD1 desde `bronze.sucursales`. |
| `notebooks/silver/05_dim_formapago.py` | SCD1 desde `bronze.formapago`. |
| `notebooks/silver/06_dim_tiempo.py` | Genera calendario `dim_tiempo` con `business_date`, `year`, `quarter`, `month`, `dow`, `festivo_col`. |
| `notebooks/silver/10_fact_ventas.py` | Desde `bronze.facventas` con `business_date = DATE(fecfven)` + saneo data sucia. |
| `notebooks/silver/11_fact_ventas_detalle.py` | Desde `bronze.detfventas` + JOIN `fact_ventas` para heredar `business_date`. |
| `notebooks/silver/12_fact_compras.py` | Desde `bronze.compras` con `business_date = DATE(feccom)`. |
| `notebooks/silver/13_fact_compras_detalle.py` | Desde `bronze.detcompras` + JOIN `fact_compras` para heredar `business_date`. |
| `notebooks/silver/14_fact_inventario.py` | Desde `bronze.auxinventario` con `business_date = DATE(docfec)`. |
| `notebooks/silver/20_quality_run.py` | Reglas de calidad: nulos en PKs, totales negativos, business_date futuro, FK huérfanas. Escribe `silver._quality_runs`. |
| `notebooks/silver/30_validate_silver.py` | V1 (duplicados) + V2 (fechas inválidas reportadas). |
| `notebooks/silver/31_reconciliation.py` | V3 (reconciliación silver vs bronze.facventas como proxy sgHermes, mes pasado, top SKUs). |
| `tests/silver/test_transformations.py` | Tests unitarios con `chispa` + datasets sintéticos. |
| `notebooks/silver/_runs/v1_no_duplicates_<fecha>.md` | Evidencia V1. |
| `notebooks/silver/_runs/v2_quality_dates_<fecha>.md` | Evidencia V2. |
| `notebooks/silver/_runs/v3_reconciliation_<fecha>.md` | Evidencia V3. |

### 4.3 Tareas en orden

1. **Dimensiones** (~2 horas):
   - Notebooks 01-06 con SCD Type 1 (snapshot del estado actual).
   - Cada `dim_*` lee `bronze.<tabla> WHERE ingest_date = MAX(ingest_date)`, aplica `TRIM` + tipados + `CREATE OR REPLACE TABLE silver.dim_<entidad>`.
   - `dim_tiempo`: rango desde `MIN(business_date)` en `fact_ventas` hasta `CURRENT_DATE + 365`.
   - Validar: cada `dim_*` con clave única no nula.

2. **Hechos** (~2 horas):
   - Notebooks 10-14.
   - Patrón canónico (`fact_ventas` ejemplo):
     ```sql
     INSERT INTO silver.fact_ventas
     REPLACE WHERE business_date = '<fecha>'
     SELECT
       numfven,
       CAST(fecfven AS TIMESTAMP) AS fecven_ts,
       DATE(fecfven) AS business_date,
       nitter,
       codpag,
       CAST(totfven AS DECIMAL(18,2)) AS total_factura,
       ingest_date
     FROM bronze.facventas
     WHERE ingest_date = '<latest>'
       AND DATE(fecfven) BETWEEN '2020-01-01' AND CURRENT_DATE + 1  -- saneo data sucia
       AND estfven = 'A'  -- solo activos
     ```
   - Detalles (`*_detalle.py`) hacen JOIN con su header para heredar `business_date`.

3. **Reglas de calidad** (~1 hora):
   - Notebook 20 ejecuta sobre cada `fact_*` un set de `assert` Spark:
     - `assert df.where(df.PK.isNull()).count() == 0`, `"PK nula"`
     - `assert df.where(df.total < 0).count() == 0`, `"Total negativo"`
     - `assert df.where(df.business_date > current_date()).count() == 0`, `"Fecha futura"`
   - Cada fallo se loguea a tabla Delta `silver._quality_runs` con `run_id`, `table`, `rule`, `failed_rows`, `timestamp`.
   - Si falla "crítica" → notebook falla. Si "warning" → continúa pero registra.

4. **Reconciliación con sgHermes** (~1 hora):
   - Notebook 31 con V3.
   - Comparar `SUM(total_factura)` mes pasado entre `silver.fact_ventas` y `bronze.facventas` (proxy de sgHermes).
   - Si diferencia > 0.5%: falla.
   - Reportar también: top 10 SKU mes pasado, top 5 cliente, top 3 bodega.

5. **Tests unitarios** (~30 min):
   - `pytest tests/silver/test_transformations.py` con `chispa`.
   - Cada función de transformación (`derive_business_date`, `sanitize_dates`, `aggregate_by_bodega`, etc.) testeada con DataFrame sintético chico.
   - Meta: cobertura > 60% de funciones de transformación.

6. **Capturar evidencias** y actualizar SEGUIMIENTO + crear las 3 notas de `_runs/`.

### 4.4 Definition of Done · Sprint F2-A

- 11 tablas silver creadas: 5 `dim_*` + 1 `dim_tiempo` + 5 `fact_*`.
- `silver._quality_runs` con al menos 1 corrida sin errores críticos.
- V1, V2, V3 verificadas con evidencia en `notebooks/silver/_runs/`.
- Tests `pytest tests/silver/` verdes con cobertura > 60%.
- Linaje visible en Unity Catalog (`SHOW LINEAGE silver.fact_ventas`).

### 4.5 Métricas a capturar

| Métrica | Objetivo |
|---------|----------|
| Tiempo corrida completa silver | < 5 min |
| Tasa filas rechazadas por reglas calidad | < 1% |
| Diff reconciliación silver vs bronze, mes pasado | < 0.5% |

### 4.6 Riesgos específicos F2-A

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F2A-1 | Volúmenes `detfventas` (27k) y `detcompras` (11k) saturan serverless Free | Dividir por chunk mensual de `business_date` |
| R-F2A-2 | `nomter` en `terceros` contiene PII (Habeas Data Col) | Pseudonimización en `dim_tercero` para datasets compartidos; documentar en notebook |
| R-F2A-3 | `codbod` vacío en `auxinventario` (descubierto en R-X2) | Stock por bodega no se desglosa; `dim_bodega` con 1 fila "BD01 / Bodega Principal". Aceptado como limitación BD actual |
| R-F2A-4 | FK huérfanas (ej. `detfventas.codprod` no existe en `productos`) | Rechazar + report (estricto), o registrar como warning (permisivo). Decisión técnica en ADR-0014 DT-F2-3 |

---

## 5 · Sprint F2-B · PWA Login + Búsqueda

**Duración estimada:** 2 sesiones del ejecutor (~6 horas total).

### 5.1 Pre-requisitos

- Sprint F2-A no estrictamente obligatorio (PWA consume API que lee Bronze), pero **recomendable** porque Silver consolida `dim_producto` con `TRIM` aplicado (evita búsquedas que fallan por whitespace).
- API operativa con endpoints F1 (`/auth/login`, `/auth/refresh`, `/products`).
- `users.yaml` con al menos 3 usuarios (admin/vendedor/gerente).

### 5.2 Archivos a crear

**Track T · Frontend Next.js:**

| Path | Rol |
|------|-----|
| `motoshop-app/web/app/login/page.tsx` | Página de login con formulario controlado. |
| `motoshop-app/web/app/api/auth/login/route.ts` | Next.js API route que llama a FastAPI y setea cookies httpOnly. |
| `motoshop-app/web/app/api/auth/refresh/route.ts` | Refresh con cookies httpOnly. |
| `motoshop-app/web/app/api/auth/logout/route.ts` | Limpia cookies. |
| `motoshop-app/web/app/(authenticated)/layout.tsx` | Layout protegido; redirige a `/login` si no hay sesión. |
| `motoshop-app/web/app/(authenticated)/page.tsx` | Dashboard básico con navegación. |
| `motoshop-app/web/app/(authenticated)/products/page.tsx` | Búsqueda de productos paginada. |
| `motoshop-app/web/lib/auth/session.ts` | Helpers de sesión server-side. |
| `motoshop-app/web/lib/auth/store.ts` | Zustand store de auth client-side (estado UI). |
| `motoshop-app/web/lib/api/client.ts` | Fetch wrapper con auto-refresh on 401. |
| `motoshop-app/web/lib/api/hooks.ts` | SWR hooks: `useProducts`, `useStock` (extendido en F2-C). |
| `motoshop-app/web/components/SearchBar.tsx` | Input con debounce 300 ms. |
| `motoshop-app/web/components/ProductCard.tsx` | Card de producto. |
| `motoshop-app/web/components/Pagination.tsx` | Paginación. |
| `motoshop-app/web/middleware.ts` | Middleware Next.js: verificar cookie en rutas `(authenticated)/*`. |
| `motoshop-app/web/tests/auth-flow.spec.ts` | Playwright E2E: login + redirect. |
| `motoshop-app/web/tests/search.spec.ts` | Playwright E2E: búsqueda + paginación. |
| `motoshop-app/web/_runs/v5_session_persistence.md` | Evidencia V5. |
| `motoshop-app/web/_runs/v6_search_latency.json` | Evidencia V6. |
| `motoshop-app/web/_runs/v7_role_perms.md` | Evidencia V7. |

### 5.3 Tareas en orden

1. **Setup base** (~1 hora):
   - Instalar deps: `next-pwa`, `zustand`, `swr`, `idb-keyval`, `tailwindcss`, `@playwright/test`.
   - Configurar Tailwind.
   - Crear `app/api/auth/*` que envuelven la API FastAPI.

2. **Flujo de login** (~2 horas):
   - `app/login/page.tsx` con formulario controlado y validación cliente.
   - `POST /api/auth/login` → llama `https://api.fragloesja.uk/auth/login` → recibe `{access_token, refresh_token}` → setea cookies `httpOnly Secure SameSite=Lax`.
   - Middleware verifica cookie en rutas protegidas.
   - Logout: `POST /api/auth/logout` limpia cookies.
   - Test E2E con Playwright.

3. **Fetch wrapper + búsqueda** (~2 horas):
   - `lib/api/client.ts`: wrapper que lee cookie, llama API, si 401 hace refresh (con lock para serializar refresh concurrente), reintenta.
   - `useProducts(query, limit, offset)`: SWR hook con caché.
   - `app/(authenticated)/products/page.tsx`: input con debounce 300 ms, lista paginada, "Cargar más".

4. **Verificaciones críticas** (~1 hora):
   - **V5** (sesión persiste): login, cerrar tab, reabrir, sigue logueado mientras JWT vivo.
   - **V6** (búsqueda < 1 s): 50 búsquedas con `q=aceite`, `q=correa`, etc. Medir p95.
   - **V7** (roles): login como `vendedor1`, intentar endpoint admin (cuando exista en F3) → 403. Por ahora F2-B verifica que el header `x-role: vendedor` se inyecta correctamente.

### 5.4 Definition of Done · Sprint F2-B

- Login funciona desde celular 4G (probado).
- Sesión persiste entre cierres de pestaña (V5 ✅).
- Búsqueda devuelve resultados < 1 s p95 (V6 ✅).
- Roles propagados correctamente al backend (V7 ✅).
- Tests E2E verdes en `playwright`.

### 5.5 Métricas a capturar

| Métrica | Objetivo |
|---------|----------|
| Tiempo primera respuesta login | < 2 s |
| Latencia búsqueda p95 | < 1 s con 6k productos |
| Bundle size JS inicial | < 200 KB gzipped |

### 5.6 Riesgos específicos F2-B

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F2B-1 | CORS: PWA y API en orígenes distintos (`localhost:3000` vs `api.fragloesja.uk`) | Ya configurado en F1; probar con cookie credenciales |
| R-F2B-2 | Refresh token race (2 requests concurrentes con JWT vencido) | Lock en `lib/api/client.ts` para serializar refresh |
| R-F2B-3 | Mobile keyboard tapa el input | Flexbox + viewport meta correctos; probar en celular real |

---

## 6 · Sprint F2-C · PWA Stock + Offline + Cierre F2

**Duración estimada:** 2 sesiones del ejecutor (~6 horas total).

### 6.1 Pre-requisitos

- Sprint F2-B completado.
- API endpoint `/products/{sku}/stock` operativo (F1 ya lo tiene).

### 6.2 Archivos a crear

| Path | Rol |
|------|-----|
| `motoshop-app/web/app/(authenticated)/products/[sku]/page.tsx` | Ficha de SKU con stock por bodega. |
| `motoshop-app/web/lib/api/hooks.ts` (extender) | `useStock(sku)` + `useStockCache`. |
| `motoshop-app/web/lib/offline/cache.ts` | IndexedDB wrapper con `idb-keyval`. |
| `motoshop-app/web/lib/offline/strategies.ts` | NetworkOnly, StaleWhileRevalidate helpers. |
| `motoshop-app/web/components/StockBadge.tsx` | Badge con cantidad por bodega. |
| `motoshop-app/web/components/SyncStatus.tsx` | Indicador "Datos al día" / "Última sync: X min". |
| `motoshop-app/web/public/manifest.json` | PWA manifest (instalable). |
| `motoshop-app/web/public/icons/*` | Iconos 192px, 512px, maskable. |
| `motoshop-app/web/next.config.mjs` (modificar) | Habilitar `next-pwa` con Workbox. |
| `motoshop-app/web/tests/stock-page.spec.ts` | Playwright E2E: ficha SKU. |
| `motoshop-app/web/tests/offline.spec.ts` | Playwright E2E: modo offline. |
| `motoshop-app/web/_runs/v4_offline_demo_<fecha>.md` | Evidencia V4 con screenshots. |
| `motoshop-app/web/_runs/v8_data_match.md` | Evidencia V8 con 5 SKUs comparados. |

### 6.3 Tareas en orden

1. **Ficha de SKU** (~2 horas):
   - `[sku]/page.tsx`: `useStock(sku)` muestra `total`, `by_bodega[]`.
   - Mostrar también: nombre, código, precio (de `useProducts(q=sku)`).
   - Botón "Actualizar" para invalidar cache manual.

2. **PWA manifest + service worker** (~2 horas):
   - Instalar `next-pwa`, configurar `next.config.mjs`.
   - `manifest.json` con nombre, color tema, iconos.
   - Probar instalación en Chrome desktop y Chrome Android.
   - **V4** (modo offline): cargar la app, modo avión, navegar productos previamente vistos.

3. **Offline cache para catálogo** (~1.5 horas):
   - `lib/offline/cache.ts`: persiste productos consultados en IndexedDB con TTL 1 h.
   - Estrategia: catálogo `StaleWhileRevalidate` (mostrar cache, fetch en background). Stock `NetworkOnly` con fallback a "última conocida hace X min" si offline.
   - `SyncStatus` muestra estado.

4. **V8 reconciliación PWA vs MySQL** (~1 hora):
   - Elegir 5 SKUs aleatorios. Comparar lo que muestra la PWA vs `SELECT codprod, SUM(valor3) FROM auxinventario WHERE codprod IN (...)` directo en MySQL.
   - Documentar en `v8_data_match.md`.

5. **Hito visible: demo en 4G desde celular** (~30 min):
   - Pedir a un usuario real (Javier o gerencia) abrir la PWA en su celular en 4G.
   - Login, buscar "aceite", abrir ficha de un SKU, ver stock.
   - Capturar timing total con cronómetro o grabación de pantalla.
   - **Si > 5 segundos, mitigar antes de cerrar F2.**

### 6.4 Definition of Done · Sprint F2-C

- Ficha de SKU muestra stock total y por bodega correctamente.
- PWA es instalable en Android (Chrome) y desktop.
- V4, V8 cerradas con evidencia.
- Demo desde 4G en celular real ≤ 5 segundos del toque del ícono al ver stock.

### 6.5 Métricas a capturar

| Métrica | Objetivo |
|---------|----------|
| Tiempo carga inicial PWA en 4G | < 3 s — **KPI F2** |
| Bundle size SW + app shell | < 500 KB gzipped |
| Tamaño cache IndexedDB tras 100 búsquedas | < 5 MB |

### 6.6 Riesgos específicos F2-C

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F2C-1 | iOS Safari PWA limitado (push, algunas APIs) | Aceptar; documentar dispositivos garantizados |
| R-F2C-2 | Cache stale tras update de API (formato cambia) | Bump `cache_version` en cookies → flush cache |
| R-F2C-3 | Stock mostrado obsoleto (cache 1 h) | Stock NUNCA se cachea agresivo (NetworkOnly + 5s timeout); solo catálogo. Documentar en UX |

---

## 7 · Riesgos cross-sprint

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F2-X1 | Free Edition Databricks: cuota mensual de horas serverless | Monitor de uso; si > 80% antes de fin de mes, pausar non-essential jobs |
| R-F2-X2 | Demo en 4G falla por latencia Cloudflare | Plan B con celular en WiFi; investigar Tailscale paralelo |
| R-F2-X3 | Vendedor real con celular viejo (Android 7) no soporta features modernos | Babel target ES2017; aceptar pérdida animaciones modernas |
| R-F2-X4 | `users.yaml` se pierde si reinstalan PC | Documentar en runbook + incluir en backups PC |
| R-F2-X5 | Cambios en API rompen contrato con PWA | OpenAPI schema en `/openapi.json`; generar tipos TS desde ahí en F2-B |

---

## 8 · KPIs F2 y cómo se miden

Derivados de PLAN.md §9 y verificaciones críticas.

| KPI | Meta | Cómo se mide |
|-----|------|---------------|
| Cobertura analítica · % tablas core en silver | 100% | Contar tablas en `silver.*` vs 12 core de F1 |
| Adopción PWA · usuarios activos / semana | ≥ 3 | Logs estructurados `POST /auth/login` con `username` distinct |
| Cobertura tests transformaciones silver | > 60% | `pytest --cov=tests/silver` |
| Tiempo carga inicial PWA en 4G | < 3 s | Chrome DevTools throttling 4G + Lighthouse |
| Tasa fallos transformación bronze → silver | < 1% | `silver._quality_runs` rows con `failed_rows > 0` / total rows procesadas |
| Latencia búsqueda `/products?q=` p95 | < 1 s | 50 búsquedas con `wrk` o equivalente; capturar en `v6_search_latency.json` |
| Diff reconciliación silver vs sgHermes mes pasado | < 0.5% | `v3_reconciliation.md` |

---

## 9 · Backout plan

| Si pasa esto… | … hacemos esto |
|---------------|-----------------|
| Silver tiene reconciliación > 0.5% que no se puede arreglar | Stop F2-A; debug; abrir F2-FIX1 |
| PWA demo en 4G toma > 10 segundos | Stop cierre F2-C; activar R-X2 (cache `/stock`); refactor lazy loading |
| Service worker rompe en producción y la PWA no carga | Cambiar `next-pwa` `disable: true` y volver a SSR puro; reabrir con bug aislado |
| API se cae por carga durante demo | Plan B: cache CDN Cloudflare como respaldo (configuración aparte) |
| Falta evidencia versionada de alguna V | F2-FIX1 corto para capturar; análogo a F1-FIX2 |

---

## 10 · Calendario sugerido

### 10.1 Modo serial *(1 ejecutor, ~12 días naturales)*

```
Día 0 — Revisor escribe este plan + ADR-0014. Push.
Día 1 — Humano aprueba ADR-0014.

Día 2 — Ejecutor F2-A.1: Dimensiones silver (01-06) + tests setup. Push.
Día 3 — Ejecutor F2-A.2: Hechos silver (10-14) + reglas calidad (20). Push.
Día 4 — Ejecutor F2-A.3: V1, V2, V3 con evidencia + reconciliación. Push.
Día 5 — Revisor audita Sprint F2-A. GO/NO-GO.

Día 6-7 — Ejecutor Sprint F2-B (Login + búsqueda + V5/V6/V7).
Día 8 — Revisor audita Sprint F2-B.

Día 9-10 — Ejecutor Sprint F2-C (Stock + offline + V4/V8).
Día 11 — Demo real en 4G.
Día 12 — Revisor audita F2 completo. Lecciones de cierre F2. GO a F3.
```

Tiempo total: **~12 días naturales**. Trabajo del ejecutor: **~18-22 horas**.

### 10.2 Modo paralelo *(2 ejecutores, ~6-7 días naturales — recomendado)*

Detalle en §13 (Paralelización).

```
Día 0 — Revisor escribe plan + ADR-0014. Push.
Día 1 — Humano aprueba ADR-0014.

Día 2-4 (en paralelo):
  ├── Dev A (Track A): Sprint F2-A · Silver
  └── Dev T (Track T): Sprint F2-B · PWA Login + Búsqueda

Día 5 — Revisor audita F2-A y F2-B (cada uno por separado).

Día 5-7 — Dev T: Sprint F2-C · PWA Stock + Offline.
            (Dev A libre, o ayuda con observaciones de F2-A si las hubo)

Día 7 — Demo real en 4G.
Día 7-8 — Revisor audita F2 completo. Lecciones cierre F2. GO a F3.
```

Tiempo total: **~6-7 días naturales** (-40% wall-clock). Trabajo del ejecutor (suma de ambos): **~18-22 horas** (igual, solo se reparte).

---

## 11 · Cómo se actualiza este plan

- Al cierre de cada sprint: marcar tareas hechas + métricas reales (no estimadas) en KPIs.
- Si una decisión técnica cambia: actualizar ADR-0014 o crear ADR-0015+.
- Si un riesgo se materializa: moverlo de §7 a SEGUIMIENTO §Tablero de riesgos vivos.

---

## 12 · Paralelización · 2 ejecutores en simultáneo

### 12.1 ¿Qué se puede paralelizar y qué no?

| Sprint | Depende técnicamente de | ¿Paralelo con? |
|--------|--------------------------|-----------------|
| **F2-A · Silver (Track A)** | Bronze (ya está) + ADR-0014 aprobado | ✅ Sí, con F2-B |
| **F2-B · PWA Login + Búsqueda (Track T)** | API endpoints F1 (ya existen) + ADR-0014 aprobado | ✅ Sí, con F2-A |
| **F2-C · PWA Stock + Offline (Track T)** | F2-B (scaffold PWA + auth wrapper + next-pwa setup) | ❌ Espera a F2-B |

**Nota:** F2-A y F2-B son completamente independientes. F2-C depende solo de F2-B, no de F2-A. Si la PWA necesita columnas saneadas con TRIM (DT-F2-1 silver), igual puede consumir el endpoint `/products?q=` de la API (que lee Bronze directo) y el TRIM se aplica en el cliente como cosmética.

### 12.2 Asignación recomendada de roles

| Rol | Sprints | Skill principal | ~Tiempo |
|-----|---------|------------------|---------|
| **Dev A** (Track A) | F2-A | PySpark + SQL + Databricks | ~6 h |
| **Dev T** (Track T) | F2-B, después F2-C | TypeScript + Next.js + PWA | ~12 h (6 + 6) |
| **Reviewer** | Auditoría de ambos | — | ~2-3 h total |

### 12.3 Política de coordinación de archivos compartidos

Hay 3 archivos que ambos agentes van a tocar al cerrar sus tareas. Política para evitar conflictos:

#### `SEGUIMIENTO.md`

Cada agente actualiza **solo su sección**:
- Dev A: §Fase 2 → Track A · Silver entregables, V1/V2/V3, métricas Track A.
- Dev T: §Fase 2 → Track T · PWA entregables, V4/V5/V6/V7/V8, métricas Track T.

Notas de sesión: cada uno escribe su propia nota (Sesión `<N>·Track A` y `<N+1>·Track T`).

**Antes de cualquier `git push`:**
```bash
git pull --rebase origin main
# Si hay conflicto: resolver MANUALMENTE manteniendo lo del otro agente,
# combinar con lo tuyo. Nunca hacer overwrite.
git push origin main
```

#### `PENDIENTES.md`

Mismo patrón: cada uno actualiza su tarea en el bloque correspondiente.

#### `docs/plan-f2.md`

Solo el revisor lo modifica. Los ejecutores NO tocan el plan; reportan al revisor si encuentran algo que requiere ajuste.

### 12.4 Cómo arrancan los 2 agentes

#### Dev A (Track A · Silver)

1. Lee [`INICIAR_AGENTE.md`](../INICIAR_AGENTE.md) y se auto-identifica como **Dev Agent · Track A**.
2. Confirma que ADR-0014 está `Accepted` (mira `docs/decisions/0014-stack-f2.md`).
3. Lee §4 (Sprint F2-A) de este plan.
4. Trabaja en notebooks `notebooks/silver/01_*.py` … `notebooks/silver/31_*.py`.
5. Commits con prefijo `feat(F2-A-silver):`.
6. Al cerrar: ping al revisor con hash de commits y archivos en `_runs/`.

#### Dev T (Track T · PWA)

1. Lee [`INICIAR_AGENTE.md`](../INICIAR_AGENTE.md) y se auto-identifica como **Dev Agent · Track T**.
2. Confirma ADR-0014 `Accepted`.
3. Lee §5 (Sprint F2-B) de este plan.
4. Trabaja en `motoshop-app/web/**/*.{ts,tsx}` y `motoshop-app/web/tests/*.spec.ts`.
5. Commits con prefijo `feat(F2-B-pwa):`.
6. Al cerrar F2-B: ping al revisor → arranca F2-C inmediatamente (no hay que esperar a Track A).
7. Mientras Dev A trabaja en Silver, Dev T también puede arrancar F2-C en seguida — ningún sprint Track T necesita Silver.

### 12.5 Punto de sincronización del revisor

El revisor audita F2-A y F2-B por separado (cada uno con su propio veredicto GO/NO-GO) y vuelve a auditar F2-C cuando termine. Si F2-A queda en NO-GO mientras Dev T avanza con F2-B/C, el problema de Track A se resuelve sin bloquear Track T (los sprints son independientes hasta el cierre final de F2).

**Cierre F2 final:** los 3 sprints deben estar ✅, con sus V correspondientes y las 8 verificaciones críticas + KPIs medidos. Si alguno queda ⚠️ o 🔴, F2 no cierra y se planifica F2-FIX.

### 12.6 Riesgos del modo paralelo

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-F2-P1 | Conflictos de merge en SEGUIMIENTO/PENDIENTES si los 2 pushean al mismo tiempo | `git pull --rebase` antes de cada push. Cada uno solo modifica su sección |
| R-F2-P2 | El revisor se ve saturado auditando 2 sprints en simultáneo | Auditar por separado en sesiones distintas; usar [`INICIAR_REVIEWER.md`](../INICIAR_REVIEWER.md) §3.2 (6 checks) por cada uno |
| R-F2-P3 | Decisión técnica que afecta a los 2 sprints (ej. cambio en API contract) | Cualquier decisión nueva pasa al revisor para evaluar impacto cross-sprint antes de aplicar |
| R-F2-P4 | Dev T encuentra que `/products?q=` tiene whitespace en codprod (necesita silver) | Aceptar; aplicar TRIM en el cliente como workaround. Migrar a leer silver cuando F2-A termine |

---

## 13 · Referencias

- Plan F1: [`plan-f1.md`](plan-f1.md).
- Plan F1.5 hardening: [`plan-f1-hardening.md`](plan-f1-hardening.md).
- Plan F1.9 robustez: [`plan-f1-9.md`](plan-f1-9.md).
- ADR-0011 stack F1: [`decisions/0011-stack-f1.md`](decisions/0011-stack-f1.md).
- **ADR-0013 fecha técnica vs negocio (Accepted, opción C):** [`decisions/0013-fecha-tecnica-vs-negocio.md`](decisions/0013-fecha-tecnica-vs-negocio.md).
- **ADR-0014 stack F2 (Proposed):** [`decisions/0014-stack-f2.md`](decisions/0014-stack-f2.md).
- Sondeo de columnas reales: [`../notebooks/bronze/_runs/business_date_survey_2026-05-29.md`](../notebooks/bronze/_runs/business_date_survey_2026-05-29.md).
- Snapshot del proyecto: [`contexto-proyecto.md`](contexto-proyecto.md).
