#!/usr/bin/env python3
"""Cleanup legacy motoshop_* tables from DuckDB.

MotoShop migró de prefijo motoshop_silver_*/motoshop_gold_* a
silver_*/gold_* (sin tenant prefix). Este script dropea las tablas legacy
que quedaron de迁移 anteriores.

Uso:
    python scripts/cleanup_legacy_tables.py
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

TENANT = os.environ.get("TENANT", "motoshop")
DB_PATH = Path(os.environ.get("DUCKDB_PATH", f"out/{TENANT}_gold.duckdb"))


def main() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: DuckDB no encontrado en {DB_PATH}")
        return

    con = duckdb.connect(str(DB_PATH))

    # Listar tablas legacy (motoshop_*)
    legacy = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name LIKE 'motoshop_%' "
        "ORDER BY table_name"
    ).fetchall()

    if not legacy:
        print("✅ No hay tablas legacy para limpiar")
        con.close()
        return

    print(f"Se encontraron {len(legacy)} tablas legacy:")
    for (tname,) in legacy:
        print(f"  [DROP] {tname}")

    # Verificar que las tablas nuevas existen (no dropear si no hay reemplazo)
    new_prefixes = {
        "motoshop_silver_": "silver_",
        "motoshop_gold_": "gold_",
    }

    can_proceed = True
    for (tname,) in legacy:
        found_replacement = False
        for old_pref, new_pref in new_prefixes.items():
            if tname.startswith(old_pref):
                replacement = new_pref + tname[len(old_pref):]
                try:
                    con.execute(f"SELECT COUNT(*) FROM \"{replacement}\"").fetchone()
                    found_replacement = True
                except Exception:
                    print(f"  [WARN] {tname} -> NO HAY REEMPLAZO ({replacement})")
                    can_proceed = False
        if not found_replacement:
            print(f"  [WARN] {tname} no tiene reemplazo conocido, revisar manualmente")

    if not can_proceed:
        print("\n[ERROR] No se puede proceder: hay tablas legacy sin reemplazo.")
        print("Revisá manualmente antes de dropear.")
        con.close()
        return

    # Dropear tablas legacy
    dropped = 0
    for (tname,) in legacy:
        try:
            con.execute(f"DROP TABLE IF EXISTS \"{tname}\"")
            dropped += 1
            print(f"  [OK] Dropeada: {tname}")
        except Exception as e:
            print(f"  [ERROR] Error dropping {tname}: {e}")

    con.commit()
    con.close()
    print(f"\n[OK] Cleanup completo: {dropped} tablas legacy eliminadas")


if __name__ == "__main__":
    main()
