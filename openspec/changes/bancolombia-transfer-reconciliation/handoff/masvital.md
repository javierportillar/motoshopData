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
- Los `codpag` **ya están confirmados con datos** (`F07` transferencia, `F05` consignación): el
  Paso 3 sólo verifica que existan en esta base. No los reemplaces por uno inventado ni copies el
  de otra empresa.
- **No** cambies `MYSQL_*`, `R2_*`, `BANK_TENANT`, `BANK_CREDENTIAL_ENTRY` ni `BANK_PROFILE_DIR` si
  ya tienen valor: sólo verificá que coincidan. Si `BANK_ACCOUNT_LABEL` ya tiene un valor distinto
  de `MasVital`, reportalo antes de tocarlo.
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

## Paso 3 — Verificar los `codpag` en `formapago` (sólo lectura)

Los códigos ya están confirmados contra los datos, no por el nombre:

- **transferencia** (recibo de factura pagada por transferencia) ⇒ `F07`;
- **consignación** (plata que entra sin factura) ⇒ `F05`.

Los dos están confirmados en esta base (y en `sgHermes`): `F05 CONSIGNACION BANCO....` y
`F07 TRANSFERENCIA BANCO....`, ambas con `codcue = 11100501` y `codban` vacío. Verificá igual:

```sql
SELECT codpag, forpag, codban, codcue FROM formapago WHERE codpag IN ('F05','F07');
SELECT codpag, COUNT(*) FROM detapago GROUP BY codpag ORDER BY 2 DESC;
```

Reportá las dos salidas tal cual. Si `F05` no existiera o su `forpag` no fuera una consignación
bancaria, **no** definas `BANK_CODPAG_CONSIGNACION_MASVITAL` y reportalo: no reutilices `F07` como
consignación. El diseño separa transferencia (recibo `S01`) de consignación (documento `CC`) por
`factura_id`, así que compartir `codcue` no las cruza.

## Paso 4 — Variables de entorno (sólo cuando el paso 3 esté confirmado)

En el `.env` de **esta máquina**:

```dotenv
BANK_TENANT=masvital
BANK_SCRAPER_ENABLED=true
BANK_CREDENTIAL_ENTRY=bancolombia-masvital
BANK_ACCOUNT_LABEL=MasVital
BANK_CODPAG_TRANSFERENCIA_MASVITAL=F07
BANK_CODPAG_CONSIGNACION_MASVITAL=F05
```

`BANK_ACCOUNT_LABEL=MasVital` es la etiqueta de la tarjeta del home del portal (cuenta
879-000605-71). La comparación es **exacta** (normaliza espacios y mayúsculas): si el portal
muestra otro texto, el scrape falla con `cuenta_no_encontrada` y hay que corregir la etiqueta, no
el número.

- Si `BANK_TENANT`, `BANK_SCRAPER_ENABLED`, `BANK_CREDENTIAL_ENTRY` o `BANK_PROFILE_DIR` ya tienen
  valor, **no los toques**: sólo verificá que coincidan con lo de arriba.
- `BANK_ACCOUNT_LABEL` es la **etiqueta** de la tarjeta, no el número de cuenta ni la etiqueta de
  MotoShop: es lo único que evita abrir la cuenta equivocada. En esta máquina es `MasVital`.
- Los `codpag` van **por tenant y por tipo**. El global `BANK_CODPAG_TRANSFERENCIA` sólo existe
  para compatibilidad de procesos de una sola empresa; en esta máquina usá las variables
  específicas. El código de transferencia **no** se usa como consignación: son formas de pago
  distintas.
- Sin la variable que corresponda, aplicar responde **409 `codpag_no_confirmado`** y el movimiento
  queda pendiente: eso es el comportamiento correcto.

## Paso 5 — Credencial del portal, perfil y navegador

```bash
# si la entrada no existe todavía (el CLI pide usuario, clave y frase sin eco)
uv run python -m motoshop_api.erp.bankreconciliation.cli --backend dpapi set bancolombia-masvital

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

## Paso 6.5 — Arreglos de infraestructura autorizados

Dos bugs del arnés, **no** de la change. Van en commits separados sobre la misma rama, cada uno con
su test y con la suite completa en verde:

1. **`run_migrations.py --prefix`** aborta con `MissingSqlFileError` porque `validate_order` exige
   que toda fila de `app_migration_state` tenga archivo, pero `discover_f8_files` filtra por
   prefijo. Arreglo: filtrar `applied_names` y `checksums` por el prefijo de la corrida (prefijo =
   `nombre.split("-", 1)[0]`) antes de validar. Test de regresión en `tests/test_erp_migrations.py`:
   estado con F8 registrado + corrida `--prefix F9` aplica F9 y no exige F8; segunda corrida es
   no-op.
2. **`UnicodeEncodeError` en consola cp1252** al imprimir `→`: en el entrypoint del runner,
   `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (y `stderr` si hace falta). No
   cambies el texto de los mensajes.

Nada de esto toca datos ni migraciones aplicadas. **No** registres `F8-004` a mano en
`app_migration_state`: queda documentado como aplicado por fuera del runner y un futuro `--prefix F8`
lo verá pendiente (el GRANT es idempotente).

## Paso 6.6 — Defectos encontrados en la revisión

Tres defectos de lo ya entregado. Dos ya están corregidos en la rama (`e0ae132` y el commit de
imports); **sólo queda el lock de Windows**. Cada arreglo va en su commit, con la suite completa en
verde antes de seguir.

### 1. Mojibake en `F9-002` y `F9-004` — corregido en `e0ae132`

Los archivos ahora están en UTF-8 real, sin BOM. Lo único que puede quedar pendiente es el
**estado**: el checksum registrado en `app_migration_state` es el del archivo con mojibake, así que
el runner puede abortar con `ChecksumMismatchError`. Si aparece:

- calculá el checksum **con la función del runner** (nunca `sha256sum`, que no normaliza fines de
  línea). Con los archivos de `e0ae132` tiene que dar exactamente:

  ```
  F9-002  12cd6c540db18b4a9712581f3833d09a6c544730ae8fec2f3cf3a7a9d78b18fc
  F9-004  d56581a294cd2607e9552195a1687337c3d88cec1d93a7117bbba91cf0e47cd2
  ```

  Si no coincide, no sigas: el archivo no es el de la rama. Comando:

  ```bash
  python -c "from pathlib import Path; from infra.migrations.run_migrations import sha256_file; print(sha256_file(Path('infra/migrations/F9-002-grant_app_writer_bank.sql')))"
  ```

- confirmá con `split_statements` que las sentencias son idénticas a las que ya corrieron: en el
  archivo sólo cambiaron comentarios;
- actualizá el estado con ese valor:

  ```sql
  UPDATE app_migration_state SET checksum = '<nuevo>' WHERE migration_name = 'F9-002-grant_app_writer_bank.sql';
  ```

  Ídem `F9-004`.
- Verificación: segunda corrida no-op. Si el mismatch persiste, **no borres la fila**: reportá.

### 2. `ruff I001` en `tests/test_bank_vault.py` — corregido

Era sólo el orden de imports; ya está arreglado en la rama. `uv run ruff check .` tiene que quedar
limpio.

### 3. Lock de Windows (`PermissionError [WinError 32]`) — pendiente, bloqueante del scraper

`_Candado.liberar()` (`erp/bankreconciliation/scraper.py`, ~387) en Windows hace
`self._ruta.unlink()` con el descriptor **todavía abierto**: Windows no permite borrar un archivo
con un handle vivo. Con `fcntl` disponible (POSIX) nunca se ve; por eso la rama Windows está
`# pragma: no cover` y pasó la suite.

Orden correcto en `liberar()`:

1. sacar `self._fd` del estado y **cerrar el handle** (`os.close`);
2. recién ahí `unlink`, con hasta 5 reintentos y 50 ms entre intentos (un antivirus puede tener el
   archivo tomado un instante);
3. idempotente: si `_fd` es `None`, no hace nada.

Tests (sacando el `pragma: no cover` de la rama):

- simulando Windows con `monkeypatch.setattr(scraper, "fcntl", None)`: `adquirir()` + `liberar()`
  dos veces no lanza y el archivo no queda;
- `Path.unlink` que falla con `PermissionError` la primera vez y funciona en el reintento: no lanza
  y el archivo se borra.

## Paso 6.7 — Portabilidad de la suite en Windows

La suite medida en este nodo da 59 fallas sobre un baseline de 69. Unas 13 son el lock del Paso
6.6.3 (bug real). Las otras ~42 son **tests que asumen POSIX**, no bugs del código: fijan
`XDG_CONFIG_HOME` y el código en Windows resuelve `%APPDATA%` (`node_config.py:216`,
`vault.py:106`), usan keychain con pseudo-terminal, o esperan que DPAPI no exista.

Arreglo, con un commit `test(banco): ...` y sin tocar lógica de producción:

1. Un helper compartido (en el `conftest.py` de los tests del módulo) que fije la variable que el
   código realmente lee según la plataforma: `APPDATA` en Windows, `XDG_CONFIG_HOME` en POSIX.
   Reemplazá los `monkeypatch.setenv("XDG_CONFIG_HOME", ...)` por ese helper. Nada de duplicar la
   regla: si podés, resolvé la ruta con la misma función que usa el código.
2. `pytest.mark.skipif` **sólo** para lo que no existe en la plataforma: backend `keychain` con
   pseudo-terminal y las expectativas de ausencia de DPAPI. Cada skip con `reason=` que nombre la
   capacidad que falta. Nada de `skip` genérico por `sys.platform` a nivel módulo.
3. No debilites aserciones para que pasen: si un test falla por una diferencia real de
   comportamiento, es un hallazgo y va al reporte, no un skip.

Aceptación: volvé a medir la suite completa y reportá el número final de fallas y de skips. Los
tests del módulo bancario tienen que pasar **enteros** en Windows (salvo los skips justificados);
las fallas que queden no pueden ser del módulo bancario ni del lock.

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
