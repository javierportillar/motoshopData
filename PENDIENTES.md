# Pendientes del humano

> Lista priorizada de tareas que tiene que ejecutar **Javier** entre sesiones del agente. Cosas que el agente **no puede hacer** (tocan sgHermes, la red local, cuentas externas, decisiones de negocio) o que requieren confirmación humana.
>
> **Convención:** cada sesión añade un bloque nuevo arriba. Los pendientes resueltos se marcan ✅ pero **no se borran** — quedan como historial. Cuando algo cambia de prioridad o se vuelve obsoleto, se reescribe y se anota el motivo.

**Leyenda:** ⬜ pendiente · 🟡 en progreso · ✅ hecho · 🔴 bloqueado · ❌ descartado

---

## Sesión 2026-05-28 (14) · F1-FIX1 · Remediación de auditoría — 🔴 NO-GO a F2

### Resumen
La auditoría de F1 (Sesión 14) detectó **5 hallazgos críticos**, **5 serios** y **3 KPIs sin medir**. F1 vuelve a 🟡. Plan correctivo: [`docs/plan-f1-fix1.md`](docs/plan-f1-fix1.md). Mientras no cierre, F2 no arranca.

> Por favor leé [`docs/plan-f1-fix1.md`](docs/plan-f1-fix1.md) antes de actuar — tiene los detalles, archivos exactos, criterios de aceptación y orden recomendado.

---

### 🚨 PASO 0 — Mitigación URGENTE de C-5 (humano, antes de cualquier otra cosa)

> Mientras esto no pase, la API en `https://api.fragloesja.uk/` es **vulnerable**. Cualquiera con acceso al repo puede loguearse con `admin/FG28`.

#### 0.1 ⬜ Generar 3 passwords aleatorios fuertes

PowerShell:
```powershell
1..3 | ForEach-Object { -join ((33..126) | Get-Random -Count 24 | ForEach-Object {[char]$_}) }
```
Guardar en password manager. **NO** compartir por chat, **NO** commitear, **NO** anotar en SEGUIMIENTO ni en commit messages (lección R1).

#### 0.2 ⬜ Generar hashes bcrypt
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
.\.venv\Scripts\Activate.ps1
python ..\..\infra\hash_password.py '<password admin>'
python ..\..\infra\hash_password.py '<password vendedor1>'
python ..\..\infra\hash_password.py '<password gerente1>'
```

#### 0.3 ⬜ Editar `motoshop-app/api/users.yaml` (gitignored)

Reemplazar los `hashed_password` por los nuevos. Verificar que NO se hace `git add`.

#### 0.4 ⬜ Reiniciar la API
```powershell
.\infra\start_api.ps1   # o reiniciar el servicio según tu setup
```

#### 0.5 ⬜ Verificar
```powershell
# La vieja debe fallar
curl -X POST https://api.fragloesja.uk/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"FG28"}'
# → debe devolver 401

# La nueva debe funcionar
curl -X POST https://api.fragloesja.uk/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"<new>"}'
# → debe devolver 200 con JWT
```

#### 0.6 ⬜ Reportar al revisor
*"Paso 0 hecho: vieja 401, nueva 200, API reiniciada."* — sin compartir las nuevas.

---

### Sprint F1-FIX1.A · Track A · Notebooks honestos (Ejecutor)

#### A-1 ⬜ Reescribir `04_check_large_tables` para probar paginación real

`notebooks/bronze/04_check_large_tables.py`: paginar `detfventas` (~27k) y `detcompras` (~11k) con offsets sucesivos de 5000, unir, comparar `distinct.count() == COUNT(*)`. Falla si pierde o duplica filas. Evidencia: `notebooks/bronze/_runs/v6_pagination_<fecha>.md`. Detalle: plan-f1-fix1.md §3 A-1.

#### A-2 ⬜ Reescribir `05_schema_drift` para comparar 2 `ingest_date`s

`notebooks/bronze/05_schema_drift.py`: capturar (nombre, tipo, nullable) de cada tabla en dos `ingest_date`s y diffearlas. Si hay drift, falla. Pre-requisito: 2 corridas del dump con `--ingest-date` distinto. Evidencia: `notebooks/bronze/_runs/v7_drift_<fecha>.md`. Detalle: plan-f1-fix1.md §3 A-2.

#### A-3 ⬜ Eliminar (o reparar) `databricks_workflow.json` y `create_databricks_workflow.py`

El JSON está corrupto sintácticamente (`Extra data`). El flujo real corre en Task Scheduler. **Recomendado: eliminar ambos archivos** y dejar R4 documentado. Si prefieres mantener, hay que arreglar las 2 líneas extra al final del JSON y verificar que el script lo carga sin error.

---

### Sprint F1-FIX1.B · Track T · Auth + stock real (Ejecutor)

> Prerequisito: Paso 0 completado.

#### B-1 ⬜ `/stock` debe leer `auxinventario` de verdad

Introspectar primero `DESCRIBE auxinventario;` y `SELECT * FROM auxinventario LIMIT 5;` para descubrir el nombre real de la columna de cantidad. Añadir tabla a `db/tables.py`. Reescribir `stock/repo.py` con JOIN `auxinventario ⨝ bodegas`. Evidencia: `notebooks/api/_runs/c1_stock_real_<fecha>.md` comparando la respuesta de la API contra `SELECT` directo en MySQL para un SKU concreto. Detalle: plan-f1-fix1.md §4 B-1.

#### B-2 ⬜ Refactor de tests con FakeRepos + `pytest.mark.integration`

- Mover tests que necesitan MySQL a `tests/integration/`.
- Reescribir `test_products.py` / `test_stock.py` / `test_sales.py` con `app.dependency_overrides` + `FakeRepos` que ya están en los `repo.py`.
- **Eliminar todos los `assert resp.status_code in (200, 500)`** y sus equivalentes.
- Registrar marker `integration` en `pyproject.toml`.
- Correr `pytest -m "not integration" --cov=...` y guardar el output en `notebooks/api/_runs/k2_coverage_<fecha>.md`. Meta: > 70%. Detalle: plan-f1-fix1.md §4 B-2.

#### B-3 ⬜ Limpiar credenciales del README

- Eliminar la tabla "Credenciales de prueba" de `motoshop-app/api/README.md`.
- Reemplazar por "Para credenciales, pedir al responsable del proyecto. Se gestionan en password manager interno; nunca se versionan."
- Actualizar `docs/handoff-f1.md` §3.2.
- Antes de commit: `git diff --cached | grep -iE "password\s*[:=]"` debe estar vacío.

#### B-4 ⬜ Login timing-safe (mitiga S-1)

Añadir dummy bcrypt verify cuando `user is None`. Añadir test que mida tiempos y verifique que la diferencia entre "usuario existe" y "usuario no existe" es < 50% del menor.

#### B-5 ⬜ Refresh token en body (mitiga S-2)

Cambiar `POST /auth/refresh` a body JSON `{"token": "..."}`. Actualizar tests.

#### B-6 ⬜ Rate limits al plan (mitiga S-3)

`/auth/login` y `/auth/refresh`: 10/min. `/products` y `/products/{sku}/stock` y `/sales/recent`: 60/min. Añadir test que excede el límite y verifica 429.

---

### Sprint F1-FIX1.C · KPIs medidos (Ejecutor + Humano)

#### C-K1 ⬜ Latencia `/stock` p95

100 requests secuenciales contra `/products/<sku>/stock` con un SKU real (post-B-1). Calcular p95. Evidencia: `notebooks/api/_runs/k1_stock_latency_<fecha>.md`. Meta: < 500 ms.

#### C-K2 ⬜ Cobertura > 70%

Cubierto por B-2. Confirmar que el reporte `pytest --cov` supera 70% en `auth/`, `products/`, `stock/`, `sales/`.

#### C-K3 ⬜ 5 corridas seguidas exitosas del dump

Hoy hay 2 documentadas. Necesitamos 3 más. Pueden venir naturalmente del schedule 3x diaria. Una vez haya 5 manifests con `error=null` consecutivos: `notebooks/bronze/_runs/k3_five_runs_<fecha>.md`.

---

### Cierre de F1-FIX1

Cuando todo esté hecho, ejecutor:
1. Actualiza SEGUIMIENTO §F1: V6/V7 vuelven a ✅, KPIs con cifras reales, sección F1-FIX1 cerrada.
2. Ping al revisor.
3. Revisor audita los `_runs/` nuevos + corre `pytest -m "not integration"` + verifica que README está limpio.
4. Si todo pasa: F1 ✅ y abre F2 🟡. Si no: F1-FIX2.

---

## Sesión 2026-05-28 (11) · Handoff F1 listo — sin acciones humanas pendientes

### Resumen
ADR-0011 Accepted, plan F1 detallado y aprobado, handoff doc escrito. El ejecutor (otra sesión de IA o vos en el PC) puede arrancar Sprint F1-A leyendo [`docs/handoff-f1.md`](docs/handoff-f1.md). El revisor (otra sesión Claude) auditará al cierre de cada sprint.

### Pendientes diferibles (no bloquean F1-A)
- ⬜ Conectar repo `motoshopdata` al workspace Databricks (3 min; mejora UX pero no necesario para correr notebooks importados).
- ⬜ CI básico GitHub Actions (lint + tests) — se planificará en Sprint F1-C o cierre F1.

### Próximo paso
Ejecutor arranca **Sprint F1-A · Bronze de las 12 tablas core** siguiendo [`docs/plan-f1.md`](docs/plan-f1.md) §Sprint F1-A.

---

## Sesión 2026-05-28 (10) · Aprobar stack F1 antes de arrancar F1-A

### Resumen
Plan detallado de F1 listo: [`docs/plan-f1.md`](docs/plan-f1.md) (3 sprints, archivos exactos, V1-V7 mapeadas, KPIs medibles, riesgos, backout) + [ADR-0011](docs/decisions/0011-stack-f1.md) con 10 decisiones técnicas.

**✅ Cerrado 2026-05-28:** ADR-0011 aprobado en bloque sin ajustes. Ejecutor confirmado en el mismo PC Windows (acceso directo a entorno). Push directo a `main` sin PRs. Handoff doc creado en [`docs/handoff-f1.md`](docs/handoff-f1.md).

### 1. ✅ Revisar y aprobar ADR-0011 *(bloquea Sprint F1-A)*

Abrir [`docs/decisions/0011-stack-f1.md`](docs/decisions/0011-stack-f1.md) y revisar la tabla resumen al final. 10 decisiones, cada una con su recomendación:

| # | Decisión | Recomendación |
|---|----------|----------------|
| DT-1 | Acceso MySQL desde API | **SQLAlchemy 2.0 core + pymysql** |
| DT-2 | JWT + bcrypt | **pyjwt + bcrypt** |
| DT-3 | Rate limiting | **slowapi in-memory** |
| DT-4 | Store usuarios F1 | **`users.yaml` gitignored** |
| DT-5 | Paginación | **offset + limit (50 / 200)** |
| DT-6 | Bronze idempotente | **`INSERT REPLACE WHERE`** |
| DT-7 | Manifest | **Subir al Volume `/_manifests/`** |
| DT-8 | Logging | **structlog JSON + PII redaction** |
| DT-9 | Tests API | **Repos + `pytest.mark.integration`** |
| DT-10 | Timezone | **Bronze raw → Silver UTC → API UTC `Z`** |

**Opciones de respuesta:**
- **"OK todas"** → marco D11 Accepted, ajusto el ADR a Accepted, y arranco F1-A en la próxima sesión.
- **"OK pero cambia X"** → me dices qué quieres distinto y lo refleja antes de arrancar.
- **"Necesito pensar Y"** → te dejo más opciones / contexto donde tengas duda.

### (Opcional, no bloquea F1-A) Cosas diferibles ya conocidas
- ⬜ Conectar repo `motoshopdata` al workspace Databricks (3 min, te pasé los pasos en sesiones previas).
- ⬜ CI básico GitHub Actions — lo escribo cuando lo pidas.

---

## Sesión 2026-05-28 (9) · Smoke test con datos reales + cierre F0 ✅

### Resumen
Se re-ejecutó el smoke test con `bodegas` (1 fila) y `formapago` (20 filas). Ambos pasaron validación (N > 0, conteos cuadran 1:1). Verificación #3 ✅. **F0 cerrado.**

### ✅ Fase 0 cerrada — no hay más acciones humanas pendientes
- ✅ 1. Smoke test real con `bodegas` (1 fila) y `formapago` (20 filas) — evidencia en `notebooks/bronze/_runs/smoke_test_2026-05-28.md`
- Pendientes diferibles: conectar repo a workspace Databricks, CI básico (GitHub Actions)

---

## Sesión 2026-05-28 (8) · Remediación de auditoría — 1 acción para cerrar F0

### Resumen
La auditoría detectó dos cosas en el cierre anterior: (a) el commit de cierre filtró la nueva password en su mensaje (**deuda aceptada** — no se va a corregir, ver R1 en SEGUIMIENTO), y (b) el smoke test atestó la verificación #3 con `sucursales` que tenía 0 filas, lo cual no demuestra movimiento de datos. Esta acción cierra (b).

El agente preparó: notebook SQL ejecutable en SQL Warehouse, scripts reproducibles del Volume y del Warehouse, deuda de credenciales documentada como riesgo vivo.

### 1. ✅ Re-ejecutar el smoke test con una tabla con datos *(bloquea cierre F0)*

**Por qué:** `sucursales` salió con 0 filas. El gate pide *"aunque sea con 10 filas"*. Hay que elegir una tabla pequeña pero **no vacía**. Candidatas:
- `bodegas` (~10 filas, recomendado — modelo mental directo)
- `formapago` (~20 filas — códigos de pago)
- `subproduct` (~? filas — alternativa)

**En el PC Windows:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
.\.venv-infra\Scripts\Activate.ps1

# Dump de las dos tablas pequeñas a Parquet local + UC Volume
python infra\dump_to_cloud.py --tables bodegas formapago
# El script imprime: filas, tamaño, ruta del Volume. Copiá esa salida.
```

**En Databricks (SQL Editor del SQL Warehouse):**

1. Importar/abrir [`notebooks/bronze/01_ingest_smoke_test.sql`](notebooks/bronze/01_ingest_smoke_test.sql) (o pegar las celdas en un nuevo notebook SQL).
2. Setear los widgets:
   - `table_name = bodegas`
   - `ingest_date = <la fecha del dump>` (por defecto hoy)
3. **Run all.**
4. La última celda 5 (validación) debe devolver:
   ```
   ✅ OK — conteos cuadran y N > 0 (verif. #3 cumplida)
   ```
5. Repetir el run con `table_name = formapago` para confirmar que el patrón funciona en >1 tabla.

### 2. ⬜ Capturar la evidencia en el repo *(2 minutos)*

Crear `notebooks/bronze/_runs/smoke_test_2026-05-28.md` con este contenido base (rellenar valores reales):

```markdown
# Smoke test bronze · 2026-05-28

## bodegas (ingest_date=2026-05-28)
- Dump local: N filas, X KB, Y segundos
- Subida UC Volume: ok
- COUNT(*) parquet:  N
- COUNT(*) bronze:   N
- Verdict: ✅ OK — conteos cuadran y N > 0

## formapago (ingest_date=2026-05-28)
- Dump local: N filas, X KB, Y segundos
- Subida UC Volume: ok
- COUNT(*) parquet:  N
- COUNT(*) bronze:   N
- Verdict: ✅ OK — conteos cuadran y N > 0

## DESCRIBE HISTORY motoshop.bronze.bodegas (5 últimas operaciones)
| version | timestamp | operation        | userName |
|---------|-----------|------------------|----------|
| ...     | ...       | CREATE_OR_REPLACE| ...      |
```

Commit:
```powershell
git add notebooks/bronze/_runs/smoke_test_2026-05-28.md
git commit -m "feat(F0): evidencia smoke test bronze - bodegas y formapago N>0"
git push
```

### 3. Reportar al agente
"Smoke test honesto pasó: bodegas N=X, formapago N=Y, evidencia en `notebooks/bronze/_runs/smoke_test_2026-05-28.md`." El agente marca verificación #3 a ✅, F0 cierra (con #5 como ⚠️ documentado por deuda aceptada), y abre F1.

---

### (Opcional, complementarias) Scripts reproducibles ya en el repo

Si querés re-correr el setup desde cero en otra máquina, ahora hay scripts versionados que reemplazan los clicks de la UI:

```powershell
python infra\create_uc_volume.py        # crea (o verifica) motoshop.bronze._landing
python infra\create_sql_warehouse.py    # crea (o verifica) auto_stop_mins ≤ 10
```

Ambos son idempotentes y validan permisos. La sesión 7 los hizo manualmente; estos scripts dejan el trabajo reproducible para auditoría académica y para F-F del roadmap.

---

## Sesión 2026-05-28 · Cierre estricto de F0 (auditoría)

### Resumen
Auditoría de la entrega F0 detectó **2 violaciones de gate** y **1 ⚠️ de compute** que la metodología obliga a cerrar antes de abrir F1. El agente preparó todo el código y la documentación; faltan **4 acciones humanas** en el PC para sellar el cierre.

> Si todo lo de abajo pasa ✅, F0 queda cerrado limpio y arrancamos F1.

### 1. ✅ Rotar contraseñas MySQL *(violación Regla de Oro #2)*

El `infra/create_users.sql.example` versionado tenía la contraseña real (`123450`). Aunque los 3 usuarios son `@localhost`, esto es deuda pública en GitHub. Pasos detallados en [infra/rotate_mysql_passwords.md](infra/rotate_mysql_passwords.md):

1. Generar 3 contraseñas de 24 caracteres con PowerShell (snippet en el doc).
2. Aplicar `SET PASSWORD FOR ... = PASSWORD('<nueva>')` para los 3 usuarios.
3. Actualizar `MYSQL_PASSWORD=` en los 3 `.env` locales.
4. Verificar: `pytest` en la API + `python infra/test_mysql_connectivity.py`.

**Reportar al agente:** "passwords rotados, todo verde" — sin compartir las contraseñas.

---

### 2. ✅ Crear el UC Volume de aterrizaje *(una vez)*

Pasos en [infra/setup_uc_volume.md](infra/setup_uc_volume.md). Desde el SQL Editor del workspace Databricks:

```sql
CREATE VOLUME IF NOT EXISTS motoshop.bronze._landing
  COMMENT 'Staging de Parquet subidos por dump_to_cloud.py (Track A · F1)';
```

**Reportar al agente:** confirmar que aparece en Catalog Explorer bajo `motoshop > bronze > _landing`.

---

### 3. ✅ Configurar SQL Warehouse con autoapagado 10 min *(verificación F0 #4)*

En el workspace:

1. **SQL → Warehouses → Create SQL Warehouse.**
2. Tamaño: el más pequeño disponible (en Free Edition, "Starter").
3. **Auto stop:** 10 minutos.
4. Permisos: el PAT actual debe poder ejecutarlo.

**Reportar al agente:** capturar el setting de auto-stop (screenshot o copy del valor). Eso cierra la verificación crítica #4.

---

### 4. ✅ Ejecutar el pipeline real Databricks ↔ MySQL *(verificación F0 #3)*

Esto es lo que de verdad sella la verificación #3 (la que el smoke test sintético no cumplía).

**En el PC Windows:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
python -m venv .venv-infra
.\.venv-infra\Scripts\Activate.ps1
pip install -r infra\requirements.txt

# Smoke test: 1 tabla, sin subir a Databricks
python infra\dump_to_cloud.py --tables sucursales --dry-run
# → genera _staging/sucursales/ingest_date=YYYY-MM-DD/part-0.parquet

# Smoke test completo: sube al UC Volume
python infra\dump_to_cloud.py --tables sucursales
# → sube al Volume + genera _staging/manifest_YYYY-MM-DD.json
```

**En Databricks (workspace UI):**

5. Importar `notebooks/bronze/01_ingest_smoke_test.py` (o ya está sincronizado si conectaste el repo en la tarea 5 de la sesión anterior).
6. Ejecutar el notebook con el SQL Warehouse pequeño o con serverless compute.
7. La última celda debe imprimir: `✅ Smoke test OK · verificación crítica #3 de F0 cumplida`.

**Reportar al agente:** copia del output de la celda 4 (los conteos coinciden) o screenshot del notebook completo. Esto cierra la verificación #3.

---

### 5. ⬜ (Opcional) Conectar el repo al workspace Databricks

Para que los notebooks se editen en Databricks UI y se versionen en GitHub:

1. **Workspace → User Settings → Linked accounts → GitHub.**
2. Conectar `javierportillar/motoshopData`.
3. **Repos → Add Repo → seleccionar el repo conectado.**
4. Trabajar los notebooks dentro de esa carpeta de `Repos/`.

No es bloqueante para cerrar F0 — se puede ejecutar el notebook importándolo manualmente — pero es lo "limpio".

---

### ✅ Fase 0 cerrada

Las 4 acciones se completaron en la sesión del 2026-05-28. Verificaciones #3, #4, #5 pasan a ✅. Fase 0 cerrada. Pasamos a Fase 1.

---

## Sesión 2026-05-27 · Decisiones P1–P4 aceptadas

### Resumen de esta sesión
- ✅ P1–P4 revisados y aceptados (recomendaciones confirmadas sin cambios)
- ✅ ADRs 0005–0008 actualizados a `Accepted`
- ✅ Script PowerShell `infra/backup_mysql.ps1` generado (alternativa Windows)
- ✅ SQL `infra/create_users.sql.example` generado con usuarios `analytics` y `api_read`
- ✅ Backup MySQL ejecutado (5.02MB, 7s)
- ✅ Usuarios MySQL creados: analytics, api_read, javier
- ➡️ Pendiente: cuenta Databricks, Cloudflare Tunnel, probar scaffolds

---

## Sesión 2026-05-27 · Cierre de andamiaje F0

### 1. ✅ Revisar y confirmar/ajustar P1–P4 *(bloquea F0 → F1)*

Los 4 ADRs fueron aceptados con las recomendaciones originales:
- P1 → **A** · Self-hosted dump → cloud storage
- P2 → **A** · Cloudflare Tunnel
- P3 → **A** · PC local
- P4 → **A** · Login propio (JWT + bcrypt)

---

### 2. ✅ Ejecutar el backup del MySQL *(verificación crítica #6 de F0)*

Desde PowerShell (como Administrador) en el PC donde corre `motoshop2024`:

```powershell
# Asegúrate de que mysqldump está en el PATH
# o ejecuta desde: C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\
cd C:\Users\MotoShop\Documents\javidevmoto
.\infra\backup_mysql.ps1 -BackupDir "$env:USERPROFILE\Backups\motoshop"
```

> Si `mysqldump` no está en el PATH, usa la ruta completa:
> ```powershell
> $env:PATH += ";C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin"
> .\infra\backup_mysql.ps1
> ```

**Reportar al agente:** tamaño y duración (los imprime el script al final).

---

### 3. ⬜ Probar que el scaffold corre *(opcional, valida los `⚠️` de F0)*

**API (FastAPI):**
```powershell
cd motoshop-app/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn motoshop_api.main:app --reload --port 8000
# abrir http://localhost:8000/health  →  {"status":"ok",...}
```

**Web (Next.js):**
```powershell
cd motoshop-app/web
npm install
copy .env.local.example .env.local
npm run dev
# abrir http://localhost:3000
```

**Reportar al agente:** si todo arranca, se marcan ✅ los dos entregables `⚠️` de F0. Si algo falla, pasar el error.

---

### 4. ✅ Crear usuarios MySQL read-only

Usuarios creados: `analytics`, `api_read`, `javier` (todos @localhost, password `123450`).
Verificación crítica #1 ✅ — INSERT command denied para los 3.

---

### 5. ⬜ Crear cuenta/workspace Databricks

- Crear cuenta en https://databricks.com (Free / Community tier para arrancar).
- Crear catálogo `motoshop` en Unity Catalog con esquemas `bronze`, `silver`, `gold`.
- Generar un Personal Access Token (PAT) y guardarlo en el password manager.
- Pasar al agente: **host** del workspace (URL) y confirmar que el PAT está disponible (sin enviarlo por chat).
- Después de esto, el agente podrá escribir el primer notebook bronze.

---

### 6. ⬜ Configurar el remoto GitHub para CI *(diferible)*

El repo ya está en [github.com/javierportillar/motoshopData](https://github.com/javierportillar/motoshopData). Cuando quieras meter CI:

- Decidir si se mantiene como repo público o se hace privado.
- Confirmar al agente para que escriba `.github/workflows/ci.yml` con ruff + pytest + (más adelante) lint del frontend y typecheck.

---

## Cómo se usa este archivo

- **Al inicio de cada sesión** el agente lo lee y prioriza según lo que esté ⬜.
- **Al cierre de cada sesión** el agente añade un nuevo bloque arriba con los pendientes nuevos generados y marca ✅ los que se resolvieron desde la sesión anterior.
- **Tú** marcas ✅ tú mismo cuando completes algo, o se lo dices al agente y él lo actualiza.
- **Histórico:** los bloques de sesiones pasadas no se borran. Sirven como rastro de qué se pidió y cuándo se cerró.
