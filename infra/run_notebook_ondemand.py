"""
MotoShop · Run Notebook On-Demand
=====================================

CLI que ejecuta UN notebook específico del workflow en Databricks sin
disparar todo el job. Útil cuando:

- Falla un mart específico y querés re-ejecutar solo ese
- Estás probando un cambio en un notebook
- Querés re-poblar una tabla sin esperar al workflow nocturno
- Querés validar un task específico antes de re-correr el workflow completo

Estrategia:
- Usa Databricks SDK `jobs.submit` para crear un job ephemeral con UNA sola task
- Apunta al mismo notebook path que el workflow productivo
- Usa el SQL Warehouse del workflow (Serverless Starter)
- Logea el run_id para tracking
- Espera la finalización (timeout configurable) y reporta status

NO MODIFICA el workflow `motoshop_full_workflow`. Es un job ephemeral separado.

Uso:
    python infra/run_notebook_ondemand.py --list
    python infra/run_notebook_ondemand.py --task gold_drift
    python infra/run_notebook_ondemand.py --task gold_rotacion_promedio --wait 600
    python infra/run_notebook_ondemand.py --notebook gold/18_mart_rotacion_promedio --wait 600
    python infra/run_notebook_ondemand.py --task silver_fact_ventas --no-wait

Requiere:
    DATABRICKS_HOST y DATABRICKS_TOKEN en .env
    databricks-sdk instalado
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Cargar .env si existe
try:
    from dotenv import load_dotenv  # type: ignore

    env_paths = [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent / "motoshop-app" / "api" / ".env",
    ]
    for p in env_paths:
        if p.exists():
            load_dotenv(p)
            break
except ImportError:
    pass

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.jobs import (
        NotebookTask,
        RunLifeCycleState,
        SubmitTask,
    )
except ImportError as e:
    print(f"ERROR: databricks-sdk no instalado: {e}")
    print("Instalar: pip install databricks-sdk python-dotenv")
    sys.exit(1)


# Inventario completo de tasks del workflow productivo (sync con
# infra/create_full_workflow.py). Si cambia el workflow, actualizar acá.
TASK_REGISTRY: dict[str, str] = {
    # Bronze
    "bronze_ingest": "bronze/02_ingest_all_bronze",
    # Silver dims
    "silver_dim_producto": "silver/01_dim_producto",
    "silver_dim_bodega": "silver/02_dim_bodega",
    "silver_dim_tercero": "silver/03_dim_tercero",
    "silver_dim_sucursal": "silver/04_dim_sucursal",
    "silver_dim_formapago": "silver/05_dim_formapago",
    "silver_dim_tiempo": "silver/06_dim_tiempo",
    # Silver facts
    "silver_fact_ventas": "silver/10_fact_ventas",
    "silver_fact_ventas_detalle": "silver/11_fact_ventas_detalle",
    "silver_fact_compras": "silver/12_fact_compras",
    "silver_fact_compras_detalle": "silver/13_fact_compras_detalle",
    "silver_fact_inventario": "silver/14_fact_inventario",
    # Silver quality + validate
    "silver_quality": "silver/20_quality_run",
    "silver_validate": "silver/30_validate_silver",
    # Gold marts
    "gold_ventas": "gold/10_mart_ventas_diarias_sku",
    "gold_inventario": "gold/11_mart_inventario_actual",
    "gold_abc": "gold/12_mart_rotacion_abc",
    "gold_cohortes": "gold/13_mart_cohortes_clientes",
    "gold_dormidos": "gold/14_mart_productos_dormidos",
    # Gold snapshots (balde B)
    "gold_snapshot_abc": "gold/30_snapshot_abc_mensual",
    "gold_snapshot_dormidos": "gold/31_snapshot_dormidos_mensual",
    "gold_snapshot_alertas": "gold/32_snapshot_alertas_diario",
    # Gold analytics F7-E D4+D5
    "gold_rotacion_promedio": "gold/18_mart_rotacion_promedio",
    "gold_abc_xyz": "gold/19_mart_abc_xyz",
    # Gold ML pipeline
    "gold_archive_forecasts": "gold/33_archive_forecasts",
    "gold_baseline": "gold/16_forecast_baseline_sku",
    "gold_feature_store": "gold/15_feature_store_sku",
    "gold_classifier": "gold/22_classifier_stockout",
    # Gold quality + validate + drift
    "gold_quality": "gold/20_quality_gold",
    "gold_validate": "gold/30_validate_gold",
    "gold_drift": "gold/25_drift_monitor",
}


def list_tasks() -> None:
    """Lista todos los tasks disponibles agrupados por capa."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for task_name, notebook in TASK_REGISTRY.items():
        layer = task_name.split("_")[0]
        groups.setdefault(layer, []).append((task_name, notebook))

    for layer in ["bronze", "silver", "gold"]:
        if layer not in groups:
            continue
        print(f"\n=== {layer.upper()} ({len(groups[layer])} tasks) ===")
        for task_name, notebook in groups[layer]:
            print(f"  {task_name:<35}  →  {notebook}")


def resolve_notebook_path(
    workspace_user: str, task: str | None, notebook: str | None
) -> str:
    """
    Convierte un task name o notebook path relativo en path absoluto Databricks.

    Si task: lookup en TASK_REGISTRY.
    Si notebook: usar como path relativo a notebooks/.

    Ambos resultan en: /Workspace/Users/<user>/Repos/motoshopData/notebooks/<path>
    """
    if task:
        if task not in TASK_REGISTRY:
            print(f"ERROR: task '{task}' no existe en TASK_REGISTRY.")
            print("Usar --list para ver disponibles.")
            sys.exit(1)
        relative = TASK_REGISTRY[task]
    elif notebook:
        relative = notebook.lstrip("/")
    else:
        print("ERROR: especificar --task o --notebook")
        sys.exit(1)

    # Path en Databricks Workspace según upload_all_notebooks.py
    # Base path actual: /Workspace/Users/<user>/motoshopData/notebooks/
    return f"/Workspace/Users/{workspace_user}/motoshopData/notebooks/{relative}"


def submit_notebook_run(
    w: WorkspaceClient,
    notebook_path: str,
    warehouse_id: str,
    run_name: str,
) -> int:
    """
    Submit un job ephemeral con UNA sola notebook task.

    Retorna run_id.
    """
    task = SubmitTask(
        task_key="ondemand_task",
        notebook_task=NotebookTask(
            notebook_path=notebook_path,
            warehouse_id=warehouse_id,
        ),
    )

    submission = w.jobs.submit(run_name=run_name, tasks=[task])
    if submission.run_id is None:
        raise RuntimeError("submit() devolvió run_id None")
    return submission.run_id


def wait_for_completion(
    w: WorkspaceClient, run_id: int, timeout_sec: int
) -> tuple[str, str | None]:
    """
    Polling cada 10s hasta que el run termine o se exceda timeout.

    Retorna (life_cycle_state, result_state).
    """
    start = time.time()
    last_state = ""
    while True:
        run = w.jobs.get_run(run_id)
        lcs = (
            run.state.life_cycle_state.value
            if run.state and run.state.life_cycle_state
            else "UNKNOWN"
        )
        rs = (
            run.state.result_state.value
            if run.state and run.state.result_state
            else None
        )

        if lcs != last_state:
            print(f"  [{int(time.time() - start)}s] state={lcs} result={rs}")
            last_state = lcs

        if lcs in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return lcs, rs

        if time.time() - start > timeout_sec:
            print(f"⚠️  Timeout {timeout_sec}s alcanzado. Run sigue corriendo.")
            return "TIMEOUT", None

        time.sleep(10)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecutar un notebook del workflow MotoShop on-demand",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista todos los tasks disponibles y sale",
    )
    parser.add_argument(
        "--task",
        type=str,
        help="Nombre del task (ej: gold_drift, silver_fact_ventas)",
    )
    parser.add_argument(
        "--notebook",
        type=str,
        help="Path relativo del notebook (ej: gold/18_mart_rotacion_promedio)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=600,
        help="Esperar finalización hasta N segundos (default 600=10min). Usar --no-wait para fire-and-forget.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="No esperar finalización. Imprimir run_id y salir.",
    )
    parser.add_argument(
        "--warehouse-id",
        type=str,
        default="43bc044eaef4cca4",
        help="Databricks SQL Warehouse ID (default = motoshop Serverless Starter)",
    )

    args = parser.parse_args()

    if args.list:
        list_tasks()
        return 0

    if not args.task and not args.notebook:
        parser.print_help()
        print("\nERROR: especificar --task, --notebook, o --list")
        return 1

    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    if not host or not token:
        print("ERROR: DATABRICKS_HOST y DATABRICKS_TOKEN no están en el entorno.")
        print("Cargar desde .env o exportar manual.")
        return 1

    w = WorkspaceClient(host=host, token=token)

    try:
        user = w.current_user.me().user_name
        assert user is not None
    except Exception as e:
        print(f"ERROR: no se pudo autenticar contra Databricks: {e}")
        return 1

    notebook_path = resolve_notebook_path(user, args.task, args.notebook)
    run_name = f"ondemand_{args.task or args.notebook}_{int(time.time())}"

    print(f"🚀 Submitting on-demand notebook run:")
    print(f"   User:     {user}")
    print(f"   Notebook: {notebook_path}")
    print(f"   Warehouse: {args.warehouse_id}")
    print(f"   Run name: {run_name}")

    try:
        run_id = submit_notebook_run(w, notebook_path, args.warehouse_id, run_name)
    except Exception as e:
        print(f"ERROR submit: {e}")
        return 1

    print(f"✅ Run submitted. run_id={run_id}")
    print(
        f"   Ver en UI: {host.rstrip('/')}/jobs/runs/{run_id}"
    )

    if args.no_wait:
        print("🏁 --no-wait. Saliendo sin esperar.")
        return 0

    print(f"⏳ Esperando finalización (timeout {args.wait}s)...")
    try:
        lcs, rs = wait_for_completion(w, run_id, args.wait)
    except KeyboardInterrupt:
        print("\n⚠️  Interrumpido por usuario. Run sigue corriendo en Databricks.")
        return 130

    if lcs == "TERMINATED" and rs == "SUCCESS":
        print(f"✅ Run {run_id} COMPLETADO exitosamente.")
        return 0
    elif lcs == "TERMINATED" and rs == "FAILED":
        print(f"🔴 Run {run_id} FAILED. Revisar stacktrace en UI.")
        return 1
    elif lcs == "TIMEOUT":
        print(f"⚠️  Timeout. Run {run_id} sigue corriendo.")
        return 2
    else:
        print(f"⚠️  Run {run_id} terminó con estado inesperado: {lcs} / {rs}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
