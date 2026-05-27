# infollm - Guía de Conexión a Base de Datos

## 1. Conexión MySQL

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Puerto | `3306` |
| Base de datos | `motoshop2024` |
| Usuario | `root` |
| Contraseña | *(vacío)* |
| Motor | MySQL 5.0 |
| Engine tablas | MyISAM |
| Driver ODBC | `MySQL ODBC 5.1 Driver` |
| Ubicación datos | `C:\Program Files (x86)\MySQL\MySQL Server 5.0\Data\` |

### JDBC URI
```
jdbc:mysql://localhost:3306/motoshop2024?useSSL=false&allowPublicKeyRetrieval=true
```

### Python SQLAlchemy
```python
from sqlalchemy import create_engine

engine = create_engine("mysql+pymysql://root@localhost:3306/motoshop2024")
```

### Python mysql-connector
```python
import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="",
    database="motoshop2024"
)
```

### ODBC Connection String
```
Driver={MySQL ODBC 5.1 Driver};Server=localhost;Port=3306;Database=motoshop2024;User=root;Password=;Option=3;
```

### Databricks JDBC
```
jdbc:mysql://localhost:3306/motoshop2024?user=root&password=&useSSL=false
```

---

## 2. Esquema General

La base de datos `motoshop2024` pertenece al sistema **sgHermes** (ERP colombiano). Contiene **179 tablas** con datos operativos de un motociclista/tienda.

### Tablas con más registros

| Tabla | Filas | Descripción |
|-------|-------|-------------|
| `detcuentas` | 137,256 | Detalle de cuentas contables |
| `detcompras` | 11,621 | Detalle de compras |
| `detapago` | 8,035 | Detalle de abonos/pagos |
| `facventas` | 6,333 | Facturas de venta |
| `productos` | 6,185 | Catálogo de productos |
| `cuentaspuc` | 2,736 | Plan Único de Cuentas (PUC) |
| `auxinventario` | 26,174 | Auxiliar de inventario |
| `detfventas` | 27,740 | Detalle de facturas de venta |
| `ciudades` | 1,120 | Ciudades/municipios |
| `compras` | 761 | Cabecera de compras |

### Dominios del negocio

| Dominio | Tablas principales |
|---------|-------------------|
| **Productos** | `productos`, `prodserlotes`, `prodcodbars`, `produndmeds`, `preciosxpro`, `preciosxdct`, `subproduct`, `listapre` |
| **Ventas** | `facventas`, `detfventas`, `formapago`, `despachos`, `detdespachos`, `domicilios` |
| **Compras** | `compras`, `detcompras`, `recepmerca`, `detrecepmerca` |
| **Terceros** | `terceros`, `tercecorreo`, `terceepsasi`, `seguimcli` |
| **Inventario** | `productos`, `bodegas`, `auxinventario`, `traslados`, `dettraslado`, `entsalida`, `detentsalida`, `subinventa`, `conteoinv`, `detconteoinv` |
| **Contabilidad** | `cuentaspuc`, `detcuentas`, `compdiario`, `comprobantes`, `concepingegr`, `cierresper` |
| **Sucursales** | `sucursales`, `sucbloqcab`, `sucbloqdet`, `succategoria`, `sucestratos` |
| **Usuarios** | `usuarios`, `usuapermiso`, `permisoscab`, `permisosusu`, `permisosfac` |
| **Financiación** | `financiacion`, `factorfin`, `detfinancia`, `solcreditos`, `solcreapro` |
| **Bancos** | `bancos`, `bancosemp`, `consbancab`, `consbandet` |
| **Nómina** | `nominas`, `detnomina`, `nomiconcep`, `nomiconcuf`, `nomiconempl`, `nomisumcab`, `nomisumdet`, `retftenomina` |
| **Presupuesto** | `presupuesto`, `detpresupues`, `cuentpresup`, `presupanos` |
| **Resoluciones DIAN** | `resolpuc`, `respdocfele`, `resdian` |
| **Facturación electrónica** | `respdocfele`, `resdian`, `conimpdoc` |

---

## 3. Columnas comunes

Casi todas las tablas siguen estas convenciones:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `codemp` | varchar(15) | Código de empresa |
| `codclas` | varchar(4) | Clase de documento |
| `numnum` / `numdoc` / `numcom` | varchar(20) | Número de documento |
| `fecdoc` | datetime | Fecha del documento |
| `nitter` | varchar(15) | NIT del tercero |
| `codres` | varchar(4) | Código de resolución |
| `empcod` | varchar(3) | Código de empresa (alterno) |
| `codbod` | varchar(4) | Código de bodega |
| `codcos` | varchar(6) | Código de centro de costo |
| `codpag` | varchar(4) | Código de forma de pago |
| `codprod` | varchar(20) | Código de producto |
| `estdoc` | char(1) | Estado del documento (A=Activo, N=Anulado) |

---

## 4. Notas importantes

- **MySQL 5.0 antiguo** — Usar driver compatible (mysql-connector-java-5.x para JDBC)
- **Autenticación**: Usar `mysql_native_password`, NO `caching_sha2_password`
- **Todas las tablas son MyISAM** — No hay transacciones ni foreign keys declarativas
- **No hay contraseña** para root — conexión directa
- **sgHermes** es un ERP contable/facturación colombiano — las tablas siguen convenciones contables colombianas (PUC, DIAN, etc.)
- Para consultas desde Databricks, se recomienda usar JDBC con `useSSL=false`
