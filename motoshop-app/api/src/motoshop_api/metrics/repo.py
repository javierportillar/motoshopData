"""Repositorio de métricas — mock (FakeMetricsRepo) + real (MetricsRepo vía Databricks SQL).

FakeMetricsRepo se usa mientras Dev A construye los gold marts.
Devuelve datos realistas de demo con cifras típicas de una tienda
de repuestos de moto en Colombia (~$50M COP/mes, ~800 facturas/mes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)

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
    PlanCompraItem,
    PlanComprasResponse,
    SalesDailyItem,
    SalesDailyResponse,
    SalesHistoricalResponse,
    SalesMonthlyResponse,
    SalesSummary,
    SalesTrendItem,
    SalesTrendResponse,
    DriftSummaryItem,
    DriftSummaryResponse,
    TopSkuItem,
    VendedorItem,
    VendedoresSummaryResponse,
)


class MetricsRepoProtocol(Protocol):
    """Contrato que cumplen FakeMetricsRepo y RealMetricsRepo."""

    def get_sales_summary(self) -> SalesSummary: ...
    def get_sales_daily(self, date: str) -> SalesDailyResponse: ...
    def get_sales_monthly(self, month: str) -> SalesMonthlyResponse: ...
    def get_sales_historical(self) -> SalesHistoricalResponse: ...
    def get_inventory_summary(self) -> InventorySummary: ...
    def get_abc_segmentation(self) -> AbcSegmentation: ...
    def get_dormidos(self) -> DormidosResponse: ...
    def get_cohortes(self) -> CohortesResponse: ...
    def get_sales_trend(self, periods: int, year: int | None = None) -> SalesTrendResponse: ...
    def get_vendedores_summary(self, period: str = "month") -> VendedoresSummaryResponse: ...
    def get_vendedor_detail(self, vendedor_id: str, period: str = "month") -> VendedorDetailResponse: ...
    def get_cohortes_detail(self) -> CohortesDetailResponse: ...
    def get_drift_summary(self) -> DriftSummaryResponse: ...
    def get_plan_compras(self) -> PlanComprasResponse: ...
    def get_forecast_categoria(self) -> ForecastCategoriaResponse: ...


# ── Fake (mock) ──────────────────────────────────────────────────────────

_MONTH = datetime.now().strftime("%Y-%m")
_this_month = datetime.now().replace(day=1)
_last_month = _this_month - timedelta(days=1)
_LAST_MONTH = _last_month.strftime("%Y-%m")

_TOP_SKUS = [
    TopSkuItem(cod_producto="MOTS1297", nom_producto="ACEITE 20W50 MOTUL 1L", cantidad_total=342.0, valor_total=8_550_000.0, porcentaje_ingreso=17.1),
    TopSkuItem(cod_producto="MOTS0412", nom_producto="FILTRO ACEITE YAMAHA YBR125", cantidad_total=287.0, valor_total=5_740_000.0, porcentaje_ingreso=11.5),
    TopSkuItem(cod_producto="MOTS2109", nom_producto="CADENA TRANSMISION RK 428", cantidad_total=156.0, valor_total=4_680_000.0, porcentaje_ingreso=9.4),
    TopSkuItem(cod_producto="MOTS0834", nom_producto="PASTILLAS FRENO DELANTERAS", cantidad_total=198.0, valor_total=3_960_000.0, porcentaje_ingreso=7.9),
    TopSkuItem(cod_producto="MOTS3512", nom_producto="BUJIA NGK CR8E", cantidad_total=423.0, valor_total=3_807_000.0, porcentaje_ingreso=7.6),
    TopSkuItem(cod_producto="MOTS1723", nom_producto="CUBIERTA PIRELLI 130/70-17", cantidad_total=45.0, valor_total=3_375_000.0, porcentaje_ingreso=6.8),
    TopSkuItem(cod_producto="MOTS0945", nom_producto="BATERIA YUASA YB14L-A2", cantidad_total=67.0, valor_total=2_680_000.0, porcentaje_ingreso=5.4),
    TopSkuItem(cod_producto="MOTS2618", nom_producto="GUAYA ACELERADOR UNIVERSAL", cantidad_total=234.0, valor_total=1_872_000.0, porcentaje_ingreso=3.7),
    TopSkuItem(cod_producto="MOTS4536", nom_producto="CABLE BUJIA SILICONA 90°", cantidad_total=312.0, valor_total=1_560_000.0, porcentaje_ingreso=3.1),
    TopSkuItem(cod_producto="MOTS3689", nom_producto="CANDADO DISCO 90DB", cantidad_total=98.0, valor_total=1_470_000.0, porcentaje_ingreso=2.9),
]

_BODEGAS = [
    BodegaItem(cod_bodega="B001", nom_bodega="Bodega Central", cantidad=12_450.0, porcentaje=38.5),
    BodegaItem(cod_bodega="B002", nom_bodega="Bodega Norte", cantidad=8_230.0, porcentaje=25.4),
    BodegaItem(cod_bodega="B003", nom_bodega="Bodega Sur", cantidad=5_670.0, porcentaje=17.5),
    BodegaItem(cod_bodega="B004", nom_bodega="Bodega Occidente", cantidad=3_980.0, porcentaje=12.3),
    BodegaItem(cod_bodega="B005", nom_bodega="Bodega Oriente", cantidad=2_040.0, porcentaje=6.3),
]

_DORMIDOS = [
    DormidoItem(cod_producto="MOTS9912", nom_producto="ESCAPE DEPORTIVO AKRAPOVIC", dias_sin_venta=187, stock_actual=3.0),
    DormidoItem(cod_producto="MOTS8745", nom_producto="ASIENTO GEL YAMAHA MT09", dias_sin_venta=156, stock_actual=2.0),
    DormidoItem(cod_producto="MOTS7634", nom_producto="KIT TRANSMISION DID 530", dias_sin_venta=134, stock_actual=5.0),
    DormidoItem(cod_producto="MOTS6523", nom_producto="FARO LED PROYECTOR 7\"", dias_sin_venta=112, stock_actual=8.0),
    DormidoItem(cod_producto="MOTS5412", nom_producto="MANILLAR CRUISER 1\"", dias_sin_venta=98, stock_actual=12.0),
    DormidoItem(cod_producto="MOTS4301", nom_producto="DEFENSA TRASERA HONDA XR190", dias_sin_venta=95, stock_actual=4.0),
]


class FakeMetricsRepo:
    """Devuelve datos mock realistas mientras no existan gold marts."""

    def get_sales_summary(self) -> SalesSummary:
        ventas_actual = 50_120_000.0
        ventas_anterior = 47_830_000.0
        return SalesSummary(
            business_month=_MONTH,
            ventas_mes_actual=ventas_actual,
            ventas_mes_anterior=ventas_anterior,
            delta_porcentual=round((ventas_actual - ventas_anterior) / ventas_anterior * 100, 1),
            ticket_promedio=62_650.0,
            num_facturas=823,
            top_skus=_TOP_SKUS,
        )

    def get_sales_daily(self, date: str) -> SalesDailyResponse:
        return SalesDailyResponse(
            date=date,
            total_ventas=1_850_000.0,
            total_facturas=28,
            productos_vendidos=[
                SalesDailyItem(sku="MOTS1297", nombre="ACEITE 20W50 MOTUL 1L", cantidad=12.0, valor=300_000.0),
                SalesDailyItem(sku="MOTS0412", nombre="FILTRO ACEITE YAMAHA YBR125", cantidad=8.0, valor=160_000.0),
            ],
        )

    def get_sales_monthly(self, month: str) -> SalesMonthlyResponse:
        return SalesMonthlyResponse(
            month=month,
            total_ventas=50_120_000.0,
            total_facturas=823,
            delta_porcentaje=4.8,
            productos_top=_TOP_SKUS,
        )

    def get_sales_historical(self) -> SalesHistoricalResponse:
        now = datetime.now()
        meses = [
            SalesTrendItem(year=now.year, month=m, total_ventas=48_000_000.0 + m * 200_000.0, num_facturas=780 + m, ticket_promedio=62_000.0 + m * 100.0)
            for m in range(1, now.month + 1)
        ]
        return SalesHistoricalResponse(
            total_ventas=sum(m.total_ventas for m in meses),
            total_facturas=sum(m.num_facturas for m in meses),
            meses=meses,
            fecha_primera_venta=f"{now.year - 3}-01-15",
        )

    def get_inventory_summary(self) -> InventorySummary:
        total = sum(b.cantidad for b in _BODEGAS)
        valor = 132_450_000.0
        return InventorySummary(
            stock_total=total,
            valor_total=valor,
            num_productos=4_217,
            por_bodega=_BODEGAS,
        )

    def get_abc_segmentation(self) -> AbcSegmentation:
        return AbcSegmentation(
            business_month=_MONTH,
            total_skus=4_217,
            total_ingresos=50_120_000.0,
            bucket_a=AbcBucket(categoria="A", num_skus=278, valor_total=40_096_000.0, porcentaje_ingreso=80.0),
            bucket_b=AbcBucket(categoria="B", num_skus=634, valor_total=7_518_000.0, porcentaje_ingreso=15.0),
            bucket_c=AbcBucket(categoria="C", num_skus=3_305, valor_total=2_506_000.0, porcentaje_ingreso=5.0),
        )

    def get_dormidos(self) -> DormidosResponse:
        return DormidosResponse(total=len(_DORMIDOS), productos=_DORMIDOS)

    def get_cohortes(self) -> CohortesResponse:
        return CohortesResponse(cohortes=[
            CohorteItem(cohorte_mes="2026-01", mes_observacion="2026-01", num_clientes=45, ticket_promedio=48_200.0, tasa_recurrencia=0.0),
            CohorteItem(cohorte_mes="2026-01", mes_observacion="2026-02", num_clientes=45, ticket_promedio=52_100.0, tasa_recurrencia=0.22),
            CohorteItem(cohorte_mes="2026-01", mes_observacion="2026-03", num_clientes=45, ticket_promedio=55_800.0, tasa_recurrencia=0.18),
            CohorteItem(cohorte_mes="2026-01", mes_observacion="2026-04", num_clientes=45, ticket_promedio=49_500.0, tasa_recurrencia=0.15),
            CohorteItem(cohorte_mes="2026-02", mes_observacion="2026-02", num_clientes=38, ticket_promedio=51_300.0, tasa_recurrencia=0.0),
            CohorteItem(cohorte_mes="2026-02", mes_observacion="2026-03", num_clientes=38, ticket_promedio=53_700.0, tasa_recurrencia=0.21),
            CohorteItem(cohorte_mes="2026-02", mes_observacion="2026-04", num_clientes=38, ticket_promedio=50_100.0, tasa_recurrencia=0.16),
            CohorteItem(cohorte_mes="2026-03", mes_observacion="2026-03", num_clientes=52, ticket_promedio=46_800.0, tasa_recurrencia=0.0),
            CohorteItem(cohorte_mes="2026-03", mes_observacion="2026-04", num_clientes=52, ticket_promedio=48_900.0, tasa_recurrencia=0.19),
            CohorteItem(cohorte_mes="2026-04", mes_observacion="2026-04", num_clientes=41, ticket_promedio=50_600.0, tasa_recurrencia=0.0),
        ])

    def get_sales_trend(self, periods: int = 6, year: int | None = None) -> SalesTrendResponse:
        """Genera tendencia mensual mock con leve crecimiento."""
        items: list[SalesTrendItem] = []
        now = datetime.now()
        for i in range(periods - 1, -1, -1):
            d = (now.replace(day=1) - timedelta(days=i * 31)).replace(day=1)
            if year is not None and d.year != year:
                continue
            items.append(SalesTrendItem(
                year=d.year, month=d.month,
                total_ventas=48_000_000.0 + (periods - 1 - i) * 500_000.0,
                num_facturas=780 + (periods - 1 - i) * 8,
                ticket_promedio=62_000.0 + (periods - 1 - i) * 150.0,
            ))
        return SalesTrendResponse(periods=periods, items=items)

    def get_vendedores_summary(self, period: str = "month") -> VendedoresSummaryResponse:
        """Top 10 vendedores con cifras mock. period: month | historical | 6months."""
        escala = {"month": 1, "historical": 12, "6months": 6}.get(period, 1)
        return VendedoresSummaryResponse(items=[
            VendedorItem(
                nit_vendedor="900123456-7", nombre_vendedor="Carlos MotoPartes",
                facturas=int(215 * escala), total_ventas=18_500_000.0 * escala, ticket_promedio=86_046.0,
            ),
            VendedorItem(
                nit_vendedor="900234567-8", nombre_vendedor="María Repuestos",
                facturas=int(178 * escala), total_ventas=14_200_000.0 * escala, ticket_promedio=79_775.0,
            ),
            VendedorItem(
                nit_vendedor="900345678-9", nombre_vendedor="Juan Talleres",
                facturas=int(142 * escala), total_ventas=10_800_000.0 * escala, ticket_promedio=76_056.0,
            ),
            VendedorItem(
                nit_vendedor="900456789-0", nombre_vendedor="Ana Lubricantes",
                facturas=int(98 * escala), total_ventas=5_620_000.0 * escala, ticket_promedio=57_346.0,
            ),
            VendedorItem(
                nit_vendedor="900567890-1", nombre_vendedor="Pedro Accesorios",
                facturas=int(67 * escala), total_ventas=3_450_000.0 * escala, ticket_promedio=51_492.0,
            ),
        ])

    def get_vendedor_detail(self, vendedor_id: str, period: str = "month") -> VendedorDetailResponse:
        """Detalle de un vendedor específico con datos mock."""
        vendedores = {
            "900123456-7": ("Carlos MotoPartes", [
                ("LLANTAS", 8_500_000.0), ("ACEITES", 5_200_000.0), ("FRENOS", 3_100_000.0), ("SUSPENSIÓN", 1_700_000.0),
            ]),
            "900234567-8": ("María Repuestos", [
                ("MOTORES", 6_200_000.0), ("TRANSMISIÓN", 4_100_000.0), ("ELÉCTRICO", 2_500_000.0), ("FILTROS", 1_400_000.0),
            ]),
            "900345678-9": ("Juan Talleres", [
                ("SUSPENSIÓN", 4_800_000.0), ("DIRECCIÓN", 3_200_000.0), ("FRENOS", 1_900_000.0), ("ESCAPE", 900_000.0),
            ]),
            "900456789-0": ("Ana Lubricantes", [
                ("ACEITES", 2_800_000.0), ("FILTROS", 1_500_000.0), ("LÍQUIDOS", 820_000.0), ("LUBRICANTES", 500_000.0),
            ]),
            "900567890-1": ("Pedro Accesorios", [
                ("ILUMINACIÓN", 1_200_000.0), ("SONIDO", 950_000.0), ("TAPIZADOS", 700_000.0), ("EMBLEMAS", 600_000.0),
            ]),
        }
        info = vendedores.get(vendedor_id, ("Vendedor no encontrado", [("GENÉRICO", 0.0)]))
        nombre, categorias = info
        escala = {"month": 1, "historical": 12, "6months": 6}.get(period, 1)
        total = sum(c[1] for c in categorias) * escala
        anterior = total * 0.85
        return VendedorDetailResponse(
            vendedor_id=vendedor_id,
            nombre=nombre,
            ventas_total=total,
            ventas_por_categoria=[VendedorCategoriaItem(categoria=c[0], total=c[1] * escala) for c in categorias],
            ticket_promedio=round(total / 150, 2),
            productos_vendidos=int(45 * escala),
            comparacion_mes_anterior=VendedorComparacion(
                actual=total, anterior=anterior,
                delta=round((total - anterior) / anterior * 100, 1),
            ),
        )

    def get_cohortes_detail(self) -> CohortesDetailResponse:
        """Detalle agregado de cohortes: LTV, retención por mes, nuevos vs recurrentes."""
        cohortes = [
            CohorteDetailItem(
                cohorte_mes="2026-01", total_clientes=45,
                ltv_promedio=51500.0,
                retencion=[
                    CohorteRetencionItem(mes_observacion="2026-01", num_clientes=45, tasa_recurrencia=0.0),
                    CohorteRetencionItem(mes_observacion="2026-02", num_clientes=10, tasa_recurrencia=0.22),
                    CohorteRetencionItem(mes_observacion="2026-03", num_clientes=8, tasa_recurrencia=0.18),
                    CohorteRetencionItem(mes_observacion="2026-04", num_clientes=7, tasa_recurrencia=0.15),
                ],
            ),
            CohorteDetailItem(
                cohorte_mes="2026-02", total_clientes=38,
                ltv_promedio=51700.0,
                retencion=[
                    CohorteRetencionItem(mes_observacion="2026-02", num_clientes=38, tasa_recurrencia=0.0),
                    CohorteRetencionItem(mes_observacion="2026-03", num_clientes=8, tasa_recurrencia=0.21),
                    CohorteRetencionItem(mes_observacion="2026-04", num_clientes=6, tasa_recurrencia=0.16),
                ],
            ),
            CohorteDetailItem(
                cohorte_mes="2026-03", total_clientes=52,
                ltv_promedio=47800.0,
                retencion=[
                    CohorteRetencionItem(mes_observacion="2026-03", num_clientes=52, tasa_recurrencia=0.0),
                    CohorteRetencionItem(mes_observacion="2026-04", num_clientes=10, tasa_recurrencia=0.19),
                ],
            ),
            CohorteDetailItem(
                cohorte_mes="2026-04", total_clientes=41,
                ltv_promedio=50600.0,
                retencion=[
                    CohorteRetencionItem(mes_observacion="2026-04", num_clientes=41, tasa_recurrencia=0.0),
                ],
            ),
            CohorteDetailItem(
                cohorte_mes="2026-05", total_clientes=35,
                ltv_promedio=49200.0,
                retencion=[
                    CohorteRetencionItem(mes_observacion="2026-05", num_clientes=35, tasa_recurrencia=0.0),
                ],
            ),
        ]
        return CohortesDetailResponse(
            cohortes=cohortes,
            total_cohortes=len(cohortes),
            nuevos_este_mes=35,
            recurrentes_este_mes=47,
            top_recurrentes=12,
        )

    def get_drift_summary(self) -> DriftSummaryResponse:
        """Alertas de drift con severidad y acciones recomendadas mock."""
        items = [
            DriftSummaryItem(
                metric_name="WAPE baseline", detected_at="2026-05-28",
                drift_magnitude=3.2, threshold=30.0, status="warning",
                recommended_action="Monitorear. Si supera 30%, re-entrenar baseline.",
            ),
            DriftSummaryItem(
                metric_name="Ventas diarias promedio", detected_at="2026-05-20",
                drift_magnitude=2.1, threshold=30.0, status="resolved",
                recommended_action="Volvió a rango normal. Sin acción requerida.",
            ),
            DriftSummaryItem(
                metric_name="Cobertura forecast", detected_at="2026-05-15",
                drift_magnitude=5.8, threshold=30.0, status="warning",
                recommended_action="Cayó 5.8pp. Verificar nuevos SKUs sin forecast.",
            ),
            DriftSummaryItem(
                metric_name="Tasa recurrencia", detected_at="2026-05-10",
                drift_magnitude=1.4, threshold=30.0, status="resolved",
                recommended_action="Sin acción requerida.",
            ),
        ]
        active = sum(1 for i in items if i.status == "active")
        warning = sum(1 for i in items if i.status == "warning")
        return DriftSummaryResponse(
            items=items,
            total_alerts=len(items),
            active_count=active,
            warning_count=warning,
            current_threshold=30.0,
        )

    def get_plan_compras(self) -> PlanComprasResponse:
        """Plan de compras mock: SKUs con stock bajo vs demanda."""
        items = [
            PlanCompraItem(sku="MOTS1297", nombre="ACEITE 20W50 MOTUL 1L", stock_actual=2, demanda_7d=18, cantidad_a_comprar=16, abc="A", urgencia="alta", dormido=False, supplier="Motul Colombia"),
            PlanCompraItem(sku="MOTS0412", nombre="FILTRO ACEITE YAMAHA YBR125", stock_actual=0, demanda_7d=12, cantidad_a_comprar=12, abc="A", urgencia="alta", dormido=False, supplier="Yamaha Parts SA"),
            PlanCompraItem(sku="MOTS0834", nombre="PASTILLAS FRENO DELANTERAS", stock_actual=3, demanda_7d=10, cantidad_a_comprar=7, abc="A", urgencia="media", dormido=False, supplier="Brembo Colombia"),
            PlanCompraItem(sku="MOTS2109", nombre="CADENA TRANSMISION RK 428", stock_actual=1, demanda_7d=8, cantidad_a_comprar=7, abc="B", urgencia="media", dormido=False, supplier="RK Japan"),
            PlanCompraItem(sku="MOTS3512", nombre="BUJIA NGK CR8E", stock_actual=5, demanda_7d=12, cantidad_a_comprar=7, abc="A", urgencia="baja", dormido=False, supplier="NGK Colombia"),
            PlanCompraItem(sku="MOTS8745", nombre="ASIENTO GEL YAMAHA MT09", stock_actual=2, demanda_7d=1, cantidad_a_comprar=0, abc="C", urgencia=None, dormido=True, supplier="Yamaha Parts SA"),
            PlanCompraItem(sku="MOTS9912", nombre="ESCAPE DEPORTIVO AKRAPOVIC", stock_actual=3, demanda_7d=0, cantidad_a_comprar=0, abc="C", urgencia=None, dormido=True, supplier="Akrapovic EU"),
        ]
        total_unidades = sum(i.cantidad_a_comprar for i in items)
        return PlanComprasResponse(
            items=items,
            total_skus=len(items),
            total_unidades=total_unidades,
            total_valor_estimado=total_unidades * 75_000.0,
            skus_urgentes=sum(1 for i in items if i.urgencia == "alta"),
            skus_dormidos=sum(1 for i in items if i.dormido),
        )

    def get_forecast_categoria(self) -> ForecastCategoriaResponse:
        """Forecast por categoría con WAPE mock."""
        items = [
            ForecastCategoriaItem(cod_grupo="IV2", demanda_real=850.0, demanda_predicha=765.0, desviacion_pct=10.0, metodo="media_movil_28d"),
            ForecastCategoriaItem(cod_grupo="IV1", demanda_real=120.0, demanda_predicha=110.0, desviacion_pct=8.3, metodo="media_movil_28d"),
            ForecastCategoriaItem(cod_grupo="SIN_GRUPO", demanda_real=45.0, demanda_predicha=38.0, desviacion_pct=15.6, metodo="media_movil_28d"),
        ]
        wape = sum(abs(i.demanda_real - i.demanda_predicha) for i in items) / sum(i.demanda_real for i in items) * 100
        return ForecastCategoriaResponse(
            items=items,
            total_categorias=len(items),
            wape_promedio=round(wape, 2),
            cobertura_pct=99.9,
        )


# ── Helpers ──────────────────────────────────────────────────────────────

def _prev_month_str(month: str) -> str:
    """Retorna el mes anterior en formato YYYY-MM."""
    from datetime import datetime
    d = datetime.strptime(month, "%Y-%m")
    if d.month == 1:
        d = d.replace(year=d.year - 1, month=12)
    else:
        d = d.replace(month=d.month - 1)
    return d.strftime("%Y-%m")


# ── Real (Databricks SQL Warehouse vía SDK) ──────────────────────────────

class RealMetricsRepo:
    """Lee de marts gold reales vía Databricks SQL Warehouse (SDK statement execution).

    Usa databricks-sdk en vez de databricks-sql-connector porque la
    conexión directa SSL tiene issues con certificados self-signed.
    """

    def __init__(self, workspace_client, warehouse_id: str) -> None:
        self._w = workspace_client
        self._wh_id = warehouse_id

    def get_sales_summary(self) -> SalesSummary:
        # Use max available date instead of CURRENT_DATE() for demo data compatibility
        rows = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM motoshop.gold.mart_ventas_diarias_sku
            )
            SELECT
                DATE_FORMAT(business_date, 'yyyy-MM') AS business_month,
                SUM(valor_total) AS ventas_mes,
                SUM(cantidad_total) AS cantidad_total,
                SUM(num_facturas) AS num_facturas,
                ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop.gold.mart_ventas_diarias_sku, max_dates
            WHERE business_date >= DATE_SUB(max_dates.max_date, 60)
            GROUP BY DATE_FORMAT(business_date, 'yyyy-MM')
            ORDER BY business_month DESC
            LIMIT 2
        """)
        top = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM motoshop.gold.mart_ventas_diarias_sku
            )
            SELECT
                cod_producto, nom_producto,
                SUM(cantidad_total) AS cantidad_total,
                SUM(valor_total) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop.gold.mart_ventas_diarias_sku, max_dates
            WHERE business_date >= DATE_SUB(max_dates.max_date, 30)
            GROUP BY cod_producto, nom_producto
            ORDER BY valor_total DESC
            LIMIT 10
        """)
        if not rows:
            logger.warning("No sales data found in gold mart")
            return FakeMetricsRepo().get_sales_summary()
        mes_actual, mes_anterior = rows[0], rows[1] if len(rows) > 1 else None
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

    def get_sales_daily(self, date: str) -> SalesDailyResponse:
        productos = self._query(f"""
            SELECT
                cod_producto AS sku,
                nom_producto AS nombre,
                SUM(cantidad_total) AS cantidad,
                ROUND(SUM(valor_total), 2) AS valor
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE business_date = '{date}'
            GROUP BY cod_producto, nom_producto
            ORDER BY valor DESC
        """)
        totals = self._query(f"""
            SELECT
                ROUND(SUM(valor_total), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE business_date = '{date}'
        """)
        if not totals:
            raise RuntimeError(f"No sales data found for date {date}")
        t = totals[0]
        return SalesDailyResponse(
            date=date,
            total_ventas=float(t["total_ventas"]),
            total_facturas=int(t["total_facturas"]),
            productos_vendidos=[SalesDailyItem(**r) for r in productos],
        )

    def get_sales_monthly(self, month: str) -> SalesMonthlyResponse:
        totals = self._query(f"""
            SELECT
                ROUND(SUM(valor_total), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE DATE_FORMAT(business_date, 'yyyy-MM') = '{month}'
        """)
        prev_month = self._query(f"""
            SELECT ROUND(SUM(valor_total), 2) AS total_ventas
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE DATE_FORMAT(business_date, 'yyyy-MM') = '{_prev_month_str(month)}'
        """)
        top = self._query(f"""
            SELECT
                cod_producto AS cod_producto,
                nom_producto AS nom_producto,
                SUM(cantidad_total) AS cantidad_total,
                ROUND(SUM(valor_total), 2) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE DATE_FORMAT(business_date, 'yyyy-MM') = '{month}'
            GROUP BY cod_producto, nom_producto
            ORDER BY valor_total DESC
            LIMIT 10
        """)
        if not totals:
            raise RuntimeError(f"No sales data found for month {month}")
        t = totals[0]
        va_actual = float(t["total_ventas"])
        va_anterior = float(prev_month[0]["total_ventas"]) if prev_month else 0.0
        delta = round((va_actual - va_anterior) / va_anterior * 100, 1) if va_anterior else None
        return SalesMonthlyResponse(
            month=month,
            total_ventas=va_actual,
            total_facturas=int(t["total_facturas"]),
            delta_porcentaje=delta,
            productos_top=[TopSkuItem(**r) for r in top],
        )

    def get_sales_historical(self) -> SalesHistoricalResponse:
        totals = self._query("""
            SELECT
                ROUND(SUM(valor_total), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM motoshop.gold.mart_ventas_diarias_sku
        """)
        meses = self._query("""
            SELECT YEAR(business_date) AS year,
                   MONTH(business_date) AS month,
                   ROUND(SUM(valor_total), 2) AS total_ventas,
                   COALESCE(SUM(num_facturas), 0) AS num_facturas,
                   ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop.gold.mart_ventas_diarias_sku
            GROUP BY YEAR(business_date), MONTH(business_date)
            ORDER BY year, month
        """)
        first = self._query("""
            SELECT MIN(business_date) AS first_date
            FROM motoshop.gold.mart_ventas_diarias_sku
        """)
        if not totals or not meses:
            raise RuntimeError("No historical sales data found")
        t = totals[0]
        fecha_primera = str(first[0]["first_date"]) if first and first[0].get("first_date") else None
        return SalesHistoricalResponse(
            total_ventas=float(t["total_ventas"]),
            total_facturas=int(t["total_facturas"]),
            meses=[SalesTrendItem(**r) for r in meses],
            fecha_primera_venta=fecha_primera,
        )

    def get_inventory_summary(self) -> InventorySummary:
        rows = self._query("""
            SELECT
                SUM(cantidad_actual) AS stock_total,
                COUNT(DISTINCT cod_producto) AS num_productos
            FROM motoshop.gold.mart_inventario_actual
        """)
        valor = self._query("""
            WITH latest_cost AS (
                SELECT cod_producto, costo_producto,
                       ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) AS rn
                FROM motoshop.silver.fact_compras_detalle
                WHERE costo_producto > 0
            )
            SELECT COALESCE(ROUND(SUM(i.cantidad_actual * COALESCE(lc.costo_producto, 0)), 2), 0) AS valor_total
            FROM motoshop.gold.mart_inventario_actual i
            LEFT JOIN latest_cost lc ON i.cod_producto = lc.cod_producto AND lc.rn = 1
        """)
        bodegas = self._query("""
            SELECT
                cod_bodega,
                COALESCE(nom_bodega, CONCAT('Bodega ', cod_bodega)) AS nom_bodega,
                SUM(cantidad_actual) AS cantidad,
                ROUND(SUM(cantidad_actual) / NULLIF(SUM(SUM(cantidad_actual)) OVER(), 0) * 100, 1) AS porcentaje
            FROM motoshop.gold.mart_inventario_actual
            GROUP BY cod_bodega, nom_bodega
            ORDER BY cantidad DESC
        """)
        if not rows:
            raise RuntimeError("No inventory data found in gold mart")
        r = rows[0]
        valor_total = float(valor[0]["valor_total"])
        return InventorySummary(
            stock_total=float(r["stock_total"]),
            valor_total=valor_total,
            num_productos=int(r["num_productos"]),
            por_bodega=[BodegaItem(**b) for b in bodegas],
        )

    def get_abc_segmentation(self) -> AbcSegmentation:
        buckets = self._query("""
            WITH max_month AS (
                SELECT MAX(business_month) AS mm FROM motoshop.gold.mart_rotacion_abc
            )
            SELECT max_month.mm AS business_month,
                   categoria_abc AS categoria, COUNT(*) AS num_skus,
                   SUM(valor_total) AS valor_total,
                   ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop.gold.mart_rotacion_abc, max_month
            WHERE business_month = max_month.mm
            GROUP BY categoria_abc, max_month.mm
            ORDER BY CASE categoria_abc WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END
        """)
        if not buckets:
            logger.warning("No ABC data found in gold mart")
            return FakeMetricsRepo().get_abc_segmentation()
        for b in buckets:
            b["num_skus"] = int(b["num_skus"])
            b["valor_total"] = float(b["valor_total"])
            b["porcentaje_ingreso"] = float(b["porcentaje_ingreso"])
        by_cat = {b["categoria"]: b for b in buckets}
        return AbcSegmentation(
            business_month=str(buckets[0].get("business_month", "")),
            total_skus=sum(b["num_skus"] for b in buckets),
            total_ingresos=sum(b["valor_total"] for b in buckets),
            bucket_a=AbcBucket(**by_cat.get("A", {"categoria": "A", "num_skus": 0, "valor_total": 0, "porcentaje_ingreso": 0})),
            bucket_b=AbcBucket(**by_cat.get("B", {"categoria": "B", "num_skus": 0, "valor_total": 0, "porcentaje_ingreso": 0})),
            bucket_c=AbcBucket(**by_cat.get("C", {"categoria": "C", "num_skus": 0, "valor_total": 0, "porcentaje_ingreso": 0})),
        )

    def get_dormidos(self) -> DormidosResponse:
        rows = self._query("""
            SELECT cod_producto, nom_producto, dias_sin_venta, stock_actual
            FROM motoshop.gold.mart_productos_dormidos
            ORDER BY dias_sin_venta DESC
            LIMIT 500
        """)
        if not rows:
            logger.warning("No dormidos data found in gold mart")
            return FakeMetricsRepo().get_dormidos()
        for r in rows:
            r["dias_sin_venta"] = int(r["dias_sin_venta"])
            r["stock_actual"] = float(r["stock_actual"])
        return DormidosResponse(total=len(rows), productos=[DormidoItem(**r) for r in rows])

    @staticmethod
    def _fill_month_gaps(rows: list[dict]) -> list[dict]:
        """Rellena meses faltantes con ceros para evitar huecos en la serie.

        Para cada mes_cohorte existente, asegura observaciones continuas
        desde su primer mes observado hasta el último.
        """
        if not rows:
            return rows

        from collections import defaultdict

        # Agrupar observaciones por cohorte
        by_cohort: dict[str, dict[str, dict]] = defaultdict(dict)
        all_months: set[str] = set()
        for r in rows:
            cm = r["cohorte_mes"]
            mo = r["mes_observacion"]
            by_cohort[cm][mo] = r
            all_months.add(cm)
            all_months.add(mo)

        if len(all_months) < 2:
            return rows

        # Generar todos los meses en orden
        from datetime import datetime

        def _iter_months(start: str, end: str) -> list[str]:
            months = []
            d = datetime.strptime(start, "%Y-%m")
            end_dt = datetime.strptime(end, "%Y-%m")
            while d <= end_dt:
                months.append(d.strftime("%Y-%m"))
                if d.month == 12:
                    d = d.replace(year=d.year + 1, month=1)
                else:
                    d = d.replace(month=d.month + 1)
            return months

        sorted_months = sorted(all_months)
        full_series = _iter_months(sorted_months[0], sorted_months[-1])

        result: list[dict] = []
        for cm in sorted(by_cohort):
            obs = by_cohort[cm]
            obs_months = sorted(obs.keys())
            for mo in full_series:
                if mo < cm:
                    continue  # observacion no puede ser anterior al cohorte
                if mo > obs_months[-1]:
                    break  # no generar mas alla del maximo observado para este cohorte
                if mo in obs:
                    result.append(obs[mo])
                else:
                    result.append({
                        "cohorte_mes": cm,
                        "mes_observacion": mo,
                        "num_clientes": 0,
                        "ticket_promedio": 0.0,
                        "tasa_recurrencia": None,
                        "muestra_pequena": True,
                    })

        return result

    def get_cohortes(self) -> CohortesResponse:
        rows = self._query("""
            SELECT
                mes_cohorte AS cohorte_mes,
                business_month AS mes_observacion,
                COUNT(DISTINCT nit_cliente) AS num_clientes,
                ROUND(AVG(ticket_promedio), 2) AS ticket_promedio,
                ROUND(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS tasa_recurrencia
            FROM motoshop.gold.mart_cohortes_clientes
            GROUP BY mes_cohorte, business_month
            ORDER BY mes_cohorte, business_month
        """)
        if not rows:
            logger.warning("No cohortes data found in gold mart")
            return FakeMetricsRepo().get_cohortes()
        for r in rows:
            r["num_clientes"] = int(r["num_clientes"])
            r["ticket_promedio"] = float(r["ticket_promedio"])
            r["tasa_recurrencia"] = float(r["tasa_recurrencia"])
            r["muestra_pequena"] = r["num_clientes"] < 5
        filled = self._fill_month_gaps(rows)
        # Set muestra_pequena on gap-filled entries
        for r in filled:
            if "muestra_pequena" not in r:
                r["muestra_pequena"] = r["num_clientes"] < 5
        return CohortesResponse(cohortes=[CohorteItem(**r) for r in filled])

    def get_sales_trend(self, periods: int = 6, year: int | None = None) -> SalesTrendResponse:
        where_year = ""
        if year is not None:
            where_year = f"AND YEAR(business_date) = {year}"
        rows = self._query(f"""
            SELECT YEAR(business_date) AS year,
                   MONTH(business_date) AS month,
                   ROUND(SUM(valor_total), 2) AS total_ventas,
                   SUM(num_facturas) AS num_facturas,
                   ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE business_date >= ADD_MONTHS(CURRENT_DATE(), -{periods})
            {where_year}
            GROUP BY YEAR(business_date), MONTH(business_date)
            ORDER BY year, month
        """)
        if not rows:
            logger.warning("No sales trend data found in gold.mart_ventas_diarias_sku")
            return FakeMetricsRepo().get_sales_trend(periods)
        for r in rows:
            r["year"] = int(r["year"])
            r["month"] = int(r["month"])
            r["total_ventas"] = float(r["total_ventas"])
            r["num_facturas"] = int(r["num_facturas"])
            r["ticket_promedio"] = float(r["ticket_promedio"])
        return SalesTrendResponse(periods=periods, items=[SalesTrendItem(**r) for r in rows])

    def get_vendedores_summary(self, period: str = "month") -> VendedoresSummaryResponse:
        where = {
            "month": "business_date >= DATE_TRUNC('MONTH', CURRENT_DATE())",
            "historical": "1 = 1",
            "6months": "business_date >= DATE_ADD(CURRENT_DATE(), -180)",
        }.get(period, "business_date >= DATE_TRUNC('MONTH', CURRENT_DATE())")
        rows = self._query(f"""
            SELECT nit_vendedor, nombre_vendedor,
                   COUNT(*) AS facturas,
                   SUM(total_factura) AS total_ventas,
                   AVG(total_factura) AS ticket_promedio
            FROM motoshop.silver.fact_ventas
            WHERE {where}
            GROUP BY nit_vendedor, nombre_vendedor
            ORDER BY total_ventas DESC
            LIMIT 10
        """)
        if not rows:
            logger.warning("No vendedores data found in silver.fact_ventas")
            return FakeMetricsRepo().get_vendedores_summary(period)
        for r in rows:
            r["facturas"] = int(r["facturas"])
            r["total_ventas"] = float(r["total_ventas"])
            r["ticket_promedio"] = float(r["ticket_promedio"])
        return VendedoresSummaryResponse(items=[VendedorItem(**r) for r in rows])

    def get_vendedor_detail(self, vendedor_id: str, period: str = "month") -> VendedorDetailResponse:
        where = {
            "month": "business_date >= DATE_TRUNC('MONTH', CURRENT_DATE())",
            "historical": "1 = 1",
            "6months": "business_date >= DATE_SUB(CURRENT_DATE(), 180)",
        }.get(period, "business_date >= DATE_TRUNC('MONTH', CURRENT_DATE())")
        stats = self._query(f"""
            SELECT
                nit_vendedor,
                nombre_vendedor,
                COUNT(*) AS facturas,
                SUM(total_factura) AS ventas_total,
                AVG(total_factura) AS ticket_promedio
            FROM motoshop.silver.fact_ventas
            WHERE nit_vendedor = '{vendedor_id}' AND {where}
            GROUP BY nit_vendedor, nombre_vendedor
        """)
        if not stats:
            logger.warning("No detail data found for vendedor %s", vendedor_id)
            return FakeMetricsRepo().get_vendedor_detail(vendedor_id, period)
        row = stats[0]
        actual = float(row["ventas_total"])

        # TODO: Reemplazar con JOIN a dim_categoria_producto cuando exista
        categorias = self._query(f"""
            SELECT 'GENÉRICO' AS categoria, CAST(SUM(total_factura) AS DOUBLE) AS total
            FROM motoshop.silver.fact_ventas
            WHERE nit_vendedor = '{vendedor_id}' AND {where}
        """)
        cats = [{"categoria": r["categoria"], "total": float(r["total"])} for r in categorias] if categorias else []

        productos = self._query(f"""
            SELECT COUNT(DISTINCT cod_producto) AS productos_vendidos
            FROM motoshop.silver.fact_ventas_detalle d
            INNER JOIN motoshop.silver.fact_ventas v ON d.num_documento = v.num_documento
            WHERE v.nit_vendedor = '{vendedor_id}' AND {where.replace('business_date', 'v.business_date')}
        """)
        prod_count = int(productos[0]["productos_vendidos"]) if productos and productos[0].get("productos_vendidos") else 0

        ant_val = 0.0
        if period == "month":
            anterior_rows = self._query(f"""
                SELECT COALESCE(SUM(total_factura), 0) AS anterior
                FROM motoshop.silver.fact_ventas
                WHERE nit_vendedor = '{vendedor_id}'
                  AND business_date >= DATE_TRUNC('MONTH', DATE_SUB(CURRENT_DATE(), 30))
                  AND business_date < DATE_TRUNC('MONTH', CURRENT_DATE())
            """)
            if anterior_rows:
                ant_val = float(anterior_rows[0]["anterior"])
        delta = round((actual - ant_val) / ant_val * 100, 1) if ant_val else None

        return VendedorDetailResponse(
            vendedor_id=str(row["nit_vendedor"]),
            nombre=str(row["nombre_vendedor"]),
            ventas_total=actual,
            ventas_por_categoria=[VendedorCategoriaItem(**c) for c in cats],
            ticket_promedio=round(float(row["ticket_promedio"]), 2),
            productos_vendidos=prod_count,
            comparacion_mes_anterior=VendedorComparacion(actual=actual, anterior=ant_val, delta=delta),
        )

    def get_cohortes_detail(self) -> CohortesDetailResponse:
        cohortes_rows = self._query("""
            SELECT mes_cohorte AS cohorte_mes,
                   COUNT(DISTINCT nit_cliente) AS total_clientes,
                   ROUND(AVG(ticket_promedio), 2) AS ltv_promedio
            FROM motoshop.gold.mart_cohortes_clientes
            GROUP BY mes_cohorte
            ORDER BY mes_cohorte
        """)
        retencion_rows = self._query("""
            SELECT mes_cohorte AS cohorte_mes,
                   business_month AS mes_observacion,
                   COUNT(DISTINCT nit_cliente) AS num_clientes,
                   ROUND(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS tasa_recurrencia
            FROM motoshop.gold.mart_cohortes_clientes
            GROUP BY mes_cohorte, business_month
            ORDER BY mes_cohorte, business_month
        """)
        nuevos_rows = self._query("""
            WITH ultimo_mes AS (
                SELECT MAX(business_month) AS mm FROM motoshop.gold.mart_cohortes_clientes
            )
            SELECT
                COALESCE(SUM(CASE WHEN mes_cohorte = business_month THEN 1 ELSE 0 END), 0) AS nuevos,
                COALESCE(SUM(CASE WHEN mes_cohorte < business_month AND compro_este_mes THEN 1 ELSE 0 END), 0) AS recurrentes,
                COALESCE(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END), 0) AS top_recurrentes
            FROM motoshop.gold.mart_cohortes_clientes, ultimo_mes
            WHERE business_month = ultimo_mes.mm
        """)
        if not cohortes_rows:
            logger.warning("No cohortes detail data found")
            return FakeMetricsRepo().get_cohortes_detail()
        for r in cohortes_rows:
            r["total_clientes"] = int(r["total_clientes"])
            r["ltv_promedio"] = float(r["ltv_promedio"])
        for r in retencion_rows:
            r["num_clientes"] = int(r["num_clientes"])
            r["tasa_recurrencia"] = float(r["tasa_recurrencia"])
        retencion_by_cohorte: dict[str, list[CohorteRetencionItem]] = {}
        for r in retencion_rows:
            retencion_by_cohorte.setdefault(r["cohorte_mes"], []).append(
                CohorteRetencionItem(**r)
            )
        cohortes = [
            CohorteDetailItem(
                cohorte_mes=c["cohorte_mes"],
                total_clientes=c["total_clientes"],
                ltv_promedio=c["ltv_promedio"],
                retencion=retencion_by_cohorte.get(c["cohorte_mes"], []),
            )
            for c in cohortes_rows
        ]
        n = nuevos_rows[0] if nuevos_rows else {"nuevos": 0, "recurrentes": 0, "top_recurrentes": 0}
        return CohortesDetailResponse(
            cohortes=cohortes,
            total_cohortes=len(cohortes),
            nuevos_este_mes=int(n["nuevos"]),
            recurrentes_este_mes=int(n["recurrentes"]),
            top_recurrentes=int(n["top_recurrentes"]),
        )

    def get_drift_summary(self) -> DriftSummaryResponse:
        rows = self._query("""
            SELECT alert_msg AS metric_name,
                   DATE_FORMAT(week_end, 'yyyy-MM-dd') AS detected_at,
                   desviacion_pct AS drift_magnitude,
                   threshold_pct AS threshold,
                   CASE
                     WHEN desviacion_pct >= threshold_pct THEN 'active'
                     WHEN desviacion_pct >= threshold_pct * 0.5 THEN 'warning'
                     ELSE 'resolved'
                   END AS status,
                   CASE
                     WHEN desviacion_pct >= threshold_pct THEN 'Re-entrenar modelo inmediatamente'
                     WHEN desviacion_pct >= threshold_pct * 0.5 THEN 'Monitorear. Si supera threshold, re-entrenar.'
                     ELSE 'Sin acción requerida'
                   END AS recommended_action
            FROM motoshop.gold.alertas_drift
            ORDER BY week_end DESC
            LIMIT 50
        """)
        threshold_row = self._query("""
            SELECT COALESCE(MAX(threshold_pct), 30.0) AS current_threshold
            FROM motoshop.gold.alertas_drift
        """)
        if not rows:
            logger.warning("No drift alerts found in gold.alertas_drift")
            return FakeMetricsRepo().get_drift_summary()
        for r in rows:
            r["drift_magnitude"] = float(r["drift_magnitude"])
            r["threshold"] = float(r["threshold"])
        current_threshold = float(threshold_row[0]["current_threshold"]) if threshold_row else 30.0
        active = sum(1 for r in rows if r["status"] == "active")
        warning = sum(1 for r in rows if r["status"] == "warning")
        return DriftSummaryResponse(
            items=[DriftSummaryItem(**r) for r in rows],
            total_alerts=len(rows),
            active_count=active,
            warning_count=warning,
            current_threshold=current_threshold,
        )

    def get_plan_compras(self) -> PlanComprasResponse:
        rows = self._query("""
            WITH demanda_7d AS (
                SELECT cod_producto, SUM(cantidad) AS qty_7d
                FROM motoshop.silver.fact_ventas_detalle
                WHERE business_date >= DATE_SUB(CURRENT_DATE(), 7)
                GROUP BY cod_producto
            ),
            suppliers AS (
                SELECT d.cod_producto, MAX(c.nombre_proveedor) AS supplier
                FROM motoshop.silver.fact_compras_detalle d
                INNER JOIN motoshop.silver.fact_compras c
                    ON d.num_documento = c.num_documento AND d.cod_clase = c.cod_clase
                WHERE c.nombre_proveedor IS NOT NULL
                GROUP BY d.cod_producto
            )
            SELECT
                inv.cod_producto AS sku,
                COALESCE(inv.nom_producto, inv.cod_producto) AS nombre,
                inv.cantidad_actual AS stock_actual,
                COALESCE(d.qty_7d, 0) AS demanda_7d,
                CASE WHEN COALESCE(d.qty_7d, 0) > inv.cantidad_actual
                     THEN COALESCE(d.qty_7d, 0) - inv.cantidad_actual
                     ELSE 0 END AS cantidad_a_comprar,
                COALESCE(abc.categoria_abc, 'C') AS abc,
                al.urgencia,
                CASE WHEN dorm.cod_producto IS NOT NULL THEN TRUE ELSE FALSE END AS dormido,
                COALESCE(s.supplier, 'Sin proveedor') AS supplier
            FROM motoshop.gold.mart_inventario_actual inv
            LEFT JOIN demanda_7d d ON inv.cod_producto = d.cod_producto
            LEFT JOIN motoshop.gold.mart_rotacion_abc abc
                ON inv.cod_producto = abc.cod_producto
            LEFT JOIN motoshop.gold.alertas_quiebre al
                ON inv.cod_producto = al.sku
            LEFT JOIN motoshop.gold.mart_productos_dormidos dorm
                ON inv.cod_producto = dorm.cod_producto
            LEFT JOIN suppliers s ON inv.cod_producto = s.cod_producto
            WHERE COALESCE(d.qty_7d, 0) > inv.cantidad_actual
               OR al.urgencia IS NOT NULL
            ORDER BY cantidad_a_comprar DESC,
                     CASE WHEN al.urgencia = 'alta' THEN 1
                          WHEN al.urgencia = 'media' THEN 2
                          WHEN al.urgencia = 'baja' THEN 3
                          ELSE 4 END
            LIMIT 100
        """)
        if not rows:
            logger.warning("No plan compras data found")
            return FakeMetricsRepo().get_plan_compras()
        for r in rows:
            r["stock_actual"] = float(r["stock_actual"])
            r["demanda_7d"] = float(r["demanda_7d"])
            r["cantidad_a_comprar"] = float(r["cantidad_a_comprar"])
            r["dormido"] = bool(r["dormido"]) if isinstance(r["dormido"], (int, float)) else r["dormido"] in (True, "true", "TRUE")
        total_unidades = sum(r["cantidad_a_comprar"] for r in rows)
        return PlanComprasResponse(
            items=[PlanCompraItem(**r) for r in rows],
            total_skus=len(rows),
            total_unidades=total_unidades,
            total_valor_estimado=total_unidades * 75_000.0,
            skus_urgentes=sum(1 for r in rows if r.get("urgencia") == "alta"),
            skus_dormidos=sum(1 for r in rows if r.get("dormido")),
        )

    def get_forecast_categoria(self) -> ForecastCategoriaResponse:
        rows = self._query("""
            SELECT cod_grupo,
                   SUM(demanda_real) AS demanda_real,
                   SUM(demanda_predicha_baseline) AS demanda_predicha,
                   ROUND(ABS(SUM(demanda_real) - SUM(demanda_predicha_baseline))
                         / NULLIF(SUM(demanda_real), 0) * 100, 2) AS desviacion_pct,
                   MAX(metodo_baseline) AS metodo
            FROM motoshop.gold.forecast_categoria
            WHERE business_date >= DATE_SUB(CURRENT_DATE(), 30)
            GROUP BY cod_grupo
            ORDER BY demanda_real DESC
        """)
        coverage_row = self._query("""
            SELECT ROUND(COUNT(DISTINCT cod_grupo) * 100.0
                   / NULLIF((SELECT COUNT(DISTINCT cod_grupo)
                             FROM motoshop.gold.forecast_categoria), 0), 2) AS cobertura_pct
            FROM motoshop.gold.forecast_categoria
            WHERE business_date >= DATE_SUB(CURRENT_DATE(), 30)
        """)
        if not rows:
            logger.warning("No forecast categoria data found")
            return FakeMetricsRepo().get_forecast_categoria()
        for r in rows:
            r["demanda_real"] = float(r["demanda_real"])
            r["demanda_predicha"] = float(r["demanda_predicha"])
            r["desviacion_pct"] = float(r["desviacion_pct"])
        wape = sum(abs(r["demanda_real"] - r["demanda_predicha"]) for r in rows) / sum(r["demanda_real"] for r in rows) * 100
        cobertura = float(coverage_row[0]["cobertura_pct"]) if coverage_row else 99.9
        return ForecastCategoriaResponse(
            items=[ForecastCategoriaItem(**r) for r in rows],
            total_categorias=len(rows),
            wape_promedio=round(wape, 2),
            cobertura_pct=cobertura,
        )

    def _query(self, sql: str) -> list[dict]:
        result = self._w.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=self._wh_id,
            wait_timeout="50s",
        )
        if result.status.state.name != "SUCCEEDED":
            error_detail = result.status.error.message if hasattr(result.status, 'error') and result.status.error else 'unknown'
            logger.error("Databricks query failed: state=%s error=%s", result.status.state.name, error_detail)
            raise RuntimeError(f"Databricks query failed: {result.status.state.name} - {error_detail}")
        # Column names come from result.manifest.schema.columns
        cols = [col.name for col in result.manifest.schema.columns]
        total_chunks = result.manifest.total_chunk_count if hasattr(result.manifest, 'total_chunk_count') else 1
        all_rows = []
        for i in range(total_chunks):
            chunk = self._w.statement_execution.get_statement_result_chunk_n(
                result.statement_id, i
            )
            if chunk.data_array:
                all_rows.extend([dict(zip(cols, row)) for row in chunk.data_array])
        return all_rows


# ── Factory ────────────────────────────────────────────────────────────────

def get_metrics_repo(workspace_client=None, warehouse_id=None) -> MetricsRepoProtocol:
    """Devuelve el repo adecuado según configuración.
    
    Si se pasa workspace_client + warehouse_id, usa RealMetricsRepo.
    Si no, cae a FakeMetricsRepo (datos mock).
    """
    if workspace_client is not None and warehouse_id:
        return RealMetricsRepo(workspace_client, warehouse_id)
    return FakeMetricsRepo()
