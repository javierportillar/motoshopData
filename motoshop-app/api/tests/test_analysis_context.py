from __future__ import annotations

import duckdb
import pytest
from fastapi import HTTPException

from motoshop_api.llm import analysis_context
from motoshop_api.llm.analysis_context import ANALYSIS_SECTIONS, build_analysis_context


@pytest.fixture
def analysis_db():
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE silver_fact_ventas (business_date DATE, estado_documento VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_compras (business_date DATE, estado_documento VARCHAR)"
    )
    connection.execute("CREATE TABLE gold_mart_inventario_actual (snapshot_date DATE)")
    connection.execute("CREATE TABLE silver_dim_producto (snapshot_date DATE)")
    connection.execute("INSERT INTO silver_fact_ventas VALUES ('2026-09-26', 'B')")
    connection.execute("INSERT INTO silver_fact_compras VALUES ('2026-09-25', 'B')")
    connection.execute("INSERT INTO gold_mart_inventario_actual VALUES ('2026-09-26')")
    connection.execute("INSERT INTO silver_dim_producto VALUES ('2026-09-27')")
    yield connection
    connection.close()


class _AnalysisRepo:
    def get_analisis_balance(self, date_from, date_to, gastos_diarios):
        expenses = round(sum(gastos_diarios.values()), 2)
        return {
            "fecha_inicio": date_from,
            "fecha_fin": date_to,
            "items": [{
                "date": date_from,
                "ventas": 1000,
                "costo_mercancia": 400,
                "gastos_operativos": expenses,
                "ganancia_bruta": 600,
                "ganancia_neta": 600 - expenses,
                "balance_acumulado": 600 - expenses,
            }],
            "total_ventas": 1000,
            "total_costo_mercancia": 400,
            "total_gastos_operativos": expenses,
            "total_ganancia_bruta": 600,
            "total_ganancia_neta": 600 - expenses,
            "margen_bruto_pct": 60,
            "margen_neto_pct": round((600 - expenses) / 10, 2),
        }

    def get_analisis_productos(self, date_from, date_to, limit):
        return {
            "fecha_inicio": date_from,
            "fecha_fin": date_to,
            "total_skus_vendidos": 12,
            "total_skus_comprados": 8,
            "total_revenue": 10_000,
            "total_margen": 3_500,
            "total_unidades": 40,
            "total_unidades_por_medida": {"g": 25, "u": 15},
            "total_compras_periodo": 5_000,
            "margen_promedio_pct": 35,
            "pareto": {"skus_para_80_pct": 3, "pct_skus": 25, "total_skus": 12},
            "top_revenue": [{"cod_producto": "SKU-1", "nom_producto": "Top product", "revenue": 5000}],
            "top_margen": [], "top_unidades": [], "top_compras": [],
            "top_ganadores": [], "top_perdedores": [], "periodo_comparado": None,
        }

    def get_analisis_proveedores(self, date_from, date_to):
        return {
            "fecha_inicio": date_from,
            "fecha_fin": date_to,
            "total_proveedores": 12,
            "total_compras": 5_000,
            "total_ventas_de_proveedores": 10_000,
            "total_margen_de_proveedores": 3_500,
            "concentracion": {"top1_pct": 45, "riesgo": "medio"},
            "pareto": {"prov_para_80_pct": 5},
            "alertas": [],
            "proveedores": [
                {"nombre": f"Supplier {i}", "total_compras": 100 - i}
                for i in range(12)
            ],
        }

    def get_hours_peak(self, date_from, date_to):
        return {
            "hora_pico_facturas": 17,
            "hora_pico_ventas": 8,
            "items": [
                {"hour": 17, "num_facturas": 12, "total_ventas": 1000},
                {"hour": 8, "num_facturas": 4, "total_ventas": 2000},
            ],
        }

    def get_heatmap_dia_hora(self, date_from, date_to):
        return {"cells": [{"dow_label": "SAB", "hora": 12, "num_facturas": 12}]}

    def get_sales_forecast_monthly(self):
        return {
            "current_month": {"month": "2026-09", "projected_amount": 25_000},
            "next_month": {"month": "2026-10", "projected_amount": 27_000, "confidence": "low"},
            "backtest_accuracy": {
                "confidence": "low",
                "sample_months": 3,
                "median_absolute_error_pct": 75.5,
                "note": "Error alto en backtest.",
            },
        }


def test_full_analysis_context_composes_dashboard_data_and_expenses(analysis_db, monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_context,
        "list_gastos",
        lambda **kwargs: [{
            "mes": "2026-09", "categoria": "arriendo", "monto": 300_000,
            "descripcion": "Local",
        }],
    )
    repo = _AnalysisRepo()

    result = build_analysis_context(
        repo,
        analysis_db,
        "motoshop",
        date_from="2026-09-01",
        date_to="2026-09-26",
    )

    assert result["status"] == "complete"
    assert set(result["sections"]) == ANALYSIS_SECTIONS
    assert result["sections"]["balance"]["net_profit_available"] is True
    assert result["sections"]["balance"]["total_operating_expenses"] == 260_000
    assert result["sections"]["productos"]["total_unidades"] is None
    assert result["sections"]["productos"]["total_unidades_mezcladas"] is True
    assert result["sections"]["productos"]["total_unidades_por_medida"] == {"g": 25, "u": 15}
    assert len(result["sections"]["proveedores"]["proveedores"]) == 10
    assert result["sections"]["proveedores"]["proveedores_omitidos"] == 2
    assert result["sections"]["horas_pico"]["hora_pico_facturas"] == 17
    assert result["sections"]["proyeccion"]["backtest_accuracy"]["confidence"] == "low"
    assert len({source["source_id"] for source in result["sources"]}) == len(result["sources"])


def test_missing_expense_service_never_reports_net_profit_as_zero(analysis_db, monkeypatch) -> None:
    def unavailable(**kwargs):
        raise HTTPException(status_code=503, detail="Supabase unavailable")

    monkeypatch.setattr(analysis_context, "list_gastos", unavailable)
    result = build_analysis_context(
        _AnalysisRepo(),
        analysis_db,
        "motoshop",
        date_from="2026-09-01",
        date_to="2026-09-26",
        sections=["balance", "gastos"],
    )

    assert result["status"] == "partial"
    assert result["sections"]["gastos"]["status"] == "unavailable"
    assert result["sections"]["balance"]["net_profit_available"] is False
    assert result["sections"]["balance"]["net_profit"] is None
    assert "no los interpreto como cero" in result["sections"]["gastos"]["message"]


def test_empty_expense_service_is_distinct_from_unavailable(analysis_db, monkeypatch) -> None:
    monkeypatch.setattr(analysis_context, "list_gastos", lambda **kwargs: [])
    result = build_analysis_context(
        _AnalysisRepo(),
        analysis_db,
        "masvital",
        date_from="2026-09-01",
        date_to="2026-09-26",
        sections=["balance", "gastos"],
    )

    assert result["status"] == "complete"
    assert result["sections"]["gastos"]["status"] == "available_empty"
    assert result["sections"]["balance"]["net_profit_available"] is True
    assert result["sections"]["balance"]["total_operating_expenses"] == 0


def test_analysis_context_validates_date_range_and_section_names(analysis_db) -> None:
    with pytest.raises(ValueError, match="anterior o igual"):
        build_analysis_context(
            _AnalysisRepo(),
            analysis_db,
            "motoshop",
            date_from="2026-09-26",
            date_to="2026-09-01",
        )
    with pytest.raises(ValueError, match="Secciones inválidas"):
        build_analysis_context(_AnalysisRepo(), analysis_db, "motoshop", sections=["secret_table"])


def test_analysis_context_uses_masvital_catalog_snapshot_cutoff(analysis_db) -> None:
    cutoffs = analysis_context._analysis_cutoffs(analysis_db, "masvital")
    assert cutoffs["inventory"].isoformat() == "2026-09-27"
