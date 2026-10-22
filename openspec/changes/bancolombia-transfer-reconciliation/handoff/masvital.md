# Handoff — PC MasVital

Prompt para el agente de la máquina de MasVital. **Ejecutá sólo lo que dice acá** y reportá la
salida de cada comando. Si algo no coincide con lo esperado, **pará y reportá**: no improvises, no
edites catálogos y no cambies variables que no estén listadas.

Contexto: la conciliación de transferencias bancarias ya está implementada en el repo y debe
funcionar para MasVital igual que para MotoShop. Falta dejar este nodo listo con **sus** valores
(tenant, base, etiqueta de cuenta, credencial y forma de pago).

---

## Reglas de la tarea

- **No** modifiques `formapago`, `facventas`, `consbancab` ni ningún catálogo. Esta tarea **no
  escribe** en las tablas legacy.
- **No** adivines el `codpag` de transferencia. Si no lo podés confirmar con datos, el paso queda
  **pendiente** y lo reportás: el sistema está diseñado para fallar cerrado en ese caso.
- **No** cambies `MYSQL_*`, `R2_*`, `BANK_TENANT`, `BANK_ACCOUNT_LABEL`, `BANK_CREDENTIAL_ENTRY`
  ni `BANK_PROFILE_DIR` si ya tienen valor. Sólo agregás lo que falta.
- **No** copies valores de MotoShop. El catálogo de formas de pago, la base y la etiqueta de cuenta
  son de esta empresa.
- Antes de aplicar migraciones, **respaldá** la base: `mysqldump --single-transaction <DB> > backup-f9-$(date +%F).sql`.
- Reportá: versión de MySQL, nombre de la base, salida de cada comando y cualquier error textual.

## Paso 1 — Código

```bash
git fetch --all
git checkout feat/banco-transfer-25-tenant-config   # rama explícita: NO uses main
git pull
cd motoshop-app/api && uv sync
```

Verificá que `tenants.yaml` tenga `bank-reconciliation` en `enabled_features` del tenant
`masvital` y que su bloque `erp` tenga `enabled: true` con la `empresa` correcta. Si falta algo,
**pará y reportá**.

## Paso 2 — Migraciones F9 (DDL + grants)

Son cuatro archivos: dos crean tablas (`app_bank_movements`, `app_bank_verification_jobs`) y dos
dan permisos a `app_writer`. Van a **la base de esta máquina** (`MYSQL_DATABASE` de MasVital), no a
la de MotoShop. Las tablas se comparten entre tenants dentro de esa base mediante la columna
`tenant`, pero **las migraciones se aplican una vez por base**.

```bash
# desde la raíz del repo, con un usuario privilegiado (no app_writer)
python -m infra.migrations.run_migrations --prefix F9 --database <MYSQL_DATABASE de esta máquina>
```

- Debe aplicar `F9-001` a `F9-004` y registrar el estado en `app_migration_state`.
- **Corré el mismo comando una segunda vez**: tiene que ser no-op.
- `app_writer` tiene que existir (si no, primero `F5-003`).

Verificación:

```sql
SHOW TABLES LIKE 'app_bank%';
SELECT name, applied_at FROM app_migration_state WHERE name LIKE 'F9-%';
```

Esperado: las dos tablas y cuatro filas de estado.

## Paso 3 — El `codpag` real de transferencia (sólo lectura)

```sql
SELECT codpag, forpag, codban, codcue FROM formapago;
```

Reportá la lista completa con los nombres tal como están. Necesito saber **cuál es el código de la
transferencia/consignación bancaria en MasVital**. No lo deduzcas si hay dudas: reportá y esperá
confirmación.

## Paso 4 — Variables de entorno (sólo cuando el paso 3 esté confirmado)

En el `.env` de **esta máquina**:

```dotenv
BANK_TENANT=masvital
BANK_SCRAPER_ENABLED=true
BANK_CREDENTIAL_ENTRY=bancolombia-masvital
BANK_CODPAG_TRANSFERENCIA_MASVITAL=<codpag confirmado>
```

- Si `BANK_TENANT`, `BANK_SCRAPER_ENABLED`, `BANK_CREDENTIAL_ENTRY` o `BANK_PROFILE_DIR` ya tienen
  valor, **no los toques**: sólo verificá que coincidan con lo de arriba.
- `BANK_ACCOUNT_LABEL` tiene que ser la **etiqueta real de la cuenta de MasVital** en el portal (no
  el número de cuenta, no la etiqueta de MotoShop). Si no la sabés, reportala como pendiente: es lo
  único que evita abrir la cuenta equivocada.
- El `codpag` va **por tenant**. Sin esta variable, aplicar responde **409
  `codpag_no_confirmado`** y el movimiento queda pendiente: eso es el comportamiento correcto.

## Paso 5 — Credencial del portal, perfil y navegador

```bash
# si la entrada no existe todavía (el CLI pide usuario, clave y frase sin eco)
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend passphrase set bancolombia-masvital

# perfil del navegador fuera del repo y con permisos 700
mkdir -p "$APPDATA/motoshop/bank-profile/masvital"   # Windows
# Linux/macOS: mkdir -p ~/.config/motoshop/bank-profile/masvital && chmod 700 ...

uv run playwright install chromium
```

La entrada es **de este tenant**: `bancolombia-masvital`. Nunca reutilices la de MotoShop.

## Paso 6 — Preflight del nodo (sin tocar el portal)

```bash
uv run python scripts/bank_verify.py --tenant masvital
```

Esperado: `PREFLIGHT OK: el nodo 'masvital' está listo.` y código de salida `0`. Si falla por
vault, perfil o etiqueta, reportá el código de error tal cual y **no** sigas.

## Paso 7 — API arriba y verificación de lectura

Reiniciá la API y consultá, con un usuario con rol de cobranzas de MasVital:

```bash
curl -s -H "Authorization: Bearer <token>" -H "X-Tenant: masvital" \
  https://<host-de-esta-maquina>/api/erp/bank/sync-status
```

Esperado: **200** con `scraperHabilitado: true`, `nodo` con la etiqueta de la cuenta y `ventana`
del día en curso. Un **503 `tenant_no_servido`** significa que `BANK_TENANT` no es `masvital`.

Después:

```bash
curl -s -H "Authorization: Bearer <token>" -H "X-Tenant: masvital" \
  https://<host-de-esta-maquina>/api/erp/bank/movements
```

Esperado: **200** con `{"movimientos": []}` (o los que ya existan), y **nunca** movimientos de
MotoShop: el tenant sale del request, no de un parámetro.

## Paso 8 — Reporte final

Devolvé exactamente esto:

1. Salida de la segunda corrida de migraciones (no-op) y las filas de `app_migration_state`.
2. La lista de `formapago` del paso 3 y qué código se confirmó.
3. Salida del preflight.
4. Código HTTP y cuerpo de `sync-status` y `movements`.
5. El `BANK_ACCOUNT_LABEL` usado (o marcado pendiente) y cualquier paso pendiente con su motivo.

No ejecutes una conciliación real ni apliques una transferencia: eso lo decide el operador desde la
UI, con la revisión posterior.
