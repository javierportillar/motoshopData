"""Tests para DuckDBMetricsRepo multi-tenant (Sprint M1 — Category 2).

Strict TDD mode: tests first, then implementation.
"""

from __future__ import annotations

import os


def test_make_db_path_prod() -> None:
    """_make_db_path debe usar /tmp/{tenant}_gold.duckdb en prod."""
    from motoshop_api.metrics.repo_duckdb import _make_db_path

    os.environ["ENV"] = "prod"
    # Clear any env override
    os.environ.pop("DUCKDB_PATH", None)
    try:
        path = _make_db_path("motoshop")
        assert str(path) == "/tmp/motoshop_gold.duckdb"
        path2 = _make_db_path("masvital")
        assert str(path2) == "/tmp/masvital_gold.duckdb"
    finally:
        os.environ["ENV"] = "dev"


def test_make_db_path_dev() -> None:
    """_make_db_path debe usar out/{tenant}_gold.duckdb en dev."""
    from motoshop_api.metrics.repo_duckdb import _make_db_path

    os.environ["ENV"] = "dev"
    os.environ.pop("DUCKDB_PATH", None)
    try:
        path = _make_db_path("motoshop")
        assert str(path) == "out/motoshop_gold.duckdb"
        path2 = _make_db_path("masvital")
        assert str(path2) == "out/masvital_gold.duckdb"
    finally:
        os.environ["ENV"] = "dev"


def test_make_db_path_ignores_global_override_for_tenant_isolation() -> None:
    """A global DUCKDB_PATH must never collapse distinct tenant paths."""
    from motoshop_api.metrics.repo_duckdb import _make_db_path

    os.environ["DUCKDB_PATH"] = "/custom/path/test.duckdb"
    os.environ["ENV"] = "prod"
    try:
        motoshop_path = _make_db_path("motoshop")
        masvital_path = _make_db_path("masvital")
        assert str(motoshop_path) == "/tmp/motoshop_gold.duckdb"
        assert str(masvital_path) == "/tmp/masvital_gold.duckdb"
        assert motoshop_path != masvital_path
    finally:
        os.environ.pop("DUCKDB_PATH", None)
        os.environ["ENV"] = "dev"


def test_duckdb_repo_accepts_tenant() -> None:
    """DuckDBMetricsRepo.__init__ debe aceptar tenant y construir path."""
    # Just verify the constructor signature accepts it.
    # We cannot actually connect without a real DuckDB file, but we
    # verify the parameter is accepted by checking the __init__ signature.
    import inspect

    from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

    sig = inspect.signature(DuckDBMetricsRepo.__init__)
    params = sig.parameters
    assert "tenant" in params, "tenant parameter missing from __init__"
    assert params["tenant"].default == "motoshop", "tenant default should be 'motoshop'"


def test_get_duckdb_repo_accepts_tenant() -> None:
    """get_duckdb_repo factory debe aceptar tenant."""
    import inspect

    from motoshop_api.metrics.repo_duckdb import get_duckdb_repo

    sig = inspect.signature(get_duckdb_repo)
    params = sig.parameters
    assert "tenant" in params, "tenant parameter missing from get_duckdb_repo"
