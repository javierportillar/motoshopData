# Plan F2-FIX1 · Cierre real de Fase 2

> Origen: auditoría reviewer sobre F2-A/F2-B/F2-C después de los commits `50953ee`, `d04dd29`, `d9829c9`, `47577b8` y `2f16a99`.
>
> Objetivo: convertir la implementación preliminar de F2 en un cierre verificable de fase. No se arranca F3 hasta que V1-V8 estén cerradas con evidencia real.

---

## 1 · Veredicto de origen

F2 queda en **NO-GO** por estos hallazgos:

| Severidad | ID | Sprint | Hallazgo | Tratamiento |
|-----------|----|--------|----------|-------------|
| 🔴 | C-1 | F2-B | Refresh token roto: Next manda `{ refresh_token }`, FastAPI espera `{ token }` | Dev T · T1 |
| 🔴 | C-2 | F2-C | Schema stock desalineado: PWA usa `codprod`/`stock`/`nom_bodega`; API devuelve `sku`/`cantidad`/`nombod` | Dev T · T2 |
| 🔴 | C-3 | F2-A | Hechos silver usan `CREATE OR REPLACE TABLE`, no `INSERT REPLACE WHERE business_date` del ADR-0014 | Dev A · A1 |
| 🔴 | C-4 | F2-B/C | Evidencias V4-V8 siguen en `PENDIENTE`; no responden al gate | Dev T · T7 |
| ⚠️ | S-1 | F2-C | `sw.js` y `workbox-*.js` generados sin versionar o sin política explícita | Dev T · T6 |
| ⚠️ | S-2 | F2-A | V2 demuestra ausencia post-filtro, no política probada de fechas inválidas | Dev A · A4 |
| ⚠️ | S-3 | F2-A | V3 tiene sección Top 10 SKUs incompleta | Dev A · A5 |
| ⚠️ | S-4 | Docs | `SEGUIMIENTO.md` no refleja F2-C implementado ni el NO-GO | Reviewer · R1 |

---

## 2 · Lo que NO entra

- No entra F3 Gold ni dashboards.
- No entra escritura hacia sgHermes ni tablas `app_*`.
- No entra migrar auth provider ni cambiar Cloudflare Tunnel.
- No entra cambiar de stack PWA salvo que `next-pwa` sea inviable; si se cambia a Serwist, documentar razón en evidencia, no abrir ADR salvo que cambie arquitectura.
- No entra rediseñar UI salvo lo mínimo para que el flujo SKU/stock sea usable.

---

## 3 · Paralelización

| Frente | Responsable | Scope | Puede correr en paralelo |
|--------|-------------|-------|--------------------------|
| F2-FIX1-A | Dev A | Silver, calidad, reconciliación, tests analíticos | Sí |
| F2-FIX1-T | Dev T | API/PWA, auth, roles, stock, offline, evidencias móviles | Sí |
| F2-FIX1-R | Reviewer | Auditoría final, sync docs, GO/NO-GO | Después de A y T |

### Política de archivos compartidos

| Archivo | Regla |
|---------|-------|
| `SEGUIMIENTO.md` | Lo actualiza el Reviewer al final. Devs no lo tocan durante FIX salvo instrucción explícita. |
| `PENDIENTES.md` | Lo actualiza el Reviewer. |
| `docs/plan-f2.md` | No tocar en FIX; este plan manda para la remediación. |
| `docs/plan-f2-fix1.md` | Solo Reviewer. |
| `notebooks/silver/_runs/*` | Dev A actualiza V1/V2/V3. |
| `motoshop-app/web/_runs/*` | Dev T actualiza V4/V5/V6/V7/V8. |

Branches sugeridas si trabajan en paralelo:

```bash
fix/f2-a-silver-gate
fix/f2-t-pwa-gate
```

Antes de push:

```bash
git pull --rebase origin main
git status
```

---

## 4 · Dev A · F2-FIX1-A · Silver Gate

### 4.1 Objetivo

Dejar Silver conforme a ADR-0014 y cerrar V1/V2/V3 con evidencia real, no placeholders.

### 4.2 Tareas

| ID | Tarea | Archivos | Criterio de hecho |
|----|-------|----------|-------------------|
| A1 | Corregir patrón idempotente de hechos | `notebooks/silver/10_fact_ventas.py`, `11_fact_ventas_detalle.py`, `12_fact_compras.py`, `13_fact_compras_detalle.py`, `14_fact_inventario.py` | Los hechos no usan `CREATE OR REPLACE TABLE`; usan patrón idempotente compatible con `business_date`. |
| A2 | Mantener dimensiones SCD1 | `01_dim_*` a `06_dim_tiempo.py` | `CREATE OR REPLACE TABLE` se mantiene solo en dimensiones. |
| A3 | Quality run que falla de verdad | `20_quality_run.py` | Registra `_quality_runs`; si hay reglas `CRITICAL`, el notebook falla con `assert_true` o equivalente. |
| A4 | V2 con caso sintético | `30_validate_silver.py`, `_runs/v2_quality_dates_2026-05-29.md` | Incluye prueba controlada de fecha futura/inválida en temp view o dataset sintético, sin tocar bronze ni MySQL. |
| A5 | Completar reconciliación | `31_reconciliation.py`, `_runs/v3_reconciliation_2026-05-29.md` | V3 incluye ventas, diferencia %, mes usado, top 10 SKUs y explicación si se usa “último mes con datos”. |
| A6 | Reemplazar tests cosméticos | `tests/silver/test_transformations.py`, `notebooks/silver/32_test_silver.py` | No quedan `assert True` como prueba de negocio; tests validan lógica o datos reales. |
| A7 | Capturar evidencia final | `notebooks/silver/_runs/v1_no_duplicates_2026-05-29.md`, `v2_quality_dates_2026-05-29.md`, `v3_reconciliation_2026-05-29.md` | Los tres archivos tienen resultados reales y ninguna sección “pendiente/completar”. |

### 4.3 Patrón esperado para hechos

La implementación exacta puede variar por limitaciones de SQL Warehouse, pero debe preservar esta semántica:

1. Crear tabla si no existe.
2. Reprocesar particiones por `business_date` sin destruir días no incluidos.
3. Poder correr dos veces sin duplicar filas.

Si `INSERT INTO ... REPLACE WHERE business_date IN (...)` no es viable para una tabla por sintaxis, Dev A debe documentar en `_runs/v1_no_duplicates_*.md` la alternativa equivalente y por qué mantiene idempotencia.

### 4.4 Comandos y ejecuciones esperadas

Local:

```bash
pytest tests/silver -v
```

Databricks / SQL Warehouse:

```text
10_fact_ventas.py
11_fact_ventas_detalle.py
12_fact_compras.py
13_fact_compras_detalle.py
14_fact_inventario.py
20_quality_run.py
30_validate_silver.py
31_reconciliation.py
32_test_silver.py
```

### 4.5 Definition of Done Dev A

- V1 duplicados ✅ con evidencia real.
- V2 fechas inválidas ✅ con política demostrada.
- V3 reconciliación ✅ con diff < 0.5% y top SKUs completo.
- Hechos silver idempotentes por `business_date` o alternativa documentada equivalente.
- Tests locales y Databricks verdes.
- Sin `PENDIENTE`, `Completar`, `assert True` cosmético en archivos de cierre.

---

## 5 · Dev T · F2-FIX1-T · PWA Gate

### 5.1 Objetivo

Cerrar V4/V5/V6/V7/V8 con PWA real y corregir contratos API/PWA rotos.

### 5.2 Tareas

| ID | Tarea | Archivos | Criterio de hecho |
|----|-------|----------|-------------------|
| T1 | Arreglar refresh token | `motoshop-app/web/app/api/auth/refresh/route.ts` | Next envía `{ token: refreshToken }`, compatible con `RefreshRequest.token`. V5 prueba refresh o persistencia real. |
| T2 | Alinear schema stock | `lib/api/hooks.ts`, `app/(authenticated)/products/[sku]/page.tsx` | Frontend usa `sku`, `nombod`, `cantidad`; no lee campos inexistentes (`codprod`, `nom_bodega`, `stock`). |
| T3 | Mostrar precio real o documentar bloqueo | API `products` y PWA | Preferido: `ProductOut` incluye `precio` desde `preciosxpro`. Si no se puede cerrar en FIX, documentar bloqueo con query y dejar precio fuera del hito. |
| T4 | Probar roles de verdad | API mínima admin o endpoint protegido existente | Usuario `admin` obtiene 200; usuario `vendedor` obtiene 403. Evidencia V7 con curls. |
| T5 | Ficha SKU funcional | `[sku]/page.tsx`, `ProductCard.tsx` | Muestra nombre, SKU, stock total y bodega. Botón “Actualizar” fuerza revalidación. |
| T6 | Offline real + SW reproducible | `next.config.mjs`, `public/manifest.json`, offline cache, `.gitignore` | Build productivo genera PWA instalable. No quedan `sw.js`/`workbox` untracked sin política explícita. |
| T7 | Evidencias reales | `motoshop-app/web/_runs/v4_offline_demo.md`, `v5_session_persistence.md`, `v6_search_latency.json`, `v7_role_perms.md`, `v8_data_match.md` | Ningún archivo dice `PENDIENTE`; todos tienen fecha, método, resultado y salida real. |
| T8 | Tests frontend | `tests/*.spec.ts` | `npm run typecheck`, `npm run build` y Playwright relevante verdes. Tests que requieren API real no cuentan si quedan skipped para el gate. |

### 5.3 Mediciones obligatorias

#### V5 · Persistencia de sesión

Demostrar:

1. Login real.
2. Cerrar pestaña/app.
3. Reabrir antes de expirar JWT.
4. Sigue en ruta protegida o refresca correctamente.

Evidencia: `motoshop-app/web/_runs/v5_session_persistence.md`.

#### V6 · Búsqueda < 1s

Medir 50 búsquedas reales por la ruta de PWA/proxy, no solo llamada directa a repo.

Archivo: `motoshop-app/web/_runs/v6_search_latency.json`.

Formato mínimo:

```json
{
  "verificacion": "V6 · Busqueda < 1s con productos reales",
  "fecha": "2026-05-29",
  "resultado": "PASS",
  "total_busquedas": 50,
  "p50_ms": 0,
  "p95_ms": 0,
  "p99_ms": 0,
  "queries": ["aceite", "correa", "filtro"],
  "metodo": "PWA -> Next proxy -> FastAPI -> MySQL",
  "meta_cumplida": true
}
```

#### V7 · Roles

Si no existe endpoint admin en F2, crear uno mínimo read-only y seguro para verificación, por ejemplo `GET /admin/ping`, protegido por rol `admin`. No introducir escritura.

Evidencia: curls con:

- `admin` → 200.
- `vendedor` → 403.

#### V8 · PWA vs MySQL

Comparar 5 SKUs aleatorios:

```sql
SELECT codprod, SUM(valor3)
FROM auxinventario
WHERE codprod = '<SKU>'
GROUP BY codprod;
```

Evidencia: tabla con SKU, PWA stock, MySQL stock, diff y PASS/FAIL.

### 5.4 Comandos esperados

En `motoshop-app/web`:

```bash
npm run typecheck
npm run build
npx playwright test
```

Si Playwright E2E necesita API real, correr con API real y documentar URL/fecha en `_runs/`. Skips no cierran gates.

### 5.5 Definition of Done Dev T

- V4 offline ✅ con prueba real post-cache.
- V5 sesión ✅ con refresh/persistencia funcional.
- V6 búsqueda ✅ p95 < 1s por PWA/proxy.
- V7 roles ✅ admin 200 / vendedor 403.
- V8 dato correcto ✅ 5 SKUs comparados contra MySQL.
- Ficha SKU muestra stock correcto según contrato real de API.
- Build productivo PWA reproducible desde Git.
- Sin evidencia en estado `PENDIENTE`.

---

## 6 · Evidencias obligatorias por gate

| Gate | Responsable | Archivo | Debe contener |
|------|-------------|---------|---------------|
| V1 | Dev A | `notebooks/silver/_runs/v1_no_duplicates_2026-05-29.md` | 11/11 tablas, filas, distinct, duplicadas, PASS/FAIL. |
| V2 | Dev A | `notebooks/silver/_runs/v2_quality_dates_2026-05-29.md` | Política de fechas inválidas + caso sintético probado. |
| V3 | Dev A | `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md` | Mes usado, ventas bronze/silver, diff %, top 10 SKUs. |
| V4 | Dev T | `motoshop-app/web/_runs/v4_offline_demo.md` | Pasos, dispositivo/navegador, resultado offline, screenshots si aplica. |
| V5 | Dev T | `motoshop-app/web/_runs/v5_session_persistence.md` | Login, cierre/reapertura, refresh o cookie viva, resultado. |
| V6 | Dev T | `motoshop-app/web/_runs/v6_search_latency.json` | 50 búsquedas, p50/p95/p99, método de medición. |
| V7 | Dev T | `motoshop-app/web/_runs/v7_role_perms.md` | Curls admin/vendedor con status. |
| V8 | Dev T | `motoshop-app/web/_runs/v8_data_match.md` | 5 SKUs, PWA vs MySQL, diff < 0.5%. |

---

## 7 · Auditoría final Reviewer · F2-FIX1-R

El Reviewer solo audita después de que Dev A y Dev T reporten commits.

### 7.1 Checks obligatorios

1. `git status --short` limpio o solo cambios documentales del reviewer.
2. `git log --oneline -20` y `git show --stat` de commits F2-FIX1.
3. Grep de secretos nuevos en commits F2-FIX1.
4. Grep `PENDIENTE|Completar|assert True|test.skip` en archivos de evidencia/tests relevantes.
5. Revisar que V1-V8 responden a la pregunta exacta del gate.
6. Verificar pruebas reportadas: pytest silver, Databricks tests, typecheck/build/Playwright.
7. Verificar que no se introdujo escritura operacional ni endpoints peligrosos.
8. Sincronizar `SEGUIMIENTO.md`, `PENDIENTES.md` y `docs/contexto-proyecto.md`.
9. Emitir GO/NO-GO a F3.

### 7.2 Criterio GO a F3

| Área | Condición |
|------|-----------|
| Silver | 11 tablas creadas; hechos idempotentes; V1/V2/V3 con evidencia real. |
| PWA | Login, refresh, búsqueda, ficha SKU, stock y offline funcionando. |
| Roles | Vendedor bloqueado explícitamente en endpoint admin/read-only. |
| Métricas | Búsqueda p95 < 1s; carga PWA documentada si se mide en 4G/Lighthouse. |
| Datos | 5 SKUs PWA vs MySQL cuadran < 0.5%. |
| Docs | `SEGUIMIENTO.md` refleja estado real; sin checks falsos. |

Si cualquiera de V1-V8 queda ⚠️ o 🔴, F2 sigue abierta y se abre F2-FIX2 con alcance mínimo.

---

## 8 · Backout plan

| Si pasa esto | Acción |
|--------------|--------|
| `INSERT REPLACE WHERE` no funciona en SQL Warehouse | Documentar error exacto y usar alternativa idempotente demostrable; Reviewer decide si acepta. |
| Precio real no se puede obtener de `preciosxpro` rápido | Cerrar F2 sin precio solo si stock y SKU cuadran; documentar deuda visible para F3. |
| PWA offline falla por `next-pwa` | Desactivar SW temporalmente y abrir subfix T6; no cerrar V4. |
| V8 no cuadra con MySQL | NO-GO; depurar API stock antes de cualquier demo. |
| Playwright no puede correr en máquina actual | Capturar prueba manual reproducible con outputs/capturas, pero typecheck/build siguen obligatorios. |

---

## 9 · Mensaje de cierre esperado de cada dev

Dev A reporta:

```text
F2-FIX1-A listo. Commits: <hashes>.
pytest tests/silver -v: <resultado>.
Databricks notebooks 10-14,20,30,31,32: <resultado>.
Evidencias V1/V2/V3 actualizadas: <paths>.
Listo para auditoría reviewer.
```

Dev T reporta:

```text
F2-FIX1-T listo. Commits: <hashes>.
npm run typecheck/build/playwright: <resultado>.
Evidencias V4/V5/V6/V7/V8 actualizadas: <paths>.
V8 SKUs comparados: <lista>.
Listo para auditoría reviewer.
```
