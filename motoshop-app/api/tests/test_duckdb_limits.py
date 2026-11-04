"""El tope de memoria de DuckDB se aplica desde el entorno y nunca rompe."""

from __future__ import annotations

import pytest

from motoshop_api.db.duckdb_limits import aplicar_limites


class _Conexion:
    def __init__(self, falla: bool = False) -> None:
        self.sentencias: list[str] = []
        self._falla = falla

    def execute(self, sql: str) -> None:
        if self._falla:
            raise RuntimeError("SET no soportado")
        self.sentencias.append(sql)


def test_aplica_memoria_e_hilos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "128MB")
    monkeypatch.setenv("DUCKDB_THREADS", "1")
    conn = _Conexion()

    aplicar_limites(conn)

    assert conn.sentencias == ["SET memory_limit='128MB'", "SET threads=1"]


def test_sin_variables_no_toca_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("DUCKDB_THREADS", raising=False)
    conn = _Conexion()

    aplicar_limites(conn)

    assert conn.sentencias == []


def test_un_set_que_falla_no_propaga(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "128MB")
    conn = _Conexion(falla=True)

    aplicar_limites(conn)  # no debe lanzar

    assert conn.sentencias == []
