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

import threading

# Shared DuckDB connection pool: key = resolved file path, value = connection
# Prevents OOM by ensuring at most ONE connection per DuckDB file across all endpoints.
_shared_connections: dict[str, duckdb.DuckDBPyConnection] = {}
_shared_connections_lock = threading.Lock()


def get_shared_connection(db_path: str | Path) -> duckdb.DuckDBPyConnection:
    """Return a shared DuckDB read-only connection for *db_path*.

    Creates one on first access, reuses on subsequent calls.
    Thread-safe: the first caller creates the connection, all others share it.
    """
    key = str(Path(db_path).resolve())
    if key not in _shared_connections:
        with _shared_connections_lock:
            # Double-check inside lock
            if key not in _shared_connections:
                _shared_connections[key] = duckdb.connect(key, read_only=True)
    return _shared_connections[key]


def close_all_shared_connections() -> None:
    """Close every pooled connection. Call on application shutdown."""
    for path, con in _shared_connections.items():
        try:
            con.close()
        except Exception:
            logger.warning("Error closing shared DuckDB connection for %s", path)
    _shared_connections.clear()


def _make_db_path(tenant: str) -> Path:
    """Construye la ruta al archivo DuckDB según tenant y entorno.

    En prod usa /tmp/{tenant}_gold.duckdb.
    En dev (local) usa out/{tenant}_gold.duckdb.

    NOTA (2026-06-15): se removio la lectura de DUCKDB_PATH env var. Estaba
    causando que el override fijo a motoshop_gold.duckdb se aplicara a TODOS
    los tenants, asi masvital leia el DuckDB equivocado. Si necesitas override
    explicito por dev local, pasa db_path al constructor de DuckDBMetricsRepo.
    """
    if os.environ.get("ENV") == "prod":
        return Path(f"/tmp/{tenant}_gold.duckdb")
    return Path(f"out/{tenant}_gold.duckdb")


# V1.10.8: auto-refresh desde R2. Throttle de chequeo HEAD a R2 por
# tenant (no chequear en cada request — solo cada N segundos).
_R2_LAST_CHECK: dict[str, float] = {}
_R2_CHECK_INTERVAL_SEC = 60  # chequear LastModified en R2 maximo 1 vez/min por tenant

# V1.12: trackear el LastModified de R2 de la ULTIMA bajada por tenant.
# Antes comparabamos mtime de R2 con mtime del filesystem local, pero el
# replace() del archivo bajado actualiza el mtime local a NOW (no preserva
# el mtime original de R2). Eso causaba que uploads posteriores cercanos
# en tiempo no triggeraran la bajada (margen de 10s + diferencia de relojes
# se comian las nuevas versiones). Ahora trackeamos r2_mtime explicito.
_R2_DOWNLOADED_MTIME: dict[str, float] = {}


def _bootstrap_duckdb_from_r2(db_path: Path, tenant: str = "motoshop") -> None:
    """Descarga {tenant}_gold.duckdb desde R2 si:
       - no existe localmente, O
       - el de R2 es mas nuevo que el local (auto-refresh).

    El segundo caso es lo importante: el pipeline corre cada 30 min y
    sube un archivo fresco a R2; sin esta logica el backend quedaba con
    el archivo del arranque hasta el siguiente deploy.

    Hay throttle: solo se hace HEAD a R2 maximo 1 vez por minuto por
    tenant para no agregar latencia a cada request."""
    r2_endpoint = os.environ.get("R2_ENDPOINT")
    r2_key = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    r2_bucket = os.environ.get("R2_BUCKET", "motoshop-gold")
    r2_object_key = os.environ.get("R2_OBJECT_KEY", f"{tenant}_gold.duckdb")

    if not all([r2_endpoint, r2_key, r2_secret]):
        if not db_path.exists():
            logger.warning("R2 credentials not set; skipping bootstrap download")
        return

    # Decidir si descargar:
    # 1) no existe local -> SIEMPRE descargar
    # 2) existe pero ya paso el throttle -> chequear R2 mtime
    must_download = not db_path.exists()
    if not must_download:
        from time import time
        last = _R2_LAST_CHECK.get(tenant, 0)
        now = time()
        if now - last < _R2_CHECK_INTERVAL_SEC:
            return  # within throttle, no chequear
        _R2_LAST_CHECK[tenant] = now

    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
            region_name="auto",
        )

        r2_mtime = None
        if not must_download:
            # V1.12: comparar LastModified de R2 contra el r2_mtime de la
            # ULTIMA bajada (no contra el mtime local, que se actualiza con
            # cada replace y rompia la deteccion de uploads cercanos).
            try:
                head = s3.head_object(Bucket=r2_bucket, Key=r2_object_key)
                r2_mtime = head['LastModified'].timestamp()
                last_downloaded = _R2_DOWNLOADED_MTIME.get(tenant, 0)
                if r2_mtime > last_downloaded:
                    must_download = True
                    logger.info(
                        "R2 has newer file for %s (R2=%.0fs ago, last_dl=%.0fs ago) — refreshing",
                        tenant,
                        (time() - r2_mtime),
                        (time() - last_downloaded) if last_downloaded else -1,
                    )
            except Exception as exc:
                logger.debug("HEAD check failed for %s: %s", tenant, exc)
                return  # no romper si HEAD falla, mantener archivo local

        if must_download:
            logger.info("Downloading DuckDB from R2: %s/%s", r2_bucket, r2_object_key)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            # bajar a un archivo temporal y mover atomicamente: asi una request
            # concurrente no abre un archivo a medio bajar
            tmp_path = db_path.with_suffix(db_path.suffix + ".downloading")
            s3.download_file(r2_bucket, r2_object_key, str(tmp_path))
            # Si no teniamos r2_mtime (caso must_download = not db_path.exists()),
            # ahora lo conseguimos del HEAD
            if r2_mtime is None:
                try:
                    head = s3.head_object(Bucket=r2_bucket, Key=r2_object_key)
                    r2_mtime = head['LastModified'].timestamp()
                except Exception:
                    r2_mtime = time()  # fallback al wall clock
            # V1.12.1: REMOVER la conexion vieja del pool sin cerrarla.
            # Antes haciamos con.close() inmediato, pero eso rompia queries
            # concurrentes con "No open result set". Al solo pop()-earla, el
            # proximo request abre una conexion nueva al archivo nuevo, y las
            # queries en vuelo siguen leyendo del inode viejo (replace es
            # atomico en Linux y el FD viejo sigue valido hasta que se libere).
            # Python GC cierra la conexion vieja cuando nadie la referencia.
            try:
                key = str(db_path.resolve())
                with _shared_connections_lock:
                    _shared_connections.pop(key, None)
            except Exception as exc:
                logger.warning("Could not evict old connection for %s: %s", db_path, exc)
            tmp_path.replace(db_path)
            _R2_DOWNLOADED_MTIME[tenant] = r2_mtime
            logger.info("DuckDB refreshed to %s (r2_mtime=%.0f)", db_path, r2_mtime)
    except Exception as exc:
        logger.warning("Failed to download DuckDB from R2: %s", exc)


class DuckDBMetricsRepo:
    """Lee de archivo DuckDB local usando SQL directo.

    Misma interfaz que RealMetricsRepo pero sin dependencia de Databricks.
    """

    def __init__(self, db_path: str | Path | None = None, tenant: str = "motoshop") -> None:
        self._tenant = tenant
        if db_path is None:
            db_path = _make_db_path(tenant)
        self._path = Path(db_path)
        _bootstrap_duckdb_from_r2(self._path, tenant)
        if not self._path.exists():
            raise FileNotFoundError(
                f"DuckDB file not found at {self._path}. "
                "Run 'python pipeline/run_all.py' first, or set DUCKDB_PATH."
            )
        logger.info("DuckDBMetricsRepo connected to %s", self._path)

    @property
    def _con(self) -> "duckdb.DuckDBPyConnection":
        """Conexion DuckDB actual del pool compartido.

        V1.10.8: hacemos esto property para que cada query agarre la conexion
        viva del pool, no una referencia a una conexion que pudo haber sido
        cerrada (por re-download desde R2 o /admin/refresh). Si la conexion
        fue cerrada, _bootstrap re-descarga y get_shared_connection abre una
        nueva al toque.
        """
        # Re-check freshness en cada acceso (esta throttleado a 1/min/tenant,
        # asi que en la practica casi siempre devuelve inmediato sin tocar R2)
        _bootstrap_duckdb_from_r2(self._path, self._tenant)
        return get_shared_connection(self._path)

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
                SELECT MAX(business_date) AS max_date FROM gold_mart_ventas_diarias_sku
            )
            SELECT
                STRFTIME(business_date, '%Y-%m') AS business_month,
                ROUND(SUM(valor_total), 2) AS ventas_mes,
                ROUND(SUM(cantidad_total), 2) AS cantidad_total,
                SUM(num_facturas) AS num_facturas,
                ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM gold_mart_ventas_diarias_sku, max_dates
            WHERE business_date >= max_dates.max_date - INTERVAL '60' DAY
            GROUP BY STRFTIME(business_date, '%Y-%m')
            ORDER BY business_month DESC
            LIMIT 2
        """)

        top = self._query("""
            WITH max_dates AS (
                SELECT MAX(business_date) AS max_date FROM gold_mart_ventas_diarias_sku
            )
            SELECT
                cod_producto, nom_producto,
                ROUND(SUM(cantidad_total), 2) AS cantidad_total,
                ROUND(SUM(valor_total), 2) AS valor_total,
                ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM gold_mart_ventas_diarias_sku, max_dates
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
            FROM gold_mart_ventas_diarias_sku
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
            FROM gold_mart_ventas_diarias_sku
            WHERE business_date = ?
            GROUP BY cod_producto, nom_producto
            ORDER BY valor DESC
        """, [effective_date])
        totals = self._query("""
            SELECT
                ROUND(COALESCE(SUM(valor_total), 0), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM gold_mart_ventas_diarias_sku
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

    def get_sales_monthly(self, month: str, products_limit: int = 10) -> SalesMonthlyResponse:
        # products_limit: cantidad maxima de productos top a devolver.
        # default 10 (preview). Pasar >10 (ej 5000) trae TODOS los productos
        # del mes ordenados por valor — el front decide cuantos mostrar.
        products_limit = max(1, min(int(products_limit), 5000))
        totals = self._query("""
            SELECT
                ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
        """, [month])
        prev = self._query("""
            SELECT ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS total_ventas
            FROM gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
        """, [_prev_month_str(month)])
        top = self._query(f"""
            SELECT
                v.cod_producto AS cod_producto,
                v.nom_producto AS nom_producto,
                ROUND(SUM(v.cantidad_total), 2) AS cantidad_total,
                ROUND(SUM(v.valor_total), 2) AS valor_total,
                ROUND(SUM(v.valor_total) / NULLIF(SUM(SUM(v.valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso,
                ANY_VALUE(dp.presentacion) AS presentacion
            FROM gold_mart_ventas_diarias_sku v
            LEFT JOIN silver_dim_producto dp ON dp.cod_producto = v.cod_producto
            WHERE STRFTIME(v.business_date, '%Y-%m') = ?
            GROUP BY v.cod_producto, v.nom_producto
            ORDER BY valor_total DESC
            LIMIT {products_limit}
        """, [month])
        # Mapear presentacion -> unidad_medida label corto
        for r in top:
            r["unidad_medida"] = _presentacion_to_unidad(r.get("presentacion"))
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

    def get_sales_historical_products(self, limit: int = 10) -> dict:
        """Top productos vendidos en TODO el histórico (agregado por SKU).

        Reusa la misma estructura TopSkuItem que sales-monthly. Default 10
        para preview; el front pide >10 cuando el usuario expande "ver todos".
        """
        limit = max(1, min(int(limit), 5000))
        rows = self._query(f"""
            SELECT
                v.cod_producto AS cod_producto,
                v.nom_producto AS nom_producto,
                ROUND(SUM(v.cantidad_total), 2) AS cantidad_total,
                ROUND(SUM(v.valor_total), 2) AS valor_total,
                ROUND(SUM(v.valor_total) / NULLIF(SUM(SUM(v.valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso,
                ANY_VALUE(dp.presentacion) AS presentacion
            FROM gold_mart_ventas_diarias_sku v
            LEFT JOIN silver_dim_producto dp ON dp.cod_producto = v.cod_producto
            GROUP BY v.cod_producto, v.nom_producto
            ORDER BY valor_total DESC
            LIMIT {limit}
        """)
        for r in rows:
            r["unidad_medida"] = _presentacion_to_unidad(r.get("presentacion"))
        total_skus = self._query("""
            SELECT COUNT(DISTINCT cod_producto) AS n
            FROM gold_mart_ventas_diarias_sku
        """)
        return {
            "items": [TopSkuItem(**r).model_dump() for r in rows],
            "total_skus_con_venta": int(total_skus[0]["n"] or 0) if total_skus else 0,
        }

    def get_sales_historical(self) -> SalesHistoricalResponse:
        totals = self._query("""
            SELECT
                ROUND(SUM(valor_total), 2) AS total_ventas,
                COALESCE(SUM(num_facturas), 0) AS total_facturas
            FROM gold_mart_ventas_diarias_sku
        """)
        meses = self._query("""
            SELECT YEAR(business_date) AS year,
                   MONTH(business_date) AS month,
                   ROUND(SUM(valor_total), 2) AS total_ventas,
                   COALESCE(SUM(num_facturas), 0) AS num_facturas,
                   ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM gold_mart_ventas_diarias_sku
            GROUP BY YEAR(business_date), MONTH(business_date)
            ORDER BY year, month
        """)
        first = self._query("""
            SELECT MIN(business_date) AS first_date
            FROM gold_mart_ventas_diarias_sku
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
        # V1.9.3 (2026-06-16): inventario REAL calculado on-the-fly
        # (compras - ventas) en vez de leer del snapshot gold_mart_inventario_actual
        # que se quedaba desactualizado entre corridas. Usa INVENTARIO_REAL_CTE.
        # Solo contamos como "productos" los SKUs con cantidad > 0 (los que
        # realmente tienen stock fisico), aunque el cantidad_actual sume todo
        # el inventario disponible.
        rows = self._query(f"""
            WITH inventario AS ({INVENTARIO_REAL_CTE})
            SELECT
                ROUND(SUM(GREATEST(cantidad_actual, 0)), 2) AS stock_total,
                SUM(CASE WHEN cantidad_actual > 0 THEN 1 ELSE 0 END) AS num_productos
            FROM inventario
        """)
        valor = self._query(f"""
            WITH inventario AS ({INVENTARIO_REAL_CTE}),
            latest_cost AS (
                SELECT cod_producto, costo_producto,
                       ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) AS rn
                FROM silver_fact_compras_detalle
                WHERE costo_producto > 0
            )
            SELECT COALESCE(ROUND(SUM(GREATEST(i.cantidad_actual, 0) * COALESCE(lc.costo_producto, 0)), 2), 0) AS valor_total
            FROM inventario i
            LEFT JOIN latest_cost lc ON i.cod_producto = lc.cod_producto AND lc.rn = 1
        """)
        bodegas = self._query(f"""
            WITH inventario AS ({INVENTARIO_REAL_CTE}),
            default_bodega AS (
                SELECT cod_bodega AS def_cod, nombre_bodega AS def_nom
                FROM silver_dim_bodega
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
                ROUND(SUM(GREATEST(inv.cantidad_actual, 0)), 2) AS cantidad,
                ROUND(SUM(GREATEST(inv.cantidad_actual, 0)) / NULLIF(SUM(SUM(GREATEST(inv.cantidad_actual, 0))) OVER(), 0) * 100, 1) AS porcentaje
            FROM inventario inv
            CROSS JOIN default_bodega db
            WHERE inv.cantidad_actual > 0
            GROUP BY 1, 2
            ORDER BY cantidad DESC
        """)
        if not rows:
            raise RuntimeError("No inventory data found")
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
                SELECT MAX(business_month) AS mm FROM gold_mart_rotacion_abc
            )
            SELECT max_month.mm AS business_month,
                   categoria_abc AS categoria, COUNT(*) AS num_skus,
                   ROUND(SUM(valor_total), 2) AS valor_total,
                   ROUND(SUM(valor_total) / NULLIF(SUM(SUM(valor_total)) OVER(), 0) * 100, 1) AS porcentaje_ingreso
            FROM gold_mart_rotacion_abc, max_month
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
        # NOTA: gold_mart_rotacion_abc NO tiene nom_producto (solo
        # business_month, cod_producto, valor_total, categoria_abc). El nombre
        # se resuelve por UNION de inventario_actual + ventas_diarias_sku para
        # cubrir productos sin stock que sí tuvieron ventas en el mes ABC.
        rows = self._query("""
            WITH dim AS (
                SELECT cod_producto, MAX(nom_producto) AS nom_producto
                FROM (
                    SELECT cod_producto, nom_producto FROM gold_mart_inventario_actual
                    UNION ALL
                    SELECT cod_producto, nom_producto FROM gold_mart_ventas_diarias_sku
                )
                GROUP BY cod_producto
            )
            SELECT
                a.cod_producto,
                COALESCE(d.nom_producto, a.cod_producto) AS nom_producto,
                ROUND(a.valor_total, 2) AS valor_total,
                ROUND(a.valor_total / NULLIF(SUM(a.valor_total) OVER(PARTITION BY a.categoria_abc), 0) * 100, 1) AS porcentaje_bucket
            FROM gold_mart_rotacion_abc a
            LEFT JOIN dim d USING (cod_producto)
            WHERE a.business_month = (SELECT MAX(business_month) FROM gold_mart_rotacion_abc)
              AND a.categoria_abc = ?
            ORDER BY a.valor_total DESC
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
        """Productos dormidos REALES — vendían y dejaron de vender.

        V1.16: filtra el bug epoch del pipeline (productos NUNCA vendidos
        con ultima_fecha_venta='1970-01-01' en gold_mart_productos_dormidos).
        Los nunca vendidos viven ahora en get_productos_zombie() — son un
        concepto distinto: nunca movieron, no se durmieron.
        """
        # Filtro principal: EXISTS en silver_fact_ventas_detalle (vendió alguna vez)
        count_rows = self._query("""
            SELECT COUNT(*) AS total
            FROM gold_mart_productos_dormidos d
            WHERE EXISTS (
                SELECT 1 FROM silver_fact_ventas_detalle v
                WHERE v.cod_producto = d.cod_producto
            )
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
                    CAST(v.ultima_venta AS VARCHAR) AS ultima_venta,
                    DATE_DIFF('day', v.ultima_venta, CURRENT_DATE) AS dias_sin_venta
            FROM gold_mart_productos_dormidos d
            INNER JOIN (
                SELECT cod_producto, MAX(business_date) AS ultima_venta
                FROM silver_fact_ventas_detalle
                GROUP BY cod_producto
            ) v ON d.cod_producto = v.cod_producto
            LEFT JOIN (
                SELECT cod_producto, MAX(business_date) AS ultima_compra
                FROM silver_fact_compras_detalle
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

    def get_productos_zombie(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Productos que NUNCA se vendieron desde que entraron al catálogo.

        V1.16: separa el concepto de 'nunca vendido' (catálogo zombie) del
        de 'dormido' (vendía y dejó de vender). Acción típica: liquidar,
        devolver al proveedor, descatalogar.

        Calcula capital inmovilizado: stock × costo (última compra como
        fallback si costo_producto=0).
        """
        # Total + capital
        totals_rows = self._query("""
            SELECT
                COUNT(*) AS total,
                ROUND(COALESCE(SUM(
                    dp.existencia * COALESCE(NULLIF(dp.costo_producto, 0), dp.costo_ultima_compra)
                ), 0), 0) AS capital_inmovilizado
            FROM silver_dim_producto dp
            WHERE NOT EXISTS (
                SELECT 1 FROM silver_fact_ventas_detalle v
                WHERE v.cod_producto = dp.cod_producto
            )
        """)
        total = int(totals_rows[0]["total"]) if totals_rows else 0
        capital = float(totals_rows[0]["capital_inmovilizado"] or 0) if totals_rows else 0.0

        offset = (page - 1) * page_size
        rows = self._query("""
            SELECT
                dp.cod_producto,
                dp.nombre_producto AS nom_producto,
                COALESCE(dp.existencia, 0) AS stock_actual,
                COALESCE(NULLIF(dp.costo_producto, 0), dp.costo_ultima_compra, 0) AS costo_unitario,
                ROUND(COALESCE(dp.existencia, 0) *
                    COALESCE(NULLIF(dp.costo_producto, 0), dp.costo_ultima_compra, 0), 0) AS capital_invertido,
                CAST(c.ultima_compra AS VARCHAR) AS ultima_compra,
                DATE_DIFF('day', c.ultima_compra, CURRENT_DATE) AS dias_en_catalogo,
                dp.presentacion
            FROM silver_dim_producto dp
            LEFT JOIN (
                SELECT cod_producto, MAX(business_date) AS ultima_compra
                FROM silver_fact_compras_detalle
                GROUP BY cod_producto
            ) c ON dp.cod_producto = c.cod_producto
            WHERE NOT EXISTS (
                SELECT 1 FROM silver_fact_ventas_detalle v
                WHERE v.cod_producto = dp.cod_producto
            )
            ORDER BY capital_invertido DESC NULLS LAST, dp.cod_producto
            LIMIT ? OFFSET ?
        """, [page_size, offset])
        items = []
        for r in rows:
            items.append({
                "cod_producto": r["cod_producto"],
                "nom_producto": r["nom_producto"] or "",
                "stock_actual": float(r["stock_actual"] or 0),
                "costo_unitario": float(r["costo_unitario"] or 0),
                "capital_invertido": float(r["capital_invertido"] or 0),
                "ultima_compra": str(r["ultima_compra"]) if r["ultima_compra"] else None,
                "dias_en_catalogo": int(r["dias_en_catalogo"]) if r["dias_en_catalogo"] is not None else None,
                "presentacion": r["presentacion"],
                "unidad_medida": _presentacion_to_unidad(r.get("presentacion")),
            })
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "capital_inmovilizado": capital,
            "items": items,
        }

    # ── Salud del catálogo (V1.16, F6 del EDA) ───────────────────────────

    def get_salud_catalogo(self) -> dict:
        """KPI agregado del catálogo: cuántos SKUs están activos, lentos,
        dormidos o nunca vendidos. Útil como medidor único de la salud
        del inventario y motivador de acción.

        Buckets:
          - activos: vendieron en últimos 30 días
          - lentos: vendieron 30-90 días atrás
          - dormidos: vendieron hace >90 días pero alguna vez
          - zombie: nunca se vendieron
        """
        rows = self._query("""
            WITH ultima_venta AS (
                SELECT cod_producto, MAX(business_date) AS uv
                FROM silver_fact_ventas_detalle
                GROUP BY cod_producto
            )
            SELECT
                SUM(CASE WHEN uv.uv IS NULL THEN 1 ELSE 0 END) AS zombie,
                SUM(CASE WHEN uv.uv IS NOT NULL
                          AND DATE_DIFF('day', uv.uv, CURRENT_DATE) > 90 THEN 1 ELSE 0 END) AS dormidos,
                SUM(CASE WHEN uv.uv IS NOT NULL
                          AND DATE_DIFF('day', uv.uv, CURRENT_DATE) BETWEEN 31 AND 90 THEN 1 ELSE 0 END) AS lentos,
                SUM(CASE WHEN uv.uv IS NOT NULL
                          AND DATE_DIFF('day', uv.uv, CURRENT_DATE) <= 30 THEN 1 ELSE 0 END) AS activos,
                COUNT(*) AS total
            FROM silver_dim_producto dp
            LEFT JOIN ultima_venta uv ON uv.cod_producto = dp.cod_producto
        """)
        r = rows[0] if rows else {}
        total = int(r.get("total") or 0)
        activos = int(r.get("activos") or 0)
        lentos = int(r.get("lentos") or 0)
        dormidos = int(r.get("dormidos") or 0)
        zombie = int(r.get("zombie") or 0)
        # Score salud: porcentaje activos + lentos (los que generan negocio)
        salud_pct = round((activos + lentos) / total * 100, 1) if total else 0.0
        return {
            "total_skus": total,
            "activos": activos,
            "activos_pct": round(activos / total * 100, 1) if total else 0.0,
            "lentos": lentos,
            "lentos_pct": round(lentos / total * 100, 1) if total else 0.0,
            "dormidos": dormidos,
            "dormidos_pct": round(dormidos / total * 100, 1) if total else 0.0,
            "zombie": zombie,
            "zombie_pct": round(zombie / total * 100, 1) if total else 0.0,
            "salud_pct": salud_pct,
        }

    # ── Heatmap día × hora (V1.16, F4 del EDA) ───────────────────────────

    def get_heatmap_dia_hora(self, fecha_inicio: str, fecha_fin: str) -> dict:
        """Matriz 7 días × 24 horas con ventas + facturas + ticket promedio.

        Útil para decidir personal, identificar picos (ej: 'sábados a las 5pm
        es siempre el techo'), y detectar gaps (ej: 'masvital cierra dominicales').
        """
        rows = self._query("""
            SELECT
                EXTRACT(dow FROM business_date)::INT AS dow,
                EXTRACT(hour FROM fecha_documento_ts)::INT AS hora,
                COUNT(*) AS num_facturas,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                ROUND(AVG(total_factura), 2) AS ticket_promedio
            FROM silver_fact_ventas
            WHERE business_date BETWEEN ? AND ?
              AND estado_documento != 'A'
              AND fecha_documento_ts IS NOT NULL
            GROUP BY dow, hora
        """, [fecha_inicio, fecha_fin])
        # Construir matriz completa 7×24 con 0s para celdas vacías
        cells = []
        by_key = {(int(r["dow"]), int(r["hora"])): r for r in rows}
        dias_label = ["DOM", "LUN", "MAR", "MIE", "JUE", "VIE", "SAB"]
        for dow in range(7):
            for hora in range(24):
                r = by_key.get((dow, hora))
                cells.append({
                    "dow": dow,
                    "dow_label": dias_label[dow],
                    "hora": hora,
                    "num_facturas": int(r["num_facturas"]) if r else 0,
                    "total_ventas": float(r["total_ventas"]) if r else 0.0,
                    "ticket_promedio": float(r["ticket_promedio"]) if r and r["ticket_promedio"] else 0.0,
                })
        # Stats globales para colorizar bien
        max_facturas = max((c["num_facturas"] for c in cells), default=0)
        max_ventas = max((c["total_ventas"] for c in cells), default=0.0)
        return {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "cells": cells,
            "max_facturas": max_facturas,
            "max_ventas": max_ventas,
        }

    # ── Vendor data availability flag (V1.16, F7 del EDA) ────────────────

    def get_vendor_data_flag(self) -> dict:
        """Detecta si este tenant tiene datos confiables de vendedor.

        Si >50% de las facturas tienen nit_vendedor NULL/vacío, el front
        debería ocultar el bloque de 'Top vendedores' porque no es útil.
        Caso típico: MasVital tiene 99% NULL, MotoShop 0.4% NULL.
        """
        rows = self._query("""
            SELECT
                SUM(CASE WHEN nit_vendedor IS NULL OR TRIM(nit_vendedor) = '' THEN 1 ELSE 0 END) AS sin_vendedor,
                COUNT(*) AS total
            FROM silver_fact_ventas
            WHERE estado_documento != 'A'
        """)
        r = rows[0] if rows else {}
        total = int(r.get("total") or 0)
        sin = int(r.get("sin_vendedor") or 0)
        pct_sin = (sin / total * 100) if total else 0.0
        has_data = pct_sin < 50.0
        return {
            "has_vendor_data": has_data,
            "facturas_sin_vendedor": sin,
            "facturas_totales": total,
            "porcentaje_sin_vendedor": round(pct_sin, 1),
        }

    # ── Cohortes ─────────────────────────────────────────────────────────

    def get_cohortes(self) -> CohortesResponse:
        rows = self._query("""
            SELECT
                STRFTIME(TRY_CAST(mes_cohorte AS DATE), '%Y-%m') AS cohorte_mes,
                STRFTIME(TRY_CAST(business_month AS DATE), '%Y-%m') AS mes_observacion,
                COUNT(DISTINCT nit_cliente) AS num_clientes,
                ROUND(AVG(ticket_promedio), 2) AS ticket_promedio,
                ROUND(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS tasa_recurrencia
            FROM gold_mart_cohortes_clientes
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
        # V1.10.9: periods y year son int validados (FastAPI Query); los
        # embedemos inline para evitar un bug intermitente del binding
        # mixto (interval dinamico + parametro entero) que en prod hacia
        # que con year=2026 devuelva vacio aunque el archivo tenia datos.
        periods_int = max(1, min(int(periods), 24))
        where_year = f"AND YEAR(business_date) = {int(year)}" if year is not None else ""
        rows = self._query(f"""
            SELECT YEAR(business_date) AS year,
                    MONTH(business_date) AS month,
                    ROUND(SUM(valor_total), 2) AS total_ventas,
                    COALESCE(SUM(num_facturas), 0) AS num_facturas,
                    ROUND(SUM(valor_total) / NULLIF(SUM(num_facturas), 0), 2) AS ticket_promedio
            FROM gold_mart_ventas_diarias_sku
            WHERE business_date >= CURRENT_DATE - INTERVAL '{periods_int}' MONTH
            {where_year}
            GROUP BY YEAR(business_date), MONTH(business_date)
            ORDER BY year, month
        """, [])
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
        max_month_sql = "(SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM silver_fact_ventas)"
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
            FROM silver_fact_ventas
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
        max_month_sql = "(SELECT STRFTIME(MAX(business_date), '%Y-%m') FROM silver_fact_ventas)"
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
            FROM silver_fact_ventas
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
            FROM silver_fact_ventas
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
            FROM silver_fact_ventas_detalle d
            INNER JOIN silver_fact_ventas v ON d.num_documento = v.num_documento
            WHERE v.nit_vendedor = ? AND {where_v}
        """, [vendedor_id])
        prod_count = int(productos[0]["productos_vendidos"]) if productos and productos[0].get("productos_vendidos") else 0

        ant_val = 0.0
        if period == "month":
            anterior_rows = self._query("""
                SELECT COALESCE(ROUND(SUM(total_factura), 2), 0) AS anterior
                FROM silver_fact_ventas
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
            FROM gold_mart_cohortes_clientes
            GROUP BY mes_cohorte
            ORDER BY mes_cohorte
        """)
        retencion_rows = self._query("""
            SELECT STRFTIME(TRY_CAST(mes_cohorte AS DATE), '%Y-%m-01') AS cohorte_mes,
                   STRFTIME(TRY_CAST(business_month AS DATE), '%Y-%m-01') AS mes_observacion,
                   COUNT(DISTINCT nit_cliente) AS num_clientes,
                   ROUND(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS tasa_recurrencia
            FROM gold_mart_cohortes_clientes
            GROUP BY mes_cohorte, business_month
            ORDER BY mes_cohorte, business_month
        """)
        nuevos_rows = self._query("""
            WITH ultimo_mes AS (
                SELECT MAX(business_month) AS mm FROM gold_mart_cohortes_clientes
            )
            SELECT
                COALESCE(SUM(CASE WHEN mes_cohorte = business_month THEN 1 ELSE 0 END), 0) AS nuevos,
                COALESCE(SUM(CASE WHEN mes_cohorte < business_month AND compro_este_mes THEN 1 ELSE 0 END), 0) AS recurrentes,
                COALESCE(SUM(CASE WHEN compro_este_mes THEN 1 ELSE 0 END), 0) AS top_recurrentes
            FROM gold_mart_cohortes_clientes, ultimo_mes
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
                FROM gold_alertas_drift
                ORDER BY week_end DESC
                LIMIT 50
            """)
            threshold_row = self._query("""
                SELECT COALESCE(MAX(threshold_pct), 30.0) AS current_threshold
                FROM gold_alertas_drift
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
        # V1.9.3 (2026-06-16): usar INVENTARIO_REAL_CTE en vez de snapshot.
        # Con el snapshot quedaban excluidos los SKUs que tenian stock real
        # pero estaban en 0 en gold_mart_inventario_actual, lo que falsificaba
        # el plan de compras al "sugerir" comprar cosas que ya estaban en stock.
        rows = self._query(f"""
            WITH inventario AS ({INVENTARIO_REAL_CTE}),
            demanda_7d AS (
                SELECT cod_producto, SUM(cantidad) AS qty_7d
                FROM silver_fact_ventas_detalle
                WHERE business_date >= CURRENT_DATE - INTERVAL '7' DAY
                GROUP BY cod_producto
            ),
            abc_latest AS (
                SELECT cod_producto, categoria_abc
                FROM (
                    SELECT cod_producto, categoria_abc,
                           ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_month DESC) AS rn
                    FROM gold_mart_rotacion_abc
                ) WHERE rn = 1
            ),
            alertas_latest AS (
                SELECT sku, urgencia
                FROM (
                    SELECT sku, urgencia,
                           ROW_NUMBER() OVER (PARTITION BY sku ORDER BY urgencia) AS rn
                    FROM gold_alertas_quiebre
                ) WHERE rn = 1
            ),
            suppliers AS (
                SELECT d.cod_producto, MAX(c.nombre_proveedor) AS supplier
                FROM silver_fact_compras_detalle d
                INNER JOIN silver_fact_compras c
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
            FROM inventario inv
            LEFT JOIN demanda_7d d ON inv.cod_producto = d.cod_producto
            LEFT JOIN abc_latest abc ON inv.cod_producto = abc.cod_producto
            LEFT JOIN alertas_latest al ON inv.cod_producto = al.sku
            LEFT JOIN gold_mart_productos_dormidos dorm
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
            FROM gold_forecast_categoria
            WHERE business_date >= CURRENT_DATE - INTERVAL '30' DAY
            GROUP BY cod_grupo
            ORDER BY demanda_real DESC
        """)
        coverage_row = self._query("""
            SELECT ROUND(COUNT(DISTINCT cod_grupo) * 100.0
                   / NULLIF((SELECT COUNT(DISTINCT cod_grupo)
                             FROM gold_forecast_categoria), 0), 2) AS cobertura_pct
            FROM gold_forecast_categoria
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
            "SELECT MAX(business_date) FROM gold_mart_ventas_diarias_sku"
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
            FROM gold_mart_ventas_diarias_sku
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
            FROM gold_mart_ventas_diarias_sku
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
                    SELECT ROUND(COALESCE(SUM(valor_total),0),2) FROM gold_mart_ventas_diarias_sku
                    WHERE business_date >= ? AND business_date <= ?
                """, [y_start, y_end]).fetchone()
                y_full = self._con.execute("""
                    SELECT ROUND(COALESCE(SUM(valor_total),0),2) FROM gold_mart_ventas_diarias_sku
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
            FROM gold_mart_ventas_diarias_sku
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
            "SELECT MAX(business_date) FROM gold_mart_ventas_diarias_sku"
        ).fetchone()[0]
        max_date = max_d if max_d else date.today()
        current_month = max_date.strftime("%Y-%m")
        day_num = max_date.day

        # Current month: acumulado / días con venta → run-rate diario
        curr = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COUNT(DISTINCT business_date)
            FROM gold_mart_ventas_diarias_sku
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
            FROM gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
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
                FROM gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
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


    # ── Inventory Detail (V1.8) ───────────────────────────────────────

    def get_inventory_detail(
        self, page: int = 1, page_size: int = 50, sort: str = "cod_producto",
        q: str | None = None, bodega: str | None = None,
        stock: str = "todos", dormido: str = "todos", abc: str | None = None,
    ) -> dict:
        """Inventario detallado con costo, última venta, dormido status, filtros."""
        offset = (page - 1) * page_size
        sort_map = {
            "cod_producto": "inv.cod_producto", "nom_producto": "inv.nom_producto",
            "stock_actual": "inv.cantidad_actual",
            "costo_unitario": "COALESCE(lc.costo_producto,0)",
            "valor_inventario": "COALESCE(lc.costo_producto,0)*inv.cantidad_actual",
            "dias_sin_venta": "COALESCE(DATE_DIFF('day', v.ultima_venta, CURRENT_DATE), 99999)",
            "ultima_venta": "v.ultima_venta",
            "abc": "CASE COALESCE(abc.categoria_abc, 'C') WHEN 'A' THEN 3 WHEN 'B' THEN 2 ELSE 1 END",
            "es_dormido": "CASE WHEN d.cod_producto IS NOT NULL THEN 1 ELSE 0 END",
        }

        # Multi-columna sort: formato "-es_dormido,-dias_sin_venta,abc"
        # "-" prefix = DESC, "+" o sin prefix = ASC. Default = DESC (backward compat)
        sort_parts = [s.strip() for s in sort.split(",") if s.strip()]
        order_bys = []
        for part in sort_parts:
            desc = False  # default ASC (sin prefijo)
            if part.startswith("-"):
                desc = True
                part = part[1:]
            elif part.startswith("+"):
                desc = False
                part = part[1:]
            col = sort_map.get(part)
            if col:
                order_bys.append(f"{col} {'DESC' if desc else 'ASC'}")
        sort_clause = ", ".join(order_bys) if order_bys else "inv.cod_producto DESC"

        where = "1=1"
        where_params = []
        count_params = []

        if q:
            q_like = f"%{q}%"
            where += " AND (LOWER(inv.cod_producto) LIKE LOWER(?) OR LOWER(inv.nom_producto) LIKE LOWER(?) OR LOWER(inv.cod_bodega) LIKE LOWER(?) OR LOWER(inv.nom_bodega) LIKE LOWER(?))"
            where_params.extend([q_like, q_like, q_like, q_like])
            count_params.extend([q_like, q_like, q_like, q_like])
        if bodega:
            where += " AND inv.cod_bodega = ?"
            where_params.append(bodega)
            count_params.append(bodega)
        if stock == "con_stock":
            where += " AND inv.cantidad_actual > 0"
        elif stock == "sin_stock":
            where += " AND inv.cantidad_actual = 0"
        if dormido == "true":
            where += " AND d.cod_producto IS NOT NULL"
        elif dormido == "false":
            where += " AND d.cod_producto IS NULL"
        if abc:
            where += " AND abc.categoria_abc = ?"
            where_params.append(abc.upper())
            count_params.append(abc.upper())

        query_params = where_params + [page_size, offset]

        rows = self._con.execute(f"""
            WITH inventario AS (
                SELECT
                    dp.cod_producto,
                    COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
                    COALESCE(dp.cod_bodega_default, '') AS cod_bodega,
                    COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
                    ROUND(COALESCE(c.total_comprado, 0) - COALESCE(v.total_vendido, 0), 2) AS cantidad_actual
                FROM silver_dim_producto dp
                LEFT JOIN (
                    SELECT cod_producto, SUM(cantidad) AS total_comprado
                    FROM silver_fact_compras_detalle
                    WHERE business_date >= DATE '2020-01-01' AND business_date <= CURRENT_DATE
                    GROUP BY cod_producto
                ) c ON dp.cod_producto = c.cod_producto
                LEFT JOIN (
                    SELECT cod_producto, SUM(cantidad) AS total_vendido
                    FROM silver_fact_ventas_detalle
                    WHERE business_date >= DATE '2020-01-01' AND business_date <= CURRENT_DATE
                    GROUP BY cod_producto
                ) v ON dp.cod_producto = v.cod_producto
                LEFT JOIN silver_dim_bodega db ON dp.cod_bodega_default = db.cod_bodega
            ),
            latest_cost AS (
                SELECT cod_producto, costo_producto,
                       ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) AS rn
                FROM silver_fact_compras_detalle WHERE costo_producto > 0
            ),
            last_sale AS (
                SELECT cod_producto, MAX(business_date) AS ultima_venta
                FROM silver_fact_ventas_detalle GROUP BY cod_producto
            ),
            abc_latest AS (
                SELECT cod_producto, categoria_abc
                FROM (SELECT cod_producto, categoria_abc, ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_month DESC) AS rn
                      FROM gold_mart_rotacion_abc) WHERE rn = 1
            )
            SELECT inv.cod_producto, inv.nom_producto, inv.cod_bodega, inv.nom_bodega,
                   inv.cantidad_actual AS stock_actual,
                   ROUND(COALESCE(lc.costo_producto, 0), 2) AS costo_unitario,
                   ROUND(inv.cantidad_actual * COALESCE(lc.costo_producto, 0), 2) AS valor_inventario,
                   v.ultima_venta,
                   COALESCE(DATE_DIFF('day', v.ultima_venta, CURRENT_DATE), 99999) AS dias_sin_venta,
                   CASE WHEN d.cod_producto IS NOT NULL THEN TRUE ELSE FALSE END AS es_dormido,
                   COALESCE(abc.categoria_abc, 'C') AS abc
            FROM inventario inv
            LEFT JOIN latest_cost lc ON inv.cod_producto = lc.cod_producto AND lc.rn = 1
            LEFT JOIN last_sale v ON inv.cod_producto = v.cod_producto
            LEFT JOIN gold_mart_productos_dormidos d ON inv.cod_producto = d.cod_producto
            LEFT JOIN abc_latest abc ON inv.cod_producto = abc.cod_producto
            WHERE {where}
            ORDER BY {sort_clause}
            LIMIT ? OFFSET ?
        """, query_params).fetchall()

        cols = ["cod_producto", "nom_producto", "cod_bodega", "nom_bodega", "stock_actual",
                "costo_unitario", "valor_inventario", "ultima_venta", "dias_sin_venta", "es_dormido", "abc"]
        items = []
        for r in rows:
            item = dict(zip(cols, r))
            item["stock_actual"] = float(item["stock_actual"] or 0)
            item["costo_unitario"] = float(item["costo_unitario"] or 0)
            item["valor_inventario"] = float(item["valor_inventario"] or 0)
            item["dias_sin_venta"] = int(item["dias_sin_venta"] or 0)
            item["es_dormido"] = bool(item["es_dormido"])
            items.append(item)

        # Count real con todos los filtros (sin LIMIT/OFFSET)
        total = self._con.execute(f"""
            WITH inventario AS (
                SELECT
                    dp.cod_producto,
                    COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
                    COALESCE(dp.cod_bodega_default, '') AS cod_bodega,
                    COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
                    ROUND(COALESCE(c.total_comprado, 0) - COALESCE(v.total_vendido, 0), 2) AS cantidad_actual
                FROM silver_dim_producto dp
                LEFT JOIN (
                    SELECT cod_producto, SUM(cantidad) AS total_comprado
                    FROM silver_fact_compras_detalle
                    WHERE business_date >= DATE '2020-01-01' AND business_date <= CURRENT_DATE
                    GROUP BY cod_producto
                ) c ON dp.cod_producto = c.cod_producto
                LEFT JOIN (
                    SELECT cod_producto, SUM(cantidad) AS total_vendido
                    FROM silver_fact_ventas_detalle
                    WHERE business_date >= DATE '2020-01-01' AND business_date <= CURRENT_DATE
                    GROUP BY cod_producto
                ) v ON dp.cod_producto = v.cod_producto
                LEFT JOIN silver_dim_bodega db ON dp.cod_bodega_default = db.cod_bodega
            ),
            abc_latest AS (
                SELECT cod_producto, categoria_abc
                FROM (SELECT cod_producto, categoria_abc, ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_month DESC) AS rn
                      FROM gold_mart_rotacion_abc) WHERE rn = 1
            )
            SELECT COUNT(*) FROM inventario inv
            LEFT JOIN gold_mart_productos_dormidos d ON inv.cod_producto = d.cod_producto
            LEFT JOIN abc_latest abc ON inv.cod_producto = abc.cod_producto
            WHERE {where}
        """, count_params).fetchone()[0]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def get_inventory_discrepancies(self) -> dict:
        """SKUs con diferencias de stock entre inventario y dormidos."""
        diffs = self._con.execute("""
            SELECT d.cod_producto, d.nom_producto,
                   d.stock_actual AS stock_dormidos,
                   COALESCE(inv.cantidad_actual, 0) AS stock_inventario,
                   COALESCE(inv.cantidad_actual, 0) - d.stock_actual AS diff,
                   d.dias_sin_venta
            FROM gold_mart_productos_dormidos d
            LEFT JOIN gold_mart_inventario_actual inv ON d.cod_producto = inv.cod_producto
            WHERE d.stock_actual != COALESCE(inv.cantidad_actual, 0)
               OR inv.cod_producto IS NULL
            ORDER BY ABS(COALESCE(inv.cantidad_actual, 0) - d.stock_actual) DESC
        """).fetchall()

        cols = ["cod_producto", "nom_producto", "stock_dormidos", "stock_inventario", "diff", "dias_sin_venta"]
        items = [dict(zip(cols, r)) for r in diffs]

        # SQL invariants
        total_dormidos_stock = self._con.execute(
            "SELECT COALESCE(SUM(stock_actual),0) FROM gold_mart_productos_dormidos"
        ).fetchone()[0]
        total_inventory_stock = self._con.execute(
            "SELECT COALESCE(SUM(cantidad_actual),0) FROM gold_mart_inventario_actual"
        ).fetchone()[0]
        invariant_ok = total_dormidos_stock <= total_inventory_stock

        return {
            "discrepancies": items,
            "total_discrepancies": len(items),
            "summary": {
                "dormidos_total_stock": float(total_dormidos_stock),
                "inventario_total_stock": float(total_inventory_stock),
                "invariant_ok": invariant_ok,
                "invariant_msg": f"SUM(dormidos.stock)={total_dormidos_stock} <= SUM(inventory.stock)={total_inventory_stock} → {'OK' if invariant_ok else 'FAIL'}",
            },
        }

    # ── Sales Day Detail (V1.9 — popup detallado) ────────────────────────

    def get_sales_day_detail(self, date: str) -> dict:
        """Detalle completo de un dia para el popup del calendario.

        Hace 6 queries:
          1. KPIs principales (ventas, facturas, ticket, ticket maximo, items/factura)
          2. Margen bruto (ventas - costo)
          3. Distribucion horaria (extraida de fecha_documento_ts)
          4. Productos top
          5. Vendedores top
          6. Forma de pago breakdown
          7. Comparativas (semana, mes, ano)
        """
        # 1. KPIs - de silver para tener acceso a ticket maximo e items/factura
        kpis_rows = self._query(
            """
            SELECT
                ROUND(COALESCE(SUM(total_factura), 0), 2) AS total_ventas,
                COUNT(*) AS total_facturas,
                ROUND(COALESCE(MAX(total_factura), 0), 2) AS ticket_mas_alto
            FROM silver_fact_ventas
            WHERE business_date = ?
              AND estado_documento != 'A'
            """,
            [date],
        )
        k = kpis_rows[0] if kpis_rows else {"total_ventas": 0, "total_facturas": 0, "ticket_mas_alto": 0}
        total_ventas = float(k["total_ventas"] or 0)
        total_facturas = int(k["total_facturas"] or 0)
        ticket_promedio = round(total_ventas / total_facturas, 2) if total_facturas > 0 else 0.0

        # Items por factura (avg)
        items_rows = self._query(
            """
            SELECT ROUND(CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT num_documento), 0), 2) AS items_promedio
            FROM silver_fact_ventas_detalle
            WHERE business_date = ?
            """,
            [date],
        )
        items_por_factura = float(items_rows[0]["items_promedio"] or 0) if items_rows else 0.0

        # 2. Margen bruto. Costo = el de la venta, o el de la ultima compra
        # si la venta no lo trae (V1.10.3 — fallback de costo).
        margen_rows = self._query(
            f"""
            WITH costo_ref AS ({COSTO_REF_CTE})
            SELECT
                ROUND(COALESCE(SUM(d.total_detalle), 0), 2) AS revenue_detalle,
                ROUND(COALESCE(SUM(COALESCE(NULLIF(d.costo_producto, 0), cr.costo_producto, 0) * d.cantidad), 0), 2) AS costo_total
            FROM silver_fact_ventas_detalle d
            LEFT JOIN costo_ref cr ON d.cod_producto = cr.cod_producto
            WHERE d.business_date = ?
            """,
            [date],
        )
        m = margen_rows[0] if margen_rows else {"revenue_detalle": 0, "costo_total": 0}
        revenue_detalle = float(m["revenue_detalle"] or 0)
        costo_total = float(m["costo_total"] or 0)
        margen_bruto = round(revenue_detalle - costo_total, 2)
        margen_pct = round((margen_bruto / revenue_detalle) * 100, 2) if revenue_detalle > 0 else None

        # 3. Distribucion horaria
        horarios = self._query(
            """
            SELECT
                CAST(EXTRACT(hour FROM fecha_documento_ts) AS INTEGER) AS hour,
                ROUND(COALESCE(SUM(total_factura), 0), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE business_date = ?
              AND estado_documento != 'A'
              AND fecha_documento_ts IS NOT NULL
            GROUP BY hour
            ORDER BY hour
            """,
            [date],
        )
        distribucion_horaria = []
        hora_pico = None
        max_ventas_hora = 0.0
        for h in horarios:
            hr = int(h["hour"])
            tv = float(h["total_ventas"] or 0)
            nf = int(h["num_facturas"] or 0)
            tp = round(tv / nf, 2) if nf > 0 else 0.0
            distribucion_horaria.append({
                "hour": hr,
                "total_ventas": tv,
                "num_facturas": nf,
                "ticket_promedio": tp,
            })
            if tv > max_ventas_hora:
                max_ventas_hora = tv
                hora_pico = hr

        # 4. TODOS los productos vendidos del dia (sin LIMIT — el frontend
        # decide cuantos mostrar con colapsable). Ordenado de mas a menos
        # vendido por valor. V1.15: incluye unidad_medida (g/u/kg/etc).
        productos_top = self._query(
            """
            SELECT
                v.cod_producto AS sku,
                v.nom_producto AS nombre,
                ROUND(SUM(v.cantidad_total), 2) AS cantidad,
                ROUND(SUM(v.valor_total), 2) AS valor,
                ANY_VALUE(dp.presentacion) AS presentacion
            FROM gold_mart_ventas_diarias_sku v
            LEFT JOIN silver_dim_producto dp ON dp.cod_producto = v.cod_producto
            WHERE v.business_date = ?
            GROUP BY v.cod_producto, v.nom_producto
            ORDER BY valor DESC
            """,
            [date],
        )
        for r in productos_top:
            r["unidad_medida"] = _presentacion_to_unidad(r.get("presentacion"))

        # 5. Vendedores top del dia
        vendedores_rows = self._query(
            """
            SELECT
                COALESCE(NULLIF(TRIM(nombre_vendedor), ''), '(sin asignar)') AS nombre_vendedor,
                nit_vendedor,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE business_date = ?
              AND estado_documento != 'A'
            GROUP BY nombre_vendedor, nit_vendedor
            ORDER BY total_ventas DESC
            LIMIT 10
            """,
            [date],
        )
        vendedores_top = []
        for v in vendedores_rows:
            tv = float(v["total_ventas"] or 0)
            pct = round((tv / total_ventas) * 100, 2) if total_ventas > 0 else None
            vendedores_top.append({
                "nombre_vendedor": v["nombre_vendedor"],
                "nit_vendedor": v["nit_vendedor"],
                "total_ventas": tv,
                "num_facturas": int(v["num_facturas"] or 0),
                "porcentaje": pct,
            })

        # 6. Forma de pago breakdown
        formas_rows = self._query(
            """
            SELECT
                COALESCE(NULLIF(TRIM(cod_formapago), ''), 'SIN_COD') AS cod_formapago,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE business_date = ?
              AND estado_documento != 'A'
            GROUP BY cod_formapago
            ORDER BY total_ventas DESC
            """,
            [date],
        )
        formas_pago = []
        for f in formas_rows:
            tv = float(f["total_ventas"] or 0)
            pct = round((tv / total_ventas) * 100, 2) if total_ventas > 0 else 0.0
            formas_pago.append({
                "cod_formapago": f["cod_formapago"],
                "nombre": _formapago_label(f["cod_formapago"]),
                "total_ventas": tv,
                "num_facturas": int(f["num_facturas"] or 0),
                "porcentaje": pct,
            })

        # 7. Comparativas. days_back es int literal (no parametrizable en INTERVAL de DuckDB).
        comparativas = []
        for label, days_back in [("semana pasada", 7), ("mes pasado", 30), ("año pasado", 365)]:
            comp_rows = self._query(
                f"""
                SELECT
                    CAST(? AS DATE) - INTERVAL '{int(days_back)}' DAY AS fecha_comp,
                    ROUND(COALESCE(SUM(total_factura), 0), 2) AS tv
                FROM silver_fact_ventas
                WHERE business_date = CAST(? AS DATE) - INTERVAL '{int(days_back)}' DAY
                  AND estado_documento != 'A'
                """,
                [date, date],
            )
            if comp_rows and comp_rows[0].get("fecha_comp"):
                fecha_c = str(comp_rows[0]["fecha_comp"])[:10]
                tv_c = float(comp_rows[0]["tv"] or 0)
                delta = round(((total_ventas - tv_c) / tv_c) * 100, 2) if tv_c > 0 else None
                comparativas.append({
                    "label": label,
                    "fecha_comparada": fecha_c,
                    "total_ventas": tv_c,
                    "delta_porcentaje": delta,
                })

        return {
            "date": date,
            "total_ventas": total_ventas,
            "total_facturas": total_facturas,
            "ticket_promedio": ticket_promedio,
            "margen_bruto": margen_bruto,
            "margen_porcentaje": margen_pct,
            "items_por_factura": items_por_factura,
            "ticket_mas_alto": float(k["ticket_mas_alto"] or 0),
            "distribucion_horaria": distribucion_horaria,
            "hora_pico": hora_pico,
            "productos_top": productos_top,
            "vendedores_top": vendedores_top,
            "formas_pago": formas_pago,
            "comparativas": comparativas,
        }

    # ── Sales Month Detail (V1.9) ─────────────────────────────────────────

    def get_sales_month_detail(self, month: str) -> dict:
        """Detalle enriquecido del mes para complementar sales-summary."""
        # 1. Margen del mes (costo con fallback a ultima compra — V1.10.3)
        margen_rows = self._query(
            f"""
            WITH costo_ref AS ({COSTO_REF_CTE})
            SELECT
                ROUND(COALESCE(SUM(d.total_detalle), 0), 2) AS revenue,
                ROUND(COALESCE(SUM(COALESCE(NULLIF(d.costo_producto, 0), cr.costo_producto, 0) * d.cantidad), 0), 2) AS costo
            FROM silver_fact_ventas_detalle d
            LEFT JOIN costo_ref cr ON d.cod_producto = cr.cod_producto
            WHERE STRFTIME(d.business_date, '%Y-%m') = ?
            """,
            [month],
        )
        m = margen_rows[0] if margen_rows else {"revenue": 0, "costo": 0}
        revenue = float(m["revenue"] or 0)
        costo = float(m["costo"] or 0)
        margen_bruto = round(revenue - costo, 2)
        margen_pct = round((margen_bruto / revenue) * 100, 2) if revenue > 0 else None

        # 2. Total mes (para % vendedores y forma de pago)
        total_mes_rows = self._query(
            """
            SELECT ROUND(COALESCE(SUM(total_factura), 0), 2) AS total
            FROM silver_fact_ventas
            WHERE STRFTIME(business_date, '%Y-%m') = ?
              AND estado_documento != 'A'
            """,
            [month],
        )
        total_mes = float(total_mes_rows[0]["total"] or 0) if total_mes_rows else 0.0

        # 3. Vendedores top del mes
        vend_rows = self._query(
            """
            SELECT
                COALESCE(NULLIF(TRIM(nombre_vendedor), ''), '(sin asignar)') AS nombre_vendedor,
                nit_vendedor,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE STRFTIME(business_date, '%Y-%m') = ?
              AND estado_documento != 'A'
            GROUP BY nombre_vendedor, nit_vendedor
            ORDER BY total_ventas DESC
            LIMIT 10
            """,
            [month],
        )
        vendedores_top = []
        for v in vend_rows:
            tv = float(v["total_ventas"] or 0)
            pct = round((tv / total_mes) * 100, 2) if total_mes > 0 else None
            vendedores_top.append({
                "nombre_vendedor": v["nombre_vendedor"],
                "nit_vendedor": v["nit_vendedor"],
                "total_ventas": tv,
                "num_facturas": int(v["num_facturas"] or 0),
                "porcentaje": pct,
            })

        # 4. Formas de pago del mes
        formas_rows = self._query(
            """
            SELECT
                COALESCE(NULLIF(TRIM(cod_formapago), ''), 'SIN_COD') AS cod_formapago,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE STRFTIME(business_date, '%Y-%m') = ?
              AND estado_documento != 'A'
            GROUP BY cod_formapago
            ORDER BY total_ventas DESC
            """,
            [month],
        )
        formas_pago = []
        for f in formas_rows:
            tv = float(f["total_ventas"] or 0)
            pct = round((tv / total_mes) * 100, 2) if total_mes > 0 else 0.0
            formas_pago.append({
                "cod_formapago": f["cod_formapago"],
                "nombre": _formapago_label(f["cod_formapago"]),
                "total_ventas": tv,
                "num_facturas": int(f["num_facturas"] or 0),
                "porcentaje": pct,
            })

        # 5. Mejor y peor dia del mes
        dias_rows = self._query(
            """
            SELECT
                business_date,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE STRFTIME(business_date, '%Y-%m') = ?
              AND estado_documento != 'A'
            GROUP BY business_date
            ORDER BY total_ventas DESC
            """,
            [month],
        )
        mejor_dia = None
        peor_dia = None
        if dias_rows:
            mejor = dias_rows[0]
            mejor_dia = {
                "date": str(mejor["business_date"]),
                "total_ventas": float(mejor["total_ventas"] or 0),
                "num_facturas": int(mejor["num_facturas"] or 0),
            }
            peor = dias_rows[-1]
            peor_dia = {
                "date": str(peor["business_date"]),
                "total_ventas": float(peor["total_ventas"] or 0),
                "num_facturas": int(peor["num_facturas"] or 0),
            }

        # 6. Aceleradores / Frenadores (productos que mas crecieron / cayeron vs mes anterior)
        prev = _prev_month_str(month)
        delta_rows = self._query(
            """
            WITH curr AS (
                SELECT cod_producto, nom_producto, SUM(cantidad_total) AS cant_curr, SUM(valor_total) AS val_curr
                FROM gold_mart_ventas_diarias_sku
                WHERE STRFTIME(business_date, '%Y-%m') = ?
                GROUP BY cod_producto, nom_producto
            ),
            prev AS (
                SELECT cod_producto, SUM(valor_total) AS val_prev
                FROM gold_mart_ventas_diarias_sku
                WHERE STRFTIME(business_date, '%Y-%m') = ?
                GROUP BY cod_producto
            )
            SELECT
                c.cod_producto AS cod_producto,
                c.nom_producto AS nom_producto,
                ROUND(c.cant_curr, 2) AS cantidad_total,
                ROUND(c.val_curr, 2) AS valor_total,
                ROUND(COALESCE(c.val_curr - p.val_prev, c.val_curr), 2) AS delta
            FROM curr c
            LEFT JOIN prev p USING (cod_producto)
            WHERE c.val_curr > 50000
            """,
            [month, prev],
        )
        # Ordenar por delta absoluto (positivo = acelerador, negativo = frenador)
        sorted_delta = sorted(delta_rows, key=lambda r: float(r.get("delta") or 0), reverse=True)
        aceleradores = [
            {k: v for k, v in r.items() if k != "delta"} for r in sorted_delta[:3]
        ]
        frenadores = [
            {k: v for k, v in r.items() if k != "delta"} for r in sorted_delta[-3:][::-1]
            if float(r.get("delta") or 0) < 0
        ]

        return {
            "month": month,
            "margen_bruto": margen_bruto,
            "margen_porcentaje": margen_pct,
            "vendedores_top": vendedores_top,
            "formas_pago": formas_pago,
            "mejor_dia": mejor_dia,
            "peor_dia": peor_dia,
            "aceleradores": aceleradores,
            "frenadores": frenadores,
        }

    # ── Sales Day Invoices (V1.9.2 — facturas con items expandidos) ──────

    def get_sales_day_invoices(self, date: str) -> dict:
        """Lista todas las facturas del dia con su detalle de items.

        Una sola query con JOIN para evitar N+1. El frontend recibe la
        lista plana de items y la agrupa por num_documento+cod_clase.

        Retorna:
          - invoices: lista de facturas. Cada una tiene:
              * num_documento, cod_clase, prefijo, hora HH:MM, cliente,
                vendedor, cod_formapago + nombre_formapago, total,
                subtotal, total_iva, total_descuentos
              * items: lista [{cod_producto, nombre, cantidad,
                valor_unitario, descuento_valor, iva_valor,
                total_detalle, cod_bodega}]
        """
        # V1.10.4: query DRIVEN POR EL DETALLE (silver_fact_ventas_detalle),
        # con LEFT JOIN a la cabecera (silver_fact_ventas). Antes era un
        # INNER JOIN a la cabecera, pero la tabla de cabeceras a veces esta
        # incompleta para dias recientes (lag del pipeline). Con INNER JOIN
        # esas facturas desaparecian ("sin facturas en este dia" aunque
        # SI hubo ventas). Ahora el detalle manda y la cabecera aporta
        # metadata (cliente, vendedor, forma de pago, hora) cuando existe.
        rows = self._query(
            f"""
            WITH costo_ref AS ({COSTO_REF_CTE})
            SELECT
                d.num_documento,
                d.cod_clase,
                v.prefijo,
                v.fecha_documento_ts,
                COALESCE(NULLIF(TRIM(v.nombre_cliente), ''), 'Consumidor final') AS cliente,
                COALESCE(NULLIF(TRIM(v.nombre_vendedor), ''), '(sin asignar)') AS vendedor,
                COALESCE(NULLIF(TRIM(v.cod_formapago), ''), 'SIN_COD') AS cod_formapago,
                ROUND(v.subtotal, 2) AS subtotal,
                ROUND(v.total_descuentos, 2) AS total_descuentos,
                ROUND(v.total_iva, 2) AS total_iva,
                ROUND(v.total_factura, 2) AS total_header,
                d.num_item,
                d.cod_producto,
                d.nombre_detalle AS producto_nombre,
                d.cantidad,
                ROUND(d.valor_unitario, 2) AS valor_unitario,
                ROUND(d.descuento_valor, 2) AS descuento_valor,
                ROUND(d.iva_valor, 2) AS iva_valor,
                ROUND(d.total_detalle, 2) AS total_detalle,
                -- Costo efectivo: el de la venta si existe, si no el de la ultima compra
                ROUND(COALESCE(NULLIF(d.costo_producto, 0), cr.costo_producto, 0), 2) AS costo_unitario,
                ROUND(COALESCE(NULLIF(d.costo_producto, 0), cr.costo_producto, 0) * d.cantidad, 2) AS costo_total,
                d.cod_bodega
            FROM silver_fact_ventas_detalle d
            LEFT JOIN silver_fact_ventas v
              ON d.num_documento = v.num_documento
             AND d.cod_clase = v.cod_clase
            LEFT JOIN costo_ref cr ON d.cod_producto = cr.cod_producto
            WHERE d.business_date = ?
              AND (v.estado_documento IS NULL OR v.estado_documento != 'A')
            ORDER BY v.fecha_documento_ts NULLS LAST, d.num_documento, d.num_item
            """,
            [date],
        )

        # Agrupar por (num_documento, cod_clase) -> factura con items
        invoices_map: dict[tuple[str, str], dict] = {}
        for r in rows:
            key = (r["num_documento"], r["cod_clase"])
            if key not in invoices_map:
                ts = r["fecha_documento_ts"]
                hora_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else (str(ts)[11:16] if ts else "")
                invoices_map[key] = {
                    "num_documento": r["num_documento"],
                    "cod_clase": r["cod_clase"],
                    "prefijo": r["prefijo"],
                    "hora": hora_str,
                    "cliente": r["cliente"],
                    "vendedor": r["vendedor"],
                    "cod_formapago": r["cod_formapago"],
                    "nombre_formapago": _formapago_label(r["cod_formapago"]),
                    "subtotal": float(r["subtotal"] or 0),
                    "total_descuentos": float(r["total_descuentos"] or 0),
                    "total_iva": float(r["total_iva"] or 0),
                    # total del header si existe; si la cabecera falta (lag
                    # del pipeline) se completa abajo con la suma del detalle.
                    "total": float(r["total_header"] or 0),
                    "_total_header_presente": r["total_header"] is not None,
                    "items": [],
                }
            costo_total = float(r["costo_total"] or 0)
            venta_total = float(r["total_detalle"] or 0)
            invoices_map[key]["items"].append({
                "num_item": int(r["num_item"] or 0),
                "cod_producto": r["cod_producto"],
                "nombre": r["producto_nombre"],
                "cantidad": float(r["cantidad"] or 0),
                "valor_unitario": float(r["valor_unitario"] or 0),
                "descuento_valor": float(r["descuento_valor"] or 0),
                "iva_valor": float(r["iva_valor"] or 0),
                "total_detalle": venta_total,
                "costo_unitario": float(r["costo_unitario"] or 0),
                "costo_total": costo_total,
                # Ganancia bruta de la linea (venta - costo). Si no hay costo
                # registrado queda igual a la venta (no penaliza con ganancia falsa).
                "ganancia": round(venta_total - costo_total, 2) if costo_total > 0 else None,
                "margen_pct": round((venta_total - costo_total) / venta_total * 100, 1) if costo_total > 0 and venta_total > 0 else None,
                "cod_bodega": r["cod_bodega"],
            })

        invoices = list(invoices_map.values())

        # Totales de factura: costo, ganancia y total
        for inv in invoices:
            # Si la cabecera no traia total (o venia 0), usar la suma del
            # detalle como total de la factura. Asi nunca queda en $0 cuando
            # el header esta incompleto.
            suma_detalle = round(sum(it["total_detalle"] for it in inv["items"]), 2)
            if not inv.pop("_total_header_presente", True) or inv["total"] <= 0:
                inv["total"] = suma_detalle
            inv_costo = sum(it["costo_total"] for it in inv["items"] if it["costo_total"] > 0)
            inv["costo_total"] = round(inv_costo, 2)
            inv["ganancia"] = round(inv["total"] - inv_costo, 2) if inv_costo > 0 else None
            inv["margen_pct"] = round((inv["total"] - inv_costo) / inv["total"] * 100, 1) if inv_costo > 0 and inv["total"] > 0 else None

        # Resumen para mostrar arriba
        total_dia = sum(inv["total"] for inv in invoices)
        total_items = sum(len(inv["items"]) for inv in invoices)
        total_costo = sum(inv["costo_total"] for inv in invoices)

        return {
            "date": date,
            "total_facturas": len(invoices),
            "total_dia": round(total_dia, 2),
            "total_costo": round(total_costo, 2),
            "total_ganancia": round(total_dia - total_costo, 2) if total_costo > 0 else None,
            "total_items": total_items,
            "invoices": invoices,
        }

    # ── Cash Closure (V1.9.1 — cierre de caja del dia) ───────────────────

    def get_cash_closure(self, date: str) -> dict:
        """Cierre de caja del dia: desglose por forma de pago + lista de
        facturas + top facturas grandes. Tipo Z-report del POS.

        IMPORTANTE: cada factura registra UN solo codpag. Si el negocio
        usa pagos partidos (efectivo + tarjeta en una misma venta),
        sgHermes los registra como un solo codigo y el desglose va a
        tener un delta vs caja fisica.
        """
        # 1. Resumen por forma de pago
        formas_rows = self._query(
            """
            SELECT
                COALESCE(NULLIF(TRIM(cod_formapago), ''), 'SIN_COD') AS cod_formapago,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas,
                ROUND(AVG(total_factura), 2) AS ticket_promedio
            FROM silver_fact_ventas
            WHERE business_date = ?
              AND estado_documento != 'A'
            GROUP BY cod_formapago
            ORDER BY total_ventas DESC
            """,
            [date],
        )
        total_dia = sum(float(r["total_ventas"] or 0) for r in formas_rows)
        total_facturas_dia = sum(int(r["num_facturas"] or 0) for r in formas_rows)

        formas_pago = []
        for r in formas_rows:
            tv = float(r["total_ventas"] or 0)
            pct = round((tv / total_dia) * 100, 2) if total_dia > 0 else 0.0
            formas_pago.append({
                "cod_formapago": r["cod_formapago"],
                "nombre": _formapago_label(r["cod_formapago"]),
                "total_ventas": tv,
                "num_facturas": int(r["num_facturas"] or 0),
                "ticket_promedio": float(r["ticket_promedio"] or 0),
                "porcentaje": pct,
            })

        # 2. Lista completa de facturas del dia
        facturas_rows = self._query(
            """
            SELECT
                num_documento,
                prefijo,
                fecha_documento_ts,
                COALESCE(NULLIF(TRIM(nombre_cliente), ''), 'Consumidor final') AS cliente,
                COALESCE(NULLIF(TRIM(nombre_vendedor), ''), '(sin asignar)') AS vendedor,
                COALESCE(NULLIF(TRIM(cod_formapago), ''), 'SIN_COD') AS cod_formapago,
                ROUND(total_factura, 2) AS total
            FROM silver_fact_ventas
            WHERE business_date = ?
              AND estado_documento != 'A'
            ORDER BY fecha_documento_ts
            """,
            [date],
        )
        facturas = []
        for f in facturas_rows:
            ts = f["fecha_documento_ts"]
            hora_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else (str(ts)[11:16] if ts else "")
            facturas.append({
                "num_documento": f["num_documento"],
                "prefijo": f["prefijo"],
                "hora": hora_str,
                "cliente": f["cliente"],
                "vendedor": f["vendedor"],
                "cod_formapago": f["cod_formapago"],
                "nombre_formapago": _formapago_label(f["cod_formapago"]),
                "total": float(f["total"] or 0),
            })

        # 3. Top 5 facturas grandes del dia
        top_grandes = sorted(facturas, key=lambda x: x["total"], reverse=True)[:5]

        return {
            "date": date,
            "total_dia": round(total_dia, 2),
            "total_facturas": total_facturas_dia,
            "formas_pago": formas_pago,
            "facturas": facturas,
            "top_facturas_grandes": top_grandes,
        }

    # ── Payments History (V1.9.1 — tendencia historica formas de pago) ───

    def get_payments_history(self, months: int = 12) -> dict:
        """Tendencia mensual de cada forma de pago en los ultimos N meses.

        Devuelve:
          - series: [{ month, formas_pago: { cod: total } }]
          - mix_actual: % de cada forma este mes
          - mix_seis_meses_atras: % de cada forma hace 6 meses (para
            comparativa de variacion)
        """
        from datetime import datetime, timedelta
        # months es int seguro, lo embebemos inline (DuckDB no acepta param en INTERVAL)
        months_int = max(1, min(int(months), 36))

        # Serie temporal
        serie_rows = self._query(
            f"""
            SELECT
                STRFTIME(business_date, '%Y-%m') AS mes,
                COALESCE(NULLIF(TRIM(cod_formapago), ''), 'SIN_COD') AS cod_formapago,
                ROUND(SUM(total_factura), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE business_date >= (CURRENT_DATE - INTERVAL '{months_int}' MONTH)
              AND estado_documento != 'A'
            GROUP BY mes, cod_formapago
            ORDER BY mes, total_ventas DESC
            """,
            [],
        )

        # Pivot a {month: {cod_formapago: total}}
        meses_dict = {}
        formas_set = set()
        for r in serie_rows:
            mes = r["mes"]
            cod = r["cod_formapago"]
            formas_set.add(cod)
            if mes not in meses_dict:
                meses_dict[mes] = {"month": mes, "total": 0.0, "by_forma": {}}
            tv = float(r["total_ventas"] or 0)
            meses_dict[mes]["by_forma"][cod] = tv
            meses_dict[mes]["total"] += tv

        # Estructurar para frontend (stacked bar)
        series = []
        for mes_key in sorted(meses_dict.keys()):
            m = meses_dict[mes_key]
            entry = {
                "month": m["month"],
                "total": round(m["total"], 2),
                "formas_pago": [
                    {
                        "cod_formapago": cod,
                        "nombre": _formapago_label(cod),
                        "total_ventas": round(m["by_forma"].get(cod, 0.0), 2),
                    }
                    for cod in sorted(formas_set)
                ],
            }
            series.append(entry)

        # Mix actual vs hace 6 meses (para comparativa de variacion)
        def _mix_pct(month_entry):
            total = month_entry["total"] if month_entry["total"] else 1
            return {
                fp["cod_formapago"]: round((fp["total_ventas"] / total) * 100, 2)
                for fp in month_entry["formas_pago"]
            }

        mix_actual = {}
        mix_seis_meses_atras = {}
        if series:
            mix_actual = _mix_pct(series[-1])
            if len(series) >= 7:
                mix_seis_meses_atras = _mix_pct(series[-7])

        variacion = []
        for cod in sorted(formas_set):
            curr = mix_actual.get(cod, 0.0)
            past = mix_seis_meses_atras.get(cod, 0.0)
            variacion.append({
                "cod_formapago": cod,
                "nombre": _formapago_label(cod),
                "pct_actual": curr,
                "pct_seis_meses_atras": past,
                "delta_puntos": round(curr - past, 2),
            })

        return {
            "months": months_int,
            "formas_pago": sorted(
                [{"cod_formapago": c, "nombre": _formapago_label(c)} for c in formas_set],
                key=lambda x: x["nombre"],
            ),
            "series": series,
            "variacion_seis_meses": variacion,
        }

    def close(self) -> None:
        """Cierra la conexión DuckDB. Para cleanup explícito."""
        try:
            self._con.close()
        except Exception:
            pass

    # ── Purchases Day Detail (V2.0) ────────────────────────────────────

    def get_purchases_day_detail(self, date: str) -> dict:
        """Retorna todas las compras de un día específico."""
        rows = self._query("""
            SELECT
                cd.num_documento,
                cd.cod_producto,
                COALESCE(dp.nombre_producto, cd.nombre_detalle, 'SIN NOMBRE') AS nom_producto,
                ROUND(cd.cantidad, 2) AS cantidad,
                ROUND(cd.valor_unitario, 2) AS valor_unitario,
                ROUND(cd.costo_producto, 2) AS costo_producto,
                ROUND(cd.total_detalle, 2) AS total
            FROM silver_fact_compras_detalle cd
            LEFT JOIN silver_dim_producto dp ON cd.cod_producto = dp.cod_producto
            WHERE cd.business_date = ?
            ORDER BY cd.num_documento, cd.cod_producto
        """, [date])

        total_compras = round(sum(float(r["total"] or 0) for r in rows), 2)
        docs = set(r["num_documento"] for r in rows)

        return {
            "date": date,
            "total_compras": total_compras,
            "total_documentos": len(docs),
            "items": rows,
        }

    # ══════════════════════════════════════════════════════════════════════
    # ANALÍTICA DE PRODUCTOS / INVENTARIO (V1.10)
    # ══════════════════════════════════════════════════════════════════════
    #
    # Motor de métricas por producto. Cruza inventario real (compras-ventas)
    # con la contribución a las ventas (Pareto/ABC dinámico) y la velocidad
    # de rotación. Responde: "¿qué productos importan más y cómo se mueven?"
    #
    # Tres consumidores:
    #   get_inventory_overview  → KPIs + Pareto + listas de decisión
    #   get_product_analytics   → tabla rica paginada y filtrable
    #   get_product_detail      → ficha completa de un SKU + timeline

    @staticmethod
    def _product_metrics_cte(window_days: int) -> str:
        """Devuelve las CTEs (sin el WITH inicial) que terminan en `metrics`.

        El caller escribe:  f"WITH {cte} SELECT ... FROM metrics WHERE ..."

        `metrics` tiene una fila por SKU con TODAS las métricas calculadas:
        stock real, costo, precio, valor inventario, revenue/unidades en la
        ventana, velocidad mensual, días de stock, rotación anual, días sin
        venta/compra, proveedor, % del revenue (Pareto), ranking, ABC
        dinámico, margen, estado y acción sugerida.
        """
        wmonths = round(window_days / 30.0, 4)
        return f"""
            compras_tot AS (
                SELECT cod_producto, SUM(cantidad) AS comprado_total
                FROM silver_fact_compras_detalle WHERE business_date <= CURRENT_DATE
                GROUP BY cod_producto
            ),
            ventas_tot AS (
                SELECT cod_producto, SUM(cantidad) AS vendido_total
                FROM silver_fact_ventas_detalle WHERE business_date <= CURRENT_DATE
                GROUP BY cod_producto
            ),
            ventas_win AS (
                -- margen con costo fallback a ultima compra (V1.10.3)
                SELECT d.cod_producto AS cod_producto,
                       SUM(d.total_detalle) AS revenue_win,
                       SUM(d.cantidad) AS unidades_win,
                       SUM(d.total_detalle - COALESCE(NULLIF(d.costo_producto, 0), cref.costo_producto, 0) * d.cantidad) AS margen_win
                FROM silver_fact_ventas_detalle d
                LEFT JOIN ({COSTO_REF_CTE}) cref ON d.cod_producto = cref.cod_producto
                WHERE d.business_date >= CURRENT_DATE - INTERVAL '{int(window_days)}' DAY
                  AND d.business_date <= CURRENT_DATE
                GROUP BY d.cod_producto
            ),
            ultima_venta AS (
                SELECT cod_producto, MAX(business_date) AS uv
                FROM silver_fact_ventas_detalle GROUP BY cod_producto
            ),
            ultima_compra AS (
                SELECT cod_producto, MAX(business_date) AS uc
                FROM silver_fact_compras_detalle GROUP BY cod_producto
            ),
            costo AS (
                SELECT cod_producto, costo_producto FROM (
                    SELECT cod_producto, costo_producto,
                           ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) rn
                    FROM silver_fact_compras_detalle WHERE costo_producto > 0
                ) WHERE rn = 1
            ),
            proveedor AS (
                SELECT cod_producto, supplier FROM (
                    SELECT d.cod_producto, c.nombre_proveedor AS supplier,
                           ROW_NUMBER() OVER (PARTITION BY d.cod_producto ORDER BY d.business_date DESC) rn
                    FROM silver_fact_compras_detalle d
                    INNER JOIN silver_fact_compras c
                        ON d.num_documento = c.num_documento AND d.cod_clase = c.cod_clase
                    WHERE c.nombre_proveedor IS NOT NULL AND TRIM(c.nombre_proveedor) != ''
                ) WHERE rn = 1
            ),
            base AS (
                SELECT
                    dp.cod_producto,
                    COALESCE(NULLIF(TRIM(dp.nombre_producto), ''), dp.cod_producto) AS nombre,
                    ROUND(COALESCE(ct.comprado_total, 0) - COALESCE(vt.vendido_total, 0), 2) AS cantidad_actual,
                    COALESCE(c.costo_producto, 0) AS costo_unit,
                    COALESCE(dp.precio_venta_con_iva, 0) AS precio,
                    COALESCE(vw.revenue_win, 0) AS revenue_win,
                    COALESCE(vw.unidades_win, 0) AS unidades_win,
                    COALESCE(vw.margen_win, 0) AS margen_win,
                    uv.uv AS ultima_venta,
                    uc.uc AS ultima_compra,
                    pr.supplier AS proveedor,
                    CASE WHEN ct.comprado_total IS NULL AND vt.vendido_total > 0 THEN TRUE ELSE FALSE END AS es_servicio
                FROM silver_dim_producto dp
                LEFT JOIN compras_tot ct USING(cod_producto)
                LEFT JOIN ventas_tot vt USING(cod_producto)
                LEFT JOIN ventas_win vw USING(cod_producto)
                LEFT JOIN ultima_venta uv USING(cod_producto)
                LEFT JOIN ultima_compra uc USING(cod_producto)
                LEFT JOIN costo c USING(cod_producto)
                LEFT JOIN proveedor pr USING(cod_producto)
            ),
            pareto AS (
                SELECT cod_producto, revenue_win,
                       SUM(revenue_win) OVER (ORDER BY revenue_win DESC, cod_producto) AS acum,
                       SUM(revenue_win) OVER () AS total_rev,
                       ROW_NUMBER() OVER (ORDER BY revenue_win DESC, cod_producto) AS rank_rev
                FROM base WHERE revenue_win > 0
            ),
            metrics AS (
                SELECT
                    b.cod_producto,
                    b.nombre,
                    b.cantidad_actual,
                    b.costo_unit,
                    b.precio,
                    ROUND(GREATEST(b.cantidad_actual, 0) * b.costo_unit, 2) AS valor_inventario,
                    ROUND(b.revenue_win, 2) AS revenue_win,
                    b.unidades_win,
                    ROUND(b.margen_win, 2) AS margen_win,
                    CASE WHEN b.revenue_win > 0 THEN ROUND(b.margen_win / b.revenue_win * 100, 1) ELSE NULL END AS margen_pct,
                    ROUND(b.unidades_win / {wmonths}, 2) AS velocidad_mensual,
                    CASE WHEN b.unidades_win > 0 AND b.cantidad_actual > 0
                         THEN ROUND(b.cantidad_actual / (b.unidades_win / {int(window_days)}.0), 0)
                         ELSE NULL END AS dias_stock,
                    CASE WHEN b.cantidad_actual > 0 AND b.unidades_win > 0
                         THEN ROUND((b.unidades_win / {wmonths} * 12) / b.cantidad_actual, 2)
                         ELSE NULL END AS rotacion_anual,
                    b.ultima_venta,
                    CASE WHEN b.ultima_venta IS NOT NULL THEN DATE_DIFF('day', b.ultima_venta, CURRENT_DATE) ELSE NULL END AS dias_sin_venta,
                    b.ultima_compra,
                    CASE WHEN b.ultima_compra IS NOT NULL THEN DATE_DIFF('day', b.ultima_compra, CURRENT_DATE) ELSE NULL END AS dias_sin_compra,
                    b.proveedor,
                    b.es_servicio,
                    COALESCE(ROUND(b.revenue_win / NULLIF(p.total_rev, 0) * 100, 3), 0) AS pct_revenue,
                    p.rank_rev,
                    CASE
                        WHEN p.acum IS NULL THEN 'sin_venta'
                        WHEN p.acum <= 0.80 * p.total_rev THEN 'A'
                        WHEN p.acum <= 0.95 * p.total_rev THEN 'B'
                        ELSE 'C'
                    END AS abc,
                    CASE
                        WHEN b.es_servicio THEN 'servicio'
                        WHEN b.cantidad_actual <= 0 AND b.unidades_win > 0 THEN 'agotado'
                        WHEN b.cantidad_actual <= 0 THEN 'sin_stock'
                        WHEN b.unidades_win > 0 AND b.cantidad_actual / (b.unidades_win / {int(window_days)}.0) < 15 THEN 'quiebre'
                        WHEN b.cantidad_actual > 0 AND (b.ultima_venta IS NULL OR DATE_DIFF('day', b.ultima_venta, CURRENT_DATE) > 90) THEN 'dormido'
                        WHEN b.unidades_win > 0 AND b.cantidad_actual / (b.unidades_win / {int(window_days)}.0) > 180 THEN 'sobrestock'
                        WHEN b.unidades_win > 0 THEN 'saludable'
                        ELSE 'sin_movimiento'
                    END AS estado
                FROM base b
                LEFT JOIN pareto p USING(cod_producto)
            )
        """

    @staticmethod
    def _accion_for(estado: str, abc: str) -> str:
        """Acción sugerida derivada del estado + importancia ABC."""
        if estado == "servicio":
            return "n/a"
        if estado in ("agotado", "quiebre"):
            return "reabastecer"
        if estado in ("sobrestock", "dormido"):
            return "liquidar"
        if estado in ("sin_stock", "sin_movimiento"):
            return "revisar"
        return "ok"

    def get_inventory_overview(self, window_days: int = 180) -> dict:
        """Resumen ejecutivo del inventario: KPIs reales, curva de Pareto y
        las 4 listas de decisión (quiebre, capital atrapado, importantes sin
        recompra, dormidos premium)."""
        cte = self._product_metrics_cte(window_days)

        # KPIs globales
        kpis = self._query(f"""
            WITH {cte}
            SELECT
                ROUND(SUM(valor_inventario), 2) AS valor_inventario_total,
                SUM(CASE WHEN cantidad_actual > 0 THEN 1 ELSE 0 END) AS skus_con_stock,
                SUM(CASE WHEN unidades_win > 0 THEN 1 ELSE 0 END) AS skus_activos,
                ROUND(AVG(rotacion_anual) FILTER (WHERE rotacion_anual IS NOT NULL), 2) AS rotacion_promedio,
                ROUND(SUM(revenue_win), 2) AS revenue_total_win,
                ROUND(SUM(margen_win), 2) AS margen_total_win
            FROM metrics
        """)[0]

        # Concentración Pareto: cuántos SKUs hacen el 80% del revenue
        pareto = self._query(f"""
            WITH {cte},
            activos AS (
                SELECT cod_producto, revenue_win, rank_rev,
                       SUM(revenue_win) OVER (ORDER BY rank_rev) AS acum,
                       SUM(revenue_win) OVER () AS total
                FROM metrics WHERE revenue_win > 0
            )
            SELECT
                COUNT(*) AS skus_activos,
                MIN(CASE WHEN acum >= 0.80 * total THEN rank_rev END) AS skus_para_80,
                MIN(CASE WHEN acum >= 0.50 * total THEN rank_rev END) AS skus_para_50
            FROM activos
        """)[0]

        # Curva de Pareto para graficar (deciles del ranking)
        curva = self._query(f"""
            WITH {cte},
            activos AS (
                SELECT revenue_win, rank_rev,
                       SUM(revenue_win) OVER (ORDER BY rank_rev) AS acum,
                       SUM(revenue_win) OVER () AS total,
                       COUNT(*) OVER () AS n
                FROM metrics WHERE revenue_win > 0
            )
            SELECT
                ROUND(rank_rev * 100.0 / n, 1) AS pct_productos,
                ROUND(acum * 100.0 / NULLIF(total, 0), 1) AS pct_revenue_acum
            FROM activos
            WHERE rank_rev % GREATEST(CAST(n / 40 AS INTEGER), 1) = 0 OR rank_rev = n
            ORDER BY rank_rev
        """)

        # Las 4 listas de decisión (resumen: count + monto, top 8 cada una)
        def _add_accion(rows):
            for r in rows:
                r["accion"] = self._accion_for(r.get("estado", ""), r.get("abc", "C"))
            return rows

        quiebre = _add_accion(self._query(f"""
            WITH {cte}
            SELECT cod_producto, nombre, cantidad_actual, dias_stock, velocidad_mensual,
                   pct_revenue, abc, estado, valor_inventario, revenue_win
            FROM metrics
            WHERE estado IN ('agotado', 'quiebre') AND NOT es_servicio
            ORDER BY pct_revenue DESC, dias_stock ASC NULLS FIRST
            LIMIT 50
        """))

        capital = _add_accion(self._query(f"""
            WITH {cte}
            SELECT cod_producto, nombre, cantidad_actual, dias_stock, valor_inventario,
                   dias_sin_venta, abc, estado, pct_revenue, velocidad_mensual
            FROM metrics
            WHERE estado = 'sobrestock'
            ORDER BY valor_inventario DESC
            LIMIT 50
        """))

        importantes = _add_accion(self._query(f"""
            WITH {cte}
            SELECT cod_producto, nombre, cantidad_actual, dias_stock, dias_sin_compra,
                   pct_revenue, abc, estado, valor_inventario, velocidad_mensual, proveedor
            FROM metrics
            WHERE abc IN ('A', 'B') AND unidades_win > 0 AND NOT es_servicio
              AND (dias_sin_compra IS NULL OR dias_sin_compra > 45)
            ORDER BY pct_revenue DESC
            LIMIT 50
        """))

        dormidos = _add_accion(self._query(f"""
            WITH {cte}
            SELECT cod_producto, nombre, cantidad_actual, valor_inventario,
                   dias_sin_venta, abc, estado, ultima_venta
            FROM metrics
            WHERE estado = 'dormido' AND valor_inventario > 0
            ORDER BY valor_inventario DESC
            LIMIT 50
        """))

        # Distribución por estado (para un donut)
        estados = self._query(f"""
            WITH {cte}
            SELECT estado, COUNT(*) AS n, ROUND(SUM(valor_inventario), 2) AS valor
            FROM metrics GROUP BY estado ORDER BY n DESC
        """)

        return {
            "window_days": window_days,
            "kpis": {
                "valor_inventario_total": float(kpis["valor_inventario_total"] or 0),
                "skus_con_stock": int(kpis["skus_con_stock"] or 0),
                "skus_activos": int(kpis["skus_activos"] or 0),
                "rotacion_promedio": float(kpis["rotacion_promedio"] or 0),
                "revenue_total_win": float(kpis["revenue_total_win"] or 0),
                "margen_total_win": float(kpis["margen_total_win"] or 0),
            },
            "pareto": {
                "skus_activos": int(pareto["skus_activos"] or 0),
                "skus_para_80": int(pareto["skus_para_80"] or 0),
                "skus_para_50": int(pareto["skus_para_50"] or 0),
                "pct_para_80": round((pareto["skus_para_80"] or 0) / (pareto["skus_activos"] or 1) * 100, 1),
                "curva": curva,
            },
            "estados": estados,
            "listas": {
                "quiebre_inminente": {
                    "total": len(quiebre),
                    "items": quiebre[:8],
                    "valor": round(sum(float(r["valor_inventario"] or 0) for r in quiebre), 2),
                },
                "capital_atrapado": {
                    "total": len(capital),
                    "items": capital[:8],
                    "valor": round(sum(float(r["valor_inventario"] or 0) for r in capital), 2),
                },
                "importantes_sin_recompra": {
                    "total": len(importantes),
                    "items": importantes[:8],
                    "valor": round(sum(float(r["valor_inventario"] or 0) for r in importantes), 2),
                },
                "dormidos_premium": {
                    "total": len(dormidos),
                    "items": dormidos[:8],
                    "valor": round(sum(float(r["valor_inventario"] or 0) for r in dormidos), 2),
                },
            },
        }

    def get_product_analytics(
        self,
        window_days: int = 180,
        page: int = 1,
        page_size: int = 50,
        q: str | None = None,
        abc: str | None = None,
        estado: str | None = None,
        sort: str = "revenue_win",
        order: str = "desc",
    ) -> dict:
        """Tabla rica de productos con filtros, búsqueda, orden y paginación."""
        cte = self._product_metrics_cte(window_days)

        where = ["1=1"]
        params: list = []
        if q:
            where.append("(LOWER(nombre) LIKE ? OR LOWER(cod_producto) LIKE ?)")
            like = f"%{q.lower()}%"
            params += [like, like]
        if abc in ("A", "B", "C"):
            where.append("abc = ?")
            params.append(abc)
        if estado:
            where.append("estado = ?")
            params.append(estado)
        where_sql = " AND ".join(where)

        sort_cols = {
            "revenue_win", "unidades_win", "cantidad_actual", "valor_inventario",
            "velocidad_mensual", "dias_stock", "rotacion_anual", "dias_sin_venta",
            "pct_revenue", "margen_pct", "margen_win",
        }
        sort_col = sort if sort in sort_cols else "revenue_win"
        order_dir = "ASC" if order == "asc" else "DESC"
        nulls = "NULLS LAST"

        offset = (page - 1) * page_size
        rows = self._query(f"""
            WITH {cte}
            SELECT cod_producto, nombre, cantidad_actual, costo_unit, precio,
                   valor_inventario, revenue_win, unidades_win, margen_win, margen_pct,
                   velocidad_mensual, dias_stock, rotacion_anual,
                   ultima_venta, dias_sin_venta, ultima_compra, dias_sin_compra,
                   proveedor, pct_revenue, rank_rev, abc, estado, es_servicio
            FROM metrics
            WHERE {where_sql}
            ORDER BY {sort_col} {order_dir} {nulls}, cod_producto
            LIMIT ? OFFSET ?
        """, params + [page_size, offset])

        for r in rows:
            r["accion"] = self._accion_for(r.get("estado", ""), r.get("abc", "C"))

        total = self._query(f"""
            WITH {cte}
            SELECT COUNT(*) AS n FROM metrics WHERE {where_sql}
        """, params)[0]["n"]

        return {
            "window_days": window_days,
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
            "items": rows,
        }

    def get_product_abc_map(self, window_days: int = 180) -> dict:
        """Mapa liviano {sku → abc/estado/pct_revenue} de TODOS los productos
        con venta en la ventana. El frontend lo busca una vez y decora
        cualquier lista de productos (mensual, diaria, facturas) sin que esos
        endpoints tengan que recalcular ABC."""
        cte = self._product_metrics_cte(window_days)
        rows = self._query(f"""
            WITH {cte}
            SELECT cod_producto, abc, estado, pct_revenue, rank_rev
            FROM metrics
            WHERE revenue_win > 0
        """)
        return {
            "window_days": window_days,
            "productos": {
                r["cod_producto"]: {
                    "abc": r["abc"],
                    "estado": r["estado"],
                    "pct_revenue": float(r["pct_revenue"] or 0),
                    "rank": int(r["rank_rev"]) if r["rank_rev"] is not None else None,
                }
                for r in rows
            },
        }

    def get_sales_history_extended(self) -> dict:
        """Histórico enriquecido: serie mensual con revenue + margen + facturas,
        mejor/peor mes, comparativa año vs año (mismo mes), y mezcla por
        categoría ABC del último mes cerrado."""
        # Serie mensual completa con margen
        serie = self._query("""
            SELECT
                STRFTIME(v.business_date, '%Y-%m') AS mes,
                ROUND(SUM(v.total_detalle), 2) AS revenue,
                ROUND(SUM(v.total_detalle - v.costo_producto * v.cantidad), 2) AS margen,
                COUNT(DISTINCT v.num_documento) AS facturas,
                ROUND(SUM(v.cantidad), 0) AS unidades
            FROM silver_fact_ventas_detalle v
            GROUP BY 1 ORDER BY 1
        """)
        for s in serie:
            rev = float(s["revenue"] or 0)
            s["revenue"] = rev
            s["margen"] = float(s["margen"] or 0)
            s["margen_pct"] = round(s["margen"] / rev * 100, 1) if rev > 0 else None
            s["facturas"] = int(s["facturas"] or 0)
            s["unidades"] = float(s["unidades"] or 0)
            s["ticket_promedio"] = round(rev / s["facturas"], 2) if s["facturas"] > 0 else 0

        # Mejor / peor mes (excluyendo el mes en curso si está incompleto)
        completos = serie[:-1] if len(serie) > 1 else serie
        mejor = max(completos, key=lambda x: x["revenue"], default=None) if completos else None
        peor = min(completos, key=lambda x: x["revenue"], default=None) if completos else None

        # Comparativa año vs año (mismo mes calendario)
        by_mes = {s["mes"]: s for s in serie}
        yoy = []
        for s in serie:
            y, m = s["mes"].split("-")
            prev_key = f"{int(y)-1}-{m}"
            if prev_key in by_mes:
                prev_rev = by_mes[prev_key]["revenue"]
                delta = round((s["revenue"] - prev_rev) / prev_rev * 100, 1) if prev_rev > 0 else None
                yoy.append({
                    "mes": s["mes"],
                    "revenue_actual": s["revenue"],
                    "revenue_anterior": prev_rev,
                    "delta_pct": delta,
                })

        return {
            "serie": serie,
            "mejor_mes": mejor,
            "peor_mes": peor,
            "yoy": yoy,
            "total_revenue": round(sum(s["revenue"] for s in serie), 2),
            "total_margen": round(sum(s["margen"] for s in serie), 2),
        }

    def get_product_detail(self, sku: str, window_days: int = 180) -> dict:
        """Ficha completa de un producto: métricas + timeline mensual de
        compras vs ventas + últimos movimientos."""
        cte = self._product_metrics_cte(window_days)

        metric_rows = self._query(f"""
            WITH {cte}
            SELECT * FROM metrics WHERE cod_producto = ?
        """, [sku])
        if not metric_rows:
            return {"found": False, "sku": sku}
        m = metric_rows[0]
        m["accion"] = self._accion_for(m.get("estado", ""), m.get("abc", "C"))

        # Timeline mensual: compras vs ventas (últimos 18 meses)
        timeline = self._query("""
            WITH meses AS (
                SELECT DISTINCT STRFTIME(business_date, '%Y-%m') AS mes
                FROM (
                    SELECT business_date FROM silver_fact_ventas_detalle WHERE cod_producto = ?
                    UNION ALL
                    SELECT business_date FROM silver_fact_compras_detalle WHERE cod_producto = ?
                )
                WHERE business_date >= CURRENT_DATE - INTERVAL '18' MONTH
            ),
            ventas AS (
                SELECT STRFTIME(business_date, '%Y-%m') AS mes,
                       SUM(cantidad) AS unidades, ROUND(SUM(total_detalle), 2) AS valor
                FROM silver_fact_ventas_detalle WHERE cod_producto = ?
                GROUP BY 1
            ),
            compras AS (
                SELECT STRFTIME(business_date, '%Y-%m') AS mes,
                       SUM(cantidad) AS unidades, ROUND(SUM(total_detalle), 2) AS valor
                FROM silver_fact_compras_detalle WHERE cod_producto = ?
                GROUP BY 1
            )
            SELECT m.mes,
                   COALESCE(v.unidades, 0) AS unidades_vendidas,
                   COALESCE(v.valor, 0) AS valor_vendido,
                   COALESCE(c.unidades, 0) AS unidades_compradas,
                   COALESCE(c.valor, 0) AS valor_comprado
            FROM meses m
            LEFT JOIN ventas v USING(mes)
            LEFT JOIN compras c USING(mes)
            ORDER BY m.mes
        """, [sku, sku, sku, sku])

        # Últimos 20 movimientos (ventas + compras intercalados)
        movimientos = self._query("""
            SELECT business_date AS fecha, 'venta' AS tipo, cantidad,
                   ROUND(total_detalle, 2) AS valor, num_documento
            FROM silver_fact_ventas_detalle WHERE cod_producto = ?
            UNION ALL
            SELECT business_date AS fecha, 'compra' AS tipo, cantidad,
                   ROUND(total_detalle, 2) AS valor, num_documento
            FROM silver_fact_compras_detalle WHERE cod_producto = ?
            ORDER BY fecha DESC
            LIMIT 20
        """, [sku, sku])

        return {
            "found": True,
            "window_days": window_days,
            "metrics": m,
            "timeline": timeline,
            "movimientos": movimientos,
        }

    # ── Horas pico (V1.11) ────────────────────────────────────────────────
    #
    # Ventas y facturas agregadas por hora del día (0-23) en un rango.
    # Sirve para el dashboard de Análisis: ver cuándo concentra el negocio
    # su movimiento. Promedia por día con datos para suavizar.

    def get_hours_peak(self, fecha_inicio: str, fecha_fin: str) -> dict:
        """Agregado por hora del día en el rango [fecha_inicio, fecha_fin].

        Retorna ventas, facturas y ticket promedio por hora.
        Identifica la hora pico (mayor cantidad de facturas y mayor venta).
        """
        rows = self._query(
            """
            SELECT
                CAST(EXTRACT(hour FROM fecha_documento_ts) AS INTEGER) AS hour,
                ROUND(COALESCE(SUM(total_factura), 0), 2) AS total_ventas,
                COUNT(*) AS num_facturas
            FROM silver_fact_ventas
            WHERE business_date BETWEEN ? AND ?
              AND estado_documento != 'A'
              AND fecha_documento_ts IS NOT NULL
            GROUP BY hour
            ORDER BY hour
            """,
            [fecha_inicio, fecha_fin],
        )

        by_hour = {int(r["hour"]): r for r in rows}
        items = []
        max_facturas = 0
        hora_pico_facturas = None
        max_ventas = 0.0
        hora_pico_ventas = None
        for h in range(24):
            r = by_hour.get(h)
            tv = float(r["total_ventas"]) if r else 0.0
            nf = int(r["num_facturas"]) if r else 0
            tp = round(tv / nf, 2) if nf > 0 else 0.0
            items.append({
                "hour": h,
                "total_ventas": tv,
                "num_facturas": nf,
                "ticket_promedio": tp,
            })
            if nf > max_facturas:
                max_facturas = nf
                hora_pico_facturas = h
            if tv > max_ventas:
                max_ventas = tv
                hora_pico_ventas = h

        return {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "items": items,
            "hora_pico_facturas": hora_pico_facturas,
            "hora_pico_ventas": hora_pico_ventas,
        }

    # ── Balance financiero (V1.11) ────────────────────────────────────────
    #
    # Día a día: ventas, costo de la mercancía vendida (no de la mercancía
    # comprada — eso ya es inventario), gastos operativos (Supabase), ganancia
    # bruta y neta, balance acumulado. Filosofía: vender es bueno solo si
    # ganás dinero, y ganar dinero requiere descontar lo que pagás cada mes.

    def get_analisis_balance(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        gastos_diarios: dict[str, float] | None = None,
    ) -> dict:
        """Balance financiero día a día.

        gastos_diarios: dict {date_str: monto} desde Supabase. Los gastos
        mensuales se prorratean por día calendario del mes en la capa de
        servicio antes de pasarlos a este método.

        V1.14: el query ahora produce serie continua de días con generate_series,
        no solo días con ventas. Filosofía financiera: el arriendo, nómina,
        servicios se pagan TODOS los días, hay ventas o no. Si el local cierra
        un domingo, el gasto operativo prorrateado ese día sigue contando como
        pérdida. Antes los días sin ventas se omitían y la ganancia neta
        aparecía artificialmente inflada.

        El rango efectivo se corta a MAX(business_date) de ventas para no
        mostrar días futuros vacíos (si el user pide hasta fin de mes pero
        hoy es día 24, solo mostramos hasta 24).
        """
        gastos_diarios = gastos_diarios or {}

        # Cortar fecha_fin a la última fecha con datos en ventas para no mostrar
        # días futuros completamente vacíos en el gráfico.
        max_date_rows = self._query(
            "SELECT MAX(business_date) AS m FROM silver_fact_ventas WHERE estado_documento != 'A'"
        )
        max_data_date = str(max_date_rows[0]["m"]) if max_date_rows and max_date_rows[0]["m"] else fecha_fin
        effective_fin = min(fecha_fin, max_data_date)

        rows = self._query(
            f"""
            WITH costo_ref AS ({COSTO_REF_CTE}),
            dias AS (
                SELECT UNNEST(generate_series(?::DATE, ?::DATE, INTERVAL '1 day'))::DATE AS date
            ),
            ventas_dia AS (
                SELECT business_date AS date,
                       ROUND(COALESCE(SUM(total_factura), 0), 2) AS ventas
                FROM silver_fact_ventas
                WHERE business_date BETWEEN ? AND ?
                  AND estado_documento != 'A'
                GROUP BY business_date
            ),
            costo_dia AS (
                SELECT d.business_date AS date,
                       ROUND(COALESCE(SUM(
                           COALESCE(NULLIF(d.costo_producto, 0), cr.costo_producto, 0) * d.cantidad
                       ), 0), 2) AS costo
                FROM silver_fact_ventas_detalle d
                LEFT JOIN costo_ref cr ON d.cod_producto = cr.cod_producto
                WHERE d.business_date BETWEEN ? AND ?
                GROUP BY d.business_date
            )
            SELECT d.date,
                   COALESCE(v.ventas, 0) AS ventas,
                   COALESCE(c.costo, 0)  AS costo_mercancia
            FROM dias d
            LEFT JOIN ventas_dia v ON v.date = d.date
            LEFT JOIN costo_dia c ON c.date = d.date
            ORDER BY d.date
            """,
            [fecha_inicio, effective_fin, fecha_inicio, effective_fin, fecha_inicio, effective_fin],
        )

        items = []
        acumulado = 0.0
        total_ventas = 0.0
        total_costo = 0.0
        total_gastos = 0.0
        for r in rows:
            date_str = str(r["date"])
            ventas = float(r["ventas"] or 0)
            costo = float(r["costo_mercancia"] or 0)
            gastos = float(gastos_diarios.get(date_str, 0.0))
            ganancia_bruta = round(ventas - costo, 2)
            ganancia_neta = round(ganancia_bruta - gastos, 2)
            acumulado = round(acumulado + ganancia_neta, 2)
            items.append({
                "date": date_str,
                "ventas": round(ventas, 2),
                "costo_mercancia": round(costo, 2),
                "gastos_operativos": round(gastos, 2),
                "ganancia_bruta": ganancia_bruta,
                "ganancia_neta": ganancia_neta,
                "balance_acumulado": acumulado,
            })
            total_ventas += ventas
            total_costo += costo
            total_gastos += gastos

        total_ganancia_bruta = round(total_ventas - total_costo, 2)
        total_ganancia_neta = round(total_ganancia_bruta - total_gastos, 2)
        margen_bruto_pct = round(total_ganancia_bruta / total_ventas * 100, 2) if total_ventas > 0 else None
        margen_neto_pct = round(total_ganancia_neta / total_ventas * 100, 2) if total_ventas > 0 else None

        return {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "items": items,
            "total_ventas": round(total_ventas, 2),
            "total_costo_mercancia": round(total_costo, 2),
            "total_gastos_operativos": round(total_gastos, 2),
            "total_ganancia_bruta": total_ganancia_bruta,
            "total_ganancia_neta": total_ganancia_neta,
            "margen_bruto_pct": margen_bruto_pct,
            "margen_neto_pct": margen_neto_pct,
        }

    # ── Inventario inteligente (V1.17 — refactor /dashboards/inventario) ──
    #
    # Endpoint único que clasifica TODOS los SKUs en buckets de acción según
    # combinación stock × rotación. Reemplaza la lógica fragmentada que
    # estaba esparcida en /productos, /abc, /plan-compras, /dormidos.
    #
    # Filosofía: una sola fuente de verdad para la pregunta "¿qué hago con
    # cada producto del catálogo?". El front presenta esto en 4 tabs
    # (Resumen, Comprar, Optimizar, Catálogo) pero la lógica vive acá.

    def get_inventario_overview(
        self,
        lead_time_dias: int = 7,
        colchon_dias: int = 14,
        umbral_sobrestock_dias: int = 180,
    ) -> dict:
        """Devuelve TODOS los SKUs con su clasificación + métricas.

        Clasificación (un SKU cae en el primer bucket que matchea):
          1. COMPRAR_YA: stock<=0 AND vendió en últimos 90d (perder ventas)
          2. COMPRAR_PRONTO: stock>0 AND cobertura<lead_time (a quebrar pronto)
          3. SOBRESTOCK: stock>0 AND cobertura>umbral (capital innecesario)
          4. LIQUIDAR: stock>0 AND vendió alguna vez pero NO en últ 90d
          5. ZOMBIE_CON_STOCK: stock>0 AND nunca vendió histórico (zombie acción)
          6. OK: stock>0 AND cobertura entre lead_time y umbral (sano)
          7. SIN_ACCION: stock<=0 sin venta reciente (descatalogable)

        Cantidad sugerida a comprar (cuando aplica):
          sugerido = ceil(rotacion_diaria * (lead_time + colchon)) - stock_actual
        """
        from math import ceil

        rows = self._query(f"""
            WITH v90 AS (
                SELECT cod_producto,
                       SUM(cantidad_total) AS uds_90d,
                       SUM(valor_total) AS rev_90d
                FROM gold_mart_ventas_diarias_sku
                WHERE business_date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY cod_producto
            ),
            v180 AS (
                SELECT cod_producto, SUM(cantidad_total) AS uds_180d
                FROM gold_mart_ventas_diarias_sku
                WHERE business_date >= CURRENT_DATE - INTERVAL '180 days'
                GROUP BY cod_producto
            ),
            v_global AS (
                SELECT cod_producto, MAX(business_date) AS ultima_venta_global
                FROM gold_mart_ventas_diarias_sku
                GROUP BY cod_producto
            ),
            uc AS (
                SELECT cod_producto, MAX(business_date) AS ultima_compra
                FROM silver_fact_compras_detalle
                GROUP BY cod_producto
            ),
            abc AS (
                SELECT cod_producto, abc
                FROM gold_mart_abc_xyz
                WHERE business_month = (SELECT MAX(business_month) FROM gold_mart_abc_xyz)
            )
            SELECT
                dp.cod_producto,
                dp.nombre_producto,
                dp.presentacion,
                COALESCE(dp.existencia, 0) AS stock,
                COALESCE(v90.uds_90d, 0) AS uds_90d,
                COALESCE(v90.rev_90d, 0) AS rev_90d,
                COALESCE(v180.uds_180d, 0) AS uds_180d,
                CAST(v_global.ultima_venta_global AS VARCHAR) AS ultima_venta,
                CAST(uc.ultima_compra AS VARCHAR) AS ultima_compra,
                COALESCE(NULLIF(dp.costo_producto, 0), dp.costo_ultima_compra, 0) AS costo_unit,
                COALESCE(dp.precio_venta_con_iva, dp.precio_venta_sin_iva, 0) AS precio_venta,
                abc.abc
            FROM silver_dim_producto dp
            LEFT JOIN v90 ON dp.cod_producto = v90.cod_producto
            LEFT JOIN v180 ON dp.cod_producto = v180.cod_producto
            LEFT JOIN v_global ON dp.cod_producto = v_global.cod_producto
            LEFT JOIN uc ON dp.cod_producto = uc.cod_producto
            LEFT JOIN abc ON dp.cod_producto = abc.cod_producto
        """)

        # Clasificar en Python (más simple que CASEs anidados en SQL)
        items = []
        for r in rows:
            stock = float(r["stock"] or 0)
            uds_90d = float(r["uds_90d"] or 0)
            uds_180d = float(r["uds_180d"] or 0)
            rev_90d = float(r["rev_90d"] or 0)
            costo = float(r["costo_unit"] or 0)
            precio = float(r["precio_venta"] or 0)
            ultima_venta = r["ultima_venta"]

            # Rotación diaria (uds/día) basada en 90 días
            rotacion_diaria = uds_90d / 90.0
            # Cobertura: cuántos días dura el stock al ritmo actual
            cobertura_dias = (stock / rotacion_diaria) if rotacion_diaria > 0 else None

            # Días desde última venta (histórico real)
            dias_desde_venta = None
            if ultima_venta and ultima_venta != "1970-01-01":
                from datetime import date
                try:
                    uv = date.fromisoformat(str(ultima_venta))
                    dias_desde_venta = (date.today() - uv).days
                except (ValueError, TypeError):
                    pass
            nunca_vendio = ultima_venta is None or ultima_venta == "1970-01-01"

            # Sugerencia de compra
            objetivo_dias = lead_time_dias + colchon_dias
            sugerido = 0
            if rotacion_diaria > 0:
                sugerido = max(0, int(ceil(rotacion_diaria * objetivo_dias - stock)))

            # Clasificación (orden importa: primer match gana)
            if stock <= 0 and uds_90d > 0:
                accion = "comprar_ya"
            elif stock > 0 and cobertura_dias is not None and cobertura_dias < lead_time_dias:
                accion = "comprar_pronto"
            elif stock > 0 and cobertura_dias is not None and cobertura_dias > umbral_sobrestock_dias:
                accion = "sobrestock"
            elif stock > 0 and uds_90d == 0 and not nunca_vendio:
                accion = "liquidar"
            elif stock > 0 and nunca_vendio:
                accion = "zombie_con_stock"
            elif stock > 0 and rotacion_diaria > 0:
                accion = "ok"
            else:
                accion = "sin_accion"  # stock=0 sin venta reciente

            capital = stock * costo
            ingreso_perdido_estimado = 0.0
            if accion == "comprar_ya":
                # Aprox: 30 días sin stock × rotación × precio
                ingreso_perdido_estimado = round(rotacion_diaria * 30 * precio, 0)

            items.append({
                "cod_producto": r["cod_producto"],
                "nom_producto": r["nombre_producto"] or "",
                "stock": stock,
                "uds_90d": uds_90d,
                "rev_90d": rev_90d,
                "rotacion_diaria": round(rotacion_diaria, 3),
                "cobertura_dias": int(cobertura_dias) if cobertura_dias is not None else None,
                "ultima_venta": str(ultima_venta) if ultima_venta and ultima_venta != "1970-01-01" else None,
                "ultima_compra": str(r["ultima_compra"]) if r["ultima_compra"] else None,
                "dias_desde_venta": dias_desde_venta,
                "costo_unit": round(costo, 2),
                "precio_venta": round(precio, 2),
                "capital_inmovilizado": round(capital, 0),
                "sugerido_comprar": sugerido,
                "abc": r["abc"],
                "presentacion": r["presentacion"],
                "unidad_medida": _presentacion_to_unidad(r["presentacion"]),
                "accion": accion,
                "ingreso_perdido_estimado": ingreso_perdido_estimado,
            })

        # Resumen agregado para el tab "Resumen"
        from collections import Counter
        cnt = Counter(it["accion"] for it in items)
        valor_total_inv = sum(it["capital_inmovilizado"] for it in items)
        capital_ocioso = sum(
            it["capital_inmovilizado"] for it in items
            if it["accion"] in ("liquidar", "zombie_con_stock", "sobrestock")
        )
        ingreso_perdido_total = sum(it["ingreso_perdido_estimado"] for it in items)

        return {
            "total_skus": len(items),
            "lead_time_dias": lead_time_dias,
            "colchon_dias": colchon_dias,
            "umbral_sobrestock_dias": umbral_sobrestock_dias,
            "valor_total_inventario": round(valor_total_inv, 0),
            "capital_ocioso": round(capital_ocioso, 0),
            "ingreso_perdido_estimado_mensual": round(ingreso_perdido_total, 0),
            "buckets_count": {
                "comprar_ya": cnt.get("comprar_ya", 0),
                "comprar_pronto": cnt.get("comprar_pronto", 0),
                "sobrestock": cnt.get("sobrestock", 0),
                "liquidar": cnt.get("liquidar", 0),
                "zombie_con_stock": cnt.get("zombie_con_stock", 0),
                "ok": cnt.get("ok", 0),
                "sin_accion": cnt.get("sin_accion", 0),
            },
            "items": items,
        }


_FORMAPAGO_LABELS = {
    "F01": "Contado/Efectivo",
    "F02": "Tarjeta crédito",
    "F03": "Tarjeta débito",
    "F04": "Transferencia",
    "F05": "Crédito a 30 días",
    "F06": "Crédito a 60 días",
    "F07": "Crédito a 90 días",
    "F08": "Cheque",
    "F09": "Nequi/Daviplata",
    "F10": "Bono/Voucher",
    "SIN_COD": "Sin clasificar",
}


def _formapago_label(cod: str) -> str:
    """Mapea codigo de forma de pago a etiqueta legible. Cae al codigo si desconocido."""
    return _FORMAPAGO_LABELS.get(cod, cod or "Sin clasificar")


# ── Helper compartido: costo de referencia (V1.10.3) ──────────────────────
#
# Costo de la ULTIMA compra de cada producto. Se usa como fallback del
# costo cuando la linea de venta trae costo_producto = 0 (la POS a veces
# no lo llena, sobre todo en ventas frescas del dia). Filosofia: "si lo
# compraste, sabes cuanto te costo".
#
# Uso: LEFT JOIN costo_ref cr ON x.cod_producto = cr.cod_producto
#      ... COALESCE(NULLIF(x.costo_producto, 0), cr.costo_producto, 0)
# V1.15: Map de presentaciones del POS Hermes a label corto para UI.
# Algunos productos en MasVital se venden por gramo (granel — chía, almendras,
# maní, etc). El mart de ventas no traía esta info y el frontend mostraba
# todo como "u", confundiendo al usuario que veía "1310 u" de maní en vez
# de "1310 g".
_PRESENTACION_LABELS = {
    "UNIDAD": "u",
    "UND": "u",
    "U": "u",
    "GRAMO": "g",
    "GRAMOS": "g",
    "G": "g",
    "KILO": "kg",
    "KILOS": "kg",
    "KG": "kg",
    "LITRO": "L",
    "LITROS": "L",
    "ML": "ml",
    "CAJA": "ca",
    "PAQUETE": "paq",
    "DOCENA": "doc",
}


def _presentacion_to_unidad(presentacion: str | None) -> str:
    """Convierte la presentación textual del POS a label corto para UI.
    Default 'u' si la presentación es null o no está mapeada."""
    if not presentacion:
        return "u"
    key = presentacion.strip().upper()
    if key in _PRESENTACION_LABELS:
        return _PRESENTACION_LABELS[key]
    # Fallback: primeras letras lowercase
    return key[:3].lower() if key else "u"


COSTO_REF_CTE = """
    SELECT cod_producto, costo_producto FROM (
        SELECT cod_producto, costo_producto,
               ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) rn
        FROM silver_fact_compras_detalle WHERE costo_producto > 0
    ) WHERE rn = 1
"""


# ── Helper compartido: Inventario REAL (V1.9.3 — fix consistencia) ────────
#
# CTE reutilizable que reemplaza a `gold_mart_inventario_actual` (snapshot
# estatico del pipeline). Calcula la cantidad actual real de cada SKU
# dinamicamente como SUM(compras) - SUM(ventas).
#
# Por que: el snapshot quedaba desactualizado entre corridas del pipeline
# y mostraba numeros que no cuadraban con la realidad (17x menos stock,
# 1400 SKUs faltantes en MotoShop). El fix `6ecbd04` del Dev Back resolvio
# esto en `get_inventory_detail`. Esta constante propaga el mismo fix al
# resto de endpoints (summary, plan-compras, recommendations, etc.) y
# unifica la fuente de verdad del inventario.
#
# Columnas: cod_producto, nom_producto, cod_bodega, nom_bodega, cantidad_actual
# (los mismos campos que tenia gold_mart_inventario_actual, drop-in
# replacement con `FROM (` + CTE + `) inv`).
INVENTARIO_REAL_CTE = """
    SELECT
        dp.cod_producto,
        COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
        COALESCE(dp.cod_bodega_default, '') AS cod_bodega,
        COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
        ROUND(COALESCE(c.total_comprado, 0) - COALESCE(v.total_vendido, 0), 2) AS cantidad_actual
    FROM silver_dim_producto dp
    LEFT JOIN (
        SELECT cod_producto, SUM(cantidad) AS total_comprado
        FROM silver_fact_compras_detalle
        WHERE business_date <= CURRENT_DATE
        GROUP BY cod_producto
    ) c ON dp.cod_producto = c.cod_producto
    LEFT JOIN (
        SELECT cod_producto, SUM(cantidad) AS total_vendido
        FROM silver_fact_ventas_detalle
        WHERE business_date <= CURRENT_DATE
        GROUP BY cod_producto
    ) v ON dp.cod_producto = v.cod_producto
    LEFT JOIN silver_dim_bodega db ON dp.cod_bodega_default = db.cod_bodega
"""


def _prev_month_str(month: str) -> str:
    """Retorna el mes anterior en formato YYYY-MM."""
    d = datetime.strptime(month, "%Y-%m")
    if d.month == 1:
        d = d.replace(year=d.year - 1, month=12)
    else:
        d = d.replace(month=d.month - 1)
    return d.strftime("%Y-%m")


def get_duckdb_repo(tenant: str = "motoshop") -> DuckDBMetricsRepo:
    """Factory para crear DuckDBMetricsRepo con ruta configurable."""
    return DuckDBMetricsRepo(tenant=tenant)
