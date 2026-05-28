# Plan de Transformación Digital - MotoShop

> Aplicación práctica del marco conceptual desarrollado en el curso **Big Data y Transformación Digital del Negocio** (Maestría IA & Ciencia de Datos, UAO 2025-2) sobre la base de datos real de MotoShop (`motoshop2024`, sgHermes), con dos tracks: **analítica escalable en Databricks Lakehouse** y **acceso remoto operativo vía PWA**.

---

## 1. Visión

> *Llevar a MotoShop de un negocio que registra datos a uno que **decide con datos y opera desde cualquier lugar**, pasando de reportes operativos en una sola máquina a una plataforma analítica (descriptiva → predictiva → prospectiva) y un canal remoto de consulta/operación, sin reemplazar sgHermes.*

### Evolución analítica buscada

```
   Descriptiva          Diagnóstica          Predictiva          Prospectiva
   ¿Qué pasó?           ¿Por qué pasó?       ¿Qué va a pasar?    ¿Qué debería pasar?
   ───────────          ──────────────       ──────────────      ──────────────────
   Dashboards           Drill-down,          Forecasting de      Optimización de
   de ventas,           segmentación,        demanda por SKU,    compras, escenarios
   inventario,          análisis de          alertas de          de demanda, what-if
   rotación             cohortes, ABC        quiebre             de precios/promos
        ↑                    ↑                    ↑                    ↑
     Fase 3               Fase 3               Fase 4               Fase 6
```

### Dos tracks paralelos

- **Track A · Analítico** — Databricks Lakehouse (medallion): bronze → silver → gold + ML.
- **Track T · Transaccional** — API + PWA para consulta remota; en fases posteriores, escritura limitada vía tablas InnoDB nuevas.

---

## 2. Puente con los talleres del curso

| Módulo | Aporte conceptual | Aterrizaje en este plan |
|--------|-------------------|--------------------------|
| **M2** — Criterios técnicos y stack | Diagnóstico de escalabilidad/latencia + herramientas | §4 Arquitectura + §11 Stack + Anexo A |
| **M3** — Decisión crítica + modelo ML | Predicción de demanda por SKU + alertas de quiebre | §5 Casos de uso + Fase 4 + Anexo A |
| **M4** — Madurez, VPC, BMC | Arquetipo "Principiante" → hoja de ruta + propuesta de valor + modelo de negocio | §3 Diagnóstico + §13 VPC + §14 BMC + §9 KPIs + Anexo A |

Mapeo detallado entrega por entrega en el **Anexo A · Trazabilidad con los talleres**.

---

## 3. Diagnóstico de partida (Módulo 4 aplicado)

Resultado del autodiagnóstico Forrester / McKinsey / MIT–Capgemini sobre MotoShop:

- **Inversión digital:** baja
- **Capacidad de transformación:** baja (promedio 2/5)
- **Arquetipo:** **Principiante** → objetivo: pasar a **Practicante** en 12 meses

### Situación real

| Dimensión | Estado actual |
|-----------|---------------|
| Infraestructura | MySQL 5.0 local en una sola máquina Windows, sin réplica, sin backups automatizados |
| Engine | MyISAM (sin transacciones, sin FKs) |
| Uso del dato | Operativo/descriptivo desde el ERP; cero analítica avanzada |
| Decisiones | Basadas en intuición y experiencia del personal |
| Pipeline | Inexistente — el dato vive y muere en sgHermes |
| Acceso remoto | Ninguno — solo desde el PC físico |
| Integración con otras fuentes | Ninguna |

### Brechas a cerrar
Flexibilidad, tolerancia a fallos, integración/orquestación, calidad de datos formalizada, elasticidad, gobernanza, **acceso remoto seguro**.

---

## 4. Arquitectura objetivo

```
                       PC MotoShop (Windows)
                       ┌─────────────────────────────┐
                       │  MySQL 5.0 motoshop2024     │
                       │  • sgHermes lee/escribe     │
                       │  • [F5+] tablas InnoDB app  │
                       └──────────┬──────────────────┘
                                  │
                  ┌───────────────┼────────────────┐
                  │ usuario       │ usuario        │
                  │ analytics     │ api_read       │
                  │ (read-only)   │ (read-only)    │
                  ▼               │                ▼
   ┌──────────────────────────┐   │   ┌──────────────────────────┐
   │  TRACK A · DATABRICKS    │   │   │  TRACK T · API + PWA     │
   │  Lakehouse + medallion   │   │   │  FastAPI + Next.js       │
   │                          │   │   │                          │
   │  ┌────┐ ┌────┐ ┌────┐    │   │   │  ┌──────────────────┐    │
   │  │BRN │→│SLV │→│GLD │    │   │   │  │  API FastAPI     │    │
   │  └────┘ └────┘ └────┘    │   │   │  │  (en el PC)      │    │
   │  + Unity Catalog         │   │   │  └────────┬─────────┘    │
   │  + Workflows             │   │   │           │              │
   │  + MLflow                │   │   │  Túnel: Cloudflare       │
   │                          │   │   │  Tunnel / Tailscale      │
   └──────────┬───────────────┘   │   │           │              │
              │                   │   │           ▼              │
              ▼                   │   │  ┌──────────────────┐    │
   ┌──────────────────────────┐   │   │  │  PWA Next.js     │    │
   │  Power BI /              │   │   │  │  (móvil + web)   │    │
   │  Databricks SQL          │   │   │  └──────────────────┘    │
   └──────────────────────────┘   │   └──────────────────────────┘
                                  │
                                  ▼
                          Futuras fuentes:
                          e-commerce, redes,
                          datos externos
```

### Capas del medallion (Track A)

| Capa | Rol | Formato | Contenido |
|------|-----|---------|-----------|
| **Bronze** | Espejo inmutable de la fuente | Delta Lake, particionado por `ingest_date` | Snapshot 1:1 de tablas MySQL, sin transformación |
| **Silver** | Datos conformados, limpios, modelo dimensional | Delta Lake en Unity Catalog | Hechos + dimensiones, tipados, deduplicados |
| **Gold** | Marts analíticos y features para ML | Delta Lake + vistas SQL | Agregaciones, KPIs, features tables |

### Componentes Track T

| Componente | Tecnología | Notas |
|------------|-----------|-------|
| API | FastAPI (Python) | Corre en el PC junto a MySQL |
| Frontend | Next.js + PWA | Instalable en móvil, funciona offline básico |
| Auth | JWT + roles (admin / vendedor / gerente) | Login propio inicialmente |
| Exposición remota | **Cloudflare Tunnel** (recomendado) | Sin abrir puertos en el router |
| BD | `motoshop2024` lectura; InnoDB en F5+ | Tablas `app_*` separadas de sgHermes |

### Justificación de Databricks (aún con volumen pequeño hoy)
- La métrica relevante es **capacidad de escalamiento sin rediseño**, no el volumen actual.
- Delta Lake da **ACID, time-travel, schema evolution** — crítico para auditoría y reproceso.
- **Unity Catalog** centraliza permisos, linaje y catálogo desde el día 1.
- **Workflows** orquestan sin tener que montar Airflow.
- **MLflow** maneja experimentos y model registry para Fase 4.
- Cuando lleguen e-commerce, redes sociales y datos externos, la plataforma ya está lista.

---

## 5. Casos de uso analíticos

### Descriptiva (Fase 3)
- Dashboard ejecutivo de ventas: ingresos por mes, categoría, sucursal, top SKUs, top clientes.
- Dashboard de inventario: stock por bodega, días de cobertura, productos dormidos.

### Diagnóstica (Fase 3)
- Segmentación ABC por ingresos y por rotación.
- Cohortes de clientes (recurrencia, ticket promedio).
- Análisis histórico de quiebres.

### Predictiva (Fase 4) — Módulo 3 directo
- **O1 · Forecasting de demanda por SKU** a 7/30 días. Baseline → Prophet/SARIMA → LightGBM global.
- **O2 · Clasificador de riesgo de quiebre** binario sobre stock + demanda predicha + lead time.
- **O3 · Análisis de sentimiento** (cuando lleguen redes/reseñas — F-B).

### Prospectiva (Fase 6)
- Optimización de compras: dado forecast + lead times + capital, minimizar quiebres y exceso.
- What-if de precios y promociones.
- Escenarios de expansión (nueva sucursal / canal e-commerce).

---

## 6. Mapeo casos de uso → tablas reales

| Caso | Tablas | Notas |
|------|--------|-------|
| Ventas (todos los casos) | `facventas` ⨝ `detfventas` ⨝ `productos` | Filtrar `estdoc = 'A'` |
| Catálogo | `productos`, `subproduct`, `prodcodbars`, `preciosxpro` | Para PWA y dashboard |
| Inventario | `auxinventario`, `bodegas`, `traslados`, `entsalida` | Stock por bodega |
| Compras y proveedores | `compras`, `detcompras`, `terceros` | Lead time histórico |
| Clientes | `terceros` | Cohortes |
| Sucursales | `sucursales` | Dimensión geográfica |
| Contabilidad (F6) | `cuentaspuc`, `detcuentas` | Margen, análisis financiero |
| App (F5+) | `app_cotizaciones`, `app_pedidos_remotos`, `app_sesiones`, `app_audit_log` | InnoDB, separadas de sgHermes |

---

## 7. Plan de entregables — 7 fases

### **Fase 0 · Cimientos** *(2 semanas)*
**Objetivo:** dejar lista la plataforma sin haber tocado dato aún.

| Track A (Analítico) | Track T (Transaccional) |
|---|---|
| Workspace Databricks + Unity Catalog | Repo `motoshop-app` (FastAPI + Next.js) |
| Catálogo `motoshop` + esquemas bronze/silver/gold | Stack base configurado |
| Usuario MySQL `analytics` read-only | Usuario MySQL `api_read` read-only |
| Conectividad PC ↔ Databricks decidida y probada | Cloudflare Tunnel configurado |
| Git + GitHub conectado al workspace | CI básico (lint, tests) |

**Hito:** `SELECT 1` desde Databricks y desde llamada HTTP remota a la API.

---

### **Fase 1 · Ingesta + API de lectura** *(3 semanas)*

| Track A | Track T |
|---|---|
| Job de ingesta diaria a Bronze (12 tablas core) | API: `/products`, `/products/{sku}/stock`, `/sales/recent` |
| Particionado por `ingest_date` | Auth JWT + roles (admin/vendedor/gerente) |
| Bookmarks por `fecdoc` | Rate limiting + logging estructurado |
| Notebook de validación de conteos | Documentación OpenAPI |

**Hito:** desde un celular fuera de la red local, hacer login y consultar stock de un SKU.

---

### **Fase 2 · Silver + PWA MVP** *(3 semanas)*

| Track A | Track T |
|---|---|
| Notebooks bronze → silver con limpieza | PWA: login, búsqueda de productos, ficha de SKU |
| Hechos: `fact_ventas`, `fact_compras`, `fact_inventario` | Vista de inventario por bodega |
| Dimensiones: `dim_producto`, `dim_tiempo`, `dim_tercero`, `dim_sucursal`, `dim_bodega` | Historial de ventas recientes |
| Reglas de calidad (DLT/expectations) | Instalable como app en móvil (manifest PWA) |
| Pruebas unitarias de transformaciones | Modo offline básico (cache de catálogo) |

**Hito:** vendedor en la calle abre la app, busca un repuesto, ve precio y stock por bodega.

---

### **Fase 3 · Gold + Dashboards** *(3 semanas)*

| Track A | Track T |
|---|---|
| Marts: `mart_ventas_diarias_sku`, `mart_inventario_actual`, `mart_rotacion_abc`, `mart_cohortes_clientes` | Sección "Dashboards" en la PWA |
| Dashboard descriptivo en Power BI / Databricks SQL | Vista ejecutiva mobile-first |
| Workflow programado (nocturno) | KPIs propios desde gold (vía API) |
| Segmentación ABC automatizada | Estructura push notifications |

**Hito:** demo a gerencia desde el celular: top SKUs, ventas del mes, productos dormidos.

---

### **Fase 4 · Predictivo (ML)** *(4 semanas)* — Módulo 3 cumplido

| Track A | Track T |
|---|---|
| Feature store: lags, calendarios, festivos COL | Vista "Predicciones": forecast por SKU |
| Baseline (naïve + media móvil) en MLflow | Vista "Alertas": SKUs en riesgo de quiebre |
| Prophet top-100 + LightGBM global cola larga | Push notifications cuando un SKU entra en zona crítica |
| Tabla gold `forecast_demanda_sku` | Filtros por bodega/categoría |
| Clasificador de quiebre + `alertas_quiebre` | |
| Notificaciones por correo desde Workflows | |

**Hito:** la app avisó al gerente que el aceite X va a quebrar en 5 días.

---

### **Fase 5 · Escritura habilitada** *(4 semanas)* — opcional, según validación de F4
**Objetivo:** permitir registrar operaciones desde el frontend (pre-ventas, cotizaciones, pedidos remotos) **sin tocar sgHermes**.

| Track T (foco principal) | Track A (impacto) |
|---|---|
| Tablas InnoDB: `app_cotizaciones`, `app_pedidos_remotos`, `app_sesiones`, `app_audit_log` | Ingesta a bronze de las tablas nuevas |
| Endpoints de escritura | Marts adicionales: conversión cotización→venta |
| Política de numeración separada de sgHermes | KPI: % ventas originadas en app |
| Job de reconciliación cotización → factura sgHermes (manual o semi-auto) | |

**Modelo recomendado:** el vendedor crea una *pre-venta* en `app_pedidos_remotos`; un operador en tienda la convierte en factura formal de sgHermes. Evita conflictos de numeración y bloqueos.

**Hito:** vendedor cierra una cotización en campo → operador la convierte en factura.

---

### **Fase 6 · Prospectivo + Hardening** *(continuo)*

| Track A | Track T |
|---|---|
| Optimización de compras (LP/heurística sobre forecast + lead time) | CI/CD completo + entornos dev/staging/prod |
| What-if de precios y promociones | Observabilidad: métricas, traces, logs centralizados |
| Lineage Unity Catalog completo + permisos por rol | Tests E2E |
| Reentrenamiento automatizado + drift monitoring | App Store / Play Store si se decide ir nativo |

**Hito:** el sistema recomienda qué comprar la próxima semana y gerencia aprueba con un click.

---

### **Fase 7 · Roadmap extendido** *(visión 12+ meses)*

| Fase | Iniciativa | Disparador |
|------|------------|------------|
| F-A | Integración e-commerce (Mercado Libre / tienda propia) | Cuando exista canal digital |
| F-B | Redes sociales + sentiment | Cuando haya presencia digital con tráfico |
| F-C | Datos externos: festivos COL, clima, indicadores macro | Cuando los modelos lo demanden |
| F-D | Prospectiva avanzada: optimización + what-if multi-variable | Tras F6 estable |
| F-E | Streaming (Kafka / Auto Loader) | Cuando latencia < 1 día sea requerimiento |
| F-F | Migración del MySQL local a managed cloud | Cuando dependencia del PC sea riesgo crítico |

---

## 8. Cronograma sugerido

```
Mes 1  ──[F0 Cimientos]──[F1 Ingesta + API]──
Mes 2  ──[F1 cont.]──[F2 Silver + PWA MVP]──
Mes 3  ──[F2 cont.]──[F3 Gold + Dashboards]──
Mes 4  ──[F3 cont.]──[F4 Predictivo]──
Mes 5  ──[F4 cont.]──
Mes 6  ──[Validación + decisión F5]──
Mes 7-8 [F5 Escritura] (si se valida)
Mes 9+ [F6 Hardening + F7 expansión]
```

---

## 9. KPIs (Módulo 4, paso 5)

### KPIs del proyecto

| KPI | Métrica | Meta 6 meses |
|-----|---------|---------------|
| Automatización pipeline | % corridas exitosas sin intervención | > 95% |
| Frescura del dato | Lag venta → dashboard | < 24 h |
| Cobertura analítica | % tablas core en silver | 100% |
| Adopción PWA | Usuarios activos / semana | ≥ 3 |
| Cobertura predictiva | % SKUs top-100 con forecast | 100% |

### KPIs de negocio

| KPI | Métrica | Meta 12 meses |
|-----|---------|----------------|
| Exactitud predicción demanda | MAPE SKUs top-100 | < 25% |
| Precisión alertas de quiebre | F1-score | > 0.7 |
| Reducción de quiebres de stock | Δ% vs. baseline | −30% |
| Reducción de inventario muerto | Δ% SKUs sin venta > 6 meses | −20% |
| Decisiones data-driven | % órdenes de compra justificadas con dato | > 70% |

---

## 10. Entregables académicos (Maestría)

| Entregable | Contenido | Cuándo |
|---|---|---|
| **E1** — Diagnóstico + arquitectura | Plan + diagrama + decisiones técnicas | Fin de Fase 0 |
| **E2** — Pipeline operativo | Repo + notebooks bronze/silver + dato cargado | Fin de Fase 2 |
| **E3** — Producto descriptivo | PWA MVP + dashboard ejecutivo en vivo | Fin de Fase 3 |
| **E4** — Producto predictivo | Modelos en MLflow + alertas funcionando + paper corto del modelo | Fin de Fase 4 |
| **E5** — Memoria final | Documento que une talleres + plan + resultados + KPIs medidos | Cierre |

---

## 11. Stack tecnológico

| Capa | Herramienta | Notas |
|------|-------------|-------|
| Fuente operacional | MySQL 5.0 (motoshop2024) | Existente |
| Ingesta a Lakehouse | Databricks JDBC + Workflows | Driver `mysql-connector-java-5.1.x` |
| Almacenamiento analítico | **Delta Lake** | ACID, time-travel |
| Catálogo y governance | **Unity Catalog** | Permisos, linaje |
| Procesamiento | Spark / Pandas API on Spark | Según volumen |
| Orquestación analítica | **Databricks Workflows** | |
| ML | scikit-learn, lightgbm, prophet, statsforecast + **MLflow** | Tracking + registry |
| BI | **Databricks SQL** o **Power BI** | |
| API operativa | **FastAPI** (Python 3.11+) | Corre en el PC |
| Frontend | **Next.js + PWA** | Web + móvil responsiva |
| Auth | JWT + bcrypt | Login propio |
| Exposición remota | **Cloudflare Tunnel** | Sin abrir puertos del router |
| Versionado | Git + GitHub (`javidevmoto`) | |

---

## 12. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| MySQL 5.0 sin soporte oficial | Compatibilidad JDBC | Driver `mysql-connector-java-5.1.x` probado |
| MyISAM sin transacciones | Inconsistencia en extracción y futura escritura | Snapshot diario; tablas `app_*` en InnoDB cuando llegue F5 |
| BD en PC de producción | Contención de recursos | Jobs nocturnos; query paginada |
| Sin contraseña root | Riesgo de seguridad | Usuarios `analytics` y `api_read` solo lectura con contraseña |
| Conectividad PC ↔ Databricks | El cluster en nube no llega al MySQL local | **Decisión Fase 0:** túnel, Databricks Connect, o self-hosted job que empuja dumps a cloud storage (recomendado) |
| Exposición API remota | Superficie de ataque | Cloudflare Tunnel (no expone puertos) + JWT + rate limiting + logs |
| sgHermes no documentado | Curva de aprendizaje | Documentar tablas usadas en `infollm.md` |
| Pocos datos por SKU | Calidad del forecast | Modelado jerárquico por categoría / top-100 prioritario |
| Datos manuales con errores | Sesgo en el modelo | Reglas de calidad obligatorias |
| Concurrencia sgHermes ↔ app (F5+) | Conflictos de numeración / locks | Tablas `app_*` separadas; reconciliación posterior |
| Costos Databricks | Sobreconsumo de cluster | Autoterminación, jobs vs all-purpose, clusters small |

### Decisión crítica de Fase 0
La BD MySQL vive en un PC local. Hay que decidir cómo hacerla accesible al cluster Databricks (nube). Opciones:
1. **Self-hosted job** Python en el PC que empuja dumps a S3/ADLS/GCS y Databricks ingiere desde ahí. **Recomendado** — desacopla, robusto, sin abrir puertos.
2. Túnel SSH/VPN desde el PC al VPC de Databricks.
3. Replicar MySQL a una instancia gestionada en nube (RDS / Cloud SQL).

---

## 13. Propuesta de valor — VPC (Módulo 4 aplicado)

### Customer Profile · Administrador / Gerencia / Vendedor

**Jobs**
- Mantener niveles óptimos de inventario, saber qué/cuánto/cuándo comprar.
- Consultar stock y ventas desde cualquier lugar.
- Tomar decisiones rápidas con información actualizada.
- Garantizar disponibilidad de repuestos críticos.

**Pains**
- Procesos manuales y dispersión de datos.
- Falta de visibilidad consolidada del inventario.
- Riesgo de quiebre o sobrestock.
- Decisiones basadas en intuición, no en datos.
- Tiempos perdidos en verificaciones manuales.
- Imposibilidad de operar desde fuera del PC físico.

**Gains esperados**
- Sistema centralizado de información.
- Predicciones confiables de demanda por SKU.
- Alertas automáticas de bajo inventario.
- Reportes claros y actualizados.
- Acceso desde móvil para consulta remota.

### Value Map · Nuestra solución

**Products & Services**
- Pipeline Big Data (ingesta, almacenamiento, procesamiento, visualización).
- Data Lake en nube (Delta Lake / cloud storage).
- Modelos ML de demanda y quiebre.
- API + PWA para consulta remota.
- Dashboards ejecutivos.

**Pain Relievers**
- Automatiza verificaciones manuales → reduce error humano.
- Reduce incertidumbre con forecasting.
- Organiza datos históricos en repositorio único.
- Predice quiebres antes de que ocurran.
- Permite operar desde el celular.

**Gain Creators**
- Base para iniciativas futuras (fidelización, e-commerce, microsegmentación).
- Aumenta margen y liquidez al reducir capital atascado.
- Mejora la velocidad de decisión.
- Aumenta competitividad tecnológica.

---

## 14. Modelo de negocio — BMC (Módulo 4 aplicado)

| Bloque | Contenido |
|--------|-----------|
| **Socios Clave** | Proveedores de repuestos (Honda, Yamaha, genéricos), proveedor de cloud (Databricks + cloud storage), Cloudflare (túnel), proveedores de datos externos (clima, festivos). |
| **Actividades Clave** | Ingesta automatizada, transformación medallion, entrenamiento y reentrenamiento de modelos ML, operación API + PWA, dashboards ejecutivos, reconciliación con sgHermes (F5+). |
| **Recursos Clave** | BD `motoshop2024` (histórico), Lakehouse Databricks, modelos ML registrados en MLflow, equipo técnico, conocimiento del dominio motociclista. |
| **Propuesta de Valor** | Predicción de demanda por SKU + alertas tempranas de quiebre + dashboard ejecutivo + consulta de stock/ventas desde cualquier lugar + base sólida para escalar a e-commerce. |
| **Relaciones con Clientes** | Self-service vía PWA, notificaciones push de alertas, dashboards de gerencia, soporte interno. |
| **Canales** | Físico: punto de venta. Digital: PWA (admin/vendedor/gerencia). Automatizado: notificaciones push y correo. Futuro: e-commerce y marketplaces. |
| **Segmentos de Clientes** | Internos: gerencia, vendedores en campo, equipo de inventario, equipo de compras. Externos (futuros): dueños de motos, talleres, mensajeros. |
| **Estructura de Costos** | Infraestructura Databricks (pay-per-use), cloud storage, Cloudflare Tunnel (gratis tier), dominios y SSL, mantenimiento del pipeline y modelos, licencias Power BI si aplica. |
| **Fuentes de Ingresos** | Indirectas (este proyecto no es producto): reducción de pérdidas por stock-out, reducción de inventario muerto, ventas adicionales por venta predictiva, eficiencia operativa. Directas a futuro: ventas vía e-commerce, modelo "as-a-service" para otros talleres. |

---

## 15. Consideraciones éticas y de gobernanza (Módulo 3 aplicado)

- **Privacidad:** `terceros` contiene NIT, nombres, teléfonos, correos. Anonimizar/pseudonimizar en silver para datasets compartidos. Marcar columnas PII en Unity Catalog.
- **Marco legal:** Ley 1581/2012 - Habeas Data Colombia. Validar consentimiento si se usan datos de clientes para campañas.
- **Transparencia algorítmica:** las recomendaciones del modelo son **sugerencias revisables**, no decisiones autónomas (en Fase 4).
- **Calidad como prerrequisito ético:** modelo entrenado sobre inventario inexacto → decisiones inexactas. Reglas de calidad obligatorias en silver.
- **Auditoría:** Delta Lake + Unity Catalog dan time-travel y linaje. La API guarda `app_audit_log` desde F5+.
- **Seguridad operacional (Track T):** JWT con expiración corta + refresh tokens, contraseñas con bcrypt, rate limiting, registro de intentos fallidos.

---

## 16. Decisiones pendientes (Fase 0)

1. **Túnel remoto:** Cloudflare Tunnel (gratis, robusto, recomendado) vs. Tailscale vs. VPS con SSH tunnel.
2. **Hosting de la API:** en el mismo PC junto a MySQL (recomendado) vs. VPS pequeño con túnel inverso.
3. **Autenticación:** login email/password propio vs. integrar Google/Microsoft.
4. **Strategy de conectividad Databricks ↔ MySQL:** self-hosted dump → cloud storage (recomendado) vs. túnel directo vs. réplica gestionada.
5. **BI:** Power BI vs. Databricks SQL vs. ambos (PBI para gerencia, DBX SQL para análisis exploratorio).
6. **Pruebas con usuarios reales:** ¿cuándo y con quién? Idealmente al cierre de F3.

---

## 17. Próximos pasos inmediatos (Semana 1)

- [ ] Crear cuenta/workspace Databricks (Free/Community para arrancar).
- [ ] Crear usuarios MySQL `analytics` y `api_read` (solo lectura, con contraseña).
- [ ] Decidir túnel remoto y conectividad Databricks ↔ MySQL.
- [ ] Estructurar repos:
  - `motoshopdata` (analítica, notebooks, plan, docs).
  - `motoshop-app` (API FastAPI + PWA Next.js).
- [ ] Lista definitiva de las 12 tablas que entran a bronze.
- [ ] Diagrama de arquitectura validado con stakeholder.

---

## Anexo A · Trazabilidad con los talleres del curso

### A.1 Módulo 2 — Criterios técnicos

| Criterio (nivel en taller) | Cómo lo resuelve este plan | Estado |
|---|---|---|
| Escalabilidad (Inicial 2) | §4 Lakehouse + Spark + cloud storage elástico | ✅ |
| Flexibilidad/adaptabilidad (Inexistente 1) | §4 medallion separa ingesta/almacén/proc/consumo | ✅ |
| Baja latencia (Inicial 2) | Hoy batch diario; streaming en **F-E** del roadmap | 🟡 diferido |
| Tolerancia a fallos (Inexistente 1) | Delta Lake (ACID, time-travel) + backup MySQL + F-F | ✅ |
| Optimización de costo (Inicial 2) | §11 autoterminación, jobs vs all-purpose | ✅ |
| Seguridad y gobernanza (Inicial 2) | Unity Catalog + usuarios read-only + PII tagging + Cloudflare Tunnel | ✅ |
| Integración/orquestación (Inexistente 1) | Databricks Workflows | ✅ |
| Mantenimiento/monitoreo (Inicial 2) | F6 monitoreo de jobs + métricas de calidad | ✅ |
| Calidad de datos (Inicial 2) | DLT expectations / reglas en silver | ✅ |
| Elasticidad (Inexistente 1) | Compute en nube por demanda | ✅ |
| Sostenibilidad tecnológica (Inicial 2) | §1 visión + §7 hoja de ruta + extensibilidad multi-fuente | ✅ |

**Herramientas propuestas en M2:**

| Recomendación M2 | En el plan |
|---|---|
| Kafka (streaming) | 🟡 F-E (no aplica hoy: MyISAM sin CDC + volumen bajo) |
| S3 / Azure Blob / GCS (data lake) | ✅ implícito en Delta Lake sobre cloud storage |
| Python (procesamiento) | ✅ §11 |
| Power BI / Tableau | ✅ §11 |

**Modelos propuestos en M2:**

| Recomendación M2 | En el plan |
|---|---|
| Gestión automatizada inventario + alertas | ✅ §5 + Fase 4 |
| Conservación de clientes (sentiment) | 🟡 F-B |

### A.2 Módulo 3 — Decisión crítica + modelo ML

| Aporte del M3 | Dónde en el plan |
|---|---|
| Problema: decisiones subjetivas, gestión manual de inventario | §1 + §3 ✅ |
| Modelo serie de tiempo por SKU | §5 O1 + Fase 4 ✅ |
| Modelo clasificación binaria de quiebre | §5 O2 + Fase 4 ✅ |
| Justificación ROI / obsolescencia / stock-outs | §9 KPIs de negocio ✅ |
| Ética: anonimización, consentimiento, transparencia, sesgo | §15 ✅ |

Este módulo está **uno a uno** con el plan.

### A.3 Módulo 4 — Madurez + VPC + BMC

| Aporte del M4 | Dónde en el plan |
|---|---|
| Diagnóstico Forrester/McKinsey/MIT → "Principiante" | §3 ✅ |
| Hoja de ruta paso 1 (Diagnóstico) | §3 ✅ |
| Paso 2 (Objetivos digitales) | §1 + §5 ✅ |
| Paso 3 (Iniciativas) | §5 + §7 fases ✅ |
| Paso 4 (Priorización F1→F4) | §7 Fases 1→6 ✅ |
| Paso 5 (KPIs) | §9 ✅ |
| VPC | §13 ✅ |
| BMC | §14 ✅ |

---

## Anexo B · Versionado del plan

| Versión | Cambio principal |
|---------|------------------|
| v1 | Pipeline ETL genérico con Databricks, sin marco analítico |
| v2 | Vinculado a módulos del curso, pero stack rebajado a DuckDB (subestimaba la visión de escalamiento) |
| v3 | Databricks Lakehouse + medallion estándar + evolución descriptiva→prospectiva + extensible |
| **v4 (actual)** | + Track T (API + PWA solo lectura) + 7 fases con entregables duales + Anexo A trazabilidad + §14 BMC completo |
