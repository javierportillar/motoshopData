"""Construye el artefacto chico del gold: sólo las tablas que el backend lee.

Uso:
    python scripts/build_metrics_duckdb.py <gold_completo.duckdb> <salida.duckdb>

Se corre después de publicar el gold en R2. Abre el origen en sólo lectura,
copia las 16 tablas del manifiesto y verifica que ninguna falte: si el pipeline
renombró una tabla, este script falla en vez de publicar un archivo incompleto.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from motoshop_api.metrics.artefacto import TABLAS_ARTEFACTO


def construir(origen: Path, destino: Path) -> dict[str, int]:
    if not origen.is_file():
        raise SystemExit(f"no existe el gold de origen: {origen}")
    if destino.exists():
        destino.unlink()

    con = duckdb.connect(str(destino))
    try:
        con.execute(f"ATTACH '{origen.as_posix()}' AS origen (READ_ONLY)")
        existentes = {
            fila[0].lower()
            for fila in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_catalog = 'origen'"
            ).fetchall()
        }
        faltantes = [t for t in TABLAS_ARTEFACTO if t not in existentes]
        if faltantes:
            raise SystemExit(
                "el gold no tiene estas tablas del manifiesto: " + ", ".join(faltantes)
            )
        tamanos: dict[str, int] = {}
        for tabla in TABLAS_ARTEFACTO:
            con.execute(f"CREATE TABLE {tabla} AS SELECT * FROM origen.{tabla}")
            # VACUUM/ANALYZE compactan el archivo y dejan estadísticas para el planner.
            tamanos[tabla] = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return tamanos


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    origen, destino = Path(sys.argv[1]), Path(sys.argv[2])
    tamanos = construir(origen, destino)
    total = destino.stat().st_size
    print(f"artefacto: {destino} ({total / 1_048_576:.1f} MB)")
    for tabla, filas in tamanos.items():
        print(f"  {tabla}: {filas} filas")
    print(f"gold origen: {origen.stat().st_size / 1_048_576:.1f} MB")


if __name__ == "__main__":
    main()
