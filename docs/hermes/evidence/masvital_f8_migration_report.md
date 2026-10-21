# Migración F8 sobre la base viva MasVital (MySQL 5.0.45)

> Fecha: 2026-10-21
> Host: `DESKTOP-LDJR4PC`
> Servidor: `5.0.45-community-nt` en `localhost:3306` (servicio `MySQL`, PID 3536)
> Base objetivo: `masvital`
> Objetivo: habilitar las escrituras transaccionales del POS Web sobre la base viva del ERP
> legacy, con journal de documentos, idempotencia y numeración protegida por índice único.

---

## 1. Resumen ejecutivo

| # | Acción | Estado |
|---|--------|--------|
| 1 | Backup completo previo a DDL | ✅ 33,56 MB / 179 tablas / `Dump completed` |
| 2 | `F8-001` journal de documentos | ✅ aplicada |
| 3 | `F8-002` idempotencia | ✅ aplicada |
| 4 | `F8-003` índice único de documentos | ✅ aplicada, `CHECK TABLE` OK |
| 5 | `F8-004` grants de `app_writer` | ⚠️ **no** vía runner (defecto del archivo), grants aplicados manualmente |
| 6 | Usuario `app_writer` con password fuerte | ✅ creado, hash `*E0727E12…`, password vacío rechazado |
| 7 | Variables `MYSQL_*` en `.env` | ✅ (`.env` ignorado por git) |
| 8 | `tenants.yaml`: MasVital ERP habilitado | ✅ `enabled: true`, `empresa: "E01"` |
| 9 | Reinicio del backend para invalidar el caché de tenants | ✅ `/health` 200 en ~4 s |
| 10 | Suite ERP (concurrencia + POS + guards) | ✅ **32/32** |
| 11 | Suite completa como control de regresión | ✅ **sin regresiones** (22F/11E idénticos antes y después) |
| 12 | Convivencia con el POS legacy | ✅ factura 3552 creada **después** del `ALTER` |
| 13 | Write path del POS Web contra el esquema real | ✅ **resuelto y verificado end-to-end — ver §9** |

**Resultado:** la infraestructura está lista — base migrada, usuario de escritura con grants,
tenant habilitado, backend reiniciado y el POS legacy convive con el índice único. **Pero el POS
Web todavía NO puede guardar una venta**: el camino de escritura real genera columnas que no
existen en el esquema legacy (§9). La migración F8 cumple su parte; falta el mapper de columnas
del writer.

---

## 2. Preflight: estado verificado antes de tocar el motor

| Verificación | Resultado |
|---|---|
| Versión / motor | `5.0.45-community-nt`, InnoDB disponible (`DEFAULT`) |
| Tablas antes | 179, **todas MyISAM**, `latin1` / `latin1_swedish_ci` |
| `sql_mode` | `STRICT_TRANS_TABLES,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION` |
| `facventas` filas | 3.547 al inicio del análisis → **3.551** al migrar (el POS estaba vendiendo) |
| NULL en `(codclas, prefven, numfven)` | **0 / 0 / 0** |
| Grupos duplicados en esa clave | **0** |
| Valores de `codclas` / `prefven` | `S15` / `FVP` en el 100 % de las filas |
| Usuario `app_writer` | **no existía** |
| Grants de `api_read@localhost` | `USAGE` + `SELECT ON masvital.*` |
| Tamaño de la base | 17,61 MB / 179 tablas |

Dos consecuencias operativas de este preflight:

1. `NO_AUTO_CREATE_USER` implica que un `GRANT` a un usuario inexistente **falla**: hay que
   `CREATE USER` primero.
2. Como no hay NULLs ni duplicados, el índice único es efectivo **de verdad** y no queda como
   adorno (MySQL permite múltiples `NULL` en un índice único).

---

## 3. Backup previo al DDL

| Archivo | Tamaño | Contenido |
|---|---|---|
| `%TEMP%\opencode\backup_masvital_pre_f8.sql` | 33,56 MB | Base completa, 179 `CREATE TABLE`, cierre `Dump completed on 2026-10-21 16:47:15` |
| `%TEMP%\opencode\backup_facventas_pre_f8.sql` | 2,51 MB | Dump focalizado de `facventas` con lock breve |

El dump completo se tomó con `--skip-lock-tables --quick` para **no bloquear al POS en
producción**. `mysqldump` 5.0 no soporta `--events` (falla con `unknown option`); ese fue el
único ajuste necesario respecto del comando del runbook.

---

## 4. Migraciones aplicadas

Runner: `python -m infra.migrations.run_migrations --database masvital --user root`
(salida: `Run complete: 3 applied in this run.`)

| Migración | Check de estado (SHA-256) | `applied_at` |
|---|---|---|
| `F8-001-app_doc_journal.sql` | `cb8e80cfab7cdbda1dbffeb14057cf06daaa746fea7cb1ed7f91688cdeea086d` | 2026-10-21 11:47:46 |
| `F8-002-app_idempotency.sql` | `bb89c57f8f68ce43bc143ffcebe11bc8d174839e2cb0c495a7af0c8f4758b29a` | 2026-10-21 11:47:46 |
| `F8-003-unique_doc_indexes.sql` | `68f85696465ccc496ef99cc40c32c23aaabd967a54892f74906e8222532dffe9` | 2026-10-21 11:47:46 |

Verificación posterior en el motor:

```
app_doc_journal      InnoDB  utf8_unicode_ci
app_idempotency      InnoDB  utf8_unicode_ci
app_migration_state  InnoDB  utf8_unicode_ci

uq_facventas_doc  (codclas, prefven, numfven)  Non_unique=0  BTREE  cardinality 3551
CHECK TABLE masvital.facventas -> status OK
```

Las tablas nuevas viven en InnoDB (`utf8_unicode_ci`) dentro de una base `latin1`/MyISAM: es
deliberado, el journal y la idempotencia necesitan transacciones y bloqueo por fila que MyISAM
no ofrece.

Estado final del esquema: **182 tablas = 179 MyISAM + 3 InnoDB**.

---

## 5. `F8-004`: defecto detectado y desviación del runbook

`infra/migrations/F8-004-grant_app_writer_erp.sql` tiene la base **codificada a `motoshop2024`**.
El runner descubre todo archivo con prefijo `F8-`, de modo que si se ejecuta desde la raíz del
repo **intenta aplicar `F8-004` y falla** (la base no existe en este host).

Decisión tomada:

- Se aplicaron `F8-001…003` usando un directorio temporal con copias de esos tres archivos, para
  no mutar el repositorio ni dejar el estado de migraciones en una posición falsa.
- Los `GRANT` se aplicaron **a mano** contra `masvital`, tal como el propio archivo documenta
  ("checkpoint applied by whoever operates the checkpoint environment").

**Deuda pendiente:** `F8-004` sigue siendo una mina para el próximo operador. Si alguien corre el
runner desde la raíz del repo, va a fallar en ese archivo. Hay que volverlo
independiente de la base (o sacarlo del patrón de descubrimiento) antes de automatizar el runner
en CI o en un arranque desatendido.

---

## 6. Usuario `app_writer`

Creado en `localhost` con password aleatorio de 32 caracteres alfanuméricos (guardado **solo** en
`.env`, fuera de git). Hash almacenado: `*E0727E12…` (nunca texto plano).

Grants otorgados sobre `masvital`:

| Tabla | Permisos | Motivo |
|---|---|---|
| `app_doc_journal`, `app_idempotency`, `app_migration_state` | `SELECT, INSERT, UPDATE` | journal, idempotencia, control de migraciones |
| `facventas`, `detfventas`, `detapago`, `detcuentas`, `compras`, `detcompras` | `SELECT, INSERT, UPDATE` | documentos y sus líneas |
| `productos`, `ubiprodbod`, `contadores` | `SELECT, UPDATE` | stock y consecutivos |

No se otorgó `DELETE` ni `GRANT OPTION`: la anulación de documentos es lógica (auditoría), no
borrado físico.

Pruebas de acceso:

```
mysql -u app_writer --password=<nueva>  -> app_writer@localhost, SELECT sobre facventas OK
mysql -u app_writer --password=""       -> ERROR 1045 (Access denied ... using password: NO)
```

> Incidencia durante el procedimiento: el primer `CREATE USER` se ejecutó con password vacío
> porque un error de sintaxis de PowerShell (`<` como redirección) abortó el script antes de
> generar la variable. Se corrigió de inmediato con `SET PASSWORD` y se verificó que el acceso sin
> password queda rechazado. La ventana de exposición fue de segundos y en `localhost`.

---

## 7. Configuración de la aplicación

### 7.1 `.env` (raíz del repo; ignorado por git, regla `.gitignore:41`)

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=masvital
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_APP_WRITER_USER=app_writer
MYSQL_APP_WRITER_PASSWORD=<32 chars, no versionado>
```

`_candidate_env_paths()` carga primero `motoshop-app/api/.env` y después el `.env` de la raíz;
**la raíz gana**, por eso el bloque se escribió ahí.

Verificación de settings y conectividad de ambos engines:

```
db      : masvital
read    : root | pwd len 0
writer  : app_writer | pwd len 32
writer -> app_writer@localhost @ masvital
erp    -> app_writer@localhost @ masvital
```

### 7.2 `tenants.yaml` — desviación necesaria

El pedido asumía que MasVital ya estaba habilitado para escrituras. **No lo estaba**:

```diff
     mysql_source: "masvital_pos"
     erp:
-      enabled: false   # transactional writes are MotoShop-only (WF-3s1)
-      empresa: ""
+      enabled: true
+      empresa: "E01"
```

Sin este cambio el POS Web responde **403 "no está habilitado"** y no persiste ninguna venta. La
`empresa: "E01"` es la que el legacy tiene activa en `SgHermes`.

> Cambio paralelo: al momento de pushear, el remoto ya contenía `b9788e5 feat(erp): enable
> masvital tenant for transactional writes`, que aplica este mismo bloque y además corrige
> `mysql_source: "masvital_pos"` → `"masvital"`. El commit local se redujo al presente informe:
> la configuración vigente es la de `b9788e5`, verificada con el backend en ejecución.

El caché de tenants (`_tenants_cache`) se llena de forma perezosa y **nunca se invalida por
`mtime`**, así que fue necesario reiniciar el backend. Verificado:

```
yaml modificado : 2026-10-21 11:49:16
proceso inicio  : 2026-10-21 11:58:47
restart posterior al cambio: True
motoshop  erp.enabled=True empresa='E01'
masvital  erp.enabled=True empresa='E01'
```

---

## 8. Verificación

### 8.1 Suite ERP objetivo

```
tests\test_erp_integration_concurrency.py
tests\test_erp_pos.py
tests\test_erp_guards.py
-> 34 passed in 31.39s
```

Incluye, contra MySQL 5.0 real (schema aislado `motoshop_erp_test`):

- reservas concurrentes que devuelven números **distintos**;
- el lock del escritorio bloquea la reserva web (convivencia legacy ↔ web);
- el índice único **rechaza** un número de documento duplicado.

Se actualizó una aserción en `tests/test_erp_guards.py::test_tenants_yaml_erp_block_loads_into_model`,
que codificaba la política vieja (`masvital.erp.enabled is False`). Ahora exige
`enabled is True` y `empresa == "E01"`: es el contrato nuevo, no un test relajado.

### 8.2 Control de regresión

Suite completa sobre `b9788e5`: **949 tests** → `22 failed, 909 passed, 8 skipped, 11 errors`.

Para descartar que esos fallos vinieran de este cambio, se corrió el mismo subconjunto con el
`tenants.yaml` **original** (`git checkout`), sobre la base `6fff717`:

| Estado | Resultado |
|---|---|
| Con el cambio aplicado | 22 failed, 11 errors |
| Con `tenants.yaml` original | **22 failed, 11 errors** |

Idénticos → **cero regresiones**. Los fallos son ambientales y preexistentes (rutas `/tmp` de
DuckDB en Windows, `C:/Users/MotoShop/...` inexistente en este host, Supabase, rate-limit).

### 8.3 Convivencia con el POS legacy

| Hora | Evento |
|---|---|
| 11:47:06 | backup focalizado de `facventas` |
| 11:47:46 | `F8-003` aplicada (índice único) |
| **11:58:17** | **factura 3552 insertada por `SgHermes.exe`** |
| 11:58:47 | reinicio del backend web |

`SgHermes.exe` (PID 2792) sigue `Responding`, con su conexión viva a `masvital` (conn 342).
Grupos duplicados después de la migración: **0**.

Esto es la prueba más importante del reporte: **el POS legacy sigue vendiendo con el índice único
activo**, sin colisiones y sin errores.

---

## 9. Write path real: bloqueante detectado y resuelto

El objetivo era "dejar la base operativa para recibir ventas del POS Web". La infraestructura sí
quedó operativa; la **persistencia de la venta no**. El camino real usaba nombres de columna que no
existen en el esquema heredado. **Estado: resuelto y verificado end-to-end** (commit `ab02482`,
§9.3); este apartado conserva el diagnóstico porque explica por qué la suite no lo detectó.

### Evidencia

`erp/pos/router.py:230` inyecta `get_invoices_repo()` → `RealInvoicesRepo`
(`erp/invoicing/repo.py:551`), que **no sobrescribe** `_persist` (`erp/invoicing/repo.py:417`).
Ese método arma las filas así:

| Tabla | Columnas generadas | Inexistentes en el esquema real |
|---|---|---|
| `facventas` | `...`, `actor`, `empresa` | **`actor`, `empresa`** |
| `detfventas` | `...`, `prefven`, `numlin` | **`prefven`, `numlin`** (el legacy usa `numite`) |
| `detapago` | `...`, `numfven`, `prefven`, `referencia` | **`numfven`, `prefven`, `referencia`** (el legacy usa `numnum`, `predoc`) |
| `detcuentas` | `...`, `numfven`, `prefven`, `valcre`, `nitope` | **`numfven`, `prefven`, `valcre`, `nitope`** (el legacy usa `numnum`, `valhab`, `nitter`) |

Prueba empírica contra un clon estructural de las tablas reales (`masvital_probe`, eliminado
después): los **4 INSERT fallan** con error del motor.

```
facventas  -> ERROR 1054 (42S22): Unknown column 'actor' in 'field list'
detfventas -> ERROR 1054 (42S22): Unknown column 'prefven' in 'field list'
detapago   -> ERROR 1054 (42S22): Unknown column 'numfven' in 'field list'
detcuentas -> ERROR 1054 (42S22): Unknown column 'numfven' in 'field list'
```

### Por qué las pruebas no lo detectaron

- `tests/test_erp_pos.py` y los guards corren con `ENV=test` → `get_invoice_store()` devuelve
  `FakeInvoiceStore` (`erp/invoicing/store.py:145`), que nunca toca MySQL.
- `tests/test_erp_integration_concurrency.py` **sí** usa MySQL real, pero crea un schema
  **sintético** (`contadores` de 10 columnas, `facventas` de 5) que solo valida numeración e
  índice único, no el INSERT real.
- El esquema documentado de MotoShop (`docs/hermes/evidence/schema_2024.sql`) **tampoco** tiene
  esas columnas: el defecto no es específico de MasVital; el writer real nunca corrió contra un
  esquema legacy.

### Impacto operativo (mientras estuvo abierto)

Con `erp.enabled: true`, una venta desde el POS Web devolvía **500** en lugar del 403 limpio
anterior. **No hubo riesgo de corrupción**: el INSERT abortaba antes de escribir. El POS legacy
nunca se vio afectado.

### Resolución

Se implementó la opción 1 y, al ejecutarla contra MySQL real, aparecieron **dos defectos más** que
la suite hermética también ocultaba. Los tres se corrigieron en `ab02482`:

| # | Defecto | Síntoma real | Corrección |
|---|---|---|---|
| 1 | `RealInvoiceStore` no exponía `terceros`/`sellers`/`productos` | `AttributeError` **antes** del primer INSERT | `_LazyMasterMap` (una consulta por clave, memoizada por request) |
| 2 | `erp/models.py` no declaraba `app_doc_journal.updated_at` | `CompileError: Unconsumed column names: updated_at` en `record_number` | columna agregada al `Table` |
| 3 | `commit()` usaba `exec_driver_sql` con placeholders nombrados | `:numfven` llegaba literal a pymysql → **ERROR 1064** | `text()` + `conn.execute(..., row)` |
| 4 | nombres de columna del payload POS | **ERROR 1054** en las 4 tablas | mapper explícito en `_persist` |

Mapeo aplicado (valores tomados del esquema y de los datos legacy, no supuestos):
`numlin`→`numite`, `numfven`→`numnum` en `detapago`/`detcuentas`, `valcre`→`valhab`,
`nitope`→`nitter`, `prefven`→`predoc`/`prenum`, `referencia`→`numpag`; `codclas='S15'` explícito;
`codmed` resuelto desde `productos.codmed` (`'001'` en 6.450 de 7.840 líneas legacy, no `'UND'`);
`despag` vacío (2.820 de 2.821 filas legacy); `codpag` del primer pago (`facventas.codpag` es
`NOT NULL` sin default).

### Verificación end-to-end (clon `masvital_clone`)

Facturas guardadas con `app_writer` por el camino real (`RealInvoicesRepo.create`), no por SQL
manual. Primera tanda (`ab02482`): `3558`, `3559`, `3560`. Segunda tanda (`4e67589`), con una línea
a granel: **3555**.

```
facventas   1 fila   codclas=S15 prefven=FVP nomuso= codcaj=C1 codemp=59312669 empcod= codpag=F01
detfventas  2 filas  numite=1 codmed=001 candet=1      totdet=11900
                     numite=2 codmed=003 candet=0.250  totdet=2095
detapago    1 fila   codpag=F01 despag= (vacío) numpag=REF-PROBE-GRANEL valpag=13995
detcuentas  3 filas  11050501 Factura de Venta     13995/0
                     41359501 Ventas Comercio       0/12000
                     24080102 IVA generado excluido 0/1995     (balance 13995 = 13995)
stock       7503008669000  21      -> 20
            OLAM001       1268.002 -> 1267.752   (0.250 a granel, sin ruido binario)
app_doc_journal   status=COMMITTED
app_idempotency   respuesta almacenada
contadores        conres 3554 -> 3556
```

Cero `ERROR 1054`/`1064`. Regresión: 8 tests nuevos en `tests/test_erp_legacy_write_path.py`;
suite completa **22F / 917P / 8S / 11E**, idéntica a la línea base (22F / 909P / 8S / 11E: los 8
passes extra son los tests nuevos).

### Deuda pendiente (no bloquea la venta)

| Tema | Legacy real | Lo que escribe el POS Web | Efecto |
|---|---|---|---|
| Débito de la causación | `11050501` para efectivo, `11100501` bancos, `1305` cartera | **siempre** `11050501` | una venta a crédito (`F10`) debita caja en vez de cartera |
| Costo/inventario | `61359501` y `14350101` por línea | no se registran | el costo de venta no se mueve en el auxiliar |
| `detcuentas.detcue` del ingreso | nombre del producto | `Ventas Comercio` | el auxiliar agrupa por cuenta, no por ítem |

Resuelto en `4e67589`: descuento de stock, `codemp`/`empcod`/`nomuso`/`codcaj` y las cuentas PUC.

La cabecera ya usa las convenciones legacy (NIT del operador, `C1`, `nomuso` vacío) y el auxiliar
libra caja contra ingreso e IVA. Lo que falta es el débito por forma de pago (crédito vs efectivo) y
el costo de venta.

## 10. Riesgos y deuda técnica

| Severidad | Riesgo | Recomendación |
|---|---|---|
| **Resuelta** | El write path real no coincidía con el esquema legacy (§9): toda venta devolvía 500 `Unknown column` | mapper implementado y probado end-to-end contra un clon; ver §9 |
| **Resuelta** | El POS Web ya descuenta `productos.exiprod` como delta en la misma UoW (§9) | pendiente: probar concurrencia con `SgHermes` en producción |
| **Media** | Venta a crédito (`F10`) debita caja (`11050501`) en vez de cartera (§9, deuda) | discriminar por `codpag` antes de vender a crédito desde la web |
| Alta | `root` **sin password** y el servidor escuchando en `0.0.0.0:3306` | fijar password de `root` y bindear a `127.0.0.1` o firewallear |
| Media | El path de lectura usa `root` porque el password de `api_read` es desconocido | rotar `api_read` y usar ese usuario en `MYSQL_USER` |
| Media | MySQL 5.0.45 (EOL desde 2012), sin FKs, `latin1` | plan de migración a 5.7/8.0 |
| Media | `facventas` es MyISAM: el índice único da atomicidad de numeración, pero no rollback transaccional de la venta completa | aceptar para slice-1, documentar |
| Baja | `numfven` es `varchar(20)`: ordenar por número da orden lexicográfico | ordenar por `fecfven` |
| Baja | Se instaló `pytest 9.1.1` en el venv de la API (no estaba) | agregar a las deps de dev del entorno |

---

## 11. Rollback

```sql
-- 1) quitar el índice único (la base y los datos no se tocan)
ALTER TABLE `masvital`.`facventas` DROP INDEX `uq_facventas_doc`;

-- 2) revertir el gate de la aplicación
--    tenants.yaml: erp.enabled: false / empresa: ""
--    y reiniciar MasVitalBackendService

-- 3) opcional: quitar las tablas del slice-1 (pierde journal e idempotencia)
DROP TABLE `masvital`.`app_doc_journal`, `masvital`.`app_idempotency`, `masvital`.`app_migration_state`;
```

Restauración total desde el backup:

```powershell
& "C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\mysql.exe" -u root -e "DROP DATABASE masvital; CREATE DATABASE masvital;"
Get-Content "$env:TEMP\opencode\backup_masvital_pre_f8.sql" | & "C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\mysql.exe" -u root masvital
```

---

## 12. Reproducibilidad

```powershell
# migraciones (solo 001-003; ver §5 sobre F8-004)
& ".\motoshop-app\api\.venv\Scripts\python.exe" -m infra.migrations.run_migrations `
    --dir "$env:TEMP\opencode\f8_apply" --database masvital --user root --password=""

# suite ERP
& ".\motoshop-app\api\.venv\Scripts\python.exe" -m pytest `
    tests\test_erp_integration_concurrency.py tests\test_erp_pos.py tests\test_erp_guards.py -v
```

## 13. Artefactos

- `%TEMP%\opencode\backup_masvital_pre_f8.sql`
- `%TEMP%\opencode\backup_facventas_pre_f8.sql`
- `%TEMP%\opencode\f8_grants.sql` (grants aplicados, sin password)
- Este documento
