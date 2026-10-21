# Base `masvital` en vivo — snapshot 2026-10

> Fecha: 2026-10-21
> Modo: **solo lectura** (`SHOW` / `SELECT` / `information_schema`). No se ejecutó ninguna escritura.
> Complementa `evidence/schema_2024.sql` (175 tablas, MotoShop) y `evidence/data_dictionary.md`.
> Este snapshot corresponde a la base **`masvital`** de la instalación con SgHermes **10.0.0.3**.

## 1. Servidor

| Campo | Valor |
|---|---|
| Motor | MySQL `5.0.45-community-nt` |
| Servicio | `MySQL` (Running), PID 3536, puerto 3306 |
| Bases | `information_schema`, `masvital`, `mysql`, `test` |
| Base de negocio | `masvital` |
| Tablas | **179** (vs 175 en `schema_2024.sql`) |
| Motor de tablas | **MyISAM — 179/179** |
| Charset | `latin1` / `latin1_swedish_ci` |
| Auth | `root` **sin password** |
| Config efectiva | `servidor.txt` en **VirtualStore** (UAC), no en Program Files — ver `masvital_v10_delta.md` §7.5 |

## 2. Volumetría

| Tabla | Filas |
|---|---:|
| `detcuentas` | 38.337 |
| `detfventas` | 7.818 |
| `usuauditoria` | 5.444 |
| `detapago` | 3.840 |
| `facventas` | 3.547 |
| `cuentaspuc` | 2.721 |
| `detcompras` | 1.551 |
| `ciudades` | 1.120 |
| `usuingre` | 767 |
| `productos` | 689 |
| `auxinventario` | 681 |
| `terceros` | 513 |
| `compras` | 216 |
| `preciosxpro` | 90 |
| `contadores` | 57 |
| `formapago` | 20 |
| `empresas` | 1 |
| `resdian` | **0** |

Actividad: **3.547 facturas** entre **2026-06-04 14:01:46** y **2026-10-20 18:16:58** (≈ 24/día), 7.818 líneas.

## 3. Tipos: no existe un solo `DECIMAL`

| Tabla.columna | Tipo |
|---|---|
| `detfventas.candet` | `double` |
| `detfventas.valuni`, `totdet` | `double` |
| `facventas.subfven`, `totiva`, `totfven`, `totdct`, `retfte`, `retiva` | `double` |
| `productos.exiprod`, `cosprod`, `pvsini`, `pvconi`, `valmed` | `double` |
| `preciosxpro.venprod`, `veniva` | `double` |

Confirma el hallazgo del blueprint: dinero y cantidades en punto flotante. En el destino: `DECIMAL(12,2)` / `DECIMAL(12,3)`.

## 4. `productos.exiprod` mezcla unidades

No existe `productos.existencia`; la columna real es `exiprod`. Su unidad depende del producto:

| Producto | `codmed` | `presen` | `exiprod` | Unidad real |
|---|---|---|---|---|
| `OLAM001` ALMENDRA AMERICANA | 003 | GRAMO | 1.268,002 | gramos |
| `OLAM002` ARANDANOS | 003 | GRAMO | 1.227 | gramos |
| `HAB001` HABAS SALADAS * GRAMO | 003 | GRAMO | 1.422 | gramos |
| `7707242892013` MANI SIN SAL * GRAMO | 003 | GRAMO | 788 | gramos |
| `7707242890101` MANI SALADO X 50 GRAMOS | 001 | UNIDAD | 9 | unidades |
| `KAR0028` LINAZA DOY PACK x 250g | 001 | UNIDAD | 2 | unidades |

`valmed` (peso por unidad) es **0** en toda la muestra: no hay factor presentación↔gramo almacenado.

## 5. Ventas a granel (3 decimales)

17 de 7.818 líneas tienen cantidad fraccionaria:

| Factura | Producto | `candet` | `valuni` | `totdet` |
|---:|---|---:|---:|---:|
| 935 | `OLAM001` ALMENDRA AMERICANA | 21,428 | 70 | 1.499,96 |
| 752 | `OLAM016` PISTACHOS | 136,36 | 110 | 14.999,60 |
| 316 | `OLAM017` DATILES DESHIDRATADO | 135,28 | 37 | 5.005,36 |
| 1246 | `OLAM006` NUEZ NOGAL ENTERA | 12,5 | 80 | 1.000,00 |
| 1246 | `OLAM007` NUEZ PECANS | 7,142 | 140 | 999,88 |
| 312 | `OLAM021` COCO CHIPS HOJUELA NATURAL | 39,21 | 51 | 1.999,71 |

Precio por gramo (`OLAM001` = 70 COP/g). **Contradicción a verificar:** `parametros.DECICANT = 0` frente a estas cantidades de 3 decimales.

Top por cantidad (gramos y unidades mezclados):

| Código | Producto | Cantidad | Líneas |
|---|---|---:|---:|
| `OLAM001` | ALMENDRA AMERICANA | 9.231,998 | 172 |
| `OLAM017` | DATILES DESHIDRATADO | 9.135,28 | 97 |
| `OLAM003` | PASA DELGADA | 8.256 | 86 |
| `OLAM002` | ARANDANOS | 7.773 | 136 |
| `OLAM004` | CIRUELA | 6.760 | 75 |

## 6. Unidades (`undmedidas`)

| Código | Nombre | Presentación | DIAN |
|---|---|---|---|
| 001 | UNIDAD | UND | 94 |
| 002 | CAJA | CAJA | BX |
| 003 | GRAMO | GRAMO | GRM |
| 004 | LIBRA | LIBRA | LBR |
| 005 | KILOGRAMO | KILO | KGM |
| 006 | UNIDAD DE MASA ATOMICA | ARROBA | KGM |
| 007 | BOLSA SUPER AGRANEL | BULTO | 43 |
| 008 | GALON | GALON | GLL |

## 7. Contadores: un solo documento vivo

| Contador | Documento | Prefijo | Consecutivo | `esfelec` |
|---|---|---|---:|---|
| **S15** | **FACTURA DE VENTA POS** | **FVP** | **3.548** | N |
| S08 | FACTURA DE VENTA | FV | 1 | N |
| S18 | COMPRA | COM | 217 | N |
| S02 | COMPROBANTE DE EGRESO | CE | 40 | N |
| S01 | RECIBO DE CAJA | RC | 15 | N |
| S16 | DEVOLUCION POS | DP | 6 | N |
| S28 | NOTA DE SALIDA | SAL | 5 | N |
| S27 | NOTA DE ENTRADA | ENT | 3 | N |

57 contadores en total: **todos** con `esfelec='N'` y `resdian='NO'`. `resdian` **sin filas**. Últimas facturas: `FVP` 3547 → 3540, del 2026-10-20, todas `estfven='B'` y `estfele='N'`.

## 8. Formas de pago (`formapago`, 20)

| Código | Forma | PUC |
|---|---|---|
| F01 | EFECTIVO | 11050501 |
| F02 | CHEQUE | 11050501 |
| F03 | TARJETA DEBITO | 11100501 |
| F04 | TARJETA CREDITO | 11100501 |
| F07 | TRANSFERENCIA BANCO | 11100501 |
| F10 | CUENTAS X COBRAR | 13050501 |
| F11 | CUENTAS X PAGAR | 22050101 |
| F12 | ANTICIPOS O SALDOS A FAVOR | 28050501 |

## 9. Empresa

`empresas` tiene una fila: `empcod = E01`, `nomemp = PRINCIPAL`.
Impresión: "Tienda Saludable y Funcional", CL 18 n25-94 esquina Centro, Pasto-Nariño, Tel 3116978695, **"No Responsable De IVA"**.

## 10. Parámetros

| Clave | Valor |
|---|---|
| `DECIGEN` | 2 |
| `DECICANT` | **0** |
| `IMPKARDEX` | 3 |
| `STOCKMIN` / `STOCKMAX` | NO / NO |
| `OBLICAUTPAG` | SI |
| `VALUVT` | 26.841 |
| `LETMONE` / `LETCENTA` | Peso / Centavo |

## 11. Usuarios: claves sin hash

`usuarios` (6 filas), `clausu varchar(30)` en claro:

| Usuario | `clausu` | Nivel |
|---|---|---|
| ADMIN | `xtd4` | 1 |
| ADMIN2 | `xtd4` | 1 |
| KAROLINA | `u6kl` | 2 |
| VALERIA | `dfcd` | 2 |
| FRANCIA | `qqc4` | 2 |
| JENNY | `qdzo` | 2 |

## 12. Riesgos específicos de esta base

| # | Riesgo | Acción |
|---|---|---|
| 1 | `double` en dinero y cantidades | `DECIMAL(12,2)` / `DECIMAL(12,3)` + recálculo |
| 2 | `exiprod` mezcla gramos y unidades | Convertir por `codmed`; recalcular desde movimientos |
| 3 | Sin factor presentación↔gramo (`valmed = 0`) | Definir factor por producto en el maestro nuevo |
| 4 | `DECICANT = 0` vs ventas con 3 decimales | Fijar precisión canónica (3) |
| 5 | FE DIAN apagada (`esfelec=N`, `resdian` vacía) | Activar proveedor + resolución |
| 6 | MyISAM, sin PK ni FKs | Migrar a InnoDB con claves |
| 7 | `latin1` | Migrar a `utf8mb4` |
| 8 | Claves en claro y `root` sin password | Reset + hash; restringir 3306 |
| 9 | Continuidad de numeración `FVP` desde 3.548 | Mapear prefijo y consecutivo |

## 13. Consultas ejecutadas (todas de lectura)

`SHOW DATABASES` · `SELECT` sobre `information_schema.TABLES` / `.COLUMNS` · `SELECT` sobre `empresas`, `contadores`, `formapago`, `resdian`, `undmedidas`, `parametros`, `usuarios`, `productos`, `preciosxpro`, `facventas`, `detfventas`, `terceros`.
