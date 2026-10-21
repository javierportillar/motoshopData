# Blueprint de ingeniería inversa — sgHermes 9.1.0

> Documento de migración hacia un sistema web/mobile (Next.js + FastAPI).
> Base: inspección estática del binario, introspección de la base de datos en producción y el manual de usuario incluido en la instalación.

## 0. Cómo leer este documento

Cada afirmación está etiquetada:

| Etiqueta | Significado |
|---|---|
| **[V]** Verificado | Confirmado con evidencia directa (metadata del binario, `information_schema`, filas reales, strings del ejecutable). |
| **[I]** Inferido | Deducción razonable a partir del modelo de datos o de muestras, pendiente de validación con el negocio. |
| **[X]** No determinable | El análisis estático no pudo resolverlo con las herramientas disponibles. Requiere decompilación o prueba dinámica. |

**Limitación principal:** REA (`rea-agents@6.7.0`) se instaló y configuró correctamente, pero su provider managed rechazó el binario: *«Managed metadata exceeds the 67108864 byte representation budget»*. La máquina no tiene .NET SDK ni decompilador (`ilspycmd`, ILSpy, dnSpy, ildasm), por lo que **no se pudo leer IL ni el árbol de tipos**. Las reglas de cálculo y el detalle de UI se reconstruyeron desde el esquema, los literales SQL embebidos y el manual; lo que dependía del código se marca **[I]** o **[X]**.

---

## 1. Ficha técnica del monolito

### 1.1 Instalación

| Dato | Valor |
|---|---|
| Producto | SgHermes 9.1.0 (MSI `{D2B4D617-D58A-439A-B8C3-5E2C252C0554}`) |
| Ruta | `C:\Program Files (x86)\Julio Chaves\SgHermes\` |
| Ejecutable principal | `SgHermes.exe` — 37.760.512 bytes, PE x86, **managed .NET** |
| SHA-256 | `6fb0c1f08bb7232f59156a46cd140a3b064dc65370c2c50468614bcb470e6ab8` |
| Variantes | `SgHermes ant.exe` (33.8 MB), `ant2.exe` (36.8 MB), `ANT1.exe` (35.6 MB) |
| Licencia/actualización | `Actualizacion_9_2` presente en Documentos → existe canal de updates |
| Distribución | Copias sueltas del .exe en `Desktop\CARGA`, `Documents` y `Documents\actualizacion hermes` **[V]** |

### 1.2 Stack detectado

| Componente | Evidencia |
|---|---|
| Runtime | `.NET Framework 4.5` — `SgHermes.exe.config`: `<supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.5" />` **[V]** |
| Tipo de app | WinForms de escritorio (una sola ventana principal con barra de botones, según manual) **[V]** |
| Acceso a datos | **ODBC** (`OdbcConnection`), driver `MySQL ODBC 5.1 Driver`; strings `DRIVER={` y `ODBC` en el binario **[V]** |
| Base de datos | MySQL `5.0.45-community-nt` en `localhost:3306` **[V]** |

### 1.3 Dependencias empaquetadas

| DLL | Función inferida |
|---|---|
| `log4net.dll` | Logging a archivo |
| `Newtonsoft.Json.dll` | Serialización (¿API externa? ¿config?) |
| `QRCoder.dll` | Generación de códigos QR en tickets/impresos |
| `Renci.SshNet.dll` | SSH/SFTP → transferencia de backups o actualizaciones |
| `System.Net.Http.dll` | Cliente HTTP (consumo de servicios externos) |
| `stdole.dll` | Interoperabilidad COM (probablemente impresión/Office) |

> La presencia de `Renci.SshNet` + `QRCoder` + `System.Net.Http` sugiere funciones de nube/QR ya presentes en el legacy; **[I]** no se pudo confirmar cuáles están activas.

### 1.4 Configuración de conexión

`servidor.txt` (formato: host; usuario; clave; puerto; base; driver):

```
<host>; <usuario>; <clave vacía>; 3306; bdempresa; MySQL ODBC 5.1 Driver;
```

**[V]** El usuario es `root` **sin contraseña**. La base declarada (`bdempresa`) **no existe** en el servidor: la base real es `motoshop2024`. Esto indica que el archivo es legado y la conexión efectiva se resuelve en código o por otro archivo **[I]**.

> ⚠️ **Riesgo crítico:** credenciales en texto plano con privilegios totales y sin contraseña. Cualquier proceso local puede leer y escribir toda la operación.

### 1.5 Base de datos

| Métrica | Valor |
|---|---|
| Bases en el servidor | `motoshop2024`, `motoshop`, `capacitacion`, `mysql`, `test` |
| Tablas en `motoshop2024` | **175** |
| Motor | **170 MyISAM**, 5 InnoDB (`app_alert_actions`, `app_audit_log`, `app_pipeline_runs`, `app_pipeline_steps`, `app_purchase_plans`) **[V]** |
| Triggers / procedimientos / funciones | **0 / 0 / 0** **[V]** |
| Charset | `latin1` **[V]** |
| `AUTO_INCREMENT` en tablas de negocio | **Ninguno** (solo en las tablas `app_*`, que pertenecen al sistema nuevo) **[V]** |

**Consecuencia arquitectónica:** la base es un almacén pasivo. Las validaciones, el cálculo y la orquestación viven en el cliente; la base solo aporta tablas contenedor y contadores. No hay integridad referencial, ni transacciones, ni auditoría a nivel de motor.

**Capa de acceso a datos [V]:** la extracción de literales recuperó **147 sentencias SQL embebidas** con **0 marcadores de parámetro (`?`)** → SQL armado por concatenación de cadenas sobre ODBC. Tablas referenciadas por esas sentencias: **79**.

### 1.6 Estado del análisis con REA

| Capacidad | Resultado |
|---|---|
| `setup` (MCP + skill) | ✅ Aplicado: registrado en OpenCode/Codex/VS Code, skill v42 (207 tools), `state: aligned` |
| `inspect-managed-artifact` | ✅ Identidad PE managed confirmada |
| `inspect-managed-members` | ❌ `resource-limit`: metadata > 64 MB → sin tipos, métodos ni `user_strings` |
| Providers nativos (Ghidra/IDA/JADX/Kuna) | ❌ No configurados (irrelevante para .NET managed) |
| Alternativa aplicada | Extracción de literales UTF-16 del binario (los literales .NET viven en el heap `#US`, no en ASCII) |

---

## 2. Modelo de datos operativo

### 2.1 Convenciones transversales

| Campo | Uso |
|---|---|
| `codclas` (varchar 4) | Clase de documento (`S15` en ventas recientes, `FVP` como prefijo de numeración) |
| `prefven` / `precom` / `preegr` | Prefijo del consecutivo por tipo de documento |
| `codemp`, `codsuc`, `empcod` | Empresa / sucursal |
| `codcaj` | Caja (único valor usado: `C1`) |
| `codres` | Resolución de facturación (DIAN) |
| `codmes`, `codpla` | Periodo contable / plan |
| `estfven`, `estcom`, `estegr` | Estado del documento |
| `codpag` → `formapago` | Forma de pago (20 formas parametrizadas) |
| `horkar`, `horfven` `tinyint(3)` | Hora comprimida (formato propio, no `TIME`) |
| Fechas default | `2000-01-20` / `2010-01-01` — valores centinela del legacy |

### 2.2 Facturación — `facventas` (7.307 filas)

**Sin PRIMARY KEY ni índice único** (`numfven` es un `KEY` no único) **[V]**.

| Grupo | Campos |
|---|---|
| Identificación | `numfven` varchar(20), `prefven`, `codclas`, `nomdoc` |
| Fecha | `fecfven` datetime, `horfven` tinyint, `perdes`, `perhas` |
| Tercero | `nitter`, `digfven`, `clifven`, `dirfven`, `telfven`, `codciu` |
| Vendedor | `nitvend`, `venfven`, `comipor` |
| Condiciones | `codpag`, `diasfven`, `tipcre` (N = normal/contado) |
| Totales | `subfven`, `totdct`, `totiva`, `totipo`, `retfte`, `retiva`, `retica`, `retcre`, `ajuspe`, `propina`, **`totfven`** |
| Estado | `estfven` (**B** = válida 7.291 / **A** = anulada 16), `estfele`, `resfele` |
| Caja/turno | `codcaj`, `turno1`, `cauret` |
| Contabilidad | `codres`, `codcos`, `codzon`, `numcru`, `clascru` |
| Otros | `obsfven`, `texres`, `docext`, `corele`, `agrupa`, `tipdomi`, `salant`, `numdeu` |

### 2.3 Detalle — `detfventas` (32.745 filas)

**Sin PK**; se vincula por (`numfven`, `codclas`) sin constraint **[V]**.

| Campo | Tipo | Significado |
|---|---|---|
| `numite` | smallint | Número de línea |
| `codprod` | varchar(20) | Producto |
| `nomdet` | varchar(300) | Descripción congelada al momento de la venta |
| `candet` | double | Cantidad |
| `valuni` | double | Valor unitario |
| `dctpor` / `dctpes` | float / double | Descuento en % / en pesos |
| `ivapor` / `ivapes` | float / double | IVA en % / en pesos |
| `ipopor` / `ipopes` | float / double | Impoconsumo % / $ **[I]** |
| `totdet` | double | Total de la línea |
| `cosprod` | double | Costo del producto al momento de la venta |
| `sernum`, `serfec` | varchar | Serie / lote y su fecha |
| `codbod` | varchar(4) | Bodega |
| `codmed`, `divmul`, `facumed` | — | Unidad de medida y factor de conversión (venta por fracción) |
| `numite`, `iterel` | smallint | Línea y línea relacionada (devolución/cambio) |
| `devcam` | char(2) | Marca de devolución/cambio **[I]** |
| `puntos` | double | Puntos de fidelidad |
| `porcomi`, `aplcomi` | float/char | Comisión del vendedor |
| `tipdet`, `tipipo`, `tiesub` | char | Tipo de detalle / impuesto |

Verificación aritmética **[V]**: en la factura 7322 la suma de `totdet` (100.000) coincide exactamente con `facventas.totfven`.

### 2.4 Pagos — `detapago` (9.315 filas) + `formapago` (20)

`detapago` **sin PK**. Columnas clave: `numnum` (número de documento), `codclas`, `numite`, `valpag` (valor aplicado), `valefe` (parte en efectivo), `codpag` (forma de pago), `codban`, `codtar`, `codcaj`, `turno1`, `fecdoc`, `fecven`, `estado`, `nitter`.

Distribución real de formas de pago **[V]**:

| Código | Forma | Usos |
|---|---|---|
| F01 | EFECTIVO | 8.082 |
| F05 | CONSIGNACIÓN BANCO | 826 |
| F11 | CUENTAS X PAGAR | 312 |
| F06 | CHEQUE | 83 |
| F10 | CUENTAS X COBRAR | 6 |
| F07 | TRANSFERENCIA | 4 |
| F03 | TARJETA DÉBITO | 1 |

`formapago` incluye además tarjeta crédito (F04), anticipos, cruces de saldo y salarios por pagar, cada una mapeada a una cuenta PUC (`11050501`, `11100501`, `13050501`, `22050101`…) **[V]**.

> **Lectura de negocio:** el 87% de las ventas es efectivo y el 9% consignación. Tarjeta es marginal. El diseño mobile debe priorizar efectivo + transferencia/QR, no un checkout con tarjeta.

### 2.5 Productos e inventario — `productos` (6.493 filas, PK `codprod`)

| Grupo | Campos |
|---|---|
| Identidad | `codprod` (PK), `codbar` (índice, código de barras), `nomprod`, `desprod`, `presen`, `fotprod` |
| Unidad | `codmed`, `valmed`, `multiplo`, `calcuni` |
| Stock | **`exiprod`** (existencia única), `stockmin`, `stockmax`, `fsinex` (¿sin existencia?), `noesven` |
| Costos | `cosprod`, `cosman`, `cosulc` (último), `cosant`, `coskar`, `tipcos` |
| Precios | `pvsini`, `pvconi`, `pvtipo`, `menopre`, `prbase`, `valform` |
| Impuestos | `impinvi`, `inviica`, `reginvi` (régimen), `regica` |
| Series/lotes | `incserl`, `inccum`, `manser`, `lotcos`, `lotobl`, `tipser` |
| Clasificación | `codlin1..codlin6` (6 niveles), `codpor`, `codpor2`, `codpor3` |
| Proveedor | `nitter`, `refprov`, `titufab`, `provetecno` |
| Comisiones/puntos | `aplcomi`, `porcomi`, `porutil`, `puntos` |
| Banderas | `actprod`, `nominv`, `actfij`, `actupr`, `aproxi`, `masiva`, `pidecos`, `pidfor`, `tiposub` |

**Estado del stock [V]:**
- 4.067 productos con existencia > 0
- 2.421 productos en **cero**
- **5 productos en negativo** (mínimo −1)
- Rango: −1 … 485

→ **El sistema permite vender con existencia cero o negativa.** No hay validación que lo impida (o el stock se ajusta a mano).

**Listas de precios [V]:** `listapre` (2: `L1` MAYORISTA, `L2` DISTRIBUIDOR) + `preciosxpro` (123 filas con `codprod`, `codlis`, `venprod`, `veniva`) + `preciosxdct` (descuentos por lista). El maestro `productos` guarda el precio base (`pvsini`/`pvconi`) y la lista guarda el precio final por lista. `terceros.codlis` asigna la lista al cliente.

> `veniva` en `preciosxpro` es una bandera: el binario rotula "P/venta con impuesto" y "P/venta sin impuesto" → el precio de lista **puede incluir IVA**. La venta debe descomponer el impuesto, no sumarlo.

**Kardex: no existe en la práctica [V]**
- `auxkardex` = **0 filas** (nunca se pobló o se purga)
- `auxinventario` = 246 filas, pero es una tabla de reporte denormalizada **sin saldo** (`valor1..valor5`), no un libro de movimientos
- No hay historial auditable de entradas/salidas: el stock es un contador mutable (`exiprod`)

**Mecanismos de inventario declarados en código pero nunca usados [V]:**

| Tabla | Filas | Rol en el binario |
|---|---|---|
| `notabodegas` | **0** | Cabecera de nota de ajuste / traslado de bodegas |
| `detbodegas` | **0** | Detalle (`codbod`, `bodori` = bodega origen, `numnum`, `codclas`) |
| `conteoinv` | **0** | Conteo físico de inventario (`numcon`, `feccon`, `rescon`, `estcon`) |
| `auxinvserial` | **0** | Auxiliar de series/IMEI |
| `recepmerca` | **0** | Recepción de mercancía |
| `ubiprodbod` | 2 | Stock mínimo/máximo **por bodega** (todo en `0`) |
| `productos.exiprod` | — | **Única fuente de verdad del stock** |

→ El sistema *tiene* el módulo de ajustes y traslados, pero en MotoShop **nunca se usó**: no hay movimientos que migrar ni historia que reconstruir.

### 2.6 Compras — `compras` (811) y `detcompras` (12.476)

**Sin PK.** Espejo del modelo de ventas:

- Cabecera: `numcom`, `precom`, `feccom`, `faccom` (número de factura del proveedor), `nitter`, `procom`, `codpag`, `diascot`, `subcom`, `totdct`, `totiva`, `totipo`, `ret*`, `ajuspe`, **`totcom`**, `estcom`, `codres`, `codcaj`?
- Detalle: mismos campos de línea que `detfventas` (`candet`, `valuni`, `dctpor/dctpes`, `ivapor/ivapes`, `ipopor/ipopes`, `totdet`) más `factpor`, `nomtec`, `horini/horfin`, `multiplo`, `prbase`.
- Compras tiene además campos de **recepción técnica** (`artsol`, `marsol`, `modsol`, `trarea`, `recesp`, `horini`, `horfin`, `verifi`) → sugiere flujo de orden de compra/servicio técnico **[I]**.

### 2.7 Caja

| Tabla | Filas | Rol |
|---|---|---|
| `cajas` | 1 (`C1` CAJA UNO) | Definición de caja (con `descj`, `resdian`, `codres`) |
| `cajaspago` | 1 | Caja ↔ cuenta PUC (`puccaj`) |
| `cajaarqueo` | **0** | Cabecera de arqueo — **no se usa** |
| `detcajarq` | **0** | Detalle de arqueo — **no se usa** |
| `comprobantes` | — | Recibos de caja (ingreso/egreso); **sin PK** |

El manual describe "Informe de Caja … filtrar por arqueo de caja, usuarios, facturas, devoluciones, recibos, comprobantes de egreso", pero las tablas de arqueo están vacías **[V]** → el cierre se hace por **reporte/filtro**, no por sesión de caja formal.

### 2.8 Impuestos — `detimpuestos` (4)

| Código | Nombre | % |
|---|---|---|
| IV1 | EXENTO | 0 |
| IV4 | SIN IVA | 0 |
| IV2 | EXCLUIDO | 0 |
| IV3 | IVA DEL 19 | **19** |

Perfil tributario **Colombia** (19% IVA, retefuente/reteIVA/reteICA, PUC, resolución DIAN) **[V]**.

> En las facturas recientes el IVA es **0**: el catálogo opera mayormente exento/excluido. El motor de impuestos debe soportar ambos casos sin asumir 19% por defecto.

### 2.9 Seguridad y usuarios

Tablas: `usuarios`, `permisosfac`, `permisoscab`, `permisosusu`, `usuapermiso`, `credclaves`, `controlcafe`.

**Autenticación [V]:**
- El binario consulta `SELECT clausu FROM usuarios`. Los literales incluyen `Desifrar clave` (sic), `Ver/ocultar clave`, `Cambio de clave` y `ADVERTENCIA!!. Este usuario ya tiene una sesi…`.
- **La contraseña es reversible**, no un hash: existe la función de "descifrar clave" y la de verla/ocultarla en pantalla.
- Los 2 usuarios existentes tienen `clausu` de 4 a 9 caracteres → sin política de complejidad.
- **Un solo usuario puede tener una sesión activa a la vez** (control en la tabla de sesión, no en el motor).
- Ambos usuarios están con `estusu = 'NO'` **[V]** → el login efectivo no depende de ese flag, o se opera con una cuenta de instalación.

**Autorización [V]:** `permisoscab` (128 filas) define por menú (`codper`, `nommen`) un juego de 16 banderas: `nuevo`, `editar`, `eliminar`, `buscar`, `desplazar`, `imprimir`, `causacion`, `aditer`, `traer`, `todo`, `numord`, `tipo`, `menu`, `adjuntar`. `permisosfac` aplica lo mismo a nivel de documento. Se replica como RBAC con permisos por recurso y acción.

> **Riesgo:** contraseñas recuperables en texto claro y sin hash. En el sistema nuevo: Argon2id/bcrypt, sin función de recuperación reversible (solo reset).

### 2.10 Hallazgos estructurales (resumen)

| Hallazgo | Impacto en la migración |
|---|---|
| 170/175 tablas MyISAM | Sin transacciones ni rollback; escrituras parciales posibles |
| Sin PK en documentos y detalles | Duplicados y huérfanos posibles; ETL debe deduplicar |
| Sin triggers ni rutinas | Toda la lógica debe extraerse del cliente |
| Sin `AUTO_INCREMENT` de negocio | Consecutivos generados en app (riesgo de colisión) |
| Kardex vacío | No hay trazabilidad de inventario que migrar |
| `latin1` | Riesgo de mojibake al migrar a UTF-8 |
| Fechas centinela y corruptas | Hay una factura con fecha `9876-01-01` **[V]** |

### 2.11 Alcance real del ERP vs. uso en MotoShop

El binario es un **ERP generalista multiindustria**, no un POS de repuestos. Módulos detectados por tablas y literales **[V]**:

| Módulo | Evidencia | Uso en MotoShop |
|---|---|---|
| Facturación / POS | `facventas`, `detfventas`, `detapago`, `contadores` | **Sí** (core) |
| Compras | `compras`, `detcompras`, `recepmerca` | Parcial (811 compras) |
| Inventario | `bodegas`, `ubiprodbod`, `notabodegas`, `detbodegas`, `conteoinv` | Solo saldo final |
| Cartera | `detcuentas` (160.287), `facaprocre`, `solcreditos`, `pararepcxcp` | Sí (contabilidad) |
| Contabilidad | `cuentaspuc`, `cuentpresup`, `auxrepconta`, `auxfiscal1`, `cierresper` | Sí (160k movimientos) |
| Nómina | `nomisumcab`, `nomisumdet`, `nomiconcep`, `nomiconcuf`, `detnomiele`, `nomiconempl` | No usado |
| Restaurante | `mesas`, `pedidores`, `domicilios` | No usado |
| Hotel | literal `S58 - RESERVACIONES - HOTEL` | No usado |
| Servicios públicos | `fincas`, `lecturas`, `mediomag`, `auxmedmag1` | No usado |
| Servicio técnico | contador `S11 SERVICIO TECNICO`, `provetecno` | No usado |
| Facturación electrónica DIAN | `resdian`, `auxfiscal1`, `respdocfele`, `ciudades.codfel1`, literal `20 - Documento equivalente P.O.S` | **Declarado, sin datos** |

**Rutina destructiva [V]:** el binario contiene una lista de `DELETE FROM` sobre ~40 tablas maestras (`productos`, `terceros`, `usuarios`, `permisos*`, `listapre`, `preciosxpro`, `subinventa`, `zonas`, `regiones`, `resolpuc`, `revelaciones`, `undmedidas`, …). Es una función de "limpiar/inicializar empresa" **sin confirmación a nivel de motor y sin transacción**. Riesgo alto de pérdida total de datos si se ejecuta por error.

### 2.12 Resoluciones DIAN

`resdian` tiene **0 filas** y `contadores.conres/preres` apuntan a resoluciones inexistentes **[V]**. Aunque el binario soporta numeración por resolución (`numini`, `numfin`, `fecres`, `freshas`, `nmeses`, `aplvig`), en MotoShop la facturación POS opera con consecutivo simple y prefijo `FVP`, sin rango autorizado registrado.

→ En el sistema nuevo, la resolución debe ser **obligatoria y validada** (rango + vigencia + prefijo único) antes de emitir.

---

## 3. Reglas de negocio

### 3.1 Consecutivos **[V]**

Los consecutivos **sí viven en la base**, en `contadores` (57 filas):

| Campo | Significado **[V] verificado en código** |
|---|---|
| `codcon` | Tipo de documento (`S15` = FACTURA DE VENTA POS) |
| `descon` | Descripción ("FACTURA DE VENTA POS") |
| `numcon` | Código numérico del tipo de documento (S15 → 15). **NO es el contador.** |
| `numini` / `numfin` | Rango autorizado (DIAN) |
| `numauto` | `SI`: autoincrementa; `NO`: el usuario digita el número manualmente |
| `preres` | Prefijo (`FVP`) |
| `conres` | **Contador vivo: próximo número a usar** (S15 → 7323) |
| `actcon` | Activo |
| `tipclas` | Clase de documento |

Contadores relevantes hoy **[V]** (`conres` = próximo número):

| `codcon` | Documento | Prefijo | `conres` (siguiente) | `numauto` |
|---|---|---|---|---|
| S15 | FACTURA DE VENTA POS | FVP | **7323** | SI |
| S08 | FACTURA DE VENTA | FV | [I] re-verificar | SI |
| S16 | DEVOLUCIÓN POS | DP | [I] re-verificar | SI |
| S18 | COMPRA | COM | [I] re-verificar | **NO** |
| S01 | RECIBO DE CAJA | RC | [I] re-verificar | SI |
| S02 | COMPROBANTE DE EGRESO | CE | [I] re-verificar | SI |
| S09 | COTIZACIÓN | COT | [I] re-verificar | SI |

**Flujo verificado en código descompilado** (`Botones.cs`):
- `Conta_ResFV` (L35): `LOCK TABLES contadores WRITE` → lee `conres` como número del documento → `UPDATE conres = conres + 1 WHERE conres <= valor_anterior`. Existe bloqueo de tabla MyISAM, no read-modify-write libre.
- `Bus_Con_Act` (L453): autocorrección con `MAX(<tabla_documento>)+1` si el contador quedó rezagado.
- `Valid_NumFin` (`MovOtros.cs` L1397): valida rango `numini`/`numfin`; si el número supera `numfin`, bloquea con "El nuevo número de documento es mayor que la numeración final, debe ampliar la numeración final". Con `numauto='NO'` (ej. compras S18) el usuario digita el número y hay validación de duplicado en aplicación ("Consecutivo actual ya existe…").

**Defectos del mecanismo:**
1. `Bus_Con_Act` usa `SELECT MAX(numdoc)` sin `UNIQUE(prefijo, número)` en la tabla de documentos: la red de seguridad depende de lectura correcta bajo carga.
2. El bloqueo `LOCK TABLES` es exclusión mutua global de MyISAM: serializa TODO documento de todas las cajas durante el latch.
3. El contador puede desincronizarse si el proceso muere después de incrementar `conres` pero antes de insertar el documento (MyISAM sin transacciones); se recupera solo vía `Bus_Con_Act`.

**Diseño nuevo:** tabla `document_sequences` con `UPDATE … RETURNING` (PostgreSQL) o `SELECT … FOR UPDATE`, más `UNIQUE(prefix, number)` como red de seguridad; el número se reserva dentro de la misma transacción que emite el documento.

### 3.2 Cálculo de totales **[V]** (fórmula extraída del SQL embebido)

El binario contiene literalmente:

```sql
-- Total de línea (usado para recalcular/imprimir)
((detfventas.valuni - detfventas.dctpes + detfventas.ivapes + detfventas.ipopes) * detfventas.candet) AS totdet1

-- Total de cabecera
(facventas.subfven - facventas.totdct + facventas.totiva + facventas.totipo) AS total

-- Subtotales de cabecera
SUM(detfventas.valuni * detfventas.candet) AS subvuni,
SUM(detfventas.dctpes * detfventas.candet)   AS subdct

-- Compras: el subtotal NO suma impuestos
SELECT SUM((detcompras.valuni - detcompras.dctpes) * detcompras.candet) AS subtotal
```

Por lo tanto:

```
# Por línea (montos por unidad)
totdet = (valuni - dctpes + ivapes + ipopes) * candet

# Cabecera
subfven = Σ (valuni * candet)
totdct  = Σ (dctpes * candet)
totiva  = Σ (ivapes * candet)
totipo  = Σ (ipopes * candet)
total   = subfven - totdct + totiva + totipo
```

**Clave conceptual:** `dctpes`, `ivapes` e `ipopes` son **valores por unidad**, no totales de línea. El sistema guarda el descuento y el impuesto ya materializados en pesos por unidad. Por eso `dctpor` e `ivapor` son solo la entrada (porcentaje) y se convierten antes de grabar **[I]**:

```
dctpes = valuni * dctpor / 100
ivapes = (valuni - dctpes) * ivapor / 100
ipopes = (valuni - dctpes) * ipopor / 100
```

> El orden importa: el IVA se calcula sobre el **precio unitario ya descontado**, no sobre el bruto. Validar con facturas que tengan `dctpor` y `ivapor` simultáneos.

**Campos fuera de la fórmula:** `ajuspe` (ajuste peso, redondeo a entero COP) y `propina` se suman **después** del cálculo y por eso no aparecen en la expresión de `total` **[I]**. En las facturas muestreadas ambos son 0.

Verificación empírica **[V]**: factura 7322 → `(100.000 − 0 + 0 + 0) × 1 = 100.000` = `totfven`. Cuadra.

**Validación pendiente:** 20 facturas con descuento y/o IVA ≠ 0 contra el recálculo.

### 3.3 Descuentos

- Por línea: `dctpor` (%) **y** `dctpes` ($) en el mismo registro → se combinan.
- A pie de factura: `totdct` acumula el descuento total.
- No hay tabla de promociones ni cupones **[V]**.

### 3.4 Impuestos

- El impuesto se define **por línea** (`ivapor`), no por producto únicamente: el maestro (`productos.impinvi`) define el régimen, pero la línea guarda la tasa aplicada, incluyendo `0` para exento/excluido.
- `detimpuestos` es el catálogo de tasas; no hay tabla de reglas por rango ni por municipio (no hay retención automática calculada en base) **[V]**.

### 3.5 Retenciones

Campos de cabecera: `retfte` (retefuente), `retiva` (reteIVA), `retica` (reteICA), `retcre`.
`compras.porrfte` guarda un porcentaje. Las tablas `retenciones` y `sucretencion` están **vacías** → las retenciones se digitan manualmente **[I]**.

### 3.6 Formas de pago y su relación con caja

- Una factura puede tener **varios registros** en `detapago` (`numite`), cada uno con su `codpag` y `valpag` → pago mixto soportado por diseño.
- `valefe` separa la porción en efectivo (relevante para el arqueo).
- `cajaspago.puccaj` mapea cada caja con su cuenta contable; `formapago` trae la cuenta PUC por forma de pago → **la contabilidad se deriva del código de forma de pago**, no de un asiento explícito.

### 3.7 Stock

- Fuente única: `productos.exiprod` (contador).
- Sin bloqueo: MyISAM no permite `SELECT … FOR UPDATE`; el control es de aplicación y de un solo usuario.
- **Se permite vender en cero/negativo** (2.421 en cero, 5 negativos) **[V]**.
- Descuento de stock al facturar: **[V] verificado** — `Edi_CueInvProd` (`Vardos.cs` L423) ejecuta `exiprod = exiprod + cantidad` al guardar el documento (venta → cantidad negativa), más costos (`cosulc` si compra, `coskar` leído de `detcuentas` en `Busca_post`, o recálculo con `Recal_Cat`). **No valida negativos**: por eso existen productos con stock negativo. Kardex reporte = `SUM(detcuentas.candet)` sobre la cuenta de inventario del producto (`SCos_Can_Cue`, `MovOtros.cs` L913). Además `UPDATE productos SET exiprod` directo existe en re-herrajes de stock (`Actualsaldo.cs` L1001, `Productos.cs` L10918, `CierreAnu2.cs` L3909).

### 3.8 Anulaciones y devoluciones **[V] verificado en código** (`Boteliminar.cs`)

La anulación **sí tiene reversa completa** (flujo `Ll_FACVENP`, L624 en adelante):

1. `Veri_Anul` (L402): rechaza si el documento ya está anulado.
2. `Hay_Cie_Eli`: rechaza si la fecha del documento cae dentro de un cierre contable cerrado.
3. `Valid_EdiDocele` (L425): rechaza modificar documentos electrónicos ya aceptados (estado DIAN 1/2).
4. Diálogo `FrModAnuDoc`: exige permiso (`TxtCodPerm='N049'`) y **motivo**.
5. `Inserta_Anu` (L385): `INSERT INTO motanudoc (numnum, fecanu, motanu, codemp, horanu, codclas, fecdoc, tipo)` — auditoría de anuladas (tipo `A`) y modificaciones (tipo `M`).
6. Reversa de asientos y pagos: `UPDATE detcuentas SET estcue='A'`, `UPDATE detapago SET estado='A'`, `UPDATE financiacion SET estfin='A'`.
7. Reversa de stock: `AcInv_Eli_Anul` (`Vardos.cs` L865) borra el asiento del documento y para cada producto `tipclas` ∈ {S18, S44, S23, S34} llama `Edi_CueInvProd(..., Recal_Cat=true)` → **recálculo completo de `exiprod` desde `detcuentas` restantes**.
8. `UPDATE facventas SET estfven='A'` (L680/770/1071) y reset del documento de domicilio asociado.

Devoluciones/cambios: documento clase S16 (DEVOLUCIÓN POS, prefijo DP) con contador propio; `detfventas.devcam` e `iterel` (línea original relacionada) **[V]** como esquema, flujo UI completo en `NotcreCLI/NotcrePRO` **[I]** (no leído línea a línea).

### 3.9 Transacciones y concurrencia

- MyISAM: **sin transacciones**. Una venta toca `facventas` + `detfventas` + `detapago` + `productos` en sentencias independientes.
- Si el proceso muere a mitad, queda una factura sin pago o con stock descontado a medias.
- El diseño asume **un solo usuario por caja** y sin concurrencia real.

---

## 4. Casos de uso esenciales

### CU-01 · Facturar (POS)

**Actor:** cajero. **Disparador:** venta presencial.

**Entrada:** caja activa (`codcaj`), cliente (opcional, por defecto consumidor final), líneas de producto, forma(s) de pago.

**Pasos:**
1. Seleccionar tipo de documento (`prefven`, `codclas`, `codres`).
2. Buscar producto por código de barras (`codbar`) o por nombre/código.
3. Agregar línea: cantidad, valor unitario, descuento, IVA/impoconsumo, bodega, vendedor.
4. Repetir hasta completar.
5. Calcular totales (ver 3.2).
6. Registrar uno o más pagos (`detapago`).
7. Calcular vuelto (si efectivo > total).
8. Guardar e imprimir.

**Validaciones observadas/deducidas:**
- No se valida stock (permite negativo) **[V]**.
- El consecutivo no tiene unicidad garantizada en base **[V]**.
- El total de líneas debe cuadrar con `totfven` **[V]** (así ocurre en la muestra).

**Efectos en base:**

| Tabla | Operación |
|---|---|
| `facventas` | INSERT cabecera (`estfven='B'`) |
| `detfventas` | INSERT N líneas |
| `detapago` | INSERT N pagos |
| `productos` | UPDATE `exiprod` (decremento) **[I]** |
| `auxkardex` | **no se escribe** (tabla vacía) **[V]** |

**Spec nueva (resumen):** `POST /sales` transaccional, idempotente (`Idempotency-Key`), con `stock_policy` configurable (`allow_negative`, por defecto `false`), `UNIQUE(prefix, number)`, y asiento de inventario append-only.

### CU-02 · Buscar producto

- Búsqueda por `codbar` exacta (lector) o por `nomprod`/`codprod` parcial.
- El legacy filtra en cliente sobre el catálogo; **no** hay motor de búsqueda.
- Spec nueva: `GET /products?q=&barcode=` con índice trigram/FTS; respuesta con stock por bodega, precio vigente e impuesto.

### CU-03 · Cobro y pagos mixtos

- Selección de forma de pago (F01 efectivo, F05 consignación, F07 transferencia, F03/F04 tarjeta, F10 crédito).
- Varias formas en una venta → varios `detapago`.
- Efectivo: cálculo de vuelto.
- Spec nueva: `payments: [{method_id, amount, reference?}]`, validación `Σ amount ≥ total` para efectivo y `== total` para no efectivo; generación automática de movimiento de caja.

### CU-04 · Comprar

**Entrada:** proveedor (`nitter`), fecha, número de factura del proveedor (`faccom`), líneas, condiciones (`diascot`, `codpag`), retenciones.

**Efectos:** INSERT `compras` + `detcompras`; UPDATE de costos (`cosulc`, `coskar`, `cosman`) y de `exiprod` (incremento) **[I]**; sin kardex **[V]**.

**Spec nueva:** `POST /purchases` con recepción parcial, actualización de costo promedio/last-cost explícita y movimiento de stock auditable.

### CU-05 · Cierre / arqueo de caja

**Situación actual [V]:** `cajaarqueo` y `detcajarq` están vacías → **no hay cierre formal**. El control se hace con el "Informe de Caja" filtrando por fecha/caja/usuario y sumando `detapago.valpag` por `codpag`.

**Spec nueva:** sesión de caja (`cash_sessions`: apertura con base inicial, movimientos, cierre con conteo por denominación, diferencia calculada, bloqueo de la sesión y reporte firmado).

### CU-06 · Anular factura

**Actual:** UPDATE `estfven='A'`. Sin reversa de stock ni de caja **[V]**.

**Spec nueva:** `POST /sales/{id}/void` con motivo obligatorio, reversa automática de inventario y caja, y rastro de auditoría (quién/cuándo/por qué). **Nunca** borrar físicamente.

### CU-07 · Informes

Del manual: Comprobantes, Caja, Ventas, Cuentas por Cobrar, Cuentas por Pagar, Contabilidad, Inventario, Kardex.

**Spec nueva:** `GET /reports/{name}?from=&to=&group_by=` con exportación CSV/XLSX y consultas materializadas para los reportes pesados (`detcuentas` tiene 160.287 filas).

---

## 5. UI/UX del legacy

### 5.1 Mapa de pantallas (Manual de Usuario, 26 páginas) **[V]**

| Módulo | Pantallas |
|---|---|
| Inicio | Ingreso al software, barra de botones, copias de seguridad |
| Parametrización | Empresa, terceros (clientes/proveedores/empleados), catálogo de productos, usuarios |
| Procesos | Saldos iniciales |
| Caja y bancos | Recibos de caja (ingreso), recibos de caja (egreso) |
| Ventas | Facturación, **Facturación POS** |
| Compras | Compra |
| Informes | Comprobantes, Caja, Ventas, CxC, CxP, Contabilidad, Inventario, Kardex |

### 5.2 Atajos y lector de código de barras

- Literal **[V]**: *"Buscar con lector de barras sin cerrar ventana (presione F7 para cambiar)"* → **F7** alterna entre buscar por código de barras y buscar por nombre/código.
- El binario contiene `Codigo de barras` / `Código de barras` / `Barcode` **[V]**.
- El manual describe "escribir el nombre o código" para agregar productos → el lector funciona como **teclado** (HID) con terminador Enter **[I]**.
- No se detectaron secuencias de escape de scanner (prefijo/sufijo configurables) **[X]**.

**Requisito para la versión web:** el buscador del POS debe mantener el foco y aceptar entrada de lector sin clics; si se pierde el foco, la venta se traba. Es el atajo que más productividad aporta y el más fácil de romper en un navegador.

### 5.3 Periféricos

| Aspecto | Hallazgo |
|---|---|
| Impresión de tickets | El manual habla de "impresoras tipo tiquete (POS)" para Facturación POS **[V]** |
| ESC/POS nativo | **No** se encontraron literales `ESCPOS`, `RAWPRINTER`, `WritePrinter`, `winspool` en UTF-16 ni ASCII **[V]** |
| Cajón monedero | Sin literales de `cash drawer` / `gaveta` / `kick` **[V]** |
| `QRCoder.dll` | Genera QR para el ticket (probablemente resolución DIAN / e-invoice) **[I]** |
| `stdole.dll` | Interop COM → impresión vía driver de Windows / automatización **[I]** |

**Conclusión [I]:** la impresión se hace por **driver de Windows** (impresora "tipo tiquete"), no por ESC/POS crudo. **No hay evidencia de apertura automática de cajón**; si existe, se hace por pulso del driver o comando manual.

**Implicación:** en la web/mobile no se puede asumir ESC/POS nativo. Se necesita:
1. `window.print()` con CSS térmico (58/80 mm) para el MVP, o
2. un **print agent** local (WebSocket) que reciba el payload y lo convierta a ESC/POS/driver, y
3. impresoras Bluetooth/USB desde la PWA vía Web Bluetooth/WebUSB cuando el navegador lo permita.

---

## 6. Propuesta de arquitectura web/mobile

### 6.1 Modelo de datos nuevo (PostgreSQL, transaccional)

```
tenants, users, roles, permissions, user_roles
warehouses, product_categories(6 niveles), units_of_measure
products(id, sku UNIQUE, barcode UNIQUE, name, unit_id, tax_id, price, cost, min_stock, is_active)
product_stock(product_id, warehouse_id, qty, reserved_qty)   -- PK compuesta
stock_movements(id, product_id, warehouse_id, qty_signed, unit_cost, reason, ref_type, ref_id, created_at)  -- append-only
document_sequences(tenant_id, doc_type, prefix, resolution, next_number)  -- UNIQUE(prefix,number)
sales(id, number, prefix UNIQUE(number,prefix), customer_id, warehouse_id, cash_session_id,
      subtotal, discount_total, tax_total, tip, rounding, total, status, voided_at, void_reason)
sale_items(id, sale_id, line_no, product_id, description, qty, unit_price, discount_pct, discount_amount,
           tax_rate, tax_amount, total, cost_at_sale, serial, lot)
payments(id, sale_id, method_id, amount, cash_amount, reference, status, created_at)
payment_methods(id, code, name, puc_account, affects_cash, requires_reference)
taxes(id, code, name, rate, kind ENUM('iva','inc','exempt','excluded'))
purchases, purchase_items, purchase_receipts
cash_sessions(id, warehouse_id, opened_by, opened_at, opening_float, closed_at, closing_count, difference, status)
cash_movements(id, cash_session_id, type, amount, ref_type, ref_id)
customers, suppliers, employees
audit_log(id, actor_id, action, entity, entity_id, before, after, created_at)
```

Diferencias deliberadas frente al legacy: PKs y FKs reales, `NUMERIC(14,2)` (no `double`), estados tipados, inventario como libro de movimientos + saldo derivado, y numeración con constraint único.

### 6.2 API REST (FastAPI)

| Método | Ruta | Propósito |
|---|---|---|
| POST | `/auth/login` | JWT (access + refresh) |
| GET | `/auth/me` | Perfil y permisos |
| GET | `/products` | Búsqueda `q`, `barcode`, `category`, paginada |
| GET | `/products/{id}` | Detalle + stock + impuesto |
| POST | `/products` · PATCH | Alta/edición (admin) |
| GET | `/products/{id}/stock` | Stock por bodega |
| GET | `/stock/movements` | Kardex filtrable (nuevo, inexistente en legacy) |
| POST | `/sales` | Crear venta (idempotente) |
| GET | `/sales/{id}` · `/sales` | Consulta y listado |
| POST | `/sales/{id}/void` | Anulación con reversa |
| POST | `/sales/{id}/payments` | Pago adicional (crédito) |
| POST | `/purchases` · GET | Compra y recepción |
| POST | `/cash-sessions` | Abrir caja |
| POST | `/cash-sessions/{id}/close` | Arqueo y cierre |
| GET | `/cash-sessions/current` | Sesión activa |
| GET | `/reports/{name}` | Informes con `from`/`to`/`group_by` |
| GET | `/sync/pull` · POST `/sync/push` | Sincronización offline |
| GET | `/health` · `/ready` | Observabilidad |

Reglas transversales: multi-tenant por header (`X-Tenant`), RBAC por endpoint, `Idempotency-Key` en escrituras, `audit_log` automático, errores RFC 7807.

### 6.3 Contrato de venta (ejemplo)

```json
POST /sales
{
  "warehouse_id": "WH1",
  "customer_id": null,
  "doc_type": "FV",
  "items": [
    {"product_id": "WSH3HB", "qty": 1, "unit_price": 100000,
     "discount_pct": 0, "tax_rate": 0}
  ],
  "payments": [{"method": "F01", "amount": 100000, "cash_amount": 100000}],
  "client_uuid": "b1e2...  (idempotencia offline)"
}
→ 201 {"id":"...","number":"7323","total":100000,"status":"issued"}
```

### 6.4 Pantallas Next.js (mobile-first)

1. **POS** — layout de una columna en móvil, dos en tablet: buscador con foco permanente (lector), lista de líneas editable, total fijo abajo, botón "Cobrar".
2. **Cobro** — bottom sheet con formas de pago, teclado numérico grande, vuelto en vivo.
3. **Ticket** — vista previa + impresión (CSS térmico o print agent).
4. **Sesión de caja** — apertura, movimientos, cierre con conteo por denominación.
5. **Compras** — recepción con escaneo y actualización de costo.
6. **Catálogo** — alta/edición con barcode, impuesto, precios y stock mínimo.
7. **Informes** — Caja, Ventas, CxC, CxP, Inventario, Kardex.
8. **Admin** — usuarios, roles, formas de pago, impuestos, resoluciones.

### 6.5 Offline-first

El legacy es local (todo en la misma máquina), así que la operación no depende de internet. La versión web debe replicarlo: IndexedDB + cola de operaciones, `client_uuid` como idempotencia, sincronización al reconectar, y resolución de conflictos por `created_at` + versión del documento.

### 6.6 Impresión y hardware

- MVP: CSS `@media print` con ancho 58/80 mm.
- Fase 2: **print agent** local (servicio .NET/Node sobre WebSocket) que hable ESC/POS y controle el cajón (`ESC p 0 25 250`), resolviendo la carencia detectada en el legacy.
- Lectores: HID (teclado) sin cambios; opcional WebHID/WebBluetooth.

### 6.7 Seguridad

- Eliminar credenciales en texto plano (el legacy usa `root` sin contraseña).
- Migrar a un usuario de BD con permisos mínimos.
- Consultas parametrizadas (el legacy arma SQL por concatenación → superficie de inyección).
- Auditoría de acciones y trazabilidad de anulaciones.

---

## 7. Migración y ETL

| Paso | Acción |
|---|---|
| 1 | Congelar escrituras del legacy durante la carga inicial (o capturar el delta por `fecfven`/`feccom`) |
| 2 | Extraer `productos`, `facventas`+`detfventas`+`detapago`, `compras`+`detcompras`, terceros, usuarios |
| 3 | Normalizar `latin1` → UTF-8; trim de códigos con espacios |
| 4 | Recalcular totales y comparar contra cabecera; registrar discrepancias |
| 5 | Sembrar `product_stock` desde `productos.exiprod` (sin kardex histórico → marcar "saldo inicial" en `stock_movements`) |
| 6 | Remapear `formapago` → `payment_methods` conservando el código (F01, F05…) |
| 7 | Sembrar `document_sequences` desde `contadores` (**`conres`** = próximo, no el último usado; `numcon` es solo el código numérico del tipo de doc) y desde `contadores.preres` |
| 8 | Importar anuladas con `status='voided'` y su `void_reason` desconocido |
| 9 | Validar contra muestras: factura 7322 (100.000, 1 línea, sin IVA) debe cuadrar al centavo |
| 10 | Cargar `listapre` + `preciosxpro` (2 listas, 123 precios) y asignar `customers.price_list_id` |

**Calidad de datos detectada [V]:** factura con fecha `9876-01-01`; 2.421 productos en cero; 5 en negativo; sin PKs → posible duplicación al reimportar.

---

## 8. Riesgos

| # | Riesgo | Severidad |
|---|---|---|
| 1 | Credenciales root sin contraseña en `servidor.txt` | Crítica |
| 2 | Contraseñas de usuario **reversibles** (`Desifrar clave`), sin hash | Crítica |
| 3 | Rutina `DELETE FROM` masiva sin transacción ni confirmación | Crítica |
| 4 | Sin transacciones (MyISAM): facturas/pagos parciales | Alta |
| 5 | Consecutivo sin unicidad ni bloqueo: duplicados posibles | Alta |
| 6 | Sin kardex: inventario no auditable | Alta |
| 7 | Anulación sin reversa de stock/caja | Alta |
| 8 | SQL por concatenación (0 parámetros en 147 sentencias) | Alta |
| 9 | `latin1` y fechas corruptas (factura con año 9876) | Media |
| 10 | Reglas de UI/validación no verificadas (sin decompilación) | Media |
| 11 | Coexistencia: el sistema nuevo ya escribe tablas `app_*` en `motoshop2024` | Media |

---

## 9. Backlog de validación con el negocio

1. **Paridad de cálculo:** recalcular 20 facturas con descuento y/o IVA ≠ 0 y comparar contra `totfven`.
2. **Momento del descuento de stock:** venta controlada, medir `exiprod` antes y después (¿al guardar o al imprimir?).
3. **Consecutivos:** confirmar qué pasa al llegar a `numfin` (100.000) y con `numauto = NO` en compras.
4. **Anulaciones:** cómo se corrige el stock hoy (procedimiento manual real).
5. **Retenciones:** si se digitan manualmente o hay cálculo oculto.
6. **Impresión:** confirmar driver, ancho de papel y si el cajón se abre.
7. **Devoluciones:** flujo real (`devcam`, `iterel`, `subinventa` — 4 filas).
8. **Usuarios inactivos:** por qué ambos usuarios están en `estusu='NO'` y con qué cuenta se opera.
9. **Decompilación:** instalar .NET SDK + `ilspycmd` en un equipo de análisis para leer IL y cerrar los puntos **[X]** (validaciones de UI, mensajes, orden exacto de escritura).

---

## Anexo · Evidencia

| Archivo | Contenido |
|---|---|
| `evidence/data_dictionary.md` | Diccionario de las 16 tablas clave, generado desde `information_schema` (motor, filas, columnas, claves) |
| `evidence/schema_2024.sql` | Dump de esquema completo de `motoshop2024` (175 tablas) — fuente de verdad para el ETL |
| `evidence/binary_strings_digest.md` | 12.538 literales UTF-16 agrupados por tema + **147 sentencias SQL** + 79 tablas referenciadas |
| `evidence/user_manual_outline.md` | Índice y pasajes verbatim del `Manual de Usuario.pdf` |
| `evidence/manual_full_text.txt` | Texto completo del manual (26 páginas) |
| `evidence/rea_commands.md` | Comandos REA ejecutados, error `resource-limit` y ruta de descompilación recomendada |
| `evidence/extract_strings.py` | Extractor reproducible de literales/SQL (UTF-16LE + ASCII) |
| `evidence/extract_pdf.py` | Extractor reproducible del manual (pypdf) |

**Reproducir la evidencia:**

```powershell
& "C:\Python314\python.exe" docs\hermes\evidence\extract_strings.py
& "C:\Python314\python.exe" docs\hermes\evidence\extract_pdf.py
```

> Los scripts apuntan a la ruta de instalación de SgHermes y escriben en `docs/hermes/evidence/`. Ajustar `EXE`/`OUT` si cambia la ruta.
