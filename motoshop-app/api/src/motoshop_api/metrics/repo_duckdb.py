"""DuckDBMetricsRepo — implementación del protocolo MetricsRepoProtocol sobre DuckDB.

Reemplaza a RealMetricsRepo (Databricks SQL Warehouse) cuando
DATA_BACKEND=duckdb está configurado.

Lee de un archivo DuckDB local (en producción, descargado de R2 al startup).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from motoshop_api.metrics.repo import MetricsRepoProtocol
from motoshop_api.metrics.schemas import (
    AbcBucket,
    AbcDetalleItem,
    AbcDetalleResponse,
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
    TopSkuItem,
    VendedoresSummaryResponse,
    VendedorItem,
    VendedorCategoriaItem,
    VendedorComparacion,
    VendedorDetailResponse,
)

logger = logging.getLogger(__name__)

# Ruta por defecto — /tmp en Render, out/ local
_DEFAULT_DB_PATH = Path(os.environ.get(
    "DUCKDB_PATH",
    "/tmp/motoshop_gold.duckdb" if os.environ.get("ENV") == "prod" else "out/motoshop_gold.duckdb"
))


def _bootstrap_duckdb_from_r2(db_path: Path) -> None:
    """Descarga motoshop_gold.duckdb desde R2 si no existe localmente."""
    if db_path.exists():
        return

    r2_endpoint = os.environ.get("R2_ENDPOINT")
    r2_key = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    r2_bucket = os.environ.get("R2_BUCKET", "motoshop-gold")

    if not all([r2_endpoint, r2_key, r2_secret]):
        logger.warning("R2 credentials not set; skipping bootstrap download")
        return

    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
            region_name="auto",
        )
        logger.info("Downloading DuckDB from R2: %s/%s", r2_bucket, "motoshop_gold.duckdb")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(r2_bucket, "motoshop_gold.duckdb", str(db_path))
        logger.info("DuckDB downloaded to %s", db_path)
    except Exception as exc:
        logger.warning("Failed to download DuckDB from R2: %s", exc)


class DuckDBMetricsRepo:
    """Lee de archivo DuckDB local usando SQL directo.

    Misma interfaz que RealMetricsRepo pero sin dependencia de Databricks.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path or _DEFAULT_DB_PATH)
        _bootstrap_duckdb_from_r2(self._path)
        if not self._path.exists():
            raise FileNotFoundError(
                f"DuckDB file not found at {self._path}. "
                "Run 'python pipeline/run_all.py' first, or set DUCKDB_PATH."
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

    @staticmethod
    def _fill_month_gaps(rows: list[dict]) -> list[dict]:
        """Rellena meses faltantes con ceros para evitar huecos en la serie."""
        if not rows:
            return rows

        from collections import defaultdict

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
                    continue
                if mo > obs_months[-1]:
                    break
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

    # ── Sales Summary ────────────────────────────────────────────────────

    def get_sales_summary(self) -> SalesSummary:
        """Resumen de ventas mes actual vs mes anterior + top 10 SKUs."""
        rows = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM motoshop_gold_mart_ventas_diarias_sku
            )
            SELECT
                STRFTIME(business_date, '%Y-%m') AS business_month,
                ROUND(SUM(valor_total), 2) AS ventas_mes,
                ROUND(SUM(cantidad_total), 2) AS cantidad_total,
                SUM(num_facturas) AS num_facturas,
                ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop_gold_mart_ventas_diarias_sku, max_dates
            WHERE business_date >= max_dates.max_date - INTERVAL '60' DAY
            GROUP BY STRFTIME(business_date, '%Y-%m')
            ORDER BY business_month DESC
            LIMIT 2
        """)

        top = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM motoshop_gold_mart_ventas_diarias_sku
            )
            SELECT
                cod_producto, nom_producto,
                ROUND(SUM(cantidad_total), 2) AS cantidad_total,
                ROUND(SUM(valor_total), 2) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop_gold_mart_ventas_diarias_sku, max_dates
            WHERE business_date >= max_dates.max_date - INTERVAL '30' DAY
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

        va_actual = float(mes_actual["ventas_mes"] or 0.0)
        va_anterior = float(mes_anterior["ventas_mes"] or 0.0) if mes_anterior else 0.0

        return SalesSummary(
            business_month=str(mes_actual["business_month"]),
            ventas_mes_actual=va_actual,
            ventas_mes_anterior=va_anterior,
            delta_porcentual=round(
                (va_actual - va_anterior) / va_anterior * 100, 1
            ) if mes_anterior and va_anterior else None,
            ticket_promedio=float(mes_actual["ticket_promedio"] or 0.0),
            num_facturas=int(mes_actual["num_facturas"]),
            top_skus=[TopSkuItem(**r) for r in top],
        )

    # ── Sales Daily ──────────────────────────────────────────────────────

    def get_sales_daily(self, date: str) -> SalesDailyResponse:
        max_date_rows = self._query("""
            SELECT MAX(business_date) AS max_date
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date <= ?
        """, [date])
        effective_date = date
        if max_date_rows and max_date_rows[0].get("max_date"):
            effective_date = str(max_date_rows[0]["max_date"])

        productos = self._query("""
            SELECT
                cod_producto AS sku,
                nom_producto AS nombre,
                ROUND(SUM(cantidad_total), 2) AS cantidad,
                ROUND(SUM(valor_total), 2) AS valor
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date = ?
            GROUP BY cod_producto, nom_producto
            ORDER BY valor DESC
        """, [effective_date])
        totals = self._query("""
            SELECT
                ROUND(COALESCE(SUM(valor_total), 0), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date = ?
        """, [effective_date])
        if not totals:
            return SalesDailyResponse(date=effective_date, total_ventas=0.0, total_facturas=0, productos_vendidos=[])
        t = totals[0]
        return SalesDailyResponse(
            date=effective_date,
            total_ventas=float(t["total_ventas"] or 0.0),
            total_facturas=int(t["total_facturas"] or 0),
            productos_vendidos=[SalesDailyItem(**r) for r in productos],
        )

    # ── Sales Monthly ────────────────────────────────────────────────────

    def get_sales_monthly(self, month: str) -> SalesMonthlyResponse:
        totals = self._query("""
            SELECT
                ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
        """, [month])
        prev = self._query("""
            SELECT ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS total_ventas
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
        """, [_prev_month_str(month)])
        top = self._query("""
            SELECT
                cod_producto AS cod_producto,
                nom_producto AS nom_producto,
                ROUND(SUM(cantidad_total), 2) AS cantidad_total,
                ROUND(SUM(valor_total), 2) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
            GROUP BY cod_producto, nom_producto
            ORDER BY valor_total DESC
            LIMIT 10
        """, [month])
        if not totals:
            raise RuntimeError(f"No sales data found for month {month}")
        t = totals[0]
        va_actual = float(t["total_ventas"] or 0.0)
        va_anterior = float(prev[0]["total_ventas"] or 0.0) if prev else 0.0
        delta = round((va_actual - va_anterior) / va_anterior * 100, 1) if va_anterior else None
        return SalesMonthlyResponse(
            month=month,
            total_ventas=va_actual,
            total_facturas=int(t["total_facturas"]),
            delta_porcentaje=delta,
            productos_top=[TopSkuItem(**r) for r in top],
        )

    # ── Sales Historical ─────────────────────────────────────────────────

    def get_sales_historical(self) -> SalesHistoricalResponse:
        totals = self._query("""
            SELECT
                ROUND(SUM(valor_total), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM motoshop_gold_mart_ventas_diarias_sku
        """)
        meses = self._query("""
            SELECT YEAR(business_date) AS year,
                   MONTH(business_date) AS month,
                   ROUND(SUM(valor_total), 2) AS total_ventas,
                   COALESCE(SUM(num_facturas), 0) AS num_facturas,
                   ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop_gold_mart_ventas_diarias_sku
            GROUP BY YEAR(business_date), MONTH(business_date)
            ORDER BY year, month
        """)
        first = self._query("""
            SELECT MIN(business_date) AS first_date
            FROM motoshop_gold_mart_ventas_diarias_sku
        """)
        if not totals or not meses:
            raise RuntimeError("No historical sales data found")
        t = totals[0]
        fecha_primera = str(first[0]["first_date"]) if first and first[0].get("first_date") else None
        return SalesHistoricalResponse(
            total_ventas=float(t["total_ventas"] or 0.0),
            total_facturas=int(t["total_facturas"] or 0),
            meses=[SalesTrendItem(**r) for r in meses],
            fecha_primera_venta=fecha_primera,
        )

    # ── Inventory Summary ────────────────────────────────────────────────

    def get_inventory_summary(self) -> InventorySummary:
        rows = self._query("""
            SELECT
                SUM(cantidad_actual) AS stock_total,
                COUNT(DISTINCT cod_producto) AS num_productos
            FROM motoshop_gold_mart_inventario_actual
        """)
        valor = self._query("""
            WITH latest_cost AS (
                SELECT cod_producto, costo_producto,
                       ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) AS rn
                FROM motoshop_silver_fact_compras_detalle
                WHERE costo_producto > 0
            )
            SELECT COALESCE(ROUND(SUM(i.cantidad_actual * COALESCE(lc.costo_producto, 0)), 2), 0) AS valor_total
            FROM motoshop_gold_mart_inventario_actual i
            LEFT JOIN latest_cost lc ON i.cod_producto = lc.cod_producto AND lc.rn = 1
        """)
        bodegas = self._query("""
            WITH default_bodega AS (
                SELECT cod_bodega AS def_cod, nombre_bodega AS def_nom
                FROM motoshop_silver_dim_bodega
                ORDER BY snapshot_date DESC
                LIMIT 1
            )
            SELECT
                CASE
                    WHEN inv.cod_bodega IS NULL OR inv.cod_bodega = ''
                        THEN COALESCE(db.def_cod, 'SIN_COD')
                    ELSE inv.cod_bodega
                END AS cod_bodega,
                CASE
                    WHEN inv.cod_bodega IS NULL OR inv.cod_bodega = ''
                        THEN COALESCE(db.def_nom, 'Sin clasificar')
                    WHEN inv.nom_bodega IS NULL OR inv.nom_bodega = '' OR inv.nom_bodega = 'SIN NOMBRE'
                        THEN COALESCE(db.def_nom, CONCAT('Bodega ', inv.cod_bodega))
                    ELSE inv.nom_bodega
                END AS nom_bodega,
                ROUND(SUM(inv.cantidad_actual), 2) AS cantidad,
                ROUND(SUM(inv.cantidad_actual) / NULLIF(SUM(SUM(inv.cantidad_actual)) OVER(), 0) * 100, 1) AS porcentaje
            FROM motoshop_gold_mart_inventario_actual inv
            CROSS JOIN default_bodega db
            GROUP BY 1, 2
            ORDER BY cantidad DESC
        """)
        if not rows:
            raise RuntimeError("No inventory data found in gold mart")
        r = rows[0]
        valor_total = float(valor[0]["valor_total"]) if valor else 0.0
        return InventorySummary(
            stock_total=float(r["stock_total"] or 0),
            valor_total=valor_total,
            num_productos=int(r["num_productos"] or 0),
            por_bodega=[BodegaItem(**b) for b in bodegas],
        )

    # ── ABC Segmentation ───────────────────────────────────────────────

    def get_abc_segmentation(self) -> AbcSegmentation:
        buckets = self._query("""
            WITH max_month AS (
                SELECT MAX(business_month) AS mm FROM motoshop_gold_mart_rotacion_abc
            )
            SELECT max_month.mm AS business_month,
                   categoria_abc AS categoria, COUNT(*) AS num_skus,
                   ROUND(SUM(valor_total), 2) AS valor_total,
                   ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM motoshop_gold_mart_rotacion_abc, max_month
            WHERE business_month = max_month.mm
            GROUP BY categoria_abc, max_month.mm
            ORDER BY CASE categoria_abc WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END
        """)
        if not buckets:
            logger.warning("No ABC data found in gold mart")
            return AbcSegmentation(business_month="", total_skus=0, total_ingresos=0.0, bucket_a=AbcBucket(categoria="A", num_skus=0, valor_total=0.0, porcentaje_ingreso=0.0), bucket_b=AbcBucket(categoria="B", num_skus=0, valor_total=0.0, porcentaje_ingreso=0.0), bucket_c=AbcBucket(categoria="C", num_skus=0, valor_total=0.0, porcentaje_ingreso=0.0))
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

    def get_abc_detalle(self, bucket: str, limit: int = 20) -> AbcDetalleResponse:
        rows = self._query("""
            WITH max_month AS (
                SELECT MAX(business_month) AS mm FROM motoshop_gold_mart_rotacion_abc
            )
            SELECT
                cod_producto,
                nom_producto,
                ROUND(valor_total, 2) AS valor_total,
                ROUND(valor_total / NULLIF(SUM(valor_total) OVER(PARTITION BY categoria_abc), 0) * 100, 1) AS porcentaje_bucket
            FROM motoshop_gold_mart_rotacion_abc, max_month
            WHERE business_month = max_month.mm AND categoria_abc = ?
            ORDER BY valor_total DESC
            LIMIT ?
        """, [bucket, limit])
        if not rows:
            return AbcDetalleResponse(bucket=bucket, total_skus=0, total_valor=0.0, items=[])
        for r in rows:
            r["valor_total"] = float(r["valor_total"])
            r["porcentaje_bucket"] = float(r["porcentaje_bucket"])
        items = [AbcDetalleItem(**r) for r in rows]
        total_valor = sum(i.valor_total for i in items)
        return AbcDetalleResponse(bucket=bucket, total_skus=len(items), total_valor=total_valor, items=items)

    # ── Dormidos ─────────────────────────────────────────────────────────

    def get_dormidos(
        self,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "dias_sin_venta",
        sort_order: str = "desc",
    ) -> DormidosResponse:
        count_rows = self._query("""
            SELECT COUNT(*) AS total
            FROM motoshop_gold_mart_productos_dormidos d
        """)
        total = int(count_rows[0]["total"]) if count_rows else 0
        offset = (page - 1) * page_size
        sort_column = {
            "dias_sin_venta": "dias_sin_venta",
            "ultima_compra": "ultima_compra",
            "ultima_venta": "ultima_venta",
        }.get(sort_by, "dias_sin_venta")
        direction = "ASC" if sort_order == "asc" else "DESC"
        rows = self._query(f"""
            SELECT d.cod_producto, d.nom_producto, d.stock_actual,
                    CAST(c.ultima_compra AS VARCHAR) AS ultima_compra,
                    COALESCE(CAST(v.ultima_venta AS VARCHAR), CAST(d.ultima_fecha_venta AS VARCHAR)) AS ultima_venta,
                    DATE_DIFF('day', COALESCE(v.ultima_venta, d.ultima_fecha_venta), CURRENT_DATE) AS dias_sin_venta
            FROM motoshop_gold_mart_productos_dormidos d
            LEFT JOIN (
                SELECT cod_producto, MAX(business_date) AS ultima_venta
                FROM motoshop_silver_fact_ventas_detalle
                GROUP BY cod_producto
            ) v ON d.cod_producto = v.cod_producto
            LEFT JOIN (
                SELECT cod_producto, MAX(business_date) AS ultima_compra
                FROM motoshop_silver_fact_compras_detalle
                GROUP BY cod_producto
            ) c ON d.cod_producto = c.cod_producto
            ORDER BY {sort_column} {direction}
            LIMIT ? OFFSET ?
        """, [page_size, offset])
        if not rows:
            logger.warning("No dormidos data found in gold mart")
            return DormidosResponse(page=page, page_size=page_size, total=0, items=[], productos=[])
        for r in rows:
            r["dias_sin_venta"] = int(r["dias_sin_venta"])
            r["stock_actual"] = float(r["stock_actual"])
            if r["ultima_compra"] is not None:
                r["ultima_compra"] = str(r["ultima_compra"])
            if r.get("ultima_venta") is not None:
                r["ultima_venta"] = str(r["ultima_venta"])
        items = [DormidoItem(**r) for r in rows]
        return DormidosResponse(page=page, page_size=page_size, total=total, items=items, productos=items)

    # ── Cohortes ─────────────────────────────────────────────────────────

    def get_cohortes(self) -> CohortesResponse:
        rows = self._query("""
            SELECT
                STRFTIME(TRY_CAST(mes_cohorte AS DATE), '%Y-%m') AS cohorte_mes,
                STRFTIME(TRY_CAST(business_month AS DATE), '%Y-%m') AS mes_observacion,
                COUNT(DISTINCT nit_cliente) AS num_clientes,
                ROUND(AVG(ticket_promedio), 2) AS ticket_promedio,
                ROUND(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS tasa_recurrencia
            FROM motoshop_gold_mart_cohortes_clientes
            GROUP BY mes_cohorte, business_month
            ORDER BY mes_cohorte, business_month
        """)
        if not rows:
            logger.warning("No cohortes data found in gold mart")
            return CohortesResponse(cohortes=[])
        for r in rows:
            r["num_clientes"] = int(r["num_clientes"])
            r["ticket_promedio"] = float(r["ticket_promedio"])
            r["tasa_recurrencia"] = float(r["tasa_recurrencia"])
            r["muestra_pequena"] = r["num_clientes"] < 5
        filled = self._fill_month_gaps(rows)
        for r in filled:
            if "muestra_pequena" not in r:
                r["muestra_pequena"] = r["num_clientes"] < 5
        return CohortesResponse(cohortes=[CohorteItem(**r) for r in filled])

    # ── Sales Trend ──────────────────────────────────────────────────────

    def get_sales_trend(self, periods: int = 6, year: int | None = None) -> SalesTrendResponse:
        where_year = ""
        params = [periods]
        if year is not None:
            where_year = "AND YEAR(business_date) = ?"
            params.append(year)
        rows = self._query(f"""
            SELECT YEAR(business_date) AS year,
                    MONTH(business_date) AS month,
                    ROUND(SUM(valor_total), 2) AS total_ventas,
                    COALESCE(SUM(num_facturas), 0) AS num_facturas,
                    ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date >= CURRENT_DATE - (CAST(? AS VARCHAR) || ' months')::INTERVAL
            {where_year}
            GROUP BY YEAR(business_date), MONTH(business_date)
            ORDER BY year, month
        """, params)
        if not rows:
            logger.warning("No sales trend data found")
            return SalesTrendResponse(periods=periods, items=[])
        for r in rows:
            r["year"] = int(r["year"])
            r["month"] = int(r["month"])
            r["total_ventas"] = float(r["total_ventas"] or 0.0)
            r["num_facturas"] = int(r["num_facturas"] or 0)
            r["ticket_promedio"] = float(r["ticket_promedio"] or 0.0)
        return SalesTrendResponse(periods=periods, items=[SalesTrendItem(**r) for r in rows])

    # ── Vendedores Summary ───────────────────────────────────────────────

    def get_vendedores_summary(self, period: str = "month") -> VendedoresSummaryResponse:
        max_month_sql = "(SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM motoshop_silver_fact_ventas)"
        where = {
            "month": f"STRFTIME(business_date, '%Y-%m') = {max_month_sql}",
            "historical": "1 = 1",
            "6months": "business_date >= CURRENT_DATE - INTERVAL '180' DAY",
        }.get(period, f"STRFTIME(business_date, '%Y-%m') = {max_month_sql}")
        rows = self._query(f"""
            SELECT
                COALESCE(NULLIF(nit_vendedor, ''), 'SIN_ASIGNAR') AS nit_vendedor,
                COALESCE(NULLIF(nombre_vendedor, ''), 'Sin asignar') AS nombre_vendedor,
                COUNT(*) AS facturas,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                ROUND(AVG(total_factura), 2) AS ticket_promedio
            FROM motoshop_silver_fact_ventas
            WHERE {where}
            GROUP BY
                COALESCE(NULLIF(nit_vendedor, ''), 'SIN_ASIGNAR'),
                COALESCE(NULLIF(nombre_vendedor, ''), 'Sin asignar')
            ORDER BY total_ventas DESC
            LIMIT 10
        """)
        if not rows:
            logger.warning("No vendedores data found")
            return VendedoresSummaryResponse(items=[])
        for r in rows:
            r["facturas"] = int(r["facturas"])
            r["total_ventas"] = float(r["total_ventas"] or 0.0)
            r["ticket_promedio"] = float(r["ticket_promedio"] or 0.0)
        return VendedoresSummaryResponse(items=[VendedorItem(**r) for r in rows])

    # ── Vendedor Detail ────────────────────────────────────────────────

    def get_vendedor_detail(self, vendedor_id: str, period: str = "month") -> VendedorDetailResponse:
        max_month_sql = "(SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM motoshop_silver_fact_ventas)"
        where = {
            "month": f"STRFTIME(business_date, '%Y-%m') = {max_month_sql}",
            "historical": "1 = 1",
            "6months": "business_date >= CURRENT_DATE - INTERVAL '180' DAY",
        }.get(period, f"STRFTIME(business_date, '%Y-%m') = {max_month_sql}")
        stats = self._query(f"""
            SELECT
                nit_vendedor,
                nombre_vendedor,
                COUNT(*) AS facturas,
                ROUND(SUM(total_factura), 2) AS ventas_total,
                ROUND(AVG(total_factura), 2) AS ticket_promedio
            FROM motoshop_silver_fact_ventas
            WHERE nit_vendedor = ? AND {where}
            GROUP BY nit_vendedor, nombre_vendedor
        """, [vendedor_id])
        if not stats:
            logger.warning("No detail data found for vendedor %s", vendedor_id)
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Vendedor no encontrado")
        row = stats[0]
        actual = float(row["ventas_total"] or 0.0)

        categorias = self._query(f"""
            SELECT 'GENÉRICO' AS categoria, CAST(SUM(total_factura) AS DOUBLE) AS total
            FROM motoshop_silver_fact_ventas
            WHERE nit_vendedor = ? AND {where}
        """, [vendedor_id])
        cats = [{"categoria": r["categoria"], "total": float(r["total"])} for r in categorias] if categorias else []

        where_v = {
            "month": f"STRFTIME(v.business_date, '%Y-%m') = {max_month_sql}",
            "historical": "1 = 1",
            "6months": "v.business_date >= CURRENT_DATE - INTERVAL '180' DAY",
        }.get(period, f"STRFTIME(v.business_date, '%Y-%m') = {max_month_sql}")
        productos = self._query(f"""
            SELECT COUNT(DISTINCT cod_producto) AS productos_vendidos
            FROM motoshop_silver_fact_ventas_detalle d
            INNER JOIN motoshop_silver_fact_ventas v ON d.num_documento = v.num_documento
            WHERE v.nit_vendedor = ? AND {where_v}
        """, [vendedor_id])
        prod_count = int(productos[0]["productos_vendidos"]) if productos and productos[0].get("productos_vendidos") else 0

        ant_val = 0.0
        if period == "month":
            anterior_rows = self._query("""
                SELECT COALESCE(ROUND(SUM(total_factura), 2), 0) AS anterior
                FROM motoshop_silver_fact_ventas
                WHERE nit_vendedor = ?
                  AND business_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1' MONTH)
                  AND business_date < DATE_TRUNC('month', CURRENT_DATE)
            """, [vendedor_id])
            if anterior_rows:
                ant_val = float(anterior_rows[0]["anterior"])
        delta = round((actual - ant_val) / ant_val * 100, 1) if ant_val else None

        return VendedorDetailResponse(
            vendedor_id=str(row["nit_vendedor"]),
            nombre=str(row["nombre_vendedor"]),
            ventas_total=actual,
            ventas_por_categoria=[VendedorCategoriaItem(**c) for c in cats],
            ticket_promedio=round(float(row["ticket_promedio"] or 0.0), 2),
            productos_vendidos=prod_count,
            comparacion_mes_anterior=VendedorComparacion(actual=actual, anterior=ant_val, delta=delta),
        )

    # ── Cohortes Detail ────────────────────────────────────────────────

    def get_cohortes_detail(self) -> CohortesDetailResponse:
        cohortes_rows = self._query("""
            SELECT STRFTIME(TRY_CAST(mes_cohorte AS DATE), '%Y-%m-01') AS cohorte_mes,
                   COUNT(DISTINCT nit_cliente) AS total_clientes,
                   ROUND(AVG(ticket_promedio), 2) AS ltv_promedio
            FROM motoshop_gold_mart_cohortes_clientes
            GROUP BY mes_cohorte
            ORDER BY mes_cohorte
        """)
        retencion_rows = self._query("""
            SELECT STRFTIME(TRY_CAST(mes_cohorte AS DATE), '%Y-%m-01') AS cohorte_mes,
                   STRFTIME(TRY_CAST(business_month AS DATE), '%Y-%m-01') AS mes_observacion,
                   COUNT(DISTINCT nit_cliente) AS num_clientes,
                   ROUND(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS tasa_recurrencia
            FROM motoshop_gold_mart_cohortes_clientes
            GROUP BY mes_cohorte, business_month
            ORDER BY mes_cohorte, business_month
        """)
        nuevos_rows = self._query("""
            WITH ultimo_mes AS (
                SELECT MAX(business_month) AS mm FROM motoshop_gold_mart_cohortes_clientes
            )
            SELECT
                COALESCE(SUM(CASE WHEN mes_cohorte = business_month THEN 1 ELSE 0 END), 0) AS nuevos,
                COALESCE(SUM(CASE WHEN mes_cohorte < business_month AND compro_este_mes THEN 1 ELSE 0 END), 0) AS recurrentes,
                COALESCE(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END), 0) AS top_recurrentes
            FROM motoshop_gold_mart_cohortes_clientes, ultimo_mes
            WHERE business_month = ultimo_mes.mm
        """)
        if not cohortes_rows:
            logger.warning("No cohortes detail data found")
            return CohortesDetailResponse(cohortes=[], total_cohortes=0, nuevos_este_mes=0, recurrentes_este_mes=0, top_recurrentes=0)
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

    # ── Drift Summary ──────────────────────────────────────────────────

    def get_drift_summary(self) -> DriftSummaryResponse:
        try:
            rows = self._query("""
                SELECT alert_msg AS metric_name,
                       STRFTIME(week_end, '%Y-%m-%d') AS detected_at,
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
                FROM motoshop_gold_alertas_drift
                ORDER BY week_end DESC
                LIMIT 50
            """)
            threshold_row = self._query("""
                SELECT COALESCE(MAX(threshold_pct), 30.0) AS current_threshold
                FROM motoshop_gold_alertas_drift
            """)
        except Exception as exc:
            logger.warning("Alertas_drift table not available: %s", exc)
            rows = []
            threshold_row = []
        if not rows:
            return DriftSummaryResponse(items=[], total_alerts=0, active_count=0, warning_count=0, current_threshold=30.0)
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

    # ── Plan Compras ────────────────────────────────────────────────────

    def get_plan_compras(self) -> PlanComprasResponse:
        rows = self._query("""
            WITH demanda_7d AS (
                SELECT cod_producto, SUM(cantidad) AS qty_7d
                FROM motoshop_silver_fact_ventas_detalle
                WHERE business_date >= CURRENT_DATE - INTERVAL '7' DAY
                GROUP BY cod_producto
            ),
            abc_latest AS (
                SELECT cod_producto, categoria_abc
                FROM (
                    SELECT cod_producto, categoria_abc,
                           ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_month DESC) AS rn
                    FROM motoshop_gold_mart_rotacion_abc
                ) WHERE rn = 1
            ),
            alertas_latest AS (
                SELECT sku, urgencia
                FROM (
                    SELECT sku, urgencia,
                           ROW_NUMBER() OVER (PARTITION BY sku ORDER BY urgencia) AS rn
                    FROM motoshop_gold_alertas_quiebre
                ) WHERE rn = 1
            ),
            suppliers AS (
                SELECT d.cod_producto, MAX(c.nombre_proveedor) AS supplier
                FROM motoshop_silver_fact_compras_detalle d
                INNER JOIN motoshop_silver_fact_compras c
                    ON d.num_documento = c.num_documento AND d.cod_clase = c.cod_clase
                WHERE c.nombre_proveedor IS NOT NULL
                GROUP BY d.cod_producto
            )
            SELECT
                inv.cod_producto AS sku,
                COALESCE(NULLIF(inv.nom_producto, ''), inv.cod_producto) AS nombre,
                inv.cantidad_actual AS stock_actual,
                COALESCE(d.qty_7d, 0) AS demanda_7d,
                CASE WHEN COALESCE(d.qty_7d, 0) > inv.cantidad_actual
                     THEN COALESCE(d.qty_7d, 0) - inv.cantidad_actual
                     ELSE 0 END AS cantidad_a_comprar,
                COALESCE(abc.categoria_abc, 'C') AS abc,
                al.urgencia,
                CASE WHEN dorm.cod_producto IS NOT NULL THEN TRUE ELSE FALSE END AS dormido,
                COALESCE(s.supplier, 'Sin proveedor') AS supplier
            FROM motoshop_gold_mart_inventario_actual inv
            LEFT JOIN demanda_7d d ON inv.cod_producto = d.cod_producto
            LEFT JOIN abc_latest abc ON inv.cod_producto = abc.cod_producto
            LEFT JOIN alertas_latest al ON inv.cod_producto = al.sku
            LEFT JOIN motoshop_gold_mart_productos_dormidos dorm
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
            return PlanComprasResponse(items=[], total_skus=0, total_unidades=0.0, total_valor_estimado=0.0, skus_urgentes=0, skus_dormidos=0)
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

    # ── Forecast Categoria ────────────────────────────────────────────

    def get_forecast_categoria(self) -> ForecastCategoriaResponse:
        rows = self._query("""
            SELECT cod_grupo,
                   ROUND(SUM(demanda_real), 2) AS demanda_real,
                   ROUND(SUM(demanda_predicha_baseline), 2) AS demanda_predicha,
                   ROUND(ABS(SUM(demanda_real) - SUM(demanda_predicha_baseline))
                         / NULLIF(SUM(demanda_real), 0) * 100, 2) AS desviacion_pct,
                   MAX(metodo_baseline) AS metodo
            FROM motoshop_gold_forecast_categoria
            WHERE business_date >= CURRENT_DATE - INTERVAL '30' DAY
            GROUP BY cod_grupo
            ORDER BY demanda_real DESC
        """)
        coverage_row = self._query("""
            SELECT ROUND(COUNT(DISTINCT cod_grupo) * 100.0
                   / NULLIF((SELECT COUNT(DISTINCT cod_grupo)
                             FROM motoshop_gold_forecast_categoria), 0), 2) AS cobertura_pct
            FROM motoshop_gold_forecast_categoria
            WHERE business_date >= CURRENT_DATE - INTERVAL '30' DAY
        """)
        if not rows:
            logger.warning("No forecast categoria data found")
            return ForecastCategoriaResponse(items=[], total_categorias=0, wape_promedio=0.0, cobertura_pct=0.0)
        for r in rows:
            r["demanda_real"] = float(r["demanda_real"] or 0.0)
            r["demanda_predicha"] = float(r["demanda_predicha"] or 0.0)
            r["desviacion_pct"] = float(r["desviacion_pct"] or 0.0)
        wape = sum(abs(r["demanda_real"] - r["demanda_predicha"]) for r in rows) / sum(r["demanda_real"] for r in rows) * 100
        cobertura = float(coverage_row[0]["cobertura_pct"]) if coverage_row else 99.9
        return ForecastCategoriaResponse(
            items=[ForecastCategoriaItem(**r) for r in rows],
            total_categorias=len(rows),
            wape_promedio=round(wape, 2),
            cobertura_pct=cobertura,
        )


    # ── Sales Summary V2 (V1.8) ──────────────────────────────────────────

    def get_sales_summary_v2(self) -> dict:
        """Ventas con comparación justa: parcial vs parcial, años anteriores."""
        from datetime import date

        # Max date
        max_d = self._con.execute(
            "SELECT MAX(business_date) FROM motoshop_gold_mart_ventas_diarias_sku"
        ).fetchone()[0]
        max_date = max_d if max_d else date.today()
        max_date_str = str(max_date)
        current_month = max_date.strftime("%Y-%m")
        day_num = max_date.day

        # Current month accumulated
        curr = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COALESCE(SUM(num_facturas),0),
                   ROUND(COALESCE(SUM(valor_total),0)/NULLIF(COALESCE(SUM(num_facturas),0),0),2),
                   COUNT(DISTINCT business_date)
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date,'%Y-%m') = ?
        """, [current_month]).fetchone()

        # Previous month, same day window
        prev_month_date = max_date.replace(day=1) - timedelta(days=1)
        prev_month = prev_month_date.strftime("%Y-%m")
        prev_day = min(day_num, (max_date.replace(day=1) - timedelta(days=1)).day)
        prev_start = f"{prev_month}-01"
        prev_end = f"{prev_month}-{prev_day:02d}"

        prev = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2)
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date >= ? AND business_date <= ?
        """, [prev_start, prev_end]).fetchone()

        va_curr = float(curr[0] or 0)
        va_prev = float(prev[0] or 0)
        delta = round((va_curr - va_prev) / va_prev * 100, 1) if va_prev else None

        # Same month, previous years
        years_prev = []
        for yr in range(max_date.year - 1, max_date.year - 3, -1):
            try:
                y_start = f"{yr}-{max_date.month:02d}-01"
                y_end = f"{yr}-{max_date.month:02d}-{day_num:02d}"
                y_same = self._con.execute("""
                    SELECT ROUND(COALESCE(SUM(valor_total),0),2) FROM motoshop_gold_mart_ventas_diarias_sku
                    WHERE business_date >= ? AND business_date <= ?
                """, [y_start, y_end]).fetchone()
                y_full = self._con.execute("""
                    SELECT ROUND(COALESCE(SUM(valor_total),0),2) FROM motoshop_gold_mart_ventas_diarias_sku
                    WHERE STRFTIME(business_date,'%Y-%m') = ?
                """, [f"{yr}-{max_date.month:02d}"]).fetchone()
                y_amount = float(y_same[0] or 0)
                y_delta = round((va_curr - y_amount) / y_amount * 100, 1) if y_amount else None
                years_prev.append({
                    "year": yr,
                    "same_day_window_amount": y_amount,
                    "full_month_amount": float(y_full[0] or 0),
                    "delta_same_window_pct": y_delta,
                })
            except Exception:
                pass

        return {
            "business_month": current_month,
            "max_sales_date": max_date_str,
            "current_month_accumulated": va_curr,
            "current_month_days_with_sales": int(curr[3] or 0),
            "previous_month_same_window": {
                "from": prev_start,
                "to": prev_end,
                "amount": va_prev,
                "delta_pct": delta,
            },
            "same_month_previous_years": years_prev,
            "ticket_promedio": float(curr[2] or 0),
            "num_facturas": int(curr[1] or 0),
        }


    # ── Sales Daily Month (V1.8) ──────────────────────────────────────

    def get_sales_daily_month(self, month: str) -> dict:
        """Evolución diaria del mes: ventas, facturas, acumulado por día."""
        rows = self._con.execute("""
            SELECT business_date, ROUND(COALESCE(SUM(valor_total),0),2) AS ventas,
                   COALESCE(SUM(num_facturas),0) AS facturas,
                   ROUND(COALESCE(SUM(valor_total),0)/NULLIF(COALESCE(SUM(num_facturas),0),0),2) AS ticket
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date,'%Y-%m') = ?
            GROUP BY business_date ORDER BY business_date
        """, [month]).fetchall()

        days = []
        accum = 0.0
        for r in rows:
            d_str = str(r[0])
            accum += float(r[1] or 0)
            days.append({
                "date": d_str,
                "day": int(d_str.split("-")[2]),
                "sales": float(r[1] or 0),
                "invoices": int(r[2] or 0),
                "avg_ticket": float(r[3] or 0),
                "accumulated": round(accum, 2),
            })
        return {"month": month, "days": days, "total_days_with_sales": len(days)}


    # ── Sales Forecast Monthly (V1.8) ─────────────────────────────────

    def get_sales_forecast_monthly(self, horizon: int = 2) -> dict:
        """Proyección run-rate: mes actual + siguiente. Modelo simple, sin LLM."""
        from datetime import date

        max_d = self._con.execute(
            "SELECT MAX(business_date) FROM motoshop_gold_mart_ventas_diarias_sku"
        ).fetchone()[0]
        max_date = max_d if max_d else date.today()
        current_month = max_date.strftime("%Y-%m")
        day_num = max_date.day

        # Current month: acumulado / días con venta → run-rate diario
        curr = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COUNT(DISTINCT business_date)
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date,'%Y-%m') = ?
        """, [current_month]).fetchone()
        accum = float(curr[0] or 0)
        days_with_sales = int(curr[1] or 1) or 1

        total_days = (max_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        remaining_days = total_days.day - day_num
        daily_rate = accum / days_with_sales
        projected_current = round(accum + daily_rate * remaining_days, 2)

        # Next month: run-rate + seasonal factor from same month last year
        next_month_num = max_date.month + 1
        next_year = max_date.year if next_month_num <= 12 else max_date.year + 1
        next_month_num = next_month_num if next_month_num <= 12 else 1
        next_month_str = f"{next_year}-{next_month_num:02d}"
        next_total_days = (date(next_year, next_month_num, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Seasonal: same month last year
        ly_month = f"{max_date.year - 1}-{max_date.month:02d}"
        ly_sales = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2)
            FROM motoshop_gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
        """, [ly_month]).fetchone()
        ly_val = float(ly_sales[0] or 0)

        # Last 3 complete months
        months = []
        for i in range(1, 4):
            m = max_date.month - i
            y = max_date.year
            if m <= 0:
                m += 12
                y -= 1
            m_str = f"{y}-{m:02d}"
            mv = self._con.execute("""
                SELECT ROUND(COALESCE(SUM(valor_total),0),2)
                FROM motoshop_gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
            """, [m_str]).fetchone()
            months.append(float(mv[0] or 0))

        avg_last_3 = sum(months) / len([m for m in months if m > 0]) if any(months) else accum
        next_projected = round(daily_rate * next_total_days.day, 2)

        return {
            "current_month": {
                "month": current_month,
                "observed_amount": accum,
                "projected_amount": projected_current,
                "daily_rate": round(daily_rate, 2),
                "days_observed": day_num,
                "days_total": total_days.day,
                "confidence": "high" if day_num > 7 else "medium",
            },
            "next_month": {
                "month": next_month_str,
                "projected_amount": next_projected,
                "days_total": next_total_days.day,
                "last_year_same_month": ly_val,
                "confidence": "low",
            },
            "model_version": "run_rate_v1",
            "drivers": ["daily_run_rate", "same_month_last_year"],
        }


def _prev_month_str(month: str) -> str:
    """Retorna el mes anterior en formato YYYY-MM."""
    d = datetime.strptime(month, "%Y-%m")
    if d.month == 1:
        d = d.replace(year=d.year - 1, month=12)
    else:
        d = d.replace(month=d.month - 1)
    return d.strftime("%Y-%m")


def get_duckdb_repo() -> DuckDBMetricsRepo:
    """Factory para crear DuckDBMetricsRepo con ruta configurable."""
    return DuckDBMetricsRepo()
