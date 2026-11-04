"""Tope de memoria e hilos para las conexiones DuckDB.

En el plan free de Render (512 MB) DuckDB compite por RAM con el propio
proceso: sin techo, una consulta sobre el gold tumba la instancia (reinicios por
"exceeded its memory limit", 2026-11-03). El tope se lee del entorno, así que en
las PCs —donde esas variables no existen— no cambia nada.

Nunca rompe la lectura: si el `SET` falla (versión vieja de DuckDB), se ignora.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any


def aplicar_limites(conn: Any) -> None:
    """Aplica ``DUCKDB_MEMORY_LIMIT`` y ``DUCKDB_THREADS`` si están definidos."""
    limite = os.environ.get("DUCKDB_MEMORY_LIMIT", "").strip()
    hilos = os.environ.get("DUCKDB_THREADS", "").strip()
    if limite:
        with contextlib.suppress(Exception):
            conn.execute(f"SET memory_limit='{limite}'")
    if hilos.isdigit():
        with contextlib.suppress(Exception):
            conn.execute(f"SET threads={int(hilos)}")
