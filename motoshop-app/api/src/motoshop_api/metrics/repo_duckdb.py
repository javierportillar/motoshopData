"""DuckDBMetricsRepo — implementación del protocolo MetricsRepoProtocol sobre DuckDB.

Reemplaza a RealMetricsRepo (Databricks SQL Warehouse) cuando
DATA_BACKEND=duckdb está configurado.

Lee de un archivo DuckDB local (en producción, descargado de R2 al startup).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

from motoshop_api.metrics.repo import MetricsRepoProtocol
from motoshop_api.metrics.schemas import (
    AbcBucket,
    AbcSegmentation,
    BodegaItem,
    CohorteDetailItem,
    CohorteItem,
    CohorteRetencionItem,
    CohortesDetailResponse,
    CohortesResponse,
    DormidoItem,
    DormidosResponse,
    DriftSummaryItem,
    DriftSummaryResponse,
    ForecastCategoriaItem,
    ForecastCategoriaResponse,
    InventorySummary,
    ActionRecommendationItem,
    ActionRecommendationsResponse,
    PlanCompraItem,
    PlanComprasResponse,
    SalesDailyItem,
    SalesDailyResponse,
    SalesHistoricalResponse,
    SalesMonthlyResponse,
    SalesSummary,
    SalesTrendItem,
    SalesTrendResponse,
    TopSkuItem,
    VendedoresSummaryResponse,
    VendedorItem,
)

logger = logging.getLogger(__name__)

# Ruta por defecto — /tmp en Render, out/ local
_DEFAULT_DB_PATH = Path(os.environ.get(
    "DUCKDB_PATH",
    "/tmp/motoshop_gold.duckdb" if os.environ.get("ENV") == "prod" else "out/motoshop_gold.duckdb"
))


class DuckDBMetricsRepo:
    """Lee de archivo DuckDB local usando SQL directo.

    Misma interfaz que RealMetricsRepo pero sin dependencia de Databricks.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path or _DEFAULT_DB_PATH)
        if not self._path.exists():
            raise FileNotFoundError(
                f"DuckDB file not found at {self._path}. "
                "Run 'python pipeline/spike_sales.py' first, or set DUCKDB_PATH."
            )
        self._con = duckdb.connect(str(self._path), read_only=True)
        logger.info("DuckDBMetricsRepo connected to %s", self._path)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _query(self, sql: str, params: list | None = None) -> list[dict]:
        """Ejecuta SQL contra DuckDB y devuelve lista de dicts."""
        if params:
            result = self._con.execute(sql, params)
        else:
            result = self._con.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    # ── Sales Summary ────────────────────────────────────────────────────

    def get_sales_summary(self) -> SalesSummary:
        """Resumen de ventas mes actual vs mes anterior + top 10 SKUs."""
        rows = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM mart_ventas_diarias_sku
            )
            SELECT
                STRFTIME(business_date, '%Y-%m') AS business_month,
                SUM(valor_total) AS ventas_mes,
                SUM(cantidad_total) AS cantidad_total,
                SUM(num_facturas) AS num_facturas,
                ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM mart_ventas_diarias_sku, max_dates
            WHERE business_date >= max_dates.max_date - INTERVAL '60 days'
            GROUP BY STRFTIME(business_date, '%Y-%m')
            ORDER BY business_month DESC
            LIMIT 2
        """)

        top = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM mart_ventas_diarias_sku
            )
            SELECT
                cod_producto, nom_producto,
                SUM(cantidad_total) AS cantidad_total,
                SUM(valor_total) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM mart_ventas_diarias_sku, max_dates
            WHERE business_date >= max_dates.max_date - INTERVAL '30 days'
            GROUP BY cod_producto, nom_producto
            ORDER BY valor_total DESC
            LIMIT 10
        """)

        if not rows:
            logger.warning("No sales data found in DuckDB")
            return SalesSummary(
                business_month="", ventas_mes_actual=0.0, ventas_mes_anterior=0.0,
                delta_porcentual=None, ticket_promedio=0.0, num_facturas=0, top_skus=[],
            )

        mes_actual = rows[0]
        mes_anterior = rows[1] if len(rows) > 1 else None

        va_actual = float(mes_actual["ventas_mes"])
        va_anterior = float(mes_anterior["ventas_mes"]) if mes_anterior else 0.0

        return SalesSummary(
            business_month=str(mes_actual["business_month"]),
            ventas_mes_actual=va_actual,
            ventas_mes_anterior=va_anterior,
            delta_porcentual=round(
                (va_actual - va_anterior) / va_anterior * 100, 1
            ) if mes_anterior and va_anterior else None,
            ticket_promedio=float(mes_actual["ticket_promedio"]),
            num_facturas=int(mes_actual["num_facturas"]),
            top_skus=[TopSkuItem(**r) for r in top],
        )

    # ── Stubs para el resto del protocolo (Sprint 2) ─────────────────────

    def get_sales_daily(self, date: str) -> SalesDailyResponse:
        raise NotImplementedError("Sprint 2")

    def get_sales_monthly(self, month: str) -> SalesMonthlyResponse:
        raise NotImplementedError("Sprint 2")

    def get_sales_historical(self) -> SalesHistoricalResponse:
        raise NotImplementedError("Sprint 2")

    def get_inventory_summary(self) -> InventorySummary:
        raise NotImplementedError("Sprint 2")

    def get_abc_segmentation(self) -> AbcSegmentation:
        raise NotImplementedError("Sprint 2")

    def get_dormidos(self, page: int = 1, page_size: int = 50, sort_by: str = "dias_sin_venta", sort_order: str = "desc") -> DormidosResponse:
        raise NotImplementedError("Sprint 2")

    def get_cohortes(self) -> CohortesResponse:
        raise NotImplementedError("Sprint 2")

    def get_sales_trend(self, periods: int = 6, year: int | None = None) -> SalesTrendResponse:
        raise NotImplementedError("Sprint 2")

    def get_vendedores_summary(self, period: str = "month") -> VendedoresSummaryResponse:
        raise NotImplementedError("Sprint 2")

    def get_vendedor_detail(self, vendedor_id: str, period: str = "month"):
        raise NotImplementedError("Sprint 2")

    def get_cohortes_detail(self) -> CohortesDetailResponse:
        raise NotImplementedError("Sprint 2")

    def get_drift_summary(self) -> DriftSummaryResponse:
        raise NotImplementedError("Sprint 2")

    def get_plan_compras(self) -> PlanComprasResponse:
        raise NotImplementedError("Sprint 2")

    def get_forecast_categoria(self) -> ForecastCategoriaResponse:
        raise NotImplementedError("Sprint 2")


def get_duckdb_repo() -> DuckDBMetricsRepo:
    """Factory para crear DuckDBMetricsRepo con ruta configurable."""
    return DuckDBMetricsRepo()
