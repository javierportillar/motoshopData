# Proposal: bancolombia-transfer-reconciliation

## Intent

Las transferencias entrantes de Bancolombia se digitan a mano en el POS. Automatizar el login al portal (bóveda cifrada + prompt interactivo), scrapeando movimientos y conciliándolos contra facturas abiertas, posteando S01 por el write-path verificado.

## Scope

### In Scope
- Módulo `erp/bankreconciliation/` (hermano de `erp/cash`).
- Bóveda + CLI, scraper Playwright, matching, posting S01/consignación, endpoints.
- Hotfix de 2 defectos del path reusado; tabla `app_bank_movements` + migración.
- Página de transferencias (frontfambus, PR propio).

### Out of Scope
- Sesión manual reutilizada (D1-B descarta fase C).
- DuckDB silver/gold; API del banco; SPEI/multi-banco.

## Capabilities

### New Capabilities
- `erp-bank-transfer-ingestion`: login automatizado, bóveda, scraping, ingesta idempotente.
- `erp-bank-reconciliation`: matching explicable y aplicación (S01 o consignación).
- `erp-bank-reconciliation-ui`: página de transferencias y resolución manual.

### Modified Capabilities
- `erp-collections-cash`: open balance contra la cartera real `13050501` (por tenant); `numpag` a 20 chars; fecha del recibo = la del movimiento ⇒ 409 en periodo cerrado (D2-A).

## Approach

Consume `erp/cash` (`RealReceiptsRepo.create`, `/api/erp/bank/consignations`). Persistencia `app_bank_movements` con `UNIQUE(tenant, id_externo)`. Matching = función pura explicable: referencia 100 · NIT 80 · nombre 60 · importe 40 · parcial 20; auto-posteo sólo con score ≥ 80 y candidata única; ambigua ⇒ `AMBIGUA`, sobrepago ⇒ `SOBREPAGO`, sin match ⇒ consignación. Idempotencia `uuid5(tenant:id_externo)`. Scraping: Playwright con perfil persistente (`user_data_dir`), JSON/XHR sobre DOM, OTP en vivo y no guardado. Bóveda: Fernet + PBKDF2 (600k), custodia `passphrase`/`keychain`/DPAPI, `keyfile` prohibido. Scraper on-premise; la API sólo consume movimientos.

## Entrega por slices

| # | Slice | Entregable | Líneas | Depende |
|---|---|---|---|---|
| 1 | Hotfix cash | cartera `13050501`; clip `numpag` | ~120 | — |
| 2 | Deps+ADR+bóveda | ADR `0026`; vault + CLI | ~340 | 1 |
| 3 | Persistencia | `F9-001-app_bank_movements.sql`; store/repo | ~300 | 1 |
| 4 | Scraper | perfil; parseo puro + fixtures; runbook | ~380 | 2,3 |
| 5 | Matching+servicio | `matching.py`; posting S01/consignación; router | ~480 | 3,4 |
| 6 | Frontend | página; `lib/erp/bank.ts`; nav + reglas | ~320 | 5 |

Cada slice lleva tests y docs; ninguno excede 800 líneas. Cadena: 1 → (2,3) → 4 → 5 → 6.

## Affected Areas

| Area | Impact |
|---|---|
| `erp/bankreconciliation/` + CLI + tests | New |
| `erp/cash/repo.py`; `erp/guards.py`; `main.py`; `tenants.yaml` | Modified |
| `infra/migrations/F9-001-*.sql`; `docs/decisions/0026-*`; `../frontfambus` | New |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| ToS: la empresa autoriza los datos, no el login | Alta | ADR con visto bueno legal; 1 corrida/día |
| Akamai bloquea el scrape | Alta | perfil persistente; plan CSV manual |
| `user_data_dir` es una credencial | Alta | dir 700 fuera del repo; rotación |
| Fuga de plaintext | Alta | `getpass`; sin argv/env/logs/trace/video |
| Periodo cerrado ⇒ 409 | Media | D2-A: bloquea hasta reabrir; aviso |
| Deps nuevas sin ADR | Media | ADR `0026` antes de `pyproject.toml` |
| Host scraper ≠ host API | Media | on-premise; Render sólo lectura (503) |

## Rollback Plan

Desactivar la feature en `tenants.yaml` y la matriz de módulos; `DROP TABLE app_bank_movements`; los recibos posteados se anulan por `erp/annulment/` (nunca borrado).

## Dependencies

- `cryptography` + `playwright` (ADR `0026`), Chromium, MySQL on-premise.

## Success Criteria

- [ ] Movimiento con score ≥ 80 postea S01 y descuenta el saldo exacto.
- [ ] Re-run del mismo `id_externo` no duplica recibo; referencia > 20 chars responde 2xx.
- [ ] Open balance real ≠ 0; periodo cerrado ⇒ 409 sin escritura parcial.
- [ ] `pytest` y `vitest` verdes; sin secretos en repo ni logs.
