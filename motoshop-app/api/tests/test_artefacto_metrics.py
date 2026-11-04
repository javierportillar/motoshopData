"""El artefacto chico tiene que ser completo, o el backend se rompe.

Si una consulta usa una tabla que no está en el manifiesto, Render devuelve 500
justo cuando se lo usa de respaldo. Este test cruza el manifiesto con las tablas
que aparecen en los SQL del código.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from motoshop_api.metrics.artefacto import TABLAS_ARTEFACTO, VENTANA_POR_TABLA

SRC = Path(__file__).resolve().parent.parent / "src" / "motoshop_api"


def _tablas_en_sql() -> set[str]:
    patron = re.compile(r"\b(?:silver|gold)_[a-z0-9_]+\b", re.I)
    vistas: set[str] = set()
    for archivo in SRC.rglob("*.py"):
        vistas |= {m.group(0).lower() for m in patron.finditer(archivo.read_text())}
    return vistas


def test_el_manifiesto_cubre_todas_las_tablas_del_codigo() -> None:
    en_codigo = _tablas_en_sql()
    faltan = sorted(en_codigo - set(TABLAS_ARTEFACTO))
    assert not faltan, f"tablas usadas y no incluidas en el artefacto: {faltan}"


def test_el_manifiesto_no_tiene_tablas_de_mas() -> None:
    en_codigo = _tablas_en_sql()
    sobran = sorted(set(TABLAS_ARTEFACTO) - en_codigo)
    assert not sobran, f"tablas del artefacto que nadie lee: {sobran}"


def test_construir_deja_solo_las_tablas_del_manifiesto(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from build_metrics_duckdb import construir  # type: ignore[import-not-found]

    origen = tmp_path / "gold.duckdb"
    con = duckdb.connect(str(origen))
    for tabla in TABLAS_ARTEFACTO:
        if tabla in VENTANA_POR_TABLA:
            con.execute(f"CREATE TABLE {tabla} (id INTEGER, business_date DATE)")
            con.execute(
                f"INSERT INTO {tabla} VALUES (1, DATE '2026-01-01'), (2, DATE '2026-01-02')"
            )
        else:
            con.execute(f"CREATE TABLE {tabla} (id INTEGER)")
    con.execute("CREATE TABLE tabla_que_nadie_usa (id INTEGER)")
    con.close()

    destino = tmp_path / "metrics.duckdb"
    tamanos = construir(origen, destino)

    assert set(tamanos) == set(TABLAS_ARTEFACTO)
    verif = duckdb.connect(str(destino), read_only=True)
    presentes = {
        fila[0]
        for fila in verif.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    verif.close()
    assert "tabla_que_nadie_usa" not in presentes


def test_construir_falla_si_falta_una_tabla(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from build_metrics_duckdb import construir  # type: ignore[import-not-found]

    origen = tmp_path / "gold_incompleto.duckdb"
    con = duckdb.connect(str(origen))
    con.execute("CREATE TABLE silver_fact_ventas (id INTEGER)")
    con.close()

    import pytest

    with pytest.raises(SystemExit):
        construir(origen, tmp_path / "salida.duckdb")
