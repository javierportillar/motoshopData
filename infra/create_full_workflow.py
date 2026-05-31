"""
Create/update the unified Databricks Workflow for F6-A.

Merges the two-pipeline architecture into a SINGLE managed workflow
that runs sequentially every day at 19:00 COL (after the last dump):

  1. bronze_ingest
  2. silver (dims → facts → quality → validate)
  3. gold marts (10–14) → snapshots ABC/dormidos (30/31) → feature store (15) →
     archive forecasts (33) → baseline (16) → classifier (22) →
     snapshot alertas (32) → quality (20) → validate (30)
  4. drift monitor (25) — final task, optional

This replaces the previous two-job setup (motoshop_bronze_silver + motoshop_gold_workflow).
The Windows Task Scheduler still handles dump_to_cloud.py (bronze landing),
but ALL PySpark transformations are now managed in Databricks.

Schedule: cron 0 0 19 * * ?  (19:00 COL, Monday–Sunday)

Usage:
    export DATABRICKS_HOST=https://dbc-e311b140-dab8.cloud.databricks.com
    export DATABRICKS_TOKEN=<token>
    python infra/create_full_workflow.py

Requires: pip install databricks-sdk
"""

from __future__ import annotations

import os
import pathlib
import sys

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service import compute, jobs
except ImportError:
    print("databricks-sdk no instalado. Ejecuta: pip install databricks-sdk")
    sys.exit(1)

# ─── Cargar .env manualmente desde la raíz del repo ────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ─── Config common ──────────────────────────────────────────────────────

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

NOTEBOOK_PATH = "/Repos/javierportillar/motoshopData/notebooks"
NOTIFICATION_EMAIL = "javierandres.008@hotmail.com"

# ─── Task definitions ─────────────────────────────────────────────────

FULL_TASKS: list[tuple[str, str, list[str]]] = [
    # ── Bronze ───────────────────────────────────────────────────────
    ("bronze_ingest", "bronze/02_ingest_all_bronze", []),

    # ── Silver dims ─────────────────────────────────────────────────
    ("silver_dim_producto", "silver/01_dim_producto", ["bronze_ingest"]),
    ("silver_dim_bodega", "silver/02_dim_bodega", ["bronze_ingest"]),
    ("silver_dim_tercero", "silver/03_dim_tercero", ["bronze_ingest"]),
    ("silver_dim_sucursal", "silver/04_dim_sucursal", ["bronze_ingest"]),
    ("silver_dim_formapago", "silver/05_dim_formapago", ["bronze_ingest"]),
    ("silver_dim_tiempo", "silver/06_dim_tiempo", ["bronze_ingest"]),

    # ── Silver facts ─────────────────────────────────────────────────
    ("silver_fact_ventas", "silver/10_fact_ventas", ["bronze_ingest"]),
    ("silver_fact_ventas_detalle", "silver/11_fact_ventas_detalle",
     ["bronze_ingest", "silver_fact_ventas"]),
    ("silver_fact_compras", "silver/12_fact_compras", ["bronze_ingest"]),
    ("silver_fact_compras_detalle", "silver/13_fact_compras_detalle",
     ["bronze_ingest", "silver_fact_compras"]),
    ("silver_fact_inventario", "silver/14_fact_inventario", ["bronze_ingest"]),

    # ── Silver quality + validate ────────────────────────────────────
    ("silver_quality", "silver/20_quality_run", [
        "silver_dim_producto", "silver_dim_bodega", "silver_dim_tercero",
        "silver_dim_sucursal", "silver_dim_formapago", "silver_dim_tiempo",
        "silver_fact_ventas", "silver_fact_ventas_detalle",
        "silver_fact_compras", "silver_fact_compras_detalle", "silver_fact_inventario",
    ]),
    ("silver_validate", "silver/30_validate_silver", ["silver_quality"]),

    # ── Gold marts (dependen de silver_validate) ──────────────────────
    ("gold_ventas", "gold/10_mart_ventas_diarias_sku", ["silver_validate"]),
    ("gold_inventario", "gold/11_mart_inventario_actual", ["silver_validate"]),
    ("gold_abc", "gold/12_mart_rotacion_abc", ["silver_validate"]),
    ("gold_cohortes", "gold/13_mart_cohortes_clientes", ["silver_validate"]),
    ("gold_dormidos", "gold/14_mart_productos_dormidos", ["silver_validate"]),

    # ── Gold snapshots · Balde B (después de marts originales) ────────
    ("gold_snapshot_abc", "gold/30_snapshot_abc_mensual", ["gold_abc"]),
    ("gold_snapshot_dormidos", "gold/31_snapshot_dormidos_mensual", ["gold_dormidos"]),

    # ── Feature store + archive + baseline + classifier ────────────────
    ("gold_feature_store", "gold/15_feature_store_sku",
     ["gold_ventas", "gold_inventario"]),
    # ── Balde B · Archive forecast ANTES de overwrite ──────────────────
    ("gold_archive_forecasts", "gold/33_archive_forecasts", ["gold_feature_store"]),
    ("gold_baseline", "gold/16_forecast_baseline_sku",
     ["gold_feature_store", "gold_archive_forecasts"]),
    ("gold_classifier", "gold/22_classifier_stockout",
     ["gold_feature_store"]),

    # ── Gold snapshot alertas diario (después de classifier) ───────────
    ("gold_snapshot_alertas", "gold/32_snapshot_alertas_diario", ["gold_classifier"]),

    # ── Gold quality + validate ───────────────────────────────────────
    ("gold_quality", "gold/20_quality_gold", [
        "gold_ventas", "gold_inventario", "gold_abc", "gold_cohortes", "gold_dormidos",
    ]),
    ("gold_validate", "gold/30_validate_gold", ["gold_quality"]),

    # ── Drift monitor (final task) ────────────────────────────────────
    ("gold_drift", "gold/25_drift_monitor", ["gold_validate"]),
]

# ─── Helpers ─────────────────────────────────────────────────────────────


def build_tasks(task_defs: list[tuple[str, str, list[str]]]) -> list[jobs.Task]:
    result = []
    for key, nb, deps in task_defs:
        nb_path = f"{NOTEBOOK_PATH}/{nb}.py"
        t = jobs.Task(
            task_key=key,
            notebook_task=jobs.NotebookTask(notebook_path=nb_path),
            timeout_seconds=3600,
            depends_on=[jobs.TaskDependency(task_key=d) for d in deps] if deps else None,
        )
        result.append(t)
    return result


def delete_existing_jobs(w: WorkspaceClient, names: list[str]) -> None:
    """Elimina jobs viejos para evitar duplicados."""
    for j in w.jobs.list():
        if j.settings and j.settings.name in names:
            print(f"  Eliminando job anterior: '{j.settings.name}' (ID {j.job_id})")
            w.jobs.delete(job_id=j.job_id)


def create_or_update_job(
    w: WorkspaceClient,
    job_name: str,
    task_defs: list[tuple[str, str, list[str]]],
    schedule: jobs.CronSchedule,
) -> int | None:
    existing_job_id = None
    for j in w.jobs.list(name=job_name):
        if j.settings and j.settings.name == job_name:
            existing_job_id = j.job_id
            print(f"  → Job existente encontrado: ID {existing_job_id}")
            break

    env_spec = jobs.JobEnvironment(
        environment_key="Default",
        spec=compute.Environment(environment_version="5"),
    )

    settings = jobs.JobSettings(
        name=job_name,
        tasks=build_tasks(task_defs),
        schedule=schedule,
        email_notifications=jobs.JobEmailNotifications(
            on_failure=[NOTIFICATION_EMAIL]
        ),
        max_concurrent_runs=1,
        environments=[env_spec],
    )

    if existing_job_id:
        print(f"  Actualizando job {existing_job_id}...")
        w.jobs.reset(job_id=existing_job_id, new_settings=settings)
        print(f"  ✅ Job {existing_job_id} actualizado")
        return existing_job_id
    else:
        print(f"  Creando nuevo job...")
        created = w.jobs.create(
            name=job_name,
            tasks=settings.tasks,
            schedule=settings.schedule,
            email_notifications=settings.email_notifications,
            max_concurrent_runs=settings.max_concurrent_runs,
            environments=settings.environments,
        )
        print(f"  ✅ Job creado: ID {created.job_id}")
        return created.job_id


# ─── Main ─────────────────────────────────────────────────────────────────


def main():
    if not DATABRICKS_HOST:
        print("❌ DATABRICKS_HOST no configurado.")
        sys.exit(1)
    if not DATABRICKS_TOKEN:
        print("❌ DATABRICKS_TOKEN no configurado.")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print("=" * 60)

    # Conectar
    print("\n1. Conectando a Databricks...")
    try:
        w = WorkspaceClient(host=DATABRICKS_HOST, token=DATABRICKS_TOKEN)
        w.current_user.me()
        print("  ✅ Conexion exitosa")
    except Exception as e:
        print(f"  ❌ Error de conexion: {e}")
        sys.exit(1)

    # ── Paso 2: Eliminar jobs viejos ──
    print(f"\n2. Eliminando jobs anteriores (motoshop_bronze_silver + motoshop_gold_workflow)...")
    delete_existing_jobs(w, ["motoshop_bronze_silver", "motoshop_gold_workflow"])

    # ── Paso 3: Crear/actualizar el unified workflow ──
    print(f"\n═══ FULL WORKFLOW: motoshop_full_workflow ({len(FULL_TASKS)} tasks) ═══")
    full_schedule = jobs.CronSchedule(
        quartz_cron_expression="0 0 19 * * ?",
        timezone_id="America/Bogota",
        pause_status=jobs.PauseStatus.PAUSED,  # PAUSED para primera corrida manual
    )

    full_id = create_or_update_job(w, "motoshop_full_workflow", FULL_TASKS, full_schedule)

    # ── Resumen ──
    print(f"\n{'=' * 60}")
    print(f"  WORKFLOW UNIFICADO CONFIGURADO")
    print(f"{'=' * 60}")
    print(f"  Job:     motoshop_full_workflow (ID: {full_id})")
    print(f"  Tasks:   {len(FULL_TASKS)} (bronze → silver → gold → drift)")
    print(f"  Schedule: 0 0 19 * * ? (19:00 COL) — PAUSED")
    print(f"  Notificaciones: {NOTIFICATION_EMAIL}")
    print(f"\n  📌 Pasos siguientes:")
    print(f"     1. Subir notebooks: python infra/upload_all_notebooks.py")
    print(f"     2. Correr manual:   Ir a Databricks → Workflows → {full_id} → Run Now")
    print(f"     3. Verificar éxito → UNPAUSE desde la UI o API")
    print(f"     4. Ver R7: consultar system.workflows.runs para confirmar ≥7 corridas")
    print(f"     5. Eliminar jobs viejos (motoshop_bronze_silver, motoshop_gold_workflow)")
    print(f"        si no se eliminaron automáticamente")


if __name__ == "__main__":
    main()
