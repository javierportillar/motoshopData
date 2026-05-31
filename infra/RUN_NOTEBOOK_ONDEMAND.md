# Run Notebook On-Demand · CLI

> Ejecutá UN notebook del workflow MotoShop sin disparar todo el job.
> Útil para re-ejecución de marts puntuales, testing, validación, debugging.

---

## Para qué sirve

El `motoshop_full_workflow` corre 31 tasks secuenciales cada noche a las 19:00 COL. Eso es perfecto para producción regular, pero **mal para casos puntuales**:

| Situación | Sin este script | Con este script |
|-----------|-----------------|-----------------|
| `gold_drift` falló, querés re-correr solo eso | "Run now" todo el workflow (30+ min) o usar "Repair Run" en UI Databricks | `python infra/run_notebook_ondemand.py --task gold_drift` (~30s + ejecución del notebook) |
| Cambiaste 1 mart y querés probarlo | Disparar workflow completo y esperar tasks anteriores | Ejecutar solo ese mart |
| Querés re-poblar `mart_inventario_actual` por algo puntual | Idem | `--task gold_inventario` |
| Probando un cambio en un notebook | Workflow completo cada vez | On-demand del notebook |

NO modifica el workflow productivo. Crea un job ephemeral con UNA sola task.

---

## Uso básico

### Listar tasks disponibles

```bash
python infra/run_notebook_ondemand.py --list
```

Output:
```
=== BRONZE (1 tasks) ===
  bronze_ingest                       →  bronze/02_ingest_all_bronze

=== SILVER (14 tasks) ===
  silver_dim_producto                 →  silver/01_dim_producto
  silver_dim_bodega                   →  silver/02_dim_bodega
  ...

=== GOLD (16 tasks) ===
  gold_ventas                         →  gold/10_mart_ventas_diarias_sku
  gold_drift                          →  gold/25_drift_monitor
  gold_rotacion_promedio              →  gold/18_mart_rotacion_promedio
  ...
```

### Ejecutar un task específico (esperando finalización)

```bash
python infra/run_notebook_ondemand.py --task gold_drift
```

Comportamiento por defecto: espera hasta 600s (10 min) y reporta status.

Output:
```
🚀 Submitting on-demand notebook run:
   User:     javier@motoshop.uy
   Notebook: /Workspace/Users/javier@motoshop.uy/motoshopData/notebooks/gold/25_drift_monitor
   Warehouse: 43bc044eaef4cca4
   Run name: ondemand_gold_drift_1735603200

✅ Run submitted. run_id=12345678
   Ver en UI: https://dbc-xxx.cloud.databricks.com/jobs/runs/12345678

⏳ Esperando finalización (timeout 600s)...
  [10s] state=PENDING result=None
  [25s] state=RUNNING result=None
  [60s] state=TERMINATED result=SUCCESS

✅ Run 12345678 COMPLETADO exitosamente.
```

### Ejecutar sin esperar (fire-and-forget)

```bash
python infra/run_notebook_ondemand.py --task gold_drift --no-wait
```

Útil si querés disparar y seguir trabajando. Imprime `run_id` y URL para ver en UI Databricks.

### Especificar timeout custom

```bash
python infra/run_notebook_ondemand.py --task silver_fact_ventas --wait 1800
```

(Algunos jobs como `silver_fact_ventas` pueden tardar varios minutos.)

### Ejecutar un notebook por path (no en TASK_REGISTRY)

```bash
python infra/run_notebook_ondemand.py --notebook gold/18_mart_rotacion_promedio
```

Útil para notebooks experimentales o nuevos antes de agregarlos al workflow oficial.

---

## Pre-requisitos

### 1. Variables de entorno

`DATABRICKS_HOST` y `DATABRICKS_TOKEN` en el entorno o `.env`:

```bash
# Ya están en motoshop-app/api/.env (el script los carga automáticamente)
DATABRICKS_HOST=https://dbc-xxx.cloud.databricks.com
DATABRICKS_TOKEN=dapi...
```

### 2. Dependencias Python

```bash
pip install databricks-sdk python-dotenv
```

(Ya están en `pyproject.toml` del API.)

### 3. Notebooks deben estar sincronizados con Databricks Workspace

El script asume que los notebooks ya están en `/Workspace/Users/<user>/motoshopData/notebooks/`. Si modificaste un notebook localmente y querés ejecutarlo on-demand, primero sincronizar:

```bash
python infra/upload_all_notebooks.py
```

O esperar al auto-pull si está habilitado (Windows).

---

## Casos de uso típicos

### Caso 1: F7-E-FIX1 — re-correr solo los 3 jobs que fallaron

```bash
# Diagnóstico previo: DROP TABLES en SQL Editor de Databricks

# Re-ejecutar los 3 tasks en orden de dependencia
python infra/run_notebook_ondemand.py --task gold_rotacion_promedio
python infra/run_notebook_ondemand.py --task gold_abc_xyz  # depende de rotacion
python infra/run_notebook_ondemand.py --task gold_drift
```

Mucho más rápido que `Run now` del workflow completo (que correría 28 tasks innecesarios).

### Caso 2: Reprocesar inventario tras backup MySQL

```bash
# Re-correr solo la cadena de inventario
python infra/run_notebook_ondemand.py --task silver_fact_inventario
python infra/run_notebook_ondemand.py --task gold_inventario
```

### Caso 3: Testing de nuevo notebook

```bash
# Tenés un cambio en gold/25_drift_monitor.py
# Sin pushear, sin afectar workflow productivo:
python infra/upload_all_notebooks.py  # sync
python infra/run_notebook_ondemand.py --task gold_drift  # test
# Si pasa, commit + push como normal
```

### Caso 4: Snapshot manual fuera de schedule

```bash
# Forzar un snapshot diario de alertas ahora
python infra/run_notebook_ondemand.py --task gold_snapshot_alertas
```

### Caso 5: Análisis ad-hoc

```bash
# Volver a generar ABC × XYZ con la data actualizada
python infra/run_notebook_ondemand.py --task gold_abc_xyz
```

---

## Comparación con métodos alternativos

| Método | Pros | Contras |
|--------|------|---------|
| **Este script (CLI)** | Reproducible, scriptable, rápido (~30s overhead) | Requiere CLI access |
| **Databricks UI "Run now" del workflow** | Visual, fácil | Corre TODO el workflow (~30 min) |
| **Databricks UI "Repair Run"** | Sigue el grafo, solo corre lo que falló | Limitado al último Run, solo tasks fallidas |
| **SQL Editor directo (paste código)** | Útil para queries puntuales | No corre notebooks completos con MAGIC commands |
| **Job individual por task** | Cada task tiene su botón Run | 31 jobs distintos a mantener (explosión) |

El script combina lo mejor: reproducibilidad de scripts + granularidad de UI.

---

## Limitaciones

### 1. NO ejecuta dependencias

Si ejecutás `gold_drift` y la tabla `forecast_baseline_sku` no está actualizada (porque `gold_baseline` no corrió), el resultado puede ser incorrecto. **Es responsabilidad tuya verificar el estado de las upstream.**

Ejemplo:
```bash
# Si no estás seguro del estado de upstream, ejecutá la cadena completa:
python infra/run_notebook_ondemand.py --task gold_baseline
python infra/run_notebook_ondemand.py --task gold_drift
```

### 2. Comparte el mismo SQL Warehouse que el workflow

Si el workflow nocturno está corriendo a las 19:00 y tirás `--task gold_drift` en ese momento, los 2 compiten por el warehouse. Esperar 5-10 min después de la corrida nocturna para evitar.

### 3. Costos

Cada `--task` consume cómputo del SQL Warehouse. Para Databricks Free es gratis (Serverless Starter), pero en V2 con Premium podrías acumular costo si lo usás muchas veces seguidas.

### 4. NO modifica el schedule del workflow

El workflow nocturno sigue corriendo a las 19:00 sin saber que ya disparaste ese task manual. Si el task ya pasó on-demand, va a volver a correr de noche (normal — no hay conflicto, las tablas son idempotentes).

---

## Troubleshooting

### `ERROR: task 'X' no existe en TASK_REGISTRY`

Lista los tasks disponibles:
```bash
python infra/run_notebook_ondemand.py --list
```

Si el task realmente existe en el workflow pero no en el script, agregar al `TASK_REGISTRY` dict (sync con `infra/create_full_workflow.py`).

### `ERROR: DATABRICKS_HOST y DATABRICKS_TOKEN no están en el entorno`

Verificar `.env`:
```bash
cat motoshop-app/api/.env | grep DATABRICKS
```

O exportar manual:
```bash
export DATABRICKS_HOST=https://dbc-xxx.cloud.databricks.com
export DATABRICKS_TOKEN=dapi...
```

### `RuntimeError: submit() devolvió run_id None`

Token Databricks expirado o sin permisos. Regenerar PAT en Databricks UI → User Settings → Developer → Access Tokens.

### Run queda en `PENDING` mucho tiempo

El SQL Warehouse está starting (cold start ~30-60s) o paused. Esperar y reintentar.

### Timeout antes que termine

```bash
# Aumentar timeout
python infra/run_notebook_ondemand.py --task X --wait 1800
```

O dejar fire-and-forget:
```bash
python infra/run_notebook_ondemand.py --task X --no-wait
# Después chequear en UI: https://dbc-xxx.cloud.databricks.com/jobs/runs/<id>
```

---

## Mantenimiento del TASK_REGISTRY

`TASK_REGISTRY` en `infra/run_notebook_ondemand.py` debe sincronizarse con `TASKS` en `infra/create_full_workflow.py` cuando se agregan tasks nuevas al workflow.

Convención: usar EXACTAMENTE el mismo `task_key` que en el workflow.

Si se agrega un task nuevo:
1. Editar `TASKS` en `create_full_workflow.py`
2. Editar `TASK_REGISTRY` en `run_notebook_ondemand.py` (mismo task_key + path)
3. Commit + push
4. (Si auto-pull está activo en Windows, se sincroniza solo)

---

## Roadmap V2

En V2 producción:

- **GitHub Actions con workflow_dispatch** que ejecute on-demand desde la UI de GitHub
- **Self-service para usuarios no-técnicos** (UI propia en la PWA con botón "Re-correr task X" para roles `admin`)
- **Audit trail de ejecuciones on-demand** en `app_audit_log`
- **Locking distribuido** para evitar correr el mismo task en paralelo

Por ahora (V1), CLI es suficiente.
