"""
Create/update Databricks Job for gold workflow using databricks-sdk.

Schedule: cron `0 30 2 * * ?` (02:30 COL every day)
Tasks: bronze ingestion -> silver notebooks -> gold/10..14 -> gold/20 -> gold/30

Uso:
    export DATABRICKS_HOST=https://dbc-e311b140-dab8.cloud.databricks.com
    export DATABRICKS_TOKEN=dapi...
    python infra/create_gold_workflow.py

Requisito: pip install databricks-sdk
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

# --- Configuracion ----------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

NOTEBOOK_PATH = "/Repos/javierportillar/motoshopData/notebooks"
JOB_NAME = "motoshop_gold_workflow"
NOTIFICATION_EMAIL = "motoshop@example.com"

TASKS = [
    ("bronze", "bronze/02_ingest_all_bronze", []),
    ("silver_dim_producto", "silver/01_dim_producto", ["bronze"]),
    ("silver_dim_bodega", "silver/02_dim_bodega", ["bronze"]),
    ("silver_dim_tercero", "silver/03_dim_tercero", ["bronze"]),
    ("silver_dim_sucursal", "silver/04_dim_sucursal", ["bronze"]),
    ("silver_dim_formapago", "silver/05_dim_formapago", ["bronze"]),
    ("silver_dim_tiempo", "silver/06_dim_tiempo", ["bronze"]),
    ("silver_fact_ventas", "silver/10_fact_ventas", ["bronze"]),
    ("silver_fact_ventas_detalle", "silver/11_fact_ventas_detalle", ["bronze", "silver_fact_ventas"]),
    ("silver_fact_compras", "silver/12_fact_compras", ["bronze"]),
    ("silver_fact_compras_detalle", "silver/13_fact_compras_detalle", ["bronze", "silver_fact_compras"]),
    ("silver_fact_inventario", "silver/14_fact_inventario", ["bronze"]),
    ("silver_quality", "silver/20_quality_run", [
        "silver_dim_producto", "silver_dim_bodega", "silver_dim_tercero",
        "silver_dim_sucursal", "silver_dim_formapago", "silver_dim_tiempo",
        "silver_fact_ventas", "silver_fact_ventas_detalle",
        "silver_fact_compras", "silver_fact_compras_detalle", "silver_fact_inventario",
    ]),
    ("gold_ventas", "gold/10_mart_ventas_diarias_sku", ["silver_fact_ventas", "silver_fact_ventas_detalle"]),
    ("gold_inventario", "gold/11_mart_inventario_actual", ["silver_fact_inventario"]),
    ("gold_abc", "gold/12_mart_rotacion_abc", ["silver_fact_ventas", "silver_fact_ventas_detalle"]),
    ("gold_cohortes", "gold/13_mart_cohortes_clientes", ["silver_fact_ventas", "silver_fact_ventas_detalle"]),
    ("gold_dormidos", "gold/14_mart_productos_dormidos", [
        "silver_fact_ventas", "silver_fact_ventas_detalle", "silver_fact_inventario"]),
    ("gold_quality", "gold/20_quality_gold", [
        "gold_ventas", "gold_inventario", "gold_abc", "gold_cohortes", "gold_dormidos"]),
    ("gold_validate", "gold/30_validate_gold", ["gold_quality"]),
]


def build_task_objects():
    result = []
    for key, nb, deps in TASKS:
        t = jobs.Task(
            task_key=key,
            notebook_task=jobs.NotebookTask(notebook_path=f"{NOTEBOOK_PATH}/{nb}"),
            timeout_seconds=3600,
            depends_on=[jobs.TaskDependency(task_key=d) for d in deps] if deps else None,
        )
        result.append(t)
    return result


def main():
    if not DATABRICKS_HOST:
        print("DATABRICKS_HOST no configurado.")
        sys.exit(1)
    if not DATABRICKS_TOKEN:
        print("DATABRICKS_TOKEN no configurado.")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Job name: {JOB_NAME}")
    print(f"Tasks: {len(TASKS)}")
    print("=" * 50)

    # Conectar
    print("\n1. Conectando a Databricks...")
    try:
        w = WorkspaceClient(host=DATABRICKS_HOST, token=DATABRICKS_TOKEN)
        w.current_user.me()
        print("  Conexion exitosa")
    except Exception as e:
        print(f"  Error de conexion: {e}")
        sys.exit(1)

    # Buscar job existente
    print("\n2. Buscando job existente...")
    existing_job_id = None
    for j in w.jobs.list():
        if j.settings.name == JOB_NAME:
            existing_job_id = j.job_id
            print(f"  Job existente encontrado: ID {existing_job_id}")
            break
    if not existing_job_id:
        print("  No existe, se creara uno nuevo")

    # Configuracion del job
    env_spec = jobs.JobEnvironment(
        environment_key="Default",
        spec=compute.Environment(environment_version="5"),
    )
    schedule = jobs.CronSchedule(
        quartz_cron_expression="0 30 2 * * ?",
        timezone_id="America/Bogota",
        pause_status=jobs.PauseStatus.PAUSED,
    )

    if existing_job_id:
        print(f"\n3. Actualizando job {existing_job_id}...")
        w.jobs.reset(
            job_id=existing_job_id,
            new_settings=jobs.JobSettings(
                tasks=build_task_objects(),
                schedule=schedule,
                email_notifications=jobs.JobEmailNotifications(
                    on_failure=[NOTIFICATION_EMAIL]
                ),
                max_concurrent_runs=1,
                environments=[env_spec],
            ),
        )
        print(f"  Job {existing_job_id} actualizado exitosamente")
    else:
        print("\n3. Creando nuevo job...")
        created = w.jobs.create(
            name=JOB_NAME,
            tasks=build_task_objects(),
            schedule=schedule,
            email_notifications=jobs.JobEmailNotifications(
                on_failure=[NOTIFICATION_EMAIL]
            ),
            max_concurrent_runs=1,
            environments=[env_spec],
        )
        print(f"  Job creado: ID {created.job_id}")

    # Resumen
    print(f"\n{'='*50}")
    print("  WORKFLOW GOLD")
    print(f"{'='*50}")
    print(f"  Job: {JOB_NAME}")
    print(f"  Schedule: 0 30 2 * * ? (02:30 COL)")
    print(f"  Tasks: {len(TASKS)}")
    print(f"  Notificaciones: {NOTIFICATION_EMAIL}")
    print(f"\n  El job se crea PAUSED. Para activar:")
    print(f"  Databricks -> Workflows -> {JOB_NAME} -> Resume")
    print(f"\n  Workflow gold configurado exitosamente")


if __name__ == "__main__":
    main()
