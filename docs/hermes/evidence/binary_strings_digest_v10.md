# Evidencia — literales de `SgHermes.exe` v10.0.0.3

> Fecha: 2026-10-21
> Artefacto: `SgHermes.exe` v10.0.0.3 — SHA-256 `39d4f2d4083ba0432fa224836500f7cfc32a0f4bb473473122b59d4d25073113` — 39.016.448 bytes
> Método: barrido estático de cadenas UTF-16LE y ASCII. Sin ejecución.
> **No sustituye** `evidence/binary_strings_digest.md`, que corresponde al binario 9.1.0 (37.760.512 bytes). Los conteos **no son comparables** (aquel dedupe, este no).

## 1. Volumen

| Métrica | Valor |
|---|---:|
| Cadenas UTF-16LE (mín. 5 caracteres) | 30.429 |
| Cadenas ASCII (mín. 6 caracteres) | 60.393 |
| Literales con forma de sentencia SQL | **1.959** |

El heap `#US` de .NET guarda los literales en UTF-16LE; el barrido ASCII sólo recupera una fracción.

## 2. Términos de dominio (UTF-16LE)

| Término | Apariciones |
|---|---:|
| `iva` | 523 |
| `productos` | 508 |
| `terceros` | 324 |
| `candet` | 232 |
| `caja` | 213 |
| `hermes` | 200 |
| `detfventas` | 177 |
| `usuario` | 136 |
| `contadores` | 132 |
| `dian` | 74 |
| `sgh` | 70 |
| `retencion` | 52 |
| `serial` | 51 |
| `preciosxpro` | 46 |
| `formapago` | 46 |
| `clave` | 28 |
| `exiprod` | 23 |
| `qr` | 22 |
| `peso` | 20 |
| `cufe` | 19 |
| `prefijo` | 18 |
| `dataico` | 16 |
| `qrcode` | 10 |
| `odbc` | 8 |
| `mysql` | 6 |
| `resolucion` | 5 |
| `tara` | 3 |
| `scale` | 2 |
| `kilo` | 2 |
| `password` | 2 |
| `facturacion electronica` | 1 |

## 3. Referencias a tablas

| Tabla | Apariciones |
|---|---:|
| `productos` | 521 |
| `compras` | 476 |
| `detcuentas` | 408 |
| `terceros` | 337 |
| `facventas` | 270 |
| `detfventas` | 177 |
| `detcompras` | 157 |
| `contadores` | 142 |
| `cuentaspuc` | 101 |
| `usuarios` | 66 |
| `parametros` | 61 |
| `formapago` | 56 |
| `preciosxpro` | 52 |
| `resdian` | 47 |
| `undmedidas` | 28 |
| `auxinventario` | 15 |
| `empresas` | 11 |
| `permisosusu` | 4 |
| `usuauditoria` | 3 |

## 4. Cadena de conexión: fragmentos sueltos

```
SERVER=        DATABASE=      UID=        PWD=
ConnectionString / Connectionstring
get_ConnectionString / set_ConnectionString
```

No aparece la cadena completa: se arma en ejecución (`Hermes\Bconexion.cs:47`).

## 5. SQL embebido — muestras

Mantenimiento de tablas auxiliares (patrón "recalcular desde cero"):

```sql
DELETE FROM auxcompven;
DELETE FROM auxdcuentpuc
DELETE FROM auxdetcompven;
DELETE FROM auxdetcue
DELETE FROM auxdetdoc
DELETE FROM auxdetforpag;
DELETE FROM auxdetimp1;
DELETE FROM auxdetimp2;
DELETE FROM auxdetrep;
DELETE FROM auxdoc
DELETE FROM archadjunto
DELETE FROM  preciosxpro
```

Agregados contables:

```sql
(SELECT Sum(detcuentas.valdeb)
(SELECT Sum(detcuentas.valhab)
```

Actualización de inventario (desde el código, no del heap):

```sql
UPDATE productos SET exiprod = '…'
UPDATE productos SET exiprod = exiprod + '…'
```

## 6. Lectura

1. Sin ORM ni repositorio: SQL concatenado y `DELETE FROM` masivo sobre `aux*` para recálculos.
2. La lógica de negocio está en el binario; el camino de ventas no depende de stored procedures.
3. `cufe`, `qrcode`, `dataico` y `dian` presentes en el heap: la FE está compilada dentro, desactivada por configuración.

## 7. Reproducibilidad

- Script: `%TEMP%\opencode\hermes_strings.py` (regex sobre el binario).
- Salida estructurada: `%TEMP%\opencode\hermes_strings.json`.
- Script equivalente del corpus base: `evidence/extract_strings.py`.
