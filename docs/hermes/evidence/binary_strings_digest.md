# Evidencia — literales del binario

Fuente: `SgHermes.exe` (37,760,512 bytes) — lectura estática, sin ejecución.

Extraccion: 12,538 literales UTF-16LE unicos y 64,578 cadenas ASCII/latin1 >= 4 chars.

> El heap `#US` de .NET almacena los literales como UTF-16LE; un barrido ASCII reproduce solo una fraccion.


## Conteo de categorias


### SQL (sentencias embebidas)  (1884 coincidencias)

```
SELECT * FROM notabodegas
SELECT nomcom FROM terceros
SELECT * FROM detbodegas
SELECT codlin1 FROM productos
SELECT codbod, bodori FROM detbodegas
SELECT * FROM productos
SELECT veniva, venprod FROM preciosxpro
SELECT * FROM mesas
SELECT preciosxpro.venprod, preciosxpro.veniva, listapre.nomlis, listapre.codlis AS codelis FROM preciosxpro
SELECT codlis FROM terceros
SELECT desubi FROM ubiprodbod
SELECT tipser FROM productos
SELECT numdoc FROM controlcafe
SELECT numcom, feccom, procom, totcom, estcom, codmes FROM compras
SELECT * FROM compras
SELECT nombod FROM bodegas;
SELECT * FROM detcompras
SELECT * FROM detcuentas
SELECT codtip FROM cuentaspuc
SELECT numcon AS numdoc, feccon AS fecha, rescon AS tercero, estcon AS estcon FROM conteoinv
SELECT * FROM conteoinv
SELECT detcompras.codprod, productos.nomprod, productos.tipser, productos.manser, productos.pidfor FROM detcompras
SELECT codcue, nomcue, tipniif FROM cuentaspuc
SELECT * FROM cuentaspuc
SELECT codrub, nomrub, clascue FROM cuentpresup
```

### Consecutivos / numeracion  (138 coincidencias)

```
facventas.nomdoc , facventas.prefven,
INNER JOIN compras ON (detcompras.numcom = compras.numcom
AND compras.numcom like '
ORDER BY ABS(compras.numcom) DESC, detcompras.sernum
numcom
controlcafe.sernum, controlcafe.numcom, controlcafe.tipclas, controlcafe.puntos,
SELECT numcom, feccom, procom, totcom, estcom, codmes FROM compras
WHERE compras.numcom like '
ORDER BY ABS(compras.numcom) DESC
WHERE numcom = '
INNER JOIN detcompras ON (detcompras.numcom = compras.numcom
SELECT domicilios.numcom, domicilios.fecdoc, domicilios.fecent, domicilios.nomcom, domicilios.totdoc, domicilios.priorid,
ORDER BY ABS(domicilios.numcom) DESC, domicilios.fecent, ABS(domicilios.priorid) DESC
ORDER BY domicilios.fecent, ABS(domicilios.priorid) DESC, ABS(domicilios.numcom) DESC
SELECT facventas.numfven, facventas.fecfven, facventas.nitter, facventas.clifven, facventas.totfven,
ORDER BY ABS(facventas.numfven) DESC;
SELECT facventas.numfven, facventas.codclas, facventas.fecfven,
facventas.nitter, facventas.prefven,
WHERE facventas.numfven = '
WHERE detcompras.numcom = '
precom
SELECT compras.numcom, compras.codclas,
INNER JOIN facventas ON detfventas.numfven = facventas.numfven
WHERE detfventas.numfven = '
Consecutivo actual ya existe debe ser un n
```

### Pagos / caja  (44 coincidencias)

```
Recibido por:
Recibido por
Cuentas por cobrar
Cuentas por pagar
Cambio de clave
Recibos de Caja (Comp. de Ingreso)
Comprobante de egreso
Arqueo de Caja
Recibo de Caja Menor
Consignaci
RECIBOS DE CAJA (COMP. DE INGRESO)
Recibos de caja (Comp. de Ingreso)
RECIBOS DE CAJA (COMP. DE EGRESO)
Recibos de caja (Comp. de Egreso)
TARJETA DE ACTIVO FIJO
Arqueo de caja obligatorio para cuadre de caja
Recibo del bien y/o prestaci
Cheque No.
ARQUEO DE CAJA
RECIBO DE CAJA MENOR
Recibo de caja menor
COMPROBANTE DE EGRESO
Comprobante de Egreso
Recibido de
RECIBO DE CAJA
```

### Impuestos / retenciones  (283 coincidencias)

```
productos.pvsini, productos.pvconi, preciosxpro.venprod, preciosxpro.veniva
SELECT veniva, venprod FROM preciosxpro
P/venta sin impuesto
P/venta con impuesto
P/venta Con Impuesto
P/venta Sin Impuesto
Impuesto al consumo
LbTarIva
Tarifa de iva
SELECT preciosxpro.venprod, preciosxpro.veniva, listapre.nomlis, listapre.codlis AS codelis FROM preciosxpro
, detcompras.nomdet, detcompras.sernum, detcompras.candet, detcompras.valuni, detcompras.dctpes, detcompras.ivapes
ivapes
ivapor
ivacos
retiva
, detfventas.nomdet, ((detfventas.valuni - detfventas.dctpes + detfventas.ivapes + detfventas.ipopes) * (detfventas.candet)) AS totdet1
detfventas.ivapor, detfventas.ivapes, detfventas.numite,
SELECT codser, detser, vconiva, valser FROM servicios
vconiva
No responsable de IVA
Agente de retenci
n IVA
20 - Documento equivalente P.O.S
dito al documento equivalente
IVAGEN
```

### Inventario / stock  (339 coincidencias)

```
squeda de Nota de ajuste de bodegas
BUSQUEDA DE NOTA DE AJUSTE DE BODEGAS
squeda de Nota de traslado de bodegas
INNER JOIN detbodegas ON (detbodegas.numnum = notabodegas.numnum
AND notabodegas.codclas = detbodegas.codclas)
%' OR notabodegas.nitter  like '%
WHERE (detbodegas.nomdet like '%
%' OR detbodegas.codprod  like '%
WHERE notabodegas.numnum like '
AND notabodegas.fecdoc >= '
AND left(notabodegas.fecdoc,10) <= '
AND notabodegas.codclas = '
ORDER BY ABS(notabodegas.numnum) DESC
SELECT * FROM notabodegas
SELECT * FROM detbodegas
bodegas
SELECT codbod, bodori FROM detbodegas
ENTRADA O SALIDA
Bodega
n en la Bodega
BODEGAS
Bodegas
SELECT bodegas.codbod, bodegas.nombod, bodegas.ubibod
FROM bodegas;
SELECT nombod FROM bodegas;
```

### Impresion / perifericos  (159 coincidencias)

```
Cod. Barras
Buscar con lector de barras sin cerrar ventana (presione F7 para cambiar)
Buscar con lector de barras sin cerrar ventana
Codigo de barras
Imprimir pedido en otras
Imprimir Aviso de corte para facturas con saldos pendientes
Imprimir carta o Media carta seg
Imprimir despues de Guardar
AND codcon != 'S54' AND codcon != 'S58'
S58 - RESERVACIONES - HOTEL
INSERT INTO permisoscab (codper, nommen, nuevo, editar, eliminar, buscar, desplazar, imprimir, causacion, aditer, traer, todo, numord, tipo, menu, adjuntar)
UPDATE ciudades SET codfel1 = '58' WHERE codciu = '05353';
UPDATE ciudades SET codfel1 = '81' WHERE codciu = '05585';
UPDATE ciudades SET codfel1 = '93' WHERE codciu = '05658';
UPDATE ciudades SET codfel1 = '111' WHERE codciu = '05809';
UPDATE ciudades SET codfel1 = '112' WHERE codciu = '05819';
UPDATE ciudades SET codfel1 = '113' WHERE codciu = '05837';
UPDATE ciudades SET codfel1 = '114' WHERE codciu = '05842';
UPDATE ciudades SET codfel1 = '115' WHERE codciu = '05847';
UPDATE ciudades SET codfel1 = '116' WHERE codciu = '05854';
UPDATE ciudades SET codfel1 = '117' WHERE codciu = '05856';
UPDATE ciudades SET codfel1 = '118' WHERE codciu = '05858';
UPDATE ciudades SET codfel1 = '119' WHERE codciu = '05861';
UPDATE ciudades SET codfel1 = '120' WHERE codciu = '05873';
UPDATE ciudades SET codfel1 = '121' WHERE codciu = '05885';
```

### Seguridad / login  (147 coincidencias)

```
BUSQUEDA DE SUCURSALES / USUARIOS DE FAC.
squeda de sucursales / Usuarios de facturaci
BUSQUEDA DE USUARIOS DE FACTURACI
squeda de usuarios de facturaci
USUARIOS
DELETE FROM permisoscab
UPDATE permisoscab SET nommen = 'NOTA DE TRASLADO DE BODEGAS', traer = 'SI', adjuntar = 'SI'
SELECT codper FROM permisoscab WHERE codper = 'P035'
UPDATE permisoscab SET editar = 'SI'
INSERT INTO permisoscab (codper, nommen, nuevo, editar, eliminar, buscar, desplazar, imprimir, causacion, aditer, traer, todo, numord, tipo, menu, adjuntar)
Contrase
Usuario:
Desifrar clave
Ver/ocultar clave
Frmlogin
SELECT clausu FROM usuarios
La contrase
UPDATE usuarios SET estusu = 'NO'
SELECT * FROM usuarios
ADVERTENCIA!!. Este usuario ya tiene una sesi
mnuSesion
Cambio de clave
Usuarios de facturac
Listado por sucursales / Usuarios de facturaci
\Manual de Usuario.pdf
```

### Conexion / configuracion  (8 coincidencias)

```
Error de conexion de base de datos auxiliar
Nombre de la copia de seguridad
Ruta, carpeta para la copia de seguridad
DRIVER={
};SERVER=
;DATABASE=
;UID=
;PWD=
```

### Actualizacion / red  (1282 coincidencias)

```
UPDATE empresas SET nomemp = '
) debe actualizar la versi
UPDATE registro SET verher = '
UPDATE sucvalbloque SET codbloq = '
UPDATE sucursales SET codbloq = '
UPDATE detimpuestos SET tipimp = '02' WHERE tipimp = '01' AND (despor = 'EXENTO' OR despor = 'EXCENTO');
UPDATE regiones SET codpais = 'CO' WHERE Trim(codpais) = '';
UPDATE provetecno SET codpro = '2' WHERE codpro = '0';
UPDATE respdocfele SET codpro = '2' WHERE codpro = '0';
UPDATE detcompras SET tipdet = 'E'
UPDATE detnotcxccxp SET tipdet = 'E'
UPDATE contadores SET tipclas = 'S14'
UPDATE permisoscab SET nommen = 'NOTA DE TRASLADO DE BODEGAS', traer = 'SI', adjuntar = 'SI'
UPDATE permisoscab SET editar = 'SI'
UPDATE ciudades SET codfel1 = '716' WHERE codciu = '52001';
UPDATE ciudades SET codfel1 = '1' WHERE codciu = '05001';
UPDATE ciudades SET codfel1 = '2' WHERE codciu = '05002';
UPDATE ciudades SET codfel1 = '3' WHERE codciu = '05004';
UPDATE ciudades SET codfel1 = '4' WHERE codciu = '05021';
UPDATE ciudades SET codfel1 = '5' WHERE codciu = '05030';
UPDATE ciudades SET codfel1 = '6' WHERE codciu = '05031';
UPDATE ciudades SET codfel1 = '7' WHERE codciu = '05034';
UPDATE ciudades SET codfel1 = '8' WHERE codciu = '05036';
UPDATE ciudades SET codfel1 = '9' WHERE codciu = '05038';
UPDATE ciudades SET codfel1 = '10' WHERE codciu = '05040';
```

### Informes  (51 coincidencias)

```
Informe control de calidad
Informes especiales
Informe de comprobantes
Informe de caja
Informe de ventas
Informe de servicio t
Informe de compras
Informe de Registro hotelero y facturaci
Informe de orden de servicio pendientes
INFORME DE ORDEN DE SERVICIO PENDIENTES
Informes de pedidos
Informe de Ventas
Informe de comandas
Informe comercial en ventas
Informe de comisi
Informe de Ventas Diarias
Informe de ventas por horas
Informe
Informe de numeraci
INFORME DE PRODUCTOS POR VENCIMIENTOS
Informe de productos m
INFORME DE PRODUCTOS MAS VENDIDOS
INFORME DE PRODUCTOS MENOS VENDIDOS
INFORME DE PRODUCTOS SIN VENDER
INFORME DE VENTA DE PRODUCTOS CON RESPONSABLE DE F
```

### Contabilidad PUC  (0 coincidencias)

_(sin coincidencias)_

## Sentencias SQL embebidas (147)

> Extraidas de ambos barridos. Confirman que el acceso a datos es ODBC con SQL concatenado.

```sql
DELETE FROM preciosxpro
DELETE FROM archadjunto
DELETE FROM auxcompven;
DELETE FROM auxdcuentpuc
DELETE FROM auxinvserial
DELETE FROM auxinvserial;
DELETE FROM auxmedmag1;
DELETE FROM auxmetafac;
DELETE FROM bancos
DELETE FROM cajas
DELETE FROM cierresper
DELETE FROM ciudades
DELETE FROM concepingegr
DELETE FROM contadores
DELETE FROM credclaves
DELETE FROM credclaves;
DELETE FROM cuentpresup
DELETE FROM detimpuestos
DELETE FROM detpedreseli
DELETE FROM empfpago
DELETE FROM emplecoman
DELETE FROM fincas
DELETE FROM lecturas
DELETE FROM linea1
DELETE FROM linea2
DELETE FROM listapre
DELETE FROM mediomag
DELETE FROM mesas
DELETE FROM nomiconempl
DELETE FROM nomisumcab
DELETE FROM paranomicos
DELETE FROM pararepcxcp
DELETE FROM permisoscab
DELETE FROM permisosfac
DELETE FROM permisosusu
DELETE FROM preciosxdct
DELETE FROM prodactfij
DELETE FROM prodacttar
DELETE FROM prodcamposad
DELETE FROM prodcodbars
DELETE FROM prodserlotes
DELETE FROM produndmeds
DELETE FROM regiones
DELETE FROM resolpuc
DELETE FROM revelaciones
DELETE FROM solcreapro
DELETE FROM solcreditos
DELETE FROM subinventa
DELETE FROM subproduct
DELETE FROM sucretencion
DELETE FROM tercecorreo
DELETE FROM terceepsasi
DELETE FROM ubiprodbod
DELETE FROM undmedidas
DELETE FROM usuarios
DELETE FROM zonas
INSERT INTO contadores (codcon, numcon, descon, caucon, numini, numfin, numauto, conres, preres, actcon, tipoher, tipclas)
INSERT INTO detnomiele (numnom, codclas, codcon, codnel1, codnel2, devded, nitter, codadm, nomcon, fecini, fecfin,
INSERT INTO facaprocre (numfven, codclas, nitter, obscre, valapro, salante, coddin)
INSERT INTO nomiconcuf (codadm, codcon, tippar, nitter, cuedeb, cuecre, nitdeb, nitcre, tipfij, codsum, valopf)
INSERT INTO resdian (codres, numres, fecres, numini, numfin, preres, actres, texres, freshas, nmeses, aplvig)
SELECT * FROM cecostos;
SELECT * FROM contadores
SELECT * FROM conteoinv
SELECT * FROM credclaves
SELECT * FROM cuentaspuc
SELECT * FROM detbodegas
SELECT * FROM detcajarq
SELECT * FROM detcompras
SELECT * FROM detcuentas
SELECT * FROM detnomiele
SELECT * FROM domicilios
SELECT * FROM facaprocre
SELECT * FROM fincas
SELECT * FROM lecturas
SELECT * FROM linea2
SELECT * FROM listapre
SELECT * FROM listapre;
SELECT * FROM mediomag
SELECT * FROM mesas
SELECT * FROM nomiconcep
SELECT * FROM nomisumcab;
SELECT * FROM paises;
SELECT * FROM pedidores
SELECT * FROM productos
SELECT * FROM provetecno
SELECT * FROM recepmerca
SELECT * FROM regiones;
SELECT * FROM servicios
SELECT * FROM servicios;
SELECT * FROM subinventa;
SELECT * FROM sucursales
SELECT * FROM terceros
SELECT * FROM undmedidas;
SELECT * FROM usuarios
SELECT * FROM variosdet
SELECT * FROM zonas;
SELECT Count(
SELECT SUM((detcompras.valuni - detcompras.dctpes) * detcompras.candet) AS subtota,
SELECT SUM((detfventas.valuni - detfventas.dctpes + detfventas.ivapes + detfventas.ipopes) * detfventas.candet) AS total
SELECT SUM(detfventas.valuni * detfventas.candet) AS subvuni, SUM(detfventas.dctpes * detfventas.candet) AS subdct,
SELECT Sum(detcuentas.valdeb)
SELECT Sum(detcuentas.valhab)
SELECT Sum(detnomiele.valdve) AS valdeve, Sum(detnomiele.valddu) AS valdedu, detnomiele.nitter, terceros.nomcom
SELECT auxfiscal1.codclas, auxfiscal1.predoc, auxfiscal1.subtot, auxfiscal1.valimp,
SELECT auxfiscal1.detalle, auxfiscal1.subtot, auxfiscal1.numtran, auxfiscal1.tippag
SELECT auxrepconta.codcue, auxrepconta.nitter, auxrepconta.detcue, auxrepconta.fecdoc, auxrepconta.codclas, auxrepconta.numnum, auxrepconta.codcos,
SELECT codres FROM
SELECT codzon FROM zonas
SELECT compras.precom AS prefijo, compras.feccom AS fecd, compras.faccom AS docext,
SELECT descaj FROM cajas
SELECT detapago.afepag
SELECT detcompras.codprod, productos.nomprod, productos.tipser, productos.manser, productos.pidfor FROM detcompras
SELECT detcompras.codprod, productos.nomprod, productos.tipser, productos.manser, productos.pidfor, productos.pidecos FROM detcompras
SELECT detcuentas.codcue
SELECT detcuentas.codcue FROM detcuentas
SELECT detcuentas.codemp
SELECT detcuentas.fecdoc, detcuentas.numnum, detcuentas.codclas, detcuentas.codprod
SELECT detcuentas.fecdoc, detcuentas.numnum, detcuentas.codclas, detcuentas.detcue, detcuentas.codcue, detcuentas.numite,
SELECT detcuentas.numnum
SELECT detcuentas.numnum, detcuentas.codclas, detcuentas.codemp, detcuentas.fecdoc,
SELECT detcuentas.numnum, detcuentas.prenum, detcuentas.codclas, cuentaspuc.natcue,
SELECT detfvensub.numite, detfvensub.codprod, detfvensub.candet, detfvensub.cosprod, detfvensub.codbod, detfvensub.codmed,
SELECT detpresupues.numpre, detpresupues.codrub, detpresupues.nomdet, detpresupues.valdeb, detpresupues.valhab, detpresupues.fecdoc,
SELECT domicilios.numcom, domicilios.fecdoc, domicilios.fecent, domicilios.nomcom, domicilios.totdoc, domicilios.priorid,
SELECT facventas.numfven
SELECT facventas.numfven, (facventas.subfven - facventas.totdct + facventas.totiva + facventas.totipo) AS total
SELECT formapago.codcue
SELECT indgen FROM cajas
SELECT linea2.impmes
SELECT nomlin FROM linea
SELECT nomzon FROM zonas
SELECT numfin FROM
SELECT preciosxpro.venprod, preciosxpro.veniva, listapre.nomlis, listapre.codlis AS codelis FROM preciosxpro
SELECT productos.codprod
SELECT productos.codprod, productos.codbar, productos.nomprod, productos.pvsini, productos.pvconi, productos.codmed,
SELECT productos.desprod
SELECT produndmeds.codmed, produndmeds.facumed, produndmeds.divmul, produndmeds.pventa, produndmeds.tipovc, undmedidas.medpres FROM produndmeds
SELECT resdian.numres, resdian.preres, resdian.fecres, resdian.freshas, resdian.numini, resdian.numfin FROM auxfiscal1
SELECT revelaciones.codper, revelaciones.tiprev, revelaciones.numrev, revelaciones.obsrev FROM revelaciones
SELECT subproduct.codprod, subproduct.codsubp, subproduct.cansub, productos.nomprod
SELECT ubiprodbod.codbod, ubiprodbod.stockmin, ubiprodbod.stockmax FROM ubiprodbod
Select productos.codlin1
UPDATE contratoemp SET
UPDATE cuentpresup SET
UPDATE resolpuc SET
UPDATE terceros SET
```

## Tablas mencionadas en los SQL (79)

| Tabla | Menciones |
|---|---|
| `zonas` | 4 |
| `cajas` | 3 |
| `contadores` | 3 |
| `credclaves` | 3 |
| `listapre` | 3 |
| `detcompras` | 3 |
| `preciosxpro` | 2 |
| `auxinvserial` | 2 |
| `cuentpresup` | 2 |
| `fincas` | 2 |
| `lecturas` | 2 |
| `linea2` | 2 |
| `mediomag` | 2 |
| `mesas` | 2 |
| `nomisumcab` | 2 |
| `produndmeds` | 2 |
| `regiones` | 2 |
| `resolpuc` | 2 |
| `revelaciones` | 2 |
| `subinventa` | 2 |
| `ubiprodbod` | 2 |
| `undmedidas` | 2 |
| `usuarios` | 2 |
| `detnomiele` | 2 |
| `facaprocre` | 2 |
| `detcuentas` | 2 |
| `servicios` | 2 |
| `terceros` | 2 |
| `archadjunto` | 1 |
| `auxcompven` | 1 |
| `auxdcuentpuc` | 1 |
| `auxmedmag1` | 1 |
| `auxmetafac` | 1 |
| `bancos` | 1 |
| `cierresper` | 1 |
| `ciudades` | 1 |
| `concepingegr` | 1 |
| `detimpuestos` | 1 |
| `detpedreseli` | 1 |
| `empfpago` | 1 |
| `emplecoman` | 1 |
| `linea1` | 1 |
| `nomiconempl` | 1 |
| `paranomicos` | 1 |
| `pararepcxcp` | 1 |
| `permisoscab` | 1 |
| `permisosfac` | 1 |
| `permisosusu` | 1 |
| `preciosxdct` | 1 |
| `prodactfij` | 1 |
| `prodacttar` | 1 |
| `prodcamposad` | 1 |
| `prodcodbars` | 1 |
| `prodserlotes` | 1 |
| `solcreapro` | 1 |
| `solcreditos` | 1 |
| `subproduct` | 1 |
| `sucretencion` | 1 |
| `tercecorreo` | 1 |
| `terceepsasi` | 1 |
| `nomiconcuf` | 1 |
| `resdian` | 1 |
| `cecostos` | 1 |
| `conteoinv` | 1 |
| `cuentaspuc` | 1 |
| `detbodegas` | 1 |
| `detcajarq` | 1 |
| `domicilios` | 1 |
| `nomiconcep` | 1 |
| `paises` | 1 |
| `pedidores` | 1 |
| `productos` | 1 |
| `provetecno` | 1 |
| `recepmerca` | 1 |
| `sucursales` | 1 |
| `variosdet` | 1 |
| `linea` | 1 |
| `auxfiscal1` | 1 |
| `contratoemp` | 1 |

## Estilo de acceso a datos

- Sentencias con marcador de parametro `?`: **0** de 147
- El resto no muestra parametros -> SQL armado por concatenacion [I]
- Cadenas con `DRIVER={` (ODBC DSN inline): **0**
- Cadenas con `OdbcConnection`/`MySqlConnection`: **0**
