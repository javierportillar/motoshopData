# ADR-0021: Migración a Databricks Workflow gestionado

**Status**: Proposed
**Date**: 2026-05-30
**Deciders**: Revisor + Dev A + Sprint F6
**Sprint**: F6-A · Hardening operativo

---

## Context

Hasta F5, el pipeline de datos se ejecutaba así:

1. **Windows Task Scheduler** dispara `dump_to_cloud.py` cada 30 min (07:00–19:30 COL) → MySQL dump → Parquet → UC Volume.
2. **Databricks Workflow `motoshop_bronze_silver`** corre cada hora (9–18 COL) transformando bronze → silver.
3. **Databricks Workflow `motoshop_gold_workflow`** corre a las 19:00 COL transformando silver → gold marts + baseline + classifier.

Este esquema funcionó durante F1–F5 con dos jobs separados porque silver necesitaba actualizarse varias veces al día (cada dump podía traer datos nuevos). Pero en F6:

- El dump de Windows ahora corre solo en ventana 07:00–19:30, y el último dump es a las 19:00.
- Silver ya no necesita múltiples corridas diarias — una sola corrida post-último-dump es suficiente.
- La deuda **R4** («Workflow Databricks postergado — corre Task Scheduler») exige migrar todo el orchestrión a Databricks.

### Decisión técnica

Unificar los dos jobs en un solo **`motoshop_full_workflow`** que ejecuta todo el pipeline en secuencia: bronze → silver (dims + facts + quality + validate) → gold (marts + feature store + baseline + classifier + quality + validate) → drift monitor.

---

## Decision · Workflow unificado gestionado en Databricks

**Decisión**: migrar de dos jobs separados (`motoshop_bronze_silver` + `motoshop_gold_workflow`) a un solo job `motoshop_full_workflow` con 25 tareas secuenciales, cron `0 0 19 * * ?` (19:00 COL, hora local Colombia).

**Implementación**:
- `infra/create_full_workflow.py` reemplaza a `infra/create_gold_workflow.py`.
- El script se conecta a Databricks SDK, elimina los jobs viejos, y crea el nuevo job unificado.
- El job arranca PAUSED para la primera corrida manual de validación, luego se UNPAUSEs.
- La tarea final `gold_drift` (notebook 25_drift_monitor.py) monitorea degradación del baseline semanalmente.

**Alternativa descartada — mantener dos jobs separados**:
  - Dos schedules independientes que pueden desincronizarse.
  - Si silver corre pero gold falla, silver vuelve a correr al día siguiente con datos que gold nunca procesó.
  - Más tareas en la UI de Databricks Workflows, más cognitive load.
  - **Motivo de descarte**: F6 es la última fase — el pipeline debe ser lo más simple posible para mantenimiento post-curso.

**Alternativa descartada — Apache Airflow / orchestrión externo**:
  - Agregar Airflow, Prefect o Dagster como orchestrión.
  - **Motivo de descarte**: Databricks Workflow es gratuito en Free Edition y ya está disponible. Agregar Airflow agrega un punto de fallo, una VM más, y costo de mantenimiento. Para el volumen actual (< 30 tablas, 1 pipeline diario) es overkill.

---

## Consequences

### Positive
- Pipeline completo en un solo lugar — debugging, logging, retry desde la UI de Databricks.
- Elimina dependencia del Windows Task Scheduler para la transformación (R4 cerrada).
- Reduce el número de jobs gestionados de 2 a 1.
- La tarea de drift monitoring se ejecuta automáticamente después de gold validate.
- Windows solo necesita el dump → UC Volume; todo lo demás es Databricks managed.

### Negative
- Si el pipeline completo falla en la mitad, no hay datos nuevos hasta el día siguiente (no hay re-ejecución parcial automática).
- El cron 19:00 COL es fijo — si cambia la ventana de dump de Windows, hay que actualizar el schedule.
- 25 tareas secuenciales pueden tomar 30–60 minutos en Free Edition (recursos limitados).

### Technical debt creada
- No hay alerta automática si la corrida completa falla (solo notificación por email configurada).
- No hay retry inteligente — si una tarea intermedia falla, hay que re-ejecutar manualmente desde esa tarea.
- Si en F7+ se necesitan múltiples corridas diarias de silver, habrá que revertir a dos jobs o implementar triggering por evento.

---

## Related artifacts

- [create_full_workflow.py](../../infra/create_full_workflow.py) — script de creación del workflow
- [create_gold_workflow.py](../../infra/create_gold_workflow.py) — script anterior (reemplazado)
- [Plan F6 §A2](../plan-f6.md#sprint-f6-a--dev-a--hardening-operativo-4-5-h) — especificación del paso A2
- [R4](../contexto-proyecto.md#10--riesgos-vivos-y-deudas-conscientes) — deuda cerrada por esta decisión
- [25_drift_monitor.py](../../notebooks/gold/25_drift_monitor.py) — tarea final del workflow
