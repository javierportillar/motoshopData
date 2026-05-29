"""
Create/update Databricks Job for gold workflow using databricks-sdk.

Schedule: cron `0 30 2 * * ?` (02:30 COL every day)
Tasks: bronze ingestion → silver notebooks → gold/10..14 → gold/20 → gold/30

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
import time

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service import jobs
except ImportError:
    print("❌ databricks-sdk no instalado. Ejecutá: pip install databricks-sdk")
    sys.exit(1)

# ─── Configuración ──────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

# Ruta base de los notebooks en Databricks Workspace
NOTEBOOK_PATH = "/Repos/javierportillar/motoshopData/notebooks"

# Nombre del job
JOB_NAME = "motoshop_gold_workflow"

# Email de notificación (placeholder)
NOTIFICATION_EMAIL = "motoshop@example.com"

# Tareas del workflow en orden de ejecución
TASKS = [
    # ── Bronze ingestion ──
    {
        "task_key": "bronze_ingestion",
        "notebook_path": f"{NOTEBOOK_PATH}/bronze/02_ingest_all_bronze",
        "description": "Ingesta de todas las tablas bronze desde MySQL",
    },
    # ── Silver notebooks (dimensiones) ──
    {
        "task_key": "silver_dim_producto",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/01_dim_producto",
        "description": "SCD Type 1 desde bronze.productos",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_dim_bodega",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/02_dim_bodega",
        "description": "SCD Type 1 desde bronze.bodegas",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_dim_tercero",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/03_dim_tercero",
        "description": "SCD Type 1 desde bronze.terceros",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_dim_sucursal",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/04_dim_sucursal",
        "description": "SCD Type 1 desde bronze.sucursales",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_dim_formapago",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/05_dim_formapago",
        "description": "SCD Type 1 desde bronze.formaspago",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_dim_tiempo",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/06_dim_tiempo",
        "description": "Dimensión temporal desde calendario",
        "depends_on": ["bronze_ingestion"],
    },
    # ── Silver notebooks (hechos) ──
    {
        "task_key": "silver_fact_ventas",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/10_fact_ventas",
        "description": "Hechos de ventas desde bronze.facventas",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_fact_ventas_detalle",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/11_fact_ventas_detalle",
        "description": "Detalle de ventas desde bronze.detfventas",
        "depends_on": ["bronze_ingestion", "silver_fact_ventas"],
    },
    {
        "task_key": "silver_fact_compras",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/12_fact_compras",
        "description": "Hechos de compras desde bronze.faccompras",
        "depends_on": ["bronze_ingestion"],
    },
    {
        "task_key": "silver_fact_compras_detalle",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/13_fact_compras_detalle",
        "description": "Detalle de compras desde bronze.detfcompras",
        "depends_on": ["bronze_ingestion", "silver_fact_compras"],
    },
    {
        "task_key": "silver_fact_inventario",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/14_fact_inventario",
        "description": "Hechos de inventario desde bronze.auxinventario",
        "depends_on": ["bronze_ingestion"],
    },
    # ── Silver quality ──
    {
        "task_key": "silver_quality",
        "notebook_path": f"{NOTEBOOK_PATH}/silver/20_quality_run",
        "description": "Quality run sobre tablas silver",
        "depends_on": [
            "silver_dim_producto", "silver_dim_bodega",
            "silver_dim_tercero", "silver_dim_sucursal",
            "silver_dim_formapago", "silver_dim_tiempo",
            "silver_fact_ventas", "silver_fact_ventas_detalle",
            "silver_fact_compras", "silver_fact_compras_detalle",
            "silver_fact_inventario",
        ],
    },
    # ── Gold marts ──
    {
        "task_key": "gold_mart_ventas_diarias_sku",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/10_mart_ventas_diarias_sku",
        "description": "Agregación diaria de ventas por SKU",
        "depends_on": ["silver_fact_ventas", "silver_fact_ventas_detalle"],
    },
    {
        "task_key": "gold_mart_inventario_actual",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/11_mart_inventario_actual",
        "description": "Snapshot del último estado de inventario",
        "depends_on": ["silver_fact_inventario"],
    },
    {
        "task_key": "gold_mart_rotacion_abc",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/12_mart_rotacion_abc",
        "description": "Clasificación ABC por ingresos mensuales",
        "depends_on": ["silver_fact_ventas", "silver_fact_ventas_detalle"],
    },
    {
        "task_key": "gold_mart_cohortes_clientes",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/13_mart_cohortes_clientes",
        "description": "Cohortes de clientes por mes de primera compra",
        "depends_on": ["silver_fact_ventas", "silver_fact_ventas_detalle"],
    },
    {
        "task_key": "gold_mart_productos_dormidos",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/14_mart_productos_dormidos",
        "description": "Productos sin venta > 90 días",
        "depends_on": [
            "silver_fact_ventas", "silver_fact_ventas_detalle",
            "silver_fact_inventario",
        ],
    },
    # ── Gold quality ──
    {
        "task_key": "gold_quality",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/20_quality_gold",
        "description": "Quality run sobre marts gold",
        "depends_on": [
            "gold_mart_ventas_diarias_sku",
            "gold_mart_inventario_actual",
            "gold_mart_rotacion_abc",
            "gold_mart_cohortes_clientes",
            "gold_mart_productos_dormidos",
        ],
    },
    # ── Gold validation ──
    {
        "task_key": "gold_validate",
        "notebook_path": f"{NOTEBOOK_PATH}/gold/30_validate_gold",
        "description": "Validación final de marts gold (idempotencia, fechas, coherencia)",
        "depends_on": ["gold_quality"],
    },
]


def build_job_settings() -> jobs.CreateJob:
    """Construye la configuración del job Databricks."""
    job_tasks = []
    for task in TASKS:
        base = jobs.Task(
            task_key=task["task_key"],
            description=task.get("description", ""),
            existing_cluster_id="",  # Se asigna automáticamente o se configura
            notebook_path=task["notebook_path"],
            timeout_seconds=3600,  # 1 hora por tarea
        )
        if task.get("depends_on"):
            base.depends_on = [
                jobs.TaskDependency(task_key=d) for d in task["depends_on"]
            ]
        job_tasks.append(base)

    return jobs.CreateJob(
        name=JOB_NAME,
        tasks=job_tasks,
        schedule=jobs.CronSchedule(
            quartz_cron_expression="0 30 2 * * ?",
            timezone_id="America/Bogota",
            pause_status="PAUSED",  # Arranca pausado; despausar manualmente
        ),
        email_notifications=jobs.JobEmailNotifications(
            on_failure=[NOTIFICATION_EMAIL],
            on_success=[],
        ),
        max_concurrent_runs=1,
    )


def main():
    if not DATABRICKS_HOST:
        print("❌ DATABRICKS_HOST no configurado.")
        sys.exit(1)

    if not DATABRICKS_TOKEN:
        print("❌ DATABRICKS_TOKEN no configurado.")
        sys.exit(1)

    print(f"Host: {DATABRICKS_HOST}")
    print(f"Job name: {JOB_NAME}")
    print(f"Schedule: 0 30 2 * * ? (02:30 COL)")
    print(f"Tasks: {len(TASKS)}")
    print("=" * 50)

    # Conectar
    print("\n1. Conectando a Databricks...")
    try:
        w = WorkspaceClient(
            host=DATABRICKS_HOST,
            token=DATABRICKS_TOKEN,
        )
        # Health check
        w.current_user.me()
        print("  ✅ Conexión exitosa")
    except Exception as e:
        print(f"  ❌ Error de conexión: {e}")
        sys.exit(1)

    # Verificar si el job ya existe
    print("\n2. Buscando job existente...")
    existing_job_id = None
    try:
        for j in w.jobs.list(name=JOB_NAME):
            if j.settings.name == JOB_NAME:
                existing_job_id = j.job_id
                print(f"  ✅ Job existente encontrado: ID {existing_job_id}")
                break
    except Exception as e:
        print(f"  ⚠️ Error listando jobs: {e}")

    # Crear o actualizar job
    settings = build_job_settings()

    if existing_job_id:
        print(f"\n3. Actualizando job {existing_job_id}...")
        try:
            w.jobs.reset(job_id=existing_job_id, new_settings=settings)
            print(f"  ✅ Job {existing_job_id} actualizado exitosamente")
        except Exception as e:
            print(f"  ❌ Error actualizando job: {e}")
            sys.exit(1)
    else:
        print("\n3. Creando nuevo job...")
        try:
            created = w.jobs.create(settings)
            print(f"  ✅ Job creado: ID {created.job_id}")
            if hasattr(created, 'url'):
                print(f"     URL: {created.url}")
        except Exception as e:
            print(f"  ❌ Error creando job: {e}")
            sys.exit(1)

    # Resumen
    print(f"\n{'='*50}")
    print("  RESUMEN WORKFLOW GOLD")
    print(f"{'='*50}")
    print(f"  Job: {JOB_NAME}")
    print(f"  Schedule: 0 30 2 * * ? (02:30 COL)")
    print(f"  Tasks: {len(TASKS)}")

    total_deps = sum(1 for t in TASKS if t.get("depends_on"))
    print(f"  Tareas con dependencias: {total_deps}/{len(TASKS)}")
    print(f"  Notificaciones: {NOTIFICATION_EMAIL}")
    print(f"\n  ⚠️ El job se crea en estado PAUSED.")
    print(f"     Para activarlo: Databricks → Workflows → {JOB_NAME} → Resume")
    print(f"\n  ✅ Workflow gold configurado exitosamente")


if __name__ == "__main__":
    main()
