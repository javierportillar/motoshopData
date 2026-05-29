# ADR-0014 · Stack técnico de Fase 2 (DT-F2-1 a DT-F2-16)

- **Estado:** **Proposed** — bloquea inicio de Sprint F2-A
- **Fecha:** 2026-05-29
- **Bloquea:** F2 (los 3 sprints)
- **Decide:** Humano

## Contexto

Antes de tocar código de F2 hay 16 micro-decisiones técnicas que afectan estructura, dependencias y velocidad. Resolverlas en bloque evita parar a debatir cada hora.

Las primeras 6 (DT-F2-1..6) son sobre **Silver** (Track A). Las siguientes 10 (DT-F2-7..16) son sobre **PWA** (Track T).

Cada decisión tiene una recomendación. El humano confirma o ajusta antes del primer commit de F2.

---

## Track A · Silver

### DT-F2-1 · Patrón de escritura silver idempotente

**Contexto:** silver debe poder reprocesarse por día sin duplicar ni perder datos. Es el mismo problema que resolvimos en bronze con `INSERT REPLACE WHERE ingest_date`, pero ahora la clave es `business_date`.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `CREATE OR REPLACE TABLE ... AS SELECT` | Simple | Pierde particiones de otros días si la query no las incluye |
| B · **`INSERT INTO ... REPLACE WHERE business_date = '...'`** | Idempotente por día; preserva otras particiones | Requiere `CREATE TABLE IF NOT EXISTS` la primera vez |
| C · `MERGE INTO ... USING ... ON` | Fila a fila | Sobrecosto cuando la partición entera se reemplaza |

**Recomendación: B** — mismo patrón de bronze, consistente, idempotente.

**Consecuencias:** todos los notebooks `silver/10_*.py` y `silver/14_*.py` usan este patrón. Primera corrida crea tabla con schema vacío; subsiguientes hacen `INSERT REPLACE WHERE`.

---

### DT-F2-2 · SCD strategy para dimensiones

**Contexto:** las dimensiones (`dim_producto`, `dim_bodega`, `dim_tercero`, `dim_sucursal`, `dim_formapago`) cambian con el tiempo. ¿Capturamos historia o solo el estado actual?

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · **SCD Type 1** (snapshot del estado actual) | Simple; refleja sgHermes hoy | Pierde historia de cambios |
| B · SCD Type 2 (history con `valid_from` / `valid_to`) | Captura historia completa | Complejidad; tablas crecen con el tiempo; no es necesario en F2 |
| C · SCD Type 4 (tabla de historia separada) | Balance | Overkill para volúmenes actuales |

**Recomendación: A · SCD Type 1.**

**Justificación:**
- Las dimensiones actuales tienen pocos cambios (1-2 productos nuevos/día).
- F3 (Gold) y F4 (ML) no requieren history hoy.
- SCD2 se puede agregar después como ADR aparte cuando el negocio lo pida explícitamente (forecast histórico tipo "¿qué precio tenía este SKU en mayo 2025?").

**Consecuencias:** `dim_*.py` usan `CREATE OR REPLACE TABLE silver.dim_<entidad>` con el snapshot del último `ingest_date`.

---

### DT-F2-3 · Reglas de calidad silver

**Contexto:** silver debe rechazar/registrar datos inválidos. Hay dos enfoques principales en Databricks.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Delta Live Tables (DLT) Expectations | Declarative; UI bonita; lineage automático | DLT requiere plan superior a Free Edition |
| B · **PySpark con `assert` + tabla `silver._quality_runs`** | Funciona en Free Edition; control total | Más boilerplate |
| C · Soda / Great Expectations (external libs) | Suite completa | Dep externa; setup complejo |

**Recomendación: B** — única que funciona en nuestro plan actual.

**Consecuencias:** notebook `silver/20_quality_run.py` ejecuta sobre cada `fact_*`:

```python
def assert_no_null_pk(df, table):
    null_count = df.where(df.PK.isNull()).count()
    if null_count > 0:
        write_quality_event(table, "null_pk", null_count, severity="CRITICAL")
        raise AssertionError(f"{table}: {null_count} null PKs")
```

Tabla `silver._quality_runs` con columnas: `run_id`, `table`, `rule`, `failed_rows`, `severity`, `timestamp`.

Severidades:
- **CRITICAL** → notebook falla.
- **WARNING** → continúa pero registra.

---

### DT-F2-4 · Particionado silver

**Contexto:** silver tiene 5 hechos + 6 dimensiones. ¿Particionar?

**Opciones**

| | Hechos | Dimensiones |
|---|---|---|
| A · Sin partición | Simple; OK para <100k filas | Simple |
| B · **`business_date`** (hechos) + **sin partición** (dims) | Queries diarias eficientes | Más particiones pequeñas |
| C · `business_date` + `<dim>_id` | Sobrecarga; no aporta para volumen actual | — |

**Recomendación: B.**

**Justificación:**
- `fact_ventas` con 6k+ filas crece ~200/día. Particionar por `business_date` da queries diarias O(1) en metadata.
- `dim_producto` con 6k filas no necesita partición.
- Coherente con ADR-0013 (silver agrupa por business_date).

**Consecuencias:** `CREATE TABLE silver.fact_<X> ... PARTITIONED BY (business_date)`.

---

### DT-F2-5 · Naming convention

**Contexto:** consistencia para que F3 (Gold) y F4 (ML) puedan navegar sin sorpresas.

**Opciones**

| | Hechos | Dimensiones |
|---|---|---|
| A · **`fact_<entidad>` / `dim_<entidad>`** | Estándar Kimball | — |
| B · `f_ventas` / `d_producto` | Más corto | Menos legible |
| C · `silver_fact_<x>` | Redundante con esquema | — |

**Recomendación: A** — estándar Kimball, legible, esperado.

**Consecuencias:** las 11 tablas silver siguen este patrón. Esquema `silver` en Unity Catalog.

---

### DT-F2-6 · Tests Spark

**Contexto:** transformaciones silver son lógica de negocio. Necesitan tests unitarios con datasets sintéticos chicos.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `pyspark.testing` (stdlib) | Sin deps | API básica, verbose |
| B · **`chispa`** (library) | DataFrame comparison rica, helpers | Una dep más |
| C · Mock Spark con `pandas` | Rápido | No prueba ejecución real Spark |

**Recomendación: B · `chispa`.**

**Consecuencias:** `tests/silver/test_transformations.py` con `chispa.assert_df_equality`. Cada función de transformación testeada con DataFrame Pandas → Spark.

---

## Track T · PWA

### DT-F2-7 · Stack PWA base

**Contexto:** ya decidido en F0 (Next.js 14 App Router + TypeScript estricto, ADR-0003). Reconfirmamos.

**Recomendación: Next.js 14 + TypeScript estricto + ESLint `next/core-web-vitals`.**

**Consecuencias:** ninguna nueva — scaffold ya existente en `motoshop-app/web/`.

---

### DT-F2-8 · Storage del JWT en frontend

**Contexto:** ¿dónde guarda el frontend el token? Las opciones tienen trade-offs de seguridad.

**Opciones**

| | Seguridad | UX | Complejidad |
|---|---|---|---|
| A · `localStorage` / `sessionStorage` | Vulnerable a XSS | Simple | Baja |
| B · `httpOnly` cookie set por API | Inmune a XSS | Más complejo | Media |
| C · **`httpOnly` cookie via Next.js API routes** | Inmune a XSS; API FastAPI no expone cookies | Más complejo pero modular | Media |

**Recomendación: C.**

**Justificación:**
- XSS es el ataque más probable contra una PWA pública.
- Next.js API routes (`/api/auth/login`) actúan como proxy: reciben credenciales del cliente, llaman a FastAPI, reciben JWT, setean cookies `httpOnly Secure SameSite=Lax`.
- El JWT NUNCA está accesible desde JavaScript del cliente.
- Middleware Next.js verifica cookie en rutas protegidas.

**Consecuencias:** 3 routes nuevas (`app/api/auth/{login,refresh,logout}/route.ts`). Cookies con flags estrictos. CSRF protección vía `SameSite=Lax`.

---

### DT-F2-9 · Fetch wrapper con auto-refresh

**Contexto:** cuando el JWT expira (15 min), la PWA tiene que refrescar transparentemente.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `axios` + interceptor `response` | Suite madura; interceptors out-of-box | Dep grande (~50KB gzipped) |
| B · **Fetch nativo + helper con lock** | Cero dep; control total | Reimplementar interceptor |
| C · `ky` o `wretch` | Wrappers livianos | Otra dep |

**Recomendación: B.**

**Justificación:**
- Una PWA tiene que ser liviana. `axios` (~50KB) es desproporcionado para 1 wrapper.
- Fetch nativo + ~30 líneas de helper con lock (para serializar refresh concurrente).

**Implementación esbozada:**

```typescript
let refreshPromise: Promise<void> | null = null;

export async function apiFetch(input: RequestInfo, init?: RequestInit) {
  let resp = await fetch(input, { ...init, credentials: "include" });
  if (resp.status === 401) {
    if (!refreshPromise) {
      refreshPromise = fetch("/api/auth/refresh", { method: "POST", credentials: "include" })
        .then(r => { if (!r.ok) throw new Error("refresh failed"); })
        .finally(() => { refreshPromise = null; });
    }
    await refreshPromise;
    resp = await fetch(input, { ...init, credentials: "include" });
  }
  return resp;
}
```

**Consecuencias:** `lib/api/client.ts` con este patrón. Si refresh también falla → redirigir a `/login`.

---

### DT-F2-10 · State management

**Contexto:** la app tiene estado de auth + datos remotos. ¿Qué herramientas?

**Opciones**

| | Auth | Data fetching |
|---|---|---|
| A · Solo Context API | Funciona | No es óptimo para cache |
| B · Redux Toolkit | Overkill | Overkill |
| C · **Zustand (auth) + SWR (data)** | Liviano y simple | Cache + revalidación gratis |
| D · TanStack Query | Más feature-rich | Más complejo que SWR |

**Recomendación: C.**

**Justificación:**
- Zustand (~1KB) para estado UI de auth (loading, error, user info).
- SWR (~4KB) para data fetching con cache, revalidación, mutación.
- Ninguna sobre-ingenierada.

**Consecuencias:** deps `zustand` + `swr` en `package.json`. `lib/auth/store.ts` con Zustand. `lib/api/hooks.ts` con `useSWR`.

---

### DT-F2-11 · UI library

**Contexto:** ¿usar una library de componentes o construir con Tailwind raw?

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Material UI | Componentes completos | Pesado; opinionated |
| B · shadcn/ui (copy-paste) | Bonito; modificable | Más código en repo |
| C · **Tailwind raw + componentes propios** | Más liviano; control total | Más trabajo inicial |
| D · Mantine | Balanceado | Una dep grande más |

**Recomendación: C.**

**Justificación:**
- F2 PWA necesita ~10 componentes (SearchBar, ProductCard, StockBadge, Pagination, etc.). Hacerlos con Tailwind raw es 1 hora cada uno.
- Bundle size importante para 4G.
- Si en F3 dashboards crecen mucho → reevaluar (probablemente shadcn).

**Consecuencias:** Tailwind ya en F0; agregar `@tailwindcss/forms` para el form de login.

---

### DT-F2-12 · PWA manifest + service worker

**Contexto:** ¿usar library o hacerlo manual?

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Manual (`public/sw.js` custom) | Control total | Mucho boilerplate; mantenimiento |
| B · **`next-pwa`** (envoltorio de Workbox) | Setup en 5 min; recetas estándar | Una dep |
| C · `@serwist/next` | Más moderno | Menos documentación |

**Recomendación: B · `next-pwa`.**

**Justificación:**
- Comunidad grande; recipes para todas las estrategias (NetworkOnly, StaleWhileRevalidate, CacheFirst).
- Auto-genera SW desde config; no tocás JavaScript del SW.

**Consecuencias:** `next.config.mjs` con `withPWA({ dest: 'public', register: true })`. `public/manifest.json` declarado.

---

### DT-F2-13 · Service worker strategy

**Contexto:** ya implícito en DT-F2-12 al elegir `next-pwa`.

**Recomendación: Workbox vía `next-pwa`.**

**Consecuencias:** runtimeCaching configurado por ruta en `next.config.mjs`.

---

### DT-F2-14 · Offline cache para catálogo

**Contexto:** la PWA tiene que mostrar productos consultados incluso sin internet.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `localStorage` | Simple | 5-10 MB límite; sincronómico |
| B · IndexedDB direct API | Capacidad ~50% del disco; async | API verbose |
| C · **IndexedDB con `idb-keyval`** (~600 bytes) | Simple como localStorage pero con IndexedDB | Una mini-dep |
| D · `Dexie.js` | Query rich | Más pesado |

**Recomendación: C.**

**Justificación:**
- Caso de uso simple (key-value: SKU → datos).
- `idb-keyval` es 600 bytes minified.
- Async desde el día 1 (importante en mobile).

**Consecuencias:** `lib/offline/cache.ts` con `get(sku)`, `set(sku, data, ttl)`, `clear()`.

---

### DT-F2-15 · Network strategy

**Contexto:** ¿cuándo confiar en cache vs cuándo ir a la red?

**Opciones por tipo de dato**

| Tipo | Estrategia | Justificación |
|------|------------|---------------|
| Catálogo (productos, búsquedas) | **`StaleWhileRevalidate`** TTL 1 h | Vendedor puede ver lista vieja un rato; revalidación en background es buena UX |
| Stock por SKU | **`NetworkOnly` + 5 s timeout** | Stock crítico para decisión; si offline → mostrar "última conocida hace N min" con advertencia |
| App shell (HTML, JS, CSS) | `CacheFirst` con expiration de build | Para PWA instalada, app shell estable |
| Login y refresh | `NetworkOnly` sin cache | Nunca cachear credenciales |

**Recomendación: la combinación de arriba.**

**Consecuencias:** runtimeCaching en `next.config.mjs` con esos patrones por ruta.

---

### DT-F2-16 · Cache invalidation

**Contexto:** ¿cómo se limpia el cache cuando hay update?

**Opciones**

| | Estrategia |
|---|------------|
| A · Auto bump version on every build | Sin cache hits across builds — costoso |
| B · TTL en cada entry | Simple, predecible |
| C · **TTL + invalidación manual con botón "Actualizar"** | TTL para casos típicos + control fino del usuario |
| D · Push notification del server cuando cambia data | Complejo, F6 |

**Recomendación: C.**

**Consecuencias:**
- Cada entrada de cache tiene TTL: catálogo 1 h, stock 5 min máx (aunque sea NetworkOnly, si offline degrade a cache antigua).
- Componente `SyncStatus.tsx` con botón "Actualizar" que llama `clearAll()` y revalida.

---

## Resumen ejecutivo · todas las DT en una tabla

| # | Decisión | Recomendación | Dependencias nuevas |
|---|----------|----------------|----------------------|
| DT-F2-1 | Escritura silver idempotente | `INSERT REPLACE WHERE business_date` | — |
| DT-F2-2 | SCD para dims | SCD1 snapshot | — |
| DT-F2-3 | Reglas calidad | PySpark assert + `_quality_runs` | — |
| DT-F2-4 | Particionado silver | Hechos por `business_date`; dims sin partición | — |
| DT-F2-5 | Naming convention | `fact_*` / `dim_*` schema `silver` | — |
| DT-F2-6 | Tests Spark | `chispa` | `chispa>=0.10` |
| DT-F2-7 | Stack PWA | Next.js 14 + TS estricto (ya en F0) | — |
| DT-F2-8 | Storage JWT | `httpOnly` cookie via Next API routes | — |
| DT-F2-9 | Fetch wrapper | Fetch nativo + lock | — |
| DT-F2-10 | State management | Zustand + SWR | `zustand>=4` `swr>=2` |
| DT-F2-11 | UI library | Tailwind raw + componentes propios | `@tailwindcss/forms` |
| DT-F2-12 | PWA setup | `next-pwa` | `next-pwa>=5` |
| DT-F2-13 | SW strategy | Workbox vía next-pwa | (incluido) |
| DT-F2-14 | Offline cache | `idb-keyval` | `idb-keyval>=6` |
| DT-F2-15 | Network strategy | Stock=NetworkOnly + Catálogo=StaleWhileRevalidate | — |
| DT-F2-16 | Cache invalidation | TTL + botón manual | — |

**Total deps nuevas:** ~7 packages, todas <10KB gzipped salvo `swr` (~4KB).

---

## Aceptación

Cuando el humano confirme este ADR (o pida cambios), el agente:
- Cambia el estado a `Accepted` y le pone fecha.
- Añade D13 a la bitácora de SEGUIMIENTO.
- Procede con Sprint F2-A.
