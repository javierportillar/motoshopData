# Plan F4-FIX1 · Remediación auditoría F4 — 3 agentes en paralelo

- **Fecha apertura:** 2026-05-30 (Sesión 42)
- **Origen:** auditoría revisor fresco post-F4-B/F4-C. Ver `SEGUIMIENTO.md` §Nota Sesión 42 (a escribir) y el resumen abajo (§1).
- **Modo:** paralelo · **2 devs (Dev A · ML, Dev T · PWA+R10) + Revisor (yo · process docs)**.
- **Duración estimada:** Dev A 2-3 h · Dev T 1.5-2 h · Revisor 45 min (asíncrono).
- **Estado:** 🟡 ABIERTA.

---

## 1 · Por qué existe F4-FIX1 (los hallazgos)

Una auditoría con contexto fresco sobre el cierre de F4-B/F4-C levantó 6 hallazgos:

### 🔴 Bloqueantes (no se debió cerrar F4-B verde con esto)

1. **Prophet MAPE = 3,540%.** No es "modelo peor que baseline" — es modelo roto o métrica rota. Causa probable: división por cero en MAPE con demanda intermitente (días con `actual=0`), Prophet sin `floor=0`, o SKUs con < 30 puntos de historia entrenándose como si tuvieran serie completa.
2. **Classifier F1 = 0.9924.** Sospechoso de data leakage o desbalance no manejado. El reporte no documenta: distribución target train/test, split temporal exacto, top-10 features por importancia.

### 🟡 Observaciones

3. **F4-C cerrado con FakeRepos en lugar de validar contra Gold real.** Repite el problema que F3.5 expuso: validar contra fakes que cuadran trivialmente.
4. **R10 (PC Windows offline) tiene "mitigación" que en realidad es aceptación.** "Documentar como stale" no alerta al usuario que está viendo datos viejos.
5. **No hay ADR de split temporal.** Sin esto, las métricas de forecasting son indefendibles ante un jurado.
6. **La lección de F3.5 §10 nunca se propagó a `INICIAR_REVIEWER.md`.** Próxima auditoría va a cometer el mismo error que F3 cometió con el universo silver↔bronze.

---

## 2 · Hipótesis a verificar (Dev A)

### Sobre Prophet (MAPE 3540%)

- **H-A1:** MAPE infla porque `actual=0` en muchos días de demanda intermitente. Verificación: calcular sMAPE y WAPE excluyendo días con `actual=0`.
- **H-A2:** Prophet entrenó con SKUs que tienen < 30 puntos. Verificación: filtrar SKUs con history_length ≥ 90 días y mínimo 30 ventas.
- **H-A3:** Prophet no tenía `floor=0`, predijo valores negativos que se cortaron a 0 a posteriori (commit `1f31f07` muestra `max(0, predicted_qty)`). Verificación: re-entrenar con `growth='linear'` + `cap` razonable + `floor=0`.

### Sobre Classifier (F1 0.9924)

- **H-B1:** Split aleatorio en vez de temporal. Verificación: imprimir min/max de `business_date` en train vs test; deben no solaparse.
- **H-B2:** Target leak en features. Verificación: top-10 feature_importances; flagear `stock_actual`, `dias_sin_venta`, `cantidad_vendida_ultimos_X` si están y eran derivados del target.
- **H-B3:** Desbalance extremo no manejado. Verificación: imprimir `value_counts(target)` en train y test; si >99% es clase mayoritaria, F1 inflado por accuracy.

---

## 3 · Alcance y NO alcance

### Alcance (qué SÍ toca F4-FIX1)

**Track A (Dev A · ML):**
- `infra/run_forecast_prophet.py` — fix metrics + filtro SKUs
- `infra/run_forecast_lightgbm.py` — mismo patrón si aplica
- `infra/run_classifier_stockout.py` — auditoría temporal split + leakage check
- `infra/run_evaluate_models.py` — métricas honestas (sMAPE/WAPE excluyendo ceros)
- `notebooks/gold/22_classifier_stockout.py` — verificar que el split sea temporal en el código fuente del notebook
- `notebooks/gold/_runs/v_fix1_*` — nueva evidencia versionada
- `docs/decisions/0017-split-temporal-y-metricas-forecasting.md` — ADR nuevo

**Track T (Dev T · PWA + R10):**
- `motoshop-app/api/src/motoshop_api/forecast/repo.py` — RealForecastRepo (no Fake) usado por defecto en prod
- `motoshop-app/api/src/motoshop_api/alerts/repo.py` — RealAlertsRepo
- `motoshop-app/web/app/(authenticated)/forecasts/page.tsx` — consume API real
- `motoshop-app/web/app/(authenticated)/alertas/page.tsx` — consume API real
- `motoshop-app/web/components/StaleDataBanner.tsx` — componente nuevo que lee `/health/data-freshness` y muestra banner si `> 24h`
- `motoshop-app/web/tests/forecasts.spec.ts` — Playwright E2E
- `motoshop-app/web/_runs/v_fix1_forecast_real.md` — evidencia reconciliación PWA↔Databricks
- `motoshop-app/web/_runs/v_fix1_stale_banner.md` — evidencia banner stale

**Revisor (yo · process):**
- `INICIAR_REVIEWER.md` — agregar §3.2 sub-check silver_completeness + §3.X nuevo "Sniff test métricas ML"
- `SEGUIMIENTO.md` — nota Sesión 42 con auditoría detallada + abrir F4-FIX1
- `PENDIENTES.md` — handoffs Dev A + Dev T + cierre revisor
- `docs/contexto-proyecto.md` §10 — R11 nuevo (métricas ML no auditadas) hasta que F4-FIX1 cierre
- `INICIAR_AGENTE.md` — si aplica, sección sobre sniff test ML para devs

### NO alcance (qué NO toca F4-FIX1)

- **No re-entrenar todos los modelos desde cero** si el fix de métricas explica los números actuales sin re-train.
- **No tocar Feature Store (`notebooks/gold/19_feature_store.py`)** salvo que H-B2 confirme leakage — entonces sí.
- **No bronze ni silver** — están sanos post-F3.5.
- **No F5 ni F6** — postergados hasta cierre F4-FIX1.

---

## 4 · Decisiones técnicas (DT-F4-FIX1)

**DT-F4-FIX1-1 · Métrica primaria para demanda intermitente: WAPE excluyendo ceros + cobertura.** Para SKUs con demanda intermitente (muchos días con `actual=0`), MAPE es inválido (división por cero). Métricas válidas: WAPE = `SUM(|y - yhat|) / SUM(y)`, evaluada solo en días con venta + cobertura (`% días con venta predichos correctamente`). sMAPE como secundaria. MAPE se reporta solo si el SKU tiene < 5% de días con `actual=0`.

**DT-F4-FIX1-2 · Filtro de elegibilidad SKU para forecasting:** mínimo 90 días de historia + ≥ 30 ventas totales. SKUs que no califican van a baseline sin ser evaluados por Prophet/LightGBM (evita métricas infladas por modelos mal especificados).

**DT-F4-FIX1-3 · Split temporal explícito documentado en ADR-0017.** Train hasta `'2026-03-31'`, test desde `'2026-04-01'` (~60 días test). Train/test NO se solapan. Si Dev A debe reentrenar, cumple este split. Walk-forward queda como mejora F6.

**DT-F4-FIX1-4 · Classifier reporta: target distribution + top-10 features + split temporal en el mismo run.** Cualquier reporte de classifier que no muestre estos tres bloques se considera incompleto. Cobertura mínima en el evidence file: 3 secciones.

**DT-F4-FIX1-5 · PWA usa Real repos por defecto en prod.** Fakes solo en `tests/`. El binding por `Depends()` en FastAPI elige Real cuando `env=prod`.

**DT-F4-FIX1-6 · Stale Data Banner activo cuando freshness > 24h.** Componente React global en `/forecasts` y `/alertas`. Lee `/health/data-freshness` con SWR cada 5 min. Si lag > 24h muestra banner amarillo con texto "Predicciones basadas en datos de hace X horas. Revisar pipeline." con `data-testid="stale-banner"`.

**DT-F4-FIX1-7 · `INICIAR_REVIEWER.md` agrega 2 checks bloqueantes:**
- Check de cuadre **silver↔bronze por tabla fact_*** antes de aceptar gate de cuadre.
- Sniff test de métricas ML: flagear como **NO-GO automático** cualquier MAPE > 100%, sMAPE > 100%, F1 > 0.97, accuracy > 0.99, sin investigación documentada de causa raíz.

---

## 5 · Sprints (2 devs + revisor en paralelo)

### Sprint F4-FIX1-A · Dev A · ML diagnosis & honest metrics (~2-3 h)

**Paso A1 · Diagnóstico métricas Prophet (~45 min)**
- Leer `infra/run_forecast_prophet.py` y `infra/run_evaluate_models.py`.
- Identificar cómo se calcula MAPE y si excluye `actual=0`.
- Imprimir distribución de `actual` en test: % días con cero por SKU evaluado.
- Verificar config Prophet: `floor`, `cap`, `growth`.
- **Entregable:** `notebooks/gold/_runs/v_fix1_prophet_diagnostico_<ts>.md` con causa raíz + tabla de SKUs evaluados con `history_length` y `% zeros`.

**Paso A2 · Fix métricas + filtro SKUs (~45 min)**
- En `run_evaluate_models.py`: WAPE (excluyendo ceros) + sMAPE + MAPE solo si `% zeros < 5%`. Cobertura como métrica adicional.
- Filtro SKU elegible (DT-FIX1-2) aplicado antes de evaluar Prophet/LightGBM.
- Re-correr evaluación y capturar `v_fix1_model_evaluation_<ts>.md`.

**Paso A3 · Auditoría Classifier (~45 min)**
- Leer `notebooks/gold/22_classifier_stockout.py` y `infra/run_classifier_stockout.py`.
- Imprimir y capturar:
  - `value_counts(target)` en train y test.
  - `min/max(business_date)` en train y test → confirmar no solapamiento.
  - `feature_importances_` top-10 con descripción de qué es cada feature.
- **Entregable:** `notebooks/gold/_runs/v_fix1_classifier_auditoria_<ts>.md` con las 3 secciones.
- Si H-B2 confirma leakage (alguna feature derivada del target con importance > 30%), aplicar fix y re-entrenar con split temporal. Si no, dejar nota explicando por qué F1 alto es legítimo (raro pero posible).

**Paso A4 · ADR-0017 Split temporal + métricas intermitentes (~30 min)**
- Crear `docs/decisions/0017-split-temporal-y-metricas-forecasting.md` siguiendo plantilla de ADRs anteriores.
- Decisión: split `2026-03-31` corte; WAPE como métrica primaria; filtro SKU mínimo 90d+30 ventas.
- Alternativas descartadas: walk-forward (postergado a F6 por compute), MAPE puro (división por cero).

**Paso A5 · Mensaje académico honesto (~15 min)**
- Crear `docs/predict/lecciones-aprendidas-f4.md` con:
  - Hipótesis: dataset insuficiente para forecasting por SKU.
  - Evidencia: cola larga con < 30 ventas en X% de SKUs; Prophet/LightGBM ganan en ~6.4% de SKUs (228+71 = ~6.4% con métricas corregidas, si aplica).
  - Recomendación F6: agregación por categoría/familia + más histórico.

### Sprint F4-FIX1-B · Dev T · PWA real + R10 banner (~1.5-2 h)

**Paso B1 · Reemplazar FakeForecastRepo en prod (~30 min)**
- En `motoshop-app/api/src/motoshop_api/forecast/router.py` (o equivalente): `Depends(get_forecast_repo)` retorna RealForecastRepo cuando `settings.env != 'test'`.
- RealForecastRepo lee `motoshop.gold.forecast_demanda_sku` vía Databricks SDK.
- Mismo patrón para `RealAlertsRepo` sobre `motoshop.gold.alertas_quiebre`.

**Paso B2 · V-fix forecast PWA↔Databricks SQL (~30 min)**
- Ejecutar query manual en Databricks SQL: top 10 SKUs con forecast más alto a 7d.
- Navegar PWA `/forecasts` con los mismos filtros; comparar.
- **Entregable:** `motoshop-app/web/_runs/v_fix1_forecast_real.md` con tabla bronze (SQL) vs PWA + match 100%.

**Paso B3 · V-fix alertas PWA↔Databricks SQL (~20 min)**
- Mismo patrón con `alertas_quiebre`: SQL devuelve 69 alertas (según report F4-B). PWA muestra las mismas 69 con mismos SKUs.
- **Entregable:** `motoshop-app/web/_runs/v_fix1_alertas_real.md`.

**Paso B4 · StaleDataBanner component (~30 min)**
- Crear `motoshop-app/web/components/StaleDataBanner.tsx`:
  - SWR a `/api/health/data-freshness` cada 5 min.
  - Si `lag_hours > 24`: banner amarillo fijo arriba con texto "Predicciones basadas en datos de hace {lag_hours}h. Revisar pipeline." + `data-testid="stale-banner"`.
- Importar en `/forecasts/page.tsx` y `/alertas/page.tsx`.

**Paso B5 · E2E Playwright (~20 min)**
- `motoshop-app/web/tests/forecasts.spec.ts`:
  - Mockear `/api/health/data-freshness` con `lag_hours: 30`.
  - Visitar `/forecasts`.
  - Assert que `data-testid="stale-banner"` está visible y contiene "30".
- **Entregable:** `motoshop-app/web/_runs/v_fix1_stale_banner.md` con screenshot + log.

### Sprint F4-FIX1-R · Revisor (yo) · Process docs (~45 min, async)

**Paso R1 · INICIAR_REVIEWER.md actualizado**
- Agregar a §3.2 ("Cuadre de cifras") sub-check explícito: para cada tabla `fact_*` en silver, comparar `COUNT(silver)` vs `COUNT(bronze WHERE filtros documentados)` con tolerancia 0 filas. Si diff > 1%, NO-GO automático.
- Agregar §3.5 (o siguiente disponible) "Sniff test de métricas ML": MAPE > 100% / sMAPE > 100% / F1 > 0.97 / accuracy > 0.99 sin investigación documentada → NO-GO automático.

**Paso R2 · SEGUIMIENTO + PENDIENTES + contexto-proyecto**
- Nota Sesión 42 en SEGUIMIENTO.md con auditoría detallada + apertura F4-FIX1.
- R11 en `contexto-proyecto.md` §10: "Métricas ML F4-B no auditadas (Prophet MAPE 3540% / Classifier F1 0.99)" — abierta hasta cierre F4-FIX1.
- PENDIENTES Sesión 42 con prompts Dev A + Dev T listos para pegar.

**Paso R3 · Commit + push**
- `docs(F4-FIX1): plan + auditoría revisor + checks reviewer actualizados`.

---

## 6 · V críticas (gates para cerrar F4-FIX1)

| ID | Verificación | Pass criterion | Owner | Evidencia |
|----|--------------|---------------|-------|-----------|
| **V-FIX1-1** | Métricas Prophet con WAPE/sMAPE excluyendo ceros + filtro SKU elegible | Reporte muestra WAPE, sMAPE, cobertura por SKU; tabla incluye `history_length` y `% zeros`; NO se reporta MAPE para SKUs con > 5% ceros | Dev A | `v_fix1_model_evaluation_<ts>.md` |
| **V-FIX1-2** | Classifier reporta target dist + split temporal + top-10 features | 3 secciones presentes en evidence; `train.max(date) < test.min(date)`; ningún feature obvio como leak | Dev A | `v_fix1_classifier_auditoria_<ts>.md` |
| **V-FIX1-3** | Re-evaluación con métricas honestas | Evaluation re-corrida; mejor modelo por SKU recalculado; conclusión académica honesta documentada | Dev A | `v_fix1_model_evaluation_<ts>.md` + `lecciones-aprendidas-f4.md` |
| **V-FIX1-4** | ADR-0017 aceptado | Status `Accepted`, decisión + alternativas + rationale presentes | Dev A | `docs/decisions/0017-*.md` |
| **V-FIX1-5** | PWA /forecasts consume Real repo | Tabla SQL vs PWA: 10 SKUs top match 100% | Dev T | `v_fix1_forecast_real.md` |
| **V-FIX1-6** | PWA /alertas consume Real repo | Tabla SQL vs PWA: 69 alertas match | Dev T | `v_fix1_alertas_real.md` |
| **V-FIX1-7** | StaleDataBanner aparece con lag > 24h | Playwright assertion verde con mock `lag_hours: 30` | Dev T | `v_fix1_stale_banner.md` |
| **V-FIX1-8** | INICIAR_REVIEWER.md tiene checks nuevos | §3.2 silver_completeness sub-check; §3.X sniff test ML | Revisor | diff visible en commit |

**Gate de cierre F4-FIX1:** V-FIX1-1 a V-FIX1-8 TODAS PASS.

---

## 7 · Riesgos

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| **R-FIX1-1** | H-B2 confirma leakage en classifier → re-entrenar agrega 1-2 h | Dev A documenta el leak en evidence y propone fix; si re-train es necesario, ejecuta. Acepto la extensión de tiempo. |
| **R-FIX1-2** | Real repo de PWA tira timeout en SQL Warehouse Free (10 min auto-stop) | Dev T añade retry con backoff en RealForecastRepo + log estructurado. Aceptable hasta F6. |
| **R-FIX1-3** | Stale banner se activa siempre porque `/health/data-freshness` devuelve > 24h en local dev | Mock en local dev con var de entorno `FORCE_FRESH=true`. Documentar en README. |
| **R-FIX1-4** | Re-corrida de evaluación tarda > 30 min en Free Edition | Dev A reporta tiempo real; si excede, factoriza solo top-100 SKUs (representativo). |
| **R-FIX1-5** | Dev A y Dev T tienen conflicto de merge en SEGUIMIENTO/PENDIENTES | Cada uno toca SOLO su sección; el revisor consolida al final con rebase. |

---

## 8 · Prompts handoff (listos para pegar)

### 🤖 Dev A · Sprint F4-FIX1-A

```
Soy Dev A · Track A · Sprint F4-FIX1 del proyecto MotoShop.
Trabajo en paralelo con Dev T (no me coordino con él en código,
solo evitamos conflicto en SEGUIMIENTO.md y PENDIENTES.md).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A)
4. Leé docs/plan-f4-fix1.md COMPLETO
5. Leé notebooks/gold/_runs/v_model_evaluation_20260530_013855.md
   (es el evaluation actual con Prophet MAPE 3540% — entender el "antes")
6. Leé infra/run_forecast_prophet.py + infra/run_evaluate_models.py +
   infra/run_classifier_stockout.py + notebooks/gold/22_classifier_stockout.py

MI MISIÓN:
Auditar Prophet (MAPE 3540% = modelo o métrica rota) y Classifier
(F1 0.9924 = sospechoso de leakage), aplicar fixes, re-evaluar con
métricas honestas, escribir ADR-0017 (split temporal + métricas
intermitentes) y lecciones-aprendidas-f4.md.

ENTREGABLES (en orden):
1. notebooks/gold/_runs/v_fix1_prophet_diagnostico_<ts>.md — causa
   raíz del MAPE 3540% identificada con tabla SKU x history_length x % zeros
2. Fix de run_evaluate_models.py: WAPE primaria + sMAPE + MAPE
   condicional + cobertura. Filtro SKU elegible (90d+30 ventas).
3. notebooks/gold/_runs/v_fix1_model_evaluation_<ts>.md con métricas
   nuevas + best model por SKU recalculado
4. notebooks/gold/_runs/v_fix1_classifier_auditoria_<ts>.md con las
   3 secciones obligatorias (target dist, split temporal, top-10 features)
5. Si H-B2 confirma leakage: fix + re-train + nueva evidence
6. docs/decisions/0017-split-temporal-y-metricas-forecasting.md
   con status Accepted
7. docs/predict/lecciones-aprendidas-f4.md con la conclusión académica
   honesta (insufficient data hypothesis)

LO QUE NO TOCO:
- motoshop-app/** (Dev T)
- notebooks/bronze/** ni notebooks/silver/** (estables post-F3.5)
- Credenciales / users.yaml / .env

COORDINACIÓN CON DEV T:
- Cada uno actualiza SOLO su sección en SEGUIMIENTO.md / PENDIENTES.md
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: fix(F4-FIX1-A-ml): ...

CIERRE:
Cuando V-FIX1-1, V-FIX1-2, V-FIX1-3, V-FIX1-4 pasen, commit + push.
Después escribo en SEGUIMIENTO.md una nota de cierre honesta.

ARRANQUE:
Paso A1 (Diagnóstico Prophet). NO toques run_evaluate_models.py
hasta tener el diagnóstico escrito.
```

### 🤖 Dev T · Sprint F4-FIX1-B

```
Soy Dev T · Track T · Sprint F4-FIX1 del proyecto MotoShop.
Trabajo en paralelo con Dev A (no me coordino con él en código,
solo evitamos conflicto en SEGUIMIENTO.md y PENDIENTES.md).

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track T)
4. Leé docs/plan-f4-fix1.md COMPLETO
5. Leé motoshop-app/api/src/motoshop_api/forecast/* y alerts/*
   (estructura actual con FakeRepos)
6. Leé motoshop-app/api/src/motoshop_api/health/router.py
   para entender el contrato /health/data-freshness existente

MI MISIÓN:
Reemplazar FakeForecastRepo y FakeAlertsRepo por Real en prod
(F4-C cerró con fakes — repite el problema de F3). Crear
StaleDataBanner para que la PWA alerte al usuario cuando los datos
están viejos (R10 actualmente solo "documenta" stale, no alerta).

ENTREGABLES (en orden):
1. motoshop-app/api/src/motoshop_api/forecast/repo.py:
   RealForecastRepo lee motoshop.gold.forecast_demanda_sku vía
   Databricks SDK. Dependency injection elige Real cuando env != 'test'
2. motoshop-app/api/src/motoshop_api/alerts/repo.py: mismo patrón
   con motoshop.gold.alertas_quiebre
3. motoshop-app/web/_runs/v_fix1_forecast_real.md: tabla SQL vs
   PWA con top 10 SKUs forecast 7d, match 100%
4. motoshop-app/web/_runs/v_fix1_alertas_real.md: 69 alertas SQL
   vs PWA match
5. motoshop-app/web/components/StaleDataBanner.tsx según DT-FIX1-6
6. Banner integrado en /forecasts y /alertas
7. motoshop-app/web/tests/forecasts.spec.ts con E2E del banner
8. motoshop-app/web/_runs/v_fix1_stale_banner.md con screenshot

LO QUE NO TOCO:
- infra/** ni notebooks/** (Dev A)
- Credenciales / users.yaml / .env

COORDINACIÓN CON DEV A:
- Cada uno actualiza SOLO su sección en SEGUIMIENTO.md / PENDIENTES.md
- Antes de cada git push: git pull --rebase origin main
- Commits con prefijo: fix(F4-FIX1-B-pwa): ...

CIERRE:
Cuando V-FIX1-5, V-FIX1-6, V-FIX1-7 pasen, commit + push.
Después escribo en SEGUIMIENTO.md una nota de cierre honesta.

ARRANQUE:
Paso B1 (RealForecastRepo). Mirá cómo lo hace metrics/repo.py
del Sprint F3-B como referencia (mismo patrón con Databricks SDK).
```

---

## 9 · Cierre + auditoría revisor

Una vez Dev A y Dev T cierren sus sprints:

1. Revisor (yo) corre los 6 checks de `INICIAR_REVIEWER.md` actualizado contra los entregables.
2. Verifica las 8 V-FIX1 con evidencia.
3. Si TODAS PASS → cierra F4-FIX1 verde, actualiza header global (F4-B ✅ / F4-C ✅), abre planificación F5.
4. Si alguna FAIL → F4-FIX2 con plan corto (mismo patrón F1-FIX1 → F1-FIX2).

---

## 10 · Costo total estimado

| Rol | Tiempo | Notas |
|-----|--------|-------|
| Dev A | 2-3 h | ML diagnosis + métricas + ADR + lecciones |
| Dev T | 1.5-2 h | PWA real repos + stale banner + E2E |
| Revisor (yo) | 45 min docs + 30 min auditoría final | Async durante sprints + bloqueo al cierre |
| **Total wall-clock** | **~3 h** (paralelo) | Si fuera secuencial: ~4-5 h |

3 agentes en paralelo (Dev A + Dev T + Revisor async) reduce wall-clock ~40% vs secuencial.
