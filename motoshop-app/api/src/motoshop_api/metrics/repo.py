"""Repositorio de métricas — mock (FakeMetricsRepo) + real (MetricsRepo vía Databricks SQL).

FakeMetricsRepo se usa mientras Dev A construye los gold marts.
Devuelve datos realistas de demo con cifras típicas de una tienda
de repuestos de moto en Colombia (~$50M COP/mes, ~800 facturas/mes).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

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
_LAST_MONTH = "2026-04"

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


# ── Real (Databricks SQL Warehouse) ──────────────────────────────────────

class RealMetricsRepo:
    """Lee de marts gold reales vía Databricks SQL Warehouse.

    Se activa cuando Dev A confirma que los marts existen y tienen datos.
    """

    def __init__(self, connection) -> None:
        self._conn = connection

    def get_sales_summary(self) -> SalesSummary:
        rows = self._query("""
            SELECT
                DATE_FORMAT(business_date, '%Y-%m') AS business_month,
                SUM(valor_total) AS ventas_mes,
                SUM(cantidad_total) AS cantidad_total,
                SUM(num_facturas) AS num_facturas,
                ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE business_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
            GROUP BY DATE_FORMAT(business_date, '%Y-%m')
            ORDER BY business_month DESC
            LIMIT 2
        """)
        top = self._query("""
            SELECT
                cod_producto, nom_producto,
                SUM(cantidad_total) AS cantidad_total,
                SUM(valor_total) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop.gold.mart_ventas_diarias_sku
            WHERE business_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
            GROUP BY cod_producto, nom_producto
            ORDER BY valor_total DESC
            LIMIT 10
        """)
        if not rows:
            return FakeMetricsRepo().get_sales_summary()
        mes_actual, mes_anterior = rows[0], rows[1] if len(rows) > 1 else None
        return SalesSummary(
            business_month=mes_actual["business_month"],
            ventas_mes_actual=mes_actual["ventas_mes"],
            ventas_mes_anterior=mes_anterior["ventas_mes"] if mes_anterior else 0.0,
            delta_porcentual=round(
                (mes_actual["ventas_mes"] - mes_anterior["ventas_mes"]) / mes_anterior["ventas_mes"] * 100, 1
            ) if mes_anterior and mes_anterior["ventas_mes"] else None,
            ticket_promedio=mes_actual["ticket_promedio"],
            num_facturas=mes_actual["num_facturas"],
            top_skus=[TopSkuItem(**r) for r in top],
        )

    def get_inventory_summary(self) -> InventorySummary:
        rows = self._query("""
            SELECT
                SUM(cantidad_total) AS stock_total,
                COUNT(DISTINCT cod_producto) AS num_productos
            FROM motoshop.gold.mart_inventario_actual
        """)
        bodegas = self._query("""
            SELECT
                cod_bodega, nom_bodega,
                SUM(cantidad_total) AS cantidad,
                ROUND(SUM(cantidad_total) / NULLIF(SUM(SUM(cantidad_total)) OVER(), 0) * 100, 1) AS porcentaje
            FROM motoshop.gold.mart_inventario_actual
            GROUP BY cod_bodega, nom_bodega
            ORDER BY cantidad DESC
        """)
        if not rows:
            return FakeMetricsRepo().get_inventory_summary()
        r = rows[0]
        return InventorySummary(
            stock_total=r["stock_total"],
            valor_total=0.0,
            num_productos=r["num_productos"],
            por_bodega=[BodegaItem(**b) for b in bodegas],
        )

    def get_abc_segmentation(self) -> AbcSegmentation:
        buckets = self._query("""
            SELECT categoria, COUNT(*) AS num_skus,
                   SUM(valor_total) AS valor_total,
                   ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop.gold.mart_rotacion_abc
            WHERE business_month = DATE_FORMAT(CURRENT_DATE(), '%Y-%m')
            GROUP BY categoria
            ORDER BY FIELD(categoria, 'A', 'B', 'C')
        """)
        if not buckets:
            return FakeMetricsRepo().get_abc_segmentation()
        by_cat = {b["categoria"]: b for b in buckets}
        return AbcSegmentation(
            business_month=datetime.now().strftime("%Y-%m"),
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
            return FakeMetricsRepo().get_dormidos()
        return DormidosResponse(total=len(rows), productos=[DormidoItem(**r) for r in rows])

    def get_cohortes(self) -> CohortesResponse:
        rows = self._query("""
            SELECT
                cohorte_mes, mes_observacion,
                num_clientes, ticket_promedio, tasa_recurrencia
            FROM motoshop.gold.mart_cohortes_clientes
            ORDER BY cohorte_mes, mes_observacion
        """)
        if not rows:
            return FakeMetricsRepo().get_cohortes()
        return CohortesResponse(cohortes=[CohorteItem(**r) for r in rows])

    def _query(self, sql: str) -> list[dict]:
        cursor = self._conn.cursor()
        cursor.execute(sql)
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ── Factory ────────────────────────────────────────────────────────────────

def get_metrics_repo(connection=None) -> MetricsRepoProtocol:
    """Devuelve FakeMetricsRepo siempre por ahora.
    
    Cuando Dev A confirme que los marts gold existen y tienen datos,
    se cambia a RealMetricsRepo(connection).
    """
    if connection is not None:
        return RealMetricsRepo(connection)
    return FakeMetricsRepo()
