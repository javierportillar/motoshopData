from __future__ import annotations

from motoshop_api.llm.inventory_queries import parse_replenishment_request


def test_zero_stock_request_routes_to_a_replenishment_shortlist() -> None:
    request = parse_replenishment_request(
        "¿Qué productos no tengo en stock y debería enlistar para mi siguiente compra?"
    )

    assert request is not None
    assert request.tool_arguments() == {
        "target_cover_days": 45,
        "sales_window_days": 180,
        "limit": 50,
    }


def test_replenishment_request_accepts_coverage_and_sales_window() -> None:
    request = parse_replenishment_request(
        "Lista productos sin stock para reponer con 30 días de cobertura según los últimos 90 días"
    )

    assert request is not None
    assert request.target_cover_days == 30
    assert request.sales_window_days == 90


def test_replenishment_request_preserves_named_supplier_filters() -> None:
    camila = parse_replenishment_request(
        "Quiero productos que no tengo en stock para mi siguiente compra a Camila, por favor"
    )
    santo_sano = parse_replenishment_request(
        "Qué productos no tengo en stock y debería enlistar para mi siguiente compra "
        "con el proveedor Santo Sano"
    )

    assert camila is not None
    assert camila.supplier_query == "camila"
    assert camila.tool_arguments()["supplier_query"] == "camila"
    assert santo_sano is not None
    assert santo_sano.supplier_query == "santo sano"


def test_unqualified_inventory_or_purchase_question_does_not_create_a_replenishment_plan() -> None:
    assert parse_replenishment_request("¿Qué productos no tienen stock?") is None
    assert parse_replenishment_request("¿Qué debo comprar para la próxima semana?") is None
