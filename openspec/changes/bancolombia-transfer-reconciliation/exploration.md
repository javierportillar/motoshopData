# Exploration: bancolombia-transfer-reconciliation

> sdd-explore artifact · 2026-10-21 · RESEARCH ONLY — no proposal/spec written here.
> Artifact language: español (code identifiers in English).

## Resumen ejecutivo (7 hallazgos con evidencia)

1. **Ya existe un write-path de recibo S01 completo y reutilizable tal cual.**
   `erp/cash/repo.py:166-273` (`_CashDocumentRepo._save`) implementa la secuencia φ0..φ4
   (idempotency replay → journal PENDING → numeración `contadores` → filas legacy → journal
   COMMITTED + snapshot). `RealReceiptsRepo` (`repo.py:509-543`) es instanciable desde
   `get_receipts_repo()`. La conciliación **debe postear receipts con este repo**, no inventar un
   segundo camino de escritura.
2. **El cruce banco→factura NO tiene columna directa.** `facventas` (`schema_2024.sql:2060-2139`)
   no tiene columna de referencia. La referencia Bancolombia viaja como texto libre en
   `detapago.numpag` (`schema_2024.sql:1240`, varchar(20)), escrita por
   `erp/invoicing/repo.py:586` desde `InvoicePaymentIn.referencia`, que el POS alimenta en
   `erp/pos/router.py:190-197`. El match real es una **búsqueda** sobre `detapago`, no un JOIN por
   clave natural.
3. **Inconsistencia real de cuenta cartera (bloqueante para conciliar).**
   `erp/cash/repo.py:59` define `CARTERA_CUENTA = "1305"`, pero la causación de facturación escribe
   la cartera en `13050501` (`erp/invoicing/repo.py:79`) y `detcuentas.codcue` se compara con
   igualdad exacta (`erp/cash/store.py:248-260`). `open_balance()` con su default **no ve** las
   filas de cartera reales → en producción el saldo disponible sería 0. Los tests herméticos
   siembran `"1305"` (`tests/test_erp_receipts.py:67`, `tests/test_erp_cash_router.py:96`), por eso
   el slice 4 pasa en verde. **La conciliación no debe reusar `open_balance()` con su default.**
4. **Bug latente en el path que se va a reusar:** `erp/cash/repo.py:434` escribe
   `"numpag": body.referencia or ""` **sin recortar**, pero `ReceiptCreate.referencia` admite 40
   chars (`erp/cash/schemas.py:49`) y la columna legacy es `varchar(20)` con
   `STRICT_TRANS_TABLES` → error MySQL 1406 → `ErpSaveFailed` 503. La ruta de invoicing sí recorta
   (`erp/invoicing/repo.py:586`, `[:20]`). Debe corregirse antes de reutilizar.
5. **Playwright NO es viable en Render free.** `motoshop-app/api/render.yaml` (`plan: free`,
   `region: oregon`, `pip install -e .`) no declara variables MySQL — los endpoints MySQL degradan
   a 503 en cloud — y el disco es efímero. El scraper debe correr en la caja **on-premise Windows**
   (`infra/start_api.ps1`, rutas `C:/Users/MotoShop/...` en `config.py:18-22`) o en el portátil del
   operador, que es donde está MySQL y donde puede vivir el `user_data_dir`.
6. **La custodia de la master key NO puede ser sólo macOS Keychain.** La API productiva corre en
   **Windows**, no en macOS. El diseño de la bóveda necesita **dos backends de custodia**
   (Keychain en macOS / DPAPI-Credential Manager en Windows) + `passphrase` como default.
7. **Ya existe una segunda ruta de aterrizaje reutilizable:** `POST /api/erp/bank/consignations`
   (`erp/cash/router.py:294-330`) escribe `consbancab` para dinero que **no** se aplica a una
   factura. Es el destino natural de una transferencia sin match: no se inventa caja, se usa la
   consignación bancaria que el legacy ya modela (`_BaseConsignmentRepo`, `repo.py:1130+`).

---

## Current State

### Backend — el módulo ERP transaccional que se va a extender

`motoshop-app/api/src/motoshop_api/erp/cash/` — 4 archivos que forman el patrón canónico del repo:

| Archivo | Líneas | Rol |
|---|---|---|
| `schemas.py` | 140 | Pydantic `extra="forbid"`, `LegacyText`, `ErpMoney` (`erp/common/`) |
| `store.py` | 370 | Acceso a filas legacy: `CashStore` Protocol + `FakeCashStore` + `RealCashStore` (SQLAlchemy `text()`, whitelist `WRITABLE_TABLES`) |
| `repo.py` | 1332 | Repos de guardado: `_CashDocumentRepo._save` (φ0..φ4) + `Fake*Repo`/`Real*Repo` + `get_*_repo()` |
| `router.py` | 330 | Endpoints FastAPI: `_validate_idempotency_key` (UUID v4), `_save_or_http_error` (422/409/503), `_log_audit` |

Endpoints vivos (`erp/cash/router.py`): `POST /api/erp/receipts` (S01), `/cash/movements` (S03),
`/cash/egresos` (S02), `/cash/arqueo` (S38), `/bank/consignations` (`consbancab`).
Montaje: `main.py:288` → `app.include_router(erp_cash_router, prefix="/api", dependencies=module_access)`.

**Guards** (`erp/guards.py`):
- `ERP_ROUTE_MODULES` (líneas 53-74) es la matriz `(method, path) -> módulos`. Una ruta nueva sin
  entrada ⇒ **HTTP 500** "La ruta no tiene una política de módulos configurada"
  (`auth/module_access.py:348-363`). No es un deny: es un error de configuración.
- `require_erp_tenant` (línea 300): sólo tenants con `erp.enabled=true` (`tenants.yaml` → `motoshop`,
  `masvital` ambos `enabled: true`, `empresa: E01`).
- `require_erp_collections_write` (línea 285): **admin/gerente** (vendedor read-only). Una matriz de
  módulos puede ampliar el *población* de usuarios, nunca el *rol*.

**Contrato de errores del write-path** (`erp/cash/router.py:131-143`): `LegacyValidationError` → 422
agregado (`fields` + `message`); `AnnulledDocumentError`/`PeriodLockedError` → 409 con `code`;
`InactiveMasterError` → 422 frozen; `ErpSaveFailed` → 503 retryable.

**Validación del recibo S01** (`erp/cash/repo.py:348-405`): `valor > 0`; `tipclas ∈ PAYMENT_TIPCLAS`
(`S01,S02,S03,S14,S21,S26`); la factura existe; `estfven != 'A'` (409); `assert_period_open`
(`Hay_Cie_Eli`, 409); `open_balance > 0`; `valor <= available` (si no → `ReceiptOverpaymentError` 422
con `saldo_disponible` en el detail). **Causalización** (`repo.py:409-487`): fila `detapago`
(`soldeb`/`solcre` según `payment_duality`) + crédito en cartera sobre `numnum = numfven` + débito en
la cuenta de la forma de pago (`formapago.codcue`), validados con `assert_causacion_balanced`.

### Esquema legacy relevante (`docs/hermes/evidence/schema_2024.sql`)

| Tabla | Línea | Columnas clave para conciliar |
|---|---|---|
| `facventas` | 2060 | `numfven`, `prefven`, `codclas`, `fecfven`, `nitter` (cliente), `clifven` (nombre), `totfven`, `estfven`, `codpag`, `numcru`/`clascru`, `docext`. **Sin columna de referencia.** |
| `detapago` | 1230 | `numnum`, `codclas`, `predoc`, `numite`, `valpag`, `valefe`, `despag`, **`numpag` (ref, varchar 20)**, `numapr`, `soldeb`/`solcre`, `codpag`, `afepag`, `codban`, `tipcmen`, **`nitter` (pagador)**, `fecdoc`, `estado` |
| `detcuentas` | 1377 | `numnum`, `codclas`, `prenum`, `codcue`, `detcue`, `valdeb`/`valhab`, `fecdoc`, `nitter`, `estcue`, `numite`, **`concili`** (flag heredado "conciliado"), `numcru`, `docext` |
| `consbancab` | 932 | `numcon`, `precon`, `feccon`, `codcue`, `codpag`, `detcon`, `totcon`, `estcon`, `tipret` (`DEPOSITO`), `codemp` |
| `consbandet` | 957 | `numcon`, `codcue`, `detcue`, `valdet`, `tipcaj`, `codpag`, **`nitter`** (pagador) |
| `formapago` | 2200 | `codpag`, `forpag`, `afepag`, `tippag`, `codcaj`, `codban`, `codcue`, `numcon` (contador propio de consignación) |

Cuentas reales (`docs/hermes/evidence/masvital_live_schema_2026-10.md:133-136`):
`F03`/`F04`/`F07` → `11100501` (bancos); `F10` → `13050501` (cartera).

### Frontend (`../frontfambus`)

- `lib/pos/bancolombia.ts` (71 líneas) — parseo regex del texto del movimiento:
  `parseBancolombiaQRText()` → `{customerName, reference, amount, rawMatched}` y
  `sanitizeBancolombiaReference()` (quita `" null"`). Tests en `lib/pos/bancolombia.test.ts`.
  Hoy es **copiador manual** en `components/pos/PaymentModal.tsx:218-256` ("Asistente QR").
  `lib/pos/types.ts:166` ya declara `qrUrl`.
- **No existe ninguna página ERP de caja/CxC en el front.** `app/(authenticated)/` contiene
  `maestros/`, `pos/`, `dian/`, `admin/`, `dashboards/`, etc.; `components/erp/` sólo tiene
  maestros (`TercerosList.tsx`, `TercerosForm.tsx`, `ProductosList.tsx`, `ProductoForm.tsx`).
- Cliente ERP: `lib/erp/client.ts` (`apiFetch`, `X-Request-Id`, `Idempotency-Key` UUID v4,
  `toErpApiError`). Utilidades: `lib/erp/{errors,fieldErrors,idempotency,validation}.ts`.
- Permisos/nav FE: `components/ui/Navigation.tsx:661-689` (`gerenteNavItems()` / `vendedorNavItems()`),
  `lib/auth/access.ts` (`PATH_RULES` + `canAccessPath`), `lib/tenant/access.ts` (rutas tenant-only),
  `motoshop-app/api/tenants.yaml` → `enabled_features` por tenant.
- E2E: `playwright.config.ts` (`testDir: ./tests`), patrón live en `tests/clientes-live.spec.ts:13`
  → `test.skip(!process.env.E2E_LIVE, ...)`.

### Pipeline / infraestructura / despliegue

- **DuckDB silver/gold** (`pipeline/silver.py`, `pipeline/gold.py`, `notebooks/silver|gold/*.py`) se
  **reconstruye** en cada corrida: MySQL → bronze → silver → gold → `out/{tenant}_gold.duckdb` →
  R2 → API. `pipeline/run_all.py` (modo `mysql`). **No es un store transaccional** y no debe recibir
  movimientos que alimenten un receipt.
- **Migraciones**: sin Alembic. SQL numerados en `infra/migrations/` aplicados por
  `infra/migrations/run_migrations.py` (prefijo por defecto `F8`, estado en `app_migration_state`,
  checksum anti-drift). Plantillas: `F8-001-app_doc_journal.sql`, `F8-002-app_idempotency.sql`,
  `F5-002-app_audit_log.sql`, `F8-004-grant_app_writer_erp.sql`.
- Tablas `app_*`: `motoshop-app/api/src/motoshop_api/erp/models.py:278-317` (`app_doc_journal`,
  `app_idempotency`) y `app_writes/models.py` (`app_audit_log`, `app_alert_actions`).
- **Despliegue**: Render free (`render.yaml`) sin MySQL; API real on-premise Windows + Cloudflare
  Tunnel (`infra/start_api.ps1`, `infra/start_tunnel.ps1`).
- **Schedulers existentes**: GitHub Actions cron (`.github/workflows/briefing-daily.yml`,
  `0 11 * * *`), Databricks jobs (`infra/create_full_workflow.py:237-243`, quartz `0 0 19 * * ?`),
  Task Scheduler de Windows (`infra/MotoShop_AutoPull.xml`). **No hay scheduler dentro del proceso
  FastAPI.**

### Dependencias

- `motoshop-app/api/pyproject.toml`: `requires-python >=3.11`, deps runtime fijas, y un único
  `[project.optional-dependencies] dev` (ruff, pytest, pytest-cov, aiosqlite). **Sin `playwright`,
  sin `cryptography` declarada** (aparece sólo como transitiva en `uv.lock:452`).
- `openspec/config.yaml` → regla explícita: *"Never modify sgHermes data, **add dependencies
  without an ADR**, or version credentials."* ⇒ `cryptography` + `playwright` exigen ADR nuevo
  (`docs/decisions/` → siguiente número libre ≈ `0026`).

---

## Affected Areas

### Backend — archivos NUEVOS

| Archivo | Responsabilidad |
|---|---|
| `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/__init__.py` | Doc del módulo (patrón `erp/cash/__init__.py`) |
| `.../erp/bankreconciliation/schemas.py` | `BankMovementIn/Out`, `ReconciliationMatch`, `ReconcileRequest` (Pydantic `extra="forbid"`) |
| `.../erp/bankreconciliation/store.py` | `BankStore` Protocol + `FakeBankStore` + `RealBankStore` (tabla `app_bank_movements`) + **lecturas** de `facventas`/`detapago`/`detcuentas` para candidatos |
| `.../erp/bankreconciliation/repo.py` | Ingesta idempotente de movimientos + posting del S01 vía `erp.cash.repo` + escritura de la conciliación |
| `.../erp/bankreconciliation/router.py` | `GET /api/erp/bank/movements`, `GET /api/erp/bank/reconciliation`, `POST /api/erp/bank/reconciliation/{id}/apply`, `POST /api/erp/bank/sync` (dispara el scrape) |
| `.../erp/bankreconciliation/matching.py` | **Función pura** de matching (sin I/O) — la parte testeable sin DB ni red |
| `.../erp/bankreconciliation/vault.py` | Bóveda: PBKDF2-HMAC-SHA256 (600k) → Fernet; ciphertext `~/.config/motoshop/credentials.enc` (600); backends de custodia `keychain` / `passphrase` |
| `.../erp/bankreconciliation/scraper.py` | Cliente Playwright (Python) + parseo puro de filas |
| `motoshop-app/api/src/motoshop_api/erp/models.py` | `app_bank_movements` (SQLAlchemy Core, junto a `app_doc_journal`) |
| `infra/migrations/F9-001-app_bank_movements.sql` | DDL InnoDB `app_*` + `UNIQUE(id_externo)` + grant al `app_writer` |
| `motoshop-app/api/scripts/bank_vault.py` (o `scripts/bank_vault.py` en la raíz) | CLI `set` / `show` / `clear` con `getpass` (argparse, como el resto de `scripts/`) |
| `motoshop-app/api/tests/test_erp_bank_vault.py` | Round-trip offline de la bóveda |
| `motoshop-app/api/tests/test_erp_bank_matching.py` | Matching como función pura |
| `motoshop-app/api/tests/test_erp_bank_scraper_parse.py` | Parseo contra fixtures guardados |
| `motoshop-app/api/tests/test_erp_bank_router.py` | Router + guardas + matriz de módulos |
| `docs/decisions/00XX-banco-vault-scraping.md` | ADR (deps nuevas + decisión legal ToS + custodia) |

### Backend — archivos a MODIFICAR

| Archivo | Cambio |
|---|---|
| `motoshop-app/api/src/motoshop_api/erp/guards.py` | Entradas nuevas en `ERP_ROUTE_MODULES` (p.ej. `("POST","/api/erp/bank/reconciliation/{id}/apply"): ("erp-cash",)`) — **sin esto la ruta da 500** |
| `motoshop-app/api/src/motoshop_api/main.py` | `app.include_router(erp_bank_router, prefix="/api", dependencies=module_access)` |
| `motoshop-app/api/src/motoshop_api/erp/cash/repo.py` | (a) recortar `numpag` a 20 chars (bug 1406); (b) parametrizar/corregir `CARTERA_CUENTA` (`"1305"` → `"13050501"`, idealmente por tenant) |
| `motoshop-app/api/src/motoshop_api/erp/cash/store.py` | Nuevo método **de lectura** `find_payments_by_reference()` / `open_invoices()` (no tocar `WRITABLE_TABLES`) |
| `motoshop-app/api/src/motoshop_api/erp/cash/schemas.py` | (opcional) `codpag` default = forma de pago "transferencia banco" real, no `"01"` |
| `motoshop-app/api/pyproject.toml` | `cryptography>=43`, `playwright>=1.47` (runtime o grupo nuevo `bank`); `uv.lock` |
| `motoshop-app/api/tenants.yaml` | `enabled_features: bank-reconciliation` (para el gate de nav FE) |

### Frontend (`../frontfambus`)

| Archivo | Cambio |
|---|---|
| `frontfambus/app/(authenticated)/banco/transferencias/page.tsx` | Página nueva (server component, metadata, como `maestros/terceros/page.tsx`) |
| `frontfambus/components/erp/TransferenciasBancarias.tsx` | Lista de movimientos + estado de conciliación + acción "Aplicar" (idempotency key) |
| `frontfambus/lib/erp/bank.ts` | Cliente nuevo (o extender `lib/erp/client.ts`) — `GET movements`, `POST apply` |
| `frontfambus/components/ui/Navigation.tsx` | Item en `gerenteNavItems()` |
| `frontfambus/lib/auth/access.ts` | Regla en `PATH_RULES` (feature `bank-reconciliation` o `adminOnly`) |
| `frontfambus/lib/pos/bancolombia.ts` + `.test.ts` | Reutilizar/extraer `sanitizeBancolombiaReference` como normalizador compartido de referencias |
| `frontfambus/tests/banco-live.spec.ts` | E2E live guardado (`test.skip(!process.env.E2E_LIVE)`) |

---

## Approaches

### Eje 1 — Estrategia de scraping

| # | Enfoque | Pros | Cons | Esfuerzo |
|---|---|---|---|---|
| **A** | **Playwright + interceptación XHR/JSON** del endpoint de movimientos | Payload estructurado y tipado; inmune a cambios de CSS; permite lotear y deduplicar por clave externa; reutiliza la sesión del mismo contexto | El endpoint interno no está documentado y **no se pudo verificar** (ver "No verificado"); puede cambiar sin aviso; el JSON puede venir cifrado/ofuscado; Akamai puede seguir bloqueando | Medio |
| **B** | **Playwright + scraping DOM** | No depende de endpoints internos; la pantalla es la superficie que el banco garantiza; el texto se parsea con la misma lógica de `parseBancolombiaQRText` | Frágil ante cambios de UI/selectores; normalización de fecha (dd/mm/aaaa) y monto ($ 45.000); paginación; más propenso a flakiness; Akamai | Medio |
| **C** | **Login manual one-time + reutilización de sesión/cookies** (`launch_persistent_context` con `user_data_dir`) | **Cero credenciales almacenadas** → cero vault, cero exposición de contraseña, menor riesgo legal (ToS); 2FA resuelta una vez por un humano; máxima compatibilidad con el banco; el `user_data_dir` ya autenticado | La sesión expira → re-login manual (fricción); el `user_data_dir` **es** una credencial (cookies) → hay que protegerlo igual; no automatizable en desatendido; requiere presencia humana | Bajo-Medio |

**Recomendación: C → A con fallback a B.**
Fase 1 (MVP): **C** — el operador abre el portal una vez en un perfil persistente y el scraper sólo
navega y extrae. Esto elimina de raíz el problema de credenciales y el riesgo de ToS/login
automatizado, y es la opción más rápida a producción.
Fase 2 (opcional): **A** (interceptación XHR) con fallback **B** (DOM) sobre el mismo perfil, sólo si
el banco caduca la sesión con frecuencia o si se necesita correr desatendido. El parser se escribe
**siempre** como función pura (parseo de filas) para que A y B compartan el resto del pipeline.

### Eje 2 — Custodia de la master key de la bóveda

| # | Custodia | Pros | Cons | ¿Desatendido? |
|---|---|---|---|---|
| **K1** | **Keychain macOS** vía CLI `security` (sin dependencia nueva) | Clave nunca en disco en texto plano; `security` ya viene en macOS; desbloqueo por ACL de la app | **Sólo macOS** — la API productiva corre en **Windows**; el llavero desbloquea en el login del usuario (sesión graphical) | Sí (macOS) |
| **K2** | **Passphrase en runtime** (PBKDF2-HMAC-SHA256, 600k iter) | Sin custodia fuera del proceso; el archivo de la bóveda es la única fuente de secreto; portable Windows/Linux; el plaintext sólo existe en la memoria del proceso | Requiere TTY → **no sirve para cron desatendido**; el usuario debe estar presente | No |
| **K3** | **Key file con permisos 600** | Simple, desatendido | junto al ciphertext ⇒ **el cifrado no aporta nada** contra un atacante local con permisos de lectura; sin hardware binding | Sí (pero inseguro) |

**Recomendación: interfaz de custodia con dos backends — `passphrase` (default) + `keychain` — y
`keyfile` explícitamente PROHIBIDO.**
En macOS: `keychain` (`security add-generic-password -a motoshop -s bancolombia -w <key> -U`) con
`passphrase` como fallback. En Windows (la caja real): equivalente vía **DPAPI** (`CryptProtectData`,
`ctypes`/`win32crypt`) o **Credential Manager** — el mismo puerto, otro backend.
El ciphertext va a `~/.config/motoshop/credentials.enc` con modo **600** y directorio **700**;
`getpass.getpass()` (sin eco) para la passphrase y para el password del banco. El prompt **lo ejecuta
el usuario** (`python -m motoshop_api.erp.bankreconciliation.vault set`), nunca el agente → el
plaintext no pasa por el contexto del chat.

### Eje 3 — Dónde persistir los movimientos scrapeados

| # | Ubicación | Pros | Cons |
|---|---|---|---|
| **P1** | **Tabla ERP `app_bank_movements` en MySQL** (InnoDB, prefijo `app_*`, migración `infra/migrations/`) | Mismo motor y mismo usuario `app_writer` que el resto del write-path; transaccional con el S01 que postea; `UNIQUE(id_externo)` da idempotencia de ingesta; consultable por la API sin depender de R2/DuckDB; patrón ya establecido (ADR-0004: "app_* … sgHermes ni se entera") | Requiere migración MySQL + grant; la BD real sólo existe on-premise |
| **P2** | DuckDB silver/gold (`silver_fact_...`) | Reutiliza el pipeline analítico existente; gratis para dashboards | Se **reconstruye** en cada corrida → no es fuente de verdad transaccional; la API cloud no tiene MySQL pero tampoco el fichero; exige mapping bronze → silver y otra capa R2 |
| **P3** | Tabla legacy `consbancab` | Ya existe, es el modelo del legacy | Es MyISAM, sinConstraints ni idempotencia, y su numerador es un contador de `formapago` → colisiona con el flujo de consignaciones manual; perdemos la trazabilidad del movimiento crudo |

**Recomendación: P1** (`app_bank_movements`), con P2 sólo como proyección analítica posterior
(opcional, fuera de alcance).

---

## Recomendación

### 1. Módulo nuevo hermano: `erp/bankreconciliation/` (NO extender `erp/cash`)

`erp/cash` es el write-path de *documentos de caja* (φ0..φ4 + numeración). La conciliación es otro
capability: ingesta de una fuente externa, matching, y **propuesta/aplicación** de un documento
existente. Meterlo en `erp/cash` mezclaría "documento" con "origen externo" y ensuciaría el
write-path que ya está verificado. Regla: el módulo nuevo **consume** `erp/cash` (repo, store,
guards, schemas), nunca lo modifica en su lógica; las correcciones al path reusado (clip de
`numpag`, cuenta cartera) son cambios pequeños y explícitos al slice 4.

### 2. Persistencia: `app_bank_movements` (P1)

DDL en `infra/migrations/F9-001-app_bank_movements.sql`, tabla Core en `erp/models.py`:

```
id BIGINT PK AUTO_INCREMENT
tenant VARCHAR(32)          -- aislamiento multi-tenant (obligatorio)
empresa VARCHAR(15)         -- del tenant.erp.empresa (server-side)
id_externo VARCHAR(64)      -- hash/clave del banco (UNIQUE con tenant) → idempotencia de ingesta
fecha_movimiento DATE
valor DECIMAL(18,2)
referencia VARCHAR(40)      -- texto del banco (sin normalizar: se guarda el crudo)
referencia_norm VARCHAR(40) -- normalizada (dígitos, sin 'null' ni ceros a la izquierda)
pagador_nombre VARCHAR(120)
pagador_nit VARCHAR(15)
cuenta_destino VARCHAR(32)
estado VARCHAR(16)          -- PENDIENTE | APLICADO | AMBIGUA | SIN_MATCH | SOBREPAGO | IGNORADO
recibo_numero INT NULL      -- S01 generado (o consbancab.numcon)
recibo_pref VARCHAR(8) NULL
idempotency_key VARCHAR(64) -- clave con la que se posteó (traza φ0)
confianza INT NULL          -- score del matching (0-100)
razones JSON/TEXT NULL      -- por qué se matcheó (explicabilidad en UI)
scraped_at TIMESTAMP
created_at TIMESTAMP
UNIQUE KEY uq_tenant_ext (tenant, id_externo)
INDEX idx_estado_fecha (tenant, estado, fecha_movimiento)
```

### 3. Matching: función pura en `matching.py`, reglas deterministas y explicables

**Generación de candidatos** (SQL sobre `facventas`/`detcuentas`/`detapago`, cuenta cartera
`13050501` — *no* el default `"1305"`):

```sql
SELECT f.numfven, f.prefven, f.nitter, f.clifven, f.fecfven,
       SUM(d.valdeb - d.valhab) AS saldo
FROM facventas f
JOIN detcuentas d ON d.numnum = f.numfven AND d.codcue = :cartera AND d.estcue <> 'A'
LEFT JOIN detapago p ON p.numnum = f.numfven AND p.predoc = f.prefven
WHERE f.estfven <> 'A' AND f.codemp = :empresa AND d.fecdoc >= :desde
GROUP BY f.numfven, f.prefven, f.nitter, f.clifven, f.fecfven
HAVING SUM(d.valdeb - d.valhab) > 0
```
(`HAVING saldo > 0` = factura abierta; el filtro `prenum` se agrega después porque
`open_balance` filtra sólo por `numnum` → riesgo de colisión entre prefijos.)

**Reglas, en orden** (cada una suma score y deja una razón textual):

| Regla | Señal | Score | Condición |
|---|---|---|---|
| R1 Referencia exacta | `detapago.numpag` normalizada == referencia normalizada del banco | 100 | 1 sola candidata |
| R2 NIT del pagador | `detapago.nitter`/`facventas.nitter` == NIT del movimiento | 80 | NIT conocido |
| R3 Nombre del pagador | normalizado (`sin tildes`, sin sufijos `S.A./LTDA/SA`, tokens ≥ 0.85) == `clifven` | 60 | fuzzy |
| R4 Importe exacto | `saldo == valor` (tolerancia 0.01 COP, todo en `Decimal`) | 40 | |
| R5 Importe parcial | `0 < valor < saldo` | 20 | pago parcial |

Normalización de referencia (espejo de `sanitizeBancolombiaReference`): sólo dígitos, sin sufijo
`"null"`, sin ceros a la izquierda, `lstrip("0") or "0"`. La referencia del banco puede venir como
`0092055984 null` → `92055984`.

**Casos especiales (obligatorios en la spec):**
- **Ambigüedad** (≥2 candidatas con el mismo score máximo) ⇒ `estado=AMBIGUA`, **no se postea**;
  se muestra en la UI con las candidatas para que el operador elija. La conciliación automática
  postea **sólo** con score ≥ 80 y candidata única.
- **Pago parcial** ⇒ S01 por el valor recibido (el saldo abierto lo refleja); resto abierto.
- **Sobrantecobro** (`valor > saldo`) ⇒ `estado=SOBREPAGO`, no se postea (el propio S01 lo
  rechazaría con 422 `ReceiptOverpaymentError`).
- **Sin candidatas** ⇒ `estado=SIN_MATCH` → el movimiento **aterriza como consignación bancaria**
  (`POST /api/erp/bank/consignations` → `consbancab`), no se inventa una factura.
- **Idempotencia** ⇒ `Idempotency-Key` = UUID v4 **determinista** derivado de
  `uuid5(NAMESPACE, f"{tenant}:{id_externo}")`; además `UNIQUE(tenant, id_externo)` en la tabla.
  Un re-run nunca duplica el recibo.

### 4. Reutilización del write-path (una sola verdad de libro)

**Ruta de match** → `erp/cash/repo.py:509-543` `RealReceiptsRepo.create(ReceiptCreate(...))`
(idem `FakeReceiptsRepo`), invocado **desde el repo de conciliación**, con:
`tenant`, `empresa` (de `tenant.erp.empresa`, nunca del cliente), `actor` (`"scraper:bancos"`),
`request_id` = id del movimiento, `idempotency_key` derivada del `id_externo`.
`codpag` = la forma de pago de **transferencia bancaria** (para que el débito caiga en bancos
`11100501` y no en caja `11050501`); `valor` = importe del movimiento; `fecha` = fecha del movimiento
(⚠ el periodo cerrado la rechazará con 409 — hay que decidir si se usa fecha del movimiento o fecha
de conciliación); `referencia` = referencia del banco (**recortada a 20 chars**, ver bug 4);
`concepto` = "Transferencia Bancolombia <referencia>".

**Ruta de no-match** → `erp/cash/router.py:294-330` / `_BaseConsignmentRepo` (`consbancab`), con la
forma de pago de consignación bancaria (`tippag`/`afepag` de la consignación; el fake siembra `"22"`).

Resultado: **ambas** rutas existen, están testeadas y escriben en el mismo ledger. La conciliación no
crea bookkeeping nuevo.

### 5. Los dos huecos que hay que cerrar antes de escribir código

1. **Cuenta cartera**: `CARTERA_CUENTA = "1305"` vs `"13050501"`. Opciones: (a) corregir el default a
   `13050501` y actualizar los tests herméticos (que siembran `"1305"`), (b) parametrizar por tenant
   vía `tenants.yaml` (`erp.cuenta_cartera`). Recomiendo (b) con default `13050501` — el PUC real
   manda, y deja de estar hardcodeado en dos módulos distintos.
2. **`numpag` sin recorte** (`erp/cash/repo.py:434`) → error 1406 con referencias > 20 chars.
   Recortar a 20 (como hace `erp/invoicing/repo.py:586`) **en el path compartido**.

### 6. Frontend

Página nueva `app/(authenticated)/banco/transferencias/page.tsx` + componente
`components/erp/TransferenciasBancarias.tsx` + cliente `lib/erp/bank.ts`, registrados en
`components/ui/Navigation.tsx` (`gerenteNavItems`) y `lib/auth/access.ts` (`PATH_RULES`) con la
feature `bank-reconciliation` (añadida a `tenants.yaml`). Listado de movimientos con estado, score y
razones; botón "Aplicar" (con `Idempotency-Key` UUID v4 vía `lib/erp/idempotency.ts`); los estados
`AMBIGUA`/`SIN_MATCH`/`SOBREPAGO` se resuelven a mano.

### 7. Dónde corre el scraper

**No en Render.** El scraper corre en la caja **on-premise Windows** (donde hay MySQL, la API con
`erp.enabled` y disco persistente) o en el portátil del operador (macOS) si se prefiere la bóveda con
Keychain. El disparo puede ser manual (CLI) o un **Windows Task Scheduler** siguiendo el patrón
`infra/MotoShop_AutoPull.xml`. La API sólo expone el resultado; **la API nunca ve la contraseña**.

---

## Riesgos

| # | Riesgo | Severidad | Mitigación / decisión |
|---|---|---|---|
| R1 | **Automatizar el login de un banco puede violar los ToS del banco**, aunque la empresa autorice el uso interno de los datos. Riesgo legal/contractual, no técnico. | **Crítica** | Fase 1 con sesión manual (opción C) → no hay login automatizado. Si se activa la fase 2 (login automatizado), requiere visto bueno legal documentado en el ADR. Es la razón principal para no empezar por la bóveda. |
| R2 | **Akamai anti-bot**: el interstitial prueba que el fetch plano no sirve; Playwright puede seguir bloqueado. | Alta | Perfil persistente + Chromium real; sin plugins stealth; rate-limit 1 corrida/ventana; si Akamai bloquea, el parser DOM/A no ayuda → plan B: exportar el movements a CSV a mano e importar. |
| R3 | **Contrato interno del banco no verificado**: no se pudo confirmar el endpoint XHR ni los selectores DOM ni la forma real del JSON. | Alta | Parser como función pura + fixtures; el modo C (DOM/HTML) es el fallback más robusto; contrato de parsing definido por tipo, no por endpoint. |
| R4 | **Sesión = credencial**: el `user_data_dir` guarda cookies activas; su robo equivale al robo de la sesión bancaria. | Alta | Directorio 700, fuera del repo, cifrado opcional del perfil, rotación (re-login manual) y revisión de permisos. |
| R5 | **Exposición de plaintext**: prompt TTY (ok), memoria del proceso, `ps`/`environ` (evitar: nunca pasar secretos por argv/env), logs de Playwright (`DEBUG=pw:api` imprime los valores llenados; `screenshot`/`trace`/`video` capturan la pantalla del login), exfiltración por el contexto del agente. | Alta | El prompt lo ejecuta el usuario, nunca el agente. `getpass` sin eco; secretos nunca por argv/env; Playwright sin `dumpio`/trace/video en la fase de login; log redaction explícita; `gitignore` del path del vault; gitleaks/detect-secrets en CI. |
| R6 | **La API cloud no tiene MySQL** → los endpoints de conciliación degradan a 503 en Render. | Media | El flujo completo (scrape + posting) corre on-premise; la API cloud sólo sirve lectura analítica. Declarar explícitamente el requisito on-premise en la spec. |
| R7 | **Sesión expira / 2FA recurrente**: el flujo desatendido se rompe. | Media | El scrape devuelve un error explícito `SESSION_EXPIRED` y no postea nada; re-login manual guiado. |
| R8 | **Doble contabilización**: el mismo movimiento scraped posteado dos veces. | Media | `UNIQUE(tenant, id_externo)` + `Idempotency-Key` determinista (uuid5) + φ0 del write-path. |
| R9 | **Match erróneo**: mismo importe, distintos clientes → recibo contra la factura equivocada. | Media | Auto-postear sólo con score ≥ 80 y candidata única; el resto a revisión manual; `razones` visibles en la UI. |
| R10 | **Importe/fecha del banco con formato local** (dd/mm, `$ 45.000`) → parseo erróneo. | Media | Normalización centralizada + tests con fixtures de formatos reales; todo en `Decimal`, nunca `float`. |
| R11 | **Dependencias nuevas sin ADR** violan `openspec/config.yaml` (`cryptography`, `playwright`). | Media | ADR nuevo obligatorio antes de tocar `pyproject.toml`/`uv.lock`. |
| R12 | **Presión de Akamai / ToS por frecuencia**: correr el scrape a diario puede parecer abusivo. | Media | 1 corrida/día, backoff exponencial, fuera de horario pico, auditar cada corrida en `app_audit_log`. |
| R13 | **Los importes del banco incluyen movimientos que no son cobros** (transferencias entre cuentas, retiros, comisiones). | Media | Filtro por cuenta destino + tipo de movimiento + signo; los que no califican quedan `IGNORADO` con su razón, no se postean. |
| R14 | **Fecha del movimiento en periodo contable cerrado** → 409 al postear. | Baja | Definir explícitamente en la spec: `fecha` = fecha del movimiento (fiel) y el 409 se reporta al operador para que re-dispare tras el cierre; o `fecha` = fecha de conciliación (contable). **Decisión de negocio pendiente.** |
| R15 | **Colisión de `numnum` entre prefijos**: `open_balance` filtra sólo por `numnum`, sin `prenum`. | Baja | El matching debe filtrar por `prefven`; corregir `open_balance` para aceptar `prenum`. |

---

## No verificado (no se pudo comprobar con el código/los datos disponibles)

1. **El portal Bancolombia**: no se pudo abrir ni autenticar (interstitial Akamai). **Desconocidos**:
   existencia y forma del endpoint XHR de movimientos, selectores del DOM, existencia y flujo de 2FA/OTP,
   formato exacto de fechas/montos/referencias, número máximo de páginas, si el banco emite el NIT del
   pagador, y los límites de uso del portal.
2. **Los datos reales de `sgHermes`** (BD legacy no accesible desde este entorno): contenido real de
   `formapago.codpag` (el fake siembra `"01"`/`"22"` de 2 chars, pero el esquema vivo muestra `F01`..`F10`
   de 4 chars — **confirmar antes de fijar `codpag` en la conciliación**), saldos reales por cuenta, y
   si `detapago.numpag` contiene efectivamente la referencia Bancolombia en producción.
3. **Comportamiento de Playwright Python contra Akamai**: no se instaló el navegador ni se ejecutó
   ningún intento (ni se debe, sin autorización explícita).
4. **Cuentas del PUC en producción**: se asumió `13050501` (cartera) y `11100501` (bancos) a partir de
   `docs/hermes/evidence/masvital_live_schema_2026-10.md:133-136`; no se verificó el plan de cuentas real.
5. **El impacto real de la inconsistencia `1305`/`13050501`**: es una lectura de código, no una
   reproducción contra la BD (los tests pasan porque siembran `"1305"`).
6. **Windows DPAPI / Credential Manager**: no se prototipó el backend de custodia en Windows.
7. **Volumen de movimientos y ventana de conciliación** (cuántos/mes): no hay datos.

---

## Ready for Proposal

**Sí — con dos decisiones de negocio que el orquestador debe llevar al usuario antes de escribir la
propuesta:**

1. **Alcance de la fase 1**: ¿arrancamos por **sesión manual reutilizada (C, sin credenciales
   almacenadas)** y dejamos la bóveda cifrada como fase 2, o la bóveda es un requisito de la primera
   entrega? La recomendación técnica es **C primero** (elimina el riesgo legal de automatizar el login
   y el de exponer la contraseña), pero la bóveda es el componente que el usuario pidió explícitamente
   y su diseño (custodia con dos backends, CLI propio) no cambia mucho por el orden.
2. **Fecha contable del recibo automático**: ¿`fecha` = fecha del movimiento bancario (fiel, puede dar
   409 por periodo cerrado) o fecha de conciliación (nunca da 409, pero dilata el devengo)?

Alcance técnico propuesto para el proposal: **backend-only** (módulo `erp/bankreconciliation` +
migración `app_bank_movements` + bóveda + CLI + scraper + matching + tests offline), con la página
frontend como unidad de trabajo separada y encadenada (regla del repo: cambios cross-repo se
entregan en unidades revisables separadas).

El proposal debe incluir además el **ADR** (`docs/decisions/00XX-…`) para las dependencias nuevas
(`cryptography`, `playwright`) y la decisión legal sobre los ToS del banco, y un **rollback plan**
(baja de la migración `DROP TABLE app_bank_movements`; los recibos ya posteados se anulan por la ruta
de anulación existente `erp/annulment/`, no por borrado).
