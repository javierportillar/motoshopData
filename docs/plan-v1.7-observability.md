# Plan V1.7 · Pipeline Observability nativo

> **Trigger:** Arranca solo cuando V1.5 Sprint 5 + V1.6 Sprints A-C estén cerrados.
>
> **Spine:** Página `/admin/pipeline` en la PWA que muestra cuándo corrió el último refresh, qué pasos tomó, cuánto tardó cada uno, qué falló si algo falló. Cero servicios externos. Todo nativo.

---

## 1. Por qué existe este plan

Hoy el gerente abre la PWA y ve sus KPIs, pero **no tiene forma de saber si esos números son de anoche o llevan 3 días sin actualizarse**. Si Windows se apaga el martes y nadie lo prende, los dashboards siguen mostrando data del lunes como si fuera fresca.

Lo único que existe hoy es `/api/health/data-freshness` que devuelve `lag_hours: 1.75`. Útil para ops, **invisible para el gerente**.

La PWA necesita una vista propia donde gerente y admin pueden:
- Ver si el refresh corrió hoy ✅ o falló ❌
- Si falló, cuál paso falló y por qué
- Cuánto tarda el pipeline en promedio (¿está degradándose?)
- Tendencia de éxito en los últimos 30 días

Eso es **observabilidad básica de pipeline**, no es opcional para una plataforma que vende decisiones basadas en datos.

ADR a generar: **ADR-0026 — Pipeline observability nativa**.

---

## 2. Objetivo y restricciones duras

| Dimensión | Objetivo | Restricción |
|-----------|----------|-------------|
| Cobertura | 100% de las corridas del pipeline (refresh + embeddings + uploads) quedan trazadas | No agregar carga de mantenimiento a Dev W |
| Latencia consulta | < 200ms para listar últimas 30 runs | MySQL InnoDB, no tocar `sgHermes` |
| Costo recurrente | $0/mes extra | Reutilizar MySQL existente + Render + Vercel |
| Privacidad | El log queda solo en MySQL local (Windows), no se sube a R2 ni cloud | sgHermes intocable, app_* OK |
| UX | Gerente entra a `/admin/pipeline` y entiende en 10 segundos si la data está OK | Sin glosarios técnicos, sin jerga de DevOps |
| Operación | Cero acción humana en el día a día — solo mirar si algo se rompió | Alertas opcionales en V1.7.1 |

---

## 3. Arquitectura objetivo

```
┌──────────────────────────────────────────────────────────────┐
│ WINDOWS · Pipeline batch                                      │
│                                                               │
│  refresh_v15.ps1 (Scheduled Task 02:00 COL)                   │
│  ├─ INSERT INTO app_pipeline_runs ... started_at, 'running'   │
│  ├─ paso 1 silver → INSERT INTO app_pipeline_steps           │
│  ├─ paso 2 gold   → INSERT/UPDATE                            │
│  ├─ paso 3 embeddings → INSERT/UPDATE                        │
│  ├─ paso 4 upload R2 → INSERT/UPDATE                         │
│  └─ UPDATE app_pipeline_runs SET finished_at, 'success'      │
│                                                               │
│  MySQL local (mismas tablas app_*)                            │
│  ├─ app_pipeline_runs   (cabecera por corrida)               │
│  └─ app_pipeline_steps  (detalle por paso)                   │
└────────────────┬─────────────────────────────────────────────┘
                 │ Cloudflare Tunnel
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ RENDER · FastAPI                                              │
│                                                               │
│  GET  /api/admin/pipeline/runs?limit=30&pipeline=X&status=Y   │
│  GET  /api/admin/pipeline/runs/{id}  (con steps)             │
│  GET  /api/admin/pipeline/summary  (KPIs últimos 30 días)    │
│                                                               │
│  Auth: require_role("admin", "gerente")                       │
└────────────────┬─────────────────────────────────────────────┘
                 │ HTTPS + JWT
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ VERCEL · PWA                                                  │
│                                                               │
│  /admin/pipeline                                              │
│  ├─ KPIs: success rate 30d, last run status, avg duration    │
│  ├─ Gráfico barras: runs por día last 30 (color por status)  │
│  ├─ Tabla últimas 30 runs (filtros: pipeline, status)        │
│  └─ Detail modal: steps de cada run + log excerpt            │
└──────────────────────────────────────────────────────────────┘
```

### Decisiones arquitectónicas

| Decisión | Por qué | Alternativa rechazada |
|----------|---------|------------------------|
| MySQL `app_pipeline_*` en Windows | Misma DB que `app_alert_actions`, `app_audit_log`, `app_purchase_plans` — patrón ya probado | Postgres dedicado (agrega infra) |
| Solo lectura desde PWA | Re-ejecutar el pipeline desde la PWA requiere wiring de auth + jobs lock + estado distribuido. **No se justifica** ahora. Si hace falta, se agrega en V1.7.1 | Botón "Re-ejecutar" en PWA |
| Logs en `log_excerpt TEXT` (últimas ~1000 líneas) | No queremos `LONGTEXT` con MBs de log → MySQL se infla | Log completo en MySQL |
| Sin alertas email/push en V1.7 | El gerente revisa la página diariamente; las alertas distraen si no hay falla | Alertas Telegram (lo dejamos para V1.7.1 si hace falta) |
| Schema en MySQL InnoDB, no en DuckDB | DuckDB se refresca → perdés historia. MySQL persiste para siempre | `app_pipeline_runs` en DuckDB |

---

## 4. Stack tecnológico

### Componentes nuevos

| Componente | Tecnología | Por qué |
|------------|-----------|---------|
| Tablas `app_pipeline_runs` + `app_pipeline_steps` | MySQL InnoDB | Mismo patrón que las otras tablas `app_*` (ADR-0004) |
| Endpoints `/api/admin/pipeline/*` | FastAPI + Pydantic | Reuso de la arquitectura existente |
| Página `/admin/pipeline` | Next.js + SWR + Recharts | Reuso de los componentes de dashboard existentes |
| Logging PowerShell → MySQL | `mysql.exe` CLI o módulo PowerShell SimplySQL | Compatible con Windows Server, no agrega dependencia Python |
| Logging Python (Mac) → MySQL | `mysql-connector-python` (ya está) | Ya está en el entorno del pipeline |

### Lo que NO se agrega

- ❌ Servicio externo de monitoring (Healthchecks.io, Datadog, etc.) — todo nativo
- ❌ Tabla de logs completa (`LONGTEXT` con MB de output) — solo excerpt
- ❌ Botón "Re-ejecutar pipeline" desde la PWA — fuera de scope V1.7
- ❌ Webhooks/integraciones con Slack/Telegram — V1.7.1 si hace falta

---

## 5. Roadmap de Sprints

V1.7 es chico — un solo sprint con 3 sub-bloques.

### Sprint Único · Pipeline Observability (~10h)

#### Sub-bloque A · Backend + schema (3-4h)

| Tarea | DoD |
|-------|-----|
| Migration `infra/migrations/app_pipeline_v17.sql` con las 2 tablas | Schema aplicado en MySQL Windows |
| Módulo `motoshop-app/api/src/motoshop_api/pipeline_runs/` con repo, schemas, router | `GET /api/admin/pipeline/runs` devuelve últimos N runs |
| Endpoint `GET /api/admin/pipeline/runs/{id}` devuelve cabecera + steps | Test local + en prod con runs ya inyectados a mano |
| Endpoint `GET /api/admin/pipeline/summary` | Devuelve `{success_rate_30d, avg_duration_seconds, total_runs, last_run_status, last_run_finished_at}` |
| Auth `require_role("admin", "gerente")` en los 3 endpoints | Vendedor recibe 403 |

#### Sub-bloque B · Pipeline scripts logean a MySQL (~2-3h)

| Tarea | DoD |
|-------|-----|
| `infra/refresh_v15.ps1` registra run + steps en MySQL antes/después de cada bloque | Tabla recibe filas con steps `bronze_load`, `silver_build`, `gold_build`, `embeddings_refresh`, `r2_upload`, `render_refresh` |
| `pipeline/embeddings_skus.py` registra su propio pipeline_name `embeddings_skus` | Cuando lo corrés en Mac, queda traza en MySQL via tunnel |
| Excerpt de log: últimos ~50 líneas por step almacenado | Si falla, el `error_message` + `log_excerpt` permiten diagnosticar sin SSH a Windows |
| Smoke test manual: ejecutás el pipeline una vez, ves la fila completa en `app_pipeline_runs` con todos sus steps | Manual end-to-end |

#### Sub-bloque C · Frontend PWA (~4-5h)

| Tarea | DoD |
|-------|-----|
| Ruta `/admin/pipeline` con guard de rol (admin, gerente) | Vendedor no la ve en navegación |
| Componente `<PipelineHealthCard>`: muestra last_run status + lag_hours | Gerente entiende el estado del pipeline en 5 segundos |
| Componente `<RunsTable>`: últimas 30 runs con filtros (pipeline, status) | Mismo pattern que `/dashboards/dormidos` |
| Componente `<RunDetail>` modal: lista de steps con duración + log_excerpt expandible | Click en una fila abre detalle |
| Gráfico barras (Recharts): success rate por día (últimos 30) | Color verde/rojo |
| Link en navegación (rol admin/gerente solamente) | Badge si hay run failed en últimas 24h |

**Criterio salida sprint:**
- Gerente entra a `/admin/pipeline`, ve el estado del último refresh
- Si hubo falla, identifica el step y lee el error sin abrir Windows ni Render dashboard
- Tabla muestra 30 runs con success rate, duración promedio
- Performance página < 1.5s First Contentful Paint
- Sin regresiones en los otros dashboards

---

## 6. Risk register

| ID | Riesgo | Mitigación | Severidad |
|----|--------|------------|-----------|
| RO1 | Volumen de logs llena el MySQL (si run falla en loop) | `log_excerpt` cap a últimas 1000 líneas / 64KB. Cleanup: cron mensual borra runs > 90 días | Baja |
| RO2 | Pipeline crashea antes de poder marcar `finished_at` → quedan rows `status='running'` huérfanas | Endpoint summary trata runs con `status='running'` y `started_at > 1h` como `failed`. Manualmente marca con error "process killed mid-run" | Media |
| RO3 | Performance página degrada con 1000+ runs | Tabla muestra solo últimas 30. Endpoint summary agrupa por día. Index en `(pipeline_name, started_at)` | Baja |
| RO4 | Dev W resiste tocar el script PowerShell otra vez | Sub-bloque B se le entrega con código listo + instrucciones paso a paso. Si tarda más de 2h → escala | Media |
| RO5 | Mac no puede escribir a MySQL Windows | Cloudflare Tunnel ya expone MySQL via `api.fragloesja.uk` para el API. Reutilizar usuario `app_writer` (ADR-0019) | Baja |

---

## 7. Equipo y handoffs

| Dev | Sprint | Tiempo |
|-----|--------|--------|
| **Dev D** | Sub-bloque A (backend) + B (Windows script) | 5-6h |
| **Dev F** | Sub-bloque C (frontend) | 4-5h |
| **Vos** | Smoke test end-to-end + decidir si activar V1.7.1 alertas | 30 min |

**Trigger:** Cuando V1.6 Sprint A (briefing diario) esté cerrado.

---

## 8. Definition of Done V1.7

- [ ] Tablas `app_pipeline_runs` + `app_pipeline_steps` en MySQL Windows
- [ ] 3 endpoints `/api/admin/pipeline/*` con auth + tests
- [ ] `refresh_v15.ps1` logea cada step en MySQL
- [ ] `pipeline/embeddings_skus.py` logea su run en MySQL
- [ ] Página `/admin/pipeline` en PWA con KPIs, tabla, gráfico, detalle
- [ ] Smoke test: ejecutás el pipeline, vas a la página, ves el run completo
- [ ] Falla intencional: matás un step a propósito, la página muestra el error con excerpt
- [ ] ADR-0026 Accepted
- [ ] SEGUIMIENTO.md bloque V1.7 cierre

---

## 9. V1.7.1 (opcional, futuro)

Si después del despliegue el gerente pide alertas activas (cuando algo falla, llegarme un mensaje), V1.7.1 agrega:

- Webhook Telegram en `refresh_v15.ps1` cuando `status='failed'`
- Email opcional vía Resend free tier
- Toggle "Activar alertas" en `/admin/pipeline` settings

~2h de trabajo. No se hace hasta que se valide que la página sola no alcanza.

---

## 10. V1.7.2 (más futuro)

Si llega a haber demanda real de re-ejecutar el pipeline desde la PWA (gerente ve "failed" a las 9am y quiere re-correrlo sin esperar a las 2am del día siguiente):

- Endpoint `POST /api/admin/pipeline/runs` que dispara un webhook a Windows
- Windows tiene un endpoint local que ejecuta el script
- UI con botón "Re-ejecutar" + confirmación

~6h de trabajo. **No se hace** hasta que el gerente lo pida explícitamente.

---

## 11. Cuándo y cómo arranca

- **Trigger:** Cuando V1.6 Sprint A (briefing diario) esté funcionando 7 días seguidos sin falla
- **Modo ejecución:** Sub-bloques A + B en paralelo (Dev D); C arranca cuando A está listo (Dev F necesita endpoints)
- **Wall clock estimado:** 1.5-2 días con 2 devs en paralelo

---

*Documento creado: 2026-06-07*
*Status: Aprobado por PO — kickoff diferido post-V1.6*
*Doc canónico V1.5: `docs/plan-v1.5-duckdb.md`*
*Doc canónico V1.6: `docs/plan-v1.6-llm.md`*
