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

> **Actualización 2026-06-08 — cambio post-auditoría:** la lectura cloud de
> `pipeline_runs` ya no debe depender de MySQL Windows desde Render. Dev W migró
> el contrato a `pipeline_runs.duckdb` publicado en R2, siguiendo la política
> DuckDB-first de ADR-0023. MySQL/Windows puede seguir siendo origen operativo
> para construir la traza, pero la PWA consume exclusivamente FastAPI en Render:
> `/api/admin/pipeline/*`.

```
┌──────────────────────────────────────────────────────────────┐
│ WINDOWS · Pipeline batch                                      │
│                                                               │
│  refresh_v15.ps1 (Scheduled Task 02:00 COL)                   │
│  ├─ registra app_pipeline_runs/app_pipeline_steps             │
│  ├─ ejecuta bronze → silver → gold                            │
│  ├─ sube motoshop_gold.duckdb a R2                            │
│  ├─ marca steps/run como success|failed                       │
│  └─ sube pipeline_runs.duckdb FINAL a R2                      │
│                                                               │
│  out/pipeline_runs.duckdb                                     │
│  ├─ app_pipeline_runs   (cabecera por corrida)                │
│  └─ app_pipeline_steps  (detalle por paso)                    │
└────────────────┬─────────────────────────────────────────────┘
                 │ Cloudflare R2
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ RENDER · FastAPI                                              │
│                                                               │
│  Lee pipeline_runs.duckdb desde R2                            │
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
| `pipeline_runs.duckdb` publicado en R2 para lectura cloud | Render no puede depender de MySQL Windows; mantiene $0/mes y alinea V1.7 con ADR-0023 DuckDB-first | Render leyendo MySQL Windows vía túnel |
| Solo lectura desde PWA | Re-ejecutar el pipeline desde la PWA requiere wiring de auth + jobs lock + estado distribuido. **No se justifica** ahora. Si hace falta, se agrega en V1.7.1 | Botón "Re-ejecutar" en PWA |
| Logs en `log_excerpt TEXT` (últimas ~50 líneas / cap 8KB) | Suficiente para diagnosticar sin inflar el DuckDB de observabilidad | Log completo en la PWA |
| Sin alertas email/push en V1.7 | El gerente revisa la página diariamente; las alertas distraen si no hay falla | Alertas Telegram (lo dejamos para V1.7.1 si hace falta) |
| Publicar el DuckDB de observabilidad solo después de cerrar el run | Si se sube antes, producción muestra `running` eternamente aunque el pipeline haya terminado | Subir `pipeline_runs.duckdb` durante el step `r2_upload` |

---

## 4. Stack tecnológico

### Componentes nuevos

| Componente | Tecnología | Por qué |
|------------|-----------|---------|
| Tablas `app_pipeline_runs` + `app_pipeline_steps` | DuckDB (`pipeline_runs.duckdb`) | Misma estrategia cloud que V1.5: archivo local + R2 + Render |
| Endpoints `/api/admin/pipeline/*` | FastAPI + Pydantic | Reuso de la arquitectura existente |
| Página `/admin/pipeline` | Next.js + SWR + Recharts | Reuso de los componentes de dashboard existentes |
| Logging PowerShell → DuckDB | `scripts/pipeline_runs_db.py` | Evita dependencia cloud→Windows |
| Publicación a R2 | `scripts/upload_duckdb_to_r2.py` + refresh API | Mantiene Render actualizado sin restart manual |

### Lo que NO se agrega

- ❌ Servicio externo de monitoring (Healthchecks.io, Datadog, etc.) — todo nativo
- ❌ Tabla de logs completa (`LONGTEXT` con MB de output) — solo excerpt
- ❌ Botón "Re-ejecutar pipeline" desde la PWA — fuera de scope V1.7
- ❌ Webhooks/integraciones con Slack/Telegram — V1.7.1 si hace falta
- ❌ Lectura directa desde MySQL Windows en Render — rompe la operación $0 y acopla producción al PC

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

**Estado para Dev F (2026-06-08):** puede arrancar integración contra
`/api/admin/pipeline/*`. Backend aún no está cerrado formalmente porque hay un
bug conocido: el último run puede aparecer como `running` si Dev W publica
`pipeline_runs.duckdb` antes de cerrar el run. El Front debe representar ese
estado honestamente, pero no intentar corregirlo en UI.

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

### Handoff listo para Dev F · Sub-bloque C Frontend

**Rol:** Dev Frontend V1.7. Implementás la página de observabilidad del pipeline
en la PWA. No tocás backend, Windows, scripts PowerShell ni R2.

**Contrato API confirmado en producción:**

```text
GET /api/admin/pipeline/runs?limit=30&pipeline=refresh_v15&status=success
GET /api/admin/pipeline/runs/{id}
GET /api/admin/pipeline/summary
```

Todos requieren Bearer JWT y roles `admin` o `gerente`. `vendedor` debe quedar
sin acceso visual y, si intenta entrar por URL directa, debe ver una pantalla
honesta de acceso denegado o redirección segura.

**Shape observado en producción:**

```ts
type PipelineRun = {
  id: number;
  pipeline_name: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "failed";
  duration_seconds: number | null;
  rows_processed: number | null;
  triggered_by: string;
  error_message: string | null;
};

type PipelineStep = PipelineRun & {
  run_id: number;
  step_order: number;
  step_name: string;
  log_excerpt: string | null;
};

type PipelineSummary = {
  success_rate_30d_pct: number;
  avg_duration_seconds: number;
  total_runs_30d: number;
  last_run_status: "running" | "success" | "failed" | null;
  last_run_finished_at: string | null;
};
```

**Implementación esperada:**

- Crear ruta `motoshop-app/web/app/(authenticated)/admin/pipeline/page.tsx`.
- Agregar hooks tipados en `motoshop-app/web/lib/api/hooks.ts` usando SWR.
- Agregar navegación solo para `admin` y `gerente`.
- Reusar componentes existentes de UI: `Stat`, `Badge`, `Table`, `ErrorState`,
  wrappers de chart si aplican.
- Renderizar:
  - cards: último estado, success rate 30d, duración promedio, total runs 30d;
  - tabla de últimas 30 corridas con filtros por `pipeline` y `status`;
  - detalle expandible/modal con steps, duración, estado, error y `log_excerpt`;
  - estado `running` como “En ejecución” si empezó hace poco y como “Revisar”
    si lleva más de 60 minutos sin `finished_at`.

**Reglas de UX:**

- No usar jerga DevOps como “artifact”, “bootstrap”, “R2 object”. El gerente
  debe entender: “Actualización de datos”, “Última corrida”, “Paso fallido”.
- Si no hay runs: mostrar empty state “Todavía no hay corridas registradas”.
- Si API responde 401/403: no mostrar datos parciales; mostrar acceso denegado.
- Si API responde 5xx: mostrar error claro y botón de reintentar.
- No agregar botón “Re-ejecutar pipeline”.
- No ocultar `running`; mostrarlo con contexto.

**Bug backend conocido — NO arreglar en Front:**

Producción puede mostrar el último run como `running` aunque el pipeline haya
terminado, porque Dev W debe republicar `pipeline_runs.duckdb` después de
`Complete-PipelineRun`. El Front solo debe mostrar ese estado como “Revisar si
lleva más de 60 min”.

**Validación mínima antes de entregar:**

- `npm run typecheck`
- `npm run build`
- Test/smoke Playwright para:
  - admin ve `/admin/pipeline`;
  - gerente ve `/admin/pipeline`;
  - vendedor no ve link y no accede a la página;
  - tabla renderiza runs mockeados;
  - modal/detalle muestra steps y `log_excerpt`.

**No tocar:**

- `infra/`
- `pipeline/`
- `scripts/`
- `motoshop-app/api/`
- configuración de Vercel/Render

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
