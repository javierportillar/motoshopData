# Handoff — PC MotoShop

Prompt para el agente de la máquina de MotoShop. **Ejecutá sólo lo que dice acá** y reportá la
salida de cada comando. Si algo no coincide con lo esperado, **pará y reportá**: no improvises, no
edites catálogos y no cambies variables que no estén listadas.

Contexto: la conciliación de transferencias bancarias ya está implementada en el repo. Falta
dejar este nodo listo. La misma tarea existe para MasVital con sus propios valores.

---

## Reglas de la tarea

- **No** modifiques `formapago`, `facventas`, `consbancab` ni ningún catálogo. Esta tarea **no
  escribe** en las tablas legacy.
- **No** adivines el `codpag` de transferencia. Si no lo podés confirmar con datos, el paso queda
  **pendiente** y lo reportás: el sistema está diseñado para fallar cerrado en ese caso.
- **No** cambies `MYSQL_*`, `R2_*`, `BANK_TENANT`, `BANK_ACCOUNT_LABEL`, `BANK_CREDENTIAL_ENTRY`
  ni `BANK_PROFILE_DIR` si ya tienen valor. Sólo agregás lo que falta.
- Antes de aplicar migraciones, **respaldá** la base: `mysqldump --single-transaction <DB> > backup-f9-$(date +%F).sql`.
- Reportá: versión de MySQL, nombre de la base, salida de cada comando y cualquier error textual.

## Paso 1 — Código

```bash
git fetch --all
git checkout feat/banco-transfer-25-tenant-config   # o main, si ya está mergeado
git pull
cd motoshop-app/api && uv sync
```

Verificá que el archivo `tenants.yaml` tenga `bank-reconciliation` en `enabled_features` del tenant
`motoshop`. Si no está, **pará y reportá**.

## Paso 2 — Migraciones F9 (DDL + grants)

Son cuatro archivos: dos crean tablas (`app_bank_movements`, `app_bank_verification_jobs`) y dos
dan permisos a `app_writer`. Van a **la base que usa esta máquina** (`MYSQL_DATABASE`), no a otra.

```bash
# desde la raíz del repo, con un usuario privilegiado (no app_writer)
python -m infra.migrations.run_migrations --prefix F9 --database <MYSQL_DATABASE de esta máquina>
```

- Debe aplicar `F9-001` a `F9-004` y registrar el estado en `app_migration_state`.
- **Corré el mismo comando una segunda vez**: tiene que ser no-op (ninguna migración pendiente).
- `app_writer` tiene que existir (si no, primero `F5-003`).

Verificación:

```sql
SHOW TABLES LIKE 'app_bank%';
SELECT name, applied_at FROM app_migration_state WHERE name LIKE 'F9-%';
```

Esperado: las dos tablas y cuatro filas de estado.

## Paso 3 — El `codpag` real de transferencia (sólo lectura)

Este dato es el único que puede bloquear el despliegue. Consultalo y **reportá la lista completa**:

```sql
SELECT codpag, forpag, codban, codcue FROM formapago;
```

Necesito saber **cuál de esos códigos es la transferencia/consignación bancaria** según el negocio
de MotoShop. No lo deduzcas por el nombre si hay dudas: reportá las filas y esperá confirmación.

## Paso 4 — Variable de entorno (sólo cuando el paso 3 esté confirmado)

En el `.env` de **esta máquina**:

```dotenv
BANK_CODPAG_TRANSFERENCIA_MOTOSHOP=<codpag confirmado>
```

- Una sola API sirve a varias empresas: el código va **por tenant**. No uses el global
  `BANK_CODPAG_TRANSFERENCIA` salvo que esta máquina sirva un único tenant.
- Sin esta variable, aplicar una transferencia responde **409 `codpag_no_confirmado`** y el
  movimiento queda pendiente. Eso es correcto, no un bug.

## Paso 5 — Credencial del portal y navegador

```bash
# si la entrada no existe todavía (el CLI pide usuario, clave y frase sin eco)
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend passphrase set bancolombia-motoshop

uv run playwright install chromium
```

La entrada es **de este tenant**: `bancolombia-motoshop`. Nunca reutilices la de MasVital.

## Paso 6 — Preflight del nodo (sin tocar el portal)

```bash
uv run python scripts/bank_verify.py --tenant motoshop
```

Esperado: `PREFLIGHT OK: el nodo 'motoshop' está listo.` y código de salida `0`. Si falla por
vault o por perfil, reportá el código de error tal cual (`vault_no_accesible`, `perfil_invalido`,
etc.) y **no** sigas.

## Paso 7 — API arriba y verificación de lectura

Reiniciá la API y consultá, con un usuario con rol de cobranzas:

```bash
curl -s -H "Authorization: Bearer <token>" -H "X-Tenant: motoshop" \
  https://<host-de-esta-maquina>/api/erp/bank/sync-status
```

Esperado: **200** con `scraperHabilitado: true`, `nodo` con la etiqueta de la cuenta y `ventana`
con el día en curso. Un **503 `tenant_no_servido`** significa que `BANK_TENANT` no es `motoshop`:
un proceso sirve un solo tenant.

Después:

```bash
curl -s -H "Authorization: Bearer <token>" -H "X-Tenant: motoshop" \
  https://<host-de-esta-maquina>/api/erp/bank/movements
```

Esperado: **200** con `{"movimientos": []}` (o los movimientos que ya existan). Si responde **500**
`La ruta no tiene una política de módulos configurada`, el deploy quedó con código viejo: repetí el
paso 1.

## Paso 8 — Reporte final

Devolvé exactamente esto:

1. Salida de la segunda corrida de migraciones (no-op) y las filas de `app_migration_state`.
2. La lista de `formapago` del paso 3 (sin datos sensibles) y qué código se confirmó.
3. Salida del preflight.
4. Código HTTP y cuerpo de `sync-status` y `movements`.
5. Cualquier paso que hayas dejado pendiente y por qué.

No ejecutes una conciliación real ni apliques una transferencia: eso lo decide el operador desde la
UI, con la revisión posterior.
