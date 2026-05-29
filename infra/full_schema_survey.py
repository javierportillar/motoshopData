"""Survey completo de la BD motoshop2024 — todas las tablas y columnas."""
from __future__ import annotations

import os
import pathlib

import mysql.connector
from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


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
    db = os.getenv("MYSQL_DATABASE", "motoshop2024")

    print(f"# Survey completo de la BD: {db}\n")

    # Listar todas las tablas
    c.execute(
        "SELECT TABLE_NAME, TABLE_ROWS, ENGINE, TABLE_COLLATION "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' "
        "ORDER BY TABLE_NAME",
        (db,),
    )
    tables = c.fetchall()
    print(f"## Resumen general\n")
    print(f"- Total tablas: **{len(tables)}**\n")
    print(f"| Tabla | Filas (est.) | Engine | Collation |")
    print(f"|-------|-------------|--------|-----------|")
    for name, rows, engine, collation in tables:
        print(f"| {name} | {rows:,} | {engine} | {collation} |")

    # Detalle de cada tabla
    print(f"\n---\n\n## Detalle por tabla\n")
    for tbl_name, tbl_rows, tbl_engine, tbl_collation in tables:
        print(f"\n### {tbl_name}")
        print(f"- **Engine:** {tbl_engine} · **Collation:** {tbl_collation} · **Filas (est.):** {tbl_rows:,}\n")

        c.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
            "CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, "
            "COLUMN_KEY, EXTRA "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            (db, tbl_name),
        )
        cols = c.fetchall()

        print(f"| # | Columna | Tipo | Nullable | Default | MaxLen | Precision | Key | Extra |")
        print(f"|---|---------|------|----------|---------|--------|-----------|-----|-------|")
        for i, (cname, dtype, nullable, default, maxlen, precision, scale, key, extra) in enumerate(cols, 1):
            maxlen_str = str(maxlen) if maxlen else "-"
            prec_str = f"{precision},{scale}" if precision else "-"
            key_str = key if key else ""
            extra_str = extra if extra else ""
            default_str = str(default) if default is not None else "NULL"
            print(f"| {i} | `{cname}` | {dtype} | {nullable} | {default_str} | {maxlen_str} | {prec_str} | {key_str} | {extra_str} |")

        # Stats rápidas por columna (solo para tablas con < 1M filas estimadas)
        if tbl_rows and tbl_rows < 1_000_000:
            print(f"\n**Stats rápidas:**\n")
            print(f"| Columna | NULLs | Distinct | Ejemplo |")
            print(f"|---------|-------|----------|---------|")
            for cname, dtype, *_ in cols:
                try:
                    c.execute(
                        f"SELECT SUM(CASE WHEN `{cname}` IS NULL THEN 1 ELSE 0 END), "
                        f"COUNT(DISTINCT `{cname}`), "
                        f"CAST(MIN(`{cname}`) AS CHAR) "
                        f"FROM `{tbl_name}`"
                    )
                    nulls, distinct, example = c.fetchone()
                    ex_str = str(example)[:40] if example is not None else "NULL"
                    print(f"| `{cname}` | {nulls:,} | {distinct:,} | {ex_str} |")
                except Exception:
                    print(f"| `{cname}` | (error) | (error) | (error) |")
        else:
            print(f"\n*(Stats omitidas — tabla muy grande para COUNT(DISTINCT) rápido)*")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
