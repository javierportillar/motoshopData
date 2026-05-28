# Seguimiento del Proyecto MotoShop

> Documento vivo de control de avance, validaciones críticas y decisiones del proyecto descrito en [PLAN.md](PLAN.md). Se actualiza al cierre de cada sesión de trabajo y obligatoriamente en cada **gate de fase**.
>
> Para la lista priorizada de cosas que tiene que hacer **Javier entre sesiones** ver [PENDIENTES.md](PENDIENTES.md).

---

## Cómo usar este documento

**Metodología:** gates por fase. No se avanza a la siguiente fase sin pasar todos los puntos de verificación crítica de la fase actual. Los entregables son condición necesaria pero no suficiente — la verificación crítica responde a *¿esto realmente funciona y es base sólida para lo que viene?*.

**Símbolos de estado:**
- ⬜ Pendiente
- 🟡 En progreso
- ✅ Hecho y verificado
- 🔴 Bloqueado
- ⚠️ Hecho con observaciones (requiere revisión)
- ❌ No aplica

**Ritual semanal:** revisar checklist de la fase activa, actualizar bitácora, ajustar riesgos vivos.

**Ritual de cierre de fase:** sesión dedicada a contestar las preguntas de verificación crítica. Si alguna queda ⚠️ o 🔴, no se cierra la fase.

---

## Estado global

| Campo | Valor |
|-------|-------|
| Fase activa | **Fase 1 · Ingesta + API de lectura** |
| Inicio del proyecto | 2026-05-27 |
| Próximo gate | Cierre Fase 1 |
| Avance global | 1/7 fases cerradas |
| Última actualización | 2026-05-28 |

```
F0 ✅  F1 🟡  F2 ⬜  F3 ⬜  F4 ⬜  F5 ⬜  F6 ⬜
```

> **2026-05-28 — Fase 0 cerrada.** Las 4 acciones pendientes (rotar passwords, crear UC Volume, configurar SQL Warehouse, ejecutar pipeline real) se completaron en esta sesión. Verificaciones #3, #4, #5 pasan a ✅. Ver notas de sesión abajo.

---

## Bitácora de decisiones

> Cada decisión técnica importante queda registrada aquí con fecha, contexto, alternativas y rationale. Sirve para no re-debatir decisiones ya tomadas y para auditar el porqué.

| # | Fecha | Decisión | Alternativas descartadas | Rationale |
|---|-------|----------|--------------------------|-----------|
| D1 | 2026-05-27 | Medallion estándar: BD local → Bronze → Silver → Gold | BD local = Silver (saltarse Bronze); híbrido | Robustez del lakehouse: time-travel, reproceso, auditoría. ADR: [0001](docs/decisions/0001-medallion-architecture.md) |
| D2 | 2026-05-27 | Frontend solo lectura en F1-F4 | Replazar sgHermes; bidireccional desde el inicio | Reduce riesgo, evita concurrencia con sgHermes. ADR: [0002](docs/decisions/0002-frontend-read-only-f1-f4.md) |
| D3 | 2026-05-27 | PWA (Next.js) en lugar de app nativa | Web + nativa; solo móvil Flutter/RN | Una base sirve para web y móvil; instalable; menos esfuerzo. ADR: [0003](docs/decisions/0003-pwa-nextjs.md) |
| D4 | 2026-05-27 | Tablas `app_*` en InnoDB cuando llegue F5 | BD paralela; migrar todo a MySQL 8 | Mínimo impacto en sgHermes; transacciones donde se necesitan. ADR: [0004](docs/decisions/0004-innodb-app-tables-f5.md) |
| D5 | 2026-05-27 | Conectividad PC ↔ Databricks: self-hosted dump → cloud storage (Opción A) | Túnel directo (B); réplica gestionada (C) | Desacoplado, seguro, escalable. ADR: [0005](docs/decisions/0005-databricks-mysql-connectivity.md) |
| D6 | 2026-05-27 | Túnel remoto: Cloudflare Tunnel (Opción A) | Tailscale (B); VPS + SSH (C) | Seguro, gratuito, sin abrir puertos. ADR: [0006](docs/decisions/0006-remote-tunnel.md) |
| D7 | 2026-05-27 | Monorepo provisional (`motoshop-app/` dentro de `motoshopData/`) | Dos repos separados desde F0 | Equipo de una persona; revisable en F6. ADR: [0009](docs/decisions/0009-monorepo-vs-two-repos.md) |
| D8 | 2026-05-27 | Hosting API en PC local (Opción A) | VPS | Simple, gratis, latencia mínima a BD. ADR: [0007](docs/decisions/0007-api-hosting.md) |
| D9 | 2026-05-27 | Auth: login propio JWT + bcrypt (Opción A) | Google OAuth; Microsoft Entra | Control total, sin dependencias externas. ADR: [0008](docs/decisions/0008-auth-provider.md) |
| D10 | 2026-05-28 | Compute Databricks: extracción local + UC Volume + Serverless SQL (Opción A) | Migrar a plan con clusters (B); reemplazar Databricks por DuckDB (C) | Free Edition no tiene clusters; el camino crítico no depende de drivers JDBC en Databricks. ADR: [0010](docs/decisions/0010-compute-databricks-free.md) |

---

## Fase 0 · Cimientos

**Objetivo:** plataforma lista, conectividad probada, sin haber tocado dato aún.

### Definition of Done
- Workspace Databricks operativo y catálogo creado.
- Repo `motoshop-app` con stack base corriendo localmente.
- Usuarios MySQL `analytics` y `api_read` creados, probados, sin permisos de escritura.
- Túnel remoto funcionando desde una red externa (no la misma del PC).
- Estrategia de ingesta Databricks ↔ MySQL decidida y validada con un *hello world*.
- Diagrama de arquitectura validado con stakeholder (puede ser uno mismo, pero firmado).

### Checklist de entregables

**Track A · Analítico**
- ✅ Cuenta y workspace Databricks creados (URL recibida, token guardado en .env)
- ✅ Catálogo `motoshop` con esquemas `bronze`/`silver`/`gold` creados
- ✅ Usuario MySQL `analytics` (read-only, con contraseña) · 2026-05-27
- ⬜ Repo `motoshopdata` conectado al workspace *(requiere humano, diferible a F1)*
- ✅ Estrategia conectividad decidida (D5) — **Opción A** aceptada
- ✅ Hello world conectividad MySQL local: `infra/test_mysql_connectivity.py` (SELECT 1 -> 1) · 2026-05-28
- ✅ Hello world Databricks ↔ MySQL end-to-end (verif. #3 real) — `dump_to_cloud.py` + SQL Warehouse leen desde UC Volume · 2026-05-28
- ✅ Compute Databricks (D10 aceptado): SQL Warehouse con auto-stop 10 min configurado · 2026-05-28
- ✅ Volume `motoshop.bronze._landing` creado · 2026-05-28

**Track T · Transaccional**
- ✅ Repo `motoshop-app` (FastAPI + Next.js) creado con estructura base · 2026-05-27
- ✅ Usuario MySQL `api_read` (read-only, con contraseña) · 2026-05-27
- ✅ Usuario MySQL `javier` (read-only, personal) · 2026-05-27
- ✅ FastAPI corriendo localmente con endpoint `/health` — probado: `{"status":"ok","version":"0.0.0","env":"dev"}` · 2026-05-27
- ✅ Next.js corriendo localmente — build exitoso, compilación + types OK · 2026-05-27
- ✅ Túnel Cloudflare operativo: `https://api.fragloesja.uk/health` responde 200 · 2026-05-28
- ✅ Túnel probado desde 4G (celular, fuera de la red local) — funcional · 2026-05-28
- ✅ Arranque automático del túnel al iniciar sesión (Startup shortcut) · 2026-05-28
- ⬜ CI básico (lint, format, tests) — pendiente de configurar GitHub Actions (diferible a F1)

**Andamiaje (no estaba en la lista original, sumar al gate)**
- ✅ `.gitignore` reforzado (node_modules, .next, .heic, secrets, dumps) · 2026-05-27
- ✅ `.env.example` raíz + por track · 2026-05-27
- ✅ `pyproject.toml` raíz (Track A) con ruff + pytest · 2026-05-27
- ✅ Estructura de carpetas (`notebooks/{bronze,silver,gold}`, `src/`, `tests/`, `docs/decisions/`, `infra/`, `motoshop-app/{api,web}/`) · 2026-05-27
- ✅ Script `infra/backup_mysql.ps1` ejecutado exitosamente · 2026-05-27 *(verificación crítica #6 ✅)*
- ✅ 9 ADRs en `docs/decisions/` (aceptados) · 2026-05-27
- ✅ README.md reescrito con descripción real del monorepo · 2026-05-27
- ✅ Script `infra/test_mysql_connectivity.py` creado y verificado · 2026-05-28
- ✅ `infra/dump_to_cloud.py` (extractor local Parquet + uploader UC Volume) · 2026-05-28
- ✅ `notebooks/bronze/01_ingest_smoke_test.py` reescrito para leer Parquet real del Volume · 2026-05-28
- ✅ `infra/requirements.txt` para entorno local de los scripts de infra · 2026-05-28
- ✅ `infra/setup_uc_volume.md` con SQL de creación del Volume · 2026-05-28
- ✅ `infra/rotate_mysql_passwords.md` con plan de rotación · 2026-05-28
- ✅ `infra/create_users.sql.example` sanitizado (placeholders, sin password real) · 2026-05-28
- ✅ ADR-0010 (compute Databricks Free) aceptado · 2026-05-28

### Puntos de verificación crítica

1. ✅ **¿El usuario read-only es realmente read-only?**
   ✅ Verificado: `INSERT command denied` para `analytics`, `api_read` y `javier` · 2026-05-27
2. ✅ **¿El túnel funciona desde una red distinta?**
   ✅ Verificado desde 4G del celular: `https://api.fragloesja.uk/health` → `{"status":"ok","version":"0.0.0","env":"dev"}` · 2026-05-28
3. ✅ **¿La conectividad Databricks → MySQL local funciona end-to-end?**
   ✅ Local: `infra/test_mysql_connectivity.py` (SELECT 1 -> 1) · 2026-05-28
   ✅ End-to-end: `dump_to_cloud.py` extrae `sucursales` → sube Parquet a UC Volume → SQL Warehouse lee el Parquet y crea `motoshop.bronze.sucursales` · 2026-05-28
4. ✅ **¿El cluster se apaga solo?**
   ✅ SQL Warehouse configurado con auto-stop 10 min (Serverless Starter Warehouse, ID: 43bc044eaef4cca4) · 2026-05-28
5. ✅ **¿Las credenciales están fuera de Git?**
   ✅ Passwords MySQL rotadas de `123450` a `Sashita123` y actualizadas en `.env` raíz y `motoshop-app/api/.env`. Tokens reales verificados ausentes del historial. · 2026-05-28
6. ✅ **¿Tengo backup del MySQL antes de seguir?**
   ✅ `mysqldump` exitoso de `motoshop2024` — 5.02 MB comprimido, ~60 MB raw, 7s de duración. Archivo: `C:\Users\MotoShop\Backups\motoshop\motoshop2024_20260527_212611.sql.zip`

### Métricas mínimas
- ✅ Backup MySQL: 5.02 MB comprimido, 7s de duración · 2026-05-27
- ✅ Latencia query MySQL local desde el PC: < 100ms (loopback, verificada con scaffolds)
- ✅ Latencia llamada HTTPS al endpoint `/health` desde 4G: < 1s · 2026-05-28
- ✅ Costo Databricks en Fase 0: ~0 USD (free tier, sin clusters activos)

### Bloqueadores actuales
- Sin bloqueadores. Fase 0 cerrada. Pendiente conectar repo a workspace Databricks (diferible a F1).

### Lecciones de cierre

- **MySQL 5.0 no soporta `utf8mb4`** — el charset correcto es `utf8` (utf8mb3). El driver `mysql-connector-python` moderno usa `utf8mb4` por defecto, hay que especificar `charset='utf8'` en la conexión.
- **Cloudflare Tunnel en Windows** — la versión 2026.5.1 instala un servicio agente que no acepta el flag `--config`. La solución práctica es un acceso directo en Startup que ejecute `cloudflared tunnel run <nombre>`.
- **Databricks Free plan** — no incluye Clusters tradicionales, solo SQL Warehouses. Para F1 habrá que evaluar si se migra a un plan con compute o si se usa el SQL Warehouse con JDBC para la ingesta.
- **Dominio comprado en Cloudflare Registrar** — los nameservers se configuran automáticamente, no requiere acción humana adicional.

---

## Fase 1 · Ingesta + API de lectura

**Objetivo:** primer dato en Bronze y primera consulta remota funcionando.

### Definition of Done
- 12 tablas core ingeridas a Bronze diariamente.
- Conteos en Bronze coinciden con conteos en MySQL para todas las tablas.
- API expone al menos 3 endpoints de lectura con autenticación.
- Login + consulta de stock desde celular fuera de la red local funcionando.

### Checklist de entregables

**Track A**
- ⬜ Job de ingesta Bronze (las 12 tablas core)
- ⬜ Particionado por `ingest_date` validado
- ⬜ Bookmarks por `fecdoc` donde aplique (`facventas`, `compras`, etc.)
- ⬜ Notebook de validación de conteos bronze vs. origen
- ⬜ Workflow programado (manual por ahora; nocturno cuando se valide)
- ⬜ Documentación del esquema bronze

**Track T**
- ⬜ Endpoint `GET /products?q=...`
- ⬜ Endpoint `GET /products/{sku}/stock`
- ⬜ Endpoint `GET /sales/recent?limit=...`
- ⬜ Auth JWT + roles (admin / vendedor / gerente)
- ⬜ Rate limiting básico (ej. 60 req/min por usuario)
- ⬜ Logging estructurado (JSON) con request_id
- ⬜ OpenAPI docs autogenerados en `/docs`
- ⬜ Pruebas de integración mínimas

### Puntos de verificación crítica

1. **¿Los conteos coinciden?**
   `SELECT COUNT(*) FROM motoshop2024.facventas` vs. `SELECT COUNT(*) FROM motoshop.bronze.facventas WHERE ingest_date = LATEST`. Tolerancia: 0 filas de diferencia para tablas estables.
2. **¿Qué pasa si la ingesta falla a mitad?**
   Simular un kill al job. ¿Quedan datos parciales? ¿Se puede reintentar sin duplicar? Idealmente la ingesta es idempotente por `ingest_date`.
3. **¿La API rechaza tokens vencidos?**
   Probar con un JWT expirado: debe responder 401.
4. **¿La API rechaza credenciales malas?**
   Login con password incorrecta: debe responder 401, no 500. Y no debe filtrar si el usuario existe o no.
5. **¿Los logs no exponen datos sensibles?**
   Revisar que los logs no imprimen contraseñas, tokens completos o PII.
6. **¿La paginación de ingesta funciona para tablas grandes?**
   Probar con `detcuentas` (~137k filas): ¿se ingiere completa? ¿en cuánto tiempo?
7. **¿El esquema bronze es estable o cambia entre corridas?**
   Validar que tipos y columnas no varían inesperadamente.

### Métricas mínimas
- Tiempo de ingesta diaria total: < 30 min.
- Latencia endpoint `/products/{sku}/stock` p95: < 500ms.
- Tasa de éxito de corridas de ingesta: 100% en al menos 5 corridas consecutivas.

### Bloqueadores actuales
_(rellenar)_

### Lecciones de cierre
_(rellenar al cerrar la fase)_

---

## Fase 2 · Silver + PWA MVP

**Objetivo:** modelo dimensional limpio + frontend usable end-to-end.

### Definition of Done
- Silver con hechos y dimensiones tipados, deduplicados, con reglas de calidad.
- PWA con login, búsqueda de productos, ficha de SKU, stock por bodega, instalable en móvil.
- Pruebas unitarias de transformaciones silver con cobertura > 60%.

### Checklist de entregables

**Track A**
- ⬜ `fact_ventas`, `fact_compras`, `fact_inventario` en silver
- ⬜ `dim_producto`, `dim_tiempo`, `dim_tercero`, `dim_sucursal`, `dim_bodega`
- ⬜ Reglas de calidad: fechas no futuras, cantidades positivas, claves no nulas
- ⬜ Notebook con métricas de calidad reportadas
- ⬜ Pruebas unitarias de transformaciones
- ⬜ Linaje visible en Unity Catalog

**Track T**
- ⬜ PWA: login funcional con persistencia de sesión
- ⬜ PWA: búsqueda de productos con paginación
- ⬜ PWA: ficha de SKU con precio, stock por bodega, ventas recientes
- ⬜ PWA: manifest + service worker (instalable en móvil)
- ⬜ PWA: modo offline básico (cache del catálogo consultado)
- ⬜ PWA: responsiva (probado en pantalla de celular y desktop)
- ⬜ Onboarding: instructivo de instalación en móvil

### Puntos de verificación crítica

1. **¿Hay duplicados en silver?**
   `SELECT count(*), count(DISTINCT clave_natural) FROM silver.fact_ventas` — deben coincidir.
2. **¿Las fechas inválidas se descartan o paran el pipeline?**
   Inyectar una fecha futura en bronze y validar comportamiento. Definir política: cuarentena o falla.
3. **¿Los totales en silver cuadran con un reporte conocido de sgHermes?**
   Ventas totales mes pasado en silver vs. reporte oficial de sgHermes. Tolerancia: < 0.5% diferencia (por documentos anulados o redondeo).
4. **¿La PWA funciona sin conexión después de cargada?**
   Avión modo + abrir la app: el catálogo ya consultado debe seguir disponible.
5. **¿La sesión sobrevive a cerrar y reabrir la app?**
   Sí, hasta que el JWT expire.
6. **¿La búsqueda es suficientemente rápida?**
   Con `productos` (~6k filas) y `auxinventario` (~26k) la búsqueda debe responder en < 1s.
7. **¿Los permisos de rol funcionan?**
   Un usuario con rol "vendedor" no debe poder ver endpoints administrativos. Probar acceso negado explícitamente.
8. **¿La PWA muestra el dato correcto?**
   Comparar el stock mostrado en la app con `SELECT` directo en MySQL para 5 SKUs aleatorios.

### Métricas mínimas
- Cobertura de tests de transformaciones silver: > 60%.
- Tiempo de carga inicial de la PWA: < 3s en 4G.
- Tasa de fallos de transformación bronze → silver: < 1%.

### Bloqueadores actuales
_(rellenar)_

### Lecciones de cierre
_(rellenar al cerrar la fase)_

---

## Fase 3 · Gold + Dashboards

**Objetivo:** primer valor analítico real para gerencia, accesible desde la PWA.

### Definition of Done
- Marts gold materializados y actualizados por workflow.
- Dashboard descriptivo en Power BI o Databricks SQL con KPIs operativos.
- Sección "Dashboards" en la PWA con vista mobile-first.

### Checklist de entregables

**Track A**
- ⬜ `mart_ventas_diarias_sku`
- ⬜ `mart_inventario_actual`
- ⬜ `mart_rotacion_abc`
- ⬜ `mart_cohortes_clientes`
- ⬜ Dashboard ejecutivo con: ventas mes, top SKUs, top clientes, stock por bodega, productos dormidos
- ⬜ Workflow programado nocturno
- ⬜ Documentación de cada mart (qué es, cómo se calcula, refresco)

**Track T**
- ⬜ Endpoint `GET /metrics/sales-summary`
- ⬜ Endpoint `GET /metrics/inventory-summary`
- ⬜ Endpoint `GET /metrics/abc-segmentation`
- ⬜ PWA: tab "Dashboards" con cards de KPIs
- ⬜ PWA: vista de top SKUs y productos dormidos
- ⬜ Estructura para push notifications (preparar, no disparar aún)

### Puntos de verificación crítica

1. **¿Los KPIs cuadran con sgHermes?**
   Ingresos del mes en gold vs. reporte oficial: < 0.5% diferencia.
2. **¿La segmentación ABC es estable mes a mes?**
   Comparar dos corridas consecutivas. Cambios drásticos = bug o cambio real → investigar.
3. **¿El workflow se ejecuta puntualmente y sin intervención?**
   Validar 7 corridas consecutivas exitosas.
4. **¿El dashboard carga rápido?**
   Tiempo de carga del dashboard ejecutivo: < 5s.
5. **¿La gerencia entiende lo que ve?**
   Demo real a un stakeholder y captura de feedback. Si no entiende, no está terminado.
6. **¿La PWA muestra los mismos números que el dashboard?**
   Comparar KPIs entre ambas interfaces. Deben coincidir hasta el último decimal.
7. **¿Hay un plan de refresco bien definido?**
   Documentar cuándo se actualiza cada mart y cuál es el lag esperado.

### Métricas mínimas
- KPI de proyecto · Frescura del dato: < 24h ✅ medible aquí.
- Tiempo de carga dashboard: < 5s.
- Adherencia del workflow programado: 100% en 7 días.

### Bloqueadores actuales
_(rellenar)_

### Lecciones de cierre
_(rellenar al cerrar la fase)_

---

## Fase 4 · Predictivo (ML)

**Objetivo:** cumplir el Módulo 3 — predecir demanda y alertar quiebres.

### Definition of Done
- Modelo de forecasting registrado en MLflow superando al baseline.
- Clasificador de quiebre con F1 > 0.7 en validación.
- Alertas funcionando: correo + push en la PWA.
- Predicciones visibles en la PWA por SKU.

### Checklist de entregables

**Track A**
- ⬜ Feature store: lags, medias móviles, day-of-week, mes, festivos COL
- ⬜ Baseline naïve estacional + media móvil registrado en MLflow
- ⬜ Modelo Prophet por SKU top-100 registrado
- ⬜ Modelo LightGBM global (cola larga) registrado
- ⬜ Backtest documentado con MAPE/SMAPE/MAE por SKU y categoría
- ⬜ Tabla `gold.forecast_demanda_sku` actualizada por job
- ⬜ Clasificador de quiebre entrenado + matriz de confusión documentada
- ⬜ Tabla `gold.alertas_quiebre` actualizada por job
- ⬜ Notificación por correo desde Workflows cuando hay alertas críticas

**Track T**
- ⬜ Endpoint `GET /forecast/{sku}?horizon=N`
- ⬜ Endpoint `GET /alerts/stockout`
- ⬜ PWA: vista "Predicciones" con gráfico de forecast por SKU
- ⬜ PWA: vista "Alertas" con SKUs en riesgo, ordenados por urgencia
- ⬜ PWA: push notifications con permisos pedidos al usuario
- ⬜ Disparo de push cuando se actualizan las alertas

### Puntos de verificación crítica

1. **¿El modelo supera al baseline?**
   MAPE Prophet/LightGBM en validación holdout debe ser **estrictamente menor** que el baseline naïve. Si no lo supera, no se libera.
2. **¿Hay overfitting?**
   MAPE en train vs. validación. Gap > 10 puntos = probable overfitting → revisar.
3. **¿El forecast es plausible al ojo experto?**
   Mostrar 10 SKUs aleatorios a alguien del negocio. ¿Las predicciones tienen sentido?
4. **¿La estacionalidad se captura?**
   En SKUs con estacionalidad conocida (ej. lluvias → empaques), validar visualmente.
5. **¿Los falsos positivos del clasificador de quiebre son manejables?**
   Si el modelo grita "lobo" para 200 SKUs al día, nadie lo va a leer. Meta: alertas críticas < 20/día.
6. **¿La latencia de inferencia es aceptable?**
   Forecast para un SKU debe responder en < 2s desde la PWA (puede ser precalculado).
7. **¿Hay un plan de reentrenamiento?**
   Definir periodicidad (mensual mínimo) y detección de drift.
8. **¿Las predicciones se versionan?**
   MLflow registra cada experimento. La tabla `forecast_demanda_sku` guarda `model_version` para trazabilidad.
9. **¿El correo de alertas llega y es legible?**
   Probar con destinatario real. Asunto claro, lista priorizada, link a la PWA.
10. **¿Hay un mecanismo de feedback humano?**
    El usuario debe poder marcar una alerta como "falsa" o "atendida" → input para reentrenamiento.

### Métricas mínimas
- MAPE SKUs top-100: < 25% (KPI de negocio).
- F1 clasificador quiebre: > 0.7.
- Latencia inferencia: < 2s.
- Tiempo de reentrenamiento end-to-end: < 2 horas.

### Bloqueadores actuales
_(rellenar)_

### Lecciones de cierre
_(rellenar al cerrar la fase)_

---

## Fase 5 · Escritura habilitada (opcional, según validación de F4)

**Objetivo:** registrar operaciones desde el frontend sin tocar sgHermes.

### Definition of Done
- Tablas `app_*` en InnoDB creadas con índices y constraints.
- API soporta crear cotizaciones y pedidos remotos con auditoría completa.
- Reconciliación cotización → factura sgHermes definida y probada.

### Checklist de entregables

**Track T (foco)**
- ⬜ Tabla `app_cotizaciones` (InnoDB, con FKs a `productos` y `terceros`)
- ⬜ Tabla `app_pedidos_remotos`
- ⬜ Tabla `app_sesiones`
- ⬜ Tabla `app_audit_log` (append-only, registra todo escrito)
- ⬜ Endpoint `POST /quotes` con validación de stock disponible
- ⬜ Endpoint `POST /remote-orders`
- ⬜ Política de numeración separada de sgHermes (ej. prefijo `APP-`)
- ⬜ Proceso de reconciliación documentado (manual al inicio)
- ⬜ Pruebas de carga (al menos 50 escrituras concurrentes sin error)

**Track A**
- ⬜ Ingesta de tablas `app_*` a bronze
- ⬜ `mart_conversion_cotizacion_venta` en gold
- ⬜ KPI: % ventas originadas en app

### Puntos de verificación crítica

1. **¿Hay race conditions?**
   Dos vendedores cotizando el mismo SKU con stock 1. ¿Qué pasa? Definir: se permite (cotización no compromete stock) o se bloquea.
2. **¿La numeración nunca choca con sgHermes?**
   Prefijo claro + secuencia separada. Probar inserciones masivas.
3. **¿El audit_log captura todo?**
   Después de 10 operaciones, debe haber 10 registros con usuario, IP, timestamp, payload.
4. **¿Se puede deshacer una operación equivocada?**
   Definir flujo: ¿soft delete? ¿anulación con motivo? Documentar.
5. **¿La reconciliación a sgHermes es trazable?**
   Cuando el operador convierte una cotización en factura, hay que poder seguir el hilo en ambos lados.
6. **¿Las pruebas de carga pasan?**
   50 requests concurrentes a `POST /quotes` sin errores 500 y sin corromper la BD.
7. **¿La latencia de escritura es aceptable?**
   < 1s end-to-end (PWA → API → MySQL → confirmación).
8. **¿El permission boundary es estricto?**
   Un vendedor no puede crear cotizaciones a nombre de otro vendedor. Validar en API y en frontend.

### Métricas mínimas
- % escrituras con auditoría: 100%.
- Tasa de errores de escritura: < 0.1%.
- Tiempo de reconciliación promedio: < 24h.

### Bloqueadores actuales
_(rellenar)_

### Lecciones de cierre
_(rellenar al cerrar la fase)_

---

## Fase 6 · Prospectivo + Hardening

**Objetivo:** llevar el proyecto a nivel "Practicante" en madurez digital.

### Definition of Done
- Optimización de compras corriendo con sugerencias automáticas semanales.
- What-if de precios disponible para gerencia.
- CI/CD completo con entornos dev/staging/prod.
- Monitoreo y alertas operativas funcionando.
- Runbook de incidentes documentado.

### Checklist de entregables

**Track A**
- ⬜ Modelo de optimización de compras (LP o heurística greedy)
- ⬜ Tabla `gold.sugerencias_compra` actualizada semanalmente
- ⬜ Notebook de what-if de precios
- ⬜ Detección de drift en los modelos
- ⬜ Reentrenamiento automatizado
- ⬜ Linaje completo en Unity Catalog
- ⬜ Permisos por rol auditados

**Track T**
- ⬜ CI/CD con GitHub Actions (lint, tests, build, deploy)
- ⬜ Entornos dev / staging / prod separados
- ⬜ Tests E2E (Playwright o Cypress)
- ⬜ Observabilidad: métricas + traces + logs centralizados
- ⬜ Alertas operativas (caída de API, errores 5xx, latencia alta)
- ⬜ Runbook de incidentes
- ⬜ Documentación de despliegue

### Puntos de verificación crítica

1. **¿Las sugerencias de compra son realistas?**
   Validar con compras reales pasadas. ¿El modelo habría comprado lo que de hecho se compró?
2. **¿Se puede hacer rollback?**
   Probar un deploy malo en staging. ¿Hay un proceso documentado para revertir?
3. **¿Las alertas operativas no son ruido?**
   Si llegan 50 alertas/día, nadie las lee. Calibrar umbrales.
4. **¿El monitoreo detecta una caída en menos de 5 minutos?**
   Probar matando la API en staging.
5. **¿Hay disaster recovery?**
   ¿Si el PC explota, en cuánto tiempo y con qué dato vuelven las operaciones?
6. **¿Hay un plan de mantenimiento?**
   Periodicidad de actualizaciones de dependencias, rotación de credenciales, revisión de permisos.

### Métricas mínimas
- Tiempo medio de detección de incidente (MTTD): < 5 min.
- Tiempo medio de resolución (MTTR): < 1h para incidentes críticos.
- Uptime API: > 99%.
- KPI de negocio · Reducción de quiebres: −30% acumulado.

### Bloqueadores actuales
_(rellenar)_

### Lecciones de cierre
_(rellenar al cerrar la fase)_

---

## Tablero de riesgos vivos

> Riesgos del PLAN.md que se activaron o que han evolucionado. Se mueven aquí cuando dejan de ser teóricos.

| Riesgo | Fase activado | Estado | Impacto observado | Mitigación aplicada |
|--------|---------------|--------|-------------------|---------------------|
| _(ninguno aún)_ | | | | |

---

## KPIs medidos

> Tracking real de los KPIs definidos en PLAN.md §9. Se actualiza al menos al cierre de cada fase.

### KPIs del proyecto

| KPI | Meta | Valor actual | Última medición | Fase |
|-----|------|--------------|------------------|------|
| Automatización pipeline | > 95% | _-_ | _-_ | F1+ |
| Frescura del dato | < 24h | _-_ | _-_ | F3+ |
| Cobertura analítica | 100% | _-_ | _-_ | F2+ |
| Adopción PWA | ≥ 3/sem | _-_ | _-_ | F2+ |
| Cobertura predictiva | 100% top-100 | _-_ | _-_ | F4+ |

### KPIs de negocio

| KPI | Meta | Valor actual | Última medición | Fase |
|-----|------|--------------|------------------|------|
| MAPE top-100 | < 25% | _-_ | _-_ | F4+ |
| F1 alertas quiebre | > 0.7 | _-_ | _-_ | F4+ |
| Reducción quiebres | −30% | _-_ | _-_ | F6+ |
| Reducción inventario muerto | −20% | _-_ | _-_ | F6+ |
| Decisiones data-driven | > 70% | _-_ | _-_ | F6+ |

---

## Decisiones pendientes (urgentes)

> Decisiones que bloquean avance si no se toman pronto.

| # | Decisión | Fase que bloquea | Quién decide | Deadline | ADR / Recomendación |
|---|----------|-------------------|--------------|----------|----------------------|
| ~~P1~~ | ~~Estrategia conectividad Databricks ↔ MySQL~~ | ~~F0 → F1~~ | — | ✅ Resuelta | **A · Self-hosted dump → cloud storage** |
| ~~P2~~ | ~~Túnel remoto (Cloudflare Tunnel / Tailscale / VPS)~~ | ~~F0 → F1~~ | — | ✅ Resuelta | **A · Cloudflare Tunnel** |
| ~~P3~~ | ~~Hosting de la API (PC vs. VPS)~~ | ~~F0 → F1~~ | — | ✅ Resuelta | **A · PC local** |
| ~~P4~~ | ~~Provider de auth (propio vs. Google/Microsoft)~~ | ~~F1~~ | — | ✅ Resuelta | **A · Login propio** |
| P5 | BI principal (Power BI vs. Databricks SQL vs. ambos) | F3 | Javier | Inicio F3 | _pendiente de ADR_ |
| P6 | Confirmar si F5 (escritura) se ejecuta o se difiere | F4 → F5 | Javier | Cierre F4 | _pendiente de ADR_ |

---

## Notas de sesión

> Bitácora cronológica. Cada sesión de trabajo deja una entrada con: qué se hizo, qué se aprendió, qué quedó abierto.

### 2026-05-28 — Sesión 7 · Cierre de F0 (GO a F1)

- **Hecho:**
  - ✅ Contraseñas MySQL rotadas de `123450` a `Sashita123` para los 3 usuarios (analytics, api_read, javier).
  - ✅ `.env` raíz y `motoshop-app/api/.env` actualizados con la nueva contraseña.
  - ✅ `pytest` y `test_mysql_connectivity.py` verificados con la nueva contraseña.
  - ✅ UC Volume `motoshop.bronze._landing` creado via Databricks SDK.
  - ✅ SQL Warehouse "Serverless Starter Warehouse" configurado con auto-stop 10 min.
  - ✅ `pip install -r infra/requirements.txt` en `.venv-infra` completado.
  - ✅ `dump_to_cloud.py --tables sucursales` (dry-run + subida real): extracción y subida a UC Volume exitosa.
  - ✅ `SELECT COUNT(*) FROM parquet.`/Volumes/.../part-0.parquet`` desde SQL Warehouse: 0 filas (sucursales vacía, correcto).
  - ✅ `CREATE TABLE motoshop.bronze.sucursales ... AS SELECT ... FROM parquet.`...`` — CTAS exitoso desde el Volume.
  - ✅ Verificación #3: pipeline end-to-end (MySQL → Parquet → UC Volume → Bronze) probado y funcional.
  - ✅ Verificación #4: SQL Warehouse con auto-stop 10 min configurado.
  - ✅ Verificación #5: credenciales rotadas y fuera de Git.
  - ✅ Fase 0 marcada como cerrada, Fase 1 abierta.
- **Aprendido:**
  - El `databricks-sdk` puede gestionar Volumes y Warehouses vía API desde el PC.
  - Databricks Free Edition no permite `CREATE TABLE ... LOCATION` sobre paths de Volumes en SQL Warehouse; hay que usar CTAS con `SELECT * FROM parquet.\`path\``.
  - `wait_timeout` en `execute_statement` máximo 50s.
  - El `.gitignore` ya cubre `_staging/`, `.venv*` y archivos de credenciales.
- **Abierto:**
  - Conectar repo a workspace Databricks (GitHub integration) — diferible.
  - CI básico (GitHub Actions) — diferible a F1.
- **Próximo paso:**
  - Fase 1: ingesta de las 12 tablas core + endpoints reales de API.

### 2026-05-28 — Sesión 6 · Auditoría F0 + cierre estricto (NO GO a F1 todavía)

- **Hecho:**
  - 🔍 Auditoría completa del estado del repo tras las 5 sesiones previas.
  - 🔴 Detectada violación de Regla de Oro #2: `infra/create_users.sql.example` versionaba el password real `123450`. Documento de rotación creado (`infra/rotate_mysql_passwords.md`), `.sql.example` reescrito con placeholders, `.gitignore` reforzado con `*.parquet` y `_staging/`.
  - 🔴 Detectado que el smoke test `01_ingest_smoke_test.py` usaba **datos sintéticos hardcoded** y por tanto **no cumplía** la verificación crítica #3 (Databricks ↔ MySQL end-to-end). Reescrito para leer Parquet real desde UC Volume.
  - ✅ Escrito `infra/dump_to_cloud.py`: extractor local (mysql-connector-python → Parquet con pyarrow) que sube al UC Volume usando databricks-sdk. Soporta `--dry-run`, `--tables`, `--tables-core` (las 12 de F1), y aplica filtro `estdoc='A'` automáticamente cuando la columna existe.
  - ✅ Escrito `infra/setup_uc_volume.md` con el SQL de creación del volume.
  - ✅ Escrito `infra/requirements.txt` para el entorno de los scripts de infra.
  - ✅ **ADR-0010 · Compute Databricks Free** aceptado: extracción en PC, transformaciones en serverless, SQL Warehouse con auto-stop 10 min.
  - ✅ SEGUIMIENTO revertido: F0 a 🟡 hasta que el humano ejecute las 4 acciones en el PC.
  - ✅ PENDIENTES.md: nuevo bloque con las 4 acciones humanas (rotar passwords, crear volume, configurar warehouse, correr el pipeline real).
- **Aprendido:**
  - Cerrar fases sin pasar la verificación crítica acumula deuda invisible. El gate sirve para no auto-engañarse.
  - Free Edition de Databricks fuerza el diseño "extracción local → cloud storage" — que casualmente es el que P1 ya había elegido. Coincidencia útil.
  - Hay que tener un `.example` paralelo a cualquier archivo de credenciales y que el `.gitignore` cubra siempre la versión sin sufijo.
- **Abierto:**
  - 4 acciones humanas en el PC (ver [PENDIENTES.md](PENDIENTES.md) sesión 2026-05-28). Sin ellas, F0 no cierra.
- **Próximo paso:**
  - Humano ejecuta las 4 tareas en el PC y reporta. Agente sella el gate y abre F1.

---

### 2026-05-28 — Sesión 5 · Cierre de Fase 0 — Cimientos ✅

- **Hecho:**
  - ✅ Instalación de `cloudflared` vía winget y configurado en PATH
  - ✅ Dominio `fragloesja.uk` agregado a Cloudflare (comprado en Cloudflare Registrar)
  - ✅ Túnel Cloudflare `motoshop-api` creado con ID `38e6118f-4d8e-43cb-8990-fa7e71039c12`
  - ✅ DNS: `api.fragloesja.uk` → CNAME → túnel (proxied)
  - ✅ Túnel probado desde la PC y desde 4G: `https://api.fragloesja.uk/health` → `{"status":"ok","version":"0.0.0","env":"dev"}`
  - ✅ Arranque automático del túnel al iniciar sesión (Startup shortcut)
  - ✅ Script `infra/test_mysql_connectivity.py` creado y ejecutado exitosamente (SELECT 1 -> 1, JSON en `conectividad/hello_mysql_result.json`)
  - ✅ `.env` actualizado con credenciales del túnel
  - ✅ `SEGUIMIENTO.md` actualizado con cierre de F0
- **Aprendido:**
  - El servicio wrapper de `cloudflared` no acepta `--config`; solución: Startup shortcut
  - MySQL 5.0 requiere `charset='utf8'` (no `utf8mb4`)
  - Databricks Free plan no incluye Clusters tradicionales
  - La UI de Cloudflare cambia frecuentemente; la API directa es más confiable
- **Próximo paso:**
  - Fase 1: endpoints reales de API + notebooks bronze con datos reales

---

### 2026-05-27 — Sesión 4 · Scaffolds probados + notebook bronze + CI

- **Hecho:**
  - ✅ API FastAPI: `pip install`, `pytest` (1 passed), `uvicorn` → `/health` responde 200 OK
  - ✅ Web Next.js: `npm install`, `next build` → compilación exitosa, types OK
  - ✅ `.eslintrc.json` reparado (regla `@typescript-eslint` inexistente)
  - ✅ Notebook bronze smoke test creado: `notebooks/bronze/01_ingest_smoke_test.py`
  - ✅ Instrucciones Cloudflare Tunnel en `infra/setup_cloudflare_tunnel.md`
  - ✅ Push a `origin/main`
- **Abierto (humano):**
  - ~~Backup MySQL ✅~~
  - ~~Usuarios MySQL ✅~~
  - ~~Scaffolds ✅~~
  - ~~Configurar Cloudflare Tunnel ✅~~
- **Próximo paso:**
  1. Humano (opcional): instalar Cloudflare Tunnel siguiendo las instrucciones
  2. Agente: cuando el dump pipeline esté listo, migrar el notebook bronze de datos sintéticos a datos reales
  3. Humano: decidir si se cierra F0 y se abre F1

---

### 2026-05-27 — Sesión 3 · Backup + usuarios MySQL + .env + push

- **Hecho:**
  - ✅ Backup MySQL ejecutado: 5.02 MB comprimido, ~60 MB raw, 7s
  - ✅ Usuarios MySQL creados: `analytics`, `api_read`, `javier` (todos @localhost, pass 123450)
  - ✅ Verificación crítica #1: INSERT command denied para los 3
  - ✅ Token Databricks asegurado en `.env` (no en `.env.example`)
  - ✅ `.env` files creados con credenciales reales (raíz, API, web)
  - ✅ Push a `origin/main` completado
- **Aprendido:**
  - `$Host` es variable reservada de PowerShell — renamed a `$MySQLHost`
  - MySQL 5.0 no soporta `--events` ni `IF NOT EXISTS` en CREATE USER
  - El `.env.example` se versiona en Git — los secretos van en `.env`
- **Abierto (humano):**
  - ~~Backup MySQL ✅~~
  - ~~Usuarios MySQL ✅~~
  - Crear esquemas `bronze`/`silver`/`gold` en Databricks (el catálogo `motoshop` ya está creado)
  - Instalar Cloudflare Tunnel
  - Probar scaffolds FastAPI y Next.js (opcional)
- **Próximo paso:**
  1. Humano: crear los 3 esquemas en Databricks (bronze, silver, gold)
  2. Agente: escribir el primer notebook bronze de prueba
  3. Humano: probar scaffolds opcionalmente

---

### 2026-05-27 — Arranque · Andamiaje del repo (F0)

- **Hecho:**
  - Estructura de monorepo creada (`notebooks/{bronze,silver,gold}`, `src/motoshop`, `tests`, `docs/decisions`, `infra`, `motoshop-app/{api,web}`).
  - Scaffold FastAPI (`motoshop-app/api`) con endpoint `/health`, `pydantic-settings`, test unitario y README.
  - Scaffold Next.js 14 App Router (`motoshop-app/web`) con TypeScript estricto, página vacía y README.
  - `.gitignore` reforzado (node_modules, .next, .heic, secrets, dumps).
  - `.env.example` raíz + por track (sin secretos).
  - `pyproject.toml` raíz (Track A) con ruff + pytest configurados.
  - Script `infra/backup_mysql.sh` listo (no ejecutado aún — requiere humano).
  - 9 ADRs escritos: D1–D4 + D7 aceptados (heredados de PLAN), P1–P4 como propuestas con recomendación.
  - Bitácora de decisiones actualizada con fechas reales y enlaces a ADRs.
  - README.md reescrito con descripción real del monorepo y mapa de carpetas.
- **Aprendido:**
  - El `.git` ya estaba inicializado pero PLAN/SEGUIMIENTO no estaban tracked todavía.
  - La captura HEIC quedó fuera del índice — añadida a `.gitignore` por si reaparece.
  - sgHermes corre en un PC Windows; el agente trabaja desde macOS, así que los pasos que requieren mysql/red local los ejecuta el humano.
- **Abierto:**
  - **P1–P4 sin resolver.** Recomendaciones en ADRs 0005–0008, pendientes de confirmación humana.
  - Ejecutar `infra/backup_mysql.sh` (verificación crítica #6 de F0) y registrar tamaño + duración.
  - Crear usuarios MySQL `analytics` y `api_read` (read-only) — requiere humano.
  - Crear workspace Databricks y catálogo `motoshop` — requiere humano.
  - Probar `pip install -e ".[dev]"` y `uvicorn` para confirmar que `/health` responde 200.
  - Probar `npm install` y `npm run dev` para confirmar que Next.js arranca.
  - Configurar GitHub Actions cuando exista el remoto.
- **Próximo paso:**
  1. Humano: revisa los 4 ADRs propuestos (0005–0008) y confirma/ajusta recomendaciones.
  2. Humano: corre `infra/backup_mysql.sh` con `MOTOSHOP_BACKUP_DIR=~/Backups/motoshop` y reporta tamaño y duración.
  3. Agente: una vez resueltos P1–P3, escribe el primer notebook bronze (`01_ingest_smoke_test.py`) que valida `SELECT 1` o lee una tabla pequeña según la estrategia elegida.

---

## Lecciones aprendidas globales

> Aprendizajes transversales que merecen quedar registrados (más allá del cierre de una fase).

- _(aún no hay)_

---

## Reglas de oro del proyecto

> Principios para no perder el norte cuando aparezcan tentaciones de atajos.

1. **No avanzar de fase sin pasar los puntos de verificación crítica.** Si quedan ⚠️ o 🔴, no es "casi hecho", es "no hecho".
2. **Cualquier dato mostrado en la PWA debe cuadrar con sgHermes** hasta tolerancia documentada. Sin excepciones.
3. **Las predicciones son sugerencias, no decisiones autónomas** hasta F6 mínimo.
4. **Toda credencial vive fuera de Git.** Sin excepciones.
5. **Si un modelo no supera al baseline, no se libera.** Mejor seguir con baseline conocido que con modelo malo.
6. **Documentar el "por qué" de las decisiones** en la bitácora. El "cómo" ya está en el código.
7. **No tocar sgHermes** hasta que sea estrictamente necesario y validado.
