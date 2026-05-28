# Plan General - javidevmoto

---

## 1. Lo que hay (Estado actual)

### Infraestructura local

| Recurso | Detalle |
|---------|---------|
| **Sistema** | Windows (PC MotoShop) |
| **Python** | 3.14.5 |
| **Git** | ✔ Instalado y configurado |
| **GitHub** | Repo: `github.com/javierportillar/javidevmoto.git` |
| **SSH** | Key ed25519 configurada |

### Base de datos: motoshop2024

| Atributo | Valor |
|----------|-------|
| Motor | **MySQL 5.0** |
| Host | `localhost:3306` |
| User | `root` (sin contraseña) |
| Tablas | **179** (motor MyISAM) |
| Sistema origen | sgHermes (ERP contable/facturación colombiano) |
| Tamaño aprox | ~137k filas en tabla más grande (detcuentas) |

### Principales dominios de datos disponibles

- **Productos e inventario** (6,185 productos, 26k movimientos)
- **Ventas y facturación** (6,333 facturas, 27k detalles)
- **Compras** (761 compras, 11k detalles)
- **Terceros / Clientes** (161 registros)
- **Contabilidad PUC** (2,736 cuentas, 137k movimientos)
- **Sucursales, presupuesto, nómina, bancos, financiación**
- **Facturación electrónica** (resoluciones DIAN)

---

## 2. Lo que se quiere hacer (Objetivo)

### Visión general

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   MySQL 5.0      │ ──► │   Databricks     │ ──► │   Data Lake /    │
│   motoshop2024   │      │   (ETL/ELT)      │      │   Procesamiento  │
│   (sgHermes)     │      │                  │      │   Reportes / ML  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

### Pipeline propuesto (a alto nivel)

#### Fase 1: Extracción (Extract)
- Conectar Databricks a MySQL 5.0 vía JDBC
- Seleccionar tablas relevantes para el análisis
- Definir frecuencia de extracción (diaria/semanal)
- Manejar tablas grandes (detcuentas: 137k registros)

#### Fase 2: Transformación (Transform)
- Limpieza y normalización de datos
- Tipado correcto (MySQL 5.0 es flexible, Databricks requiere esquema)
- Manejo de nulos y valores por defecto
- Uniones entre tablas del mismo dominio
- Construcción de vistas analíticas

#### Fase 3: Carga (Load)
- Tablas bronze (capa cruda, copy exacto)
- Tablas silver (datos limpios y modelados)
- Tablas gold (vistas para reportes/ML)

#### Fase 4: Consumo
- Dashboards en Databricks SQL
- Notebooks de análisis
- Modelos de ML (predicción de ventas, clasificación de productos, etc.)

---

## 3. Priorización sugerida

### Inmediato (Sprint 1)
1. Conexión Databricks → MySQL probada
2. Extracción de tablas principales: `productos`, `facventas`, `detfventas`, `terceros`
3. Capa bronze funcional

### Corto plazo (Sprint 2)
4. Tablas de inventario: `auxinventario`, `bodegas`, `traslados`
5. Tablas de compras: `compras`, `detcompras`
6. Tablas contables: `cuentaspuc`, `detcuentas`
7. Capa silver con joins y limpieza

### Mediano plazo (Sprint 3+)
8. Automatización del pipeline (schedule)
9. Dashboards operativos
10. Modelos predictivos

---

## 4. Riesgos y consideraciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| MySQL 5.0 sin soporte oficial | Compatibilidad JDBC | Usar driver mysql-connector-java-5.x |
| MyISAM sin transacciones | Consistencia en extracción | Marcar bookmarks por fecha |
| BD en producción local | Contención de recursos | Extraer en horario de bajo uso |
| Sin contraseña root | Seguridad | Considerar crear usuario restringido para Databricks |
| sgHermes no documentado | Curva de aprendizaje del esquema | Usar infollm.md como referencia constante |

---

## 5. Stack tecnológico

| Herramienta | Uso |
|-------------|-----|
| **Python 3.14** | Scripts de extracción local, pruebas |
| **Databricks** | Pipeline ETL, procesamiento distribuido |
| **MySQL 5.0 + JDBC** | Fuente de datos |
| **Git + GitHub** | Control de versiones |
| **SQLAlchemy / PyMySQL** | Conexión Python → MySQL |

---

## 6. Próximos pasos concretos

- [ ] Crear repo en GitHub (`javierportillar/javidevmoto`) y pushear
- [ ] Probar conexión Databricks → MySQL usando infollm.md
- [ ] Definir qué tablas se llevan a bronze primero
- [ ] Escribir notebook de extracción inicial
- [ ] Decidir frecuencia de sincronización
