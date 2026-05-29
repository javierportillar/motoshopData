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
    CohorteItem,
    CohortesResponse,
    DormidoItem,
    DormidosResponse,
    InventorySummary,
    SalesSummary,
    TopSkuItem,
)


class MetricsRepoProtocol(Protocol):
    """Contrato que cumplen FakeMetricsRepo y RealMetricsRepo."""

    def get_sales_summary(self) -> SalesSummary: ...
    def get_inventory_summary(self) -> InventorySummary: ...
    def get_abc_segmentation(self) -> AbcSegmentation: ...
    def get_dormidos(self) -> DormidosResponse: ...
    def get_cohortes(self) -> CohortesResponse: ...


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

    def get_inventory_summary(self) -> InventorySummary:
        rows = self._query("""
            SELECT
                SUM(cantidad_actual) AS stock_total,
                COUNT(DISTINCT cod_producto) AS num_productos
            FROM motoshop.gold.mart_inventario_actual
        """)
        valor = self._query("""
            SELECT ROUND(SUM(cantidad_actual * ultimo_costo), 2) AS valor_total
            FROM motoshop.gold.mart_inventario_actual
            WHERE ultimo_costo IS NOT NULL AND ultimo_costo > 0
        """)
        bodegas = self._query("""
            SELECT
                cod_bodega, nom_bodega,
                SUM(cantidad_actual) AS cantidad,
                ROUND(SUM(cantidad_actual) / NULLIF(SUM(SUM(cantidad_actual)) OVER(), 0) * 100, 1) AS porcentaje
            FROM motoshop.gold.mart_inventario_actual
            GROUP BY cod_bodega, nom_bodega
            ORDER BY cantidad DESC
        """)
        if not rows:
            raise RuntimeError("No inventory data found in gold mart")
        r = rows[0]
        valor_total = float(valor[0]["valor_total"]) if valor else 0.0
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
            LIMIT 50
        """)
        if not rows:
            logger.warning("No dormidos data found in gold mart")
            return FakeMetricsRepo().get_dormidos()
        for r in rows:
            r["dias_sin_venta"] = int(r["dias_sin_venta"])
            r["stock_actual"] = float(r["stock_actual"])
        return DormidosResponse(total=len(rows), productos=[DormidoItem(**r) for r in rows])

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
        return CohortesResponse(cohortes=[CohorteItem(**r) for r in rows])

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
