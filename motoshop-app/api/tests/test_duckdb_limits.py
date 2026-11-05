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


def test_auto_refresh_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    from motoshop_api.metrics.repo_duckdb import _auto_refresh_habilitado

    monkeypatch.delenv("DUCKDB_R2_AUTO_REFRESH", raising=False)
    assert _auto_refresh_habilitado() is True

    for apagado in ("0", "false", "no", "off", "OFF"):
        monkeypatch.setenv("DUCKDB_R2_AUTO_REFRESH", apagado)
        assert _auto_refresh_habilitado() is False

    monkeypatch.setenv("DUCKDB_R2_AUTO_REFRESH", "1")
    assert _auto_refresh_habilitado() is True


def test_ttl_de_refresco_desde_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    from motoshop_api.metrics.repo_duckdb import _ttl_refresco

    monkeypatch.delenv("DUCKDB_R2_REFRESH_TTL", raising=False)
    assert _ttl_refresco() == 1800

    monkeypatch.setenv("DUCKDB_R2_REFRESH_TTL", "600")
    assert _ttl_refresco() == 600

    monkeypatch.setenv("DUCKDB_R2_REFRESH_TTL", "no-es-numero")
    assert _ttl_refresco() == 1800


def test_worker_de_assessments_se_puede_apagar(monkeypatch: pytest.MonkeyPatch) -> None:
    from motoshop_api.purchase_assessments.worker import worker_habilitado

    monkeypatch.delenv("PA_WORKER_ENABLED", raising=False)
    assert worker_habilitado() is True

    for apagado in ("0", "false", "off", "NO"):
        monkeypatch.setenv("PA_WORKER_ENABLED", apagado)
        assert worker_habilitado() is False

    monkeypatch.setenv("PA_WORKER_ENABLED", "1")
    assert worker_habilitado() is True


def test_bodega_por_defecto_es_bd01() -> None:
    """El POS escribía codbod '01', que no existe en el catálogo de bodegas."""
    from motoshop_api.erp.invoicing.repo import LEGACY_WAREHOUSE

    assert LEGACY_WAREHOUSE == "BD01"
    assert len(LEGACY_WAREHOUSE) <= 4  # detfventas.codbod es varchar(4)
