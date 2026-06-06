"""Pipeline orquestador V1.5 (seed interino desde exports JSON).

Ejecuta: carga silver+gold desde exports JSON → DuckDB out/motoshop_gold.duckdb

NOTA: En produccion Windows, este pipeline leera directamente de MySQL bronze.
Los exports JSON son seed interino mientras Databricks esta inestable.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from pipeline import gold, silver
from pipeline.build_duckdb_from_export import build_from_databricks

OUTPUT_PATH = Path("out/motoshop_gold.duckdb")


def run_all() -> str:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Usa build_duckdb_from_export que ya funciona con los JSON exportados
    build_from_databricks(OUTPUT_PATH)
    return str(OUTPUT_PATH)


if __name__ == "__main__":
    run_all()
