# Roadmap V2 · MotoShop como solución empresarial real

- **Fecha:** 2026-05-30 (Sesión 53)
- **Status:** Activo · CORE del proyecto
- **Audiencia:** revisor, devs futuros, stakeholder MotoShop, posibles inversores
- **Para qué sirve:** trazar de forma explícita todo lo que la V1 (académica) dejó como deuda consciente y que la V2 (producción real) tiene que cerrar.

---

## 1 · Contexto

**V1 (actual, académica):**
- Maestría UAO 2025-2 · entrega académica con foco en arquitectura medallion + ML + PWA
- Optimizada para **demostrar el concepto** + ser defendible ante jurado
- 7 fases (F0-F7) + hardening sprints + FIX1 por fase
- 100% gratuita (Databricks Free, Render free, Vercel free, Cloudflare gratuito)
- Single PC Windows como servidor on-premise

**V2 (siguiente, producción seria):**
- MotoShop deja de ser proyecto académico y pasa a ser solución empresarial usada 24/7
- SLAs reales · uptime garantizado · seguridad endurecida · escalabilidad
- Aceptación de costo recurrente acotado (~$50-200/mes según escala)
- Posible multi-tenant (si MotoShop quiere replicar a otras tiendas hermanas)
- Equipo distribuido podría operar la plataforma (no solo Javier)

**Regla fundamental:** **cada deuda consciente que aceptamos en V1 con argumento "para defensa académica X" tiene que tener su contrapartida en V2.** Este documento las mapea explícitamente.

---

## 2 · Deudas conscientes V1 → V2 (lista canónica)

### 🔒 Seguridad

| ID V1 | Deuda en V1 | Acción V2 |
|-------|-------------|-----------|
| R1 | Passwords MySQL (`123450`, `Sashita123`) en historial Git | Reescribir historia con `git filter-repo` + rotar todos los passwords MySQL + generar nuevos hashes bcrypt. Plan: 1 sprint dedicado pre-launch V2. |
| R2 | Password API `FG28` compartida para 3 usuarios + filtrada en historial | Eliminar password compartida. Migrar a usuarios individuales con bcrypt + opcional SSO (Microsoft Entra o Google Workspace) si MotoShop tiene cuenta corporativa. |
| R15 | `users.yaml` con hashes versionado en repo (vía `git add -f`) | Migrar usuarios a tabla MySQL `app_users` con campos: id, username, password_hash, role, is_active, created_at, last_login. CRUD desde UI admin. `users.yaml` queda solo como bootstrap inicial. |
| R-V2-1 | JWT_SECRET en `.env` (texto plano) | Migrar a gestor de secretos (AWS Secrets Manager / HashiCorp Vault / Doppler). |
| R-V2-2 | No hay 2FA | Implementar TOTP (Time-based One-Time Password) para roles `admin` y `gerente`. |
| R-V2-3 | No hay audit log de logins exitosos/fallidos | Tabla `app_login_audit` con: user_id, success, ip, user_agent, timestamp. Para detectar brute-force. |
| R-V2-4 | API expone CORS amplio (Vercel + cloud-api) | Lockdown CORS solo al dominio productivo + rate limiting más estricto + WAF (Cloudflare). |
| R-V2-5 | No hay key rotation policy | Cron mensual rotación JWT_SECRET + cron trimestral rotación DATABRICKS_TOKEN. |

### 🏗️ Infraestructura

| ID V1 | Deuda en V1 | Acción V2 |
|-------|-------------|-----------|
| R10 | PC Windows como SPOF (servidor on-premise + MySQL 5.0) | Migrar a infra cloud completa: MySQL 8.0 RDS/Aurora + API permanente (Fly.io paid / Railway / Vercel Functions). PC Windows queda solo como cliente de tienda. |
| R-V2-6 | Render Free se duerme tras 15 min (UptimeRobot mitiga) | Render Pro ($7/mes) o Fly.io Hobby ($5/mes) — sin sleep, sin UptimeRobot |
| R-V2-7 | MySQL 5.0 sin partitioning, sin JSON nativo, sin window functions modernas | Migrar a MySQL 8.0+ (Aurora Serverless v2 si AWS / Planetscale / Neon Postgres) |
| R-V2-8 | Cloudflare Tunnel depende de cloudflared corriendo en Windows | Reemplazar túnel cuando API y MySQL estén en cloud. Tunnel queda solo si sgHermes sigue on-premise. |
| R-V2-9 | Backup MySQL solo manual (mysqldump) | Backups automáticos cada 6 horas con retención 30 días (RDS auto-backup o pg_dump cron). Snapshot point-in-time. |
| ADR-0022 | 1 workflow unificado Databricks (gold falla = todo FAILED) | Separar en 3 jobs con SLAs distintos:<br>- **Job Bronze** (CRITICAL, retry 3×, alerta inmediata)<br>- **Job Silver** (HIGH, retry 2×, alerta business hours)<br>- **Job Gold** (MEDIUM, retry 1×, alerta lunes AM). Cada uno con schedule + alertas + reintentos independientes. |
| R-V2-10 | Databricks Free Edition (sin clusters, sin DLT, sin Unity Catalog avanzado) | Migrar a Databricks Premium o Enterprise SKU si el volumen lo justifica. Habilita streaming, Delta Live Tables, governance avanzado. |
| R-V2-11 | Workflow corre 19:00 COL — datos del día disponibles solo en la mañana siguiente | Migrar parte del pipeline a streaming (Spark Structured Streaming desde MySQL via Debezium CDC) → datos near-real-time. |

### 📊 Analytics y ML

| ID V1 | Deuda en V1 | Acción V2 |
|-------|-------------|-----------|
| R-V2-12 | Forecasting por SKU no funciona (dataset insuficiente, ADR-0017) | Implementar forecasting jerárquico: categoría → subcategoría → SKU con reconciliación bottom-up/top-down. Librería: `hts` (Python) o Nixtla `hierarchicalforecast`. |
| R-V2-13 | Solo baseline funciona bien en producción (Prophet/LightGBM no superan) | Re-evaluar con más datos (12+ meses de operación V2). Probar modelos más sofisticados: DeepAR, NHITS, TimesFM. Documentar con honestidad académica. |
| R-V2-14 | Classifier de quiebre F1 = 0.54 (sin leakage, pero rendimiento bajo) | Más features: lag categorías, evento calendario (lluvias, festivos), eventos de la tienda (descuentos pasados, campañas). Modelo: LightGBM con HPO + walk-forward CV. |
| R-V2-15 | Drift monitor con threshold fijo 30% | Threshold adaptativo basado en distribución histórica (p99). Alertas automatizadas vía Slack/Email/WhatsApp. |
| R-V2-16 | Snapshots históricos requieren 30 días para tener data útil | A los 30 días post-launch V2: validar que dashboards históricos (migración ABC, tendencia alertas) muestran data real. Si no, debugar pipeline de snapshots. |
| R-V2-17 | No hay backtesting visual de predicciones | Implementar dashboard `/backtesting` que muestre predicción vs realidad por SKU/categoría con métricas por semana. |
| R-V2-18 | No hay AutoML / model selection automático | Pipeline que cada mes re-evalúe los 5+ modelos y promueva el champion automáticamente (con quality gate). |

### 🎨 UX / Frontend

| ID V1 | Deuda en V1 | Acción V2 |
|-------|-------------|-----------|
| R-V2-19 | Logo PNG raster (175 KB) — no escalable, no dark variant | Rediseñar logo en Figma → SVG vectorial + variantes light/dark/mark only. Reemplazar `public/logo.png` → `public/logo.svg` |
| R-V2-20 | Tipografía Inter (Google Fonts) — no es branding propio | Definir tipografía corporativa (Roboto, IBM Plex, Manrope, o custom). Self-host para evitar dependency Google Fonts. |
| R-V2-21 | Sin internacionalización (todo es-CO) | Implementar i18n con `next-intl` o `next-i18next`. Soportar es-CO + es-419 + en-US si el negocio crece a otras regiones. |
| R-V2-22 | Mobile-first PWA pero sin push notifications reales | Implementar push notifications via Vercel WebPush o OneSignal para alertas críticas (quiebre inminente, drift detectado). |
| R-V2-23 | No hay analítica de uso de la PWA | Integrar Vercel Analytics (privacy-first) + Posthog/Mixpanel para entender qué dashboards realmente usan vendedores vs gerentes. |
| R-V2-24 | Sin dark mode | Implementar dark mode usando los tokens ya definidos en `colors.md` §"Superficies oscuras". |
| R-V2-25 | Tests Playwright son 71 pero NO hay tests visuales (visual regression) | Agregar Chromatic o Percy para visual regression testing en cada PR. |

### 🔄 Operación y procesos

| ID V1 | Deuda en V1 | Acción V2 |
|-------|-------------|-----------|
| R-V2-26 | Sin CI/CD pipeline real (commits van directo a main) | GitHub Actions: lint + typecheck + tests + smoke API + Lighthouse en cada PR. Branch protection en main. PRs obligatorios. |
| R-V2-27 | Deploy manual (Vercel auto desde main, pero migrations + restart API es manual via Dev W) | Pipeline CD que aplica migrations + restarts API + sync notebooks automáticamente cuando hay merge a main. |
| R-V2-28 | Sin observability stack (logs solo en stdout / Cloudflare) | Centralizar logs en Datadog / Grafana Cloud / BetterStack. Métricas + traces + alertas + dashboards de health. |
| R-V2-29 | Sin incident response runbook | Playbooks operativos para escenarios típicos: API caída, Databricks down, MySQL replica lag, key compromise. |
| R-V2-30 | Sin SLAs definidos | Definir SLAs explícitos: API uptime ≥ 99%, latencia p95 ≤ 500ms, freshness datos ≤ 1h, time-to-recovery ≤ 1h. |
| R-V2-31 | Sin disaster recovery plan | DR plan: backups offsite + runbook restore + RTO (Recovery Time Objective) + RPO (Recovery Point Objective) definidos. |
| R-V2-32 | Single tenant (MotoShop hardcoded) | Si MotoShop quiere replicar a otras tiendas hermanas: multi-tenant con tenant_id en todas las tablas + RLS (Row-Level Security) en MySQL. |
| R-V2-33 | Sin onboarding de nuevos usuarios fluido | Wizard onboarding vendedor (3 pasos: rol → tutorial → primera acción). Email de bienvenida. |
| R-V2-34 | Documentación dispersa entre `SEGUIMIENTO`, `PENDIENTES`, `docs/`, `_runs/` | Migrar docs operativas a wiki estructurada (Notion, GitBook, Outline). `docs/` queda como referencia técnica versionada. |

### 💰 Negocio y producto

| ID V1 | Deuda en V1 | Acción V2 |
|-------|-------------|-----------|
| R-V2-35 | Sin pricing model (V1 es gratis para MotoShop) | Definir si V2 es: (a) interno para MotoShop, (b) SaaS B2B para otras tiendas similares, (c) licencia self-hosted. |
| R-V2-36 | Sin integración con e-commerce / canales digitales | API pública para integrar con Shopify, WooCommerce, o sitio propio de MotoShop. |
| R-V2-37 | Sin reportes exportables a PDF/Excel | Botón "Exportar" en cada dashboard → PDF (con branding) y Excel (raw data). |
| R-V2-38 | Sin demo gerencia capturada (R8) — diferida V1 → si no cierra antes de defensa | Cierra en V1 si Javier graba antes de defensa. Si no, V2 obligatorio. |
| R-V2-39 | Sin demo 4G capturada (R6) — diferida V1 | Mismo. |
| R-V2-40 | E5 memoria académica diferente de pitch comercial | V2 incluye: deck inversores + ROI calculator + casos de uso por persona. |

---

## 3 · Prioridades V2 sugeridas (4 olas)

### Ola 1 · Hardening seguridad + infra cloud (2-4 semanas)

**Críticas para producción real:**
- R-V2-6 Render Pro o Fly.io paid (sin sleep)
- R-V2-7 Migrar MySQL 5.0 → 8.0 (Aurora Serverless v2 o Planetscale)
- R-V2-10 Databricks Premium SKU
- R1, R2, R15 Rotación passwords + reescribir historia + tabla `app_users`
- R-V2-1 Secrets manager
- R-V2-9 Backups automáticos
- R-V2-26 CI/CD GitHub Actions
- ADR-0022 → separar workflow en 3 jobs

### Ola 2 · Observability + reliability (2-3 semanas)

- R-V2-28 Stack observability (Datadog/Grafana)
- R-V2-29 Incident runbooks
- R-V2-30 SLAs definidos
- R-V2-31 DR plan
- R-V2-3 Audit login
- R-V2-2 2FA

### Ola 3 · Analytics avanzados (3-4 semanas)

- R-V2-12 Forecasting jerárquico (categoría → SKU)
- R-V2-14 Classifier mejorado con más features
- R-V2-15 Drift threshold adaptativo
- R-V2-17 Backtesting visual
- R-V2-18 AutoML pipeline

### Ola 4 · UX + escalabilidad de producto (3-4 semanas)

- R-V2-19, R-V2-20 Branding pro (logo SVG + tipografía propia)
- R-V2-21 i18n
- R-V2-22 Push notifications reales
- R-V2-23 Analytics de uso
- R-V2-24 Dark mode
- R-V2-32 Multi-tenant si aplica

**Total V2:** ~10-15 semanas de trabajo según equipo.

---

## 4 · Cómo encaja con V1 hoy

**V1 NO se borra ni se reescribe.** V1 es el cimiento defendible que demuestra el concepto. V2 es la evolución.

**Decisión clave:** todas las deudas conscientes que acepté en V1 con argumento "para defensa académica X" se documentan en este roadmap **antes** de escribir E5 memoria final. Eso convierte la honestidad académica en activo: "sabemos exactamente qué falta y cómo se cierra en V2".

**Para defensa académica V1:** el roadmap V2 es **parte del entregable** — demuestra madurez del proceso, no debilidad.

---

## 5 · Mantenimiento de este documento

- Cada nueva deuda consciente que aceptemos en lo que queda de V1 (entre hoy y defensa) se agrega acá con su correspondiente acción V2.
- En el cierre de V1: hacer una pasada final agregando lo que el revisor identifique en el audit final.
- Al iniciar V2: este documento se convierte en el `plan-v2.md` de trabajo activo.

---

## 6 · Mapeo a documentos existentes

| Documento V1 | Cómo se conecta con V2 |
|--------------|------------------------|
| `docs/decisions/0007-api-hosting.md` | API en PC local → V2: API cloud permanente |
| `docs/decisions/0010-compute-databricks-free.md` | Free Edition → V2: Premium SKU |
| `docs/decisions/0017-split-temporal-metricas-intermitentes.md` | Métricas honestas baseline → V2: forecasting jerárquico |
| `docs/decisions/0022-workflow-unificado.md` | 1 workflow → V2: separar en 3 con SLAs |
| `docs/contexto-proyecto.md` §10 | Riesgos vivos R1-R15 → V2: todos cierran |
| `docs/lecciones-aprendidas-f4.md` | Limitación dataset → V2: agregación jerárquica |
| `docs/lecciones-aprendidas-f6.md` | Workflow operativo → V2: pipelines independientes |
| `docs/entregable/E5-memoria-final.md` (a redactar) | Honestidad académica → V2: este roadmap como anexo |

---

## 7 · Aprobación humana

✅ V1 sigue como está documentada en F0-F7.
✅ V2 documentada acá como CORE del proyecto, no afterthought.
✅ Cada deuda V1 tiene su contrapartida V2 explícita.
✅ Para defensa V1, este roadmap es parte del entregable (no debilidad).

**Estado:** activo. Se actualiza con cada deuda nueva que aceptemos en lo que queda de V1.
