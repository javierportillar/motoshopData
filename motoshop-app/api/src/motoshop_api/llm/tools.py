"""Tools registry — tools tipadas para Q&A chat sobre DuckDB.

Cada tool toma args Pydantic, ejecuta query DuckDB, devuelve dict JSON.
TOOL_DEFINITIONS exporta specs OpenAI-compatible para function calling.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher

from motoshop_api.metrics.repo_duckdb import get_shared_connection

logger = logging.getLogger(__name__)


def _json_safe(value):
    """Convert DuckDB date values nested in tool results to JSON-safe values."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


_PRODUCT_SEARCH_STOPWORDS = {
    "a", "al", "con", "cual", "cómo", "como", "de", "del", "detalle",
    "dame", "el", "en", "esta", "está", "información", "la", "los",
    "me", "para", "por", "producto", "qué", "que", "sobre", "un", "una",
}


def _search_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii").lower()
    return [
        token for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in _PRODUCT_SEARCH_STOPWORDS
    ]


def _product_match_score(query: str, searchable_text: str) -> float:
    """Score partial, reordered and lightly misspelled product-name matches."""
    query_tokens = _search_tokens(query)
    candidate_tokens = _search_tokens(searchable_text)
    if not query_tokens or not candidate_tokens:
        return 0.0

    scores = []
    for query_token in query_tokens:
        token_scores = []
        for candidate_token in candidate_tokens:
            if query_token == candidate_token:
                token_scores.append(1.0)
            elif len(query_token) >= 4 and (
                query_token in candidate_token or candidate_token in query_token
            ):
                token_scores.append(0.9)
            elif len(query_token) >= 4 and len(candidate_token) >= 4:
                token_scores.append(SequenceMatcher(None, query_token, candidate_token).ratio())
        scores.append(max(token_scores, default=0.0))

    if any(score < 0.72 for score in scores):
        return 0.0
    return sum(scores) / len(scores)


PUBLIC_TOOL_NAMES = {
    "get_kpis_today",
    "get_kpis_month",
    "get_top_skus",
    "get_dormidos",
    "get_alerts_by_urgency",
    "get_vendedor_performance",
    "get_inventory_value",
    "compare_periods",
    "get_abc_distribution",
    "get_forecast_summary",
    "get_data_freshness",
    "search_business_knowledge",
    "get_ultima_compra",
    "get_compras_recientes",
    "search_products",
    "get_productos_comportamiento",
    "get_top_clientes",
    "get_inventario_por_bodega",
    "get_abc_xyz_distribution",
    "get_cohortes_clientes",
    "get_drift_alerts",
    "buscar_compras_por_proveedor",
    "get_producto_detalle",
    "get_detalle_compra",
    "generate_report",
}


# ── Tool execution ─────────────────────────────────────────────────────────


class ToolExecutor:
    """Ejecuta tools contra DuckDB."""

    def __init__(
        self,
        duckdb_path: str | None = None,
        tenant: str = "motoshop",
        user_id: str = "agent",
        tenant_context=None,
    ):
        from motoshop_api.metrics.repo_duckdb import _make_db_path

        # Nunca heredar DUCKDB_PATH global: en producción rompería el aislamiento.
        path = duckdb_path or str(_make_db_path(tenant))
        self.tenant = tenant
        self.user_id = user_id
        self.duckdb_path = path
        self._con = get_shared_connection(path)
        self._assistant_enabled = True
        from motoshop_api.tenants import get_tenant_config

        config = get_tenant_config(tenant)
        configured = (
            set(config.agent.enabled_tools)
            if config and config.agent.enabled_tools
            else PUBLIC_TOOL_NAMES
        )
        self._allowed_tools = PUBLIC_TOOL_NAMES & configured
        if tenant_context is not None:
            self._assistant_enabled = tenant_context.assistant_enabled
            self.set_capability_context(tenant_context.allowed_domains)

    def set_capability_context(self, allowed_domains: set[str] | frozenset[str]) -> None:
        from motoshop_api.auth.module_access import assistant_tool_allowed

        self._allowed_tools = {
            name for name in self._allowed_tools if assistant_tool_allowed(name, allowed_domains)
        }

    def _get_max_date(self) -> date | None:
        """Devuelve la fecha máxima con datos, o None si el DuckDB está vacío."""
        try:
            r = self._con.execute(
                "SELECT MAX(business_date) FROM gold_mart_ventas_diarias_sku"
            ).fetchone()
            return r[0] if r and r[0] else None
        except Exception:
            return None

    # ── Tool implementations ──────────────────────────────────────────────

    def get_kpis_today(self) -> dict:
        """KPIs del último día con datos: ventas, facturas, ticket promedio."""
        d = self._get_max_date()
        if d is None:
            return {"mensaje": "No hay datos de ventas disponibles.", "fecha": None, "ventas": 0, "facturas": 0, "ticket_promedio": 0}
        r = self._con.execute(
            """
            SELECT ROUND(COALESCE(SUM(valor_total),0),2) AS ventas,
                   COALESCE(SUM(num_facturas),0) AS facturas,
                   ROUND(COALESCE(SUM(valor_total),0)/NULLIF(COALESCE(SUM(num_facturas),0),0),2) AS ticket
            FROM gold_mart_ventas_diarias_sku WHERE business_date = ?
        """,
            [d.isoformat()],
        ).fetchone()
        return {
            "fecha": d.isoformat(),
            "ventas": float(r[0] or 0),
            "facturas": int(r[1] or 0),
            "ticket_promedio": float(r[2] or 0),
        }

    def get_kpis_month(self, month: str | None = None) -> dict:
        """KPIs mensuales: ventas totales, facturas, ticket promedio."""
        if not month:
            d = self._get_max_date()
            month = d.strftime("%Y-%m") if d else date.today().strftime("%Y-%m")
        r = self._con.execute(
            """
            SELECT ROUND(COALESCE(SUM(valor_total),0),2) AS ventas,
                   COALESCE(SUM(num_facturas),0) AS facturas,
                   ROUND(COALESCE(SUM(valor_total),0)/NULLIF(COALESCE(SUM(num_facturas),0),0),2) AS ticket
            FROM gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
        """,
            [month],
        ).fetchone()
        return {
            "month": month,
            "ventas": float(r[0] or 0),
            "facturas": int(r[1] or 0),
            "ticket_promedio": float(r[2] or 0),
        }

    def get_top_skus(self, period: str = "day", limit: int = 10) -> dict:
        """Top SKUs vendidos en el período (day, week, month, all)."""
        d = self._get_max_date()
        if d is None:
            return {"period": period, "skus": []}
        since = d.isoformat()
        if period == "week":
            since = (d - timedelta(days=7)).isoformat()
        elif period == "month":
            since = (d - timedelta(days=30)).isoformat()
        elif period == "all":
            since = "1900-01-01"

        limit = max(1, min(int(limit), 50))
        rows = self._con.execute(
            """
            SELECT cod_producto, nom_producto, ROUND(SUM(valor_total),2) AS valor, ROUND(SUM(cantidad_total),2) AS cantidad
            FROM gold_mart_ventas_diarias_sku
            WHERE business_date >= ?
            GROUP BY cod_producto, nom_producto ORDER BY valor DESC LIMIT ?
        """,
            [since, limit],
        ).fetchall()
        return {
            "period": period,
            "skus": [
                {"sku": r[0], "nombre": r[1], "valor": float(r[2]), "cantidad": float(r[3])}
                for r in rows
            ],
        }

    def get_dormidos(self, days_min: int = 90, limit: int = 20) -> dict:
        """Productos sin venta hace al menos days_min días. Excluye never-sold (sentinel >5000)."""
        days_min = max(0, min(int(days_min), 3650))
        limit = max(1, min(int(limit), 100))
        rows = self._con.execute(
            """
            SELECT cod_producto, nom_producto, stock_actual, dias_sin_venta
            FROM gold_mart_productos_dormidos
            WHERE dias_sin_venta >= ? AND dias_sin_venta < 5000
            ORDER BY dias_sin_venta DESC LIMIT ?
        """,
            [days_min, limit],
        ).fetchall()
        return {
            "dormidos": [
                {
                    "sku": r[0],
                    "nombre": r[1],
                    "stock": float(r[2]),
                    "dias_sin_venta": int(r[3] if r[3] else 99999),
                }
                for r in rows
            ],
            "total": len(rows),
        }

    def get_alerts_by_urgency(self, urgency: str | None = None) -> dict:
        """Alertas de quiebre de stock, filtrables por urgencia."""
        where = "WHERE urgencia = ?" if urgency else ""
        params = [urgency] if urgency else []
        rows = self._con.execute(
            f"""
            SELECT sku, nom_producto, stock_actual, demanda_predicha, dias_hasta_quiebre, urgencia
            FROM gold_alertas_quiebre {where}
            ORDER BY dias_hasta_quiebre ASC LIMIT 20
        """,
            params,
        ).fetchall()
        return {
            "alerts": [
                {
                    "sku": r[0],
                    "nombre": r[1],
                    "stock": float(r[2]),
                    "demanda": float(r[3]),
                    "dias": int(r[4]),
                    "urgencia": r[5],
                }
                for r in rows
            ],
            "total": len(rows),
        }

    def get_vendedor_performance(
        self, vendedor_id: str | None = None, period: str = "month"
    ) -> dict:
        """Performance de vendedores. Si no se especifica ID, top 5.

        period: 'day' (último día), 'week' (7 días), 'month' (mes actual), 'all' (histórico).
        """
        d = self._get_max_date()
        if d is None:
            return {"period": period, "vendedores": []}
        period = str(period or "month").lower().strip()

        if period == "day":
            since = d.isoformat()
        elif period == "week":
            since = (d - timedelta(days=7)).isoformat()
        elif period == "all":
            since = "1900-01-01"
        else:  # month (default)
            since = d.replace(day=1).isoformat()

        where_v = "AND nit_vendedor = ?" if vendedor_id else ""
        params: list = [since, d.isoformat()]
        if vendedor_id:
            params.append(vendedor_id)

        rows = self._con.execute(
            f"""
            SELECT COALESCE(NULLIF(nit_vendedor,''),'SIN_ASIGNAR') AS nit,
                   COALESCE(NULLIF(nombre_vendedor,''),'Sin asignar') AS nombre,
                   COUNT(*) AS facturas, ROUND(SUM(total_factura),2) AS total
            FROM silver_fact_ventas
            WHERE business_date >= ? AND business_date <= ? {where_v}
            GROUP BY nit_vendedor, nombre_vendedor ORDER BY total DESC LIMIT 5
        """,
            params,
        ).fetchall()
        return {
            "period": period,
            "vendedores": [
                {"nit": r[0], "nombre": r[1], "facturas": int(r[2]), "total": float(r[3])}
                for r in rows
            ],
        }

    def get_inventory_value(self) -> dict:
        """Valor total del inventario, usando último costo de compra disponible."""
        r = self._con.execute("""
            WITH latest_cost AS (
                SELECT cod_producto, costo_producto,
                       ROW_NUMBER() OVER (PARTITION BY cod_producto ORDER BY business_date DESC) AS rn
                FROM silver_fact_compras_detalle
                WHERE costo_producto > 0
            )
            SELECT
                ROUND(COALESCE(SUM(i.cantidad_actual),0),2) AS stock,
                ROUND(COALESCE(SUM(i.cantidad_actual * COALESCE(lc.costo_producto, 0)), 0), 0) AS valor_total,
                COUNT(DISTINCT i.cod_producto) AS productos
            FROM gold_mart_inventario_actual i
            LEFT JOIN latest_cost lc ON i.cod_producto = lc.cod_producto AND lc.rn = 1
        """).fetchone()
        return {
            "stock_total_unidades": float(r[0] or 0),
            "valor_total_cop": float(r[1] or 0),
            "num_productos_distintos": int(r[2] or 0),
        }

    def compare_periods(self, period_1: str, period_2: str) -> dict:
        """Compara ventas entre dos meses (YYYY-MM)."""
        r1 = self._con.execute(
            """
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COALESCE(SUM(num_facturas),0)
            FROM gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
        """,
            [period_1],
        ).fetchone()
        r2 = self._con.execute(
            """
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COALESCE(SUM(num_facturas),0)
            FROM gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
        """,
            [period_2],
        ).fetchone()
        v1 = float(r1[0] or 0)
        v2 = float(r2[0] or 0)
        delta = round((v2 - v1) / v1 * 100, 1) if v1 else None
        return {
            "period_1": {"ventas": v1, "facturas": int(r1[1] or 0)},
            "period_2": {"ventas": v2, "facturas": int(r2[1] or 0)},
            "delta_pct": delta,
        }

    def get_abc_distribution(self) -> dict:
        """Distribución ABC del último mes."""
        rows = self._con.execute("""
            WITH mm AS (SELECT MAX(business_month) AS m FROM gold_mart_rotacion_abc)
            SELECT categoria_abc, COUNT(*) AS skus, ROUND(SUM(valor_total),2) AS valor
            FROM gold_mart_rotacion_abc, mm WHERE business_month = mm.m
            GROUP BY categoria_abc ORDER BY categoria_abc
        """).fetchall()
        return {"abc": [{"categoria": r[0], "skus": int(r[1]), "valor": float(r[2])} for r in rows]}

    def get_forecast_summary(self) -> dict:
        """Resumen del forecast por categoría."""
        rows = self._con.execute("""
            SELECT cod_grupo, ROUND(SUM(demanda_real),2),
                   ROUND(SUM(demanda_predicha_baseline),2),
                   ROUND(ABS(SUM(demanda_real)-SUM(demanda_predicha_baseline))/NULLIF(SUM(demanda_real),0)*100,2)
            FROM gold_forecast_categoria
            WHERE business_date >= CURRENT_DATE - INTERVAL '30' DAY
            GROUP BY cod_grupo ORDER BY 2 DESC
        """).fetchall()
        return {
            "forecast": [
                {
                    "grupo": r[0],
                    "real": float(r[1]),
                    "predicho": float(r[2]),
                    "desviacion_pct": float(r[3]),
                }
                for r in rows
            ]
        }

    def get_data_freshness(self) -> dict:
        """Fecha máxima disponible en las tablas de hechos del tenant."""
        tables = (
            ("gold_mart_ventas_diarias_sku", "business_date"),
            ("gold_mart_inventario_actual", "snapshot_date"),
            ("silver_fact_compras", "business_date"),
        )
        result: dict[str, str | None] = {}
        for table, col in tables:
            try:
                row = self._con.execute(f"SELECT MAX({col}) FROM {table}").fetchone()
                result[table] = row[0].isoformat() if row and row[0] else None
            except Exception:
                result[table] = None
        dates = [value for value in result.values() if value]
        return {
            "tenant": self.tenant,
            "fecha_maxima": max(dates) if dates else None,
            "por_tabla": result,
        }

    def get_ultima_compra(self) -> dict:
        """Última compra válida, con proveedor, monto, estado y productos."""
        row = self._con.execute(
            """
            SELECT business_date, num_documento, cod_clase, nit_proveedor,
                   nombre_proveedor, total_factura, estado_documento
            FROM silver_fact_compras
            WHERE COALESCE(estado_documento, '') != 'A'
            ORDER BY business_date DESC,
                     TRY_CAST(num_documento AS BIGINT) DESC NULLS LAST,
                     num_documento DESC
            LIMIT 1
        """
        ).fetchone()
        if not row:
            return {
                "mensaje": "No hay compras registradas para este tenant.",
                **self._purchase_metadata(None),
            }

        items = self._con.execute(
            """
            SELECT cod_producto, nombre_detalle, cantidad, total_detalle
            FROM silver_fact_compras_detalle
            WHERE num_documento = ? AND cod_clase = ?
            ORDER BY total_detalle DESC
            LIMIT 15
        """,
            [row[1], row[2]],
        ).fetchall()

        estado = str(row[6] or "").strip()
        result = {
            "fecha": row[0].isoformat(),
            "num_documento": row[1],
            "proveedor": row[4],
            "nit_proveedor": row[3],
            "total_factura": float(row[5] or 0),
            "estado_documento": estado,
            "nota_estado": (
                "El documento figura con estado 'A' (posiblemente anulada); verificá con contabilidad."
                if estado == "A"
                else None
            ),
            "productos": [
                {
                    "codigo": i[0],
                    "nombre": i[1],
                    "cantidad": float(i[2] or 0),
                    "valor_total": float(i[3] or 0),
                }
                for i in items
            ],
        }
        return {**result, **self._purchase_metadata(row[0])}

    def get_compras_recientes(self, limit: int = 5) -> dict:
        """Últimas N compras válidas (fecha, documento, proveedor, total, estado)."""
        limit = max(1, min(int(limit), 20))
        rows = self._con.execute(
            """
            SELECT business_date, num_documento, nombre_proveedor, total_factura, estado_documento
            FROM silver_fact_compras
            WHERE COALESCE(estado_documento, '') != 'A'
            ORDER BY business_date DESC,
                     TRY_CAST(num_documento AS BIGINT) DESC NULLS LAST,
                     num_documento DESC
            LIMIT ?
        """,
            [limit],
        ).fetchall()
        if not rows:
            return {
                "mensaje": "No hay compras registradas para este tenant.",
                **self._purchase_metadata(None),
            }
        result = {
            "compras": [
                {
                    "fecha": r[0].isoformat(),
                    "num_documento": r[1],
                    "proveedor": r[2],
                    "total_factura": float(r[3] or 0),
                    "estado_documento": str(r[4] or "").strip(),
                }
                for r in rows
            ],
            "count": len(rows),
        }
        return {**result, **self._purchase_metadata(rows[0][0])}

    def buscar_compras_por_proveedor(self, query: str, limit: int = 10) -> dict:
        """Busca compras por nombre de proveedor (búsqueda parcial, case-insensitive, multi-palabra)."""
        limit = max(1, min(int(limit), 50))
        # Split query into words; each word must appear somewhere in the supplier name
        words = [w.strip() for w in query.split() if w.strip()]
        if not words:
            return {"mensaje": "Proporcioná un nombre de proveedor para buscar.", **self._purchase_metadata(None)}
        where_clauses = " AND ".join(["nombre_proveedor ILIKE ?"] * len(words))
        params = [f"%{w}%" for w in words] + [limit]
        rows = self._con.execute(
            f"""
            SELECT business_date, num_documento, cod_clase, nombre_proveedor,
                   nit_proveedor, total_factura, estado_documento
            FROM silver_fact_compras
            WHERE {where_clauses}
              AND COALESCE(estado_documento, '') != 'A'
            ORDER BY business_date DESC,
                     TRY_CAST(num_documento AS BIGINT) DESC NULLS LAST,
                     num_documento DESC
            LIMIT ?
        """,
            params,
        ).fetchall()
        if not rows:
            return {
                "mensaje": f"No se encontraron compras para proveedores que coincidan con '{query}'.",
                **self._purchase_metadata(None),
            }
        result = {
            "compras": [
                {
                    "fecha": r[0].isoformat(),
                    "num_documento": r[1],
                    "proveedor": r[3],
                    "nit_proveedor": r[4],
                    "total_factura": float(r[5] or 0),
                    "estado_documento": str(r[6] or "").strip(),
                }
                for r in rows
            ],
            "count": len(rows),
            "busqueda": query,
        }
        return {**result, **self._purchase_metadata(rows[0][0])}

    def get_producto_detalle(self, codigo: str, window_days: int = 180) -> dict:
        """Detalle operativo completo de un producto usando las mismas métricas de la ficha web."""

        # 1. Ficha técnica del producto
        prod = self._con.execute(
            """
            SELECT cod_producto, nombre_producto, codigo_barras, presentacion,
                   existencia, costo_producto, costo_ultima_compra,
                   precio_venta_sin_iva, precio_venta_con_iva,
                   estado_producto, cod_grupo, nit_proveedor,
                   stock_minimo, stock_maximo, fecha_actualizacion
            FROM silver_dim_producto
            WHERE cod_producto = ?
            """,
            [codigo],
        ).fetchone()
        if not prod:
            return {"error": f"Producto '{codigo}' no encontrado en el catálogo."}

        # 2. Nombre del proveedor (por NIT o por última compra directa)
        proveedor_nombre = proveedor_nombre = prod[11]  # NIT por defecto
        if prod[11]:
            proveedor_row = self._con.execute(
                "SELECT nombre_proveedor FROM silver_fact_compras WHERE nit_proveedor = ? AND nombre_proveedor != '' LIMIT 1",
                [prod[11]],
            ).fetchone()
            if proveedor_row:
                proveedor_nombre = proveedor_row[0]

        # 3. Última compra del producto (via detalle)
        ultima_compra = self._con.execute(
            """
            SELECT c.business_date, c.num_documento, c.nombre_proveedor, c.total_factura
            FROM silver_fact_compras c
            INNER JOIN silver_fact_compras_detalle d
              ON d.num_documento = c.num_documento AND d.cod_clase = c.cod_clase
            WHERE d.cod_producto = ? AND COALESCE(c.estado_documento, '') != 'A'
            ORDER BY c.business_date DESC LIMIT 1
            """,
            [codigo],
        ).fetchone()

        # 4. Última venta
        ultima_venta = self._con.execute(
            """
            SELECT v.business_date, v.num_documento, v.nombre_cliente,
                   d.total_detalle, d.cantidad
            FROM silver_fact_ventas_detalle d
            JOIN silver_fact_ventas v ON d.num_documento = v.num_documento AND d.cod_clase = v.cod_clase
            WHERE d.cod_producto = ?
            ORDER BY v.business_date DESC LIMIT 1
            """,
            [codigo],
        ).fetchone()

        # 5. Resumen de compras (totales)
        compras_resumen = self._con.execute(
            """
            SELECT COUNT(*) as num_compras,
                   SUM(d.cantidad) as total_unidades,
                   SUM(d.total_detalle) as total_valor
            FROM silver_fact_compras_detalle d
            JOIN silver_fact_compras c ON d.num_documento = c.num_documento AND d.cod_clase = c.cod_clase
            WHERE d.cod_producto = ? AND COALESCE(c.estado_documento, '') != 'A'
            """,
            [codigo],
        ).fetchone()

        # 6. Resumen de ventas (totales)
        ventas_resumen = self._con.execute(
            """
            SELECT COUNT(*) as num_ventas,
                   SUM(d.cantidad) as total_unidades,
                   SUM(d.total_detalle) as total_valor
            FROM silver_fact_ventas_detalle d
            JOIN silver_fact_ventas v ON d.num_documento = v.num_documento AND d.cod_clase = v.cod_clase
            WHERE d.cod_producto = ? AND COALESCE(v.estado_documento, '') != 'A'
            """,
            [codigo],
        ).fetchone()

        # 7. Movimiento mensual — últimos meses con actividad
        movimientos = self._con.execute(
            """
            SELECT
              strftime(c.business_date, '%Y-%m') as mes,
              SUM(CASE WHEN c.tipo = 'compra' THEN c.cantidad ELSE 0 END) as comprado_u,
              SUM(CASE WHEN c.tipo = 'compra' THEN c.total ELSE 0 END) as comprado_valor,
              SUM(CASE WHEN c.tipo = 'venta' THEN c.cantidad ELSE 0 END) as vendido_u,
              SUM(CASE WHEN c.tipo = 'venta' THEN c.total ELSE 0 END) as vendido_valor
            FROM (
              SELECT d.cod_producto, c.business_date, 'compra' as tipo,
                     d.cantidad, d.total_detalle as total
              FROM silver_fact_compras_detalle d
              JOIN silver_fact_compras c ON d.num_documento = c.num_documento AND d.cod_clase = c.cod_clase
              WHERE d.cod_producto = ? AND COALESCE(c.estado_documento, '') != 'A'
              UNION ALL
              SELECT d.cod_producto, v.business_date, 'venta' as tipo,
                     d.cantidad, d.total_detalle as total
              FROM silver_fact_ventas_detalle d
              JOIN silver_fact_ventas v ON d.num_documento = v.num_documento AND d.cod_clase = v.cod_clase
              WHERE d.cod_producto = ? AND COALESCE(v.estado_documento, '') != 'A'
            ) c
            GROUP BY mes
            ORDER BY mes DESC
            LIMIT 12
            """,
            [codigo, codigo],
        ).fetchall()

        movimientos_lista = [
            {
                "mes": m[0],
                "comprado_u": float(m[1]),
                "comprado_valor": float(m[2]),
                "vendido_u": float(m[3]),
                "vendido_valor": float(m[4]),
            }
            for m in movimientos
        ]

        # 8. Valor inventario actual
        inv_valor = self._con.execute(
            """
            SELECT COALESCE(SUM(valor_costo * cantidad), 0)
            FROM silver_fact_inventario
            WHERE cod_producto = ? AND business_date = (SELECT MAX(business_date) FROM silver_fact_inventario)
            """,
            [codigo],
        ).fetchone()

        existencia = float(prod[4] or 0)
        costo = float(prod[5] or 0)
        precio = float(prod[7] or 0)
        margen_unit = precio - costo if precio and costo else 0
        margen_pct = (margen_unit / precio * 100) if precio else 0

        resultado = {
            "ficha": {
                "codigo": prod[0],
                "nombre": prod[1],
                "codigo_barras": prod[2],
                "presentacion": prod[3],
                "estado": prod[9],
                "grupo": prod[10],
            },
            "stock": {
                "actual": existencia,
                "minimo": float(prod[12] or 0),
                "maximo": float(prod[13] or 0),
                "valor_inventario": float(inv_valor[0]) if inv_valor else 0,
                "sin_stock": existencia == 0,
            },
            "precios": {
                "precio_venta": precio,
                "costo": costo,
                "costo_ultima_compra": float(prod[6] or 0),
                "margen_unitario": margen_unit,
                "margen_porcentaje": round(margen_pct, 1),
            },
            "proveedor": {
                "nit": prod[11],
                "nombre": proveedor_nombre,
            },
            "compras": {
                "total_transacciones": int(compras_resumen[0] or 0),
                "total_unidades": float(compras_resumen[1] or 0),
                "total_valor": float(compras_resumen[2] or 0),
                "ultima_compra": {
                    "fecha": ultima_compra[0].isoformat() if ultima_compra else None,
                    "documento": ultima_compra[1] if ultima_compra else None,
                    "proveedor": ultima_compra[2] if ultima_compra else None,
                    "total": float(ultima_compra[3]) if ultima_compra else None,
                } if ultima_compra else None,
            },
            "ventas": {
                "total_transacciones": int(ventas_resumen[0] or 0),
                "total_unidades": float(ventas_resumen[1] or 0),
                "total_valor": float(ventas_resumen[2] or 0),
                "ultima_venta": {
                    "fecha": ultima_venta[0].isoformat() if ultima_venta else None,
                    "documento": ultima_venta[1] if ultima_venta else None,
                    "cliente": ultima_venta[2] if ultima_venta else None,
                    "total": float(ultima_venta[3]) if ultima_venta else None,
                } if ultima_venta else None,
            },
            "movimiento_mensual": movimientos_lista,
        }
        # Reutilizar el cálculo canónico del dashboard evita que el asistente
        # informe stock, costos o estados distintos a los de la ficha web.
        try:
            from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

            dashboard_detail = DuckDBMetricsRepo(
                db_path=self.duckdb_path,
                tenant=self.tenant,
            ).get_product_detail(codigo, window_days)
        except Exception:
            dashboard_detail = {"found": False}

        if dashboard_detail.get("found") and dashboard_detail.get("metrics"):
            metrics = _json_safe(dashboard_detail["metrics"])
            timeline = _json_safe(dashboard_detail.get("timeline", []))
            movements = _json_safe(dashboard_detail.get("movimientos", []))
            visible_movements = movements[:100]
            sales_by_month = [float(row.get("unidades_vendidas", 0) or 0) for row in timeline]
            average_monthly_sales = (
                sum(sales_by_month) / len(sales_by_month) if sales_by_month else 0
            )
            last_month_sales = sales_by_month[-1] if sales_by_month else None
            trend_pct = (
                round((last_month_sales - average_monthly_sales) / average_monthly_sales * 100, 1)
                if last_month_sales is not None and average_monthly_sales > 0
                else None
            )
            rotation_days = (
                round(365 / metrics["rotacion_anual"])
                if metrics.get("rotacion_anual") and metrics["rotacion_anual"] > 0
                else None
            )

            resultado.update({
                "metricas_operativas": metrics,
                "estado_operativo": {
                    "estado": metrics.get("estado"),
                    "accion": metrics.get("accion"),
                    "categoria_abc": metrics.get("abc"),
                    "descripcion": (
                        f"{metrics.get('estado')}; acción sugerida: {metrics.get('accion')}"
                    ),
                },
                "ritmo_rotacion": {
                    "velocidad_mensual": metrics.get("velocidad_mensual"),
                    "dias_stock": metrics.get("dias_stock"),
                    "dias_por_rotacion": rotation_days,
                    "rotacion_anual": metrics.get("rotacion_anual"),
                    "tendencia_ultimo_mes_pct": trend_pct,
                },
                "timeline_mensual": timeline,
                "historial_movimientos": visible_movements,
                "movimientos_totales": len(movements),
                "movimientos_mostrados": len(visible_movements),
                "movimientos_omitidos": max(0, len(movements) - len(visible_movements)),
                "periodo_metricas_dias": window_days,
            })
            # Estos valores deben coincidir con la ficha del dashboard.
            resultado["stock"].update({
                "actual": metrics.get("cantidad_actual", resultado["stock"]["actual"]),
                "valor_inventario": metrics.get("valor_inventario", resultado["stock"]["valor_inventario"]),
            })
            resultado["precios"].update({
                "costo": metrics.get("costo_unit", resultado["precios"]["costo"]),
                "margen_unitario": round(
                    float(metrics.get("precio", 0) or 0) - float(metrics.get("costo_unit", 0) or 0), 2
                ),
                "margen_porcentaje": metrics.get("margen_pct"),
            })
            if metrics.get("proveedor"):
                resultado["proveedor"]["nombre"] = metrics["proveedor"]

        return resultado

    def get_detalle_compra(
        self,
        num_documento: str,
        fecha: str = "",
        producto: str = "",
        limit: int = 40,
    ) -> dict:
        """Detalle resumido y consultable de productos de una compra específica."""
        limit = max(1, min(int(limit), 100))
        # Buscar la compra
        if fecha:
            compra = self._con.execute(
                """
                SELECT business_date, num_documento, cod_clase, nombre_proveedor,
                       nit_proveedor, total_factura, estado_documento
                FROM silver_fact_compras
                WHERE num_documento = ? AND business_date = ? AND COALESCE(estado_documento, '') != 'A'
                LIMIT 1
                """,
                [num_documento, fecha],
            ).fetchone()
        else:
            compra = self._con.execute(
                """
                SELECT business_date, num_documento, cod_clase, nombre_proveedor,
                       nit_proveedor, total_factura, estado_documento
                FROM silver_fact_compras
                WHERE num_documento = ? AND COALESCE(estado_documento, '') != 'A'
                ORDER BY business_date DESC LIMIT 1
                """,
                [num_documento],
            ).fetchone()

        if not compra:
            return {"error": f"No se encontró la compra '{num_documento}' (fecha: {fecha or 'cualquiera'})."}

        # Obtener detalles de productos
        todos_los_detalles = self._con.execute(
            """
            SELECT cod_producto, nombre_detalle, cantidad, valor_unitario,
                   total_detalle, costo_producto
            FROM silver_fact_compras_detalle
            WHERE num_documento = ? AND cod_clase = ?
            ORDER BY total_detalle DESC
            """,
            [num_documento, compra[2]],
        ).fetchall()

        # El detalle puede tener cientos de líneas. Filtrar antes de construir
        # la respuesta evita exceder el límite de contexto del proveedor LLM.
        terminos = [term.casefold() for term in str(producto or "").split() if term.strip()]
        detalles = [
            detalle
            for detalle in todos_los_detalles
            if not terminos
            or all(
                termino in f"{detalle[0] or ''} {detalle[1] or ''}".casefold()
                for termino in terminos
            )
        ]
        detalles_visibles = detalles[:limit]
        total_calculado = sum(float(d[4] or 0) for d in todos_los_detalles)

        resultado = {
            "compra": {
                "fecha": compra[0].isoformat(),
                "num_documento": compra[1],
                "proveedor": compra[3],
                "nit_proveedor": compra[4],
                "total_factura": float(compra[5] or 0),
                "total_calculado_detalles": round(total_calculado, 2),
                "estado_documento": str(compra[6] or "").strip(),
            },
            "productos": [
                {
                    "codigo": d[0],
                    "nombre": d[1],
                    "cantidad": float(d[2] or 0),
                    "valor_unitario": float(d[3] or 0),
                    "total": float(d[4] or 0),
                    "costo": float(d[5] or 0),
                }
                for d in detalles_visibles
            ],
            "total_productos": len(detalles),
            "total_productos_factura": len(todos_los_detalles),
            "productos_mostrados": len(detalles_visibles),
            "productos_omitidos": max(0, len(detalles) - len(detalles_visibles)),
            "filtro_producto": producto or None,
        }
        return resultado

    @staticmethod
    def _purchase_metadata(cutoff: date | None) -> dict:
        cutoff_at = cutoff.isoformat() if cutoff else None
        observed_at = datetime.now(UTC).isoformat()
        return {
            "sources": [{
                "source_id": "duckdb-purchases",
                "domain": "purchases",
                "kind": "duckdb",
                "citation": "DuckDB purchases snapshot",
                "cutoff_at": cutoff_at,
                "observed_at": observed_at,
                "status": "used",
            }],
            "freshness": [{
                "domain": "purchases",
                "cutoff_at": cutoff_at,
                "observed_at": observed_at,
                "status": "current" if cutoff_at else "unknown",
            }],
        }

    def search_products(self, query: str, limit: int = 10) -> dict:
        """Busca productos por código, nombre parcial, palabras reordenadas o typos leves.

        Devuelve código, nombre, precio de venta, costo, stock, proveedor y estado.
        NO la uses para auditar comportamiento de productos — usa get_productos_comportamiento.
        """
        limit = max(1, min(int(limit), 30))
        query = str(query or "").strip()
        if not query:
            return {"productos": [], "total": 0}
        rows = self._con.execute(
            """
            SELECT cod_producto, nombre_producto, precio_venta_sin_iva, costo_ultima_compra,
                   existencia, nit_proveedor, estado_producto, cod_grupo
            FROM silver_dim_producto
            """
        ).fetchall()

        scored_rows = []
        for row in rows:
            score = _product_match_score(
                query,
                " ".join(str(value or "") for value in (row[0], row[1], row[5], row[7])),
            )
            if score > 0:
                scored_rows.append((score, row))
        scored_rows.sort(key=lambda item: (item[0], float(item[1][4] or 0)), reverse=True)
        matches = [row for _, row in scored_rows]
        visible_rows = matches[:limit]
        result = {
            "productos": [
                {
                    "codigo": r[0],
                    "nombre": r[1],
                    "precio_venta": float(r[2] or 0),
                    "costo_ultima_compra": float(r[3] or 0),
                    "stock": float(r[4] or 0),
                    "proveedor": r[5],
                    "estado": r[6],
                    "grupo": r[7],
                }
                for r in visible_rows
            ],
            "total": len(matches),
            "ambiguo": len(matches) > 1,
            "criterio_busqueda": query,
        }
        if len(matches) > limit:
            result["productos_omitidos"] = len(matches) - limit
        return result

    def get_productos_comportamiento(self, skus: list[str], period: str = "month") -> dict:
        """Analiza el comportamiento de una lista de SKUs: ventas, stock, demanda y alertas.

        Usala para auditar compras o responder '¿cómo se comportan estos productos?',
        '¿se vendieron?', '¿tenían stock antes de comprarlos?'.
        Recibe una lista de códigos de producto y devuelve ventas, stock actual,
        alertas de quiebre y clasificación ABC para cada uno.
        """
        if not skus:
            return {"productos": []}
        skus = [str(s).strip() for s in skus if s][:20]  # max 20 SKUs
        period = str(period or "month").lower().strip()
        d = self._get_max_date()
        if d is None:
            return {"productos": [], "mensaje": "No hay datos disponibles"}

        if period == "day":
            since = d.isoformat()
        elif period == "week":
            since = (d - timedelta(days=7)).isoformat()
        elif period == "all":
            since = "1900-01-01"
        else:  # month
            since = d.replace(day=1).isoformat()

        placeholders = ",".join(["?" for _ in skus])

        # Ventas por SKU
        ventas_rows = self._con.execute(
            f"""
            SELECT cod_producto, ROUND(SUM(valor_total),2) AS valor, ROUND(SUM(cantidad_total),2) AS cantidad,
                   COUNT(*) AS num_ventas
            FROM gold_mart_ventas_diarias_sku
            WHERE cod_producto IN ({placeholders}) AND business_date >= ?
            GROUP BY cod_producto
        """,
            skus + [since],
        ).fetchall()
        ventas_map = {r[0]: {"valor_vendido": float(r[1] or 0), "unidades_vendidas": float(r[2] or 0), "num_ventas": int(r[3])} for r in ventas_rows}

        # Stock actual
        stock_rows = self._con.execute(
            f"""
            SELECT cod_producto, cantidad_actual
            FROM gold_mart_inventario_actual
            WHERE cod_producto IN ({placeholders})
        """,
            skus,
        ).fetchall()
        stock_map = {r[0]: float(r[1] or 0) for r in stock_rows}

        # Info del catálogo
        cat_rows = self._con.execute(
            f"""
            SELECT cod_producto, nombre_producto, precio_venta_sin_iva, costo_ultima_compra, existencia
            FROM silver_dim_producto
            WHERE cod_producto IN ({placeholders})
        """,
            skus,
        ).fetchall()
        cat_map = {r[0]: {"nombre": r[1], "precio_venta": float(r[2] or 0), "costo": float(r[3] or 0), "stock_catalogo": float(r[4] or 0)} for r in cat_rows}

        # Alertas de quiebre
        alert_rows = self._con.execute(
            f"""
            SELECT sku, dias_hasta_quiebre, urgencia
            FROM gold_alertas_quiebre
            WHERE sku IN ({placeholders})
        """,
            skus,
        ).fetchall()
        alert_map = {r[0]: {"dias_quiebre": int(r[1] or 0), "urgencia": r[2]} for r in alert_rows}

        # Dormidos
        dorm_rows = self._con.execute(
            f"""
            SELECT cod_producto, dias_sin_venta
            FROM gold_mart_productos_dormidos
            WHERE cod_producto IN ({placeholders}) AND dias_sin_venta < 5000
        """,
            skus,
        ).fetchall()
        dorm_map = {r[0]: int(r[1] or 0) for r in dorm_rows}

        productos = []
        for sku in skus:
            cat = cat_map.get(sku, {})
            v = ventas_map.get(sku, {})
            s = stock_map.get(sku, cat.get("stock_catalogo", 0))
            a = alert_map.get(sku)
            dorm = dorm_map.get(sku)

            producto = {
                "codigo": sku,
                "nombre": cat.get("nombre", "Desconocido"),
                "precio_venta": cat.get("precio_venta", 0),
                "costo": cat.get("costo", 0),
                "stock_actual": s,
                "valor_vendido_periodo": v.get("valor_vendido", 0),
                "unidades_vendidas_periodo": v.get("unidades_vendidas", 0),
                "num_ventas_periodo": v.get("num_ventas", 0),
                "dias_sin_venta": dorm,
                "alerta_quiebre": a,
            }
            productos.append(producto)

        return {
            "period": period,
            "productos": productos,
            "total": len(productos),
        }

    def get_top_clientes(self, period: str = "month", limit: int = 10) -> dict:
        """Top clientes por total facturado. Filtrable por período (day, week, month, all)."""
        d = self._get_max_date()
        if d is None:
            return {"clientes": []}
        limit = max(1, min(int(limit), 20))
        period = str(period or "month").lower().strip()

        if period == "day":
            since = d.isoformat()
        elif period == "week":
            since = (d - timedelta(days=7)).isoformat()
        elif period == "all":
            since = "1900-01-01"
        else:  # month
            since = d.replace(day=1).isoformat()

        rows = self._con.execute(
            """
            SELECT COALESCE(NULLIF(nit_cliente,''),'SIN_ASIGNAR') AS nit,
                   COALESCE(NULLIF(nombre_cliente,''),'Sin asignar') AS nombre,
                   COUNT(*) AS facturas, ROUND(SUM(total_factura),2) AS total
            FROM silver_fact_ventas
            WHERE business_date >= ? AND business_date <= ?
              AND COALESCE(estado_documento, '') != 'A'
            GROUP BY nit_cliente, nombre_cliente
            ORDER BY total DESC LIMIT ?
        """,
            [since, d.isoformat(), limit],
        ).fetchall()
        return {
            "period": period,
            "clientes": [
                {"nit": r[0], "nombre": r[1], "facturas": int(r[2]), "total": float(r[3])}
                for r in rows
            ],
        }

    def get_inventario_por_bodega(self, limit: int = 20) -> dict:
        """Inventario actual agrupado por bodega: unidades, valor y SKUs."""
        limit = max(1, min(int(limit), 50))
        rows = self._con.execute(
            """
            SELECT cod_bodega, nombre_bodega,
                   ROUND(SUM(cantidad),2) AS unidades,
                   ROUND(SUM(cantidad * COALESCE(valor_costo, 0)), 0) AS valor,
                   COUNT(DISTINCT cod_producto) AS skus
            FROM silver_fact_inventario
            WHERE cantidad > 0
            GROUP BY cod_bodega, nombre_bodega
            ORDER BY valor DESC LIMIT ?
        """,
            [limit],
        ).fetchall()
        return {
            "bodegas": [
                {
                    "codigo": r[0],
                    "nombre": r[1],
                    "unidades": float(r[2] or 0),
                    "valor_cop": float(r[3] or 0),
                    "skus": int(r[4] or 0),
                }
                for r in rows
            ],
        }

    def get_abc_xyz_distribution(self) -> dict:
        """Distribución ABC/XYZ del último mes: cuántos productos en cada combinación."""
        rows = self._con.execute("""
            WITH mm AS (SELECT MAX(business_month) AS m FROM gold_mart_abc_xyz)
            SELECT abc, xyz, COUNT(*) AS skus
            FROM gold_mart_abc_xyz, mm WHERE business_month = mm.m
            GROUP BY abc, xyz ORDER BY abc, xyz
        """).fetchall()
        return {
            "abc_xyz": [
                {"abc": r[0], "xyz": r[1], "skus": int(r[2])}
                for r in rows
            ],
        }

    def get_cohortes_clientes(self, limit: int = 6) -> dict:
        """Retención de cohortes de clientes: cuántos compran mes a mes desde su primer compra."""
        limit = max(1, min(int(limit), 12))
        rows = self._con.execute(
            """
            SELECT mes_cohorte, business_month,
                   COUNT(DISTINCT nit_cliente) AS clientes,
                   ROUND(AVG(ticket_promedio),2) AS ticket_promedio
            FROM gold_mart_cohortes_clientes
            WHERE mes_cohorte >= (
                SELECT MAX(mes_cohorte) FROM gold_mart_cohortes_clientes
            ) - INTERVAL '?' MONTH
            GROUP BY mes_cohorte, business_month
            ORDER BY mes_cohorte, business_month
        """,
            [limit],
        ).fetchall()
        return {
            "cohortes": [
                {
                    "mes_cohorte": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]),
                    "mes_medicion": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                    "clientes_activos": int(r[2]),
                    "ticket_promedio": float(r[3] or 0),
                }
                for r in rows
            ],
        }

    def get_drift_alerts(self) -> dict:
        """Alertas de drift: categorías con desviación significativa entre demanda real y predicha."""
        rows = self._con.execute("""
            SELECT cod_grupo, week_end, desviacion_pct, threshold_pct, alert_msg
            FROM gold_alertas_drift
            ORDER BY week_end DESC
            LIMIT 10
        """).fetchall()
        return {
            "drift_alerts": [
                {
                    "grupo": r[0],
                    "semana": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                    "desviacion_pct": float(r[2] or 0),
                    "umbral_pct": float(r[3] or 0),
                    "mensaje": r[4],
                }
                for r in rows
            ],
            "total": len(rows),
        }

    def search_business_knowledge(self, query: str, limit: int = 5) -> dict:
        """Busca procedimientos/documentos del tenant con recuperación híbrida."""
        from motoshop_api.llm.retrieval import get_hybrid_retriever

        return get_hybrid_retriever().search(self.tenant, query, max(1, min(limit, 20)))

    # Ventanas de análisis soportadas. 'custom' exige date_from explícito.
    _PERIOD_DAYS = {
        "day": 1,
        "week": 7,
        "month": 30,
        "quarter": 90,
        "year": 365,
    }

    def _resolve_report_window(
        self,
        period: str,
        date_from: str | None,
        date_to: str | None,
        max_date: date,
    ) -> tuple[date, date, str]:
        """Resuelve el rango [desde, hasta] del análisis y su etiqueta legible.

        DuckDB no acepta aritmética parametrizada de fechas, por lo que los
        bounds se calculan SIEMPRE en Python y se pasan como ISO strings.
        """
        from datetime import datetime

        period = str(period or "month").lower().strip()

        def _parse(value: str | None, field: str) -> date | None:
            if not value:
                return None
            try:
                return datetime.fromisoformat(str(value).strip()).date()
            except ValueError as exc:
                raise ValueError(
                    f"'{field}' debe ser una fecha ISO válida (YYYY-MM-DD); recibí '{value}'"
                ) from exc

        parsed_from = _parse(date_from, "date_from")
        parsed_to = _parse(date_to, "date_to")
        if parsed_from and parsed_to and parsed_from > parsed_to:
            raise ValueError(
                f"date_from ({parsed_from}) no puede ser posterior a date_to ({parsed_to})"
            )

        until = min(parsed_to, max_date) if parsed_to else max_date

        if parsed_from:
            since = parsed_from
            label = f"{since.isoformat()} a {until.isoformat()}"
            return since, until, label

        if period == "all":
            r = self._con.execute(
                "SELECT MIN(business_date) FROM gold_mart_ventas_diarias_sku"
            ).fetchone()
            since = r[0] if r and r[0] else max_date - timedelta(days=365 * 5)
            label = f"{since.isoformat()} a {until.isoformat()} (histórico completo)"
            return since, until, label

        if period == "custom":
            raise ValueError(
                "period='custom' requiere date_from (YYYY-MM-DD). Sin fecha de inicio no puedo acotar el análisis."
            )

        days = self._PERIOD_DAYS.get(period)
        if days is None:
            days = self._PERIOD_DAYS["month"]
        since = max_date - timedelta(days=days - 1) if days > 1 else max_date
        label = f"{since.isoformat()} a {until.isoformat()} (últimos {days} día{'s' if days > 1 else ''})"
        return since, until, label

    def generate_report(
        self,
        format: str = "excel",
        report_type: str = "ventas_resumen",
        limit: int = 25,
        period: str = "month",
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """Genera un archivo descargable profesional en Excel, PDF o Word con datos de DuckDB.

        El rango de fechas del análisis es explícito: presets (day/week/month/
        quarter/year/all) o fechas exactas vía date_from/date_to (ISO YYYY-MM-DD).
        El período resuelto se imprime en el documento y se devuelve en el
        resultado para que el agente lo comunique al usuario.
        """
        from datetime import datetime

        from motoshop_api.reports.generator import (
            ReportData,
            generate_excel,
            generate_pdf,
            generate_word,
        )
        from motoshop_api.reports.storage import get_report_storage
        from motoshop_api.tenants import get_tenant_config

        config = get_tenant_config(self.tenant)
        tenant_name = config.nombre if config else self.tenant.capitalize()
        brand_color = config.color_brand if config and config.color_brand else "#7B1818"
        max_date = self._get_max_date()
        if max_date is None:
            return {"status": "empty", "summary": "No hay datos disponibles para generar el reporte."}
        date_str = max_date.isoformat()
        limit = max(5, min(int(limit), 100))

        fmt = str(format or "excel").lower().strip()
        if fmt in ("xlsx", "xls"):
            fmt = "excel"
        elif fmt == "docx":
            fmt = "word"
        if fmt not in ("excel", "pdf", "word"):
            fmt = "excel"

        report_type = str(report_type or "ventas_resumen").lower().strip()
        if report_type not in (
            "ventas_resumen",
            "top_productos",
            "inventario_critico",
            "productos_dormidos",
        ):
            report_type = "top_productos"

        # Solo los reportes de ventas tienen ventana temporal; los de
        # inventario/dormidos son fotos al corte y no filtran por fechas.
        applies_window = report_type in ("ventas_resumen", "top_productos")
        period_label = f"foto al corte {date_str}"
        since = until = max_date
        if applies_window:
            since, until, period_label = self._resolve_report_window(
                period, date_from, date_to, max_date
            )
        since_str, until_str = since.isoformat(), until.isoformat()
        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

        summary_metrics: dict[str, str] = {}

        if report_type in ("ventas_resumen", "top_productos"):
            title = f"Reporte de Ventas y Productos Más Vendidos — {tenant_name}"
            subtitle = f"Período analizado: {period_label} · Generado el {generated_at}"
            columns = [
                "Código SKU",
                "Nombre del Producto",
                "Cantidad Vendida",
                "Total Facturado (COP)",
            ]

            kpis = self._con.execute(
                """
                SELECT ROUND(COALESCE(SUM(valor_total),0),2),
                       COALESCE(SUM(num_facturas),0)
                FROM gold_mart_ventas_diarias_sku
                WHERE business_date >= ? AND business_date <= ?
            """,
                [since_str, until_str],
            ).fetchone()
            ventas_total = float(kpis[0] or 0)
            facturas_total = int(kpis[1] or 0)
            summary_metrics = {
                "Total Ventas Período": f"${ventas_total:,.0f} COP".replace(",", "."),
                "Total Facturas": f"{facturas_total:,}".replace(",", "."),
                "Ticket Promedio": f"${(ventas_total / facturas_total if facturas_total else 0):,.0f} COP".replace(
                    ",", "."
                ),
                "Período Analizado": period_label,
                "Fecha de Corte de Datos": date_str,
            }

            db_rows = self._con.execute(
                """
                SELECT cod_producto, nom_producto, ROUND(SUM(cantidad_total),2) AS cantidad, ROUND(SUM(valor_total),2) AS valor
                FROM gold_mart_ventas_diarias_sku
                WHERE business_date >= ? AND business_date <= ?
                GROUP BY cod_producto, nom_producto
                ORDER BY valor DESC LIMIT ?
            """,
                [since_str, until_str, limit],
            ).fetchall()
            rows = [[r[0], r[1], float(r[2] or 0), float(r[3] or 0)] for r in db_rows]

        elif report_type == "inventario_critico":
            title = f"Reporte de Inventario Crítico y Quiebre de Stock — {tenant_name}"
            subtitle = (
                f"Foto al corte {date_str} (sin ventana temporal) · Generado el {generated_at}"
            )
            columns = [
                "Código SKU",
                "Producto",
                "Stock Actual",
                "Demanda Predicha",
                "Días Quiebre",
                "Urgencia",
            ]

            db_rows = self._con.execute(
                """
                SELECT sku, nom_producto, stock_actual, demanda_predicha, dias_hasta_quiebre, urgencia
                FROM gold_alertas_quiebre
                ORDER BY dias_hasta_quiebre ASC LIMIT ?
            """,
                [limit],
            ).fetchall()
            rows = [
                [
                    r[0],
                    r[1],
                    float(r[2] or 0),
                    float(r[3] or 0),
                    int(r[4] or 0),
                    str(r[5] or "MEDIA"),
                ]
                for r in db_rows
            ]
            summary_metrics = {
                "SKUs en Riesgo": str(len(rows)),
                "Fecha de Corte": date_str,
            }

        elif report_type == "productos_dormidos":
            title = f"Reporte de Productos Dormidos (Sin Venta) — {tenant_name}"
            subtitle = (
                f"Foto al corte {date_str} (sin ventana temporal) · Generado el {generated_at}"
            )
            columns = ["Código SKU", "Producto", "Stock Actual", "Días sin Venta"]

            db_rows = self._con.execute(
                """
                SELECT cod_producto, nom_producto, stock_actual, dias_sin_venta
                FROM gold_mart_productos_dormidos
                WHERE dias_sin_venta >= 60 AND dias_sin_venta < 5000
                ORDER BY dias_sin_venta DESC LIMIT ?
            """,
                [limit],
            ).fetchall()
            rows = [[r[0], r[1], float(r[2] or 0), int(r[3] or 0)] for r in db_rows]
            summary_metrics = {
                "Total Dormidos": str(len(rows)),
                "Fecha de Corte": date_str,
            }

        report_data = ReportData(
            title=title,
            subtitle=subtitle,
            tenant_name=tenant_name,
            brand_color=brand_color,
            columns=columns,
            rows=rows,
            summary_metrics=summary_metrics,
        )

        date_clean = date_str.replace("-", "_")
        base_name = f"reporte_{report_type}_{self.tenant}_{date_clean}"

        if fmt == "excel":
            file_bytes = generate_excel(report_data)
            filename = f"{base_name}.xlsx"
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "pdf":
            file_bytes = generate_pdf(report_data)
            filename = f"{base_name}.pdf"
            mime_type = "application/pdf"
        else:
            file_bytes = generate_word(report_data)
            filename = f"{base_name}.docx"
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        storage = get_report_storage()
        rec = storage.save_report(file_bytes, filename, mime_type, self.tenant, self.user_id)

        return {
            "status": "success",
            "format": fmt,
            "filename": rec.filename,
            "download_url": rec.download_url,
            "file_size_kb": round(rec.file_size / 1024, 1),
            "records_count": len(rows),
            "date_from": since_str,
            "date_to": until_str,
            "period_label": period_label,
            "expires_at": rec.expires_at_iso,
            "summary": (
                f"Archivo {fmt.upper()} generado exitosamente: '{rec.filename}' "
                f"({round(rec.file_size / 1024, 1)} KB). Período analizado: {period_label}. "
                f"Comunicá este período al usuario."
            ),
        }

    def run(self, name: str, args: dict) -> dict:
        """Ejecuta una tool por nombre. Devuelve dict JSON."""
        if not getattr(self, "_assistant_enabled", True) or name not in self._allowed_tools:
            logger.warning("tool_denied tenant=%s tool=%s", self.tenant, name)
            return {"error": "Tool not allowed for this tenant"}
        method = getattr(self, name, None)
        if not method:
            return {"error": f"Tool '{name}' not found"}
        try:
            return method(**args)
        except ValueError as exc:
            logger.warning(
                "tool_validation_error tool=%s error_type=%s",
                name,
                type(exc).__name__,
            )
            return {"error": str(exc)}
        except Exception as exc:
            logger.warning(
                "tool_error tool=%s argument_keys=%s error_type=%s",
                name,
                sorted(str(key) for key in args),
                type(exc).__name__,
            )
            return {"error": "Tool execution failed"}

    def close(self):
        pass  # Connection is shared and managed globally


# ── Tool definitions (OpenAI-compatible) ────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_kpis_today",
            "description": "KPIs del último día con datos: ventas totales en COP, número de facturas, ticket promedio.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpis_month",
            "description": "KPIs de un mes específico (YYYY-MM) o del mes actual si no se especifica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "Mes en formato YYYY-MM (ej: 2026-05)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_skus",
            "description": "Top SKUs más vendidos en un período (day, week, month, all). Use 'all' para ranking histórico completo desde el inicio de operaciones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["day", "week", "month", "all"]},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dormidos",
            "description": "Productos sin venta hace al menos N días.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_min": {"type": "integer", "default": 90},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alerts_by_urgency",
            "description": "Alertas de quiebre de stock. Filtrar por urgencia: alta, media, baja.",
            "parameters": {
                "type": "object",
                "properties": {"urgency": {"type": "string", "enum": ["alta", "media", "baja"]}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vendedor_performance",
            "description": "Performance de vendedores. Filtrable por período (day, week, month, all) y vendedor_id opcional.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendedor_id": {"type": "string"},
                    "period": {"type": "string", "enum": ["day", "week", "month", "all"], "default": "month"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_value",
            "description": "Valor total del inventario en COP (valor_total_cop), stock en unidades (stock_total_unidades), y cantidad de productos distintos (num_productos_distintos).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "Compara ventas entre dos meses (YYYY-MM). Devuelve delta porcentual.",
            "parameters": {
                "type": "object",
                "properties": {"period_1": {"type": "string"}, "period_2": {"type": "string"}},
                "required": ["period_1", "period_2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_abc_distribution",
            "description": "Distribución ABC del último mes: cuántos SKUs en A, B, C y su valor.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast_summary",
            "description": "Resumen del forecast de demanda por categoría (real vs predicho).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_freshness",
            "description": "Fecha máxima disponible por tabla para no presentar datos desactualizados como actuales.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ultima_compra",
            "description": (
                "Consulta la última compra válida en DuckDB (excluye documentos anulados), incluyendo fecha, "
                "número de documento, proveedor, total, estado y productos comprados. "
                "Usala para preguntas como 'cuál fue la última compra' o 'cuándo se hizo la última compra'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_compras_recientes",
            "description": "Lista las últimas compras válidas (excluye documentos anulados) con fecha, proveedor, documento, total y estado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "description": "Cantidad de compras a devolver, entre 1 y 20.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_compras_por_proveedor",
            "description": (
                "Busca compras por nombre de proveedor (búsqueda parcial, case-insensitive). "
                "Devuelve todas las compras encontradas con fecha, documento, NIT, total y estado. "
                "Usala cuando el usuario pregunte por compras de un proveedor específico, "
                "por ejemplo '¿compramos a Karol Burgos?', '¿qué compras hicimos con Reprefil?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Nombre del proveedor a buscar (parcial, ej: 'Karol', 'Reprefil', 'Atmopel').",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Cantidad máxima de resultados, entre 1 y 50.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_producto_detalle",
            "description": (
                "Detalle completo de un producto: ficha técnica, stock, valor de inventario, "
                "precios, margen, velocidad, días de stock, rotación, estado operativo, "
                "ABC, ranking, proveedor, historial de compras, historial de ventas y "
                "movimiento mensual. "
                "Usala cuando el usuario pida detalles de un producto específico, "
                "por ejemplo '¿cómo está el producto 06-108?', 'detalles del comando derecho', "
                "'¿cuánto se vendió de este producto?', '¿cuándo se compró por última vez?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "Código del producto (ej: '06-108', '04-001').",
                    },
                    "window_days": {
                        "type": "integer",
                        "default": 180,
                        "description": "Días del período para ventas, velocidad y margen; normalmente 180.",
                    },
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_detalle_compra",
            "description": (
                "Detalle de productos de una compra específica: productos, cantidades, valores unitarios, "
                "totales y costos. Devuelve un resumen completo y una lista acotada de productos para no "
                "exceder el contexto; usá producto para consultar una línea concreta. "
                "Usala cuando el usuario pida el detalle de una compra específica, "
                "por ejemplo '¿qué productos tiene la compra 13?', 'detalla la compra del 27 de julio', "
                "'¿qué se compró en el documento 13?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "num_documento": {
                        "type": "string",
                        "description": "Número de documento de la compra (ej: '13', '43').",
                    },
                    "fecha": {
                        "type": "string",
                        "default": "",
                        "description": "Fecha de la compra en formato YYYY-MM-DD (opcional, si hay varias compras con mismo número).",
                    },
                    "producto": {
                        "type": "string",
                        "default": "",
                        "description": "Código o palabras del producto a consultar (opcional).",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 40,
                        "description": "Cantidad máxima de líneas devueltas, entre 1 y 100.",
                    },
                },
                "required": ["num_documento"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_business_knowledge",
            "description": "Busca conocimiento documental del tenant usando recuperación semántica y lexical.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Busca productos del catálogo por código SKU, nombre parcial, palabras "
                "desordenadas o errores leves de escritura. Devuelve un indicador ambiguo "
                "cuando hay varias coincidencias. "
                "Devuelve precio, costo, stock, proveedor y estado. "
                "Usala para preguntas como '¿tenemos filtros de aceite?', "
                "'¿cuál es el precio del SKU X?', '¿qué productos nos provee Y?'. "
                "NO la uses para auditar comportamiento de productos — usa get_productos_comportamiento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Término de búsqueda: nombre, código o proveedor."},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_productos_comportamiento",
            "description": (
                "Analiza el comportamiento de una lista de SKUs: ventas, stock, demanda y alertas de quiebre. "
                "Usala para auditar compras ('¿cómo se comportan estos productos?', '¿se vendieron?', "
                "'¿tenían stock antes de comprarlos?'). "
                "Recibe una lista de códigos de producto (máximo 20) y devuelve para cada uno: "
                "valor vendido, unidades vendidas, stock actual, alertas de quiebre y días sin venta. "
                "Usa esta tool en vez de llamar search_products múltiples veces."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de códigos de producto a analizar (máximo 20).",
                    },
                    "period": {"type": "string", "enum": ["day", "week", "month", "all"], "default": "month"},
                },
                "required": ["skus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_clientes",
            "description": (
                "Top clientes por total facturado. Filtrable por período (day, week, month, all). "
                "Usala para preguntas como '¿quiénes son nuestros mejores clientes?', "
                "'¿cuánto vendimos al cliente X?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["day", "week", "month", "all"], "default": "month"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventario_por_bodega",
            "description": (
                "Inventario actual agrupado por bodega: unidades, valor en COP y SKUs distintos. "
                "Usala para preguntas como '¿cuánto inventario hay por bodega?', "
                "'¿qué bodega tiene más stock?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_abc_xyz_distribution",
            "description": (
                "Distribución ABC/XYZ del último mes: muestra cuántos productos hay en cada "
                "combinación (A-X, A-Y, A-Z, B-X, etc.). "
                "Usala para preguntas como '¿cuántos productos son XYZ?', "
                "'¿cuáles son clase A pero impredecibles?'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cohortes_clientes",
            "description": (
                "Retención de cohortes de clientes: cuántos compran mes a mes desde su primera compra. "
                "Usala para preguntas como '¿cómo van los cohortes?', "
                "'¿cuántos clientes nuevos seguían comprando al mes siguiente?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 6, "description": "Meses de cohorte a mostrar (1-12)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_drift_alerts",
            "description": (
                "Alertas de drift: categorías con desviación significativa entre demanda real y predicha. "
                "Usala para preguntas como '¿hubo drift en alguna categoría?', "
                "'¿qué categorías se desviaron del forecast?'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": (
                "Genera un archivo descargable en Excel (.xlsx), PDF (.pdf) o Word (.docx) "
                "con datos de la empresa. Úsala SOLO cuando el usuario pida EXPLÍCITAMENTE "
                "un archivo, exportación o descarga ('pasame un excel', 'exportame un pdf', "
                "'descargame el reporte en word'). NO la uses para responder preguntas de "
                "datos en el chat ('cuáles son los productos con stock bajo') — para eso usá "
                "las tools de consulta como get_alerts_by_urgency, get_top_skus o get_dormidos. "
                "Ante pedidos ambiguos, respondé en el chat con los datos y ofrecé la "
                "exportación como opción. El documento indica el período analizado; "
                "comunicáselo siempre al usuario. Los reportes de inventario y dormidos son "
                "fotos al corte y no filtran por fechas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["excel", "pdf", "word"],
                        "description": "Formato del archivo a generar: 'excel' (.xlsx), 'pdf' (.pdf) o 'word' (.docx).",
                    },
                    "report_type": {
                        "type": "string",
                        "enum": [
                            "ventas_resumen",
                            "top_productos",
                            "inventario_critico",
                            "productos_dormidos",
                        ],
                        "description": "Tipo de reporte: 'ventas_resumen', 'top_productos', 'inventario_critico' o 'productos_dormidos'.",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["day", "week", "month", "quarter", "year", "all", "custom"],
                        "description": (
                            "Ventana temporal del análisis (solo reportes de ventas): 'day', 'week', "
                            "'month', 'quarter', 'year', 'all' (histórico completo) o 'custom' "
                            "(requiere date_from). Por defecto 'month'."
                        ),
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Fecha inicial del análisis en formato ISO YYYY-MM-DD. Usala cuando el usuario especifique 'desde' una fecha (ej. 'desde julio de 2024' → '2024-07-01'). Requiere period='custom' o reemplaza el preset.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Fecha final del análisis en ISO YYYY-MM-DD. Si no se envía, se usa la última fecha con datos.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Cantidad máxima de registros en la tabla (por defecto 25).",
                    },
                },
                "required": ["format"],
            },
        },
    },
]
