# Plan detallado · Fase 1 · Ingesta + API de lectura

> Plan operativo de F1, derivado de PLAN.md §7 y SEGUIMIENTO.md. Sirve como sprint planning real. Cada entregable apunta a un archivo concreto, una verificación crítica F1 y una métrica medible. Se actualiza al cierre de cada sprint.
>
> **⚠️ 2026-05-28 (Sesión 14):** la implementación de los 3 sprints (F1-A/B/C) tuvo problemas detectados por auditoría. F1 sigue 🟡. Plan de remediación en [`docs/plan-f1-fix1.md`](plan-f1-fix1.md).

---

## Objetivo y hito

**Hito de F1:** *"Desde un celular fuera de la red local, hacer login y consultar stock de un SKU."* (PLAN.md §7).

**Objetivo Track A:** primer dato real de las 12 tablas core aterrizando en `motoshop.bronze.*` con ingesta idempotente diaria.

**Objetivo Track T:** API con auth JWT + 3 endpoints de lectura, con rate limiting, logs estructurados y OpenAPI.

---

## Decisiones técnicas

Resueltas en [ADR-0011 · Stack técnico F1](decisions/0011-stack-f1.md), **Accepted 2026-05-28**.

| # | Decisión | Recomendación | Estado |
|---|----------|----------------|--------|
| DT-1 | Acceso MySQL desde API | SQLAlchemy 2.0 core + pymysql | Accepted |
| DT-2 | JWT + bcrypt | pyjwt + bcrypt | Accepted |
| DT-3 | Rate limiting | slowapi in-memory | Accepted |
| DT-4 | Store usuarios F1 | users.yaml gitignored | Accepted |
| DT-5 | Paginación | offset+limit (50/200) | Accepted |
| DT-6 | Bronze idempotente | `INSERT REPLACE WHERE` | Accepted |
| DT-7 | Manifest del dump | Subir al Volume `/_manifests/` | Accepted |
| DT-8 | Logging | structlog JSON + PII redaction | Accepted |
| DT-9 | Tests API | Repos + `pytest.mark.integration` | Accepted |
| DT-10 | Timezone | Bronze raw → Silver UTC → API UTC `Z` | Accepted |

---

## Mapa de entregables → verificaciones críticas

Las 7 verificaciones críticas de F1 (ya en SEGUIMIENTO.md):

| # | Verificación | Cierra con… |
|---|--------------|--------------|
| V1 | ¿Conteos bronze == origen? | Notebook `03_validate_counts.sql` + evidencia `notebooks/bronze/_runs/full_run_<fecha>.md` (Sprint F1-A) |
| V2 | ¿La ingesta es idempotente? | Test: kill a mitad del dump, re-correr, mismos conteos. Documentado en `notebooks/bronze/_runs/idempotency_test_<fecha>.md` (Sprint F1-A) |
| V3 | ¿La API rechaza tokens vencidos? | Test `test_auth_expired_token` (Sprint F1-B) |
| V4 | ¿La API rechaza credenciales malas sin filtrar? | Test `test_auth_wrong_password_returns_401_without_user_enumeration` (Sprint F1-B) |
| V5 | ¿Los logs no exponen datos sensibles? | Test `test_logs_redact_pii_and_secrets` + revisión manual de muestras (Sprint F1-B) |
| V6 | ¿Paginación funciona en tablas grandes? | Notebook `04_check_large_tables.sql` con `detfventas` (~27k) y `detcompras` (~11k) (Sprint F1-A) |
| V7 | ¿El esquema bronze es estable entre corridas? | Notebook `05_schema_drift.sql` que compara `DESCRIBE TABLE` entre 2 ingest_dates (Sprint F1-A) |

---

## Sprint F1-A · Bronze de las 12 tablas core

**Duración estimada:** 1 sesión (~2-3 h de agente + 1 sesión de validación humana).

**Pre-requisitos**
- F0 ✅ (smoke test cerrado).
- ADR-0011 aceptado (DT-6, DT-7 obligatorios para este sprint).
- `_landing` y SQL Warehouse operativos.

**Archivos a crear**

| Path | Rol |
|------|-----|
| `infra/dump_to_cloud.py` | (modificar) añadir subida del manifest al Volume tras todas las tablas |
| `notebooks/bronze/02_ingest_all_bronze.sql` | Patrón canónico de ingesta (DT-6): `CREATE TABLE IF NOT EXISTS` + `INSERT REPLACE WHERE`. Itera por las 12 tablas vía widgets o ejecución manual celda por celda. |
| `notebooks/bronze/03_validate_counts.sql` | Lee `_manifests/manifest_<date>.json` con `json.\`...\`` y compara contra `COUNT(*) FROM motoshop.bronze.<tabla> WHERE ingest_date = '<date>'`. Falla si mismatch. |
| `notebooks/bronze/04_check_large_tables.sql` | `detfventas` (~27k) y `detcompras` (~11k): conteo + estadísticas (min/max `fecdoc`, # filas por mes). Cumple V6. |
| `notebooks/bronze/05_schema_drift.sql` | Compara esquemas entre 2 ingest_dates con `DESCRIBE TABLE`. Cumple V7. |
| `notebooks/bronze/_schema/<tabla>.md` × 12 | Documentación auto-generada del esquema bronze por tabla (snapshot de `DESCRIBE TABLE EXTENDED`). |
| `notebooks/bronze/_runs/full_run_<fecha>.md` | Evidencia: 12 tablas, conteos, duración, cuadre. Producido por el humano tras correr el Workflow. |
| `notebooks/bronze/_runs/idempotency_test_<fecha>.md` | Evidencia: kill-y-retry. Producido por el humano. |
| `infra/run_dump.ps1` | Wrapper PowerShell para Windows Task Scheduler. Llama `dump_to_cloud.py --tables-core`. |
| `infra/databricks_workflow.json` | Definición del Workflow (job) con la secuencia 02 → 03 → 04 → 05. Reproducible vía SDK. |
| `infra/create_databricks_workflow.py` | Script idempotente que crea/verifica el Workflow desde el JSON anterior. |

**Tareas en orden**

1. Agente actualiza `dump_to_cloud.py`: tras la última tabla, sube `manifest_<date>.json` al Volume en `/_manifests/`.
2. Agente escribe `02_ingest_all_bronze.sql` y verifica con `bodegas` que el patrón `INSERT REPLACE WHERE` corre.
3. Agente escribe `03_validate_counts.sql` y prueba contra el run del 2026-05-28.
4. Humano ejecuta `python infra/dump_to_cloud.py --tables-core` desde el PC.
5. Humano corre `02_ingest_all_bronze.sql` para las 12 tablas (manualmente o vía Workflow).
6. Humano corre `03_validate_counts.sql` — debe devolver "OK" para las 12.
7. Humano corre el dump dos días seguidos para tener 2 particiones; corre `05_schema_drift.sql` (V7).
8. Humano simula falla a mitad del dump (`Ctrl+C` tras la 6ª tabla); re-corre; valida que conteos finales cuadran (V2).
9. Humano captura evidencia en `notebooks/bronze/_runs/full_run_<fecha>.md` y `_runs/idempotency_test_<fecha>.md`.
10. Agente escribe `04_check_large_tables.sql` para V6, humano lo corre.
11. Agente escribe `infra/databricks_workflow.json` + `create_databricks_workflow.py`, humano lo crea desde la UI o vía script.
12. Agente actualiza SEGUIMIENTO F1 con los checks V1, V2, V6, V7 a ✅.

**Definition of Done · Sprint F1-A**
- 12 tablas core en `motoshop.bronze.<tabla>`, particionadas por `ingest_date`.
- Manifest del último run accesible en `/Volumes/motoshop/bronze/_manifests/`.
- `03_validate_counts.sql` devuelve "OK" para las 12.
- Workflow ejecutable manualmente desde la UI; programación nocturna queda diferida hasta tener 5 corridas manuales exitosas (V1 KPI).
- Evidencia versionada en `notebooks/bronze/_runs/`.
- V1, V2, V6, V7 marcados ✅ en SEGUIMIENTO.

**Métricas a capturar**
- Tiempo total de la ingesta (objetivo: <30 min — KPI F1).
- Tamaño total Parquet local y en Volume.
- Conteo por tabla (origen vs bronze) — debe coincidir para todas.

**Riesgos específicos**
- **R-A1 · `detcompras` (~11k) y `detfventas` (~27k) son lo más grande.** Si `pyarrow` agota memoria o `databricks-sdk` rechaza el upload, hay que chunkear. Plan: si pasa, paginamos en `dump_to_cloud.py` por chunks de 5k filas con archivos `part-0.parquet`, `part-1.parquet`, …
- **R-A2 · MyISAM y datetimes pre-1970 o NULL.** Algunas tablas históricas pueden tener `fecdoc = '0000-00-00'`. `mysql-connector-python` con `use_pure=True` los devuelve como `None`; pyarrow los guarda como `null`. Documentar en `notebooks/bronze/_schema/`.
- **R-A3 · `productos.codprod` puede tener trailing whitespace.** Frecuente en sgHermes. Bronze guarda como vino; silver hará `TRIM`.

---

## Sprint F1-B · Auth JWT + primer endpoint `/products`

**Duración estimada:** 1 sesión (~2-3 h agente + 30 min validación humana).

**Pre-requisitos**
- F1-A completado (al menos `motoshop.bronze.productos` existe, aunque la API lee directo de MySQL).
- ADR-0011 aceptado.

**Archivos a crear/modificar**

| Path | Rol |
|------|-----|
| `motoshop-app/api/pyproject.toml` | Añadir deps: sqlalchemy, pymysql, pyjwt, bcrypt, slowapi, pyyaml, structlog |
| `motoshop-app/api/src/motoshop_api/config.py` | Añadir `jwt_secret`, `users_file_path`; validador para JWT_SECRET no vacío en `env=prod` |
| `motoshop-app/api/src/motoshop_api/db/__init__.py` | export `get_engine`, `get_session` |
| `motoshop-app/api/src/motoshop_api/db/engine.py` | factory `create_engine` con `pool_pre_ping=True`, charset=`utf8` |
| `motoshop-app/api/src/motoshop_api/db/tables.py` | Tablas SQLAlchemy core reflejadas o declaradas: `productos`, `auxinventario`, `bodegas`, `facventas`, `detfventas`, `terceros` |
| `motoshop-app/api/src/motoshop_api/auth/__init__.py` | exports |
| `motoshop-app/api/src/motoshop_api/auth/hash.py` | `hash_password()`, `verify_password()` con bcrypt |
| `motoshop-app/api/src/motoshop_api/auth/jwt.py` | `create_access_token()`, `create_refresh_token()`, `decode_token()` con pyjwt HS256 |
| `motoshop-app/api/src/motoshop_api/auth/users.py` | `load_users(path)` que parsea `users.yaml`; `get_user_by_username()` |
| `motoshop-app/api/src/motoshop_api/auth/deps.py` | dependencia FastAPI `get_current_user`; `require_role(role)` |
| `motoshop-app/api/src/motoshop_api/auth/router.py` | `POST /auth/login`, `POST /auth/refresh` |
| `motoshop-app/api/src/motoshop_api/auth/schemas.py` | `LoginRequest`, `TokenPair`, `UserOut` |
| `motoshop-app/api/src/motoshop_api/logging.py` | structlog config + middleware request_id + PII processor |
| `motoshop-app/api/src/motoshop_api/products/__init__.py` | — |
| `motoshop-app/api/src/motoshop_api/products/repo.py` | `ProductsRepo` (SQLAlchemy core); `FakeProductsRepo` para tests |
| `motoshop-app/api/src/motoshop_api/products/router.py` | `GET /products?q=` con paginación |
| `motoshop-app/api/src/motoshop_api/products/schemas.py` | `ProductOut`, `ProductPage` |
| `motoshop-app/api/src/motoshop_api/main.py` | Wire-up: middleware, routers, rate limit, lifespan que carga users.yaml |
| `motoshop-app/api/users.yaml.example` | Plantilla con 3 usuarios y hashes de ejemplo (placeholders) |
| `motoshop-app/api/.env.example` | Añadir `JWT_SECRET`, `USERS_FILE_PATH` |
| `motoshop-app/api/.gitignore` | Excepción para `users.yaml` (sí gitignored) + `!users.yaml.example` |
| `infra/hash_password.py` | CLI utility: `python infra/hash_password.py 'plaintext'` → imprime bcrypt hash |
| `motoshop-app/api/tests/conftest.py` | fixtures: `client`, `engine_test` (SQLite in-memory), `fake_users` |
| `motoshop-app/api/tests/test_auth_login.py` | login OK + login con password mala (V4) + token expirado (V3) + rate limit |
| `motoshop-app/api/tests/test_auth_logging.py` | V5: log con campo `password` debe aparecer `[REDACTED]` |
| `motoshop-app/api/tests/test_products.py` | GET /products con / sin auth, paginación, rol |
| `motoshop-app/api/tests/integration/test_products_real_mysql.py` | `@pytest.mark.integration` |

**Tareas en orden**

1. Actualizar `pyproject.toml` con las 7 deps nuevas; `pip install -e ".[dev]"` desde el venv.
2. Escribir `db/engine.py` + `db/tables.py`.
3. Escribir `auth/{hash,jwt,users,schemas,deps,router}.py`.
4. Escribir `infra/hash_password.py` y generar 3 hashes para `users.yaml.example`.
5. Escribir `logging.py` con middleware request_id y PII processor.
6. Escribir `products/{repo,schemas,router}.py`.
7. Wire-up `main.py` con lifespan que carga usuarios.
8. Tests unitarios; correr `pytest -m "not integration"` verde.
9. Humano crea su `users.yaml` real con `infra/hash_password.py`.
10. Humano hace `POST /auth/login` desde curl/Postman → recibe JWT → `GET /products?q=aceite` → 200.
11. Humano captura evidencia en `notebooks/api/_runs/sprint_f1b_demo.md` (curl outputs).
12. Agente marca V3, V4, V5 a ✅.

**Definition of Done · Sprint F1-B**
- `pytest -m "not integration"` verde con cobertura > 70% en `auth/` y `products/`.
- `POST /auth/login` con credenciales correctas devuelve `{access_token, refresh_token, expires_in}`.
- Login fallido devuelve 401 sin distinguir "usuario no existe" vs "password mala" (V4).
- Token vencido devuelve 401 con detalle `token_expired` (V3).
- `GET /products?q=aceite` con JWT válido devuelve `{items: [...], total, limit, offset}`.
- Logs muestran `request_id`, redactan `password` y `authorization` (V5).
- Rate limit 60 req/min por usuario, 10/min en `/auth/login` por IP.
- Documentación OpenAPI en `/docs` muestra los endpoints con auth scheme `bearerAuth`.

**Métricas a capturar**
- Latencia `/products?q=` con MySQL real (objetivo p95 < 500ms).
- Tiempo de hash bcrypt (no debería ser >150ms con cost 12).

**Riesgos específicos**
- **R-B1 · MyISAM no soporta connection pooling con transacciones.** `pool_pre_ping=True` y `connect_args={"autocommit": True}` para evitar locks. Sin `BEGIN/COMMIT` para queries de lectura.
- **R-B2 · `productos.codprod` con whitespace** se pasa al `q` y a la respuesta. Hacer `TRIM()` en la query.
- **R-B3 · JWT_SECRET débil.** Validador en `config.py`: en `env=prod` rechaza secrets < 32 chars o vacíos.

---

## Sprint F1-C · `/products/{sku}/stock`, `/sales/recent`, cierre F1

**Duración estimada:** 1 sesión.

**Pre-requisitos**
- F1-B completado.

**Archivos a crear/modificar**

| Path | Rol |
|------|-----|
| `motoshop-app/api/src/motoshop_api/stock/{repo,router,schemas}.py` | `GET /products/{sku}/stock` |
| `motoshop-app/api/src/motoshop_api/sales/{repo,router,schemas}.py` | `GET /sales/recent?since=&limit=` |
| Tests para ambos | Unit + integration |
| `notebooks/api/_runs/sprint_f1c_demo.md` | Evidencia: curl desde celular en 4G |

**Endpoints**

- `GET /products/{sku}/stock` → `{sku, total: N, by_bodega: [{codbod, nombod, cantidad}]}` (lee `auxinventario` ⨝ `bodegas`).
- `GET /sales/recent?since=2026-05-01T00:00:00Z&limit=50` → últimas N facturas activas con cabecera + total. Lee `facventas` con `estdoc='A'`, ordenadas por `fecdoc DESC`.

**Definition of Done · Sprint F1-C**
- Los 3 endpoints listados en PLAN.md §7 funcionando con auth y rate limit.
- Tests verdes.
- Hito F1 demo: vendedor abre la PWA desde 4G, login, busca SKU, ve stock.
- Métricas F1 medidas y registradas en SEGUIMIENTO §KPIs:
  - Tiempo ingesta diaria total.
  - Latencia `/products/{sku}/stock` p95.
  - Tasa de éxito ingesta (5 corridas seguidas).

**Gate de cierre de F1**
- Las 7 verificaciones críticas (V1-V7) en ✅ con evidencia versionada.
- KPIs medidos.
- Si alguna ⚠️ o 🔴: F1 no cierra, se replanifica.

---

## Riesgos cross-sprint

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R-X1 | Workflow Databricks Free Edition limita las horas serverless mensuales | Programar manualmente las primeras corridas; sólo activar schedule cuando el patrón sea estable |
| R-X2 | `auxinventario` (26k filas, sin índice por `codprod`) hace `/stock` lento | Si p95 > 500ms, considerar caché en memoria con TTL 5 min o un índice de aplicación |
| R-X3 | `users.yaml` se pierde al reinstalar el PC | Incluir en backups del PC; documentar en runbook |
| R-X4 | Cloudflare Tunnel cae | Documentar reinicio en runbook; alerta UptimeRobot (diferible a F6) |

---

## KPIs F1 y cómo se miden

| KPI | Meta | Medición | Cuándo |
|-----|------|----------|--------|
| Tiempo ingesta diaria | < 30 min | `manifest.duration_seconds` | Cada corrida |
| Latencia `/products/{sku}/stock` p95 | < 500 ms | structlog escribe `duration_ms` por request; agregamos con `jq` sobre el log del día | Sprint F1-C |
| Tasa éxito ingesta | 100% en 5 corridas | Contar manifests `error=null` en `/_manifests/` | Cierre F1 |
| Cobertura tests `auth/` y `products/` | > 70% | `pytest --cov` | Cierre F1-B |

---

## Backout plan

| Si pasa esto… | … hacemos esto |
|---------------|-----------------|
| El Workflow nocturno falla 3 corridas seguidas | Volver al disparo manual; investigar; documentar como R-X1 activado |
| El API resulta lenta (>1s p95) en `/stock` | Caché en memoria + revisar query plan; última opción, índice en `auxinventario` (requiere humano + ALTER cuidadoso) |
| Auth filtra info de usuario en `/auth/login` | Hotfix patch a 401 genérico; test que reproduce el filtrado |
| Un commit filtra JWT_SECRET o un `users.yaml` real | Rotación de secret + revoke de tokens emitidos; aprender de la lección F0 #5 |

---

## Calendario sugerido

| Día | Actividad |
|-----|-----------|
| D+0 | Humano revisa y aprueba ADR-0011. |
| D+1 | Agente ejecuta Sprint F1-A (parte código); humano corre el primer dump completo. |
| D+2 | Humano completa V1, V2, V6, V7 y captura evidencia. |
| D+3 | Agente ejecuta Sprint F1-B; humano crea `users.yaml` real y prueba login. |
| D+4 | Humano valida V3, V4, V5. |
| D+5 | Agente ejecuta Sprint F1-C. |
| D+6 | Humano corre demo desde celular en 4G; captura evidencia. |
| D+7 | Gate de cierre F1 → KPIs medidos → SEGUIMIENTO actualizado. |

---

## Cómo se actualiza este plan

- Al cierre de cada sprint, marcar tareas como hechas + añadir métricas reales (no estimadas) en la tabla de KPIs.
- Si una decisión técnica cambia, actualizar [ADR-0011](decisions/0011-stack-f1.md) (o crear ADR-0012, etc.) y referenciarlo aquí.
- Si un riesgo se materializa, moverlo del cuadro de Riesgos cross-sprint a SEGUIMIENTO §Tablero de riesgos vivos.
