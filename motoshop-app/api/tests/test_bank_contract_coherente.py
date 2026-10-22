"""El scraper y el contrato no pueden desincronizarse.

Regresión: al renombrar un campo del contrato (`movements_tab`) el scraper
siguió pidiendo el nombre viejo y el scrape fallaba con `AttributeError` en
tiempo de ejecución, lejos del cambio.
"""

from __future__ import annotations

import dataclasses
import inspect
import re

from motoshop_api.erp.bankreconciliation import scraper
from motoshop_api.erp.bankreconciliation.portal_pages import PortalContract


def _campos_del_contrato() -> set[str]:
    return {campo.name for campo in dataclasses.fields(PortalContract)}


def test_todo_selector_pedido_existe_en_el_contrato() -> None:
    """Cada selector que el scraper pide tiene que existir en el contrato."""
    fuente = inspect.getsource(scraper)
    campos = _campos_del_contrato()

    pedidos = set(re.findall(r"self[.]_contrato[.]([a-z_]+)", fuente))
    pedidos |= set(re.findall(r"_spec[(]\"([a-z_]+)\"[)]", fuente))

    faltantes = {nombre for nombre in pedidos if nombre not in campos}
    assert not faltantes, (
        "el scraper pide selectores que el contrato no define: "
        + ", ".join(sorted(faltantes))
    )


def test_el_scraper_usa_el_resolvedor_de_selectores() -> None:
    """Ningún acceso directo al contrato: todo pasa por `_spec`, que tiene respaldo."""
    fuente = inspect.getsource(scraper.PlaywrightPortalSession)
    directos = re.findall(r"self[.]_contrato[.]([a-z_]+)", fuente)
    assert not directos, (
        "accesos directos al contrato (usar `_spec`): " + ", ".join(sorted(set(directos)))
    )
