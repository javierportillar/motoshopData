# Análisis de código descompilado — sgHermes

Complemento del blueprint (`hermes_reverse_engineering_blueprint.md`). Este documento deja
constancia de la lógica de negocio **leída directamente del binario** (ILSPY 8.2, .NET SDK 8.0.426,
decompilado VB.NET WinForms → C#), para que el sistema nuevo (web) la replique con criterio.

- Fuente descompilada: `C:\Users\MotoShop\AppData\Local\Temp\opencode\hermes\decompiled\` (797 `.cs`)
- Namespaces: `Hermes` (raíz, ~721 clases), `ADODB` (wrapper local sobre ADO), `Microsoft.Office.Interop.Excel`, `Properties`
- Convención: `Inicio.SQL` arma la cadena y `Inicio.CnBd.Execute(...)` la lanza (sin prepared
  statements, sin transacciones). Los formularios acumulan filas en arrays de string
  (`DP_Detaafort`, `DP_Paga`) y el guardado centralizado hace los `INSERT` uno a uno.

Referencias con `archivo.cs:LNNN` corresponden a ese árbol descompilado.

---

## 1. Arquitectura efectiva

| Capa | Implementación |
|---|---|
| UI | WinForms (VB.NET) — cada módulo es un form con código en el code-behind |
| Reglas de negocio | Mezcladas en forms + helpers estáticos (`Botones`, `Botonesaux`, `Variables`, `Vardos`, `MovOtros`, `Botelim`/`Boteliminar`, `Varelim`) |
| Acceso a datos | `Inicio.CnBd` (Connection ADODB-like) + `Bconexion.Asig_Recordset` (Recordset ADODB-like) |
| Persistencia | MySQL 5.0.45, MyISAM, sin stored procedures ni triggers (170 tablas) |
| Impresión | GDI `PrintDocument` sobre driver de Windows (ver §9) — **nunca ESC/POS raw** |
| Catálogo | Form de maestros `BotGuarMaes`/`BotGuarMa` centraliza INSERT de terceros, productos, usuarios, etc. |

El dispatcher que ejecuta el guardado de TODO documento es `Botones.cs` (y su hermano `Botonesaux`):
cada flujo del menú termina en un método `F_<Documento>` que pregunta
*"Esta seguro de que los datos son correctos?"* y luego inserta cabecera + detalle + pagos +
asientos contables en sentencias sueltas.

## 2. Mapa completo de documentos (dispatcher)

Cada entrada = INSERT cabecera/detalle verificado en `Botones.cs`:

| Documento | Tablas | Referencias |
|---|---|---|
| Factura de venta (S12/S40/S44 variantes) | `facventas` + `detfventas` | L575/L667, L882 |
| Factura POS (S15 FVP) | `facventas` + `detfventas` | L1159/L1250 |
| Nota crédito POS (S14/S21, devoluciones DP) | `facventas` + `detfventas` | L6297/L6371 |
| Recibo de caja (S01 RC) | `detapago` | L6401 |
| Comprobante egreso (S02 CE) | `comprobantes` | L1760, L2008 |
| Compra (S18 COM) | `compras` + `detcompras` | L2265/L2288, L2439, L3898, L5594, L7966, L8416 |
| Entradas/salidas inventario (S17) | `entsalida` + `detentsalida` | L2708/L2723, L2943, L6039 |
| Nómina | `nominas` + `detnomiele` | L3182/L3202, L3525 |
| Ajustes contables | `ajustes` | L3735, L5865, L7636 |
| Notas CxC/CxP | `notascxccxp` + `detnotcxccxp` | L4058/L4097, L4500, L4871 |
| Consignaciones bancarias | `consbancab` | L6998, L7471 |
| Arqueo de caja (S38) | `cajaarqueo` + `detcajarq` | L6629/L6644–6672 |
| Despachos | `despachos` + `detdespachos` | L7139/L7172 |
| Conteo físico inventario | `conteoinv` + `detconteoinv` | L7323/L7337 |
| Orden servicio | `solservicios` + `detsolser` | L7779/L7796 |
| Financiación (créditos con cuotas) | `financiacion` + `detfinancia` | L8154/L8189 |
| Lista de empaque/guías | `listempaques` + `detlistempaq` | L8534/L8555 |
| Adjuntos de doc | `archadjunto` (transversal) | L973, L6504, etc. |

**Conclusión para el rediseño:** todos los documentos comparten el mismo patrón
cabecera/detalle/pagos/asientos. Un único motor de guardado transaccional puede cubrir
todo el catálogo usando `codcon`/`tipclas` como discriminador.

## 3. Motor de consecutivos (`contadores`)

- **`Conta_ResFV`** (`Botones.cs` L35):
  1. `LOCK TABLES contadores WRITE`
  2. `SELECT conres, preres, numcon … WHERE codcon = '<tipo>'` → `conres` es el **próximo número**,
     `preres` el prefijo (FVP), `numcon` el código del tipo de doc (no es contador).
  3. `UPDATE contadores SET conres = conres + 1 WHERE conres <= <anterior>` (switch guard light).
- **`Bus_Con_Act`** (`Botones.cs` L453): si el contador quedó rezagado, autocorrige con
  `SELECT MAX(<numdoc de la tabla documento>) + 1`.
- **`Valid_NumFin`** (`MovOtros.cs` L1397): exige `numini <= n <= numfin`. Con `numauto = 'NO'`
  (S18 compras) el número se digita y valida "Consecutivo actual ya existe debe ser un n…" —
  unicidad garantizada **solo en aplicación**.
- El único `UPDATE formapago SET numcon = numcon + 1` del árbol (`Variables.cs` L1061)
  incrementa el consecutivo de **consignaciones bancarias** (`tippag=2 AND afepag=22`),
  no el de documentos.

Riesgos confirmados en §3.1 del blueprint: sin índice único por (prefijo, número) en la tabla
de documento, y si el proceso muere tras incrementar `conres` y antes del INSERT, el número se
pierde (MyISAM, sin transacción). `Bus_Con_Act` es la red de seguridad.

## 4. Cálculo de totales (fórmula del SQL embebido)

Confirmada en los INSERT del detalle (`Botones.cs` L667/L882/L1250/L6371 y equivalentes):

```
totdet   = (valuni − dctpes + ivapes + ipopes) × candet
total    = subfven − totdct + totiva + totipo
dctpes / ivapes / ipopes: montos POR UNIDAD (los porcentajes viven en dctpor/ivapor)
```

Para compras (`F_Compras`):
- `valdeb` = valor línea **sin IVA** (el impuesto no entra al subtotal de la compra).
- Costeo: `Edi_CueInvProd` actualiza `cosulc` (costo de última compra) cuando el documento es
  compra; `Busca_post` toma `coskar` (costo promedio ponderado) desde los últimos asientos de
  inventario en `detcuentas`; `Recal_Cat` recalcula todo.

## 5. Factura POS — flujo de guardado (`F_FacvenPos`)

Dispatcher: `MyProject.Forms.FacvenPos` → `Bot_Guardar` → `F_FacvenPos` (`Botones.cs` L1068).

1. **Validación previa** (`FacvenPos.cs` `Validar`, L13887):
   - duplicado de número de documento, cliente existente, `inater` (inactivo) / `cupblo`
     (crédito bloqueado) del tercero, vendedor válido, total ≥ 0, tope `Max_Monto`/`Max_Items`.
2. **Consecutivo** (§3) y luego INSERT:
   - `facventas` (L1159): numfven, prefven (FVP), fecfven (con hora), cliente, totales, caja, vendedor…
   - `detfventas` (L1250): una fila por línea con `totdet` calculado, `iterel`/`sernum` opcionales.
   - Columna `grusub`/flags DIAN-electrónico generados por `GridCue.SubItems[23]` (tipos 5/6).
3. **Pagos** — `Graba_Fpago` (`Variables.cs` L974):
   - lee `formapago` por cada forma usada (`afepag`, `tippag`, `codpag`, `codcue`)
   - `INSERT INTO detapago (... soldeb, solcre, codpag, afepag, codban, codtar, estado 'B',
     tipcmen, nitter, codcaj, turno1, fecven) ...`
   - **dualidad débito/crédito** según tipclas del documento: S14/S21 (notas) → `solcre`,
     S02/S03/S26 y S18/S44 → `soldeb`; normal (S15 etc.) → `soldeb`.
   - `valefe` = total efectivo EFECTIVO de la factura (replicado en cada fila de pago), no por línea.
   - Consignaciones: las formas de pago tipo consignación (`tippag=2, afepag=22`) incrementan
     su propio consecutivo bancario (§3).
4. **Causación contable** — la venta alimenta `GridCue` (esbozo de asientos) y
   `Vardos.Grab_NueCausa` (`Vardos.cs` L275, ~50 parámetros) escribe cada asiento en
   `detcuentas`: cuenta por línea según `linea1.codcue`, cuenta de IVA, cuenta de costeo
   (inventario), cuenta de caja/banco/cartera por forma de pago, retenciones y otros.
   El `SUM(detcuentas)` es TODO el libro de la empresa.
5. **Stock** — `Edi_CueInvProd` (`Vardos.cs` L423): `exiprod = exiprod + cantidad` por cada
   línea (cantidad negativa en venta), junto al costeo de §4. **Sin validación de stock**
   (hay 5 productos en negativo, 2.421 en cero).
6. **Impresión** condicional (`Varuno.Imp_Des_Gra(codcon)`) → `Botonesaux.Bot_Imprimir(...)`
   (motor GDI, §9) tras el guardado — nunca dentro de la transacción.

## 6. Crédito con financiación

- `facaprocre` (aprobación de cupo, L597/L1180) registra `obscre, valapro, salante, coddin`.
- Documento `financiacion` + `detfinancia` (L8154/L8189): cuotas con `salcre, intere, capital,
  nuesal, valcuo, valseg, valcomi, ivacuo, valiva` — tabla de amortización escrita por el form.
- Forma de pago `afepag=5` (crédito) valida módulo `factorfin` (L3173: factores por N cuotas)
  y consulta `mora`/`descto` del tercero.

## 7. Anulación — reversa completa (`Boteliminar.cs`)

Flujo `Ll_FACVENP` (L624). Pasos verificados:

1. `Veri_Anul` (L402): si `estado='A'`, no se puede anular dos veces.
2. `Hay_Cie_Eli`: si el doc cae dentro de un cierre contable, se rechaza.
3. `Valid_EdiDocele` (L425): no se modifica/elimina documento electrónico aceptado
   (Estado_Dfele 1/2 = aceptado DIAN).
4. Permiso en diálogo `FrModAnuDoc` (`TxtCodPerm = 'N049'`) + **motivo** obligatorio.
5. `Inserta_Anu` (L385): `INSERT INTO motanudoc (numnum, fecanu, motanu, codemp, horanu,
   codclas, fecdoc, tipo)` — tipo `A` (anulado), `M` (modificado); motivo truncado a 800 chars.
   La tabla `motanudoc` es el audit log de cambios/anulaciones del sistema.
6. Reversas ejecutadas en el flujo:
   - `UPDATE detcuentas SET estcue='A'` (asientos)
   - `UPDATE detapago  SET estado='A'` (pagos)
   - `UPDATE financiacion SET estfin='A'` (cuotas del crédito)
   - `AcInv_Eli_Anul` (`Vardos.cs` L865): después de borrar el asiento del documento, por cada
     producto `tipclas ∈ {S18, S44, S23, S34}` llama `Edi_CueInvProd(..., Recal_Cat=true)` —
     **recalcula `exiprod` completo desde `detcuentas`** (kardex = verdad).
   - `UPDATE facventas SET estfven='A'` (L680/770/1071) + reset del documento domicilio/pedido.
7. En arqueo/modificación con misma numeración (`b==2`, L6603-6626): `Inserta_Anu` tipo `M`
   + `Eli_CabDet` borra `detcajarq`/`cajaarqueo` para reusar el número — el "update" de docs
   bajo rangos fijos se materializa como DELETE por numeración bloqueada.

## 8. Caja POS y arqueo

- **Catálogo de caja** (`BotGuarMa.cs` L2596): `INSERT INTO cajas (codcaj, descaj, indgen…)`
  + `empfpago` (formas de pago habilitadas por caja) + `conimpdoc` (layout de impresión por doc)
  + una batería de `INSERT INTO parametros (tipo, valor, codcaj)` (L2645-2771): parámetros
  de impresora fiscal/cash drawer, redondeo, etc.
- **Arqueo (S38)** (`Botones.cs` L6570-6712): pedido "datos correctos" → `Validar` de `ArqCaja`
  → conteo por `GridBille` (billetes), `GridMone` (monedas), `GridOtro` (otros):
  `INSERT INTO cajaarqueo (numarq, nomdoc, prearq, fecarq, nitter, codcue, salcaj, obsarq,
  estarq 'B', codemp, codclas S38, tiparq = OptArqSol.Tag, empcod)` + filas
  `detcajarq (tiparq 1=billetes, 2=monedas, 3=otros)`. En este local las tablas están vacías:
  la funcionalidad existe en código pero no se usa en producción.
- El cierre de caja POS diario vive en `cierresper` (reportes `RepFrCuadCaj.cs`, cuadre de caja)

## 9. Motor de impresión

- ~60+ forms/reportes instancian `System.Drawing.Printing.PrintDocument` y dibujan con GDI
  (`PrintPage` + `e.Graphics.DrawString`), sobre el driver de Windows en ImpDocumen.cs.
- El layout por documento se parametriza en `conimpdoc` (cab/det/pie) y `parametros` por caja.
- No existe `StartDocPrinter/WritePrinter/OpenPrinter` en el árbol: **no hay ESC/POS**.
  La térmica de la POS se maneja vía driver (Windows) que ya traduce el flujo — el sistema web
  nuevo puede elegir: PDF/P80 desde el navegador, o QZ Tray para raw ESC/POS si se quiere.
- Impresión de etiquetas de activo fijo en `ImpEtiqueta.cs` (PrintDocument + `prtDoc`, L2776);
  las etiquetas Zebra del equipo se imprimen vía driver BarTender propio (carpeta `BarTender`
  y `Zebra Technologies` del usuario).

## 10. Maestros observados en `BotGuarMa.cs` (catálogo completo)

`terceros`+`tercecorreo`+`fincas`, `productos`+`prodcodbars`+`prodcamposad`+`subproduct`
(kits/subproductos)+`produndmeds` (unidades/multiplos)+`preciosxpro`+`ubiprodbod`+`prodactfij`
(activos fijos)+`prodacttar` (ta…/depreciación), `formapago`+`empfpago`+`bancosemp`,
`cuentaspuc`, `linea1` (líneas con cuenta de inventario + retención), `bodegas`, `ciudades`,
`regiones`, `cecostos`, `cargosemp`, `usuarios`+`permisosusu`+`permisosfac`, `contadores`
(nuevo doc: L3391 inserta fila de contadores con conres = numini), `solcreditos`/`solcreapro`
(`factorfin`), `listapre`, `mesas` (POS restaurant), `concepingegr`, `detimpuestos`,
`variosdet`, `cuentpresup`.

## 11. Seguridad y datos sensibles del binario (además del blueprint)

- Login con salt por usuario y contraseñas **reversibles** (`Encriptar` simétrica con la clave
  de instalación `Hermes_Licen` — licencia de módulos en tabla `registro`, `Variables.cs`
  `Full_Demo1` L1072): el sistema nuevo debe usar hash (argon2/bcrypt) y no heredar eso.
- La licencia/HW-lock y la auditoría `motanudoc` son el par de tablas que el nuevo sistema
  debería replicar (audit log) sin replicar el esquema de licenciamiento.
- `archadjunto` ya da un patrón de adjuntos por documento (numnum + codclas + numite + url).

## 12. Qué NO modelar del legado

1. MyISAM/sentencias sueltas → reemplazar por un único `BEGIN/COMMIT` con FKs e índices únicos.
2. SQL por concatenación de strings (todas las consultas vistas) → parámetros preparados.
3. Stock sin validación y descuentos/impuestos por unidad en el detalle → computar totales en
   backend con `DECIMAL` y validar stock según las reglas de negocio del cliente.
4. Manejo numérico tipo `Conversion.Val`/`PuntX_Coma` (formato decimal con coma) → usar
   `Decimal` en el ORM y formatear por locale solo en presentación.
5. Consecutivos con `LOCK TABLES` global → secuencias transaccionales por tipo de doc
   (`document_sequences`, ver blueprint §3.1 y §7.7).

## 13. Pendientes de lectura opcional (no bloqueantes)

- Apertura/cierre de caja POS con turnos (tabla `cierresper`; reporte `RepFrCuadCaj.cs`).
- UI de devoluciones `NotcreCLI/NotcrePRO` (el esquema S16/DP está claro; falta el flujo de mouse).
- Nómina detallada `MenImpNom` (fuera del alcance POS para MotoShop).
- Reportes fiscales centrales en `ImpDocumen.cs` / `RepFrFiscal1.cs`.
