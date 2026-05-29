# Plan F4 · Predictivo (ML)

- **Fecha apertura:** 2026-05-29 (Sesión 38)
- **Origen:** cierre exitoso F3.5 + F3.6, universo Silver corregido, ADR-0015 stack F3 aceptado
- **Modo:** secuencial · **1 dev por sprint** (Dev A para F4-A/B, Dev T para F4-C)
- **Duración estimada:** 20-26 h totales (3-4 sesiones)
- **Estado:** 🟡 ABIERTA.
- **ADR:** [0016-stack-f4.md](decisions/0016-stack-f4.md) — 10 decisiones técnicas

---

## 1 · Contexto y viabilidad

### Datos confirmados post-F3.5/F3.6

| Métrica | Valor |
|---------|-------|
| Filas diarias-SKU (mart_ventas_diarias_sku) | 24,374 |
| Rango temporal | 2024-01-11 a 2026-05-28 (~29 meses) |
| SKUs en catálogo | 6,185 |
| SKUs con inventario actual | 4,829 |
| Promedio facturas/mes | ~373 |
| Promedio ventas/mes | ~$23.5M COP |
| Top SKU | MOTS1297 (aceite) — $28.2M total, 850 facturas |
| Clientes únicos | 39 (15 cohortes) |

### Veredicto de viabilidad

- **Prophet viable** para top-100 SKUs: tienen señal diaria suficiente (~29 meses de historia).
- **LightGBM viable** para cola larga: features cross-SKU (categoría, bodega, rotación) compensan poca historia individual.
- **Constraint principal:** Databricks Free Edition no tiene clusters. Training local en Mac + MLflow remote tracking en workspace Databricks.

### ⚠️ Constraint crítico — PC Windows (sgHermes)

La base de datos MySQL `motoshop2024` (sgHermes) está en el **PC Windows**, que no está encendido todo el tiempo.

**Flujo de datos:**
```
PC Windows (MySQL) → dump_to_cloud.py → UC Volume → Databricks Bronze → Silver → Gold
```

**Implicaciones para F4:**
- **Training:** ✅ No depende del PC. Lee de `gold.feature_store_sku` que ya está en Databricks.
- **Serving:** ✅ No depende del PC. API lee de `gold.forecast_demanda_sku` y `gold.alertas_quiebre` en Databricks.
- **Data freshness:** ⚠️ Si el PC está apagado, no llegan datos nuevos a Bronze. Las predicciones se basan en el último snapshot disponible.
- **Re-entrenamiento:** ⚠️ Para re-entrenar modelos con datos nuevos, el PC debe estar online y el workflow de dump debe haber corrido.

**Mitigación existente (F1.9):**
- Dump cada 30 min en ventana 07:00–19:30 COL (25 oportunidades/día)
- Task Scheduler con `StartWhenAvailable=true` + retry
- Flag `--catch-up` que sube Parquets pendientes al volver internet
- Lag monitor: `GET /health/data-freshness`

**Regla para F4:** Los modelos se entrenan con el dataset existente (29 meses, 6,339 facturas). Si el PC está offline > 48h, las predicciones se consideran "stale" y se documenta en la evidencia.

---

## 2 · Decisiones técnicas (DT-F4)

Ver [ADR-0016](decisions/0016-stack-f4.md) para detalle completo.

| # | Decisión | Elección |
|---|----------|----------|
| DT-F4-1 | Compute para training | Local Mac + MLflow remote tracking |
| DT-F4-2 | Framework forecasting | Prophet (top-100) + LightGBM (global) |
| DT-F4-3 | HPO | Optuna (bayesiano) |
| DT-F4-4 | Feature store | Gold table `feature_store_sku` |
| DT-F4-5 | Serving | Pre-computed en gold, API lee gold |
| DT-F4-6 | Clasificador quiebre | LightGBM classifier |
| DT-F4-7 | Alertas push | pywebpush + infra existente |
| DT-F4-8 | Backtest | Walk-forward validation |
| DT-F4-9 | Métricas | MAPE, sMAPE, WAPE |
| DT-F4-10 | Umbral quiebre | Stock < demanda_diaria × horizon |

---

## 3 · Alcance y NO alcance

### Alcance (qué SÍ hace F4)

- Feature store Gold con lags, medias móviles, features temporales
- Baseline naive estacional registrado en MLflow
- Prophet para top-100 SKUs con predicciones 7/14/30 días
- LightGBM global para cola larga
- Clasificador de quiebre con F1 > 0.7
- Tablas `gold.forecast_demanda_sku` y `gold.alertas_quiebre`
- Endpoints `/forecast/{sku}` y `/alerts/stockout`
- PWA: vistas Predicciones y Alertas
- Push notifications activas para alertas críticas
- Backtest completo con MAPE comparativo

### NO alcance (qué NO toca F4)

- `notebooks/bronze/**` — bronze intacto
- `notebooks/silver/10-14_fact_*.py` — silver intacto (excepto push subscriptions)
- `motoship-app/api/src/motoship_api/metrics/**` — módulo metrics intacto
- Módulo auth, products, stock, sales — intactos
- `docs/plan-f3*.md` — no retroactivo
- F5 (escritura) — se decide en cierre F4
- Migración a Databricks pagado — se decide si compute local no alcanza

---

## 4 · Sprint F4-A · Feature Store + Baseline + MLflow

**Objetivo:** features materializadas, baseline registrado, sandbox MLflow funcionando.
**Dev:** A (Track A) · **Duración:** ~6-8 h

### Tareas

| # | Tarea | Archivos | Entregable |
|---|-------|----------|------------|
| A-1 | Crear `gold.feature_store_sku` | `notebooks/gold/15_feature_store_sku.py` | Tabla con lags 7/14/28d, medias móviles 7/14/28d, dia_semana, mes, es_festivo, stock_actual, dias_sin_venta, categoria_abc |
| A-2 | Crear `gold.forecast_baseline_sku` | `notebooks/gold/16_forecast_baseline_sku.py` | Naive estacional: predicción = demanda del mismo día/mes del año anterior |
| A-3 | Registrar baseline en MLflow | `notebooks/gold/17_mlflow_register_baseline.py` | `mlflow.log_metric("MAPE", ...)`, model registry |
| A-4 | Script backtest local | `infra/run_backtest.py` | Walk-forward, MAPE/sMAPE/WAPE por SKU |
| A-5 | Tests feature store | `tests/gold/test_feature_store.py` | Schema validation, null checks, lag correctness |
| A-6 | Evidencia | `notebooks/gold/_runs/v_feature_store_<ts>.md` | Conteos, stats, MAPE baseline |

### V-checks F4-A

| ID | Verificación | Pass criterion |
|----|-------------|----------------|
| V-FS1 | Feature store completo | `feature_store_sku` tiene ≥ 15 columnas y > 20K filas |
| V-FS2 | Baseline registrado | MLflow tiene ≥ 1 experimento con MAPE |
| V-FS3 | MAPE baseline documentado | MAPE calculado para top-100 SKUs |
| V-FS4 | Tests pasan | `pytest tests/gold/test_feature_store.py` verde |

---

## 5 · Sprint F4-B · Modelos + Clasificador

**Objetivo:** Prophet top-100, LightGBM global, clasificador quiebre, todo en MLflow.
**Dev:** A (Track A) · **Duración:** ~8-10 h

### Tareas

| # | Tarea | Archivos | Entregable |
|---|-------|----------|------------|
| B-1 | Prophet top-100 SKUs | `notebooks/gold/20_forecast_prophet.py` | Modelo por SKU, predicciones 7/14/30 días, MLflow |
| B-2 | LightGBM global (cola larga) | `notebooks/gold/21_forecast_lightgbm.py` | Modelo único cross-SKU, predicciones para todos |
| B-3 | Clasificador de quiebre | `notebooks/gold/22_classifier_stockout.py` | LightGBM classifier, F1 > 0.7 |
| B-4 | Tabla `gold.forecast_demanda_sku` | En notebooks 20/21 | sku, horizon, forecast_date, predicted_qty, model_version, confidence_lower, confidence_upper |
| B-5 | Tabla `gold.alertas_quiebre` | En notebook 22 | sku, stock_actual, demanda_predicha, dias_hasta_quiebre, urgencia |
| B-6 | Backtest completo | `infra/run_backtest.py` (extendido) | MAPE por SKU, F1 classifier, comparación vs baseline |
| B-7 | Tests modelos | `tests/gold/test_forecasts.py` | Schema, no negatives, confidence intervals |
| B-8 | Evidencia | `notebooks/gold/_runs/v_forecast_<ts>.md` | MAPE results, F1, comparison |

### V-checks F4-B

| ID | Verificación | Pass criterion |
|----|-------------|----------------|
| V-M1 | Prophet supera baseline | MAPE Prophet < MAPE baseline para top-100 |
| V-M2 | LightGBM supera baseline | MAPE LightGBM < MAPE baseline para cola larga |
| V-M3 | Classifier F1 | F1 > 0.7 en validación holdout |
| V-M4 | Predicciones completas | `forecast_demanda_sku` tiene ≥ 7 días de horizon |
| V-M5 | Alertas con urgencia | `alertas_quiebre` tiene registros alta/media/baja |
| V-M6 | Sanity check | 0 negative forecasts, 0 null SKU |

---

## 6 · Sprint F4-C · API + PWA + Push

**Objetivo:** endpoints forecast/alertas, PWA con gráficos, push activas.
**Dev:** T (Track T) · **Duración:** ~6-8 h

### Tareas

| # | Tarea | Archivos | Entregable |
|---|-------|----------|------------|
| C-1 | `ForecastRepo` + schemas | `forecast/repo.py`, `forecast/schemas.py` | Protocol + RealMetricsRepo lee gold |
| C-2 | `GET /forecast/{sku}?horizon=N` | `forecast/router.py` | JSON predicciones, model_version, confidence |
| C-3 | `GET /alerts/stockout` | `alerts/router.py` | Lista SKUs riesgo, ordenada por urgencia |
| C-4 | DB push subscriptions | `notebooks/silver/15_app_push_subscriptions.sql` | Tabla para persistir suscripciones |
| C-5 | Push sending | `push/sender.py` | pywebpush envía alertas urgencia alta |
| C-6 | PWA: vista Predicciones | `forecast/page.tsx` | Recharts forecast, selector SKU, horizon 7/14/30 |
| C-7 | PWA: vista Alertas | `alerts/page.tsx` | Lista riesgo, colores urgencia, push prompt |
| C-8 | Tests API forecast | `tests/test_forecast.py` | Schema, auth, cache, empty state |
| C-9 | Tests API alerts | `tests/test_alerts.py` | Schema, auth, urgency filter |
| C-10 | Evidencia V6 forecast | `v6_forecast_match.md` | PWA forecast = SQL forecast |

### V-checks F4-C

| ID | Verificación | Pass criterion |
|----|-------------|----------------|
| V-A1 | Forecast endpoint funciona | `GET /forecast/{sku}` → 200 con predicciones |
| V-A2 | Forecast 404 | `GET /forecast/INEXISTENTE` → 404 |
| V-A3 | Alerts endpoint funciona | `GET /alerts/stockout` → lista ordenada por urgencia |
| V-A4 | PWA forecast renderiza | Gráfico recharts sin errores |
| V-A5 | Push end-to-end | Alerta alta → push recibido en PWA |
| V-A6 | V6 forecast match | PWA forecast = SQL forecast |

---

## 7 · Archivos a crear

```
docs/plan-f4.md                              ← este archivo
docs/decisions/0016-stack-f4.md              ← ADR
notebooks/gold/15_feature_store_sku.py
notebooks/gold/16_forecast_baseline_sku.py
notebooks/gold/17_mlflow_register_baseline.py
notebooks/gold/20_forecast_prophet.py
notebooks/gold/21_forecast_lightgbm.py
notebooks/gold/22_classifier_stockout.py
notebooks/silver/15_app_push_subscriptions.sql
infra/run_backtest.py
tests/gold/test_feature_store.py
tests/gold/test_forecasts.py
motoship-app/api/src/motoship_api/forecast/repo.py
motoship-app/api/src/motoship_api/forecast/schemas.py
motoship-app/api/src/motoship_api/forecast/router.py
motoship-app/api/src/motoship_api/alerts/repo.py
motoship-app/api/src/motoship_api/alerts/schemas.py
motoship-app/api/src/motoship_api/alerts/router.py
motoship-app/api/src/motoship_api/push/sender.py
motoship-app/web/app/(authenticated)/forecast/page.tsx
motoship-app/web/app/(authenticated)/alerts/page.tsx
motoship-app/api/tests/test_forecast.py
motoship-app/api/tests/test_alerts.py
```

---

## 8 · Stack técnico

| Componente | Tecnología | Notas |
|------------|-----------|-------|
| Forecasting | Prophet | Para top-100 SKUs |
| ML general | LightGBM | Para cola larga + classifier |
| HPO | Optuna | Bayesiano, integrado con MLflow |
| ML tracking | MLflow | Remote tracking en Databricks workspace |
| Features | Delta Lake (gold tables) | Refresh por workflow |
| Serving | Pre-computed gold + FastAPI | Sin inferencia real-time |
| Push | pywebpush | VAPID keys + service worker existente |
| Charts | Recharts | Ya instalado en PWA |
| Tests | pytest + sqlparse | Patrón existente |

---

## 9 · Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|----|--------|-------|---------|------------|
| R-A4 | Compute Free Edition insuficiente | Media | Alto | Training local en Mac. Si Prophet no cabe: reducir top-100 a top-50 |
| R-F4-1 | MAPE Prophet no supera baseline | Media | Alto | Usar LightGBM como principal; Prophet como benchmark |
| R-F4-2 | Datos insuficientes para estacionalidad anual | Alta | Medio | Solo 29 meses; usar features mes/dia_semana como proxy |
| R-F4-3 | Clasificador con muchos falsos positivos | Media | Medio | Umbral ajustable; filtrar urgencia alta en push |
| R-F4-4 | pywebpush requiere VAPID keys | Baja | Bajo | Generar con `pyvapid` en setup inicial |
| R-F4-5 | Prophet installation en Mac falla | Baja | Medio | Usar Docker o conda; alternativa: statsforecast |
| R-F4-6 | PC Windows offline > 48h = datos stale | Media | Medio | Mitigado con F1.9 (dump cada 30min, catch-up). Documentar predicciones como "stale" si PC offline. F4 NO necesita MySQL en tiempo real. |

---

## 10 · Orden de ejecución

```
F4-A (Dev A, ~6-8h)
  feature_store + baseline + MLflow
     │
     ▼
F4-B (Dev A, ~8-10h)
  Prophet + LightGBM + classifier
     │
     ▼
F4-C (Dev T, ~6-8h)
  API + PWA + push
```

**Total:** 20-26 h, 3-4 sesiones.

---

## 11 · Preguntas antes de arrancar

1. ¿MLflow tracking ya está configurado en el workspace Databricks?
2. ¿Las VAPID keys para push ya existen?
3. ¿Se quiere Prophet en local o en Databricks?
4. ¿Horizonte de predicción por defecto: solo 7 días o 7/14/30?

---

## 12 · Próximo paso del revisor

1. Aprobar plan F4 y ADR-0016.
2. Dev A ejecuta F4-A (feature store + baseline).
3. Revisor audita V-FS1 a V-FS4.
4. Dev A ejecuta F4-B (modelos + classifier).
5. Revisor audita V-M1 a V-M6.
6. Dev T ejecuta F4-C (API + PWA + push).
7. Revisor audita V-A1 a V-A6.
8. Cierre F4 → GO a F5 o F6.
