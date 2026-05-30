"""
Create/update Databricks Jobs for the two-pipeline architecture.

Ahora separado en DOS jobs independientes:

  1. motoshop_bronze_silver  → bronze → silver (dims + facts + quality + validate)
  2. motoshop_gold_workflow   → gold marts (10-14) → gold quality (20) → gold validate (30)

Schedule:
  - Bronze-silver:  cron `0 0 9-18 * * ?` (cada hora, 9 AM-6 PM COL)
  - Gold:          cron `0 0 19 * * ?` (7 PM COL) — después del último bronze-silver

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

# ─── Job 1: Bronze → Silver ─────────────────────────────────────────────

BRONZE_SILVER_TASKS = [
    # Bronze
    ("bronze_ingest", "bronze/02_ingest_all_bronze", []),
    # Silver dims
    ("silver_dim_producto", "silver/01_dim_producto", ["bronze_ingest"]),
    ("silver_dim_bodega", "silver/02_dim_bodega", ["bronze_ingest"]),
    ("silver_dim_tercero", "silver/03_dim_tercero", ["bronze_ingest"]),
    ("silver_dim_sucursal", "silver/04_dim_sucursal", ["bronze_ingest"]),
    ("silver_dim_formapago", "silver/05_dim_formapago", ["bronze_ingest"]),
    ("silver_dim_tiempo", "silver/06_dim_tiempo", ["bronze_ingest"]),
    # Silver facts
    ("silver_fact_ventas", "silver/10_fact_ventas", ["bronze_ingest"]),
    ("silver_fact_ventas_detalle", "silver/11_fact_ventas_detalle",
     ["bronze_ingest", "silver_fact_ventas"]),
    ("silver_fact_compras", "silver/12_fact_compras", ["bronze_ingest"]),
    ("silver_fact_compras_detalle", "silver/13_fact_compras_detalle",
     ["bronze_ingest", "silver_fact_compras"]),
    ("silver_fact_inventario", "silver/14_fact_inventario", ["bronze_ingest"]),
    # Silver quality
    ("silver_quality", "silver/20_quality_run", [
        "silver_dim_producto", "silver_dim_bodega", "silver_dim_tercero",
        "silver_dim_sucursal", "silver_dim_formapago", "silver_dim_tiempo",
        "silver_fact_ventas", "silver_fact_ventas_detalle",
        "silver_fact_compras", "silver_fact_compras_detalle", "silver_fact_inventario",
    ]),
    # Silver validate
    ("silver_validate", "silver/30_validate_silver", ["silver_quality"]),
]

# ─── Job 2: Gold ─────────────────────────────────────────────────────────

GOLD_TASKS = [
    ("gold_ventas", "gold/10_mart_ventas_diarias_sku", []),
    ("gold_inventario", "gold/11_mart_inventario_actual", []),
    ("gold_abc", "gold/12_mart_rotacion_abc", []),
    ("gold_cohortes", "gold/13_mart_cohortes_clientes", []),
    ("gold_dormidos", "gold/14_mart_productos_dormidos", []),
    ("gold_quality", "gold/20_quality_gold", [
        "gold_ventas", "gold_inventario", "gold_abc", "gold_cohortes", "gold_dormidos",
    ]),
    ("gold_validate", "gold/30_validate_gold", ["gold_quality"]),
]

# ─── Helpers ─────────────────────────────────────────────────────────────


def build_tasks(task_defs: list[tuple[str, str, list[str]]]) -> list[jobs.Task]:
    result = []
    for key, nb, deps in task_defs:
        # Los notebooks en el Workspace se subieron con extensión .py
        nb_path = f"{NOTEBOOK_PATH}/{nb}.py"
        t = jobs.Task(
            task_key=key,
            notebook_task=jobs.NotebookTask(notebook_path=nb_path),
            timeout_seconds=3600,
            depends_on=[jobs.TaskDependency(task_key=d) for d in deps] if deps else None,
        )
        result.append(t)
    return result


def create_or_update_job(
    w: WorkspaceClient,
    job_name: str,
    task_defs: list[tuple[str, str, list[str]]],
    schedule: jobs.CronSchedule,
) -> int | None:
    """Crea un job nuevo o actualiza uno existente. Devuelve job_id."""
    # Buscar job existente
    existing_job_id = None
    for j in w.jobs.list(name=job_name):
        if j.settings.name == job_name:
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
        existing_job_id = created.job_id
        print(f"  ✅ Job creado: ID {created.job_id}")

    return existing_job_id


def pause_status(s: str) -> jobs.PauseStatus:
    """Convierte string a PauseStatus."""
    return jobs.PauseStatus.PAUSED if s == "PAUSED" else jobs.PauseStatus.UNPAUSED


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

    # ── Job 1: Bronze → Silver ──
    print(f"\n═══ JOB 1: motoshop_bronze_silver ({len(BRONZE_SILVER_TASKS)} tasks) ═══")
    bs_schedule = jobs.CronSchedule(
        quartz_cron_expression="0 0 9-18 * * ?",
        timezone_id="America/Bogota",
        pause_status=jobs.PauseStatus.UNPAUSED,
    )
    bs_id = create_or_update_job(w, "motoshop_bronze_silver", BRONZE_SILVER_TASKS, bs_schedule)

    # ── Job 2: Gold ──
    print(f"\n═══ JOB 2: motoshop_gold_workflow ({len(GOLD_TASKS)} tasks) ═══")
    gold_schedule = jobs.CronSchedule(
        quartz_cron_expression="0 0 19 * * ?",
        timezone_id="America/Bogota",
        pause_status=jobs.PauseStatus.UNPAUSED,
    )
    gold_id = create_or_update_job(w, "motoshop_gold_workflow", GOLD_TASKS, gold_schedule)

    # ── Resumen ──
    print(f"\n{'='*60}")
    print(f"  WORKFLOWS CONFIGURADOS")
    print(f"{'='*60}")
    print(f"  Job 1: motoshop_bronze_silver  (ID: {bs_id})")
    print(f"    Tasks: {len(BRONZE_SILVER_TASKS)} (bronze → silver)")
    print(f"    Schedule: 0 0 9-18 * * ?  (cada hora, 9 AM-6 PM COL) — UNPAUSED")
    print(f"  Job 2: motoshop_gold_workflow   (ID: {gold_id})")
    print(f"    Tasks: {len(GOLD_TASKS)} (gold marts → quality → validate)")
    print(f"    Schedule: 0 0 19 * * ?  (7 PM COL) — UNPAUSED")
    print(f"  Notificaciones: {NOTIFICATION_EMAIL}")
    print(f"\n  🕐 Bronze-silver corre cada hora 9 AM-6 PM para mantener actualizado silver.")
    print(f"  Gold corre a las 7 PM con los datos del día.")
    print(f"\n  ✅ Workflows configurados exitosamente")
    print(f"\n  Nota: ejecutá primero upload_all_notebooks.py para subir")
    print(f"  todos los notebooks al Workspace antes de correr los jobs.")


if __name__ == "__main__":
    main()
