# Plan F5 · Operación bidireccional — PWA escribe a sgHermes vía app_* InnoDB

- **Fecha apertura:** 2026-05-30 (Sesión 44)
- **Estado:** 🟡 ABIERTA
- **Modo:** paralelo · **2 devs (Dev A · Backend, Dev T · Frontend) + Revisor (yo · process docs + ADRs)**.
- **Duración estimada:** Dev A 3-4 h · Dev T 3-4 h · Revisor 1 h. Wall-clock ~4 h.
- **Dependencias previas:** F4-FIX1 ✅ cerrada. R14 (remover Prophet/LightGBM) y R15 (users.yaml) abiertos.

---

## 1 · Visión y por qué existe F5

Hasta F4 la PWA es **solo lectura**: consulta catálogo, stock, ventas, dashboards, predicciones y alertas. El operador no puede **actuar** desde la PWA — tiene que volver al PC con sgHermes para registrar acciones.

F5 abre el primer canal de **escritura controlada**:

- **PWA escribe a MySQL en tablas `app_*` (InnoDB)** — separadas de las tablas sgHermes (MyISAM).
- **sgHermes permanece intocable** (ADR-0002): cero modificaciones a sus tablas, su esquema, ni sus datos.
- **Una sola acción de negocio** en F5 para mantener scope acotado: **gestionar una alerta de quiebre** (`ordered` / `dismissed` / `postponed`).

Más adelante (F6/F7) se agregan más acciones (notas de venta, follow-ups, etc.). F5 prueba el patrón end-to-end con la acción más útil.

### Por qué "gestionar alerta" como primera acción

- Las 46 alertas de quiebre generadas en F4-FIX1 (`gold.alertas_quiebre`) son la salida más accionable del producto predictivo.
- Hoy el operador las ve en la PWA pero no puede marcarlas — vuelven a aparecer cada noche aunque ya las haya atendido.
- Cerrar el loop "alerta → acción → registro" es la primera funcionalidad que materializa el valor de los modelos ML.

---

## 2 · Scope mínimo viable

### Lo que SÍ entrega F5

- **1 acción de negocio:** gestionar alerta (3 opciones: `ordered` con cantidad y proveedor; `dismissed` con razón; `postponed` con fecha de revisión).
- **1 tabla nueva:** `app_alert_actions` en InnoDB.
- **1 tabla auxiliar:** `app_audit_log` para trazabilidad de TODAS las escrituras de F5+.
- **API write contract:** `POST /alerts/{alert_id}/action` con idempotency-key en header.
- **RBAC fino** por roles en JWT: `admin` y `gerente` pueden escribir; `vendedor` solo lee.
- **Offline queue** en PWA con `idb-keyval` + retry exponencial.
- **PWA UI:** botón "Gestionar" en lista de alertas + modal de captura + listado de "Mis acciones del día".
- **R14 cleanup:** archivar `infra/run_forecast_prophet.py` y `infra/run_forecast_lightgbm.py` con README explicativo. Baseline queda como único modelo de producción.
- **Migration scripts versionados** en `infra/migrations/` (sin ORM tool, solo SQL puro idempotente).
- **Tests:** unit (FakeRepo + dependency_overrides), integration (con DB real test), E2E Playwright (incluyendo offline simulation).
- **ADR-0018** stack F5 + **ADR-0019** estrategia de idempotencia y RBAC.

### Lo que NO entra en F5 (diferido)

- Escritura a tablas sgHermes (jamás según ADR-0002).
- Otras acciones (notas de venta, follow-ups clientes, ajustes inventario) → F6/F7.
- Workflow Databricks migrado (R4) → F6.
- Walk-forward validation, drift monitoring → F6.
- Forecasting por categoría/familia → F6+.
- Demo a gerencia (R8), demo 4G (R6), V3 workflow 7 corridas (R7) → F6 hardening.
- Cleanup R15 (`users.yaml` con FG28) → F6 (decisión humana ya tomada).

---

## 3 · Decisiones técnicas (DT-F5)

Estas decisiones van a ADR-0018 (stack F5) y ADR-0019 (idempotencia + RBAC).

### DT-F5-1 · Tablas `app_*` en InnoDB con AUTO_INCREMENT + idempotency_key UNIQUE

Schema `app_alert_actions`:

```sql
CREATE TABLE IF NOT EXISTS app_alert_actions (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  alert_id      VARCHAR(64) NOT NULL,
  sku           VARCHAR(64) NOT NULL,
  user_id       VARCHAR(64) NOT NULL,
  action_type   ENUM('ordered','dismissed','postponed') NOT NULL,
  quantity      DECIMAL(10,2) NULL,
  supplier      VARCHAR(255) NULL,
  reason        VARCHAR(500) NULL,
  postponed_to  DATE NULL,
  notes         TEXT NULL,
  idempotency_key VARCHAR(64) NOT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  request_id    VARCHAR(64) NOT NULL,
  UNIQUE KEY uq_idempotency (idempotency_key),
  INDEX idx_user_created (user_id, created_at),
  INDEX idx_alert (alert_id),
  INDEX idx_sku_created (sku, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

Schema `app_audit_log`:

```sql
CREATE TABLE IF NOT EXISTS app_audit_log (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id     VARCHAR(64) NOT NULL,
  user_role   VARCHAR(32) NOT NULL,
  action      VARCHAR(64) NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_id   VARCHAR(64) NOT NULL,
  request_id  VARCHAR(64) NOT NULL,
  ip_address  VARCHAR(45) NULL,
  user_agent  VARCHAR(500) NULL,
  payload     JSON NULL,
  status      ENUM('success','failure') NOT NULL,
  error_msg   VARCHAR(500) NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_created (user_id, created_at),
  INDEX idx_target (target_type, target_id),
  INDEX idx_action_created (action, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### DT-F5-2 · Write contract con idempotency-key header

`POST /alerts/{alert_id}/action`

Headers obligatorios:
- `Authorization: Bearer <JWT>` (JWT debe tener claim `role`)
- `Idempotency-Key: <UUID v4 generado por cliente>`
- `X-Request-Id: <UUID v4>` (opcional, generado por middleware si falta)

Body (JSON):

```json
{
  "action_type": "ordered" | "dismissed" | "postponed",
  "quantity": 50,                  // requerido si ordered
  "supplier": "ATMOPEL",           // opcional si ordered
  "reason": "ya hay pedido",       // requerido si dismissed
  "postponed_to": "2026-06-15",    // requerido si postponed
  "notes": "texto libre"           // opcional
}
```

Response 201:

```json
{
  "id": 123,
  "alert_id": "abc-123",
  "sku": "MOTS1297",
  "action_type": "ordered",
  "user_id": "admin",
  "created_at": "2026-05-30T15:30:00Z"
}
```

Response 409 (idempotency replay): retorna el registro original con status 200, NO error.

Response 403: role insuficiente.

Response 422: validación falla (e.g. `ordered` sin `quantity`).

### DT-F5-3 · RBAC fino por role claim en JWT

`users.yaml` ya tiene `role` por usuario (`admin`, `gerente`, `vendedor`). Al hacer login, el JWT incluye `role` en el payload.

Middleware FastAPI `require_role(*roles)`:

```python
def require_role(*allowed_roles: str):
    def checker(user: User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return checker

@router.post("/alerts/{alert_id}/action")
def gestionar_alerta(
    alert_id: str,
    body: AlertActionRequest,
    idempotency_key: str = Header(...),
    user: User = Depends(require_role("admin", "gerente")),
    repo: AlertActionsRepo = Depends(get_alert_actions_repo),
):
    ...
```

`vendedor` queda explícitamente excluido. Si vendedor llama, recibe 403.

### DT-F5-4 · Audit trail dual: structlog JSON + tabla `app_audit_log`

Cada escritura genera:

1. **structlog event** con todos los campos (user_id, role, action, target, request_id, ip, status). Va a stdout para Cloudflare logs.
2. **Insert en `app_audit_log`** con los mismos campos persistido en MySQL. Sobrevive a rotación de logs.

Middleware `AuditMiddleware` después de `RequestIDMiddleware` captura request/response y persiste si la ruta está en lista (`/alerts/*/action`, futuras rutas de escritura).

### DT-F5-5 · Offline queue en PWA con idb-keyval + retry exponencial

Cuando PWA pierde conexión y el operador marca una alerta:

1. La acción se persiste en IndexedDB store `pending-actions` con campos: `{ idempotency_key, alert_id, body, attempt, next_retry_at }`.
2. Background sync con `navigator.serviceWorker.sync` (cuando disponible) o fallback con `setInterval` cada 30 s reintenta.
3. Retry exponencial: 1s → 5s → 30s → 5min → 30min → 6h (máx 6 reintentos).
4. Si recibe 201/200 (idempotent replay): elimina del store, notifica UI.
5. Si recibe 4xx (no 408/429): elimina del store, notifica error.
6. Si recibe 5xx/408/429 o network error: reintenta.

UI muestra badge "X acciones pendientes de sincronizar" cuando hay items en queue.

### DT-F5-6 · Sin transacciones distribuidas

F5 solo escribe a `app_*` (InnoDB). NO toca tablas sgHermes (MyISAM, sin transacciones). El `commit` de InnoDB es local. No hay XA, no hay 2PC, no hay riesgo cross-engine.

### DT-F5-7 · Migration scripts SQL puros, idempotentes, versionados

`infra/migrations/F5-001-app_alert_actions.sql`  
`infra/migrations/F5-002-app_audit_log.sql`  
`infra/migrations/F5-003-grant_app_read_writer.sql` (nuevo usuario MySQL `app_writer` con INSERT/SELECT sobre `app_*` y SELECT sobre sgHermes).

Cada migration con:
- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS` (o `DROP INDEX` + `CREATE` si MySQL 5.0 no soporta IF NOT EXISTS — verificar)
- Rollback documentado en comentario al final

Sin Alembic ni ORM tool — el volumen es bajo y SQL puro es más auditable.

### DT-F5-8 · R14 cleanup como parte de F5

Dev A archiva en mismo sprint:
- `infra/run_forecast_prophet.py` → `docs/archive/infra/`
- `infra/run_forecast_lightgbm.py` → `docs/archive/infra/`
- `notebooks/gold/20_forecast_prophet.py` y `21_forecast_lightgbm.py` → `docs/archive/notebooks-gold/`

Tablas `gold.forecast_prophet_sku` y `gold.forecast_lightgbm_sku` se mantienen (audit trail) pero NO se actualizan más. Workflow `motoshop_gold_workflow` se ajusta para skip las tasks correspondientes.

Crear `docs/archive/infra/README.md` con explicación: "Modelos archivados por R14 (decisión 2026-05-30): WAPE 864% y 57% vs baseline 45.83% — inservibles para este dataset. Conservados como audit trail. Ver `docs/lecciones-aprendidas-f4.md`."

### DT-F5-9 · Tests honestos

- **Unit (FastAPI testclient + FakeRepo):** valida contrato request/response sin tocar DB.
- **Integration:** `pytest -m integration` con DB MySQL real (test DB separada, no `motoshop2024`). Cada test corre dentro de transacción y rollback al final.
- **E2E (Playwright):** flujo completo PWA → API → DB. Incluye:
  - Marcar alerta `ordered` con cantidad → ver en "Mis acciones del día".
  - Marcar alerta `dismissed` → ya no aparece en listado.
  - Simular offline (devtools): marcar → ver en cola → reconectar → ver sincronizado.
  - Login como `vendedor`: botón "Gestionar" no aparece (RBAC frontend).
  - Replay de idempotency-key: misma request 2 veces → segunda devuelve mismo ID sin duplicar.

### DT-F5-10 · UI minimalista, mobile-first

- Lista de alertas (ya existe): agregar botón "Gestionar" si user.role in admin/gerente.
- Modal de captura: 3 tabs (Pedir / Descartar / Posponer) + campos contextuales + botón submit + indicador offline.
- "Mis acciones del día": `GET /alerts/actions/me?date=today` lista las acciones del usuario actual.
- Sin tablas complicadas, sin charts, sin recharts (no se necesita).

---

## 4 · Sprints (3 sprints, 2 devs en paralelo + revisor async)

### Sprint F5-A · Dev A · Backend + Schema + R14 (~3-4 h)

#### Paso A1 · Migration scripts (~30 min)
- Crear `infra/migrations/F5-001-app_alert_actions.sql`
- Crear `infra/migrations/F5-002-app_audit_log.sql`
- Crear `infra/migrations/F5-003-grant_app_writer.sql` (usuario MySQL nuevo con INSERT/SELECT sobre app_*)
- Verificar compatibilidad MySQL 5.0 (sin features modernas tipo CHECK constraints, JSON column type — usar TEXT si JSON no funciona)
- Ejecutar manualmente en MySQL test DB y validar.
- **Entregable:** `infra/migrations/_runs/migration_f5_<ts>.md` con CREATE TABLE confirmado.

#### Paso A2 · Models + Repos (~45 min)
- `motoshop-app/api/src/motoshop_api/app_writes/models.py` (SQLAlchemy core tables matching schema)
- `motoshop-app/api/src/motoshop_api/app_writes/repo.py` con `AlertActionsRepo` (insert con idempotency) y `AuditLogRepo`
- `FakeAlertActionsRepo` para tests
- `FakeAuditLogRepo` para tests

#### Paso A3 · Endpoint + RBAC (~45 min)
- `motoshop-app/api/src/motoshop_api/app_writes/router.py` con `POST /alerts/{alert_id}/action`
- `motoshop-app/api/src/motoshop_api/auth/deps.py`: agregar `require_role(*roles)`
- Validación Pydantic con field-level (e.g. `quantity` requerido si `action_type == ordered`)
- Idempotency: try-except sobre UniqueViolation → retornar registro existente con 200 (no 201).

#### Paso A4 · Endpoint `GET /alerts/actions/me` (~30 min)
- Lista acciones del usuario logueado para un rango de fechas (default: today).
- Paginación simple (limit/offset).

#### Paso A5 · AuditMiddleware (~30 min)
- Captura todas las requests a `/alerts/*/action` + futuras rutas de escritura.
- Persiste a `app_audit_log` después de cada response.
- Logs estructurados con structlog para Cloudflare.

#### Paso A6 · R14 cleanup (~30 min)
- `git mv` Prophet/LightGBM scripts a `docs/archive/`
- Actualizar `infra/create_gold_workflow.py` para skip tasks de Prophet/LightGBM.
- Crear `docs/archive/infra/README.md` con explicación.
- Re-correr `motoshop_gold_workflow` para confirmar que skip funciona.

#### Paso A7 · Tests (~45 min)
- Unit: `tests/api/test_alert_actions.py` con 8+ casos:
  - Happy path admin
  - Happy path gerente
  - 403 vendedor
  - 422 validación (ordered sin quantity)
  - 422 validación (postponed sin postponed_to)
  - Idempotency replay (mismo idempotency-key 2 veces)
  - 401 sin JWT
  - JWT expirado
- Integration: `tests/integration/test_alert_actions_db.py` con DB real:
  - Inserción ok + audit log entry
  - Rollback en caso de error
- Confirma cobertura `pytest --cov`.

### Sprint F5-B · Dev T · Frontend + Offline queue (~3-4 h)

#### Paso B1 · Lista alertas con botón "Gestionar" (~30 min)
- Modificar `motoshop-app/web/app/(authenticated)/alerts/page.tsx`
- Botón "Gestionar" visible solo si `user.role in ['admin', 'gerente']` (RBAC frontend con role en JWT decoded en context).
- Modal trigger.

#### Paso B2 · Modal de captura (~45 min)
- `motoshop-app/web/components/AlertActionModal.tsx`
- 3 tabs: Pedir / Descartar / Posponer.
- Campos contextuales por tab (quantity+supplier / reason / postponed_to).
- Validación frontend (required + tipo de dato).
- Botón submit con loader.
- Indicador "Sin conexión — se guardará localmente" si `navigator.onLine == false`.

#### Paso B3 · Offline queue (~45 min)
- `motoshop-app/web/lib/offlineQueue.ts`:
  - `enqueueAction(action)` → guarda en idb-keyval store `pending-actions`.
  - `flushQueue()` → recorre items, intenta enviar, retry con backoff exponencial.
  - Subscribe a `online` event para flush automático al reconectar.
  - `setInterval` cada 30 s como fallback (background sync no garantizado en todos los browsers).
- Genera idempotency-key con `crypto.randomUUID()` antes de encolar.

#### Paso B4 · Badge UI offline (~30 min)
- `motoshop-app/web/components/OfflineQueueBadge.tsx` flotante en header.
- Muestra "X acciones pendientes" cuando store no está vacío.
- Color amarillo si hay queue, oculto si vacía.

#### Paso B5 · "Mis acciones del día" page (~45 min)
- `motoshop-app/web/app/(authenticated)/acciones/page.tsx`
- Lista paginada de las acciones del usuario logueado.
- Filtros simples: hoy / esta semana / este mes.
- Indicador visual por tipo de acción (verde ordered / gris dismissed / azul postponed).

#### Paso B6 · E2E Playwright (~45 min)
- `motoshop-app/web/tests/alert-action.spec.ts`:
  - admin marca alerta ordered → ve en lista.
  - admin marca alerta dismissed → desaparece de alertas activas.
  - vendedor no ve botón.
  - offline simulation: devtools network offline → marca alerta → ve en queue → online → ve sincronizada.
  - idempotency replay: doble submit no duplica.
- Capturar evidencia en `motoshop-app/web/_runs/v_f5_e2e_<ts>.md`.

### Sprint F5-C · Revisor + ambos devs · Cierre (~1 h)

#### Paso C1 · ADR-0018 stack F5 (~30 min)
- Crear `docs/decisions/0018-stack-f5.md` con DT-F5-1..10.
- Aprobar en bloque o con ajustes humanos.

#### Paso C2 · ADR-0019 idempotencia + RBAC (~15 min)
- Crear `docs/decisions/0019-idempotency-y-rbac.md`.
- Documentar patrón canónico para futuras rutas de escritura.

#### Paso C3 · Auditoría revisor (~15 min)
- Aplicar 9 checks de INICIAR_REVIEWER.md.
- Especial atención a Check 4 (seguridad: nuevo usuario MySQL `app_writer` sin password en código).
- Veredicto.

---

## 5 · V críticas (gates para cerrar F5)

| ID | Verificación | Pass criterion | Owner | Evidencia |
|----|--------------|---------------|-------|-----------|
| **V-F5-1** | Schema app_* creado y poblado | `SELECT COUNT(*) FROM app_alert_actions` ≥ 1 tras flujo E2E | Dev A | `infra/migrations/_runs/migration_f5_<ts>.md` |
| **V-F5-2** | Idempotency funciona | Test integration replay 2x mismo key → único registro en DB | Dev A | `tests/integration/test_alert_actions_db.py` output |
| **V-F5-3** | RBAC bloquea vendedor | Test unit POST con JWT `role=vendedor` → 403 | Dev A | `tests/api/test_alert_actions.py` |
| **V-F5-4** | Audit log persiste cada escritura | 1 entry en `app_audit_log` por cada POST exitoso | Dev A | `_runs/migration_f5_<ts>.md` con SELECT del audit |
| **V-F5-5** | Offline queue sincroniza al reconectar | E2E offline → online → DB tiene el registro | Dev T | `v_f5_e2e_<ts>.md` |
| **V-F5-6** | PWA muestra "Mis acciones del día" | UI lista las acciones del usuario logueado en orden cronológico | Dev T | screenshot en `v_f5_e2e_<ts>.md` |
| **V-F5-7** | R14 cleanup completo | `git log` muestra Prophet/LightGBM movidos a `docs/archive/`; workflow gold no falla | Dev A | output de `motoshop_gold_workflow` ejecutado post-cleanup |
| **V-F5-8** | ADR-0018 y ADR-0019 Accepted | Status en ambos = `Accepted` | Revisor | git log |
| **V-F5-9** | Tests pasan 100% | `pytest` + `npx playwright test` ambos verdes | Ambos | output combinado |

**Gate de cierre F5:** V-F5-1 a V-F5-9 TODAS PASS.

---

## 6 · Riesgos específicos de F5

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| **R-F5-1** | MySQL 5.0 no soporta features modernas (`JSON` column, `CHECK` constraints, `IF NOT EXISTS` en `CREATE INDEX`) | Dev A verifica en paso A1 y adapta — fallback: `TEXT` en lugar de `JSON`, validación en app en lugar de constraint, `DROP INDEX IF EXISTS` + `CREATE INDEX`. |
| **R-F5-2** | Coexistencia InnoDB + MyISAM en mismo database puede tener side effects | Verificar con `SHOW ENGINE INNODB STATUS` que no haya warnings. Si hay, separar a database `motoshop_app` distinto (rollback aceptable). |
| **R-F5-3** | Idempotency-key generado mal por cliente (no UUID v4) | Backend valida regex UUID v4 en Pydantic; rechaza con 422 si no cumple. |
| **R-F5-4** | Concurrent writes de 2 users en misma alerta | Aceptable — cada acción es de un usuario; las acciones se agregan, no se sobrescriben. Si negocio quiere "primera gana" lo agregamos en F6 con lock optimista. |
| **R-F5-5** | Offline queue se llena indefinidamente si API está caída | Cap de 100 items en queue; si excede, mostrar warning al usuario "Demasiadas acciones pendientes, sincronizá manualmente". |
| **R-F5-6** | Audit log crece rápido si hay muchas escrituras | Partition por mes en F6 hardening. F5 OK con tabla simple. |
| **R-F5-7** | Usuario MySQL nuevo `app_writer` con password leak | Generar password fuerte en `.env`, NO hardcodear. Documentar rotación en `infra/rotate_mysql_passwords.md`. |
| **R-F5-8** | R14 cleanup rompe workflow Databricks porque tabla `forecast_prophet_sku` se referencia en algún mart | Dev A revisa todos los marts antes de archivar; si hay referencia, dejar tabla en gold sin actualizarla (audit trail). |

---

## 7 · Prompts handoff (listos para pegar)

### 🤖 Dev A · Sprint F5-A · Backend + R14 (~3-4 h)

```
Soy Dev A · Track A · Sprint F5-A del proyecto MotoShop.
Trabajo en paralelo con Dev T (no nos coordinamos en código,
solo evitamos conflicto en SEGUIMIENTO.md y PENDIENTES.md).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A)
4. Leé docs/plan-f5.md COMPLETO
5. Leé motoshop-app/api/src/motoshop_api/auth/deps.py (entender patrón JWT actual)
6. Leé motoshop-app/api/src/motoshop_api/alerts/router.py (entender contrato actual)
7. Verificá versión MySQL: mysql --version (debería ser 5.0 según contexto)

MI MISIÓN:
Crear el primer canal de escritura PWA → MySQL con tablas app_* en InnoDB.
Acción única: gestionar alerta (ordered/dismissed/postponed). Implementar
endpoint POST /alerts/{alert_id}/action con idempotency + RBAC + audit log.
Adicionalmente: ejecutar R14 cleanup (archivar Prophet/LightGBM).

ENTREGABLES (en orden):
1. infra/migrations/F5-001-app_alert_actions.sql (InnoDB, idempotency_key UNIQUE)
2. infra/migrations/F5-002-app_audit_log.sql
3. infra/migrations/F5-003-grant_app_writer.sql (nuevo MySQL user)
4. infra/migrations/_runs/migration_f5_<ts>.md (evidencia ejecución)
5. motoshop-app/api/src/motoshop_api/app_writes/* (models, repo, router, schemas)
6. require_role(*roles) middleware en auth/deps.py
7. AuditMiddleware en logging.py o nuevo audit_middleware.py
8. Tests: tests/api/test_alert_actions.py (8+ casos) + tests/integration/
9. R14 cleanup: git mv infra/run_forecast_*.py + notebooks/gold/2{0,1}_* a docs/archive/
10. docs/archive/infra/README.md explicando R14
11. Re-correr motoshop_gold_workflow y confirmar skip de tasks Prophet/LightGBM

NO TOCO:
- motoshop-app/web/** (Dev T)
- notebooks/bronze|silver/** (estables)
- Tablas sgHermes (intocable, ADR-0002)
- users.yaml (deuda R15 diferida)

COORDINACIÓN CON DEV T:
- Cada uno actualiza SOLO su sección en SEGUIMIENTO.md / PENDIENTES.md
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: feat(F5-A-backend): ...

CIERRE:
Cuando V-F5-1..V-F5-4 + V-F5-7 + V-F5-9 (tests backend) pasen,
commit + push. Después escribo en SEGUIMIENTO.md una nota de cierre
honesta que el revisor master pueda auditar.

ARRANQUE:
Paso A1 (Migration scripts). Verificá compatibilidad MySQL 5.0
con DECIMAL, ENUM, JSON antes de tirar el schema. Adaptá si algo
no funciona.
```

### 🤖 Dev T · Sprint F5-B · Frontend + Offline queue (~3-4 h)

```
Soy Dev T · Track T · Sprint F5-B del proyecto MotoShop.
Trabajo en paralelo con Dev A (no nos coordinamos en código).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track T)
4. Leé docs/plan-f5.md COMPLETO (especial §3 DT-F5-5, DT-F5-10)
5. Leé motoshop-app/web/app/(authenticated)/alerts/page.tsx
6. Leé motoshop-app/web/lib/* (entender patrón actual)
7. Leé motoshop-app/web/components/StaleDataBanner.tsx (patrón de componente flotante)

MI MISIÓN:
Implementar UI para que admin/gerente puedan gestionar alertas desde PWA:
botón "Gestionar" en lista de alertas, modal con 3 tabs (Pedir/Descartar/
Posponer), offline queue con retry, badge de cola, página "Mis acciones
del día". RBAC: vendedor NO ve botón.

ENTREGABLES (en orden):
1. motoshop-app/web/components/AlertActionModal.tsx (3 tabs, validación)
2. motoshop-app/web/lib/offlineQueue.ts (idb-keyval + retry exponencial
   con cap 6 retries: 1s, 5s, 30s, 5min, 30min, 6h)
3. motoshop-app/web/components/OfflineQueueBadge.tsx (header flotante)
4. motoshop-app/web/app/(authenticated)/acciones/page.tsx (lista mi día)
5. Modificar alerts/page.tsx para mostrar botón "Gestionar" solo si
   user.role in ['admin', 'gerente']
6. motoshop-app/web/tests/alert-action.spec.ts (5+ casos E2E)
7. motoshop-app/web/_runs/v_f5_e2e_<ts>.md con screenshots + log

NO TOCO:
- motoshop-app/api/** (Dev A)
- infra/** (Dev A)
- notebooks/** (Dev A)

COORDINACIÓN CON DEV A:
- Cada uno actualiza SOLO su sección en SEGUIMIENTO.md / PENDIENTES.md
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: feat(F5-B-frontend): ...

DEPENDENCIA:
El endpoint POST /alerts/{id}/action lo crea Dev A en F5-A. Mientras
Dev A trabaja, vos podés:
1. Hacer la UI con un mock local (un fetch que devuelva 201 simulado)
2. Cuando Dev A pushee el endpoint, integrá contra él
3. Si Dev A demora, podés crear el endpoint con FakeRepo en
   motoshop-app/api/.../app_writes/router.py temporalmente y ajustar
   cuando Dev A push el final (coordinen por el chat humano)

CIERRE:
Cuando V-F5-5 + V-F5-6 + V-F5-9 (tests E2E) pasen, commit + push.
Después escribo en SEGUIMIENTO.md nota de cierre honesta.

ARRANQUE:
Paso B1 (botón Gestionar en alerts/page.tsx). Antes de tocar
offlineQueue, asegurate de que el modal funciona en happy path.
```

---

## 8 · Cronograma sugerido

| Tiempo | Dev A | Dev T | Revisor (yo) |
|--------|-------|-------|--------------|
| 0:00 | Paso A1 (migrations) | Paso B1 (botón) | ADR-0018 draft |
| 0:30 | Paso A1 cont. | Paso B2 (modal happy path) | ADR-0018 review |
| 1:00 | Paso A2 (models) | Paso B2 cont. | ADR-0019 draft |
| 1:30 | Paso A3 (endpoint) | Paso B3 (offline queue) | ADR-0019 review |
| 2:00 | Paso A4 (GET actions) | Paso B3 cont. | Standby |
| 2:30 | Paso A5 (audit middleware) | Paso B4 (badge) | Standby |
| 3:00 | Paso A6 (R14 cleanup) | Paso B5 (mis acciones) | Standby |
| 3:30 | Paso A7 (tests) | Paso B6 (E2E) | Standby |
| 4:00 | Push + write nota | Push + write nota | Audit 9 checks |
| 4:30 | — | — | Veredicto |

Total wall-clock: ~4.5 h con buen ritmo, ~6 h con interrupciones.

---

## 9 · Cierre + auditoría revisor

Una vez Dev A y Dev T cierren sus sprints:

1. Revisor (yo) corre los 9 checks de `INICIAR_REVIEWER.md` actualizado contra los entregables.
2. Verifica las 9 V-F5 con evidencia.
3. Especial atención a:
   - **Check 4 (Seguridad):** nuevo usuario `app_writer` con password en `.env` (no hardcoded). R15 NO se cierra acá (sigue diferida F6).
   - **Check 5 (Sniff test ML):** N/A en F5.
   - **Check 7 (Silver↔Bronze):** N/A en F5 (no toca silver).
   - **Check 9 (Real vs Fake):** verificar que `app_writes/router.py` use `RealAlertActionsRepo` cuando `env != 'test'`.
4. Si TODAS PASS → cierra F5 verde, actualiza header global, abre planificación F6.
5. Si alguna FAIL → F5-FIX1 con plan corto.

---

## 10 · Costo total estimado

| Rol | Tiempo | Notas |
|-----|--------|-------|
| Dev A | 3-4 h | Backend + schema + R14 + tests |
| Dev T | 3-4 h | UI + offline queue + tests E2E |
| Revisor (yo) | 1 h ADRs + 30 min audit | Async durante sprints + bloqueo final |
| **Total wall-clock** | **~4.5 h** (paralelo) | Si fuera secuencial: ~7-8 h |

Reducción ~40% vs secuencial gracias a paralelización con scope aislado por dev.

---

## 11 · Qué sigue después de F5

Cierre F5 verde → planificación F6 · Hardening + entrega académica:

- Cerrar R6 (demo 4G), R7 (workflow 7 corridas), R8 (demo gerencia), R15 (users.yaml cleanup).
- Workflow Databricks migrado (cierra R4).
- Monitoring + alerting + drift monitoring.
- Forecasting por categoría/familia (extender más allá de baseline).
- Demo final + memoria E5 completa.
- Entrega académica formal Maestría UAO 2025-2.
