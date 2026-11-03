"""The real ERP repo factories must exist and build without a database.

Why this file exists
--------------------
`get_contadores_repo` has been imported by the invoice engine (since ``b90126c``)
and by the four cash repos, but it was never implemented in
``motoshop_api.erp.numbering``. Every real dependency blew up with
``ImportError`` **before** touching MySQL, so the POS and the cash screens
answered ``500`` at the counter while the suite stayed green: the tests always
override the dependency with the fake repos.

These tests build the five factories the routers depend on **without** any
override and **without** opening a connection: a broken import (or an
eager connection) fails in CI instead of at the sales counter.
"""

from __future__ import annotations

import pytest

from motoshop_api.erp import numbering
from motoshop_api.erp.cash.repo import (
    get_arqueo_repo,
    get_cash_movements_repo,
    get_consignment_repo,
    get_receipts_repo,
)
from motoshop_api.erp.cash.repo import (
    RealArqueoRepo,
    RealCashMovementsRepo,
    RealConsignmentRepo,
    RealReceiptsRepo,
)
from motoshop_api.erp.invoicing.repo import RealInvoicesRepo, get_invoices_repo


@pytest.fixture()
def sin_conexion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempt to reach MySQL fails the test.

    The repos resolve their engine lazily (inside the call that needs it), so
    patching the module attributes is enough to prove the factories only build
    objects.
    """
    from motoshop_api.db import engine as db_engine

    def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "la factory abrio una conexion: debe construir el repo sin tocar MySQL"
        )

    for nombre in ("get_engine", "get_erp_engine", "get_writer_engine"):
        monkeypatch.setattr(db_engine, nombre, prohibido, raising=False)


def test_numbering_exporta_get_contadores_repo() -> None:
    """The missing symbol is the regression this file protects."""
    assert callable(getattr(numbering, "get_contadores_repo", None))


def test_get_contadores_repo_construye_sin_conexion(sin_conexion: None) -> None:
    repo = numbering.get_contadores_repo()

    assert isinstance(repo, (numbering.RealContadoresRepo, numbering.FakeContadoresRepo))
    assert callable(repo.reserve)
    assert callable(repo.resolve_prefix)


def test_get_invoices_repo_construye_sin_conexion(sin_conexion: None) -> None:
    """The POS and the invoice endpoint depend on this one."""
    assert isinstance(get_invoices_repo(), RealInvoicesRepo)


def test_factories_de_caja_construyen_sin_conexion(sin_conexion: None) -> None:
    assert isinstance(get_receipts_repo(), RealReceiptsRepo)
    assert isinstance(get_cash_movements_repo(), RealCashMovementsRepo)
    assert isinstance(get_arqueo_repo(), RealArqueoRepo)
    assert isinstance(get_consignment_repo(), RealConsignmentRepo)
