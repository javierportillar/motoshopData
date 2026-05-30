# Plan F1-FIX1 · Remediación de auditoría F1

> Sprint correctivo de F1. Nace del **NO-GO a F2** emitido por el revisor el **2026-05-28 (Sesión 12)** tras auditar la entrega marcada como cierre de F1. Mientras este sprint no cierre, F1 vuelve a **🟡** y F2 no arranca.
>
> Antecedente: la auditoría detalla los hallazgos en la nota de Sesión 12 de [SEGUIMIENTO.md](../SEGUIMIENTO.md). Este doc convierte cada hallazgo en una tarea concreta con archivo, criterio de hecho y evidencia.

---

## 1 · Resumen ejecutivo

| Severidad | Hallazgo | Tratamiento |
|-----------|----------|-------------|
| 🔴 C-1 | `/stock` devuelve 0 siempre (no lee `auxinventario`) | **Corregir** |
| 🔴 C-2 | Tests de productos/stock/sales aceptan 500 como pass | **Corregir** |
| 🔴 C-3 | V6 cerrado con notebook que no prueba paginación | **Corregir** |
| 🔴 C-4 | V7 cerrado con notebook que no compara drift | **Corregir** |
| 🔴 C-5 | Passwords reales (`FG28`) en README público | **Corregir** + **rotación urgente** |
| ⚠️ S-1 | Login timing-vulnerable | **Corregir** |
| ⚠️ S-2 | Refresh token en query string | **Corregir** |
| ⚠️ S-3 | Rate limits sobre el plan | **Corregir** |
| ⚠️ S-4 | V2 idempotencia parcial (no probó kill-y-retry) | **Deuda documentada** (R3) |
| ⚠️ S-5 | `infra/databricks_workflow.json` inválido | **Deuda documentada** (R4) |
| 📉 K-1 | Latencia `/stock` p95 no medida | **Medir** |
| 📉 K-2 | Cobertura tests no medida | **Medir** |
| 📉 K-3 | 5 corridas seguidas no probadas | **Medir** (3 corridas adicionales) |

**Mandatorios para cerrar F1:** C-1, C-2, C-3, C-4, C-5, S-1, S-2, S-3, K-1, K-2, K-3.
**Aceptados como deuda en [SEGUIMIENTO §Tablero de riesgos vivos](../SEGUIMIENTO.md#tablero-de-riesgos-vivos):** S-4, S-5.

---

## 2 · 🚨 Paso 0 · Mitigación inmediata de C-5 (humano-PC owner, antes de tocar nada)

> Mientras este paso no se ejecute, **la API expuesta en `https://api.fragloesja.uk` es vulnerable**. Cualquiera con acceso al repo público puede loguearse con `admin/FG28`.

1. Generar 3 passwords aleatorios fuertes (>= 20 chars, sin palabras de diccionario). PowerShell:
   ```powershell
   1..3 | ForEach-Object { -join ((33..126) | Get-Random -Count 24 | ForEach-Object {[char]$_}) }
   ```
   Guardar en password manager. **NO compartir por chat, NO commit.**
2. Generar hashes con `python infra/hash_password.py '<password>'` por cada uno.
3. Editar `motoshop-app/api/users.yaml` (gitignored) con los hashes nuevos.
4. Reiniciar la API (`start_api.ps1` o equivalente). Verificar con `curl POST /auth/login` que `admin` con la nueva password devuelve 200 y la vieja devuelve 401.
5. Confirmar al revisor: *"Rotado, API reiniciada, vieja credencial 401"* — sin compartir las nuevas.

> Hasta acá: el riesgo activo bajó a 0. El historial de Git sigue conteniendo `FG28`, lo cual queda como **deuda residual aceptada** (mismo modelo que F0 R1). Documentado abajo.

---

## 3 · Sprint F1-FIX1.A · Track A · Notebooks honestos

**Duración estimada:** 1 sesión.
**Pre-requisitos:** ninguno (independiente del paso 0).

### Tarea A-1 · `04_check_large_tables` reescrito para probar paginación de verdad

Cierra **C-3** y reabre **V6**.

**Archivos a modificar:**
- `notebooks/bronze/04_check_large_tables.py`
- `notebooks/bronze/04_check_large_tables.sql` (la versión PySpark queda como referencia, la SQL es la ejecutable hoy)

**Patrón requerido:** verificar que paginar `detfventas` con offsets sucesivos cubre el total exactamente una vez, sin duplicados ni huecos. Pseudocódigo:

```python
total = COUNT(*) FROM bronze.detfventas WHERE ingest_date = X
chunks = []
offset = 0
chunk_size = 5000
while offset < total:
    chunk = spark.table(...).where(ingest_date=X).orderBy("numfven","codprod").limit(chunk_size).offset(offset)
    chunks.append(chunk)
    offset += chunk_size
all_rows = chunks[0].unionAll(chunks[1]).unionAll(...).distinct()
assert all_rows.count() == total, "Paginación pierde o duplica filas"
```

Reportar también: tiempo total de paginación, tiempo del COUNT directo. Si la paginación cubre el total con `distinct().count() == COUNT(*)`, V6 ✅.

**Acceptance criteria:**
- El notebook se ejecuta sobre `detfventas` (~27k) y `detcompras` (~11k).
- Imprime explícitamente `assert total == distinct_after_pagination`. Si falla, el job falla.
- Evidencia versionada en `notebooks/bronze/_runs/v6_pagination_<fecha>.md` con valores reales.

**Anotación honesta a registrar:** este test cubre `detfventas` y `detcompras`. Para tablas 100k+ (ej. `detcuentas` si entra en F2+) habrá que volver a probar. Documentar en V6 que el alcance actual es "hasta 30k filas".

### Tarea A-2 · `05_schema_drift` reescrito para comparar entre `ingest_date`s

Cierra **C-4** y reabre **V7**.

**Archivos a modificar:**
- `notebooks/bronze/05_schema_drift.py`
- `notebooks/bronze/05_schema_drift.sql`

**Patrón requerido:** capturar el esquema (columna, tipo, nullable) en al menos dos `ingest_date`s y diffearlos.

```python
def get_schema(table, ingest_date):
    df = spark.table(f"motoshop.bronze.{table}").where(f"ingest_date='{ingest_date}'")
    return [(f.name, str(f.dataType), f.nullable) for f in df.schema.fields]

drift = []
for t in TABLES:
    s_a = get_schema(t, ingest_date_a)   # ej. 2026-05-28
    s_b = get_schema(t, ingest_date_b)   # ej. 2026-05-29
    if set(s_a) != set(s_b):
        drift.append((t, set(s_a) ^ set(s_b)))
assert not drift, f"Schema drift detectado: {drift}"
```

**Pre-condición:** necesitamos 2 `ingest_date`s. Opciones:
- **Opción 1 (recomendada):** correr el dump con `--ingest-date 2026-05-28` y otra vez con `--ingest-date 2026-05-29` (forzar la fecha por argumento) sobre la misma data. El test de drift es válido aunque la "data" sea la misma — lo que se compara es el esquema.
- **Opción 2:** esperar el dump real del día siguiente y correr V7 entonces. Más lento pero más realista.

**Acceptance criteria:**
- Notebook compara explícitamente al menos 2 `ingest_date`s.
- Si los esquemas difieren, el notebook falla (no warning).
- Evidencia en `notebooks/bronze/_runs/v7_drift_<fecha>.md`.

### Tarea A-3 · S-4 idempotencia kill-y-retry — **deuda documentada (R3)**

V2 ya está marcada ✅ pero solo cubre "dos runs limpios". El test verdadero (matar a mitad y verificar conteos finales) **se difiere a F1-FIX2 o se acepta** como deuda residual.

**Acción en F1-FIX1:** registrar en SEGUIMIENTO §Tablero de riesgos vivos:
- **R3 · Idempotencia bajo fallo parcial no probada.** Estado: aceptado provisional. Trigger de re-evaluación: si el dump nocturno falla a mitad y al reintentar quedan filas duplicadas o partición inconsistente. Mitigación pasiva: `INSERT REPLACE WHERE ingest_date='X'` sobreescribe el día completo en cada corrida exitosa, así que un fallo seguido de un retry exitoso converge al estado correcto. Lo que no garantiza es que un fallo a mitad no deje un estado intermedio temporal.

### Tarea A-4 · S-5 `databricks_workflow.json` — **deuda documentada (R4)**

El JSON está corrupto y el flujo real es Task Scheduler de Windows (`run_dump.ps1` + cron 3x diaria). En la práctica, el Workflow de Databricks no se está usando.

**Acción en F1-FIX1:** **eliminar** `databricks_workflow.json` y `create_databricks_workflow.py`, registrar en SEGUIMIENTO:
- **R4 · Workflow Databricks postergado.** Estado: aceptado. La orquestación nocturna corre en Task Scheduler del PC. Trigger de re-evaluación: si el PC se rompe o se mueve la compute a Databricks (F-F del roadmap).

> Alternativa si se prefiere mantener: arreglar el JSON (quitar las 2 líneas extra al final) y verificar que `create_databricks_workflow.py` lo carga sin error. **Por simplicidad recomendamos eliminar.** Documentar como decisión humana.

---

## 4 · Sprint F1-FIX1.B · Track T · Auth + stock real

**Duración estimada:** 1-2 sesiones.
**Pre-requisitos:** Paso 0 (rotación) completado.

### Tarea B-1 · C-1 · `/stock` lee `auxinventario` de verdad

**Archivos a modificar:**

- `motoshop-app/api/src/motoshop_api/db/tables.py` → añadir definición de `auxinventario`.
- `motoshop-app/api/src/motoshop_api/stock/repo.py` → reescribir `get_stock_by_sku`.
- `motoshop-app/api/src/motoshop_api/stock/schemas.py` → confirmar que el esquema soporta `cantidad` y `total`.
- `motoshop-app/api/tests/test_stock.py` → tests reales con FakeRepo.
- `motoshop-app/api/tests/integration/test_stock_real.py` (nuevo) → `@pytest.mark.integration`.

**Pre-trabajo de introspección:** antes de codificar el JOIN, el ejecutor debe consultar el esquema real:

```sql
DESCRIBE auxinventario;
SELECT * FROM auxinventario LIMIT 5;
```

Las columnas esperadas en sgHermes suelen ser `codprod`, `codbod`, `canexi` o `cantidad` (varía). **Documentar los nombres reales en el commit message y en el docstring de la tabla.** Si la columna de cantidad no existe en `auxinventario`, **parar y consultar** — puede que el stock esté en `subinventa` o en otra tabla del dominio inventario (ver `infollm.md §2`).

**Patrón del repo:**

```python
def get_stock_by_sku(self, sku: str) -> dict:
    # 1. Verificar que el producto existe
    prod = select(productos).where(productos.c.codprod == sku)
    # 2. JOIN auxinventario + bodegas
    join = (
        select(
            bodegas.c.codbod, bodegas.c.nombod,
            auxinventario.c.<columna_cantidad>.label("cantidad"),
        )
        .select_from(
            auxinventario.join(bodegas, auxinventario.c.codbod == bodegas.c.codbod)
        )
        .where(auxinventario.c.codprod == sku)
    )
    # 3. Sumar para el total
    total = sum(filas["cantidad"])
    return {"sku": sku, "nomprod": prod_row.nomprod, "total": total, "by_bodega": [...]}
```

**Acceptance criteria:**
- Para un SKU conocido (`28GM003` u otro elegido por el ejecutor), `GET /products/28GM003/stock` devuelve `total > 0` y `by_bodega` con cantidades reales.
- Comparación manual con `SELECT codbod, <cantidad> FROM auxinventario WHERE codprod='28GM003'` en MySQL → mismos números.
- Evidencia en `notebooks/api/_runs/c1_stock_real_<fecha>.md` con el SKU usado, las cifras de la API y las cifras del SQL directo.
- Test integration `pytest -m integration motoshop-app/api/tests/integration/test_stock_real.py` verde.

### Tarea B-2 · C-2 · Refactor de tests con FakeRepos

**Archivos a modificar:**
- `motoshop-app/api/tests/conftest.py` → fixtures para `FakeProductsRepo`, `FakeStockRepo`, `FakeSalesRepo` ya existentes; añadir `app.dependency_overrides`.
- `motoshop-app/api/tests/test_products.py` → reescribir cada test para usar el cliente con override + `FakeProductsRepo` con data fija; **eliminar `assert resp.status_code in (200, 500)`**.
- `motoshop-app/api/tests/test_stock.py` → idem con `FakeStockRepo`.
- `motoshop-app/api/tests/test_sales.py` → idem con `FakeSalesRepo`.
- `motoshop-app/api/tests/integration/` (nuevo directorio) → mover los tests que tocan MySQL aquí; marcar `@pytest.mark.integration`.
- `motoshop-app/api/pyproject.toml` → registrar marker `integration`.

**Patrón del fixture:**

```python
@pytest.fixture()
def app_with_fakes(fake_products_data):
    from motoshop_api.main import app
    from motoshop_api.products.router import get_products_repo
    from motoshop_api.products.repo import FakeProductsRepo

    fake = FakeProductsRepo(items=fake_products_data)
    app.dependency_overrides[get_products_repo] = lambda: fake
    yield app
    app.dependency_overrides.clear()
```

**Acceptance criteria:**
- `pytest -m "not integration"` corre **sin necesidad de MySQL** y todos los asserts verifican lógica real (cifras, longitudes, errores).
- Cobertura medida con `pytest --cov=motoshop_api/auth --cov=motoshop_api/products --cov=motoshop_api/stock --cov=motoshop_api/sales --cov-report=term-missing`.
- **Meta:** > 70% en cada módulo (KPI K-2).
- Evidencia: `notebooks/api/_runs/k2_coverage_<fecha>.md` con el output de `pytest --cov`.

### Tarea B-3 · C-5 · Limpiar credenciales del README

**Archivos a modificar:**
- `motoshop-app/api/README.md` → eliminar la sección "Credenciales de prueba". Reemplazar por: *"Para credenciales, pedir al responsable del proyecto. Se gestionan en el password manager interno; nunca se versionan."*
- `docs/handoff-f1.md` → añadir advertencia en §3.2 Pre-flight: *"`users.yaml` no se versiona. Copiar de `users.yaml.example` y pedir credenciales al humano-PC owner."*
- `.gitignore` raíz → revisar que no se haya colado nada.

**Pre-trabajo:** ejecutar `git log -p | grep -iE "FG28|admin123|vend123|gerente123"` y reportar al revisor cualquier ocurrencia en el historial. Esto NO se borra (deuda aceptada), pero queda documentado.

**Acceptance criteria:**
- Ningún archivo trackeado contiene una contraseña en texto plano (passwords reales o de prueba).
- Grep `git diff --cached | grep -iE "password\s*[:=]\s*['\"][^'\"]+['\"]"` debe estar vacío antes del commit.
- Evidencia: capturar el `git diff` del commit que elimina las creds y registrarlo en la nota de sesión.
- **R2 · Credenciales API en historial** registrada en SEGUIMIENTO §Tablero de riesgos vivos.

### Tarea B-4 · S-1 · Login timing-safe

**Archivos a modificar:**
- `motoshop-app/api/src/motoshop_api/auth/router.py` → reescribir `login`:

```python
# Hash dummy precomputado de un password aleatorio que nunca será válido.
# bcrypt verify contra este toma el mismo tiempo que un verify real.
_DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()

user = get_user_by_username(body.username)
if user is None:
    verify_password(body.password, _DUMMY_BCRYPT_HASH)  # consumir tiempo
    raise HTTPException(401, "Credenciales incorrectas")
if not verify_password(body.password, user.hashed_password):
    raise HTTPException(401, "Credenciales incorrectas")
```

- `motoshop-app/api/tests/test_auth_login.py` → añadir test:

```python
def test_login_timing_is_similar_for_existing_and_nonexisting_users(client, fake_users):
    import time
    # Usuario inexistente
    t0 = time.perf_counter(); client.post("/auth/login", json={"username":"noexiste","password":"x"}); t_no = time.perf_counter() - t0
    # Usuario existente con password mala
    t1 = time.perf_counter(); client.post("/auth/login", json={"username":"admin","password":"wrong"}); t_yes = time.perf_counter() - t1
    # Diferencia menor al 50% del menor de los dos
    assert abs(t_no - t_yes) / min(t_no, t_yes) < 0.5, f"timing leak: no={t_no:.3f}s, yes={t_yes:.3f}s"
```

**Acceptance criteria:**
- El test de timing pasa en CI local.
- V4 se re-marca ✅ con referencia al nuevo test.

### Tarea B-5 · S-2 · Refresh token en body, no en query

**Archivos a modificar:**
- `motoshop-app/api/src/motoshop_api/auth/schemas.py` → añadir `RefreshRequest(BaseModel): token: str`.
- `motoshop-app/api/src/motoshop_api/auth/router.py` → cambiar firma a `async def refresh(request: Request, body: RefreshRequest)`.
- `motoshop-app/api/tests/test_auth_login.py` → actualizar `test_auth_refresh_token_works` para usar `json={"token": ...}` en vez de `params=`.

**Acceptance criteria:**
- El refresh token no aparece nunca en URL ni en logs de acceso de Cloudflare.
- Test actualizado verde.

### Tarea B-6 · S-3 · Rate limits al plan

**Archivo a modificar:**
- `motoshop-app/api/src/motoshop_api/auth/router.py` → `@limiter.limit("10/minute")` en `/auth/login`.
- Cambiar `/auth/refresh` a `@limiter.limit("10/minute")` (consistente).
- `motoshop-app/api/src/motoshop_api/products/router.py` → confirmar `60/minute` (ya está).
- Aplicar `60/minute` también a `/products/{sku}/stock` y `/sales/recent`.

**Acceptance criteria:**
- Test que excede el límite y verifica 429:

```python
def test_login_rate_limit(client):
    for _ in range(10):
        client.post("/auth/login", json={"username":"x","password":"y"})
    resp = client.post("/auth/login", json={"username":"x","password":"y"})
    assert resp.status_code == 429
```

(Nota: el `fixture _disable_rate_limiting` actual es noop, no hace falta tocarlo. Pero este test sí debe correr con el limiter activo.)

---

## 5 · Sprint F1-FIX1.C · KPIs medidos

**Duración estimada:** 1 sesión (corta, requiere acción humana).

### Tarea K-1 · Latencia `/stock` p95

**Mecanismo recomendado:** correr 100 requests secuenciales contra `/products/<sku>/stock` con un SKU real, capturar `duration_ms` del log estructurado, calcular p95 con `jq`.

**Script sugerido (`infra/measure_stock_latency.ps1`):**
```powershell
$token = (curl -X POST https://api.fragloesja.uk/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"<NEW>"}' | ConvertFrom-Json).access_token
1..100 | ForEach-Object {
  Measure-Command { curl https://api.fragloesja.uk/products/28GM003/stock -H "Authorization: Bearer $token" } | Select-Object TotalMilliseconds
} | Export-Csv stock_latencies.csv
```

O con `wrk`/`k6` si está disponible.

**Acceptance criteria:**
- 100 muestras mínimo.
- Cálculo p95 documentado.
- Evidencia en `notebooks/api/_runs/k1_stock_latency_<fecha>.md`.
- **Meta:** p95 < 500 ms.
- Si p95 > 500 ms: documentar, no falla F1 (es KPI no DoD), pero activa R-X2 (cache en memoria) como mitigación pendiente para F2.

### Tarea K-2 · Cobertura > 70%

Cubierta en Tarea B-2. Verificar que después del refactor de tests, el reporte de cobertura supera el umbral.

**Acceptance criteria:**
- `pytest --cov=motoshop_api/auth --cov=motoshop_api/products --cov=motoshop_api/stock --cov=motoshop_api/sales` reporta > 70% en cada uno.
- Evidencia capturada (texto completo del output) en `notebooks/api/_runs/k2_coverage_<fecha>.md`.

### Tarea K-3 · 5 corridas seguidas exitosas del dump

**Mecanismo:** correr el dump 3 veces más (hoy ya hay 2 documentadas). Pueden ser:
- 3 manualmente con `python infra/dump_to_cloud.py --tables-core` separadas por 1h.
- O dejar que Task Scheduler las haga durante el día (cron 3x ya configurado).

**Acceptance criteria:**
- 5 manifests `manifest_<fecha>.json` en `_staging/` con `error=null` en todas las tablas.
- 5 entradas en una tabla de evidencia.
- Evidencia en `notebooks/bronze/_runs/k3_five_runs_<fecha>.md`.
- **Meta:** 5/5 sin errores.

---

## 6 · Cierre y aceptación

Cuando los Sprints A, B, C terminen:

1. **Ejecutor** actualiza SEGUIMIENTO §F1:
   - V6 y V7 vuelven a ✅ con referencia a los nuevos `_runs/`.
   - Tabla de KPIs medidos con las cifras reales.
   - Sección F1-FIX1 cerrada en la bitácora.
2. **Ejecutor** notifica al revisor.
3. **Revisor** audita:
   - Lee los `_runs/` nuevos.
   - Corre `pytest -m "not integration"` localmente o lee el log.
   - Verifica que el README de la API no tiene credenciales.
   - Verifica que `git log -p` no añade nuevas credenciales.
4. **Revisor** decide:
   - ✅ GO a F2 → marca F1 ✅, abre F2 🟡.
   - 🔴 NO-GO → emite F1-FIX2 con lo que falta.

## 7 · Riesgos a registrar en SEGUIMIENTO §Tablero de riesgos vivos

| ID | Riesgo | Estado | Trigger de re-evaluación |
|----|--------|--------|---------------------------|
| **R2** | Credenciales API (`FG28`) en historial de commits | 🟡 Aceptado | Si la API se mueve a una red más expuesta o si se filtra una sesión real. |
| **R3** | Idempotencia bajo fallo parcial no probada | 🟡 Aceptado | Si el dump nocturno falla a mitad y al reintentar quedan duplicados o estado inconsistente. |
| **R4** | Workflow Databricks postergado (corre en Task Scheduler Windows) | 🟡 Aceptado | Si el PC se rompe o se mueve compute a Databricks (F-F del roadmap). |

---

## 8 · Orden de ejecución sugerido

```
Día 0 (urgente):
  Paso 0 (Humano) — rotar passwords + reiniciar API
Día 1:
  Sprint F1-FIX1.A · Notebooks honestos (Tareas A-1 a A-4)
Día 2:
  Sprint F1-FIX1.B · Auth + stock real (Tareas B-1 a B-6)
Día 3:
  Sprint F1-FIX1.C · KPIs medidos
Día 4:
  Cierre + audit del revisor → GO/NO-GO a F2
```

## 9 · Lo que NO entra en F1-FIX1

Quedan registrados como deuda y se reevaluarán antes de F2:

- Workflow Databricks reproducible (R4).
- Test de idempotencia kill-y-retry (R3).
- Conectar repo motoshopData al workspace Databricks (siempre estuvo diferible).
- CI GitHub Actions (siempre estuvo diferible).
- Migración del `users.yaml` a `app_usuarios` en MySQL (es F5).

## 10 · Lecciones para evitar el mismo patrón

> Para el ejecutor que vaya a desarrollar:

1. **Si un test no puede verificar lógica sin servicios externos disponibles, no es un test — es un noop.** Usar `app.dependency_overrides` con FakeRepos siempre.
2. **Marcar una verificación ✅ requiere que la evidencia cumpla el espíritu del gate.** Contar filas no es verificar paginación. Verificar existencia no es verificar drift. Si la evidencia no responde a la pregunta exacta del gate, está incompleta.
3. **Nunca commitear contraseñas, ni siquiera "de demo".** La regla aplica también al README.
4. **Antes de cerrar un sprint, releer las acceptance criteria una a una.** Si alguna está en duda, marcar ⚠️, no ✅.

---

## 11 · Referencias

- Auditoría que originó este sprint: SEGUIMIENTO §Notas de sesión 12 (2026-05-28).
- Plan F1 original: [`docs/plan-f1.md`](plan-f1.md).
- ADR-0011 (stack F1, Accepted): [`docs/decisions/0011-stack-f1.md`](decisions/0011-stack-f1.md).
- Handoff para el ejecutor: [`docs/handoff-f1.md`](handoff-f1.md).
