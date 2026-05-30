# Plan F6 · Hardening + Entrega académica — el último sprint del proyecto

- **Fecha apertura:** 2026-05-30 (Sesión 45)
- **Estado:** 🟡 ABIERTA
- **Modo:** paralelo · **2 devs (Dev A · Hardening operativo, Dev B · Analítica robusta) + Revisor (yo · E5 memoria + audit final) + Humano (demos)**.
- **Duración estimada:** Dev A 4-5 h · Dev B 3-4 h · Revisor 2-3 h · Humano 2 h (demos). Wall-clock ~6 h.
- **Dependencias previas:** F5 ✅ cerrada. Deudas activas: R1, R2, R4, R5, R6, R7, R8, R15, R16.
- **Es el último sprint del proyecto académico.** Después de F6 viene la defensa de Maestría.

---

## 1 · Visión y por qué F6 es especial

F0-F5 entregaron las **funcionalidades técnicas**. F6 hace **dos cosas en paralelo**:

1. **Hardening operativo**: cerrar todas las deudas vivas con triggers que ya se cumplieron (R4, R6, R7, R8, R16) + producto predictivo robusto (forecasting por categoría que F4-FIX1 recomendó como dirección correcta).
2. **Entrega académica**: capturar las demos pendientes, escribir la memoria final E5, dejar el repositorio en estado defendible ante el jurado de la Maestría UAO 2025-2.

Las deudas R1, R2, R15 NO se cierran en F6 (decisión humana explícita: dejar `Sashita123` y `FG28` como están, no rotar). Se documentan en E5 como **deudas conscientes con análisis de impacto + mitigaciones activas**.

R5 (pipeline resiliente) está mitigada de F1.9 — se ratifica como cerrada con la evidencia de 30 días de operación continua.

---

## 2 · Deudas vivas que F6 debe cerrar (o ratificar como mitigadas)

| Deuda | Estado entrada F6 | Acción F6 | Cierra F6? |
|-------|-------------------|-----------|-----------|
| **R1** Passwords MySQL en historial Git | 🟡 Aceptada (decisión humana) | Documentar en E5 §3 (Seguridad) con mitigaciones activas | NO — sigue aceptada |
| **R2** `FG28` en historial | 🟡 Aceptada (decisión humana) | Documentar en E5 §3 | NO — sigue aceptada |
| **R4** Workflow Databricks postergado (corre Task Scheduler) | 🟡 Aceptado | **F6-A2:** migrar a Databricks Workflow gestionado | ✅ |
| **R5** Pipeline pre-internet-estable | 🟡 Mitigada con F1.9 | Verificar que `system.workflows.runs` muestra ≥30 corridas exitosas; ratificar | ✅ Ratificada |
| **R6** Demo 4G no capturada | 🟡 Diferida a F6 | **F6-C1:** humano graba 5 min en celular real | ✅ |
| **R7** V3 workflow 7 corridas | 🟡 Diferida a F6 | **F6-A3:** revisor verifica `system.workflows.runs` con tasa éxito > 95% | ✅ |
| **R8** Demo a gerencia | 🟡 Diferida a F6 | **F6-C2:** humano agenda 30 min, captura feedback | ✅ |
| **R15** `users.yaml` con FG28 force-added | 🟡 Diferida a F6 | Documentar en E5 §3 como aceptada (decisión humana 2026-05-30) | NO — sigue aceptada |
| **R16** ENV guardrail | 🔴 Abierto | **F6-A1:** startup check bloquea `ENV=test` en producción | ✅ |

Resultado esperado al cierre F6: **5 deudas cerradas (R4, R5, R6, R7, R8, R16)** + **3 deudas conscientes documentadas (R1, R2, R15)**.

---

## 3 · Scope total F6

### Lo que SÍ entrega F6

**Hardening operativo (F6-A — Dev A):**
- ENV guardrail en startup (cierra R16)
- Workflow Databricks migrado a managed (cierra R4)
- V3 workflow 7 corridas exitosas evidenciada (cierra R7)
- Audit log monthly partition (deuda técnica F5-R-F5-6)
- Drift monitoring básico: track baseline WAPE deviation semanal
- Walk-forward validation para classifier (deuda técnica F4)

**Analítica robusta (F6-B — Dev B / Dev A second pass):**
- Forecasting por **categoría/familia** en lugar de por SKU individual (recomendación F4-FIX1)
- Re-evaluation con agregación: hipótesis = baseline categoría > baseline SKU
- ADR-0020 (forecasting agregado + futura jerarquía)
- Tests sqlparse + chispa

**Entrega académica (F6-C — Humano + Revisor):**
- Demo 4G grabada en celular (cierra R6)
- Demo gerencia con feedback capturado (cierra R8)
- **E5 memoria final completa** (~30-50 páginas)
- Presentation slides para defensa (opcional, recomendado)
- README público actualizado con badges + screenshots finales
- Cleanup final del repo (.gitignore review, archive completo)

### Lo que NO entra en F6

- Rotar `Sashita123` (R1), `FG28` (R2), `users.yaml` (R15) — decisión humana explícita 2026-05-30.
- Streaming, multi-tenant, marketplace → F7+ post-curso.
- Cloud migration (DB cloud) → post-curso.
- Walk-forward de forecasting (ya cubierto con categoría, no por SKU) → F7+.
- Refactoring grande del código → post-curso.

---

## 4 · Decisiones técnicas (DT-F6)

### DT-F6-1 · ENV guardrail en startup (cierra R16)

`motoshop-app/api/src/motoshop_api/main.py` `lifespan` valida:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.env == "test":
        is_localhost = settings.host in ("127.0.0.1", "localhost", "::1")
        allow_test = os.getenv("ALLOW_TEST_ENV_IN_PROD") == "true"
        if not is_localhost and not allow_test:
            raise RuntimeError(
                "ENV=test detected on non-localhost host. "
                "Set ALLOW_TEST_ENV_IN_PROD=true to override (NOT RECOMMENDED)."
            )
    ...
```

Bloquea el incidente F5 sin agregar fricción al desarrollo local.

### DT-F6-2 · Migración a Databricks Workflow gestionado (cierra R4)

Hoy: `infra/motoshop_dump_to_cloud.ps1` corre en Windows Task Scheduler cada 30 min, después un notebook gold corre nightly 02:30 COL.

F6: el flujo completo (bronze → silver → gold) se mueve a Databricks Workflow. El PC Windows sigue haciendo el dump → UC Volume (porque MySQL es local), pero la transformación bronze → silver → gold corre 100% en Databricks managed.

ADR de la decisión + diff vs hoy en `docs/decisions/0021-databricks-workflow-managed.md`.

### DT-F6-3 · Forecasting por categoría/familia (F4-FIX1 recomendación)

`notebooks/gold/24_forecast_categoria.py`:
- Agrega `mart_ventas_diarias_sku` por `categoria` o `familia` (definir esquema de agregación primero).
- Aplica baseline (media móvil 7/14/28 días) + Prophet sobre serie agregada.
- Compara WAPE vs baseline-por-SKU.
- Si WAPE categoría < WAPE SKU → producción cambia a forecasting agregado.

**Hipótesis a probar:** la cola larga de 6,185 SKUs con baja frecuencia se agrega bien en ~50 categorías con alta frecuencia → Prophet puede aprender estacionalidad.

### DT-F6-4 · ADR-0020 Forecasting agregado + jerarquía

`docs/decisions/0020-forecasting-agregado.md`:
- Decisión: forecast a nivel categoría como modelo de producción.
- Alternativa: forecast jerárquico (categoría + reconciliación a SKU) — diferido a F7 si negocio lo pide.
- Status: Proposed → Accepted al cierre F6-B si la hipótesis se valida.

### DT-F6-5 · Audit log monthly partition

`infra/migrations/F6-001-app_audit_log_partition.sql`:
- Convierte `app_audit_log` a tabla particionada por RANGE de `created_at` mensual.
- Job housekeeping en F6+ para drop particiones > 12 meses.
- Compatible con MySQL 5.0 (que sí soporta partitioning desde 5.1, validar versión exacta).

### DT-F6-6 · Drift monitoring básico

`notebooks/gold/25_drift_monitor.py`:
- Calcula WAPE de baseline semana actual vs WAPE histórico de las últimas 4 semanas.
- Si deviation > 30%, escribir alerta en `gold.alertas_drift`.
- Notificación push (re-usa infra F4-C) a admin.

### DT-F6-7 · Walk-forward validation classifier

`infra/run_classifier_walkforward.py`:
- Para cada semana W desde 2026-04-15: train con datos < W, test con W, recompute F1.
- Reporta F1 por semana → detecta degradación temporal.
- Resultado documentado en `docs/lecciones-aprendidas-f6.md`.

### DT-F6-8 · E5 memoria final estructurada

`docs/entregable/E5-memoria-final.md` se reescribe completo (no esqueleto) siguiendo plantilla de Maestría UAO:

1. Resumen ejecutivo (1 página)
2. Contexto del negocio + diagnóstico inicial
3. Arquitectura técnica final (con diagrama actualizado)
4. Pipeline operativo (E2 reusada)
5. Producto descriptivo (E3 reusada)
6. Producto predictivo (E4 ratificada + actualizada con forecasting categoría)
7. Operación bidireccional (F5)
8. Hardening + entrega (F6, este sprint)
9. Lecciones aprendidas (síntesis de F1-FIX1, F2-FIX1, F3.5, F4-FIX1, F5-FIX1)
10. Riesgos remanentes (R1, R2, R15)
11. Decisiones que cambiaríamos
12. Roadmap post-curso (F7+)
13. Bibliografía
14. Apéndices (ADRs, riesgos, capturas, métricas)

### DT-F6-9 · Demo 4G estandarizada

Humano graba 5 min con celular en 4G:
1. Login con usuario `vendedor`.
2. Búsqueda producto "aceite".
3. Ver ficha SKU + stock.
4. Logout, login como `admin`.
5. Ver dashboards (`/dashboards/ventas`, `/abc`, `/dormidos`).
6. Ver `/forecast` con StaleDataBanner si aplica.
7. Ver `/alerts`, click "Gestionar", marcar `ordered` con cantidad.
8. Ver `/acciones` con la acción recién creada.

Video subido a `motoshop-app/web/_runs/v_hito_demo_4g.mp4` (o link a Drive si pesa mucho).

### DT-F6-10 · Demo gerencia + feedback estructurado

Humano agenda 30 min con stakeholder (gerencia o Javier mismo como dueño):
1. Walkthrough de la PWA (10 min)
2. Demo del flujo "alerta → gestionar → registro" (5 min)
3. Demo del dashboard descriptivo (5 min)
4. Preguntas + feedback (10 min)

Captura en `notebooks/gold/_runs/v5_stakeholder_demo.md` con:
- 3 cosas que funcionaron
- 3 cosas a mejorar
- 1 feature solicitada (input para F7)

### DT-F6-11 · Cleanup final del repo

Revisor (yo) hace pass final:
- Verificar que `docs/archive/` tiene todo lo histórico.
- README público actualizado con badge de "5/7 fases cerradas → 7/7 cerradas".
- Capturas de PWA + Databricks SQL en `docs/entregable/screenshots/`.
- `.gitignore` review (asegurar no haya secrets nuevos por filtrarse).

### DT-F6-12 · Presentación final (opcional pero recomendado)

`docs/entregable/presentation/`:
- Slides (LaTeX Beamer o Keynote/PPT) de ~15 slides para defensa.
- Estructura: contexto → diagnóstico → arquitectura → métricas finales → lecciones → preguntas.
- Si humano quiere, lo armo yo en markdown + reveal.js.

---

## 5 · Sprints (3 sprints + humano)

### Sprint F6-A · Dev A · Hardening operativo (~4-5 h)

**Paso A1 · ENV guardrail (~30 min)**
- Implementar startup check en `main.py` siguiendo DT-F6-1.
- Test unit: arrancar con `ENV=test` + host=`192.168.x.x` → debe levantar RuntimeError.
- **Evidencia:** `tests/api/test_env_guardrail.py`.

**Paso A2 · Migración a Databricks Workflow (~1.5 h)**
- Crear `infra/create_full_workflow.py` que define el job completo (bronze → silver → gold → drift).
- Schedule cron `0 0 19 * * ?` (19:00 COL — después del último dump del día).
- Ejecutar 1 vez manual + UNPAUSE.
- **Evidencia:** `infra/_runs/full_workflow_unpaused_<ts>.md`.
- ADR-0021 documentando la migración.

**Paso A3 · Verificar R7 (workflow 7 corridas) (~15 min)**
- Query `system.workflows.runs` filtrado a `motoshop_gold_workflow` + `motoshop_full_workflow`.
- Reportar ≥ 7 corridas exitosas + tasa > 95%.
- **Evidencia:** `notebooks/gold/_runs/v_r7_workflow_runs_<ts>.md`.

**Paso A4 · Audit log monthly partition (~45 min)**
- Validar MySQL versión soporte partitioning (probablemente sí desde 5.1).
- Migration `F6-001-app_audit_log_partition.sql`.
- Backfill de datos existentes a particiones correctas.
- **Evidencia:** `infra/migrations/_runs/f6_partition_<ts>.md`.

**Paso A5 · Drift monitoring (~1 h)**
- `notebooks/gold/25_drift_monitor.py` siguiendo DT-F6-6.
- Crear tabla `gold.alertas_drift`.
- Agregar a workflow para ejecutar semanal.
- **Evidencia:** `notebooks/gold/_runs/v_drift_baseline_<ts>.md`.

**Paso A6 · Walk-forward classifier (~45 min)**
- `infra/run_classifier_walkforward.py` siguiendo DT-F6-7.
- Reportar F1 por semana en `notebooks/gold/_runs/v_walkforward_classifier_<ts>.md`.

### Sprint F6-B · Dev B (o Dev A second pass) · Forecasting categoría/familia (~3-4 h)

**Paso B1 · Esquema de agregación (~30 min)**
- Definir mapping SKU → categoría/familia (usando `dim_producto` campos existentes).
- Documentar en `notebooks/gold/_runs/v_categoria_schema_<ts>.md`.

**Paso B2 · Notebook forecasting categoría (~1.5 h)**
- `notebooks/gold/24_forecast_categoria.py`:
  - Agrega ventas por categoría × día.
  - Aplica baseline (media móvil 7/14/28) + Prophet sobre serie agregada.
  - Output a `gold.forecast_categoria`.

**Paso B3 · Evaluation comparativa (~45 min)**
- WAPE Prophet-categoría vs Baseline-categoría vs Baseline-SKU (referencia F4-FIX1).
- Cobertura: ¿cuántas categorías tienen ≥ 90d historia? (esperamos ~todas, vs 0.7% en SKU).
- **Hipótesis a validar:** Prophet-categoría < Baseline-categoría < Baseline-SKU (WAPE).
- **Evidencia:** `notebooks/gold/_runs/v_forecast_categoria_eval_<ts>.md`.

**Paso B4 · ADR-0020 + lecciones-aprendidas-f6.md (~30 min)**
- ADR-0020 con decisión (Proposed → Accepted si hipótesis se valida).
- `docs/lecciones-aprendidas-f6.md` con findings: walk-forward classifier + forecasting categoría.

**Paso B5 · Tests (~30 min)**
- Tests sqlparse en `tests/gold/test_forecast_categoria.py`.

### Sprint F6-C · Humano + Revisor · Entrega académica (~3-4 h)

**Paso C1 · Demo 4G (humano, ~30 min)**
- Humano graba en celular siguiendo guion DT-F6-9.
- Sube a `motoshop-app/web/_runs/v_hito_demo_4g.{mp4,md}`.
- Cierra R6.

**Paso C2 · Demo gerencia (humano, ~1 h)**
- Humano agenda + ejecuta sesión.
- Captura feedback en `notebooks/gold/_runs/v5_stakeholder_demo.md`.
- Cierra R8.

**Paso C3 · E5 memoria final (revisor, ~2 h)**
- Reescribir `docs/entregable/E5-memoria-final.md` siguiendo DT-F6-8.
- ~30-50 páginas markdown.
- Reusar contenido de E1, E2, E3, E4 con actualizaciones post-F5/F6.
- Sección "Decisiones que cambiaríamos" con 5-7 items reales.

**Paso C4 · Cleanup final + presentación (revisor, ~1 h)**
- Pass final repo siguiendo DT-F6-11.
- README público actualizado (badges, screenshots).
- Si humano quiere, slides en `docs/entregable/presentation/`.

**Paso C5 · Auditoría final (revisor)**
- Aplicar 9 checks de INICIAR_REVIEWER.md.
- Veredicto cierre proyecto.

---

## 6 · V críticas (gates para cerrar F6)

| ID | Verificación | Pass criterion | Owner | Evidencia |
|----|--------------|---------------|-------|-----------|
| **V-F6-1** | ENV guardrail funciona | Test arranca `ENV=test` + host externo → RuntimeError; arranca `ENV=test` + localhost → OK | Dev A | `tests/api/test_env_guardrail.py` |
| **V-F6-2** | Workflow Databricks migrado | `system.workflows.runs` muestra `motoshop_full_workflow` UNPAUSED + ≥1 corrida exitosa | Dev A | `_runs/full_workflow_unpaused_<ts>.md` |
| **V-F6-3** | R7 cierra: 7+ corridas exitosas | Query muestra ≥7 runs successful, tasa > 95% | Dev A | `v_r7_workflow_runs_<ts>.md` |
| **V-F6-4** | Audit log particionado | `EXPLAIN PARTITIONS SELECT * FROM app_audit_log` muestra particiones mensuales | Dev A | `f6_partition_<ts>.md` |
| **V-F6-5** | Drift monitoring operativo | `gold.alertas_drift` poblada con al menos 1 corrida + lógica validada | Dev A | `v_drift_baseline_<ts>.md` |
| **V-F6-6** | Walk-forward classifier | Reporte F1 por semana desde 2026-04-15 a hoy | Dev A | `v_walkforward_classifier_<ts>.md` |
| **V-F6-7** | Forecasting categoría WAPE < Baseline SKU | Tabla comparativa muestra Prophet-categoría WAPE < 45.83% (Baseline-SKU referencia F4-FIX1) | Dev B | `v_forecast_categoria_eval_<ts>.md` |
| **V-F6-8** | ADR-0020 + ADR-0021 Accepted | Status en ambos = Accepted | Revisor | git diff |
| **V-F6-9** | Demo 4G capturada | Video + README en `_runs/v_hito_demo_4g.md` | Humano | archivo subido |
| **V-F6-10** | Demo gerencia con feedback | `v5_stakeholder_demo.md` con 3+3+1 estructurado | Humano | archivo subido |
| **V-F6-11** | E5 memoria final completa | Doc ~30-50 págs con 14 secciones de DT-F6-8 | Revisor | git diff |
| **V-F6-12** | Cleanup final + repo defendible | README actualizado, `.gitignore` review, capturas en `docs/entregable/screenshots/` | Revisor | git diff |

**Gate de cierre F6:** V-F6-1 a V-F6-12 TODAS PASS.

Excepción aceptable: V-F6-7 puede fallar si la hipótesis de agregación no se cumple. En ese caso documentar honestamente en lecciones-aprendidas-f6.md (mismo patrón de F4-FIX1).

---

## 7 · Riesgos específicos de F6

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| **R-F6-1** | Forecasting categoría no supera baseline (V-F6-7 falla) | Aceptable. Documentar honestamente igual que F4-FIX1. Dataset puede ser insuficiente aún a nivel categoría. |
| **R-F6-2** | Demo gerencia no se puede agendar antes del cierre académico | Humano hace demo a sí mismo o a un familiar como stand-in; documentar como auto-demo. |
| **R-F6-3** | MySQL 5.0 no soporta partitioning real (era 5.1+) | Verificar en Paso A4. Si falla, mantener tabla simple + housekeeping job manual. R-F5-6 sigue abierta. |
| **R-F6-4** | Workflow Databricks managed tiene costo no esperado | Free Edition limita corridas. Validar que cron 19:00 + bronze hourly no exceda quota antes de UNPAUSE. |
| **R-F6-5** | Video demo 4G muy pesado para git | Subir a Drive/YouTube; en repo solo link + screenshots. |
| **R-F6-6** | E5 memoria queda más larga de lo permitido por curso | Curso Maestría suele aceptar 30-50 págs. Si necesita ser más corta, sintetizar + apéndices. |
| **R-F6-7** | Drift monitoring tarda en arrancar (necesita 4 semanas para baseline) | Implementar lógica + dejar corriendo; documentar como "se activa en 4 semanas". |

---

## 8 · Prompts handoff

### 🤖 Dev A · Sprint F6-A · Hardening operativo (~4-5 h)

```
Soy Dev A · Track A · Sprint F6-A del proyecto MotoShop.
Trabajo en paralelo con Dev B (no nos coordinamos en código,
solo evitamos conflicto en SEGUIMIENTO.md y PENDIENTES.md).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A)
4. Leé docs/plan-f6.md COMPLETO
5. Leé docs/contexto-proyecto.md §10 (deudas R4, R7, R16)
6. Leé infra/create_gold_workflow.py (entender setup actual)
7. Leé motoshop-app/api/src/motoshop_api/main.py (lifespan actual)

MI MISIÓN:
Hardening operativo del último sprint del proyecto. Cerrar R4 (workflow
Databricks managed), R7 (7+ corridas exitosas), R16 (ENV guardrail).
Implementar drift monitoring + walk-forward classifier como mejoras
predictivas. Audit log particionado.

ENTREGABLES (en orden):
1. ENV guardrail en main.py lifespan + tests/api/test_env_guardrail.py
2. infra/create_full_workflow.py (bronze→silver→gold→drift, cron 19:00)
3. Re-correr full workflow + UNPAUSE + evidencia en _runs/
4. notebooks/gold/_runs/v_r7_workflow_runs_<ts>.md (≥7 runs, >95%)
5. infra/migrations/F6-001-app_audit_log_partition.sql + evidencia
6. notebooks/gold/25_drift_monitor.py + tabla gold.alertas_drift
7. infra/run_classifier_walkforward.py + reporte F1 por semana
8. docs/decisions/0021-databricks-workflow-managed.md (Proposed)
9. Actualizar SEGUIMIENTO.md sección Dev A

NO TOCO:
- motoshop-app/web/** (no aplica en F6-A)
- notebooks/silver/** (estables)
- users.yaml (R15 diferida sigue)
- infra/start_api.ps1 + start_tunnel.ps1 (operativos)

COORDINACIÓN CON DEV B:
- Cada uno actualiza SOLO su sección en SEGUIMIENTO/PENDIENTES
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: feat(F6-A-hardening): ...

CIERRE:
Cuando V-F6-1..V-F6-6 + V-F6-8 (ADR-0021) pasen, commit + push.
Después escribo en SEGUIMIENTO.md una nota de cierre honesta.

ARRANQUE:
Paso A1 (ENV guardrail). Es lo más rápido y desbloquea cualquier
deploy a Windows con confianza. Después seguí con A2 (workflow
migration) que es lo más largo.
```

### 🤖 Dev B · Sprint F6-B · Forecasting categoría/familia (~3-4 h)

```
Soy Dev B · Track A · Sprint F6-B del proyecto MotoShop.
Trabajo en paralelo con Dev A. Soy un dev nuevo en este sprint para
hacer trabajo analítico mientras Dev A hace hardening operativo.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A · subteam analítico)
4. Leé docs/plan-f6.md COMPLETO (especial §3 DT-F6-3, DT-F6-4)
5. Leé docs/lecciones-aprendidas-f4.md (entender por qué F4 no funcionó)
6. Leé docs/decisions/0017-split-temporal-metricas-intermitentes.md
7. Leé notebooks/gold/19_feature_store.py (estructura del feature store)
8. Leé notebooks/silver/01_dim_producto.py (entender campos categoría/familia)

MI MISIÓN:
Validar la hipótesis académica de F4-FIX1: forecasting agregado por
categoría/familia supera al baseline por SKU individual. Implementar
notebook + evaluación honesta + ADR-0020.

ENTREGABLES (en orden):
1. notebooks/gold/_runs/v_categoria_schema_<ts>.md con mapping SKU→categoría
2. notebooks/gold/24_forecast_categoria.py (baseline+Prophet sobre serie agregada)
3. Tabla gold.forecast_categoria poblada
4. notebooks/gold/_runs/v_forecast_categoria_eval_<ts>.md con WAPE
   comparativa (vs Baseline-SKU 45.83% de F4-FIX1)
5. docs/decisions/0020-forecasting-agregado.md (Proposed → Accepted
   si hipótesis se valida)
6. docs/lecciones-aprendidas-f6.md (resumen findings)
7. tests/gold/test_forecast_categoria.py (sqlparse)
8. Actualizar SEGUIMIENTO.md sección Dev B

NO TOCO:
- motoshop-app/** (Dev A o no aplica)
- infra/** (Dev A)
- notebooks/bronze|silver/** (estables)
- users.yaml (R15 diferida)

COORDINACIÓN CON DEV A:
- Cada uno actualiza SOLO su sección en SEGUIMIENTO/PENDIENTES
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: feat(F6-B-analytics): ...

HONESTIDAD ACADÉMICA:
Si la hipótesis NO se valida (Prophet-categoría no supera Baseline-SKU),
DOCUMÉNTALO igual que F4-FIX1 hizo con Prophet por SKU. Eso es
descubrimiento técnico válido, no fracaso. La conclusión real sirve
para defensa académica.

CIERRE:
Cuando V-F6-7 + V-F6-8 (ADR-0020) pasen (PASS o FAIL documentado),
commit + push. Después escribo en SEGUIMIENTO.md una nota de cierre
honesta.

ARRANQUE:
Paso B1 (esquema de agregación). NO empieces el notebook sin tener
claro qué nivel de agregación usás (línea/categoría/familia) — eso
afecta todo lo demás.
```

### 👤 Humano · Sprint F6-C · Demos académicas (~2 h)

```
Acciones humanas para cerrar F6:

PASO C1 · Demo 4G (~30 min)

En el celular (red 4G real, NO Wi-Fi):
1. Abrir https://api.fragloesja.uk (PWA instalable)
2. Login como vendedor (admin/FG28 si es solo prueba)
3. Búsqueda producto "aceite" → ver resultados
4. Click en un SKU → ver ficha + stock
5. Logout + login como admin
6. Ver /dashboards/ventas, /abc, /dormidos
7. Ver /forecast (notar StaleDataBanner si datos > 24h)
8. Ver /alerts → click "Gestionar" en una alerta → marcar ordered con qty=10
9. Ver /acciones → confirmar que aparece la acción nueva

GRABAR todo el flujo en video (~5 min). Subir a motoshop-app/web/_runs/
como v_hito_demo_4g.mp4 (o link a Drive si > 50 MB).

Crear motoshop-app/web/_runs/v_hito_demo_4g.md con:
- Fecha + duración del video
- Red usada (4G operador X)
- Modelo de celular
- Observaciones (latencia subjetiva, glitches, etc.)


PASO C2 · Demo gerencia (~1 h)

Agendar 30 min con stakeholder (gerencia MotoShop o vos mismo como
dueño del negocio). Estructura:

10 min — Walkthrough PWA (login, dashboards, alertas)
5 min  — Demo flujo "alerta → gestionar → registro"
5 min  — Demo dashboards descriptivos
10 min — Preguntas + feedback

Capturar en notebooks/gold/_runs/v5_stakeholder_demo.md:
- Asistentes
- 3 cosas que funcionaron
- 3 cosas a mejorar
- 1 feature solicitada (input para F7+)


PASO C3 · Aviso al revisor

Cuando C1 + C2 estén hechos, avísame en el chat del revisor.
Yo escribo la E5 memoria final + cleanup repo + audit cierre F6.
```

---

## 9 · Cronograma sugerido

| Tiempo | Dev A | Dev B | Humano | Revisor |
|--------|-------|-------|--------|---------|
| 0:00 | A1 ENV guardrail | B1 esquema agregación | — | E5 draft sections 1-3 |
| 0:30 | A2 workflow migration | B2 notebook | — | E5 draft sections 4-6 |
| 1:00 | A2 cont. | B2 cont. | — | E5 draft sections 7-9 |
| 1:30 | A2 cont. | B3 evaluation | — | Standby |
| 2:00 | A3 R7 verify | B4 ADR-0020 + lecciones | C1 Demo 4G | Standby |
| 2:30 | A4 partition | B5 tests | C1 cont. | Standby |
| 3:00 | A5 drift monitor | Push final | C2 Demo gerencia | Standby |
| 3:30 | A5 cont. | — | C2 cont. | Standby |
| 4:00 | A6 walk-forward | — | C2 cont. | E5 sections 10-14 |
| 4:30 | Push final | — | C3 aviso | Cleanup final + presentation |
| 5:00 | — | — | — | Audit final + veredicto |
| 5:30 | — | — | — | Cierre proyecto |

Total wall-clock estimado: **~5-6 horas** con paralelización máxima.

---

## 10 · Cierre + auditoría final del proyecto

Una vez Dev A + Dev B + Humano cierren:

1. Revisor (yo) corre los 9 checks de `INICIAR_REVIEWER.md`.
2. Verifica las 12 V-F6.
3. Especial atención a:
   - **Check 4 (Seguridad):** documentar formalmente R1/R2/R15 como aceptadas en E5 §3.
   - **Check 5 (Sniff test ML):** validar WAPE de forecasting categoría con misma rigurosidad que F4-FIX1.
   - **Check 7 (Silver↔Bronze):** ratificar que sigue cuadrando tras 30+ días.
   - **Check 9 (Real vs Fake):** verificar que el guardrail R16 está activo en prod.
4. Si TODAS PASS → cierra F6 verde + **cierra el proyecto académico**. README público actualizado con "7/7 fases cerradas". Repo en estado defendible.
5. Si alguna FAIL → F6-FIX1 con plan corto (estamos contra el calendario académico — priorizar fixes críticos).

---

## 11 · Qué sigue después de F6 (post-curso)

**No es parte de F6**, pero queda documentado en E5 §12 (Roadmap):

- **F7 · Streaming + drift monitoring avanzado** (Spark Structured Streaming + reentrenamiento automático).
- **F8 · Multi-tienda** (multi-tenancy MotoShop como SaaS).
- **F9 · Marketplace** (B2B entre tiendas hermanas).
- **Cleanup R1/R2/R15** (rotación passwords + reescritura history) — si el repo se vuelve público + acceso a la BD.
- **Migración BD cloud** (MySQL en RDS/Aurora) — cuando MotoShop crezca o tenga otra tienda.

---

## 12 · Costo total estimado

| Rol | Tiempo | Notas |
|-----|--------|-------|
| Dev A | 4-5 h | ENV guardrail + workflow migration + audit partition + drift + walk-forward |
| Dev B | 3-4 h | Forecasting categoría + evaluation + ADR-0020 + lecciones |
| Humano | 2 h | Demo 4G + demo gerencia + agenda |
| Revisor (yo) | 2-3 h | E5 memoria + cleanup + audit final |
| **Total wall-clock** | **~5-6 h** (paralelo) | Si fuera secuencial: ~11-14 h |

Reducción ~45% vs secuencial con paralelización Dev A + Dev B + Humano + Revisor.

---

## 13 · Definition of Done del proyecto

F6 cerrada verde = **proyecto académico MotoShop COMPLETO**.

Entregables finales:
- ✅ 7/7 fases cerradas (F0 → F6) + 4 hardening sprints
- ✅ 21+ ADRs aceptados
- ✅ 5/16 riesgos cerrados (R3 ✅, R-X2 ✅, R4 ✅, R7 ✅, R16 ✅) + 7 mitigados (R5, R6, R8, R11, R12, R13, R14) + 4 aceptadas (R1, R2, R10, R15)
- ✅ Repo público con README defendible
- ✅ E1-E5 en `docs/entregable/` completos
- ✅ Demo 4G + demo gerencia capturadas
- ✅ Memoria final E5 lista para entrega Maestría UAO 2025-2
- ✅ Pipeline operativo 24/7 con monitoring
- ✅ Producto descriptivo (4 dashboards) + producto predictivo (baseline + classifier + forecasting categoría)
- ✅ Operación bidireccional (PWA → MySQL via app_*)

**Después de F6 no hay más sprints — el proyecto está completo.**
