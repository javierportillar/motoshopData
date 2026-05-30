# Lecciones aprendidas — Sprint F4 (Forecasting y Clasificador)

> Sprint completo: F4-A (Pipeline) → F4-B (Forecast + Classifier) → F4-C (Dashboard) → F4-FIX1 (Auditoría)
> Fecha: 2026-05-30

---

## Resumen ejecutivo

El sprint F4 implementó un pipeline completo de forecasting y clasificador de quiebre de stock. La revisión FIX1 con contexto independiente descubrió que **las métricas reportadas eran engañosas por errores metodológicos**, no porque los modelos funcionaran mal. Al corregir la metodología, las métricas cayeron de forma dramática pero honesta.

| Modelo | Antes (F4) | Después (FIX1) | Diferencia |
|--------|-----------|----------------|------------|
| Prophet MAPE | 3540% | 1325% | Data leak + métrica incorrecta |
| Prophet WAPE | — | 864% | No comparable (nueva métrica) |
| LightGBM MAPE | 347% | 101% | Filtro SKU elegibles |
| LightGBM WAPE | — | 57% | No comparable (nueva métrica) |
| Classifier F1 | 0.99 | 0.54 | Target leakage corregido |

---

## Lecciones

### 1. MAPE miente en demanda intermitente

**Problema**: MAPE divide el error absoluto por cada valor real individual. Cuando `actual = 1` y `predicción = 36`, MAPE = 3500% aunque el error absoluto sea solo 35 unidades.

**Solución**: WAPE (Weighted Absolute Percentage Error) suma todos los errores y divide por la suma de todos los reales. Una predicción mala no domina el agregado.

**Regla**: Para demanda intermitente (>50% de días con demanda = 0), usar WAPE. MAPE solo tiene sentido si todos los valores reales son > 0 y no hay valores atípicos pequeños.

### 2. No evaluar modelos en SKUs que no deberían tener modelo

**Problema**: Se evaluó Prophet sobre TODOS los SKUs, incluyendo aquellos con 1-3 ventas en 6 meses. Con 1-3 puntos históricos, cualquier modelo de series temporales falla.

**Solución**: Filtro de elegibilidad: ≥ 90 días de historia Y ≥ 30 ventas totales. Solo 31 de 4,392 SKUs (0.7%) pasan el filtro.

**Regla**: Antes de evaluar un modelo, preguntar: "¿Este SKU tiene suficientes datos para que el modelo funcione?" Si la respuesta es no, el SKU recibe baseline.

### 3. Target leakage mata la evaluación del clasificador

**Problema**: El target del clasificador se definía como `stock_actual < media_movil_7d * 0.5` y el feature set incluía `stock_actual` y `media_movil_7d`. El modelo "aprendió" una regla aritmética de primer grado → F1 = 0.99.

**Solución**: Excluir del feature set cualquier variable que se use para definir el target. Sacar `stock_actual` hizo que F1 cayera a 0.54, pero ahora el modelo aprende patrones reales (el feature más importante pasó a ser `dia_semana`).

**Regla de oro**: Si features + target pueden expresar una relación determinística (una cuenta matemática exacta), el modelo no está aprendiendo — está memorizando una fórmula.

### 4. Split aleatorio en datos temporales es data leakage

**Problema**: El clasificador usaba `train_test_split(stratify=y)` que mezcla filas de las mismas fechas en train y test. El modelo veía patrones del mismo período que después evaluaba.

**Solución**: Split temporal estricto. Train ≤ fecha_corte, Test > fecha_corte. Verificar que no haya fechas en común entre train y test.

**Regla**: En problemas de series temporales o con dependencia temporal, el split SIEMPRE es cronológico. El random split solo aplica cuando las filas son i.i.d. (independientes e idénticamente distribuidas).

### 5. Prophet no sirve para este dataset

**Resultado**: WAPE 864% en los 31 SKUs elegibles. Prophet gana solo 81 de 4,436 predicciones (1.8%). La estacionalidad semanal que Prophet busca no existe en datos de motocicletas con demanda intermitente.

**Lección**: No todos los modelos sirven para todos los problemas. Prophet está diseñado para series con estacionalidad fuerte y regular (tráfico web, ventas diarias de supermercado). La demanda de repuestos de moto es demasiado intermitente y esporádica.

**Recomendación**: Remover Prophet del pipeline en F5. LightGBM forecasting es marginalmente mejor (WAPE 57%) pero no suficiente para justificar su complejidad frente a baseline (WAPE 45%).

### 6. Las métricas honestas son mejores que las métricas lindas

**Falso**: "F1 = 0.99, MAPE = 3540%, pero Prophet anda peor que baseline".
**Verdad**: "F1 = 0.54, WAPE = 45-864%, baseline gana 97.9% de las predicciones".

La segunda versión es fea pero útil: sabemos que Prophet no sirve, que el clasificador necesita más trabajo, y que baseline es la opción correcta por ahora. La primera versión es linda pero peligrosa: sugiere que los modelos ML funcionan cuando no es así.

---

### 7. Los notebooks en Databricks se ejecutan desde el Workspace, no desde el repo

**Problema**: El job `motoshop_gold_workflow` falló porque los notebooks silver/bronze **nunca se subieron** al Workspace Databricks. Los archivos `.py` estaban en el repo de GitHub, pero Databricks Jobs ejecuta notebooks desde `Repos/` o desde import directo. El error `Unable to access the notebook… does not exist` aparecía sin que el código tuviera un bug.

**Solución**: `infra/upload_all_notebooks.py` sube los 35 notebooks (bronze PYTHON, silver/gold SQL) al Workspace. También se agregó un skip-check al bronze notebook para no re-procesar fechas ya ingeridas.

**Regla operativa**: después de **cualquier cambio** en `notebooks/`:

```bash
python3 infra/upload_all_notebooks.py
```

Si además cambió la configuración de jobs (schedules, tareas):

```bash
python3 infra/create_gold_workflow.py
```

Luego commit + push normal.

**Automatización futura (F5+)**: un GitHub Action que corra `upload_all_notebooks.py` al hacer push a `main`, o conectar el repo al Workspace Databricks via Repos (la UI no siempre muestra un Pull claro, pero el agente puede sincronizar por API).

### 8. Los jobs Databricks no soportan múltiples cron schedules

**Problema**: Queríamos un solo job que corra bronze_silver cada hora **y** gold una vez al día. Databricks Jobs solo permite **un** schedule por job.

**Solución**: Dividir en 2 jobs independientes:
- `motoshop_bronze_silver` (14 tasks) → cron `0 0 9-18 * * ?` (cada hora)
- `motoshop_gold_workflow` (7 tasks) → cron `0 0 19 * * ?` (19:00)

El bronze notebook además auto-detecta la última partición disponible (`MAX(ingest_date)` del Volume) para no hardcodear la fecha de ingesta, y salta si la fecha ya fue procesada.

---

## Acciones

| Prioridad | Acción | Dueño |
|-----------|--------|-------|
| 🔴 | Remover Prophet del pipeline (F5) | F5 Team |
| 🟡 | Classifier: target real (stock=0 AND demanda>0) + más features | F5 Team |
| 🟡 | Walk-forward validation en lugar de split fijo | F6 |
| 🟢 | Monitorear WAPE en producción, no MAPE | Ops |
| 🟢 | Agregar alerta cuando cobertura de SKUs elegibles < 0.5% | Ops |
| 🟢 | Documentar upload manual a Databricks como paso obligatorio tras cambios de notebooks | Ops |
