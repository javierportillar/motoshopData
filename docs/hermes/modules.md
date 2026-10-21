?# sgHermes — Análisis de módulos (cobertura completa del binario)

Complemento de `code_analysis.md`. Este documento cubre **el 100% del árbol descompilado**
(721 clases con código, 1.301.583 líneas) con dos niveles de evidencia:

1. **Catálogo completo** (`form_catalog.csv`, mismo directorio): cada archivo `.cs` con su tamaño,
   número de métodos, bloques SQL y tablas que toca. Metodología: extracción regex de todas las
   cadenas SQL (`INSERT INTO / UPDATE / DELETE FROM / SELECT … FROM / LOCK TABLES`) + conteo de
   firmas de métodos, sobre los 797 archivos descompilados con ILSPY 8.2.
2. **Lectura profunda** con referencias file:line para los formularios que concentran lógica
   (los 16 documentos principales + helpers). El resto (357 archivos sin SQL, 364 en dominios de
   UI/reporte) son diseñadores de formularios (InitializeComponent) o pantallas de consulta cuyo
   único trabajo es leer tablas ya descritas.

Clasificación por dominio (del catálogo): VENTAS_FACTURACION 55 · CONTABILIDAD 73 ·
INVENTARIO 63 · CONFIG_MAESTROS 79 · COMPRAS 25 · POS_CAJA 23 · NOMINA 7 · FISCAL_DIAN 5 ·
BANCARIO 3 · REPORTE/OTRO 31 · UI_SIN_SQL 357 · (CARTERA viaja en CONTABILIDAD/VENTAS).

---

## 1. Arquitectura transversal descubierta

### 1.1 Tablas `aux*` — el patrón de materialización
La aplicación NUNCA hace lógica compleja en SQL: materializa resultados en tablas auxiliares
(MyISAM, desechadas), renderiza desde ahí, y las borra al terminar:

| Tabla aux | Producida por | Consumida por |
|---|---|---|
| `auxdoc`, `auxdetdoc`, `auxdetcue` | `ImpDocumen` (Graba_Doc/DetContab/SalEnt/Despach/ReceMer) | Motor GDI de documentos formales |
| `auxfiscal1`, `auxdetdoc`, `auxinvserial`, `auxinventario` | `RepFrCuadCaj`, cierre de caja | Tiquetes fiscales y cuadre (VImpTiqNet) |
| `auxkardex` | `kardBode` (leyenda de detcuentas + notabodegas + derivados) | Reporte kardex |
| `auxrep`, `auxdetrep` | Reportes varios | Impresión genérica |
| `auxdcuentpuc` | `CierreAnu2` (cierre contable) | Ajuste de cierre |
| `auxrepcart` | `MovCxcP` (cartera) | Reporte CxC/CxP |
| `auxmedmag1` | `MedMag2` (medicamentos mágicos INVIMA) | Exporte Excel |
| `linea2` (temporal) | `RepFrCuadCaj` (borra y repuebla) | Totales fiscales por línea de producto |

**Implicación de diseño nuevo:** esas aux son "vistas materializadas desechables". En el
sistema web nadie las desea: los reportes se computarán con `SELECT ... GROUP BY` sobre la
fuente o con vistas/CTEs.

### 1.2 Crystal Reports también existe
`ImpDocumen.SetDBLogonMysql(ReportDocument)` conecta documentos Crystal a MySQL. La mezcla real:
GDI handmade para POS/tiquetes, Crystal para ciertos formatos formales. El render GDI de
`VImpTiqNet`/`ImpDocumen` es la única fuente confiable para replicar el formato de tiquete POS.

### 1.3 `FrmInicio` — el actualizador de esquema (bootstrap de la app)
8.750 líneas, 1.457 bloques SQL. Es **el motor de migración/seed de la app**: en cada arranque
compara `registro.verher` y ejecuta silenciosamente todas las migraciones acumuladas:
- Seed/reparación: países CO/EC/PE/VE/US/PA/BR/AR/CL + ~1.100 `UPDATE ciudades SET codfel1`
  (códigos postal-DIAN de Colombia), `linea2`, contadores nuevos (NA2, S50 CONSIGNACIÓN etc.),
  `resdian`, `permisoscab` (P035 traslados, N065), tablas `traslados`/`dettraslado`,
  `notabodegas`/`detbodegas`, `prodserlotes`, `sucbloqcab`/`sucbloqdet`.
- Migración de datos: `detimpuestos.tipimp` normalizado (11/12/02/03 – EXENTO/EXCLUIDO),
  `detcompras.tipdet GA→E`, `detnotcxccxp.tipdet G→E`, `contadores.tipclas S16→S14`,
  `provetecno/respdocfele.codpro=2`, `contadores.envfele='S'`.
- Limpieza `parametros` huérfanos y reconstrucciones de `permisoscab`.

**Implicación:** el "esquema canónico" del binario incluye TODOS esos parches; el schema
migrado de la vida real (`schema_2024.sql`) ya los trae aplicados. El sistema nuevo debe migrar
con herramientas versionadas (Flyway/Alembic), no con este script gigante.

### 1.4 `BotActualiza` — refrescador de catálogo en memoria
Cada combo/lista de cada form se repuebla desde BD vía los ~45 métodos `ActCmb_*`
(ActCmb_FACV/FVPOS/COMP/COMAN/RECEP/FINAN/SOLSER/DESPA/CONSB/COTIZ/NOMINEL1/ENTRA…).
Es la lista completa de tipos de documento del sistema, en código:
FVPOS, FACV, COMP, CMING, CMEGR, AJUSUBINV, RECEPEVEN, SOLTRASLA, RECMER, ORDCOM, FINAN,
SOLSER, SINIT, RETBAN, CONTEO, DESPA, CONSB, CMEN, ARCAJ, TERC, SERV, SALI, FVSER, CONVER,
NCOSTO, REMIS, PEDIDO, PROD, NOCREPRO, NODEBCOM, NODEBCLI, NOCRECLI, COTIZ, NOMINEL1, PRESU, PUC…

## 2. Tesorería y caja

- **Comprobantes de egreso/ingreso** (S02/S03): `comprobantes` + causación `detcuentas`; con
  nitter, digver, banco (bancos), consignación; ver `Botones.cs` L1760/L2008.
- **Consignaciones bancarias** `consbancab` + consecutivo propio en `formapago.numcon`.
- **Arqueo de caja** (S38): detallado en `code_analysis.md` §8 (`cajaarqueo`+`detcajarq`,
  tiparq 1 billetes/2 monedas/3 otros). `VImpTiqNet.Det_ImpArq` imprime el tiquete de arqueo.
- **Cajas** (`CajasPOS` + `BotGuarMa` L2596): catálogo por caja: `indgen` (reportes individuales
  vs generales), formapago habilitadas (`empfpago`), layout `conimpdoc`, parámetros
  de impresora + resolución DIAN (`codres,resdian,titfac` en `cajas`).
- **Cuadre fiscal de caja** (`RepFrCuadCaj`): el mecanismo de cierre de turno/día:
  1. filtra `cajaarqueo` del rango (`fecarq, estarq`) — se exige arqueo previo abierto;
  2. agrega por líneas: `SUM((valuni−dctpes)×candet)` sobre `detfventas` y `detnotcxccxp`
     (grupales 5 copias por revisión de tipclas) + `SUM(subfven−totdct)` por cabecera;
  3. agrega pagos `SUM(detapago.valpag)`/`Count(codpag)` por forma y por hora (OptPorhor);
  4. cuenta anuladas `Count(codclas) WHERE estfven/estnot='A'` (`numanu`);
  5. egresos `SUM(comprobantes.totegr)` y `SUM(denarq×cantden)` del arqueo;
  6. materializa todo en `auxfiscal1` (tipinf/tipdet/detalle/subtot/valimp/porimp/valreca/numtran)
     y `auxdetdoc`, para tiquete fiscal y/o exporte Excel (CmdExelIm).
- **Nómina bancaria de colaborador por caja** vía `empfpago.nitter` (MedMag/CuadCaj).

## 3. Ventas: documentos de crédito/notas

Las **notas** (S14 NC cli `/Nota crédito cliente`, S21 nota crédito proveedor, S16 devolución POS,
nota débito comercial) Todas viven en `notascxccxp` + `detnotcxccxp` (o `facventas` para el caso
POS) y comparten un esquema de formulario idéntico (NotcreCLI 16.332 líneas/244 métodos,
NotcrePRO 10.664/160, NotaDebCom 14.924/232):

1. **Documento afectado**: `clasafe/docafe/numcuo` determinan a qué factura/compra/financiación
   apunta la nota; valida `estfven/estcom/estnot` antes de permitir afectar.
2. **Crédito**: lee `fecuno, fecves, intmor, pordct` (politica de interés de mora/pct descuento)
   y las cuotas afectadas (`numcuo, valdeb, valhab` en `detfinancia`), generando cruce via
   `AuxPagCru` + `detapago`.
3. **Retenciones manuales** por línea: RteFte/RteIva/RteIca/RteCre (`CmdRet*`) sobre `detimpuestos`.
4. **Inventario**: `CmdSubInv` (subinventa) e items con `iterel` a la línea original en
   `detfventas`/`detcompras`, para devolución de stock de la línea exacta (a bodega).
5. **Pagos de nota de débito**: mismo esquema de formas de pago que las facturas.
6. Los 3 guardan vía los INSERT del dispatcher en `Botones.cs` L4058-5316 (ver §2 del map).

### 3.1 Facturación masiva de servicios (`FacLotServ`)
Form de 7.735 líneas/124 métodos que factura **lotes de servicios a muchas sucursales/terceros
en una sola corrida** (tipo administración de propiedades/lotes):
- Lee parámetros de sucursales: estratos (`sucestratos`), categorías (`succategoria`),
  impuesto al consumo por rasgo (`sucursales.impcod`), bloqueos (`sucbloqcab/det` con
  `tipbloq` por servicio: bloquear emisión si hay deuda), zona/ruta (`nomrut/nomzon`):
  física del lote en `sucursales` (metrfij/metralc/metrase).
- Acumula los cargos por cliente en **`detsucursal`** (staging del lote: codsuc, codser,
  valuni, candet, tiptip F/facturada), con lecturas (`lecturas`) para medidores.
- Al emitir: genera la factura `facventas`+`detfventas` **por cada sucursal del lote**
  (L176111/L179021/L181827: mismo INSERT que el dispatcher Devin cuenta `numite`,
  pagos en `detapago`, adjuntos `archadjunto`), moviendo `detsucursal → detfventas`,
  causación de intereses de mora (`Saldo_Cuenta_intmor` L168: `SUM(detcuentas.valdeb−valhab)`
  para intereses), y retenciones de servicios (`tipret/basret/porret/valret/cauret`).
- Resolución por lote: lee contadores y `UPDATE contadores SET conres=` masivamente (L285045).

## 4. Compras, recepciones y logística

- **Compras** (S18) y variantes + **recepmerca** (recepcion de mercancía), **traslados**
  (`notabodegas`+`detbodegas` con `bodori→boddst`), **despachos** (`despachos`+`detdespachos`
  ligados a factura via `numfven/docafe`), **solicitud de traslado** (`soltrasla`),
  **lista de empaque** (`listempaques` con guías), **ordenes de compra**.
- Los lotes/series reciben registro en `prodserlotes` (FrmInicio L56875+ seeds y los forms
  detrecepmerca/detbodegas/detdespachos son fuente de `sernum`+`serfec` — trazabilidad física).

## 5. Inventario: kardex virtual y bodegas

- **El kardex no existe como tabla de negocio** — `kardBode` reconstruye el kardex de cada
  producto/bodega desde los eventos: `detcuentas` (diario de ventas/compras/ajustes con
  `codcue` de inventario) copiado a `auxkardex` (L73446: join contadores.descon,
  `entsal`/`detkar`/`cankar`/`coskar`/`tipkar`/`clase`/`numdoc`/`codbod`), más
  `notabodegas`+`detbodegas` (traslados), `despachos`, `recepmerca`, `KardxNue` (entradas
  `kardBode.Cal_Bode_Kar`). Reporte serializable/df: `Busca_serial1` recupera por sernum.
- **exiprod** solo es un saldo cacheado; su recompute lo hace `CierreAnu2.Actual_salProd`
  (L129563 `UPDATE productos SET exiprod=`), `Actualsaldo`, edición de productos.
- **subinventa**: sub-inventario para notas de crédito/débito que re-desplaza inventario
  entre bodegas desde el form de notas (`subproduct`: kits).
- **conteoinv** (conteo físico) y **ajustes de inventario** (S17: `entsalida` con `tiptip E/S`
  + det etc.) cierran el ciclo de stock.

## 6. Contabilidad general

- **PUC** (`cuentaspuc` + `codtip`), **centros de costo** (`cecostos`), **anexos** por
  terceros/costo/producto en `detcuentas` (columnas `nitter/codcos/codprod/canpro`).
- ** cierre contable mensual/anual** (`CierreAnu2.F_CierConta`):
  1. Abre `tipcie` M/A; valida rango `fechas/fecdes` sin traslape sobre `DELETE FROM cierresper`
     si cancelación; lee el rango de `detcuentas` (Min fecdoc = primer libro del sistema);
  2. Materializa saldos: `SUM(valdeb/hab) GROUP BY codcue (+codcos/nitter/codprod/canpro)`
     en `auxdcuentpuc` (4 INSERT según agrupación anexo: cuenta/tercero/costo/producto);
  3. Con `paraciecue.cuefin` y `parinfcontab.sumres` (layout parametrizado por cuenta final)
     construye el **ajuste de cierre** `ajustes+detajustes` (`valdeb/valcre`), lo numera con
     contadores (codcon 'S20'?) y lo causa en `detcuentas` (L143330 INSERT) para amortizar
     cuentas de gasto/ingreso contra utilidad/pérdida del ejercicio;
  4. `UPDATE contadores SET conres=` (consecutivo de ajustes), `UPDATE productos SET exiprod`
     recompute (Actual_salProd).
- **presupuestos** (`cuentpresup` + `detpresupues`, `Graba_IngEgr(..., Es_Presup)` en ImpDocumen).
- **NIIF** (`RepFrNiif1`, `tipniif` en `cuentaspuc`) ya existe como dimensión.
- **Presupuesto/reportes anexos** (`RepCueErr` consistencias de contabilidad — detección
  de descuadres débito≠haber).

## 7. Parámetría (config del negocio)

- **ParaGen**: ~60 controles que SIEMPRE esconden un `parametros(tipo,valor)`+INSERT/UPDATE
  (decimales de cantidades/saldos, formato comas, tamaños de ticket, decimales de causación,
  margen de venta, articulo por defecto, metros/kilo marca sugerencia, etc). El "tipo" es la
  constante, ej. numfactauto/redondeo centavo/botón de caja rápida.
- **ParaConGen**: cuentas contables parametrizadas para notas crédito/débito: retención/IVA/
  intereses/mora/seguro de **compra y de venta** (BusCom/VenPucIva/Int/Mor/Seg/Otr) —
  cuentas de causación por concepto, escritas en `parametros` (tipos 'Cxxxxx').
- **MedMag2 (Medicamentos Mágicos)**: reporte regulatorio INVIMA: `mediomag`/`mediomdet`
  definen para cada medicamento (`codmed`) la cuenta base y tip categorías; el reporte agrega
  `SUM(detcuentas.valdeb/valhab/basimp/ivacos)` para exportar a Excel vía `auxmedmag1`
  (columnas val01..). Multi-formato por marca (`Inserta_MMag2(marka)`).

## 8. Nómina (7 archivos, 161 SQL blocks)
`nominas` + `detnomiele` (por elemento débito/crédito) causadas como todo documento; NO es un módulo
usado en este local (tablas vacías) pero trae: tipos de elemento, nómina electrónica
(DIAN, campos `detnomiele.codnel1/codnel2`), cargos (`cargosemp`),
`MenImpNom` (3 motores PrintDocument de desprendibles).

## 9. Fiscal y DIAN

- **resoluciones** (`resolpuc` + `codres`/`resdian`): habilitación de impresión de cada documento,
  con resolución, rango fecha-servicio (`Res_Numxauto`, `Bus_Con_Act`), prefijo.
- **Facturación electrónica** (conocida como F/E o d fele en el código):
  `respdocfele` guarda la respuesta (cocufe/CUFE, protección, QR code por documento),
  `contadores.envfele='S'`, `dfele` workflow tables, `Este_Dfele` prisma estado 1/2 en 3.8 anulación.
  El QR (cocufe+protec) se imprime en el foot del tiquete (VImpTiqNet L141196).
- **resdian**: resoluciones DIAN por caja y por tipo de doc.
- **impuesto al consumo** (`sucestratos`/`succategoria`/`impconsumo` en sucursales) y
  **exenciones/remisivos** por línea (`linea1/impmes`, `detimpuestos`), retención por bodega
  `linea1.autret/porret`.

## 10. Restaurante/mesas (`Repub pedHabTarR2`, `mesas`)

- `mesas` (posleft/postop/height/width/pisalon) layout de restaurante designable.
- `pedidores` + `detpedires`: pedidos a domicilio/repartidores.
- Comanda cocina: `Doc_TiqFVCocina`/`Doc_TiqRestur1` (según `linea2.lugimp` = lugar de
  impresión por línea: cocina/bar) — el tiquete POS se separa por destino de impresión.
- `pedHabTarR2` es el POS restaurant (tarjetas por mesa, cubiertos, servicios con cobro
  tipcob) — no se usa en esta tienda pero está compilado en el binario.

## 11. Reportes (motor `Rep*` — 100+ formularios)

Todos operan con el mismo patrón: filtro → `SELECT` agregado → materializa en `auxrep`/`auxdetrep`/
`auxfiscal1`/`auxrepcart` → `PrintDocument` (o Crystal o Excel COM Interop —
`Microsoft.Office.Interop.Excel` namespace existe en el binario: exportes `CmdExelIm`).
Los reportes tocan (del catálogo): ventas 4.169, contabilidad 2.729, compras 2.046, POS/caja
2.033, inventario 1.816 (ver clasificación del encabezado). Representativos:
- `RepFrFiscal1` (656 SQL): reporte fiscal anual/mensual (ventas por línea/proveedor/resolución
  + recaudo) → vuelca en `auxfiscal1`.
- `RepFrEstaFin`, `RepFrMayBal` (mayor, balance), `RepAuxLib` (auxiliar/libro), `RepCoVent`,
  `RepCoCPR`, `RepFrIva1` (IVA), `RepCartera2` (aging), `RepFrFluCaj` (flujo caja),
  `RepFrInventa1-4` (existencias/costos), `KardxNue`, `MovCxcP`, `RepFrComiven` (comisiones),
  `RepFrGrafCue` (gráficas), `RepDocuAnu` (anuladas), `RepDocHuecos` (huecos numeración),
  `RepFrDoDesp` (despachos), `RepDColum` (columna dinámica), `RepFrNiif1`.

## 12. Seguridad, licencia y anulación — recap de `code_analysis.md`

- Login con hash reversible + permisos `usuarios/permisosusu (14 acciones)/permisosfac`,
  `Claweb` (puente web del Hermes viejo), cambio de mesa de datos `menu`.
- Licencia: `registro.codreg` + `Encriptar` simétrico con `Hermes_Licen`; full demo mod niveles.
- Anulación con reversa: ver `code_analysis.md` §7 — completa (asientos, stock, financiación).

## 13. Cierre de periodos (`CierrePer`) — resuelve el pendiente de `cierresper`

`cierresper` es el **registro de periodos bloqueados**; lo escriben dos forms:

- `CierrePer` (L754): cierre de periodo puntual — `INSERT INTO cierresper (codcie, fecdes,
  fechas, tipcie) VALUES (…, 'P')` con `codcie` secuencial calculado recorriendo la tabla.
  Valida traslapes con cierres existentes por ambos extremos de rango, y avisa si existen
  documentos con fecha anterior al rango elegido.
- `CierreAnu2` (L114645): los cierres contables M/A descritos en §6, mismas condiciones.

**Efecto:** la anulación (`Hay_Cie_Eli`) y la edición de documentos dentro del rango de
cualquier cierre P/M/A quedan bloqueadas. Los **turnos de caja** no viven acá: se manejan con
`cajaarqueo` + turno1/detapago + el cuadre de `RepFrCuadCaj`.

## 14. Facturación electrónica DIAN — pipeline completo

Tres integradores embebidos bajo namespaces `WA*` (clases serializadoras JSON + envío HTTP),
parametrizables por empresa vía `provetecno` (proveedor tecnológico, UI `ParaProvTec1`)
y `formapago.codfele` / `contadores.envfele`:

| Proveedor | Clases | Produce |
|---|---|---|
| **Dataico** | `WADataico\CreaD1..5\CreaDoc1-5` (arman los payloads), `Enviod1\EnvioDico` (HTTP) | Facturas, notas crédito, documentos soporte y nómina electrónica |
| **SoftProp Latam** (hosting propio) | `WASofPropLat\Dc1–Dc2\SofP_CreaLatam1/2` (payloads de fac/notas/compras/retenciones), `EnvioSop1\EnviarSofPlat` (HTTP) | Todos los documentos + respuesta CUFE/QR |
| **Integrador alternativo** | `WAContrtex\Crea3\CreaDocCt3` (payload docs), `CreaNom1\Class1` (nómina), `WAContrte1\Envia1\EnviarApi2` | Múltiples tipos de doc |

- **Endpoints reales detectados**: `https://api.dataico.com/direct/dataico_api/v2/invoices?number=…`,
  `…/v2/credit_notes?number=…`, `…/v2/support_docs?prefix=…&number=…`, `…/v2/reception_events?number=…`,
  `https://api.dataico.com/direct/payroll-api/payroll-entries/<prefijo>/<numnum>`.
  Proveedor SoftProp: `http://84.247.183.77` (DOMINIO 1) / `http://194.163.144.234` (DOMINIO 2) —
  IPs fijas hardcodeadas (HTTP, no HTTPS: hallazgo de seguridad complejo).
- **QR oficial DIAN** cuando no hay proveedor: `https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=<CUFE>`
  (VImpTiqNet L141196).
- **Respuesta**: `respdocfele (numnum, codclas, cocufe (CUFE), cuuid, qrcode, respcod, estfele,
  estcli, resptxt, codpro)`; el estado `estfele` (1/2 = aceptado) es lo que bloquea edición/anulación
  (`Valid_EdiDocele`, `Vardos.Estado_Dfele`). El QR/CUFE sale en el pie del tiquete y en
  `DocElReenv2`/`FacElConsul1` (consola de reenvíos/consultas).
- Nota de dise�o: el flujo es un cliente Web API puro (HttpClient + Newtonsoft), sin TLS
  pinning ni retry/backoff. En el sistema web nuevo: cola de env�o con retries,
  idempotencia por CUFE y guardado de la respuesta del proveedor.

## 15. Maestro de productos y precios (`Productos`, `PreciosXpro`, `ParaLisPre`)

- **Precio por lista**: `preciosxpro (codprod, codlis, venprod, veniva, porutil, actupr, pvtipo)`
  — productId × lista de precio (`listapre`) con modalidades:
  - `pvtipo=2` → precio a nivel incluido "sobre lo anterior" (OptPrpAntI) vs desglose (OptPrpDesI);
  - `pvsini/pvconi`: precio con y sin IVA precalculados (Product p. 23.382 area);
  - `porutil`: utilidad objetivo de la lista; recomputo masivo de precios desde `ParaLisPre`
    y `ModPrecio` (recalcula todas por lista/meta).
- **Unidades de medida**: `produndmeds (codprod, codmed, divmul, facumed, pventa, tipovc)`
  permite vender por caja/frac etc. a distintos precios (`pventa`/multi-canal `tipovc`);
  catálogo de unidades en `undmedidas` (`CmbUndmed` en el form).
- **Kits**: `subproduct (codprod, codsubp, cansub, tipsub)` — componentes; al facturar un kit,
  el detalle materializa sub-productos (`insertbs Kits2`, `FrVerKits1`).
- **Costos**: `coskar` (pesoponderado desde asientos) / `cosulc` (última compra) / `cosman`
  (manual, "OptCosKar" checked indica forzar kardex; `LbNotCos1` warning de costo no gestionado).
- **EAN/código de barras múltiple**: `prodcodbars (codprod, codbar)` — varios por producto.
- Activos fijos (`prodactfij/prodacttar`) siguen siendo parte del maestro.

## 16. Brechas honestas del análisis (para claridad total)

Cubierto en decisión (no necesarios para la reconstrucción point-of-sale objetivo):
- `Facventas.cs` (form de facturación en mostrador no-POS, 703KB): replica del POS; el guardado
  ya está cubierto por el dispatcher (`F_Facventas`). Su única diferencia relevante es el manejo
  de redondeo y comandas — no estudiado línea por línea.
- `PedHabTarR2` y los ~80 forms `Ped*`/`Hotel*` (restaurante/hotel): extra sistemas POS embebidos
  en el binario; no en el alcance de una tienda de repuestos/motopartes.
- `NotaPTrae1-6` (notas de traslado/inventario) y servicios especiales: igual criterio, ya
  cubiertos a nivel firma SQL en el catálogo.

Todo lo demás (POS, caja, contabilidad, compras, cartera, fiscal, DIAN) está documentado
con evidencia según la matriz de §17.

## 17. Matriz de cobertura del análisis

| Paquete | Cobertura |
|---|---|
| Maestros (terceros, productos, PUC, usuarios…) | Código analizado (`BotGuarMa`, `Productos`, `Actualdatos`) + esquema |
| Flujos core (facturas, notas, ventas POS) | Línea por línea (code_analysis.md + este doc) |
| Pagos, caja, arqueo, cierre fiscal | Línea por línea |
| Anulación y contabilización | Línea por línea |
| Documentos restantes (compras, traslados, despachos, recep, solsi, financia…) | Firma SQL + dispatcher (mapa completo extractado) |
| Reportes (~100 forms) | Patrón común aux* + firma SQL por reporte (catálogo CSV) |
| UI pura (357 archivos) | No requieren análisis lógico (InitializeComponent) |
| Migraciones/seed (FrmInicio, BotActualiza) | Semántica completa documentada |

Cualquier módulo se puede profundizar pidiendo file:line adicional: el árbol descompilado queda
en `C:\Users\MotoShop\AppData\Local\Temp\opencode\hermes\decompiled\` y el catálogo completo en
`form_catalog.csv`.
