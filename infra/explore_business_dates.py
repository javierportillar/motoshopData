"""Sondeo read-only de columnas de fecha en las 12 tablas core."""
from __future__ import annotations

import os
import pathlib
import re

import mysql.connector
from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

TABLES_CORE = [
    "facventas", "detfventas", "productos", "auxinventario", "bodegas",
    "terceros", "compras", "detcompras", "sucursales", "formapago",
    "subproduct", "preciosxpro",
]

DATE_HINT = re.compile(r"(fec|fch|date|fech)", re.IGNORECASE)


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "motoshop2024"),
        charset="utf8",
    )
    c = conn.cursor()

    print(f"# Sondeo de columnas de fecha — {pathlib.Path(__file__).name}\n")
    print(f"BD: {os.getenv('MYSQL_DATABASE')}  · usuario: {os.getenv('MYSQL_USER')}\n")

    for table in TABLES_CORE:
        print(f"\n## {table}")
        c.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (os.getenv("MYSQL_DATABASE"), table),
        )
        cols = c.fetchall()
        candidatas = [
            (name, dtype, null)
            for (name, dtype, null) in cols
            if DATE_HINT.search(name) or dtype in ("date", "datetime", "timestamp")
        ]
        if not candidatas:
            print(f"  · sin columnas candidatas a fecha")
            continue

        print(f"  · columnas candidatas: {len(candidatas)}")
        for name, dtype, null in candidatas:
            print(f"    - `{name}` ({dtype}, nullable={null})")
            try:
                c.execute(
                    f"SELECT MIN(`{name}`), MAX(`{name}`), "
                    f"SUM(CASE WHEN `{name}` IS NULL THEN 1 ELSE 0 END) AS nulls, "
                    f"SUM(CASE WHEN CAST(`{name}` AS CHAR) LIKE '0000-%%' THEN 1 ELSE 0 END) AS zeros, "
                    f"COUNT(*) AS total "
                    f"FROM `{table}`"
                )
                mn, mx, nulls, zeros, total = c.fetchone()
                print(f"      MIN={mn} · MAX={mx} · NULLs={nulls} · `0000-*`={zeros} · TOTAL={total}")
            except Exception as e:
                print(f"      (stats error: {e})")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
