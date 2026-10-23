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
| `BANK_ACCOUNT_LABEL` | `MasVital` | `Cuenta de Ahorros` | según tenant | — |
| `BANK_VAULT_BACKEND` | `dpapi` | `dpapi` | `keychain` | — |
| `BANK_PROFILE_DIR` | `%APPDATA%\motoshop\bank-profile\<tenant>` | ídem | `~/.config/motoshop/bank-profile/<tenant>` | — |
| `BANK_CODPAG_TRANSFERENCIA_<TENANT>` | `F07` | `F07` | ídem | — |
| `BANK_CODPAG_CONSIGNACION_<TENANT>` | `F05` | `F05` | ídem | — |

Reglas de la tabla:

- `BANK_CREDENTIAL_ENTRY` sigue la convención `bancolombia-<tenant>`. Cada tenant tiene **su
  propia** entrada en el vault: nunca se comparte una credencial entre tenants.
- `BANK_ACCOUNT_LABEL` es la **etiqueta** de la cuenta en el portal (no el número de cuenta). Es
  lo único que permite abrir la cuenta correcta sin abrir la de otro tenant.
- `BANK_PROFILE_DIR` es el perfil del navegador (el perfil **es** la sesión). Nunca dentro del
  repositorio: el preflight lo rechaza.
- `BANK_VAULT_BACKEND=dpapi` (Windows): la clave maestra es aleatoria y la protege DPAPI en
  `%APPDATA%\motoshop\master.key.dpapi`. **No hay frase maestra** y el proceso que raspa tiene que
  correr con el mismo usuario de Windows que guardó la credencial. `passphrase` en Windows obliga a
  escribir la frase en cada corrida, así que no sirve para una tarea programada.
- `BANK_SCRAPER_ENABLED=false` ⇒ ese nodo no raspa. En la nube es lo normal.
- `BANK_CODPAG_*` vive en el catálogo `formapago` de **cada** empresa y **no se comparte**: el
  recibo por transferencia y la consignación bancaria son formas de pago distintas (filas distintas,
  cuentas de contrapartida distintas). Los globales sin sufijo sólo existen para procesos de una
  sola empresa: nunca se usa el código de transferencia como consignación. Sin el código
  confirmado, aplicar responde **409 `codpag_no_confirmado`** y el movimiento queda pendiente.

### Valores confirmados (evidencia, no nombres)

El `codpag` no se adivina por el nombre de la forma de pago: se toma de la distribución real de
`detapago.codpag` (blueprint de `sgHermes`, §2.4):

| Código | Forma | Usos en `sgHermes` |
|---|---|---:|
| F01 | EFECTIVO | 8.082 |
| F05 | **CONSIGNACIÓN BANCO** | **826** |
| F11 | CUENTAS X PAGAR | 312 |
| F06 | CHEQUE | 83 |
| F10 | CUENTAS X COBRAR | 6 |
| F07 | **TRANSFERENCIA** | **4** |
| F03 | TARJETA DÉBITO | 1 |

- Transferencia bancaria (cobro de factura) ⇒ **F07**.
- Consignación bancaria (sin factura) ⇒ **F05**.
- `BANK_ACCOUNT_LABEL` es la etiqueta de la tarjeta del home (`<p class="text-ellipsis">`): se
  compara **exacta** tras normalizar espacios y mayúsculas. MasVital = `MasVital`
  (879-000605-71); MotoShop = `Cuenta de Ahorros` (879-777844-40).
- Verificado en vivo en las dos bases (`sgHermes` y `masvital`): existen las 20 filas y las dos
  que importan son `F05 CONSIGNACION BANCO....` y `F07 TRANSFERENCIA BANCO....`, ambas con
  `codcue = 11100501`. Comparten la cuenta bancaria de contrapartida pero describen hechos
  distintos: transferencia entra con factura (recibo `S01`) y consignación entra sin factura
  (documento `CC`). El código las separa por `factura_id`, no por el código de forma de pago.
- `codban` va vacío en todas las filas: la cuenta sale de `codcue`, no de `codban`.

#### Hallazgo de datos (2026-10-22): la venta nunca usa `F07`

Verificado en las dos bases con el cruce contra la cabecera de la venta: **ninguna factura de
`facventas` tiene `codpag = 'F07'`**. La distribución real de `facventas.codpag` es `F01` 2.787,
`F05` 755, vacío 40, `F10` 21, `F03` 3, `F14` 2, `F04` 1. Las filas `F07` de `detapago` (218 en
`masvital`) pertenecen todas a compras: `codclas = S18`, `predoc = COM` (pagos a proveedores,
plata que **sale**), no a recaudos.

Consecuencias, para no volver a tropezar:

- La cobranza bancaria real de estos negocios es **`F05` consignación**. La rama de transferencia
  (`S01`) queda configurada y fail-closed, pero en estas bases **no tiene datos detrás**: no se
  puede probar el flujo con una factura de transferencia porque no existe.
- Las pruebas manuales del botón **Comprobar** se hacen con una factura `F05` real, no con una
  transferencia.
- El cruce no depende del `codpag`: el código separa por `factura_id`. Por eso una factura `F05`
  concilia igual contra el movimiento del banco.

Para re-verificar por empresa:

```sql
SELECT codpag, COUNT(*) FROM detapago GROUP BY codpag ORDER BY 2 DESC;
SELECT codpag, COUNT(*) FROM facventas GROUP BY codpag ORDER BY 2 DESC;
SELECT codpag, forpag, codcue FROM formapago ORDER BY codpag;
```

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

### Automatización: la cuenta de Windows del proceso que raspa

El scrape corre **dentro del proceso de la API** (el botón *Comprobar* despacha un hilo del mismo
proceso, `router.py`), así que la cuenta que decide si funciona es la del servicio/tarea que levanta
la API, no la de la consola del operador. DPAPI y `%APPDATA%` son **por usuario**:

- Como `SYSTEM`, `%APPDATA%` es `C:\Windows\system32\config\systemprofile\AppData\Roaming`: ahí no
  están ni `master.key.dpapi` ni `bank-profile\<tenant>`. El job falla en **`credencial_ausente`**
  (`VaultNotFound`), que no es lo mismo que `vault_no_accesible` (vault presente pero ilegible).
  Probado en MotoShop: job `fallido` / `credencial_ausente` sin tocar el portal.
- La tarea tiene que correr con el **usuario que guardó la credencial** (`MotoShop`, `ProDesk`).
- Si la tarea corre «aunque el usuario no haya iniciado sesión», no hay escritorio interactivo y
  Chromium no puede abrir ventana: hay que poner `BANK_BROWSER_HEADLESS=true` **y validar que el
  portal no lo tome como antibot**. La alternativa pragmática en una PC de local es la tarea con
  «sólo cuando el usuario inició sesión», que conserva el navegador con ventana.
- No se re-crea el vault bajo `SYSTEM`: además de no resolver el perfil del navegador, dejaría la
  credencial del banco al alcance de cualquier proceso que corra como `SYSTEM`.
- Con la tarea «sólo cuando el usuario inició sesión», el autostart ocurre **al iniciar sesión**, no
  al arrancar Windows. Si la PC reinicia y nadie entra, no hay API: cae el ERP entero, no sólo el
  botón. Quien opera el local tiene que saberlo y entrar como el usuario de la tarea.

### R2 — Arranque autónomo tras reinicio: **PRODESK OK; ACÁ CONFIGURADO, PENDIENTE PRUEBA DE REINICIO**

**Actualización 2026-10-23 (nodo masvital / ProDesk, mensaje 0034 del bus):**
- Allá el autologon **ya funciona**: reinicio a las 22:17 y la sesión entró sin tocar teclado.
- Apareció una falla más sutil: la tarea de API quedó `Running` desde 22:17:17 con el puerto 8000
  **sin escuchar**. Proceso vivo COLGADO (descargas S3 en vuelo cuando la red aún no estaba lista);
  `schtasks /Run` no hace nada por `IgnoreNew`. `RestartCount` no cubre este caso: la política de
  reinicio sólo aplica si el proceso **termina**.
- Fix de masvital (commit `10c34c1`, sólo `infra/guardian-bus-masvital.ps1`): watchdog de arranque
  en `run_api.py` (150 s sin escuchar → exit 1) + guardián que mata el proceso si la tarea lleva
  >6 min `Running` con `/health` caído. Evidencia: API arriba en 10 s, job resuelto en 145 s.
- **Divergencia a resolver por masvital:** `run_api.py` NO existe en este repo (ni en historial git).
  Es un lanzador local de ProDesk, así que su capa anti‑colgado no es reproducible desde el repo.
  Pedido en el bus: commitearlo o reemplazarlo por algo versionado.

**Estado en ESTE nodo — AUTOLOGON CONFIGURADO 2026-10-23 04:00Z (pendiente prueba de reinicio):**
- `net user MotoShop` → `Contraseña requerida: No` (cuenta sin contraseña). **No se tocó la clave**
  de la cuenta: cambiarla rompería DPAPI/vault.
- Aplicado en `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`:
  `AutoAdminLogon=1`, `DefaultUserName=MotoShop`, `DefaultDomainName=SERVER`, `DefaultPassword=""`
  (vacío porque la cuenta no tiene clave). Valores previos respaldados en
  `%TEMP%\opencode\winlogon_backup_20261023.txt`. Con clave real, usar Sysinternals Autologon.exe
  para que quede cifrada en LSA en vez de texto plano.
- Tarea API: `python.exe -m uvicorn motoshop_api.main:app --port 8000` directo (no hay `run_api.py`),
  `IgnoreNew`, `RestartCount=5 / PT1M`; arranca por `LogonTrigger` al entrar la sesión autologon
  (`BootTrigger` no aplica a tareas «solo cuando el usuario inició sesión»).
- Guardián: espera hasta 180 s a que la API responda antes del primer ciclo (commit `b60af37`) para
  no pelear con el arranque de la tarea de API.
- Alineación aplicada (commit `b31ec8e` en `infra/guardian-bus.ps1`): antes de recuperar, registra
  evidencia (`estado=listener_sin_health | COLGADA_proceso_vivo | caida_sin_proceso`, estado de la
  tarea, PIDs, dueño del puerto); si `start_api.ps1` no devuelve health en 25 s, mata **sólo los PIDs
  exactos** de `uvicorn|motoshop_api` y reintenta una vez. `start_api.ps1` ya mataba por cmdline y por
  dueño del puerto, así que el caso ProDesk (vivo sin escuchar) queda cubierto acá.
- Verificación del botón tras estos cambios (sin reiniciar): job `110d35ee` → `sin_coincidencia` en
  36 s, 3 movimientos, sin campo `error`.
- **Pendiente único**: reiniciar y confirmar sin tocar teclado: sesión inicia sola, `/health` 200,
  evidencia en `%TEMP%\guardian-banco.log` (`arranque: api=True`), latido del bus y un POST real.
  Rollback: restaurar `winlogon_backup_20261023.txt` (`AutoAdminLogon=0`).
- Tarea API: `python.exe -m uvicorn motoshop_api.main:app --port 8000` directo (no hay `run_api.py`),
  `IgnoreNew`, `RestartCount=5 / PT1M`.
- Alineación aplicada (commit `b31ec8e` en `infra/guardian-bus.ps1`): antes de recuperar, registra
  evidencia (`estado=listener_sin_health | COLGADA_proceso_vivo | caida_sin_proceso`, estado de la
  tarea, PIDs, dueño del puerto); si `start_api.ps1` no devuelve health en 25 s, mata **sólo los PIDs
  exactos** de `uvicorn|motoshop_api` y reintenta una vez. `start_api.ps1` ya mataba por cmdline y por
  dueño del puerto, así que el caso ProDesk (vivo sin escuchar) queda cubierto acá.

**Camino elegido (A): autologon + tarea «sólo cuando el usuario inició sesión».**
La tarea `MotoShopBackendSvc` ya corre como `SERVER\MotoShop` (`Solo interactivo`) con
`BootTrigger` + `LogonTrigger`, así que con el autologon el arranque queda cubierto. Comandos
(ejecutar como administrador, reemplazando `<CLAVE>`):

```powershell
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d 1 /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "MotoShop" /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "<CLAVE>" /f
```

Advertencia: `DefaultPassword` queda **en claro** en el registro (es el costo del autologon en
Windows local; una PC de local con acceso físico controlado es el único escenario aceptable).
Verificación posterior: reiniciar, esperar ~2 min, `curl http://127.0.0.1:8000/health` → 200 y un
POST de verificación de prueba.

**Camino B (descartado con evidencia): navegador headless.** `BANK_BROWSER_HEADLESS=true` →
`BankScrapeError portal_no_disponible` (timeout de 30 s esperando `input#username`): el portal de
Bancolombia no entrega el login sin ventana en este nodo. No insistir sin probar contra el portal
primero.

**Camino C (descartado): tarea «aunque el usuario no haya iniciado sesión» (S4U).** Rompe el
vault: DPAPI y `%APPDATA%` son por usuario y sin sesión interactiva no hay perfil → `credencial_ausente`
(ver sección anterior). No re-crear el vault bajo `SYSTEM`.
