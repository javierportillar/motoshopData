"""Crea o verifica el Databricks Workflow de ingesta bronze.

Lee la definición de infra/databricks_workflow.json y crea/actualiza
el Workflow vía Databricks SDK.

Uso:
    .venv-infra\Scripts\Activate.ps1
    python infra/create_databricks_workflow.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    CronSchedule,
    JobsHealthRules,
    NotebookTask,
    Task,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

WORKFLOW_DEF = PROJECT_ROOT / "infra" / "databricks_workflow.json"


def main() -> int:
    cfg = {
        "host": os.environ.get("DATABRICKS_HOST", ""),
        "token": os.environ.get("DATABRICKS_TOKEN", ""),
    }
    if not cfg["host"] or not cfg["token"]:
        print("ERROR: DATABRICKS_HOST y DATABRICKS_TOKEN requeridos en .env")
        return 1

    w = WorkspaceClient(host=cfg["host"], token=cfg["token"])

    with open(WORKFLOW_DEF) as f:
        wf_def = json.load(f)

    # Buscar si ya existe un Workflow con ese nombre
    existing = None
    for job in w.jobs.list():
        if job.settings and job.settings.name == wf_def["name"]:
            existing = job
            break

    if existing:
        print(f"Workflow '{wf_def['name']}' ya existe (ID: {existing.job_id}). Actualizando...")
        w.jobs.reset(
            job_id=existing.job_id,
            new_settings=wf_def,
        )
        print("Actualizado.")
    else:
        print(f"Creando Workflow '{wf_def['name']}'...")
        result = w.jobs.create(**wf_def)
        print(f"Creado con ID: {result.job_id}")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
