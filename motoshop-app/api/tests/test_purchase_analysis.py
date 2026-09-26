from __future__ import annotations

import duckdb
import pytest

from motoshop_api.llm.purchase_analysis import (
    analyze_purchase_period,
    evaluate_planned_purchase,
)


@pytest.fixture
def purchase_db():
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE silver_fact_compras (num_documento VARCHAR, cod_clase VARCHAR, "
        "business_date DATE, nombre_proveedor VARCHAR, total_factura DOUBLE, estado_documento VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_compras_detalle (num_documento VARCHAR, cod_clase VARCHAR, "
        "cod_producto VARCHAR, nombre_detalle VARCHAR, cantidad DOUBLE, valor_unitario DOUBLE, "
        "total_detalle DOUBLE, business_date DATE)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_ventas (num_documento VARCHAR, cod_clase VARCHAR, "
        "business_date DATE, estado_documento VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_ventas_detalle (num_documento VARCHAR, cod_clase VARCHAR, "
        "cod_producto VARCHAR, cantidad DOUBLE, total_detalle DOUBLE, business_date DATE)"
    )
    connection.execute(
        "CREATE TABLE silver_dim_producto (cod_producto VARCHAR, nombre_producto VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE gold_mart_inventario_actual (cod_producto VARCHAR, cantidad_actual DOUBLE, snapshot_date DATE)"
    )
    connection.execute(
        "INSERT INTO silver_dim_producto VALUES "
        "('DORM', 'Dormant product'), ('NEW', 'New product'), "
        "('FAST', 'Fast mover'), ('STALE', 'Stale demand product'), ('ALT', 'Alternative fast mover')"
    )
    connection.execute(
        "INSERT INTO silver_fact_compras VALUES "
        "('A1', 'FC', '2026-08-05', 'Supplier', 700, 'B'), "
        "('A2', 'FC', '2026-08-07', 'Supplier', 300, 'B'), "
        "('S1', 'FC', '2026-09-05', 'Supplier', 200, 'B'), "
        "('ALT1', 'FC', '2026-03-01', 'Supplier', 500, 'B')"
    )
    connection.execute(
        "INSERT INTO silver_fact_compras_detalle VALUES "
        "('A1', 'FC', 'DORM', 'Dormant product', 4, 100, 400, '2026-08-05'), "
        "('A2', 'FC', 'NEW', 'New product', 3, 100, 300, '2026-08-07'), "
        "('S1', 'FC', 'DORM', 'Dormant product', 2, 100, 200, '2026-09-05'), "
        "('ALT1', 'FC', 'ALT', 'Alternative fast mover', 5, 100, 500, '2026-03-01')"
    )
    connection.execute(
        "INSERT INTO silver_fact_ventas VALUES "
        "('V0', 'FV', '2025-12-01', 'B'), ('VSTALE', 'FV', '2025-12-01', 'B'), "
        "('V1', 'FV', '2026-08-20', 'B'), "
        "('V2', 'FV', '2026-09-10', 'B'), ('V3', 'FV', '2026-09-12', 'A'), "
        "('VALT', 'FV', '2026-09-14', 'B')"
    )
    connection.execute(
        "INSERT INTO silver_fact_ventas_detalle VALUES "
        "('V0', 'FV', 'DORM', 1, 100, '2025-12-01'), "
        "('VSTALE', 'FV', 'STALE', 1, 100, '2025-12-01'), "
        "('V1', 'FV', 'DORM', 1, 100, '2026-08-20'), "
        "('V2', 'FV', 'DORM', 1, 100, '2026-09-10'), "
        "('V3', 'FV', 'FAST', 99, 9900, '2026-09-12'), "
        "('VALT', 'FV', 'ALT', 90, 9000, '2026-09-14')"
    )
    connection.execute(
        "INSERT INTO gold_mart_inventario_actual VALUES "
        "('DORM', 10, '2026-09-15'), ('NEW', 3, '2026-09-15'), "
        "('FAST', 5, '2026-09-15'), ('STALE', 4, '2026-09-15'), ('ALT', 5, '2026-09-15')"
    )
    yield connection
    connection.close()


def test_historical_audit_distinguishes_dormant_skus_from_new_items(purchase_db) -> None:
    result = analyze_purchase_period(
        purchase_db, "2026-08-01", "2026-09-30", target_cover_days=45
    )

    assert result["status"] == "complete"
    assert result["periodo_parcial"] is True
    assert [row["mes"] for row in result["resumen_por_mes"]] == ["2026-08", "2026-09"]
    august = next(row for row in result["productos"] if row["codigo"] == "DORM" and row["mes"] == "2026-08")
    new_item = next(row for row in result["productos"] if row["codigo"] == "NEW")
    assert august["unidades_vendidas_acumuladas_antes_del_mes"] == 1
    assert august["unidades_vendidas_180d_antes_del_mes"] == 0
    assert august["stock_estimado_al_inicio_del_mes"] == 6
    assert august["unidades_vendidas_despues_de_ultima_compra_del_mes"] == 1
    assert august["evaluacion_de_la_compra"] == "producto_con_historial_sin_rotacion_180d"
    assert new_item["evaluacion_de_la_compra"] == "producto_sin_historial_previo"
    assert result["resumen_por_mes"][0]["productos_sin_historial_previo"] == 1
    assert "no se deben clasificar automáticamente" in result["respuesta_fallback"]


def test_historical_audit_validates_date_order_and_empty_period(purchase_db) -> None:
    with pytest.raises(ValueError, match="date_from"):
        analyze_purchase_period(purchase_db, "2026-09-30", "2026-08-01")

    result = analyze_purchase_period(purchase_db, "2025-01-01", "2025-01-31")

    assert result["status"] == "empty"
    assert result["mensaje"] == "No se encontraron compras válidas en ese período."


def test_planned_purchase_compares_requested_quantity_with_stock_and_velocity(purchase_db) -> None:
    purchase_db.execute(
        "INSERT INTO silver_fact_ventas VALUES ('F1', 'FV', '2026-09-14', 'B')"
    )
    purchase_db.execute(
        "INSERT INTO silver_fact_ventas VALUES ('F2', 'FV', '2026-08-14', 'B')"
    )
    purchase_db.execute(
        "INSERT INTO silver_fact_ventas_detalle VALUES ('F1', 'FV', 'FAST', 90, 9000, '2026-09-14')"
    )
    purchase_db.execute(
        "INSERT INTO silver_fact_ventas_detalle VALUES ('F2', 'FV', 'FAST', 90, 9000, '2026-08-14')"
    )
    result = evaluate_planned_purchase(
        purchase_db,
        [
                {"codigo": "FAST", "nombre": "Fast mover", "cantidad": 15},
                {"codigo": "DORM", "nombre": "Dormant product", "cantidad": 4},
                {"codigo": "NEW", "nombre": "New product", "cantidad": 2},
                {"codigo": "STALE", "nombre": "Stale demand product", "cantidad": 3},
        ],
        target_cover_days=45,
        sales_window_days=180,
    )

    products = {row["codigo"]: row for row in result["productos"]}
    assert products["FAST"]["cantidad_sugerida"] == 40
    assert products["FAST"]["recomendacion"] == "cantidad_insuficiente_para_objetivo"
    assert products["DORM"]["recomendacion"] == "reducir_o_eliminar_por_stock_actual"
    assert products["NEW"]["recomendacion"] == "revisar_sin_historial_de_ventas"
    assert products["STALE"]["recomendacion"] == "revisar_sin_rotacion_en_ventana"
    assert result["resumen"]["unidades_sugeridas"] == 40
    assert result["productos_con_demanda_y_stock_bajo_fuera_de_la_lista"][0]["codigo"] == "ALT"


def test_planned_purchase_rejects_empty_or_oversized_order(purchase_db) -> None:
    with pytest.raises(ValueError, match="al menos un producto"):
        evaluate_planned_purchase(purchase_db, [])
    with pytest.raises(ValueError, match="hasta 50"):
        evaluate_planned_purchase(
            purchase_db,
            [{"codigo": "DORM", "cantidad": 1}] * 51,
        )
