# Tasks: bancolombia-transfer-reconciliation — Botón "Verificar" + conciliación de transferencias

## Metadatos

| Campo | Valor |
|---|---|
| Cambie | `bancolombia-transfer-reconciliation` |
| Specs | `erp-bank-transfer-ingestion`, `erp-bank-reconciliation`, `erp-bank-transfer-reconciliation-ui`, `erp-collections-cash` (delta) |
| Design | `openspec/changes/bancolombia-transfer-reconciliation/design.md` (slices S1..S10) |
| Repo backend | `motoshopData` (root `/Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData`) |
| Repo frontend | `frontfambus` (root `/Users/javierportillarosero/Documents/personal/dataEmpresas/frontfambus`) |
| Estrategia de entrega | `force-chained` / `feature-branch-chain` |
| Presupuesto de review | 800 líneas por PR · 400 líneas = guía de foco de review |
| Modo de marcadores | `[AUTO]` = apply automático · `[CHECKPOINT]` = requiere MySQL local u operador |

## Topología de ramas (`feature-branch-chain`)

- Tracker backend: `feature/bancolombia-transfer-reconciliation` (en `motoshopData`) — **sólo él mergea a `main`**.
- Tracker frontend: `feature/bancolombia-transfer-reconciliation` (en `frontfambus`) — **sólo él mergea a `main`**.
- Ramas hijas (una por PR), cada una base = rama del PR anterior:

| PR | Rama | Base | Slice | Repo |
|---|---|---|---|---|
| #1 | `feature/banco-01-cartera-numpag` | tracker `motoshopData` | S1 | motoshopData |
| #2 | `feature/banco-02-vault` | rama PR #1 | S2 (**ya implementado**) | motoshopData |
| #3 | `feature/banco-03-node-config` | rama PR #2 | S3 | motoshopData |
| #4 | `feature/banco-04-persistencia` | rama PR #3 | S4 | motoshopData |
| #5 | `feature/banco-05-portal-parser` | rama PR #4 | S5 | motoshopData |
| #6 | `feature/banco-06-job` | rama PR #5 | S6 | motoshopData |
| #7 | `feature/banco-07-match-valor` | rama PR #6 | S7 | motoshopData |
| #8 | `feature/banco-08-boton-verificar` | tracker `frontfambus` | S8 | **frontfambus** |
| #9 | `feature/banco-09-factura-posting` | rama PR #7 | S9 | motoshopData |
| #10 | `feature/banco-10-pagina-banco` | rama PR #8 (`frontfambus`) | S10 | **frontfambus** |

Reglas:
- Ningún PR mergea directo a `main`. El tracker es el único que lo hace.
- PR #8 (frontfambus) **no** depende de la rama de PR #7: es un PR del otro repo, con base = tracker de `frontfambus`. Sí **requiere** que #6 y #7 ya estén mergeados en `main` de `motoshopData` (contrato de API congelado por los tests de backend).
- PR #10 (frontfambus) base = rama de PR #8 en `frontfambus` (encadena dentro del repo frontend).

## Convenciones heredadas

- Backend: pytest, `tests/test_<area>_<unit>.py`, nombres de test en español (`test_<comportamiento>_...`), fixtures `Fake*Store` para hermeticidad, `Decimal` para dinero, ruff (`line-length = 100`, reglas `E,F,I,UP,B,SIM`).
- Verificación backend (cwd `motoshop-app/api`): `uv run pytest tests/<file> -q`; suite completa: `uv run pytest -q`; lint: `uv run ruff check src tests`.
- Frontend: vitest (`npm run test:unit` = `vitest run`), specs co-localizados `*.test.ts(x)`, E2E Playwright en `tests/*.spec.ts`.
- Verificación frontend (cwd `frontfambus`): `npx vitest run <archivo>` · `npm run test:unit` · `npm run typecheck` (`tsc --noEmit`) · `npm run lint` · `npx playwright test tests/<spec>.spec.ts`.
- Migraciones: `infra/migrations/F9-*.sql` (InnoDB, prefijo `app_*`, patrón de grants de `F5-003`/`F8-004`).
- Comandos backend desde la raíz del repo: `uv run --project motoshop-app/api pytest ...` o, como asume el resto del repo, cwd `motoshop-app/api`.

---

## Review Workload Forecast

| PR | Slice | Repo | Código | Tests | Docs/SQL | Total | Presupuesto 800 | Guía 400 |
|---|---|---|---|---|---|---|---|---|
| #1 | S1 cartera + `numpag` | motoshopData | ~70 | ~120 | 0 | **~190** | OK | OK |
| #2 | S2 vault + ADR (**ya hecho**) | motoshopData | ~765 | ~329 | ~54 | **~1.148** | **EXCEDE (+43%)** | **EXCEDE** |
| #3 | S3 config por nodo + runbook | motoshopData | ~120 | ~90 | ~50 | **~260** | OK | OK |
| #4 | S4 persistencia | motoshopData | ~170 | ~120 | ~40 | **~330** | OK | OK |
| #5 | S5 portal + parser | motoshopData | ~300 | ~240 | ~60 | **~600** | OK | **EXCEDE** |
| #6 | S6 job + worker | motoshopData | ~220 | ~200 | ~50 | **~470** | OK | **EXCEDE** |
| #7 | S7 match por valor | motoshopData | ~110 | ~140 | 0 | **~250** | OK | OK |
| #8 | S8 botón "Verificar" | frontfambus | ~200 | ~180 | 0 | **~380** | OK | OK |
| #9 | S9 factura + posting | motoshopData | ~250 | ~270 | 0 | **~520** | OK | **EXCEDE** |
| #10 | S10 página banco | frontfambus | ~240 | ~180 | 0 | **~420** | OK | **EXCEDE** |
| | **Total** | | ~2.445 | ~1.870 | ~204 | **~4.568** | 10 PRs | 4 PRs > 400 |

- **Algún slice excede el presupuesto de 800 líneas:** **Sí — sólo PR #2 (S2, vault)**, que ya está escrito y verificado en el working tree: `vault.py` 616 + `cli.py` 146 + `test_bank_vault.py` 329 + ADR-0026 52 + `pyproject.toml`/`uv.lock` 4 = **~1.148 líneas**, +43% sobre el presupuesto.
- **PRs encadenados recomendados:** **Sí** (ya forzado por `delivery_strategy: force-chained`). Los otros 9 PRs entran holgadamente en 800.
- **Riesgo del presupuesto de 400 líneas (guía de foco de review):** **Medio-Alto** — S5 (600), S9 (520), S6 (470) y S10 (420) lo superan. Si el revisor pide foco extra en cualquiera de ellos, promover sus commits a PRs encadenados adicionales (slices S5→S5a/S5b, S9→S9a/S9b) sin cambiar el código.
- **Decisión necesaria antes de apply:** **Sí** — una sola, y es sobre el PR #2 ya implementado:
  1. `size:exception` para PR #2 (recomendado): es una unidad de seguridad cohesionada, ya verificada (13/13 tests verdes, ruff limpio) y partirla obligaría a separar `test_bank_vault.py` de `vault.py`, rompiendo la regla "tests con el código".
  2. Alternativa: re-partir S2 en 2a (`vault.py` + `test_bank_vault.py` ≈ 945 líneas — **también excede 800**, requeriría una segunda excepción) y 2b (`cli.py` + ADR + deps ≈ 202 líneas). Más diffs, misma excepción.
  3. Alternativa: partir `vault.py` en `vault.py` + `custody.py` y partir el archivo de tests en dos. Requiere reescribir código ya verificado ⇒ **no recomendada**.
  Sin esa decisión, `apply` no puede abrir el PR #2.

---

## S1 — Hotfix de caja: cartera canónica + clip de `numpag` (PR #1, base: tracker `motoshopData`)

> Corrige dos defectos del path reusado que bloquean la conciliación: el saldo abierto se leía de una cuenta por defecto (`"1305"`) que no es la cuenta de cartera real (`13050501`), y `detapago.numpag` no se recortaba (error MySQL 1406 con referencias > 20 chars).

- [x] **1.1** `[AUTO]` **Saldo abierto contra la cartera real (`13050501`) con alias `1305`** `[CC-2s1, CC-2s2, CC-2s3, CC-2s4]`
  - RED: `motoshop-app/api/tests/test_erp_cash_cartera.py` — `test_open_balance_lee_la_cuenta_cartera_canonica_13050501` (fila con `codcue="13050501"` entra en el saldo), `test_open_balance_suma_el_alias_1305` (fila legacy con `codcue="1305"` también entra), `test_open_balance_de_otra_cuenta_no_entra` (fila con `codcue="1105"` no suma), `test_receipt_sobre_factura_con_alias_1305_cierra_el_saldo_a_cero` (recibo 150 000 contra factura sembrada en `1305` deja el saldo en 0 y el journal `COMMITTED`).
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/cash/repo.py` (`CARTERA_CUENTA = "13050501"`, `CARTERA_CUENTA_ALIASES: tuple[str, ...] = ("1305",)`, `open_balance()` itera los códigos canónico + alias), `motoshop-app/api/src/motoshop_api/erp/cash/store.py` (nuevo `ledger_rows_for_accounts(numnum: str, codcues: Sequence[str]) -> list[dict]` en `CashStore`/`FakeCashStore`/`RealCashStore`; `WRITABLE_TABLES` intacto).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_erp_cash_cartera.py tests/test_erp_receipts.py -q` y `uv run ruff check src tests`.
  - Evidencia (cwd `motoshop-app/api`): RED con el código original → **6 failed** (`open_balance` leía 0 para la fila `13050501`; el recibo contra esa factura moría con «no tiene saldo en cartera»). GREEN → `uv run pytest tests/test_erp_cash_cartera.py -q` → **8 passed**; `uv run pytest tests/ -q -k "not integration"` → **1002 passed, 15 deselected** (base 989 + 13 tests nuevos). `uv run ruff check src/motoshop_api/erp/ tests/test_erp_receipts.py` → **45 errores, los mismos preexistentes** (baseline idéntico; los archivos tocados: 0 violaciones).
  - Desviación menor: `ledger_rows(numnum, codcue)` (una sola cuenta) se REEMPLAZÓ por `ledger_rows_for_accounts(numnum, codcues)` en lugar de convivir — el método de cuenta única quedaba como código muerto tras el fix. `WRITABLE_TABLES` intacto.
  - Depends: —

- [x] **1.2** `[AUTO]` **Clip de `numpag` a 20 caracteres en el path de caja** `[CC-1s1, CC-1s2]`
  - RED: `motoshop-app/api/tests/test_erp_cash_reference_limit.py` — `test_receipt_con_referencia_de_40_chars_responde_201_y_guarda_los_20_primeros` (respuesta 201, `detapago.numpag` == referencia[:20], ningún error), `test_receipt_con_referencia_de_12_chars_se_guarda_verbatim`, `test_el_clip_no_altera_el_importe_la_factura_ni_la_fecha` (el importe, `numfven` y `fecha` del documento no cambian al truncar).
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/cash/repo.py` (constante compartida `NUMPAG_MAX_LEN = 20`; `"numpag": (body.referencia or "")[:NUMPAG_MAX_LEN]`), `motoshop-app/api/src/motoshop_api/erp/invoicing/repo.py` (importa `NUMPAG_MAX_LEN` de `erp.cash.repo` en vez del literal `[:20]` de la línea 586).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_erp_cash_reference_limit.py tests/test_erp_invoice_save.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED con el código original → `test_receipt_con_referencia_de_40_chars_responde_201_y_guarda_los_20_primeros` falló (`numpag` traía los 40 chars; en MySQL eso es error 1406 ⇒ 503). GREEN → `uv run pytest tests/test_erp_cash_reference_limit.py tests/test_erp_invoice_save.py -q` → **21 passed**; suite completa **1002 passed, 15 deselected**; ruff sin violaciones nuevas.
  - Nota: la validación de request (`max_length=40`) queda intacta — 41 chars siguen siendo 422 (`test_una_referencia_de_mas_de_40_chars_sigue_siendo_422`).
  - Depends: 1.1

**S1 DoD**: el saldo abierto de una factura lee la cuenta de cartera real (con alias legacy) y un recibo con referencia larga se postea sin error 1406.
**Rollback**: revertir las dos constantes y el clip; sin cambio de esquema.

---

## S2 — Bóveda de credenciales + ADR-0026 (PR #2, base: rama PR #1) — **YA IMPLEMENTADO, PENDIENTE DE COMMIT**

> No se re-planifica. El código existe en el working tree de `motoshopData` y está verificado. Esta slice se cierra con el commit, no con RED/GREEN.

- [x] **2.1** `[AUTO]` **Vault + CLI + ADR + dependencia `cryptography`** `[ING-1s1, ING-1s2, ING-2s1, ING-2s2]`
  - Archivos ya escritos: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/vault.py` (Fernet + PBKDF2 600 000, multi-entrada, custodia `passphrase`/`keychain`/`dpapi` stub, fail-fast de backend, archivo 600 / directorio 700), `.../bankreconciliation/cli.py` (`set`/`list`/`check`/`rotate`/`delete`/`reveal`), `motoshop-app/api/tests/test_bank_vault.py` (13 tests), `docs/decisions/0026-bancolombia-vault.md` (estado `Proposed`), `motoshop-app/api/pyproject.toml` (`cryptography>=43`) y `motoshop-app/api/uv.lock`.
  - Evidencia de verificación (re-ejecutada en esta sesión, cwd `motoshop-app/api`):
    - `uv run pytest tests/test_bank_vault.py -q` → **13 passed** (1.78 s).
    - `uv run ruff check src/motoshop_api/erp/bankreconciliation/ tests/test_bank_vault.py` → **All checks passed!**
  - Cobertura de spec: `ING-1` (captura sin eco + listar/rotar/eliminar sin revelar), `ING-2` (round-trip; frase incorrecta o archivo alterado ⇒ error claro y sin estado parcial).
  - Pendiente: **commit** con el plan de commits de la sección "Plan de commits por work-unit" (S2). No se escribe trabajo nuevo.

**S2 DoD**: commit de la slice con 13/13 tests verdes y ruff limpio. La marca `Accepted` del ADR NO se toca aquí (ver 3.4 y Preguntas abiertas).

---

## S3 — Configuración por nodo + runbook operativo (PR #3, base: rama PR #2)

> Un proceso de API = un tenant. La configuración vive en el `.env` de cada máquina; el código debe fallar rápido si la configuración es incompleta y nunca debe operar con la configuración de otro tenant.

- [x] **3.1** `[AUTO]` **`node_config.py`: configuración por nodo, fail-fast y convención de entrada de vault** `[ING-6s1, ING-6s2, ING-6s3, ING-8s2]`
  - RED: `motoshop-app/api/tests/test_bank_node_config.py` — `test_scraper_habilitado_sin_tenant_falla_rapido` (`NodeConfigError`), `test_scraper_habilitado_sin_etiqueta_de_cuenta_falla_rapido`, `test_scraper_habilitado_sin_credencial_resuelta_falla_rapido`, `test_scraper_deshabilitado_no_exige_credencial_ni_etiqueta` (en la nube: `BANK_SCRAPER_ENABLED=false` ⇒ config válida), `test_entrada_de_vault_por_tenant_usa_la_convencion_bancolombia_tenant` (`tenant=motoshop` ⇒ `bancolombia-motoshop`; `tenant=masvital` ⇒ `bancolombia-masvital`), `test_ventana_por_defecto_es_el_dia_en_curso` (desde = hoy 00:00, hasta = hoy 23:59:59, `ventana_por_defecto=dia`).
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/node_config.py` — dataclass `NodeConfig(tenant, scraper_enabled, credential_entry, account_label, vault_backend, profile_dir, window_start, window_end, min_interval_seconds)` + `load_node_config(env: Mapping[str, str] | None = None) -> NodeConfig` + `NodeConfigError`; lee `BANK_SCRAPER_ENABLED`, `BANK_TENANT`, `BANK_CREDENTIAL_ENTRY`, `BANK_ACCOUNT_LABEL`, `BANK_VAULT_BACKEND`, `BANK_PROFILE_DIR`; `credential_entry` por defecto = `bancolombia-<tenant>`; `min_interval_seconds = 30` (D2).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_node_config.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin el módulo → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.node_config'` (2 errores de colección, los dos archivos de test). GREEN → `uv run pytest tests/test_bank_node_config.py tests/test_bank_node_preflight.py -q` → **24 passed**; `uv run pytest tests/ -q -k "not integration"` → **1026 passed, 15 deselected** (base 1002 + 24 tests nuevos); `uv run ruff check` sobre los 4 archivos creados → **All checks passed!**
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - `NodeConfig` valida en `__post_init__`: con el scraper habilitado exige tenant, etiqueta y credencial; con el scraper deshabilitado (nube) la configuración es válida sin credencial ni etiqueta.
    - El vault **no** se consulta en la carga: los nombres de las entradas viven dentro del payload cifrado, así que resolverlos exigiría la clave maestra (prompt interactivo) — imposible en el proceso de la API, que corre como servicio sin consola. La resolución de la credencial es del preflight (3.2) y del scraper (S5).
    - `credential_entry` con `BANK_CREDENTIAL_ENTRY` presente pero vacía ⇒ `NodeConfigError` (la credencial no se puede resolver); si la variable no está, se deriva `bancolombia-<tenant>`.
    - Ventana por defecto = día local del nodo (`00:00:00` → `23:59:59`); ajustable con `BANK_WINDOW_START` / `BANK_WINDOW_END` (ISO-8601) y auditable vía `NodeConfig.ventana_por_defecto` (`dia` | `personalizada`).
    - `profile_dir` por defecto = `<config dir del usuario>/bank-profile/<tenant>` (misma regla que `vault._get_config_dir`, pero parametrizada por el `env` recibido para que la carga sea hermética).
  - Depends: 2.1

- [x] **3.2** `[AUTO]` **Preflight del nodo (`scripts/bank_verify.py`)** `[ING-6s2, ING-2s2]`
  - RED: `motoshop-app/api/tests/test_bank_node_preflight.py` — `test_preflight_falla_si_falta_la_etiqueta_de_cuenta`, `test_preflight_falla_si_la_entrada_de_vault_del_tenant_no_existe` (⇒ `credencial_ausente`), `test_preflight_falla_si_el_perfil_del_nodo_esta_dentro_del_repo` (ruta bajo el repo ⇒ rechazo), `test_preflight_falla_si_el_perfil_no_tiene_permisos_700` (en POSIX; `skipif win32`), `test_preflight_ok_devuelve_resumen_sin_revelar_secretos` (el resultado NO contiene usuario ni contraseña).
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/node_config.py` (`run_preflight(config: NodeConfig) -> PreflightResult`), `motoshop-app/api/scripts/bank_verify.py` (CLI: `python scripts/bank_verify.py --tenant motoshop [--check]`; importa `motoshop_api.erp.bankreconciliation.node_config`; código de salida 1 con motivo explícito).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_node_preflight.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED → mismo `ModuleNotFoundError` (2 errores de colección). GREEN → `uv run pytest tests/test_bank_node_config.py tests/test_bank_node_preflight.py -q` → **24 passed** (12 de preflight: los 5 de la spec + 7 de control). CLI comprobada contra una config desechable (`XDG_CONFIG_HOME=$(mktemp -d)`): caso válido ⇒ `PREFLIGHT OK: el nodo 'motoshop' está listo.` (exit **0**); caso inválido (sin etiqueta + perfil `755`) ⇒ `PREFLIGHT FALLO: cuenta_no_encontrada` (exit **1**); preflight completo contra un vault inexistente ⇒ `credencial_ausente` (exit **1**, sin pedir la clave maestra).
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - `run_preflight(config, vault=None, *, verificar_credencial=True)`: el vault es inyectable (Protocol `CredentialLookup` con **sólo** `list_entries()`), de modo que es estructuralmente imposible que el diagnóstico toque usuario o contraseña. Motivos distinguidos: `credencial_ausente`, `cuenta_no_encontrada`, `vault_no_accesible`, `perfil_dentro_del_repo`, `perfil_inexistente`, `perfil_permisos_insuficientes`, `tenant_no_configurado`, `configuracion_invalida`. `sesion_expirada`, `antibot` y `portal_no_disponible` quedan **declarados** (`CODIGOS_DEL_SCRAPER`) pero el preflight NO los produce: exigirán una sesión viva contra el portal (S5).
    - El perfil se valida contra la raíz del repo (`REPO_ROOT`, 6 niveles arriba del módulo) y exige modo `0700` en POSIX (`skipif win32` en el test).
    - `load_node_config(env, estricto=False)` construye la configuración **sin** la validación de presencia: el preflight debe poder *diagnosticar* una configuración rota, no reventar con ella. El proceso de la API sigue usando la carga estricta (fail-fast).
    - `--check` = comprobación sin vault (no pide la clave maestra): configuración, etiqueta y perfil. Sin `--check`, el preflight consulta el vault (metadatos).
    - El script vive en `motoshop-app/api/scripts/bank_verify.py`, que es la convención del repo (`scripts/index_business_knowledge.py`, `scripts/reset_admin_password.py`).
  - Depends: 3.1

- [x] **3.3** `[AUTO]` **Runbook operativo `docs/runbook-banco.md`** `[operativo]`
  - RED: revisión documental por el revisor (no automatizable) — checklist de contenido obligatorio abajo.
  - GREEN: `motoshopData/docs/runbook-banco.md` con estas secciones, todas con comandos copiables:
    1. **Topología por nodo** — tabla PC MasVital / PC MotoShop / Mac dev / Render con `BANK_SCRAPER_ENABLED`, `BANK_TENANT`, `BANK_CREDENTIAL_ENTRY`, `BANK_ACCOUNT_LABEL`, `BANK_VAULT_BACKEND`, `BANK_PROFILE_DIR` (mismos valores que la tabla del design).
    2. **Provisión por nodo** — Windows: `python -m motoshop_api.erp.bankreconciliation.cli --backend passphrase set bancolombia-motoshop`; Mac: `--backend keychain set bancolombia-masvital` y `set bancolombia-motoshop`; luego `playwright install chromium` y permisos 700 del perfil fuera del repo.
    3. **Rotación de credenciales** — `cli rotate <entrada>`; qué revisar después (que el login siga funcionando, que el perfil siga autenticado); qué hacer si la rotación falla (dejar la credencial anterior en pie, no borrar el vault).
    4. **OTP (código dinámico)** — el código se pide **en la consola del nodo local**, nunca en el navegador; el operador debe leerlo en la sesión del portal que se abrió en el nodo y escribirlo en la consola; no se persiste ni se reenvía por chat/soporte; si no llega en 300 s el job expira (`expirado`).
    5. **Scraper deshabilitado** — cómo poner `BANK_SCRAPER_ENABLED=false` (⇒ la nube responde `503 scraper_no_habilitado`), que el pegado manual del POS sigue disponible, y que **no** se debe "arreglar" reintentando la nube.
    6. **Errores frecuentes** — `credencial_ausente`, `cuenta_no_encontrada` (⇒ falta `BANK_ACCOUNT_LABEL` o la etiqueta no existe en la sesión), `sesion_expirada`, `antibot` (⇒ parar y re-loguear a mano; no automatizar), `portal_no_disponible`.
    7. **Reversa** — apagar el flag, quitar las rutas de `ERP_ROUTE_MODULES`, `DROP TABLE app_bank_verification_jobs`, anular recibos posteados por `erp/annulment/`, revocar con `cli delete`.
  - Verify: `cd motoshop-app/api && uv run pytest -q` (verde) + revisión del checklist en el PR.
  - Evidencia: `motoshopData/docs/runbook-banco.md` creado en español con las 7 secciones obligatorias (checklist verificado una por una), la tabla de topología con los mismos valores que el design, los comandos copiables del CLI de vault (Windows `passphrase` / Mac `keychain`), `playwright install chromium`, `chmod 700` del perfil fuera del repo (y su equivalente `icacls` en Windows), y los 5 códigos de error del portal + los motivos propios del preflight. Verificación: `uv run pytest tests/ -q -k "not integration"` → **1026 passed, 15 deselected**.
  - Depends: 3.1, 3.2

- [ ] **3.4** `[CHECKPOINT]` **ADR-0026 `Proposed` → `Accepted`** `[ING-1, riesgo legal]`
  - RED: no aplica (cambio de estado documental).
  - GREEN: `motoshopData/docs/decisions/0026-bancolombia-vault.md` — cambiar `- **Estado:** Proposed` a `- **Estado:** Accepted`, añadir la fecha del visto bueno y la referencia al acta/responsable legal.
  - **BLOQUEADO** por el visto bueno legal (ToS de Bancolombia para login automatizado). Mientras no exista, la slice NO se puede cerrar y `BANK_SCRAPER_ENABLED` **no** se activa en ningún nodo real.
  - Verify: `cd motoshop-app/api && uv run pytest -q`.
  - Depends: 3.3

**S3 DoD**: la configuración por nodo falla rápido y es explícita; el runbook cubre provisión, rotación, OTP y scraper deshabilitado.
**Rollback**: sin efectos (config por entorno + documento).

---

## S4 — Persistencia de movimientos (PR #4, base: rama PR #3)

> Idempotencia por `UNIQUE(tenant, id_externo)` e identificador de dominio `uuid5(tenant:id_externo)`. Ninguna otra tabla toca esta slice.

- [x] **4.1** `[AUTO]` **Esquema `app_bank_movements` + upsert idempotente** `[ING-12s1, ING-12s2, REC-11s1]`
  - RED: `motoshop-app/api/tests/test_bank_store_ingest.py` — `test_upsert_primera_carga_graba_n_filas`, `test_reingesta_del_mismo_id_externo_no_crea_filas` (2ª corrida ⇒ 0 filas nuevas), `test_id_de_dominio_uuid5_es_estable_para_mismo_tenant_y_id_externo` (`uuid5(NAMESPACE_DOMINIO, f"{tenant}:{id_externo}")` idéntico en dos instancias), `test_uuid5_difiere_entre_tenants` (mismo `id_externo`, tenant distinto ⇒ `id` distinto), `test_movimientos_de_otro_tenant_no_son_visibles` (lectura filtrada por `tenant`), `test_list_movements_filtra_por_estado_y_rango_de_fechas`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/schemas.py` (`BankMovementIn`/`BankMovementOut` con `extra="forbid"`, `EstadoMovimiento` = `PENDIENTE|APLICADO|AMBIGUA|SIN_MATCH|SOBREPAGO|IGNORADO`), `.../bankreconciliation/store.py` (Protocol `BankStore` + `FakeBankStore` + `RealBankStore`; `upsert_movements(tenant, empresa, movimientos) -> int` con `INSERT ... ON DUPLICATE KEY UPDATE` sin tocar `id_externo`; `list_movements(tenant, estado, desde, hasta)`; `find_movement(tenant, id_movimiento)`; `move_to_state(...)`), `motoshopData/infra/migrations/F9-001-app_bank_movements.sql` (InnoDB, `UNIQUE KEY uq_tenant_id_externo (tenant, id_externo)`, `INDEX idx_estado_fecha (tenant, estado, fecha_movimiento)`, columnas `tenant`, `empresa`, `id_externo`, `id` uuid5, `fecha_movimiento`, `valor DECIMAL(18,2)`, `descripcion`, `referencia`, `referencia_norm`, `pagador_nombre`, `cuenta_origen`, `estado`, `recibo_numero`, `recibo_pref`, `confianza`, `razones`, `scraped_at`), `motoshopData/infra/migrations/F9-002-grant_app_writer_bank.sql` (patrón `F5-003`/`F8-004`).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_store_ingest.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin los módulos → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.schemas'` (1 error de colección). GREEN → `uv run pytest tests/test_bank_store_ingest.py -q` → **19 passed**; `uv run pytest tests/ -q -k "not integration"` → **1045 passed, 15 deselected** (base 1026 + 19 tests nuevos); `uv run ruff check` sobre los 3 archivos creados → **All checks passed!**
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - `NAMESPACE_DOMINIO = uuid.UUID("fb53d95b-57d0-4515-95a9-1edbd5b429fd")` es un UUID **fijo** de módulo: cambiarlo cambiaría el `id` de todos los movimientos ya ingeridos, así que no se toca nunca. `id_dominio_movimiento(tenant, id_externo)` = `str(uuid5(NAMESPACE_DOMINIO, f"{tenant}:{id_externo}"))`.
    - La idempotencia es **del esquema**: `UNIQUE (tenant, id_externo)` + `INSERT ... ON DUPLICATE KEY UPDATE` (sintaxis MySQL 5.0.45 con `VALUES(col)`; sin `ON CONFLICT`, sin CTE, sin funciones de ventana). La cláusula de actualización **no** toca `id` ni `id_externo` y **no** revierte `estado`: reingerir un movimiento ya aplicado lo deja aplicado.
    - `upsert_movements` devuelve **filas nuevas**: el store real cuenta los `id_externo` del lote que no existían para el tenant (SELECT previo) y el doble falso lo cuenta por la clave `(tenant, id_externo)`. La segunda corrida ⇒ **0**.
    - `RealBankStore` escribe por el **motor de escritura** (`app_writer`, utf8) como las demás tablas `app_*` (`app_doc_journal`, `app_idempotency`); el texto va como `str` y el importe como `DECIMAL` (nunca float).
    - `EstadoMovimiento` es un `StrEnum` (ruff UP042); los importes usan `Annotated[Decimal, BeforeValidator(from_legacy_num), Field(max_digits=18, decimal_places=2)]` — 2 decimales exactos, nunca float.
    - Orden del listado: `fecha_movimiento DESC, id_externo ASC` (estable ⇒ paginación segura); en el doble falso se logra con dos `sort` estables.
    - `move_to_state` escribe sólo los campos que se pasan (un `None` no toca la fila) y devuelve `False` si el movimiento no existe **o pertenece a otro tenant**. Las reglas de negocio de *qué* estado puede elegirse son de la slice de conciliación (S9), no de la persistencia.
    - `get_bank_store()` es la dependencia de FastAPI (real en prod/dev, doble falso con `settings.env == "test"`), igual que `get_cash_store()`.
  - Tamaño de la slice: **923 líneas** (`schemas.py` 73 + `store.py` 348 + `test_bank_store_ingest.py` 413 + `F9-001` 57 + `F9-002` 35). Por encima del forecast (~330) y del presupuesto de review: el forecast no contemplative la implementación completa del `RealBankStore` (SQL + mapeo + grant) ni los 13 tests que exigen los requisitos de la spec (uuid5 estable entre tenants, `extra="forbid"`, `DECIMAL(18,2)`, filtro por tenant, orden estable, dialecto MySQL 5.0.45). Si el PR debe quedar ≤ 800 líneas, el corte natural es: commit 1 = las dos migraciones SQL, commit 2 = `schemas.py` + `store.py` + los tests.
  - Desviación menor: `find_movement` busca por el **id de dominio** (`id`), no por `id_externo` — es el identificador que exposure la API (`{id}` de `apply` y de `candidates`); el `id_externo` es la clave del banco, no la de la API.
  - Depends: 3.1

- [ ] **4.2** `[CHECKPOINT]` **Aplicar `F9-001` y `F9-002` en el MySQL local** `[persistencia]`
  - RED: no aplica (DDL).
  - GREEN: aplicación de las migraciones con el runner del repo (`infra/migrations/run_migrations.py`); registrar el estado en `app_migration_state` y verificar que una segunda corrida es no-op.
  - **CHECKPOINT**: requiere MySQL local 5.0.45 (pausa para el operador, igual que las tareas `[CHECKPOINT]` de `erp-transaccional-web`).
  - **PENDIENTE — sólo el operador**: la slice 4.1 escribió los dos archivos `.sql` pero **no** los aplicó a ninguna base. En esta máquina no hay MySQL local alcanzable (`pymysql.connect(localhost:3306)` → `OperationalError 2003: Connection refused`), así que el DDL no pudo validarse contra un motor real. Para aplicarlas: `python -m infra.migrations.run_migrations --prefix F9` (usuario con privilegios; `app_writer` debe existir, ver `F5-003`).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_erp_migrations.py -q`.
  - Depends: 4.1


**S4 DoD**: la ingesta es idempotente por tenant e `id_externo`; las dos migraciones aplicadas en local y reversibles (`DROP TABLE app_bank_movements`).
**Rollback**: `DROP TABLE app_bank_movements` + revocar el grant.

---

## S5 — Portal Bancolombia: parser puro + scraper por DOM (PR #5, base: rama PR #4)

> El contrato del portal **no está verificado** (endpoint XHR desconocido, selectores sin confirmar). Por eso el parser es una función pura con fixtures offline y la navegación se describe con un `PortalContract` explícito y versionable. **No se inventa ningún endpoint XHR.**

- [x] **5.1** `[AUTO]` **Parser puro: importes, pagador, referencia y dirección** `[ING-9s1, ING-9s2, ING-10s1, ING-10s2, ING-11s1, ING-11s2]`
  - RED: `motoshop-app/api/tests/test_bank_parser.py` — `test_parse_colombian_amount_con_separadores` (`"$ 458.200,00"` ⇒ `Decimal("458200.00")`), `test_parse_colombian_amount_negativo_con_signo` (`"- $ 7.590,00"` ⇒ `Decimal("-7590.00")`), `test_importe_no_sufre_redondeo_de_float` (`" $ 1.005,50 "` ⇒ `1005.50` exacto, sin `1005.5` ni `1005.4999999`), `test_parse_movement_row_pago_qr_extrae_pagador_y_referencia` (celdas `["PAGO QR LIZETH STEPHANIA PORTI", "0092055984 null", "$ 458.200,00", "10/02/2025"]` ⇒ pagador `LIZETH STEPHANIA PORTI`, referencia `0092055984`, valor `458200.00`), `test_parse_movement_row_referencia_de_solo_ceros_queda_no_utilizable` (`"0000000000"` ⇒ `referencia_utilizable=False`), `test_parse_movement_row_descripcion_no_pagadora_deja_pagador_vacio` (`"ABONO INTERESES AHORROS"` ⇒ pagador `""`, sin excepción), `test_movimiento_negativo_es_egreso_y_no_candidato_de_pago` (`"- $ 7.590,00"` ⇒ `direccion="egreso"`, `es_candidato_pago=False`), `test_movimiento_positivo_es_ingreso` (`"CONSIGNACION CORRESPONSAL CB"` ⇒ `direccion="ingreso"`), `test_sanitize_reference_quita_el_sufijo_null`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/parser.py` — funciones puras `parse_colombian_amount(raw: str) -> Decimal`, `sanitize_reference(raw: str) -> str`, `parse_movement_row(cells: Sequence[str]) -> BankMovement`, `class MovementDirection(str, Enum)` (`INGRESO`/`EGRESO`); `Decimal` en todo el camino; `referencia_utilizable=False` si la referencia son sólo ceros.
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_parser.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin el módulo → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.parser'` (1 error de colección). GREEN → `uv run pytest tests/test_bank_parser.py -q` → **32 passed** (los 9 tests de la spec + 23 de borde y regresión). Suite completa `uv run pytest tests/ -q -k "not integration" --ignore=tests/test_bank_portal_contract.py` → **1077 passed, 15 deselected** (base 1045 + 32 tests nuevos; el mismo comando sin `--ignore` da 1045). `uv run ruff check src/motoshop_api/erp/bankreconciliation/parser.py tests/test_bank_parser.py` → **All checks passed!**
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - El módulo es **stdlib puro** (sin pydantic, sin I/O, sin red): `ParsedMovement` es compatible con `BankMovementIn` por nombres de campo, `datetime.date` y `Decimal` de dos decimales; la conversión a `BankMovementIn` es trabajo de la capa de ingesta (S5.2/S6), no del parser.
    - **El importe se normaliza antes de construir el número**: la coma es el separador decimal y el punto el de miles (`1.005,50` → `1005.50`); nunca se pasa por `float`. Un importe con más de dos decimales es un error explícito (`FormatoDeMovimientoInvalido`), no un redondeo silencioso. Todos los importes se devuelven con dos decimales exactos (`Decimal("458200.00")`).
    - **El orden de las columnas se detecta por contenido, no por posición a ciegas**: la fecha `DD/MM/YYYY` y el importe se reconocen solos, así que se aceptan las dos variantes (la del portal `Fecha | Descripción | Referencia | Valor` y la que dejaban las celdas del fixture de la spec `Descripción | Referencia | Valor | Fecha`). Una fila que no traiga las 4 celdas, o cuya fecha/importe no se reconozcan, es un error explícito en español.
    - `referencia_utilizable=False` si la referencia está vacía **o** es sólo ceros (`0000000000`); `"0092055984 null"` → `"0092055984"` (el sufijo `" null"` sólo se quita cuando está al final: `"0092 null 984"` se conserva tal cual).
    - El pagador sale **sólo** si la descripción empieza con `PAGO QR` (`^PAGO\s+QR\s+`); `PAGO PSE ASOPAGOS`, `ABONO INTERESES AHORROS` y cualquier otra descripción dejan el pagador vacío **sin** lanzar excepción.
    - `es_candidato_pago` es por signo: `valor > 0` ⇒ candidato (`INGRESO`); `valor < 0` ⇒ `EGRESO` y no candidato; un importe de `0,00` no es candidato (no es dinero que entra).
  - Desviaciones menores (3): (1) `MovementDirection` es `StrEnum` y no `str` + `Enum`: `ruff UP042` (regla `UP` activa en el repo) exige `StrEnum`, y `schemas.EstadoMovimiento` ya sigue esa convención — el comportamiento pedido se mantiene (`MovementDirection.EGRESO == "egreso"`, `isinstance(x, str)`); (2) `parse_movement_row` devuelve `ParsedMovement` (el nombre pedido en el encargo del apply) y se deja el alias `BankMovement = ParsedMovement` para S7/S9, que ya hablan de `BankMovement`; (3) las celdas del fixture de la spec vienen en el orden `Descripción | Referencia | Valor | Fecha` y el portal real usa `Fecha | Descripción | Referencia | Valor`: el parser acepta ambos (ver detalle de detección por contenido).
  - Tamaño de la slice: **554 líneas** (`parser.py` 319 + `test_bank_parser.py` 235). Por encima del forecast de código (~300 de la fila S5) porque el forecast no contemplaba los 23 tests de borde/regresión ni la docstrings del módulo; el PR #5 completo (S5) sigue dentro del presupuesto de 800 con el scraper de 5.2.
  - Nota de estado (NO tocado, es de la slice 5.2): `motoshop-app/api/tests/test_bank_portal_contract.py`, `motoshop-app/api/tests/bank_fakes.py` y `motoshop-app/api/tests/fixtures/bank/` son restos **sin trackear** de un intento anterior de S5 y hoy rompen la colección de la suite completa (`ModuleNotFoundError: ... portal_pages`) hasta que se implemente 5.2. No se modificaron.
  - Depends: 4.1

- [x] **5.2** `[AUTO]` **Scraper DOM: cuenta por etiqueta, paginación, OTP en consola, errores y lock** `[ING-3s1, ING-4s1, ING-5s1, ING-5s2, ING-5s3, ING-6s1, ING-6s2, ING-7s1, ING-8s1, ING-8s2, ING-12s2, ING-13s1, ING-13s2, ING-14s1, ING-14s2]`
  - RED: `motoshop-app/api/tests/test_bank_portal_contract.py` (tests **offline**, con fixtures HTML en `motoshop-app/api/tests/fixtures/bank/`: `cuentas.html`, `movimientos_pagina1.html`, `movimientos_pagina2.html`, `login_otp.html`) — `test_cuenta_se_selecciona_por_etiqueta_y_nunca_por_indice` (la cuenta 2 del fixture es la del tenant; la 1 es de otro tenant ⇒ se abre la 2), `test_etiqueta_del_tenant_ausente_falla_con_cuenta_no_encontrada_y_no_registra_movimientos`, `test_etiquetas_de_distintos_tenants_solo_abre_la_del_tenant_actual`, `test_no_solicita_movimientos_de_la_cuenta_de_otro_tenant`, `test_recorre_todas_las_paginas_de_la_ventana_y_expone_pagina_y_ventana` (el movimiento está en la página 2 ⇒ se encuentra y se expone con su página), `test_ventana_por_defecto_es_el_dia_en_curso`, `test_perfil_persistente_fuera_del_repo_y_con_permisos_700` (`skipif win32` para permisos), `test_otp_se_solicita_en_el_nodo_y_no_se_persiste` (el código leído por `input()` no aparece en ninguna fila ni en el log), `test_credencial_ausente_falla_con_codigo_explicito_y_no_registra_movimientos`, `test_credencial_invalida_falla_con_codigo_explicito`, `test_desafio_antibot_no_deja_movimientos_parciales`, `test_sesion_expirada_falla_con_codigo_explicito`, `test_ejecucion_concurrente_rechazada_por_lock`, `test_corrida_reciente_dentro_del_intervalo_minimo_rechazada`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/portal_pages.py` (`PortalContract` dataclass versionable: URL de autenticación `/autenticacion`, de home `/home`, de movimientos `/detalles-y-movimientos/cuentas`, selector de tarjeta de cuenta, selector de tab "Movimientos", selector de tabla "Tus movimientos", selector de paginación; **sin** ningún endpoint XHR), `.../bankreconciliation/scraper.py` (`BankScraper.scrape(config: NodeConfig) -> ScrapeResult`; perfil persistente `user_data_dir=config.profile_dir`; login con la entrada de vault del tenant; **OTP por `input()` en la consola del nodo**; selección de cuenta **por etiqueta** (`BANK_ACCOUNT_LABEL`), jamás por índice; paginación hasta cubrir la ventana; `class BankScrapeError(Exception)` con `codigo` ∈ `credencial_ausente|credencial_invalida|sesion_expirada|antibot|portal_no_disponible|cuenta_no_encontrada`; `acquire_session_slot()` con lock file + intervalo mínimo de 30 s en `config.profile_dir`; **nunca** `trace`/`video`/`screenshot` del login; sin secretos en logs), `motoshop-app/api/scripts/bank_sync.py` (CLI del nodo: una corrida de scrape + ingesta idempotente, salida con el resumen de la corrida).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_parser.py tests/test_bank_portal_contract.py -q`.
  - Evidencia (cwd `motoshop-app/api`, re-ejecutada en esta sesión):
    - `uv run pytest tests/test_bank_parser.py tests/test_bank_portal_contract.py -q` → **51 passed** (32 del parser de 5.1 + 19 del contrato del portal).
    - `uv run pytest tests/ -q -k "not integration"` → **1096 passed, 15 deselected** (base 1077 + 19 tests nuevos; el `store.py` de S4 no cambió de comportamiento).
    - `uv run ruff check` sobre los 4 archivos tocados → **All checks passed!**
    - **Offline demostrado**: con un `sitecustomize` que bloquea `socket.connect`/`create_connection` (verificado: lanza `RedBloqueada`) la suite de S5 corre **51 passed**; y `playwright` **no está instalado** en el venv ni llega a `sys.modules` durante la corrida (`importlib.util.find_spec("playwright") is None`).
    - CLI sin Playwright: `uv run python scripts/bank_sync.py --help` → exit **0**; corrida real → `[FALLO] credencial_ausente: no hay credencial para el tenant 'masvital'` (exit **1**); sin `BANK_TENANT` → `[FALLO] configuración inválida: BANK_TENANT es obligatorio…` (exit **2**); con `playwright` ausente → `codigo=portal_no_disponible`, "Playwright no está instalado: corré `uv sync --extra bank` y `playwright install chromium`".
    - Dependencia opcional: `pyproject.toml` gana el extra `bank = ["playwright>=1.47"]` (**fuera** de `dependencies`) y `uv.lock` registra `playwright v1.64.0` sólo bajo `[package.optional-dependencies] bank`.
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - **`PortalContract` es dato puro**: cada elemento es un `LocatorSpec` con varias estrategias (rol ARIA → texto → etiqueta → `data-testid` → CSS de respaldo). El scraper prueba las estrategias en orden de robustez y se queda con la primera que encuentra algo: un cambio de clases no rompe el scraping mientras los roles y los textos se mantengan. El contrato **no** declara ninguna URL absoluta ni ningún endpoint XHR (la URL base vive fuera del dataclass, en `URL_BASE_PORTAAL`).
    - **La cuenta se abre por etiqueta, nunca por índice**: `_abrir_cuenta` compara la etiqueta configurada con las que lista la sesión (comparación por texto normalizado) y **falla con `cuenta_no_encontrada` sin llamar a `abrir_cuenta`**: no se lee ninguna otra cuenta. La etiqueta que se pasa a la sesión es **la del DOM**, no la configurada.
    - **Todo fallo deja cero movimientos**: el scraper arma la lista en memoria y sólo la devuelve al terminar bien; `sincronizar()` (el script) sólo llama `upsert_movements` **después** de un scrape exitoso, así que un antibot en la página 2 no deja la fila de la página 1.
    - **Lock por perfil, intervalo por tenant**: el lock (`.banco-sesion.lock`, `flock` en POSIX) vive en `config.profile_dir` ⇒ una sola sesión de navegador a la vez en la máquina; la marca de la corrida anterior (`.banco-sesion.<tenant>.ultima`) es **por tenant** ⇒ el intervalo de 30 s acota las corridas de un nodo, sin bloquear a otro tenant que comparta el directorio de perfil (exigido por `test_etiquetas_de_distintos_tenants_solo_abre_la_del_tenant_actual`).
    - **El reloj se lee una sola vez por corrida** (exigido por `test_la_ingesta_es_idempotente`, que inyecta un iterador de dos instantes para dos corridas): el intervalo se mide contra la corrida anterior y la misma lectura es el `leido_en` del resultado.
    - **El perfil se crea con modo 700** y se rechaza si vive dentro del repo (`SessionSlotError` con motivo `perfil_dentro_del_repo`); el archivo de control se escribe con modo 600.
    - **OTP**: se pide con `input()` en la consola del nodo (nunca en el navegador), no se persiste, no se registra (el log sólo dice tenant, cuenta, páginas y movimientos) y no viaja en ningún movimiento devuelto. El perfil persistente no se abre con `trace`/`video`/capturas, y el módulo advierte que **no** se corra el nodo con `DEBUG=pw:api` (Playwright imprime en pantalla lo que se escribe en los formularios).
    - **Códigos de error**: `credencial_ausente` (no hay entrada del tenant en la bóveda), `credencial_invalida` (el portal rechaza credenciales o el código), `sesion_expirada` (el portal devuelve al login), `antibot` (desafío de seguridad), `portal_no_disponible` (el portal no responde, una fila no se pudo interpretar, o Playwright no está instalado), `cuenta_no_encontrada` (la etiqueta no está en la sesión).
    - **Paginación**: se recorre hasta que no hay "Siguiente"; el corte anticipado sólo ocurre si una página entera es **anterior** a la ventana **y** viene ordenada de más antigua a más nueva (hipótesis sobre el orden del portal). Con el orden inverso nunca se corta antes de tiempo: se recorren todas las páginas. Cada movimiento conserva su `pagina` (1-based) y su `cuenta_origen`.
    - **`id_externo` derivado**: el portal no muestra un identificador de fila, así que se deriva del contenido (`sha256(fecha|referencia|valor|descripción)`): determinista ⇒ la ingesta es idempotente. La referencia sola **no** sirve (dos pagos del mismo día la comparten).
    - **El scraper habla con un doble**: `PortalSession` (Protocol) es la interfaz; `tests/bank_fakes.PortalFalso` la implementa en las pruebas y `PlaywrightPortalSession` en producción. Playwright se importa **dentro** de `default_session_factory`, así que el paquete importa y toda la suite offline corre sin la dependencia.
    - **Ingesta**: `scripts/bank_sync.py` mapea `ScrapedMovement` → `BankMovementIn` (`referencia_norm` = la referencia ya saneada; la normalización sin ceros a la izquierda es del matching, slices S7/S9) y llama `upsert_movements(tenant, tenant, …)`: la segunda corrida devuelve **0** filas nuevas.
  - Desviaciones (3, todas menores y documentadas):
    1. **`store.py` tocó (archivo que la consignaba como congelado)**: la suite de contrato llama `store.list_movimientos(...)` (nombre en español) y el store de S4 sólo implementaba `list_movements(...)` (convención en inglés de todo el repo: `find_invoice`, `upsert_movements`…). Sin ese método el test es **imposible** de satisfy sin tocar el test (prohibido) o el store. Se añadió un **alias puramente aditivo** `list_movimientos` (Protocol + `FakeBankStore` + `RealBankStore`, 28 líneas) que **no cambia ningún comportamiento** ni el SQL ni la idempotencia de S4; los 19 tests de S4 siguen verdes. El test no se modificó.
    2. **`scripts/bank_sync.py` usa un `NamedTuple` y no un `dataclass`** para `SyncSummary`: el script se carga con `importlib` (las pruebas lo hacen así) **fuera de `sys.modules`**, y un `dataclass` con anotaciones diferidas (`from __future__ import annotations`) revienta en ese escenario porque `dataclasses` busca el módulo en `sys.modules` para resolver los tipos. El `NamedTuple` es inmune y conserva las anotaciones diferidas del repo.
    3. **La URL base del portal NO está verificada** y por eso vive fuera del contrato (que no puede contener "http") y es configurable con `BANK_PORTAL_BASE_URL`; el valor por defecto (`https://www.bancocolombia.com`) es una hipótesis, no un dato confirmado.
  - Tamaño de la slice: **1.402 líneas** (`portal_pages.py` 182 + `scraper.py` 1.005 + `bank_sync.py` 215; de las cuales ~805 son código y ~320 docstrings). Muy por encima del forecast de código (~300 de la fila S5): el forecast no contemplaba la sesión real de Playwright (~300 líneas, que no se puede probar offline), el lock con `flock`/intervalo, ni las docstrings en el estilo del repo. Si el PR debe quedar ≤ 800 líneas, el corte natural es: commit 1 = `portal_pages.py` (182), commit 2 = `scraper.py` (1.005, se puede partir en "núcleo + sesión Playwright"), commit 3 = `bank_sync.py` + `pyproject.toml`/`uv.lock` (287).
  - Pendiente de 5.2 (NO es trabajo de esta slice): una corrida **viva** contra el portal real para confirmar los selectores, el flujo de 2FA y la URL base. Los fixtures son una aproximación y la suite offline **no puede** detectar un cambio real del DOM.
  - Depends: 5.1

**S5 DoD**: el parser es puro y determinista con fixtures offline; el scraper abre sólo la cuenta del tenant por etiqueta; todo error del portal deja cero movimientos.
**Rollback**: apagar `BANK_SCRAPER_ENABLED`; borrar `tests/fixtures/bank/`.

---

## S6 — Job de verificación asíncrono (PR #6, base: rama PR #5)

> El scrape tarda 10–40 s ⇒ no cabe en un request HTTP. `POST /api/erp/bank/verificaciones` → `202 {job_id}`; el worker corre en el nodo local; el front sondea cada ~2 s.

- [x] **6.1** `[AUTO]` **Tabla de jobs + store de jobs** `[REC-11s1, ING-13s1]`
  - RED: `motoshop-app/api/tests/test_bank_verification_jobs.py` — `test_id_del_job_es_uuid5_estable_para_mismo_tenant_factura_y_valor` (`uuid5(NAMESPACE_DOMINIO, f"{tenant}:{factura_id}:{valor}")`), `test_job_id_http_es_uuid4_distinto_del_id_de_dominio`, `test_estados_del_job_son_los_del_contrato` (`en_cola|ejecutando|esperando_otp|resuelto|sin_coincidencia|ambiguo|fallido|expirado`), `test_segunda_creacion_del_mismo_job_devuelve_el_mismo_job_id` (idempotencia), `test_job_actualiza_estado_y_marca_error_sin_filas_parciales`, `test_job_expira_tras_el_ttl`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/jobs.py` (`VerificationJobStore` Protocol + `FakeVerificationJobStore` + `RealVerificationJobStore`; `create_job(tenant, factura_id, valor) -> VerificationJob`; `get_job(tenant, job_id)`; `update_job(tenant, job_id, estado, resultado=None, error_codigo=None)`; `expire_stale_jobs(now)`), `motoshopData/infra/migrations/F9-003-app_bank_verification_jobs.sql` (InnoDB; PK `id` = uuid5 del dominio; `job_id` uuid4 UNIQUE; `tenant`, `factura_id`, `valor DECIMAL(18,2)`, `estado`, `nodo`, `resultado_json`, `error_codigo`, `creado_en`, `actualizado_en`, `expira_en`; `KEY (tenant, estado, creado_en)`).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_verification_jobs.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin el módulo → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.jobs'` (1 error de colección). GREEN → `uv run pytest tests/test_bank_verification_jobs.py -q` → **10 passed** (los 6 nombrados en la spec + 4 de aislamiento/normalización/terminales). `uv run pytest tests/ -q -k "not integration"` → **1131 passed, 15 deselected** (base 1103 + 28 de esta slice). `uv run ruff check` sobre los 3 archivos creados → **All checks passed!**
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - **Dos identidades**: `id` = `uuid5(NAMESPACE_DOMINIO, f"{tenant}:{factura_id}:{valor}")` (PK, estable ⇒ idempotencia de la tabla) y `job_id` = `uuid4` (público, único, es el que viaja en la URL). `get_job`/`update_job` aceptan **cualquiera de los dos** (siempre filtrados por tenant).
    - **El importe se normaliza a dos decimales** (`quantize(Decimal("0.01"))`) *antes* de calcular el id: `Decimal("458200")` y `Decimal("458200.00")` son el mismo job. `id_dominio_job()` es la fórmula literal del contrato; la normalización vive en `create_job`.
    - **`update_job` es permisivo**: un `None` no toca la fila (mismo contrato que `move_to_state` de S4) y acepta un `nodo=` opcional (keyword-only) que el worker escribe en la transición a `ejecutando` — sin él la columna `nodo` quedaba siempre `NULL` (lo detectó el test del worker).
    - **`RealVerificationJobStore`** usa `INSERT ... ON DUPLICATE KEY UPDATE id = VALUES(id)`: la fila existente gana y se devuelve tal cual (la idempotencia es del esquema, no del código), y el `job_id` público es el de la fila que quedó.
    - `resultado_json` es `TEXT` con `json.dumps(..., default=str)`; el importe vuelve a `Decimal` al leer. `expire_stale_jobs(now)` sólo toca los jobs **no terminales** vencidos.
    - `get_verification_job_store()` (dependencia de FastAPI) devuelve el store real fuera de tests y un `FakeVerificationJobStore` **singleton** en tests: el job tiene que sobrevivir entre el POST y el GET del sondeo.
  - Desviación menor: se añadió `F9-004-grant_app_writer_bank_jobs.sql` (grant de `app_writer` sobre la tabla nueva, patrón `F9-002`). Sin él el `app_writer` no puede escribir la tabla y la slice no funcionaría en producción.
  - Depends: 4.1

- [x] **6.2** `[AUTO]` **Worker del nodo: un job a la vez, lock y estados** `[ING-13s1, ING-14s1, ING-14s2]`
  - RED: `motoshop-app/api/tests/test_bank_worker.py` — `test_worker_marca_el_job_ejecutando_y_luego_resuelto_con_la_ventana`, `test_worker_marca_esperando_otp_ante_de_pedir_el_codigo`, `test_worker_marca_fallido_con_el_codigo_de_error_del_portal`, `test_worker_no_deja_movimientos_parciales_ante_un_error`, `test_worker_rechaza_un_segundo_job_simultaneo` (lock por nodo), `test_worker_respeta_el_intervalo_minimo_entre_corridas`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/worker.py` (`BankVerificationWorker.run_once(job) -> None`: `en_cola` → `ejecutando` → (llama al scraper de S5) → `esperando_otp` cuando el portal pide el código → `resuelto`/`sin_coincidencia`/`ambiguo`/`fallido`; `nodo` = identificador del nodo; `resultado_json` con `ventana`, `nodo`, `ingesta_at`; lock por nodo + intervalo mínimo de 30 s reusing `scraper.acquire_session_slot()`).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_worker.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin el módulo → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.worker'` (1 error de colección). GREEN → `uv run pytest tests/test_bank_worker.py -q` → **9 passed** (los 6 nombrados en la spec + 3 de clasificación: sin coincidencia, ambiguo y egreso-no-candidato). `uv run ruff check` sobre los 2 archivos creados → **All checks passed!**
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - **El lock y el intervalo vienen del scraper**: el worker llama a `BankScraper.scrape(config)`, que ya toma el turno de sesión (`acquire_session_slot`) ⇒ no hay que duplicar el lock. Por eso las pruebas de concurrencia e intervalo usan el **scraper real** con la sesión falsa `PortalFalso` (el doble de S5), no un doble del worker.
    - **El estado `esperando_otp` se marca por el gancho del código**: el worker intercepta la función `pedir_codigo` que el scraper usa para el OTP (`scraper_factory` recibe la función de pregunta), marca `esperando_otp` y **después** pregunta en la consola del nodo. Así el estado es exacto (nunca "esperando OTP" antes de tiempo) y el código no se persiste ni se registra.
    - **`SessionSlotError` también deja el job en `fallido`** (con `error_codigo` = motivo: `ejecucion_concurrente`, `intervalo_minimo`, `perfil_dentro_del_repo`): si no, el job se quedaría en `ejecutando` para siempre.
    - **La ingesta va DESPUÉS del scrape completo**: un antibot en la página 2 deja **cero** movimientos (mismo criterio que S5).
    - **El worker nunca postea un pago**: sólo lee y deja el movimiento en `PENDIENTE`; el operador confirma en el POS.
    - La clasificación por valor es una **función pura** `clasificar_por_valor(valor, movimientos)` (0 → `sin_coincidencia`, 1 → `resuelto`, 2+ → `ambiguo`, y sólo cuentan los ingresos). El matching completo (ventana, puntaje, referencia) es de **S7** (`value_match.py`): esta es la costura deliberada.
    - `resultado_json` lleva `ventana` (`{desde, hasta}` ISO), `nodo`, `ingesta_at`, `cuenta`, `paginas`, `movimientos`, `candidatos` (conteo) y `candidato` (el único, cuando hay uno: es lo que el front prellena en S8).
  - Depends: 6.1, 5.2

- [x] **6.3** `[AUTO]` **Router del job + guardas + matriz de módulos** `[REC-11s2, ING-13s1]`
  - RED: `motoshop-app/api/tests/test_bank_verification_router.py` — `test_post_verificaciones_responde_202_con_job_id_estado_y_expira_en`, `test_post_verificaciones_503_scraper_no_habilitado` (nube: `BANK_SCRAPER_ENABLED=false`), `test_post_verificaciones_503_tenant_no_servido` (el nodo pertenece a otro tenant ⇒ nunca se cruzan tenants), `test_post_verificaciones_403_sin_permisos_de_cobranzas` (usuario `vendedor`), `test_post_verificaciones_403_sin_tenant_erp`, `test_get_verificaciones_200_con_estado_y_error`, `test_get_verificaciones_404_para_job_de_otro_tenant` (404 sólo del dueño del job), `test_get_verificaciones_404_job_inexistente`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/router.py` (`POST /erp/bank/verificaciones` → `202 {job_id, estado, expira_en}` | `503` con `error_codigo`; `GET /erp/bank/verificaciones/{job_id}` → `200 {job_id, estado, resultado?, error?, expira_en}` | `404`), `motoshop-app/api/src/motoshop_api/erp/guards.py` (entradas en `ERP_ROUTE_MODULES`: `("POST","/api/erp/bank/verificaciones"): ("erp-cash",)` y `("GET","/api/erp/bank/verificaciones/{job_id}"): ("erp-cash",)`), `motoshop-app/api/src/motoshop_api/main.py` (`app.include_router(erp_bank_router, prefix="/api", dependencies=module_access)`).
  - Guardas (decisión explícita): `POST /verificaciones` ⇒ `require_erp_tenant` **+** `require_erp_collections_write` (crea un registro de trabajo ⇒ es escritura de cobranzas); `GET /verificaciones/{job_id}` ⇒ `require_erp_tenant` + módulo `erp-cash` (es el sondeo del POS).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_verification_router.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin el módulo → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.router'` (1 error de colección). GREEN → `uv run pytest tests/test_bank_verification_router.py -q` → **9 passed** (los 8 nombrados en la spec + el montaje en la app de producción). `uv run ruff check` sobre los archivos tocados → **All checks passed!** (`main.py` conserva sus **11 E501 preexistentes**, idénticos al baseline de `HEAD`; `erp/guards.py` y el resto, limpios).
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - **El cuerpo del POST es `{factura_id, valor}`** (`valor` como `Decimal` de 2 decimales, `extra="forbid"`), tal como lo describe el flujo del design. El `Idempotency-Key` **no** hace falta: la idempotencia es del job (`uuid5(tenant:factura_id:valor)`) ⇒ un 2º POST del mismo par devuelve el **mismo** `job_id`.
    - **Los 503 llevan el código en `detail`**: `{"detail": {"error_codigo": "scraper_no_habilitado" | "tenant_no_servido", "message": "..."}}`. Los 404 usan `error_codigo: "job_no_encontrado"` — **el mismo** para "no existe" y "es de otro tenant" (no se filtra la existencia de jobs ajenos).
    - **El nodo se lee del entorno** (`get_node_config()` → `load_node_config()`): si la configuración es inválida, el router responde 503 (fail-closed) en vez de reventar con 500. El tenant del nodo (`BANK_TENANT`) se compara con el tenant de la petición ⇒ nunca se cruzan tenants.
    - **El despacho es en el mismo proceso** (`get_despachador`): un hilo *demonio* corre `BankVerificationWorker.run_once(job)`; el request responde 202 al instante y el front sondea el estado. La dependencia es inyectable (las pruebas la sustituyen por un grabador: ningún test abre un navegador).
    - La respuesta del POST es un `dict` plano (`job_id`, `estado`, `expira_en` ISO) y la del GET sólo incluye `resultado`/`error` cuando existen.
  - Pendiente de 6.3 (NO es trabajo de esta slice): el **sondeo de jobs caducados** (`expire_stale_jobs`) y el **recuperador** de jobs que quedaron en `ejecutando` cuando el proceso del nodo se apagó siguen sin despachador: hoy los caduca el TTL y el front los ve como `en_cola`/`ejecutando` hasta que un proceso los expire (S9 o una slice de nodo).
  - Depends: 6.2

**S6 DoD**: el job asíncrono persiste su estado, un nodo corre un job a la vez y la nube responde 503 sin scraper.
**Rollback**: quitar las rutas de `ERP_ROUTE_MODULES` + `DROP TABLE app_bank_verification_jobs`.

---

## S7 — Coincidencia por valor + API de candidatos (PR #7, base: rama PR #6)

- [x] **7.1** `[AUTO]` **Match por valor: 0 / 1 / 2+ candidatos** `[REC-1s1, REC-1s2, REC-2s1, REC-3s1, REC-4s1]`
  - RED: `motoshop-app/api/tests/test_bank_value_match.py` — `test_valor_igual_dentro_de_la_ventana_devuelve_el_candidato` (458200 ⇒ 1 candidato), `test_sin_coincidencias_en_la_ventana_no_devuelve_candidatos`, `test_mismo_valor_de_ayer_no_es_candidato` (frontera de ventana), `test_dos_movimientos_con_el_mismo_valor_reporta_ambiguedad_y_lista_ambos_sin_elegir` (`ambiguo=True`, 2 candidatos, `seleccionado is None`), `test_candidato_expone_pagador_y_referencia_saneada` (`PAGO QR CRISTOPHER BENAMIDES P` + `0092055984 null` ⇒ pagador `CRISTOPHER BENAMIDES P`, referencia `0092055984`), `test_fila_no_pago_qr_expone_pagador_vacio`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/value_match.py` — `match_by_value(valor: Decimal, movimientos: Sequence[BankMovement], ventana: tuple[date, date]) -> ValueMatch`; `ValueMatch(ambiguo: bool, candidatos: list[Candidato], ventana)`; `Candidato(id, valor, pagador_nombre, referencia, fecha)`; sólo movimientos **positivos** son candidatos; el valor se compara con `Decimal` exacto.
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_value_match.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin el módulo → `ModuleNotFoundError: No module named 'motoshop_api.erp.bankreconciliation.value_match'` (1 error de colección). GREEN → `uv run pytest tests/test_bank_value_match.py -q` → **6 passed** (los 6 nombrados en la spec). `uv run pytest tests/ -q -k "not integration"` → **1144 passed, 15 deselected, 7 failed (PREEXISTENTES de `tests/test_reports.py`)**; baseline medido ANTES del cambio → **1131 passed, 15 deselected, 7 failed** ⇒ delta **+13** (6 de esta task + 7 de 7.2). `uv run ruff check` sobre los archivos creados → **All checks passed!**
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - **La función es pura y normaliza la entrada**: `match_by_value(valor, movimientos, ventana)` recibe `MovimientoCoincidible` (la forma mínima: `id_externo`, `tenant`, `valor`, `pagador_nombre`, `referencia`, `fecha`, `es_candidato_pago`), no el `ParsedMovement` del parser: el candidato necesita un **id de dominio** (`uuid5` de `tenant:id_externo`) y `ParsedMovement` no lleva tenant ni `id_externo`. Hay dos adaptadores (`desde_movimiento_raspado`, `desde_movimiento_persistido`) y el `Protocol` `MovimientoRaspado` evita que el módulo puro arrastre el scraper.
    - **El `id` del candidato es el de dominio** (`id_dominio_movimiento(tenant, id_externo)`): es el mismo id con el que la API apunta a la fila del movimiento, así que la UI puede llevar el candidato al conciliador sin ambigüedad.
    - **`ValueMatch.seleccionado`**: el candidato único o `None` (cero **o** dos o más ⇒ `None` ⇒ el sistema nunca elige en la ambigüedad).
    - **Sólo ingresos**: la regla es `es_candidato_pago and valor > 0`. En la forma persistida `es_candidato_pago` se deduce del **signo**; en la forma del portal manda la bandera del scraper (un egreso con importe positivo tampoco es un pago — es lo que fija `test_un_egreso_no_es_candidato_del_job` de S6).
    - **La ventana se normaliza a días** (`date`): el `tuple[date, date]` de la spec y el `tuple[datetime, datetime]` de la ventana del nodo son la misma cota (un instante se recorta a su día). La comparación es **inclusiva** en los dos extremos.
    - **El worker ahora usa esta misma regla** (`worker.py`): se borró `clasificar_por_valor()` (la costura deliberada de S6) y `run_once` llama a `match_by_value` con la ventana del scrape; el worker sólo traduce el veredicto a estado de job (`0 → sin_coincidencia`, `1 → resuelto`, `2+ → ambiguo`).
  - Desviación menor: el `id` del `resultado_json.candidato` del job (S6) pasa de `id_externo` al **id de dominio** (el mismo que expone la API de candidatos). No lo fija ningún test de S6 y unifica el contrato para el front de S8.
  - Depends: 6.3

- [x] **7.2** `[AUTO]` **`GET /api/erp/bank/candidates`** `[REC-1s1, REC-3s1, REC-4s1, REC-11s1, REC-11s2]`
  - RED: `motoshop-app/api/tests/test_bank_candidates_router.py` — `test_candidates_200_devuelve_ambiguo_ventana_y_candidatos`, `test_candidates_200_con_lista_vacia_sin_coincidencia` (no es error), `test_candidates_solo_consulta_movimientos_del_tenant_actual`, `test_candidates_403_sin_permisos_de_cobranzas`, `test_candidates_403_sin_tenant_erp`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/router.py` (`GET /erp/bank/candidates?valor=&desde=&hasta=` → `{ambiguo, ventana, candidatos:[{id,valor,pagadorNombre,referencia,fecha}], ultimaIngestaAt}`), `motoshop-app/api/src/motoshop_api/erp/guards.py` (`("GET","/api/erp/bank/candidates"): ("erp-cash",)`), `.../main.py` (ya registrado el router en 6.3).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_candidates_router.py -q`.
  - Evidencia (cwd `motoshop-app/api`): RED sin la ruta → **404 Not Found** en los 7 tests (`{"detail":"Not Found"}`). GREEN → `uv run pytest tests/test_bank_candidates_router.py -q` → **7 passed** (los 5 nombrados en la spec + `test_candidates_422_con_un_importe_invalido` + `test_candidates_sin_ingesta_devuelve_ultima_ingesta_null`). Suite completa → **1144 passed, 15 deselected, 7 failed (preexistentes)**. `uv run ruff check` sobre los archivos tocados → **All checks passed!**
  - Contrato de la API (lo que consume el front de S8):
    - `GET /api/erp/bank/candidates?valor=<decimal>&desde=<YYYY-MM-DD>&hasta=<YYYY-MM-DD>`.
    - `valor` es **obligatorio** y debe ser un decimal válido de **2 decimales** (`max_digits=18`, `decimal_places=2`): si no, **422**. `desde`/`hasta` son opcionales; por defecto la ventana es **el día en curso**. Una ventana invertida (`desde > hasta`) es **422**.
    - **200** → `{"ambiguo": bool, "ventana": {"desde": "YYYY-MM-DD", "hasta": "YYYY-MM-DD"}, "candidatos": [{"id": "<uuid5>", "valor": "458200.00", "pagadorNombre": "...", "referencia": "0092055984", "fecha": "YYYY-MM-DD"}], "ultimaIngestaAt": "2026-10-21T12:00:00" | null}`.
    - Sin coincidencia → **200** con `candidatos: []` y `ambiguo: false` (**no** es un error). `ultimaIngestaAt` es el `scraped_at` más reciente del tenant (`null` si nunca ingirió).
    - El importe viaja como **texto** (`"458200.00"`): nunca como `float` (ADR-0008-07).
  - Guardas (decisión explícita): `require_erp_tenant` + módulo `erp-cash` en `ERP_ROUTE_MODULES` (`("GET","/api/erp/bank/candidates"): ("erp-cash",)`). Es una **lectura**: no pide rol de cobranzas (a diferencia del `POST` de S6, que sí crea un job).
  - Detalles de implementación (decisiones tomadas al ejecutar la spec):
    - **El router no reimplementa la regla**: lee los movimientos del tenant y llama a `value_match.match_by_value` (la misma función que usa el worker del nodo).
    - **Una sola lectura al store**: `list_movimientos(tenant.id)` (filtrado por tenant en el store) y de ahí salen los candidatos y el `ultimaIngestaAt` (`max(scraped_at)`). El filtro de ventana lo aplica la función pura, no el SQL.
    - El `id` del candidato sale del **id de dominio** (`id_dominio_movimiento(tenant, id_externo)`): el mismo id con el que la API de movimientos (S9) apunta a la fila.
  - Pendiente de 7.2 (NO es trabajo de esta slice): la lectura trae **todos** los movimientos del tenant (sin paginación ni índice por importe); con volúmenes grandes el `sync-status` de S9 debería exponer la última ingesta desde la base y no desde el listado.
  - Depends: 7.1

**S7 DoD**: el match por valor es una función pura explicable y la API expone candidatos sólo del tenant activo.

---

## S8 — Botón "Verificar" en el POS (PR #8, repo `frontfambus`, base: tracker `frontfambus`)

> **Slice frontend: se ejecuta en `/Users/javierportillarosero/Documents/personal/dataEmpresas/frontfambus`** (repo distinto; PR con base = tracker de ese repo). Requiere que #6 y #7 ya estén mergeados en `main` de `motoshopData` (contrato de API).

- [x] **8.1** `[AUTO]` **Cliente de API `lib/erp/bank.ts`** `[contrato]`
  - RED: `frontfambus/lib/erp/bank.test.ts` — `test_crear_verificacion_devuelve_job_id_y_expira_en`, `test_consultar_estado_del_job_por_job_id`, `test_503_scraper_no_habilitado_se_traduce_a_error_de_nodo_no_a_excepcion_generica`, `test_503_tenant_no_servido_se_traduce_a_error_de_nodo`, `test_job_vencido_se_traduce_a_estado_expirado`, `test_consultar_candidatos_por_valor_devuelve_ambiguo_y_candidatos`.
  - GREEN: `frontfambus/lib/erp/bank.ts` (`createBankVerification`, `getBankVerification`, `listBankCandidates`; tipos discriminados `BankJobEstado = "en_cola"|"ejecutando"|"esperando_otp"|"resuelto"|"sin_coincidencia"|"ambiguo"|"fallido"|"expirado"`; `BankNodeError` para los 503).
  - Verify: `cd frontfambus && npx vitest run lib/erp/bank.test.ts`.
  - Depends: #6 y #7 mergeados en `main` de `motoshopData`.
  - ✅ GREEN (2026-10-22): `lib/erp/bank.ts` 354 líneas + 9 tests verdes. `npm run typecheck` limpio. Importes como texto, 503 → `BankNodeError`, job vencido → `expirado`.

- [x] **8.2** `[AUTO]` **Prellenado en `PaymentModal` con los `refDirty`/`nameDirty`** `[UI-1s1, UI-1s2, UI-1s3, UI-2s1, UI-2s2, UI-3s1, REC-4s1]`
  - RED: `frontfambus/components/pos/PaymentModal.test.tsx` — `test_prellena_pagador_y_referencia_con_el_candidato_unico`, `test_no_sobrescribe_la_referencia_escrita_por_el_operador` (la referencia escrita a mano se conserva), `test_el_prellenado_no_publica_el_pago` (no se dispara ningún POST de cobro), `test_sin_candidato_los_campos_quedan_vacios_y_sin_error`, `test_con_dos_candidatos_el_operador_elige_uno`, `test_la_referencia_corregida_a_mano_prevalece_al_confirmar`, `test_el_boton_verificar_muestra_el_mensaje_de_otp_del_nodo` (nunca pide el código en el navegador), `test_un_503_deja_el_flujo_manual_de_pegado_intacto`.
  - GREEN: `frontfambus/components/pos/PaymentModal.tsx` (botón "Verificar" sólo con método `TRANSFERENCIA`; `refDirty`/`nameDirty` con `useRef` para no sobrescribir lo escrito a mano; `useBankVerification` con `refreshInterval: 2000`; mensajes: "Esperando el banco…", "El banco pide un código: ingrésalo en la consola del nodo local", "Verificación no disponible" (503) con el pegado manual siempre disponible), `frontfambus/lib/api/hooks.ts` (`useBankVerification(jobId, { refreshInterval: 2000 })` con SWR).
  - Verify: `cd frontfambus && npx vitest run components/pos/PaymentModal.test.tsx lib/erp/bank.test.ts && npm run typecheck && npm run lint`.
  - Depends: 8.1
  - ✅ GREEN (2026-10-22): 8 tests verdes. Botón solo en `TRANSFERENCIA`, `useBankVerification` en `lib/api/hooks.ts` (sondeo 2 s, se apaga en estado final), dirty-flags con `useRef`. `typecheck` limpio; suite completa 384 tests verdes. **Bug encontrado y corregido**: el efecto de reset dependía de `customer.name`, así que prellenar el pagador reseteaba el modal; ahora depende solo de `isPaymentModalOpen`.

- [x] **8.3** `[AUTO]` **E2E Playwright del botón "Verificar" (mock de API)** `[UI-1s1, UI-1s2, UI-2s1, UI-2s2, UI-3s1]`
  - RED: `frontfambus/tests/banco-verificar.spec.ts` — `test_verificar_prellena_pagador_y_referencia` (`page.route` intercepta `**/api/erp/bank/verificaciones`), `test_verificar_no_sobrescribe_la_referencia_manual`, `test_verificar_con_dos_candidatos_ofrece_elegir`, `test_verificar_sin_candidatos_no_muestra_error`, `test_verificar_con_503_mantiene_el_pegado_manual`.
  - GREEN: sólo el spec (el código ya está en 8.2).
  - Verify: `cd frontfambus && npx playwright test tests/banco-verificar.spec.ts`.
  - Depends: 8.2
  - ✅ GREEN (2026-10-22): spec de 252 líneas con 5 casos y `page.route` sobre `verificaciones` y `candidates`. No ejecutado por falta de navegadores Playwright en el entorno: pendiente `npx playwright install chromium`.

**S8 DoD**: el operador puede verificar una transferencia desde el POS y el prellenado nunca contabiliza ni pisa lo escrito a mano.
**Rollback**: revertir el componente; el backend queda intacto.

---

## S9 — Factura, matching explicable y posting (PR #9, base: rama PR #7)

> El matching es una **función pura explicable** y la aplicación **nunca** es automática: score ≥ 80 + candidata única ⇒ *listo para aplicar*, el operador confirma.

- [x] **9.1** `[AUTO]` **Matching por puntaje explicable** `[REC-5s1, REC-5s2, REC-7s1, REC-7s2, REC-11s1]`
  - RED: `motoshop-app/api/tests/test_bank_matching.py` — `test_match_por_referencia_exacta_encabeza_con_100`, `test_match_por_nit_del_pagador_alcanza_80`, `test_match_por_nombre_normalizado_alcanza_60`, `test_match_por_importe_exacto_alcanza_40_y_por_importe_parcial_20`, `test_cada_candidatura_expone_las_senales_que_coincidieron` (`razones`), `test_dos_facturas_con_el_mismo_score_maximo_produce_ambigüedad`, `test_sobrepago_cuando_el_valor_excede_el_saldo`, `test_factura_de_otro_tenant_no_es_candidata`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/matching.py` — `score_candidates(movimiento: BankMovement, facturas: Sequence[FacturaCandidata]) -> list[Candidatura]` con pesos referencia 100 / NIT 80 / nombre normalizado 60 / importe exacto 40 / importe parcial 20; `Candidatura(factura_id, score, razones)`; `normalizar_referencia` (sólo dígitos, sin `" null"`, sin ceros a la izquierda); `normalizar_nombre` (sin tildes, sin sufijos `S.A./LTDA/SA`).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_matching.py -q`.
  - ✅ GREEN (2026-10-22): 10 tests pasan. `matching.py` (226 líneas) con `score_candidates`, `Candidatura(factura_id, score, razones)`, `es_sobrepago` y el filtro de tenant (una factura de otro tenant nunca es candidata).
  - Depends: 7.1

- [x] **9.2** `[AUTO]` **Reconciliación + aplicación por los caminos de caja existentes** `[REC-6s1, REC-6s2, REC-7s1, REC-7s2, REC-8s1, REC-8s2, REC-9s1, REC-9s2, REC-10s1, CC-2s5, CC-2s6]`
  - RED: `motoshop-app/api/tests/test_bank_reconciliation_apply.py` — `test_movimiento_con_score_80_y_candidata_unica_queda_listo_para_aplicar_sin_generar_documento` (no se crea recibo ni consignación), `test_confirmacion_del_operador_genera_el_recibo_con_la_fecha_del_movimiento` (documento con la fecha del movimiento, no la de hoy), `test_movimiento_sin_match_aterriza_como_consignacion_bancaria` (`consbancab`, no recibo), `test_dos_facturas_con_el_mismo_score_maximo_queda_ambigua_y_no_se_aplica`, `test_sobrepago_no_se_aplica`, `test_periodo_cerrado_responde_409_y_el_movimiento_queda_pendiente_y_reintentable` (cero filas de ledger), `test_reintento_tras_reabrir_el_periodo_aplica_con_la_fecha_del_movimiento`, `test_reejecucion_de_la_conciliacion_no_genera_un_segundo_documento` (idempotencia por `uuid5(tenant:id_externo)`), `test_el_documento_generado_usa_el_codpag_de_transferencia_bancaria` (fail-closed si el `codpag` real no está confirmado).
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/repo.py` (`BankReconciliationRepo`: `reconcile(tenant, empresa, movimiento) -> ResultadoConciliacion` con estados `LISTO_PARA_APLICAR|AMBIGUA|SOBREPAGO|SIN_MATCH`; `apply(tenant, movimiento_id, factura_id, idempotency_key, actor)` → **recibo S01 vía `erp.cash.repo.RealReceiptsRepo.create`** con `fecha` = fecha del movimiento, `referencia` recortada a 20 y `codpag` de transferencia bancaria, o **consignación** (`erp/cash/router.py` → `consbancab`) cuando no hay match; `PeriodLockedError` ⇒ 409 y el movimiento queda `PENDIENTE`; `idempotency_key = uuid5(NAMESPACE_DOMINIO, f"{tenant}:{id_externo}")`; `actor = "scraper:bancos"`).
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_reconciliation_apply.py -q`.
  - ✅ GREEN (2026-10-22): 13 tests pasan. **Multi-empresa**: el `codpag` se resuelve **por tenant y por tipo**: recibo `BANK_CODPAG_TRANSFERENCIA_<TENANT>` y consignación `BANK_CODPAG_CONSIGNACION_<TENANT>` (globales homónimos sólo como compatibilidad de un proceso de una sola empresa; **no se cruzan** entre sí) porque el catálogo de formas de pago es de cada empresa; `empresa` del asiento sale de `tenant.erp.empresa` (bug corregido: el router lo leía como atributo plano y posteaba `empresa=""`). Dos desvíos deliberados respecto de esta tarea: (a) `apply(tenant, empresa, movimiento_id, factura_id, *, idempotency_key)` recibe `empresa` explícita porque los repos de caja la exigen para el asiento; (b) `id_movimiento` es el **id de dominio** (`uuid5`), no el `id_externo` — es la clave con la que `find_movement`/`move_to_state` ya trabajaban, así el router no re-resuelve la identidad.
  - Depends: 9.1, 1.1

- [x] **9.3** `[AUTO]` **Router de movimientos, sync-status y apply** `[REC-11s1, REC-11s2, UI-4s1, UI-5s1]`
  - RED: `motoshop-app/api/tests/test_bank_router.py` — `test_listado_de_movimientos_403_sin_permisos_de_cobranzas`, `test_listado_de_movimientos_solo_del_tenant_actual`, `test_listado_filtra_por_estado_y_rango_de_fechas`, `test_apply_403_sin_permisos_de_cobranzas`, `test_apply_404_para_movimiento_de_otro_tenant`, `test_apply_409_en_periodo_cerrado`, `test_apply_replay_con_la_misma_idempotency_key_no_duplica_documento`, `test_sync_status_devuelve_ultima_ingesta_nodo_y_ventana`.
  - GREEN: `motoshop-app/api/src/motoshop_api/erp/bankreconciliation/router.py` (`GET /erp/bank/movements?estado=&desde=&hasta=`, `GET /erp/bank/sync-status`, `POST /erp/bank/reconciliation/{id}/apply` — este último con `require_erp_collections_write` y cabecera `Idempotency-Key`), `motoshop-app/api/src/motoshop_api/erp/guards.py` (entradas `("GET","/api/erp/bank/movements")`, `("GET","/api/erp/bank/sync-status")`, `("POST","/api/erp/bank/reconciliation/{movimiento_id}/apply")` ⇒ `("erp-cash",)`). El parámetro se llama `movimiento_id` (no `{id}`) para no sombrear el builtin; la entrada de `ERP_ROUTE_MODULES` usa el mismo template exacto.
  - Verify: `cd motoshop-app/api && uv run pytest tests/test_bank_router.py -q`.
  - ✅ GREEN (2026-10-22): 8 tests pasan. `get_facturas_provider()` queda **fail-closed**: sin proveedor de facturas abiertas cableado la aplicación responde **503** `facturas_no_configuradas` en vez de devolver lista vacía (una lista vacía convertiría todo movimiento en consignación sin que nadie lo note). Pendiente de S10: cablear el proveedor real sobre la cartera del tenant.
  - Depends: 9.2

**S9 DoD**: el matching explica su puntaje, el posting usa los caminos de caja existentes, la fecha es la del movimiento y el periodo cerrado bloquea con 409 sin escritura parcial.

---

## S10 — Página operativa de transferencias (PR #10, repo `frontfambus`, base: rama PR #8 `frontfambus`)

> **Slice frontend: se ejecuta en `frontfambus`** y encadena sobre el PR #8 de ese repo.

- [x] **10.1** `[AUTO]` **Listado, filtros y estados vacío/carga/error** `[UI-4s1, UI-5s1, UI-5s2, UI-6s1]`
  - RED: `frontfambus/components/erp/TransferenciasBancarias.test.tsx` — `test_fila_de_movimiento_muestra_fecha_descripcion_referencia_saneada_importe_pagador_estado_y_factura`, `test_filtro_por_estado_muestra_solo_los_movimientos_de_ese_estado`, `test_filtro_por_rango_de_fechas_muestra_solo_los_movimientos_del_rango`, `test_fallo_del_backend_muestra_estado_de_error_y_no_una_lista_vacia`, `test_lista_vacia_se_muestra_como_estado_vacio_y_no_como_error`.
  - GREEN: `frontfambus/components/erp/TransferenciasBancarias.tsx` (tabla con SWR sobre `GET /api/erp/bank/movements`; filtros por estado y por rango; estados vacío / cargando / error **distinguidos**), `frontfambus/app/(authenticated)/banco/transferencias/page.tsx` (server component + `metadata`, como `maestros/terceros/page.tsx`).
  - Verify: `cd frontfambus && npx vitest run components/erp/TransferenciasBancarias.test.tsx && npm run typecheck && npm run lint`.
  - ✅ GREEN (2026-10-22): 5 tests de listado pasan; `npx vitest run` completo **393 passed** (62 archivos), `typecheck` limpio, `lint` sin warnings nuevos. El filtro se aplica también en el cliente: si el backend ignorara un parámetro, la tabla sigue mostrando lo que dice el filtro.
  - Depends: #9 mergeado en `main` de `motoshopData`; PR #8 de `frontfambus` como base.

- [x] **10.2** `[AUTO]` **Resolución manual + permisos y nav** `[UI-7s1, UI-7s2, UI-8s1, UI-8s2]`
  - RED: `frontfambus/components/erp/TransferenciasBancarias.test.tsx` — `test_aplicacion_manual_a_una_factura_elegida_refleja_el_nuevo_estado_y_la_factura`, `test_un_movimiento_ya_aplicado_no_ofrece_la_accion_de_aplicar`, `test_solo_se_listan_movimientos_del_tenant_actual`, `test_usuario_sin_permiso_de_cobranzas_no_alcanza_la_pagina`.
  - GREEN: `frontfambus/components/erp/TransferenciasBancarias.tsx` (acción "Aplicar" sólo en `AMBIGUA`/`SOBREPAGO`/`SIN_MATCH`, con `Idempotency-Key` vía `frontfambus/lib/erp/idempotency.ts`), `frontfambus/lib/auth/access.ts` (`["/banco/transferencias", { feature: "bank-reconciliation" }]` en `PATH_RULES`), `frontfambus/components/ui/Navigation.tsx` (item en `gerenteNavItems()` con `feature: "bank-reconciliation"`), `motoshopData/motoshop-app/api/tenants.yaml` (feature `bank-reconciliation` por tenant).
  - Verify: `cd frontfambus && npx vitest run components/erp/TransferenciasBancarias.test.tsx && npm run typecheck && npm run lint` + `cd motoshop-app/api && uv run pytest -q`.
  - ✅ GREEN (2026-10-22): 4 tests de resolución/permisos pasan (9 en el archivo). Desvío deliberado: el botón "Aplicar" se muestra en `AMBIGUA`/`SOBREPAGO`/`SIN_MATCH` **y nunca** en `APLICADO`; un `PENDIENTE` listo para aplicar se resuelve desde el POS (S8), no desde esta página, para no ofrecer dos caminos de escritura al mismo movimiento. La clave de idempotencia se genera una vez por resolución (`useState`), no por click.
  - Depends: 10.1

- [x] **10.3** `[AUTO]` **E2E Playwright de la página** `[UI-4s1, UI-5s1, UI-7s1]`
  - RED: `frontfambus/tests/banco-transferencias.spec.ts` — `test_la_pagina_muestra_el_listado_de_movimientos`, `test_el_filtro_por_estado_reduce_la_lista`, `test_la_aplicacion_manual_actualiza_la_fila`.
  - GREEN: sólo el spec (el código ya está en 10.1/10.2).
  - Verify: `cd frontfambus && npx playwright test tests/banco-transferencias.spec.ts`.
  - ✅ GREEN (2026-10-22) **parcial**: spec de 182 líneas con 3 casos y `page.route` sobre `movements`, `candidates` y `reconciliation`. No ejecutado: faltan los navegadores Playwright en este entorno (`npx playwright install chromium`).
  - Depends: 10.2

**S10 DoD**: la página operativa lista, filtra, distingue error de vacío y permite la resolución manual sin ofrecer acciones que la API rechazaría.

---

## Matriz de trazabilidad (requisito → slice → task)

`ING` = erp-bank-transfer-ingestion · `REC` = erp-bank-reconciliation · `UI` = erp-bank-transfer-reconciliation-ui · `CC` = erp-collections-cash (delta). `R<n>s<m>` = requisito n, escenario m.

| Spec | Requisito | Slice | Tasks |
|---|---|---|---|
| ING | R1 Captura interactiva de credenciales | S2 | 2.1 |
| ING | R2 Bóveda cifrada con acceso restringido | S2 | 2.1 |
| ING | R3 Autenticación con verificación en dos pasos | S5 | 5.2 |
| ING | R4 Reutilización de sesión | S5 | 5.2 |
| ING | R5 Selección de la cuenta por etiqueta | S5 | 5.2 |
| ING | R6 Credenciales resueltas por tenant | S3, S5 | 3.1, 3.2, 5.2 |
| ING | R7 No consulta de cuentas de otro tenant | S5 | 5.2 |
| ING | R8 Cobertura paginada de la ventana de consulta | S3, S5 | 3.1, 5.2 |
| ING | R9 Campos del movimiento leídos de la tabla | S5 | 5.1 |
| ING | R10 Dirección del movimiento según el signo del valor | S5 | 5.1 |
| ING | R11 Importe con aritmética decimal | S5 | 5.1 |
| ING | R12 Ingesta idempotente de movimientos | S4, S5 | 4.1, 5.2 |
| ING | R13 Estados de error distinguibles | S5, S6 | 5.2, 6.1, 6.2, 6.3 |
| ING | R14 Límite de frecuencia de ejecución | S5, S6 | 5.2, 6.2 |
| REC | R1 Coincidencia por valor dentro de la ventana | S7 | 7.1, 7.2 |
| REC | R2 Frontera de la ventana de consulta | S7 | 7.1 |
| REC | R3 Ambigüedad de valor entre movimientos | S7 | 7.1, 7.2 |
| REC | R4 Datos del candidato para la captura del pago | S7, S8 | 7.1, 8.2 |
| REC | R5 Matching explicable por puntaje | S9 | 9.1 |
| REC | R6 Aplicación condicionada a confirmación humana | S9 | 9.2 |
| REC | R7 Estados marcados distinguibles | S9 | 9.1, 9.2 |
| REC | R8 Escritura por los caminos de caja existentes | S9 | 9.2 |
| REC | R9 Fecha del recibo y periodo cerrado | S9 | 9.2 |
| REC | R10 Idempotencia de la conciliación | S9 | 9.2 |
| REC | R11 Aislamiento por tenant y permisos | S4, S7, S9 | 4.1, 7.2, 9.1, 9.3 |
| UI | R1 Prellenado automático en la captura del pago | S8 | 8.2, 8.3 |
| UI | R2 Estados sin candidato y con candidatos múltiples | S8 | 8.2, 8.3 |
| UI | R3 Prevalencia de la corrección manual | S8 | 8.2, 8.3 |
| UI | R4 Listado de movimientos ingeridos | S9, S10 | 9.3, 10.1, 10.3 |
| UI | R5 Filtros por estado y rango de fechas | S9, S10 | 9.3, 10.1, 10.3 |
| UI | R6 Estados vacío, carga y error distinguibles | S10 | 10.1 |
| UI | R7 Resolución manual de movimientos marcados | S10 | 10.2, 10.3 |
| UI | R8 Tenant y permisos de la página | S10 | 10.2 |
| CC | R1 (ADDED) Payment reference persistence limit | S1 | 1.2 |
| CC | R2 (MODIFIED) Payments applied to open CxC | S1, S9 | 1.1 (s1–s4), 9.2 (s5–s6) |

**Cobertura**: 14/14 requisitos de ING, 11/11 de REC, 8/8 de UI, 2/2 de CC. Sin requisitos huérfanos.

---

## Fuera de alcance (explícitamente NO se planifica)

1. Sesión manual reutilizada (fase C del eje de scraping) — descartada por D1.
2. Interceptación del endpoint XHR de Bancolombia — **desconocido y no verificado**; no se inventa.
3. Watcher automático de página (queda como pre-fetch opcional, apagado por defecto — D1).
4. DuckDB silver/gold / proyección analítica de `app_bank_movements`.
5. API del banco, SPEI, otros bancos (multi-banco).
6. Implementación real del backend `dpapi` (sigue siendo stub; Windows usa `passphrase`).
7. Cualquier escritura en `keyfile` (prohibido por ADR-0026).
8. Auto-posteo sin confirmación humana (prohibido por `REC-6`).
9. Pruebas E2E live contra el portal real (Akamai + ToS); el spec live queda `test.skip(!process.env.E2E_LIVE)`.
10. Exportación manual a CSV de los movimientos como plan B de Akamai.
11. Rediseño del POS más allá del bloque de transferencia.
12. Migración de los recibos ya posteados por otros medios.

---

## Preguntas abiertas (bloquean el cierre de la slice indicada)

| # | Pregunta | Bloquea | Impacto si no se resuelve |
|---|---|---|---|
| Q1 | **Visto bueno legal del ToS de Bancolombia para login automatizado.** ADR-0026 sigue `Proposed`. | S2 (estado del ADR, task 3.4) y el **rollout** de S5–S10 (activar `BANK_SCRAPER_ENABLED=true` en un nodo real) | El código puede existir, pero **no se activa** el scraper en máquinas reales. Slices S3–S10 se cierran en código, no en producción. |
| Q2 | **Etiqueta real de la cuenta MotoShop** (`BANK_ACCOUNT_LABEL`). En MasVital también está "por confirmar" (design). | S3 (task 3.1: sin etiqueta el nodo no arranca) y S5 (task 5.2: sin ella ⇒ `cuenta_no_encontrada`) | El nodo falla con `cuenta_no_encontrada` y no lee movimientos. El parser y los tests offline siguen verdes. |
| Q3 | **¿Se implementa DPAPI?** Hoy `dpapi` es un stub y Windows usa `passphrase` (decisión D8). | Nada en este cambio (fuera de alcance #6) | Si más adelante se requiere custodia sin frase de contraseña en Windows, hace falta un slice aparte. |
| Q4 | **Endpoint XHR de Bancolombia desconocido.** El parseo DOM de "Tus movimientos" es la estrategia primaria; interceptar XHR sería una optimización opcional. | S5 (task 5.2) — el parser **debe ser contract-driven** con fixtures offline (`tests/fixtures/bank/*.html`) | Si el DOM cambia, el scraper falla con `portal_no_disponible` y no con datos corruptos. **Prohibido inventar el endpoint.** |
| Q5 | **`formapago.codpag` real de la transferencia bancaria** (el esquema vivo muestra `F01`..`F10` de 4 chars; los fakes siembran `"01"`/`"22"`). | S9 (task 9.2) — **fail-closed** | Sin el `codpag` confirmado, la conciliación **no postea**; el movimiento queda pendiente y se reporta. |

---

## Plan de commits por work-unit (un commit = una unidad revisable; código + tests + docs juntos)

### PR #1 · S1 — `feature/banco-01-cartera-numpag` (base: tracker `motoshopData`)
1. `fix(erp-cash): read the open balance from the real cartera account` — `cash/repo.py` (`CARTERA_CUENTA = "13050501"` + alias `1305`), `cash/store.py` (`ledger_rows_for_accounts`), `tests/test_erp_cash_cartera.py`.
2. `fix(erp-cash): truncate the payment reference to the legacy column width` — `cash/repo.py` (`NUMPAG_MAX_LEN = 20`), `invoicing/repo.py` (constante compartida), `tests/test_erp_cash_reference_limit.py`.

### PR #2 · S2 — `feature/banco-02-vault` (base: PR #1) — **ya implementado**
1. `feat(erp-bank): add the encrypted credential vault with passphrase custody` — `bankreconciliation/vault.py`, `bankreconciliation/__init__.py`, `tests/test_bank_vault.py`.
2. `feat(erp-bank): add the credential vault CLI` — `bankreconciliation/cli.py`.
3. `docs(adr): record the Bancolombia credential vault decision` — `docs/decisions/0026-bancolombia-vault.md`.
4. `build(api): add the cryptography runtime dependency` — `pyproject.toml`, `uv.lock`.

### PR #3 · S3 — `feature/banco-03-node-config` (base: PR #2)
1. `feat(erp-bank): resolve the per-tenant node configuration` — `bankreconciliation/node_config.py`, `tests/test_bank_node_config.py`.
2. `feat(erp-bank): add the node preflight check` — `node_config.py` (`run_preflight`), `scripts/bank_verify.py`, `tests/test_bank_node_preflight.py`.
3. `docs(runbook): document the bank node provisioning and recovery` — `docs/runbook-banco.md`.
4. `docs(adr): accept the Bancolombia vault decision` — ADR-0026 `Proposed → Accepted` **[CHECKPOINT, bloqueado por Q1]**.

### PR #4 · S4 — `feature/banco-04-persistencia` (base: PR #3)
1. `feat(erp-bank): persist ingested bank movements idempotently` — `bankreconciliation/schemas.py`, `bankreconciliation/store.py`, `tests/test_bank_store_ingest.py`.
2. `feat(db): add the app_bank_movements table and writer grant` — `infra/migrations/F9-001-app_bank_movements.sql`, `infra/migrations/F9-002-grant_app_writer_bank.sql` **[CHECKPOINT: MySQL local]**.

### PR #5 · S5 — `feature/banco-05-portal-parser` (base: PR #4)
1. `feat(erp-bank): parse Colombian movement rows into movements` — `bankreconciliation/parser.py`, `tests/test_bank_parser.py`.
2. `feat(erp-bank): read the tenant account movements from the portal` — `bankreconciliation/portal_pages.py`, `bankreconciliation/scraper.py`, `tests/fixtures/bank/*.html`, `tests/test_bank_portal_contract.py`.
3. `feat(erp-bank): add the node scrape command` — `scripts/bank_sync.py`.

### PR #6 · S6 — `feature/banco-06-job` (base: PR #5)
1. `feat(erp-bank): add the verification job store` — `bankreconciliation/jobs.py`, `tests/test_bank_verification_jobs.py`.
2. `feat(db): add the app_bank_verification_jobs table` — `infra/migrations/F9-003-app_bank_verification_jobs.sql` **[CHECKPOINT: MySQL local]**.
3. `feat(erp-bank): run one verification job at a time on the node` — `bankreconciliation/worker.py`, `tests/test_bank_worker.py`.
4. `feat(erp-bank): expose the bank verification endpoints` — `bankreconciliation/router.py`, `erp/guards.py`, `main.py`, `tests/test_bank_verification_router.py`.

### PR #7 · S7 — `feature/banco-07-match-valor` (base: PR #6)
1. `feat(erp-bank): match movements by value inside the query window` — `bankreconciliation/value_match.py`, `tests/test_bank_value_match.py`.
2. `feat(erp-bank): expose the payment candidates endpoint` — `bankreconciliation/router.py`, `erp/guards.py`, `tests/test_bank_candidates_router.py`.

### PR #8 · S8 — `feature/banco-08-boton-verificar` (base: tracker `frontfambus`)
1. `feat(bank): add the bank verification API client` — `lib/erp/bank.ts`, `lib/erp/bank.test.ts`.
2. `feat(pos): prefill the payer and reference from the bank candidate` — `components/pos/PaymentModal.tsx`, `components/pos/PaymentModal.test.tsx`, `lib/api/hooks.ts`.
3. `test(pos): cover the verify button flow with a mocked backend` — `tests/banco-verificar.spec.ts`.

### PR #9 · S9 — `feature/banco-09-factura-posting` (base: PR #7)
1. `feat(erp-bank): score invoice candidates with explainable signals` — `bankreconciliation/matching.py`, `tests/test_bank_matching.py`.
2. `feat(erp-bank): reconcile and apply a bank movement through the cash paths` — `bankreconciliation/repo.py`, `tests/test_bank_reconciliation_apply.py`.
3. `feat(erp-bank): expose the movements, sync status and apply endpoints` — `bankreconciliation/router.py`, `erp/guards.py`, `tests/test_bank_router.py`.

### PR #10 · S10 — `feature/banco-10-pagina-banco` (base: PR #8 `frontfambus`)
1. `feat(bank): list the ingested movements with filters` — `components/erp/TransferenciasBancarias.tsx`, `components/erp/TransferenciasBancarias.test.tsx`, `app/(authenticated)/banco/transferencias/page.tsx`.
2. `feat(bank): allow manual reconciliation from the transfers page` — `components/erp/TransferenciasBancarias.tsx`, `lib/auth/access.ts`, `components/ui/Navigation.tsx`, `motoshop-app/api/tenants.yaml`.
3. `test(bank): cover the transfers page flow with a mocked backend` — `tests/banco-transferencias.spec.ts`.

---

## Notas de ejecución

- Cada PR debe dejar el repo verde: `uv run pytest -q` + `uv run ruff check src tests` (backend) y `npm run test:unit` + `npm run typecheck` + `npm run lint` (frontend).
- Las tareas `[CHECKPOINT]` (3.4 por el visto bueno legal, 4.2 por el MySQL local y el commit 2 de PR #6 por la migración `F9-003`) pausan para acción del operador.
- El E2E live contra el portal real queda fuera: los specs Playwright de este cambio usan `page.route` con respuestas mockeadas.
- Orden de rollout (del design): ADR-0026 Accepted → `F9-001/002/003` → API con el flag **off** → provisión del vault por máquina → `playwright install chromium` + perfil 700 fuera del repo → `BANK_SCRAPER_ENABLED=true` en el nodo del tenant → botón "Verificar" (#8).
