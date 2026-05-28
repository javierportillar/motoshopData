# ADR-0011 · Stack técnico de Fase 1 (DT-1 a DT-10)

- **Estado:** **Proposed** — bloquea inicio de Sprint F1-A
- **Fecha:** 2026-05-28
- **Bloquea:** F1 (los 3 sprints)
- **Decide:** Humano (responsable del proyecto)

## Contexto

Antes de tocar código de F1 hay 10 micro-decisiones técnicas que afectan estructura, dependencias y velocidad. Resolverlas en bloque evita parar a debatir cada hora y deja la arquitectura consistente entre los sprints F1-A (Bronze de las 12 tablas) y F1-B/F1-C (API + auth + endpoints).

Cada decisión tiene una recomendación; el humano confirma o ajusta antes del primer commit de F1.

---

## DT-1 · Acceso a MySQL desde la API (Track T)

**Contexto:** la API lee desde `motoshop2024` (MyISAM, sin FKs declarativas) con el usuario `api_read`. En F5 escribirá a tablas `app_*` InnoDB. Necesitamos un cliente que sirva ambos modos sin reescribir.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `mysql-connector-python` directo | Mínimo overhead; lo usa `dump_to_cloud.py` | Sin pool de conexiones de fábrica; queries como strings; no aprovecha tipado |
| B · **SQLAlchemy 2.0 core** + `pymysql` | Pool de conexiones nativo; query builder tipado pero sin ORM; compatible con raw SQL puntual; el lenguaje estándar del ecosistema Python | Una dependencia más; curva de aprendizaje pequeña |
| C · SQLAlchemy 2.0 ORM completo | Mapeo objeto-relacional; útil si hubiera FKs | Sobreingeniería sobre MyISAM sin FKs; las consultas terminan siendo `select()` igual; gestión de sesiones añade fricción |

**Recomendación: B · SQLAlchemy 2.0 core con driver `pymysql`.**

**Consecuencias:** dependencia `sqlalchemy>=2.0,<3`, `pymysql>=1.1`. Carpeta `motoshop-app/api/src/motoshop_api/db/` con `engine.py` (factory con pool) y `tables.py` (definiciones Core reflejadas o declaradas). Tests pueden montar un engine SQLite en memoria para unit tests; integración hace hit al MySQL local.

---

## DT-2 · Librería JWT y bcrypt

**Contexto:** D9 (ADR-0008) confirmó "JWT + bcrypt". Falta elegir librerías concretas.

**Opciones**

| | JWT | Hash |
|---|-----|------|
| A · `python-jose` | Soporte amplio de algoritmos | Mantenimiento sporadic; depende de `cryptography` |
| B · **`pyjwt`** + **`bcrypt`** | Focused; bien mantenido; ligero | bcrypt directo (sin passlib) requiere usar la API binaria |
| C · `authlib` | Suite OAuth/OIDC completa | Overkill para login propio |

**Recomendación: B · `pyjwt>=2.8` + `bcrypt>=4.1`.**

**Consecuencias:** módulo `motoshop_api/auth/hash.py` con `hash_password()` / `verify_password()`; `motoshop_api/auth/jwt.py` con `create_access_token()` / `create_refresh_token()` / `decode_token()`. Algoritmo `HS256` con secret en `.env`. TTL: access 15 min, refresh 7 días (ya en `.env.example`).

---

## DT-3 · Rate limiting

**Contexto:** verificación crítica F1 implica rate limiting. La API corre en una sola instancia (PC). Aún no hay Redis ni se justifica añadirlo en F1.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · **`slowapi`** (in-memory) | Cero infra adicional; integración directa con FastAPI | Si en F-F la API escala horizontal hay que migrar |
| B · `fastapi-limiter` (Redis) | Distribuible | Requiere Redis ya en F1 |
| C · custom in-memory | Sin deps | Reinventar la rueda |

**Recomendación: A · `slowapi>=0.1.9` con backend in-memory.**

**Consecuencias:** límite global por usuario autenticado: **60 req/min**; por IP no autenticada en `/auth/login`: **10 req/min**. Decorador `@limiter.limit(...)` en los routers. Si en F-F migramos a varias instancias, swap a `fastapi-limiter` (decisión separada).

---

## DT-4 · Store de usuarios en F1

**Contexto:** F1 necesita 2-3 usuarios (admin, vendedor, gerente) para probar auth. F5 traerá `app_usuarios` en InnoDB. No queremos meter una tabla MySQL "provisional" que después haya que migrar.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · **`users.yaml` gitignored** (+ `users.yaml.example`) | Inspeccionable, simple, sin DB; estructura mapea 1:1 a `app_usuarios` futuro | Cambios requieren reiniciar API; no escala más allá de ~50 usuarios |
| B · Variables `.env` | Sin archivo extra | Imposible con >2 usuarios sin volverlo ilegible |
| C · SQLite local | Mismo modelo que MySQL | Sobreingeniería para 3 usuarios; otra DB que respaldar |
| D · Esperar a F5 | "Limpio" | F1 entera bloqueada |

**Recomendación: A · `users.yaml` gitignored con `users.yaml.example` versionado.**

**Esquema propuesto:**

```yaml
users:
  - username: admin
    hashed_password: "$2b$12$..."   # bcrypt
    email: admin@motoshop.local
    role: admin
  - username: vendedor1
    hashed_password: "$2b$12$..."
    email: ...
    role: vendedor
```

**Consecuencias:** módulo `motoshop_api/auth/users.py` con carga al startup (`@app.on_event("startup")` o lifespan). Script `infra/hash_password.py` para generar hashes sin tener que importar la lib en interactivo. Cuando llegue F5, migración trivial: leer `users.yaml` y `INSERT INTO app_usuarios`.

---

## DT-5 · Paginación de endpoints

**Contexto:** `productos` tiene ~6.2k filas, `auxinventario` ~26k, `facventas` ~6.3k. Volúmenes moderados.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · **offset + limit** | Trivial; suficiente para los volúmenes actuales | Degrada con N grande (cursor de DB salta filas); cambios concurrentes pueden duplicar/omitir |
| B · keyset (cursor) | No degrada; estable bajo cambios | Más código; UX del cliente más compleja |

**Recomendación: A · offset + limit en F1.**

**Consecuencias:** parámetros estándar `?limit=N&offset=M` con `limit` por defecto 50, máximo 200. Respuesta envuelve con `{items: [...], total: N, limit: 50, offset: 0}`. Documentar en `docs/plan-f1.md` que la migración a cursor entra cuando `productos` o `auxinventario` superen 100k filas o cuando un endpoint p95 > 1s.

---

## DT-6 · Patrón de escritura idempotente en Bronze

**Contexto:** el smoke test usó `CREATE OR REPLACE TABLE`, que sobreescribe la tabla completa cada vez. En producción esto **pierde particiones previas** — y nuestro modelo es "ingest diario, partición por `ingest_date`". Necesitamos un patrón que:
- Sea idempotente por día (re-correr el job del día N produce el mismo resultado).
- Preserve particiones anteriores.
- Funcione en SQL Warehouse (Free Edition, sin PySpark).

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `CREATE OR REPLACE TABLE` | Lo más simple | Pierde particiones anteriores. NO sirve para producción. |
| B · **`INSERT INTO ... REPLACE WHERE ingest_date = '...'`** (Delta SQL) | Idempotente por partición; preserva el historial; soportado en SQL Warehouse | Requiere `CREATE TABLE IF NOT EXISTS` la primera vez |
| C · `MERGE INTO ... USING ... ON` | Idempotente fila a fila | Más complejo; sobrecosto cuando la partición entera puede reemplazarse de bloque |

**Recomendación: B · `INSERT … REPLACE WHERE`.**

**Patrón canónico (notebook SQL):**

```sql
-- Primera ejecución (idempotente por nombre):
CREATE TABLE IF NOT EXISTS motoshop.bronze.<tabla>
USING DELTA
PARTITIONED BY (ingest_date)
AS SELECT *, CAST(NULL AS STRING) AS ingest_date
   FROM parquet.`/Volumes/motoshop/bronze/_landing/<tabla>/ingest_date=$ingest_date/`
   WHERE 1=0;

-- Inserción idempotente de la partición del día:
INSERT INTO motoshop.bronze.<tabla>
REPLACE WHERE ingest_date = '$ingest_date'
SELECT *, '$ingest_date' AS ingest_date
FROM parquet.`/Volumes/motoshop/bronze/_landing/<tabla>/ingest_date=$ingest_date/`;
```

**Consecuencias:** `01_ingest_smoke_test.sql` se mantiene como smoke (con `CREATE OR REPLACE` aceptado por simplicidad), pero el notebook de producción `02_ingest_all_bronze.sql` usa el patrón B.

---

## DT-7 · Manifest del dump y su consumo

**Contexto:** `dump_to_cloud.py` ya escribe `_staging/manifest_<ingest_date>.json` con `{ingest_date, duration_seconds, tables: [{table, rows, columns, local_file, remote_path, error?}]}`. Falta:
1. Estandarizar el contrato.
2. Subirlo también al UC Volume para que el notebook de validación lo lea.
3. Definir cómo el notebook de validación lo consume.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Solo local (status quo) | Cero cambios | El notebook de validación no puede leer expectativas |
| B · **Subir también al Volume** en `/_manifests/manifest_<date>.json` | El notebook de validación puede ser SQL puro leyendo el JSON | Requiere lectura JSON en Spark/SQL Warehouse |
| C · Insertar manifest en una tabla Delta `bronze._meta_runs` | SQL puro fácil | El script local tendría que escribir Delta (complicado sin Spark local) |

**Recomendación: B · subir el manifest al Volume.**

**Consecuencias:**
- `dump_to_cloud.py` añade un paso final: `w.files.upload(f"{DATABRICKS_VOLUME_PATH}/_manifests/manifest_{ingest_date}.json", contents=manifest_bytes)`.
- Notebook `03_validate_counts.sql` lee `json.\`/Volumes/.../manifest_<date>.json\`` y compara `manifest.tables[*].rows` contra `COUNT(*) FROM motoshop.bronze.<tabla> WHERE ingest_date = '<date>'`. Si hay mismatch, falla.

---

## DT-8 · Logging estructurado en la API

**Contexto:** verificación crítica F1 #5: *"¿Los logs no exponen datos sensibles?"* Necesitamos JSON con `request_id`, sin contraseñas/tokens/PII.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · `structlog` | Contexto bind-able (request_id en middleware); procesadores componibles; JSON nativo; filtros de PII fáciles | Una dep más; API ligeramente distinta de la stdlib |
| B · `loguru` | API muy ergonómica | Menos JSON-first; mocking en tests es incómodo |
| C · stdlib `logging` con JSONFormatter custom | Sin deps extra | Sin contexto bind por request; reinventar PII filter |

**Recomendación: A · `structlog>=24`.**

**Consecuencias:**
- Middleware `request_id_middleware` genera UUID por request y lo bindea al logger.
- Processor de PII redacta automáticamente keys `password`, `hashed_password`, `token`, `authorization`, `nitter`, `email`, `telefono`.
- Output: JSON a stdout (lo recoge `journalctl` o similar en el PC).
- Tests verifican que un log con `password=...` se redacta a `[REDACTED]`.

---

## DT-9 · Tests de la API

**Contexto:** queremos tests rápidos (unit) y tests que prueben la integración con MySQL (integration). CI no tiene MySQL.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Solo unit con mocks | Rápido; CI feliz | No prueba la query real |
| B · Solo integration | Real | Lento; CI necesita MySQL |
| C · **Híbrido con repositorios y `pytest.mark.integration`** | Rápido en CI; cobertura real en local | Más estructura inicial |

**Recomendación: C · híbrido.**

**Consecuencias:**
- Cada feature de lectura se accede vía un **repositorio** (`ProductsRepo`, `StockRepo`, `SalesRepo`) que toma `engine` por DI.
- Unit tests usan `FakeProductsRepo` con datos en memoria.
- Integration tests llevan `@pytest.mark.integration` y leen `motoshop2024` real (saltados en CI mediante `pytest -m "not integration"`).
- CI corre solo unit + lint + typecheck. Local corre todo.

---

## DT-10 · Timezone para `fecdoc` y `/sales/recent`

**Contexto:** sgHermes guarda `fecdoc` como `DATETIME` sin info de TZ. El negocio está en `America/Bogota` (UTC-5). Los clientes de la PWA pueden estar en otras TZ.

**Opciones**

| | Pros | Contras |
|---|------|---------|
| A · Bronze como string, silver UTC, API UTC | Trazabilidad clara; cliente convierte a local | Cliente tiene que saber la TZ del origen |
| B · Bronze como string, silver America/Bogota, API America/Bogota | Cliente recibe hora local del negocio | Frágil ante cambios de TZ futuros (multi-país) |
| C · Todo en TZ del origen sin convertir | Cero conversiones | Cliente cree que es UTC y se equivoca |

**Recomendación: A · bronze raw, silver UTC, API UTC.**

**Consecuencias:**
- Bronze: columnas datetime almacenadas como string (ya lo hace `dump_to_cloud.py`).
- Silver (F2): casteo `CAST(fecdoc AS TIMESTAMP)` interpretando como `America/Bogota` y convertir a UTC.
- API: devuelve ISO 8601 con sufijo `Z` (UTC) en todos los `datetime`.
- Frontend (F2): `Intl.DateTimeFormat` con TZ local del navegador.
- `/sales/recent?since=` acepta ISO 8601 UTC.

---

## Resumen ejecutivo · todas las DT en una tabla

| # | Decisión | Recomendación | Dependencias añadidas |
|---|----------|----------------|------------------------|
| DT-1 | Acceso MySQL desde API | SQLAlchemy 2.0 core + pymysql | `sqlalchemy>=2.0`, `pymysql>=1.1` |
| DT-2 | JWT + bcrypt | pyjwt + bcrypt | `pyjwt>=2.8`, `bcrypt>=4.1` |
| DT-3 | Rate limiting | slowapi in-memory | `slowapi>=0.1.9` |
| DT-4 | Store de usuarios F1 | users.yaml gitignored | `pyyaml>=6` |
| DT-5 | Paginación | offset+limit (50/200) | — |
| DT-6 | Bronze idempotente | `INSERT REPLACE WHERE` | — |
| DT-7 | Manifest | Subir a Volume `/_manifests/` | — |
| DT-8 | Logging | structlog JSON con PII redaction | `structlog>=24` |
| DT-9 | Tests API | Repos + `pytest.mark.integration` | `pytest-asyncio`, `aiosqlite` (unit) |
| DT-10 | Timezone | Bronze raw → Silver UTC → API UTC `Z` | — |

## Aceptación

Cuando el humano confirme este ADR (o pida cambios), el agente:
- Cambia el estado a `Accepted` y le pone fecha.
- Añade D11 a la bitácora de SEGUIMIENTO.
- Procede con Sprint F1-A.
