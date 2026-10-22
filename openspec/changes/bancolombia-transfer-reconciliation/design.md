# Design: Conciliación de transferencias Bancolombia — botón "Verificar"

## Technical Approach

**El disparador es un botón "Verificar" en el POS.** El operador ya capturó el importe, lo
presiona y el sistema entra al portal, abre la cuenta **del tenant** y extrae el movimiento de ese
valor; el front prellena pagador + referencia saneada y el operador confirma el pago (el
prellenado **nunca contabiliza**).

Un scrape tarda 10–40 s ⇒ no cabe en un request HTTP (BFF serverless + timeouts de la nube) ⇒
**job asíncrono**: `POST /api/erp/bank/verificaciones` → `202 {job_id}` → el scrape corre en el
**nodo local del tenant** → estado persistido → el front sondea cada ~2 s. El scrape **no** corre
en la nube: Render no tiene navegador ni disco, y el perfil de Playwright **es** la sesión; el
nodo local ya está priorizado por `resolveFallbackUrls(tenant)`
(`frontfambus/lib/api/backendFailover.ts`).

Puente del portal (sin cuentas ni etiquetas fijas): `/autenticacion` → `/home` → tarjeta de
cuentas → **la cuenta cuya etiqueta == `BANK_ACCOUNT_LABEL`** → `/detalles-y-movimientos/cuentas`
→ tab "Movimientos" → tabla "Tus movimientos", paginada. **El parseo DOM es la estrategia
primaria**; no se inventa endpoint XHR.

## Architecture Decisions

| # | Decisión y razón |
|---|---|
| D1 | **Botón bajo demanda**; el watcher queda como pre-fetch **opcional y secundario** (apagado por defecto). |
| D2 | **Job asíncrono** con estado persistido; poll ~2 s; timeout 120 s (300 s esperando OTP); un worker por nodo (lock) + 30 s mínimo ⇒ sin sesiones concurrentes. |
| D3 | **Scrape en el nodo local**; la nube responde `503` ⇒ la UI conserva el pegado manual (nunca punto único de fallo). |
| D4 | **Failover**: `fetchWithFailover` escala en 502/503/504 ⇒ el `503` de la nube salta al PC del tenant; nodo de otro tenant ⇒ `503` ⇒ no se cruzan tenants; `404` sólo del dueño del job. |
| D5 | **Credencial por tenant** (`bancolombia-<tenant>`; vault multi-entrada ya soportado); sin entrada ⇒ `credencial_ausente`: nunca otra credencial ni scraping anónimo. |
| D6 | **Cuenta por etiqueta** (`BANK_ACCOUNT_LABEL`), nunca por índice; ausente ⇒ `cuenta_no_encontrada`, no se lee otra cuenta. |
| D7 | **OTP en la consola del nodo** (proceso hijo con consola en Windows), nunca en el navegador; no se persiste. |
| D8 | *Conservada* **Custodia**: `keyfile` prohibido, `passphrase` default, `keychain` macOS, **`dpapi` stub** ⇒ Windows `passphrase`; 700/600; Fernet+PBKDF2 600k. |
| D9 | *Conservada* **Parser**: celda a celda, `Decimal` colombiano, `sanitize_reference` quita " null", ceros no utilizable, pagador sólo "PAGO QR", signo ⇒ dirección. |
| D10 | *Conservada* **Idempotencia**: `uuid5(tenant:id_externo)` de dominio, uuid4 HTTP, `UNIQUE(tenant,id_externo)`; job con PK `uuid5(tenant:factura_id:valor)`. |
| D11 | *Conservada* **Cartera/`numpag`**: canónica `13050501` + alias `1305`; clip `numpag` a 20. |
| D12 | *Conservada* **Confirmación humana**: score ≥ 80 + candidata única ⇒ *listo para aplicar*, nunca auto; S01 o consignación por `erp/cash`; `409` en periodo cerrado. |
| D13 | *Conservada* **Aislamiento/permisos**: BD por tenant + columna `tenant`; rutas `erp-cash` + `require_erp_tenant`; `apply` ⇒ `require_erp_collections_write`. |
| D14 | *Conservada* **Redacción**: `PII_KEYS` ⇒ subcadena; sin trace/video; perfil fuera del repo (700); `codpag` fail-closed. |

## Configuración por nodo

Un proceso de API = un tenant. Variables de entorno en el `.env` de cada máquina (ya leído por
`infra/start_api.ps1`):

| Variable | PC MasVital | PC MotoShop | Mac (dev) | Render |
|---|---|---|---|---|
| `BANK_SCRAPER_ENABLED` | `true` | `true` | `true` | `false` |
| `BANK_TENANT` | `masvital` | `motoshop` | tenant en pruebas | — |
| `BANK_CREDENTIAL_ENTRY` | `bancolombia-masvital` | `bancolombia-motoshop` | `bancolombia-<tenant>` | — |
| `BANK_ACCOUNT_LABEL` | etiqueta MasVital | etiqueta MotoShop *(por confirmar)* | según tenant | — |
| `BANK_VAULT_BACKEND` | `passphrase` | `passphrase` | `keychain` | — |
| `BANK_PROFILE_DIR` | `%APPDATA%\motoshop\bank-profile\<tenant>` | ídem | `~/.config/motoshop/bank-profile/<tenant>` | — |

Provisión: Mac → `python -m motoshop_api.erp.bankreconciliation.cli --backend keychain set
bancolombia-masvital` (y `bancolombia-motoshop`); Windows → mismo CLI con `--backend passphrase`.
El Mac guarda **ambas** entradas y cambia de tenant relanzando con otro `BANK_TENANT`. Convención y
topología en `docs/runbook-banco.md` (S3). Cada nodo abre **sólo** la cuenta de su etiqueta; la nube
no abre cuentas.

## Data Flow (botón "Verificar")

```
 POS "Verificar"        front/BFF                API nube            nodo local (PC del tenant)
 POST /bank/verificaciones ► app/api/[...path] ─► Render ─► 503 scraper_no_habilitado
 {factura_id, valor}    (fetchWithFailover) ─►         └── 503 ⇒ cascada ──┐
                                                                    ┌────────▼─────────┐
                                                                    │ 202 {job_id}     │
                                                                    │ worker: vault →  │
                                                                    │ Playwright perfil│
                                                                    │ 700 → /autentica-│
                                                                    │ ción → /home →   │
                                                                    │ cuenta por ETIQ.│
                                                                    │ → Movimientos →   │
                                                                    │ "Tus movim." →   │
                                                                    │ parseo → upsert  │
                                                                    │ → match por valor│
                                                                    └────────┬─────────┘
  poll ~2 s ◄─ GET /bank/verificaciones/{job_id} ───────────────────────┘ (tabla del job)
  en_cola → ejecutando → (esperando_otp) → resuelto | sin_coincidencia | ambiguo | fallido
  resuelto ⇒ prellena pagador + referencia (si el operador no los escribió) → el operador
  confirma ⇒ se registra el pago. Nunca contabiliza solo.
```

Mientras `esperando_otp`, el front muestra: *"El banco pide un código: ingrésalo en la consola del
nodo local"* (nunca pide el código en el navegador). Con `503`, el botón queda deshabilitado con el
motivo del nodo y el pegado manual sigue disponible.

## File Changes

Base API `motoshop-app/api/src/motoshop_api/`. Cadena `feature-branch-chain`: tracker
`feature/bancolombia-transfer-reconciliation` (sólo él mergea a `main`), ramas
`feature/banco-NN-<slug>`, cada hija contra la rama de la anterior, máx. 800 líneas/PR. #8 y #10
son PRs de `frontfambus` (base = tracker de ese repo). Camino crítico **botón→POS** en
#6+#7+#8, antes de la conciliación por factura (#9) y la página operativa (#10).

| PR | Slice (qué entrega) | Archivos | Base |
|---|---|---|---|
| #1 | S1 Hotfix cash — cartera + alias `1305`; clip `numpag` | `erp/cash/{repo,store}.py`, `erp/invoicing/repo.py` | tracker |
| #2 | S2 Bóveda + ADR — **ya implementado** | `erp/bankreconciliation/{vault,cli}.py`, `tests/test_bank_vault.py` | #1 |
| #3 | S3 Config por tenant — env, fail-fast, runbook | `erp/bankreconciliation/node_config.py`, `scripts/bank_verify.py`, `docs/runbook-banco.md` | #2 |
| #4 | S4 Persistencia — DDL + upsert idempotente | `infra/migrations/F9-001/002-*.sql`, `erp/bankreconciliation/{schemas,store}.py` | #3 |
| #5 | S5 Portal + parser — cuenta por etiqueta, scraper DOM | `erp/bankreconciliation/{portal_pages,parser,scraper}.py`, `scripts/bank_sync.py` | #4 |
| #6 | S6 Job — tabla, worker, `POST/GET /bank/verificaciones` | `infra/migrations/F9-003-*.sql`, `erp/bankreconciliation/{jobs,worker}.py`, `router.py` | #5 |
| #7 | S7 Match valor + API — 0/1/2+ candidatos | `erp/bankreconciliation/value_match.py`, `router.py` | #6 |
| #8 | S8 **Botón "Verificar"** — polling 2 s, prellenado | `frontfambus/lib/erp/bank.ts`, `lib/api/hooks.ts`, `components/pos/PaymentModal.tsx` | tracker (pide #6, #7) |
| #9 | S9 Factura + posting — score, listo para aplicar, S01 | `erp/bankreconciliation/{matching,repo}.py`, `router.py` | #7 |
| #10 | S10 Página banco — listado, filtros, resolución manual | `frontfambus/app/(authenticated)/banco/transferencias/page.tsx`, `components/erp/TransferenciasBancarias.tsx` | #8 (pide #9) |

## Interfaces / Contracts

`app_bank_verification_jobs` (InnoDB, `F9-003`): PK `id` = `uuid5(tenant:factura_id:valor)`;
`tenant`, `factura_id`, `valor DECIMAL(18,2)`, `job_id` uuid4 UNIQUE, `estado`, `nodo`,
`resultado_json`, `error_codigo`, `creado_en`, `actualizado_en`, `expira_en`,
KEY `(tenant, estado, creado_en)`.

Estados: `en_cola · ejecutando · esperando_otp · resuelto · sin_coincidencia · ambiguo · fallido ·
expirado`. Errores: `credencial_ausente · credencial_invalida · sesion_expirada · antibot ·
portal_no_disponible · cuenta_no_encontrada · scraper_no_habilitado · tenant_no_servido`. Ningún
error deja movimientos ni filas parciales.

```python
# parser.py — puro, offline
def parse_colombian_amount(raw: str) -> Decimal: ...   # "$ 458.200,00" -> 458200.00
def parse_movement_row(cells: Sequence[str]) -> BankMovement: ...   # 4 celdas
# value_match.py: match_by_value(valor, movs, ventana) -> ValueMatch(ambiguo, candidatos); 2+ => ambiguo
```

Rutas (`("erp-cash",)` en `ERP_ROUTE_MODULES` + `require_erp_tenant`):

```
POST /api/erp/bank/verificaciones            → 202 {job_id, estado, expira_en} | 503 scraper_no_habilitado | 503 tenant_no_servido
GET  /api/erp/bank/verificaciones/{job_id}   → 200 {job_id, estado, resultado?, error?, expira_en} | 404
GET  /api/erp/bank/candidates?valor=         → {ambiguo, ventana, candidatos:[{id,valor,pagadorNombre,referencia,fecha}], ultimaIngestaAt}
GET  /api/erp/bank/movements?estado=&desde=&hasta= → listado con estado y factura
GET  /api/erp/bank/sync-status                → última ingesta, nodo, ventana
POST /api/erp/bank/reconciliation/{id}/apply → S01 o consignación, 409 periodo cerrado, Idempotency-Key v4
```

```tsx
// frontfambus/components/pos/PaymentModal.tsx
const refDirty = useRef(false);   // onChange de "Referencia"
const nameDirty = useRef(false);  // onChange del nombre del pagador
// "Verificar": POST 202 {job_id} → poll 2 s → "resuelto" ⇒ prellena sólo lo NO tocado.
//   503 ⇒ "Verificación no disponible"; se conserva el pegado manual.
```

## Testing Strategy

| Capa | Qué | Enfoque |
|---|---|---|
| Unit | parser (importes, " null", ceros, "PAGO QR", signo) + `match_by_value` (0/1/2, fuera de ventana) + `node_config` (fail-fast) + vault por tenant | pytest puro + fixtures DOM |
| Integration | ingesta idempotente (2ª corrida ⇒ 0 filas), `uuid5` estable, aislamiento por tenant, job idempotente (2º POST ⇒ mismo `job_id`) | hermético (`Fake*Store`) |
| Integration | router: 403 sin `erp-cash`; sin scraper ⇒ 503; tenant ajeno ⇒ 503; `apply` sin admin/gerente ⇒ 403; 409 periodo cerrado + reintento | hermético (TestClient) |
| E2E | FE mock (prellena 1; **no** sobrescribe referencia escrita; 2 ⇒ elegir; 0 ⇒ vacío sin error; 503 ⇒ flujo manual intacto) · live (login+scrape) | vitest + Playwright `page.route` |

## Migration / Rollout

Orden: ADR-0026 Accepted → `F9-001/002/003` → API con flag **off** → provisión del vault por
máquina (`bank_vault set`) → `playwright install chromium` + perfil 700 fuera del repo →
`BANK_SCRAPER_ENABLED=true` en el nodo del tenant → botón "Verificar" (#8). Ventana por defecto =
día en curso, configurable y auditable.

Rollback: apagar `BANK_SCRAPER_ENABLED` (⇒ 503 y flujo manual); quitar las rutas de
`ERP_ROUTE_MODULES`; `DROP TABLE app_bank_verification_jobs`; recibos posteados se anulan por
`erp/annulment/`; revocar con `bank_vault.py delete`.

## Open Questions

- [x] **Convención de entradas del vault** (`bancolombia-<tenant>`): resuelta; vive en este diseño
  y en `docs/runbook-banco.md`.
- [ ] **Visto bueno legal** del ToS para login automatizado — ADR-0026 sigue `Proposed`.
- [ ] **Etiqueta de la cuenta MotoShop**: por confirmar; sin ella el nodo falla con
  `cuenta_no_encontrada`.
- [ ] **`dpapi` sigue siendo stub**: Windows usa `passphrase`; ¿se implementa DPAPI?
- [ ] **Endpoint XHR desconocido**: el parseo DOM de "Tus movimientos" es la estrategia primaria;
  interceptar XHR sería optimización opcional. **No se inventa endpoint.**
- [ ] `formapago.codpag` real de transferencia: **fail-closed** (ver D14).
