from __future__ import annotations

import pytest

from motoshop_api.llm.catalog_queries import parse_catalog_list_request


@pytest.mark.parametrize(
    ("message", "abc"),
    [
        ("Lista los productos del catálogo categoría A con stock y acción", "A"),
        ("¿Cuáles son los productos que son de categoría A?", "A"),
        ("Lista productos ABC-A con stock", "A"),
        ("Dame el listado ABC B", "B"),
        ("Muestra los productos categoría C", "C"),
    ],
)
def test_explicit_abc_catalog_lists_use_the_catalog_window(message: str, abc: str) -> None:
    request = parse_catalog_list_request(message)

    assert request is not None
    assert request.abc == abc
    assert request.window_days == 180
    assert request.page == 1
    assert request.page_size == 50


def test_catalog_list_accepts_a_bounded_custom_window_and_page() -> None:
    request = parse_catalog_list_request(
        "Lista top 20 productos ABC A de los últimos 90 días, página 3"
    )

    assert request is not None
    assert request.tool_arguments() == {
        "abc": "A", "window_days": 90, "page": 3, "page_size": 50,
    }


@pytest.mark.parametrize(
    ("message", "estado"),
    [
        ("Lista productos ABC A agotados", "agotado,sin_stock"),
        ("Lista productos ABC-A de quiebre", "agotado,quiebre"),
        ("Lista productos ABC B con sobrestock", "sobrestock"),
        ("Lista productos categoría C dormidos", "dormido"),
    ],
)
def test_catalog_list_preserves_explicit_inventory_state_filters(
    message: str,
    estado: str,
) -> None:
    request = parse_catalog_list_request(message)

    assert request is not None
    assert request.estado == estado
    assert request.tool_arguments()["estado"] == estado


def test_catalog_next_page_inherits_only_the_previous_abc_filter() -> None:
    request = parse_catalog_list_request(
        "Siguiente página",
        inherited_abc="A",
        inherited_page=1,
    )

    assert request is not None
    assert request.abc == "A"
    assert request.page == 2
    assert request.window_days == 180


def test_catalog_next_page_preserves_the_requested_state_filter() -> None:
    request = parse_catalog_list_request(
        "Siguiente página",
        inherited_abc="A",
        inherited_page=2,
        inherited_estado="agotado,sin_stock",
    )

    assert request is not None
    assert request.page == 3
    assert request.estado == "agotado,sin_stock"


@pytest.mark.parametrize(
    "message",
    [
        "¿Qué productos debo reponer?",
        "Analiza el Pareto de productos de agosto",
        "¿Qué significa la categoría A?",
    ],
)
def test_non_catalog_intents_do_not_route_to_an_abc_product_list(message: str) -> None:
    assert parse_catalog_list_request(message) is None


@pytest.mark.parametrize("page,window", [(0, 180), (1001, 180), (1, 29), (1, 721)])
def test_catalog_list_rejects_unbounded_page_or_window(page: int, window: int) -> None:
    request = parse_catalog_list_request(
        f"Lista productos categoría A página {page} últimos {window} días"
    )

    assert request is None
