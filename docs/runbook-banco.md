# Runbook operativo · Conciliación de transferencias Bancolombia

Este runbook es la referencia del operador para dejar **un nodo local** listo para rascar el
portal de Bancolombia: qué configurar en cada máquina, cómo provisionar la credencial, cómo
rotarla, qué hacer con el código dinámico y cómo revertir todo.

> **Estado del rollout:** el scraping **no** está habilitado en ninguna máquina real. La
> automatización del login queda bloqueada por el visto bueno legal de los términos de servicio
> del banco (ADR-0026 sigue en estado `Proposed`). Este documento describe cómo queda cada nodo
> **cuando** se levante ese bloqueo.

**Ruta rápida (nodo local nuevo)**

1. Copiá la tabla de [Topología por nodo](#1-topología-por-nodo) a tu `.env`.
2. Proporcioná la credencial con el CLI del vault (ver [Provisión por nodo](#2-provisión-por-nodo)).
3. Instalá Chromium de Playwright y creá el perfil **fuera del repo** con permisos `700`.
4. Verificá el nodo: `uv run python scripts/bank_verify.py --tenant <tenant>`.

---

## 1. Topología por nodo

Un proceso de API = **un tenant**. La configuración vive en el `.env` de cada máquina
(Windows: `%APPDATA%`; macOS/Linux: `~/.config`).

| Variable | PC MasVital | PC MotoShop | Mac (dev) | Render (nube) |
|---|---|---|---|---|
| `BANK_SCRAPER_ENABLED` | `true` | `true` | `true` | `false` |
| `BANK_TENANT` | `masvital` | `motoshop` | tenant en pruebas | — |
| `BANK_CREDENTIAL_ENTRY` | `bancolombia-masvital` | `bancolombia-motoshop` | `bancolombia-<tenant>` | — |
| `BANK_ACCOUNT_LABEL` | etiqueta MasVital | etiqueta MotoShop *(por confirmar)* | según tenant | — |
| `BANK_VAULT_BACKEND` | `passphrase` | `passphrase` | `keychain` | — |
| `BANK_PROFILE_DIR` | `%APPDATA%\motoshop\bank-profile\<tenant>` | ídem | `~/.config/motoshop/bank-profile/<tenant>` | — |
| `BANK_CODPAG_TRANSFERENCIA_<TENANT>` | código de transferencia | ídem | ídem | — |
| `BANK_CODPAG_CONSIGNACION_<TENANT>` | código de consignación | ídem | ídem | — |

Reglas de la tabla:

- `BANK_CREDENTIAL_ENTRY` sigue la convención `bancolombia-<tenant>`. Cada tenant tiene **su
  propia** entrada en el vault: nunca se comparte una credencial entre tenants.
- `BANK_ACCOUNT_LABEL` es la **etiqueta** de la cuenta en el portal (no el número de cuenta). Es
  lo único que permite abrir la cuenta correcta sin abrir la de otro tenant.
- `BANK_PROFILE_DIR` es el perfil del navegador (el perfil **es** la sesión). Nunca dentro del
  repositorio: el preflight lo rechaza.
- `BANK_SCRAPER_ENABLED=false` ⇒ ese nodo no raspa. En la nube es lo normal.
- `BANK_CODPAG_*` vive en el catálogo `formapago` de **cada** empresa y **no se comparte**: el
  recibo por transferencia y la consignación bancaria son formas de pago distintas (filas distintas,
  cuentas de contrapartida distintas). Los globales sin sufijo sólo existen para procesos de una
  sola empresa: nunca se usa el código de transferencia como consignación. Sin el código
  confirmado, aplicar responde **409 `codpag_no_confirmado`** y el movimiento queda pendiente.

### Variables opcionales

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `BANK_WINDOW_START` | hoy `00:00:00` | Inicio de la ventana de consulta (ISO-8601: `YYYY-MM-DD` o `YYYY-MM-DDTHH:MM:SS`) |
| `BANK_WINDOW_END` | hoy `23:59:59` | Fin de la ventana de consulta |

Si sólo se ajusta un extremo, el otro acompaña al día indicado. Con la ventana por defecto la
configuración queda **auditable**: el preflight informa `ventana: dia` o `ventana: personalizada`.

---

## 2. Provisión por nodo

Todos los comandos se ejecutan desde `motoshop-app/api` (con el venv del proyecto: `uv run ...`
o `python ...` con el venv activado).

### 2.1 Credencial en el vault

**Windows (PC MasVital / PC MotoShop — backend `passphrase`):**

```powershell
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend passphrase set bancolombia-motoshop
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend passphrase set bancolombia-masvital
```

**macOS (Mac de desarrollo — backend `keychain`):**

```bash
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend keychain set bancolombia-masvital
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend keychain set bancolombia-motoshop
```

El CLI pide el usuario, la clave y la frase de contraseña **por prompt local sin eco**. El texto
claro no queda en disco, ni en el `.env`, ni en `argv`, ni en los logs.

El Mac guarda **ambos** tenants y cambia de tenant relanzando la API con otro `BANK_TENANT`.

### 2.2 Navegador (Playwright)

```bash
uv run --with playwright playwright install chromium
```

> Cuando la slice del scraper agregue `playwright` como dependencia del proyecto, el comando
> `uv run playwright install chromium` alcanza.

### 2.3 Perfil del navegador: fuera del repo y con permisos `700`

**macOS / Linux:**

```bash
mkdir -p ~/.config/motoshop/bank-profile/motoshop
chmod 700 ~/.config/motoshop/bank-profile/motoshop
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force -Path "$env:APPDATA\motoshop\bank-profile\motoshop" | Out-Null
icacls "$env:APPDATA\motoshop\bank-profile\motoshop" /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F"
```

El directorio del perfil **nunca** va dentro del repositorio: ahí queda la sesión del banco
(cookies). El preflight lo rechaza con el motivo `perfil_dentro_del_repo`.

### 2.4 Verificación del nodo

```bash
uv run python scripts/bank_verify.py --tenant motoshop
```

Salida esperada: `PREFLIGHT OK: el nodo 'motoshop' está listo.` (código de salida `0`).

Para una comprobación **sin** tocar el vault (no pide la clave maestra):

```bash
uv run python scripts/bank_verify.py --tenant motoshop --check
```

Con cualquiera de los dos comandos, si algo falta el proceso termina con código `1` e imprime el
motivo (`credencial_ausente`, `cuenta_no_encontrada`, `perfil_permisos_insuficientes`, …).

---

## 3. Rotación de credenciales

```bash
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend keychain rotate bancolombia-motoshop
```

Después de rotar, revisá:

1. Que el login del portal siga funcionando con la credencial nueva (login manual en el nodo).
2. Que el perfil del navegador siga autenticado: si el portal cambió, cerrá sesión y volvé a
   entrar **a mano**.
3. Que el preflight siga en verde: `uv run python scripts/bank_verify.py --tenant <tenant>`.

Si la rotación falla:

- **No borres el vault** ni la entrada anterior: `rotate` es atómico (o actualiza la entrada, o no
  cambia nada). La credencial anterior sigue en pie y el nodo sigue funcionando.
- Repetí la rotación con la clave nueva. Si el error es de custodia (`vault_no_accesible`), la
  causa es la frase de contraseña o el archivo alterado: **no** regeneres el vault.

---

## 4. OTP (código dinámico)

Cuando el portal exige una verificación en dos pasos:

1. El código se pide **en la consola del nodo local**, nunca en el navegador ni en el POS.
2. El operador lee el código en la sesión del portal que se abrió en el nodo y lo escribe en esa
   consola.
3. El código **no se persiste** (ni en disco, ni en la base, ni en el log del job) y **no se
   reenvía** por chat, correo ni ticket de soporte.
4. Si el código no llega en **300 s**, el job expira con estado `expirado`: el operador reintenta
   desde el POS.

El front nunca pide el código: mientras el job está `esperando_otp` muestra *"El banco pide un
código: ingrésalo en la consola del nodo local"*.

---

## 5. Scraper deshabilitado

Un nodo con el scraping apagado (por defecto en la nube) es una configuración **válida**, no un
error:

```bash
BANK_SCRAPER_ENABLED=false
```

Efectos:

- La API de la nube responde `503` con `error_codigo: scraper_no_habilitado`.
- El **pegado manual del POS sigue disponible**: capturar el pago a mano nunca se bloquea.
- El preflight de ese nodo responde `PREFLIGHT OK` con la comprobación `scraper_deshabilitado`, y
  **no pide ninguna clave** del vault.

**No lo "arregles" reintentando contra la nube.** El `503` es la respuesta esperada: el trabajo
de scraping corre en el nodo local del tenant, no en Render.

---

## 6. Errores frecuentes

| Motivo | Qué significa | Qué hacer |
|---|---|---|
| `credencial_ausente` | El vault no tiene la entrada de este tenant (o no hay vault). | Provisioná la entrada: `cli --backend <backend> set bancolombia-<tenant>`. El nodo **no** usa la credencial de otro tenant. |
| `cuenta_no_encontrada` | Falta `BANK_ACCOUNT_LABEL` o la etiqueta no existe en la sesión del portal. | Revisá la etiqueta real de la cuenta en el portal y actualizá `BANK_ACCOUNT_LABEL`. Nunca se abre la cuenta por índice. |
| `sesion_expirada` | El portal cerró la sesión (el perfil no la renovó). | Re-logueá **a mano** en el perfil del nodo y volvé a correr. |
| `antibot` | El portal pidió una verificación automática. | **Pará y re-logueá a mano.** No automatices ni reintentes en bucle: el job falla sin dejar movimientos parciales. |
| `portal_no_disponible` | El portal no respondió (o el DOM cambió). | Reintentá más tarde. Si persiste, el contrato del portal (`PortalContract`) puede haber cambiado: revisar con el equipo backend. |

Motivos propios del diagnóstico local del nodo:

| Motivo | Qué significa | Qué hacer |
|---|---|---|
| `vault_no_accesible` | El vault no se pudo leer (frase de contraseña o archivo alterado). | Verificá la frase de contraseña; no regeneres el vault. |
| `perfil_dentro_del_repo` | El perfil del navegador está dentro del repositorio. | Movelo a `%APPDATA%\motoshop\bank-profile\<tenant>` (Windows) o `~/.config/motoshop/bank-profile/<tenant>` (macOS). |
| `perfil_inexistente` | No existe el directorio del perfil. | Crealo con `mkdir -p` + `chmod 700`. |
| `perfil_permisos_insuficientes` | El perfil no tiene permisos `700`. | `chmod 700 <perfil>` (macOS/Linux) o `icacls` (Windows). |
| `tenant_no_configurado` | El nodo no declara `BANK_TENANT`. | Configuralo en el `.env` del nodo. |

---

## 7. Reversa

Para dejar el sistema como estaba, en este orden:

1. **Apagá el flag** en todos los nodos: `BANK_SCRAPER_ENABLED=false` (⇒ `503 scraper_no_habilitado`
   y el flujo manual intacto).
2. **Quitá las rutas** de `ERP_ROUTE_MODULES` (`src/motoshop_api/erp/guards.py`): las entradas
   `POST /api/erp/bank/verificaciones`, `GET /api/erp/bank/verificaciones/{job_id}`,
   `GET /api/erp/bank/candidates`, `GET /api/erp/bank/movements`,
   `GET /api/erp/bank/sync-status` y `POST /api/erp/bank/reconciliation/{id}/apply`.
3. **Drop de las tablas** del módulo:

   ```sql
   DROP TABLE app_bank_verification_jobs;
   DROP TABLE app_bank_movements;
   ```

4. **Anulá los recibos posteados** por la conciliación con el módulo de anulación existente
   (`erp/annulment/`), no borres las filas del ledger.
5. **Revocá la credencial** del vault:

   ```bash
   uv run python -m motoshop_api.erp.bankreconciliation.cli --backend keychain delete bancolombia-motoshop
   uv run python -m motoshop_api.erp.bankreconciliation.cli --backend keychain delete bancolombia-masvital
   ```

6. **Borrá el perfil** del navegador (`bank-profile/<tenant>`) si querés revocar la sesión
   abierta del portal.

El flag apagado es reversible en cualquier momento: no hay migración de datos que deshacer.
