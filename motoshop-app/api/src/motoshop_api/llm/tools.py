"""Tools registry — tools tipadas para Q&A chat sobre DuckDB.

Cada tool toma args Pydantic, ejecuta query DuckDB, devuelve dict JSON.
TOOL_DEFINITIONS exporta specs OpenAI-compatible para function calling.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from contextlib import nullcontext
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

_VALID_SALES_CUTOFF_SQL = """
    WITH candidate_headers AS (
        SELECT business_date, num_documento, cod_clase,
               COUNT(*) OVER (
                   PARTITION BY business_date, cod_clase, num_documento
               ) AS identity_count
        FROM silver_fact_ventas
        WHERE UPPER(TRIM(COALESCE(estado_documento, ''))) != 'A'
          AND business_date IS NOT NULL
          AND TRIM(COALESCE(num_documento, '')) != ''
          AND TRIM(COALESCE(cod_clase, '')) != ''
    )
    SELECT MAX(business_date)
    FROM candidate_headers
    WHERE identity_count = 1
"""
_VALID_PURCHASE_CUTOFF_SQL = """
    WITH candidate_headers AS (
        SELECT business_date, num_documento, cod_clase,
               COUNT(*) OVER (
                   PARTITION BY business_date, cod_clase, num_documento
               ) AS identity_count
        FROM silver_fact_compras
        WHERE UPPER(TRIM(COALESCE(estado_documento, ''))) != 'A'
          AND business_date IS NOT NULL
          AND cod_clase = TRIM(COALESCE(cod_clase, ''))
          AND num_documento = TRIM(COALESCE(num_documento, ''))
          AND cod_clase != '' AND num_documento != ''
    )
    SELECT MAX(business_date)
    FROM candidate_headers
    WHERE identity_count = 1
"""


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
    "get_top_productos_periodo",
    "get_productos_para_reponer",
    "get_productos_catalogo",
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
    "get_compras_periodo",
    "get_top_compras_periodos",
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
    "analizar_compras_periodo",
    "evaluar_compra_planeada",
    "get_analisis_modulo",
    "generate_report",
    "get_cash_closure",
    "get_expiry_alerts",
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

    def _get_valid_sales_cutoff(self) -> date | None:
        """Return the latest date with unique, navigable, non-canceled sales headers."""
        try:
            row = self._con.execute(_VALID_SALES_CUTOFF_SQL).fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None

    def _get_valid_purchase_cutoff(self) -> date | None:
        """Return the latest date with unique, navigable, non-canceled purchases."""
        try:
            row = self._con.execute(_VALID_PURCHASE_CUTOFF_SQL).fetchone()
            return row[0] if row and row[0] else None
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

    def get_top_productos_periodo(
        self,
        periods: list[dict[str, str]],
        metric: str = "units",
        limit: int = 1,
    ) -> dict:
        """Rank products by valid sales over exact requested date ranges."""
        if metric not in {"units", "revenue"}:
            raise ValueError("La métrica debe ser units o revenue.")
        if periods == []:
            return {
                "status": "needs_clarification",
                "respuesta_fallback": "¿Qué mes, rango o fecha exacta querés rankear?",
                "productos": [],
                "sources": [],
                "freshness": [],
            }
        if not isinstance(periods, list) or not 1 <= len(periods) <= 6:
            raise ValueError("Indicá entre uno y seis períodos de ventas.")
        limit = int(limit)
        if not 1 <= limit <= 20:
            raise ValueError(
                "El ranking debe solicitar entre 1 y 20 posiciones por período y medida."
            )
        if len(periods) * limit > 20:
            raise ValueError("La comparación está limitada a veinte posiciones por respuesta.")

        requested: list[dict[str, object]] = []
        month_labels = (
            "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        )
        for period_id, period in enumerate(periods):
            if not isinstance(period, dict):
                raise ValueError("Cada período debe incluir fecha de inicio y fin.")
            try:
                start = date.fromisoformat(str(period.get("date_from", "")))
                end = date.fromisoformat(str(period.get("date_to", "")))
            except ValueError as exc:
                raise ValueError("Las fechas de ventas deben usar YYYY-MM-DD.") from exc
            if start > end or (end - start).days > 365:
                raise ValueError("Cada período debe cubrir como máximo 366 días.")
            if any(
                start <= date.fromisoformat(str(existing["date_to"]))
                and end >= date.fromisoformat(str(existing["date_from"]))
                for existing in requested
            ):
                raise ValueError("Los períodos de comparación no pueden superponerse.")
            if start == end:
                label = start.strftime("%d/%m/%Y")
            elif start.day == 1 and start.month == end.month and start.year == end.year:
                next_month = date(
                    start.year + (start.month == 12),
                    1 if start.month == 12 else start.month + 1,
                    1,
                )
                label = (
                    f"{month_labels[start.month - 1]} {start.year}"
                    if end.day == (next_month - timedelta(days=1)).day
                    else f"{start.isoformat()} a {end.isoformat()}"
                )
            else:
                label = f"{start.isoformat()} a {end.isoformat()}"
            requested.append({
                "period_id": period_id, "date_from": start, "date_to": end, "label": label,
            })

        period_values = ", ".join("(?, ?, ?, ?)" for _ in requested)
        period_params = [
            value
            for period in requested
            for value in (
                period["period_id"], period["date_from"], period["date_to"], period["label"]
            )
        ]
        metric_column = "units_sold" if metric == "units" else "revenue"
        rank_partition = "period_id, unit_group" if metric == "units" else "period_id"
        query = f"""
            WITH requested_periods(period_id, date_from, date_to, period_label) AS (
                VALUES {period_values}
            ), period_sales_headers AS (
                SELECT p.period_id, p.period_label,
                       h.business_date, h.num_documento, h.cod_clase,
                       COUNT(*) OVER (
                           PARTITION BY p.period_id, h.business_date, h.cod_clase, h.num_documento
                       ) AS identity_count
                FROM requested_periods p
                INNER JOIN silver_fact_ventas h
                    ON h.business_date BETWEEN p.date_from AND p.date_to
                WHERE UPPER(TRIM(COALESCE(h.estado_documento, ''))) != 'A'
                  AND TRIM(COALESCE(h.num_documento, '')) != ''
                  AND TRIM(COALESCE(h.cod_clase, '')) != ''
            ), valid_sales_headers AS (
                SELECT period_id, period_label, business_date, num_documento, cod_clase
                FROM period_sales_headers
                WHERE identity_count = 1
            ), sales_lines AS (
                SELECT h.period_id, h.period_label, d.cod_producto AS sku,
                       COALESCE(NULLIF(TRIM(d.nombre_detalle), ''), d.cod_producto) AS detail_name,
                       COALESCE(d.cantidad, 0) AS quantity,
                       COALESCE(d.total_detalle, 0) AS line_revenue
                FROM valid_sales_headers h
                INNER JOIN silver_fact_ventas_detalle d
                    ON h.business_date = d.business_date
                   AND h.cod_clase = d.cod_clase
                   AND h.num_documento = d.num_documento
                WHERE d.cod_producto IS NOT NULL AND TRIM(d.cod_producto) != ''
            ), catalog AS (
                SELECT cod_producto, nombre_producto, cod_medida, presentacion
                FROM (
                    SELECT cod_producto, nombre_producto, cod_medida, presentacion,
                           ROW_NUMBER() OVER (
                               PARTITION BY cod_producto
                               ORDER BY snapshot_date DESC NULLS LAST,
                                        fecha_actualizacion DESC NULLS LAST
                           ) AS snapshot_rank
                    FROM silver_dim_producto
                ) latest_catalog
                WHERE snapshot_rank = 1
            ), sku_totals AS (
                SELECT s.period_id, s.period_label, s.sku,
                       COALESCE(MAX(NULLIF(TRIM(c.nombre_producto), '')),
                                MAX(NULLIF(TRIM(s.detail_name), '')), s.sku) AS nombre,
                       MAX(COALESCE(NULLIF(TRIM(c.presentacion), ''),
                                    NULLIF(TRIM(c.cod_medida), ''))) AS unit_label,
                       MAX(NULLIF(TRIM(c.cod_medida), '')) AS unit_code,
                       ROUND(SUM(s.quantity), 2) AS units_sold,
                       ROUND(SUM(s.line_revenue), 2) AS revenue
                FROM sales_lines s
                LEFT JOIN catalog c ON c.cod_producto = s.sku
                GROUP BY s.period_id, s.period_label, s.sku
            ), eligible AS (
                SELECT *,
                       CASE
                           WHEN unit_code IS NOT NULL AND TRIM(unit_code) != ''
                               THEN UPPER(TRIM(unit_code))
                           WHEN unit_label IS NOT NULL AND TRIM(unit_label) != ''
                               THEN UPPER(TRIM(unit_label))
                           ELSE 'UNKNOWN:' || sku
                       END AS unit_group
                FROM sku_totals
                WHERE {metric_column} > 0
            ), ranked_products AS (
                SELECT *,
                       DENSE_RANK() OVER (
                           PARTITION BY {rank_partition} ORDER BY {metric_column} DESC
                       ) AS metric_rank,
                       ROW_NUMBER() OVER (
                           PARTITION BY {rank_partition}, {metric_column}
                           ORDER BY units_sold DESC, revenue DESC, sku
                       ) AS tie_row,
                       COUNT(*) OVER (
                           PARTITION BY {rank_partition}, {metric_column}
                ) AS tie_count
                FROM eligible
            ), all_ranked_results AS (
                SELECT *, COUNT(*) OVER () AS ranked_result_count
                FROM ranked_products
                WHERE metric_rank <= ?
            ), tie_capped_results AS (
                SELECT *, COUNT(*) OVER () AS tie_capped_result_count
                FROM all_ranked_results
                WHERE tie_row <= 25
            ), bounded_results AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           ORDER BY period_id, metric_rank,
                                    CASE WHEN unit_group LIKE 'UNKNOWN:%' THEN 1 ELSE 0 END,
                                    unit_group, units_sold DESC, revenue DESC, sku
                       ) AS result_row
                FROM tie_capped_results
            )
            SELECT period_id, period_label, sku, nombre, unit_label, unit_group,
                   units_sold, revenue, metric_rank, tie_row, tie_count,
                   ranked_result_count, tie_capped_result_count
            FROM bounded_results
            WHERE result_row <= 100
            ORDER BY period_id, metric_rank,
                     CASE WHEN unit_group LIKE 'UNKNOWN:%' THEN 1 ELSE 0 END,
                     unit_group, units_sold DESC, revenue DESC, sku
        """
        query_cursor = None
        try:
            sales_cutoff = self._get_valid_sales_cutoff()
            query_cursor = self._con.cursor()
            rows = query_cursor.execute(query, [*period_params, limit]).fetchall()
        except Exception as exc:
            logger.warning(
                "sales_product_ranking_failed tenant=%s error_type=%s",
                self.tenant,
                type(exc).__name__,
            )
            return {
                "status": "unavailable",
                "respuesta_fallback": (
                    "No pude verificar el ranking porque la fuente de ventas no respondió."
                ),
                "productos": [],
                "sources": [{
                    "source_id": "duckdb-sales-detail", "domain": "sales", "kind": "duckdb",
                    "citation": "DuckDB valid sales headers and detail", "cutoff_at": None,
                    "status": "failed",
                }],
                "freshness": [{"domain": "sales", "cutoff_at": None, "status": "unknown"}],
            }
        finally:
            for cursor in (query_cursor,):
                if cursor is not None and hasattr(cursor, "close"):
                    cursor.close()

        products = [
            {
                "sku": str(row[2]), "nombre": str(row[3]),
                "unidad": str(row[4] or "sin unidad"), "unidad_grupo": str(row[5]),
                "unidades": float(row[6] or 0), "valor": float(row[7] or 0),
                "rank": int(row[8]), "tie_row": int(row[9]), "tie_count": int(row[10]),
                "period_id": int(row[0]), "period_label": str(row[1]),
            }
            for row in rows
        ]
        ranked_result_count = int(rows[0][11]) if rows else 0
        tie_capped_result_count = int(rows[0][12]) if rows else 0
        global_truncated = tie_capped_result_count > 100
        ranking_truncated = ranked_result_count > len(products)
        period_availability: dict[int, dict[str, str | None]] = {}
        for period in requested:
            start = period["date_from"]
            end = period["date_to"]
            period_id = int(period["period_id"])
            if sales_cutoff is None:
                period_availability[period_id] = {
                    "status": "unavailable", "available_through": None,
                }
            elif start > sales_cutoff:
                period_availability[period_id] = {
                    "status": "unavailable", "available_through": None,
                }
            elif end > sales_cutoff:
                period_availability[period_id] = {
                    "status": "partial", "available_through": sales_cutoff.isoformat(),
                }
            else:
                period_availability[period_id] = {
                    "status": "complete", "available_through": end.isoformat(),
                }
        cutoff_at = sales_cutoff.isoformat() if sales_cutoff else None
        observed_at = datetime.now(UTC).isoformat()
        metadata = {
            "sources": [{
                "source_id": "duckdb-sales-detail", "domain": "sales", "kind": "duckdb",
                "citation": "DuckDB valid sales headers and detail", "cutoff_at": cutoff_at,
                "observed_at": observed_at, "status": "used" if cutoff_at else "failed",
            }],
            "freshness": [{"domain": "sales", "cutoff_at": cutoff_at, "observed_at": observed_at,
                           "status": "current" if cutoff_at else "unknown"}],
        }
        by_period: dict[int, list[dict]] = {}
        for product in products:
            by_period.setdefault(product["period_id"], []).append(product)
        metric_label = "unidades por medida" if metric == "units" else "valor facturado"
        fallback = [
            f"Ranking por {metric_label}; muestro los empates. "
            + (
                "Las medidas distintas no se comparan entre sí; productos sin unidad de catálogo "
                "se muestran por separado."
                if metric == "units" else ""
            )
        ]
        if tie_capped_result_count > 100:
            fallback.append(
                f"El resultado tiene {tie_capped_result_count} posiciones después de conservar "
                "empates; muestro hasta 100 "
                "para mantener la respuesta acotada."
            )
        if ranked_result_count > tie_capped_result_count:
            fallback.append(
                "Algunos empates superan 25 productos por posición y medida; se acotó la lista."
            )
        for period in requested:
            period_id = int(period["period_id"])
            availability = period_availability[period_id]
            winners = by_period.get(period_id, [])
            if not winners:
                fallback.extend(["", f"### {period['label'].capitalize()}"])
                if availability["status"] == "unavailable":
                    fallback.append(
                        "No puedo verificar este período: empieza después del corte válido "
                        f"de ventas ({cutoff_at or 'sin corte disponible'})."
                    )
                elif global_truncated:
                    fallback.append(
                        "No puedo confirmar si hubo ventas en este período: la respuesta llegó "
                        "al límite global de resultados. Consultá menos períodos o posiciones."
                    )
                elif availability["status"] == "partial":
                    fallback.append(
                        f"No encontré ventas válidas hasta {availability['available_through']}; "
                        "los días posteriores exceden el corte y no están verificados."
                    )
                else:
                    fallback.append(
                        f"No encontré ventas entre {period['date_from']} y {period['date_to']}; "
                        "no reemplacé el rango por otra fecha."
                    )
                continue

            if availability["status"] == "partial":
                fallback.extend([
                    "",
                    f"Datos disponibles solo hasta {availability['available_through']}; "
                    "el resto del período no está verificado.",
                ])

            unit_groups = (
                sorted({product["unidad_grupo"] for product in winners})
                if metric == "units" else [None]
            )
            for unit_group in unit_groups:
                group = [
                    product for product in winners
                    if unit_group is None or product["unidad_grupo"] == unit_group
                ]
                unit_label = group[0]["unidad"] if metric == "units" else None
                if unit_group and unit_group.startswith("UNKNOWN:"):
                    unit_label = f"medida no informada · SKU {group[0]['sku']}"
                fallback.extend([
                    "",
                    f"### {period['label'].capitalize()}"
                    + (f" · {unit_label}" if unit_label is not None else ""),
                ])
                if any(
                    sum(1 for item in group if item["rank"] == rank) < winner["tie_count"]
                    for winner in group
                    for rank in {winner["rank"]}
                ):
                    fallback.append(
                        "No se muestran todos los productos empatados por los límites de respuesta."
                    )
                for product in group:
                    total = f"${int(round(product['valor'])):,}".replace(",", ".")
                    fallback.append(
                        f"{product['rank']}. SKU {product['sku']} · {product['nombre']} · "
                        f"{product['unidades']:g} {product['unidad']} · {total} COP"
                    )
        if sales_cutoff:
            fallback.extend(["", f"Corte de ventas válidas: {sales_cutoff.isoformat()}."])
        return {
            "status": (
                "unavailable" if sales_cutoff is None
                else "partial" if any(
                    availability["status"] != "complete"
                    for availability in period_availability.values()
                ) or ranking_truncated
                else "complete" if products else "empty"
            ),
            "metric": metric,
            "ranking_result_count": ranked_result_count,
            "ranking_tie_capped_count": tie_capped_result_count,
            "ranking_truncated": ranking_truncated,
            "period_results": [
                {
                    **period,
                    **period_availability[int(period["period_id"])],
                    "productos": by_period.get(int(period["period_id"]), []),
                }
                for period in requested
            ],
            "productos": products,
            "respuesta_fallback": "\n".join(fallback),
            **metadata,
        }

    def get_productos_para_reponer(
        self,
        target_cover_days: int = 45,
        sales_window_days: int = 180,
        limit: int = 50,
        supplier_query: str | None = None,
    ) -> dict:
        """Return zero-stock SKUs with valid recent demand and a bounded coverage guide."""
        target_cover_days = int(target_cover_days)
        sales_window_days = int(sales_window_days)
        limit = int(limit)
        supplier_query = " ".join((supplier_query or "").split())
        if not 1 <= target_cover_days <= 365:
            raise ValueError("La cobertura objetivo debe estar entre 1 y 365 días.")
        if not 7 <= sales_window_days <= 365:
            raise ValueError("La ventana de ventas debe estar entre 7 y 365 días.")
        if not 1 <= limit <= 100:
            raise ValueError("El listado debe solicitar entre 1 y 100 productos.")
        if len(supplier_query) > 100 or any(ord(char) < 32 for char in supplier_query):
            raise ValueError("El filtro de proveedor debe tener hasta 100 caracteres válidos.")
        normalized_supplier_query = supplier_query.casefold()

        cutoff_cursor = query_cursor = None
        try:
            cutoff_cursor = self._con.cursor()
            cutoff_row = cutoff_cursor.execute(
                """
                SELECT
                    (SELECT MAX(snapshot_date) FROM silver_dim_producto)
                """
            ).fetchone()
            sales_cutoff = self._get_valid_sales_cutoff()
            inventory_cutoff = cutoff_row[0] if cutoff_row else None
            purchase_cutoff = self._get_valid_purchase_cutoff()
            if sales_cutoff is None or inventory_cutoff is None:
                raise LookupError("sales_or_inventory_cutoff_missing")
            sales_start = sales_cutoff - timedelta(days=sales_window_days - 1)
            query_cursor = self._con.cursor()
            rows = query_cursor.execute(
                """
                WITH valid_sales_headers AS (
                    SELECT * EXCLUDE (identity_count)
                    FROM (
                        SELECT h.business_date, h.cod_clase, h.num_documento,
                               COUNT(*) OVER (
                                   PARTITION BY h.business_date, h.cod_clase, h.num_documento
                               ) AS identity_count
                        FROM silver_fact_ventas h
                        WHERE UPPER(TRIM(COALESCE(h.estado_documento, ''))) != 'A'
                          AND h.business_date IS NOT NULL
                          AND h.business_date BETWEEN ? AND ?
                          AND TRIM(COALESCE(h.cod_clase, '')) != ''
                          AND TRIM(COALESCE(h.num_documento, '')) != ''
                    ) sales_headers
                    WHERE identity_count = 1
                ), demand AS (
                    SELECT d.cod_producto,
                           ROUND(SUM(COALESCE(d.cantidad, 0)), 2) AS units_sold,
                           ROUND(SUM(COALESCE(d.total_detalle, 0)), 2) AS revenue
                    FROM silver_fact_ventas_detalle d
                    INNER JOIN valid_sales_headers h
                        ON h.business_date = d.business_date
                       AND h.cod_clase = d.cod_clase
                       AND h.num_documento = d.num_documento
                     GROUP BY d.cod_producto
                    HAVING SUM(COALESCE(d.cantidad, 0)) > 0
                ), latest_products AS (
                    SELECT cod_producto, nombre_producto, existencia, cod_medida,
                           presentacion, snapshot_date, nit_proveedor
                    FROM (
                        SELECT p.cod_producto, p.nombre_producto, p.existencia,
                               p.cod_medida, p.presentacion, p.snapshot_date, p.nit_proveedor,
                               ROW_NUMBER() OVER (
                                   PARTITION BY p.cod_producto
                                   ORDER BY p.snapshot_date DESC,
                                            p.fecha_actualizacion DESC NULLS LAST
                               ) AS snapshot_rank
                        FROM silver_dim_producto p
                        WHERE p.snapshot_date = ?
                    ) ranked_products
                    WHERE snapshot_rank = 1
                ), zero_stock_skus AS (
                    SELECT p.cod_producto
                    FROM latest_products p
                    INNER JOIN demand d ON d.cod_producto = p.cod_producto
                    WHERE p.existencia IS NOT NULL AND p.existencia <= 0
                ), valid_purchase_headers AS (
                    SELECT * EXCLUDE (identity_count)
                    FROM (
                        SELECT h.business_date, h.cod_clase, h.num_documento,
                               h.nit_proveedor, h.nombre_proveedor,
                               COUNT(*) OVER (
                                   PARTITION BY h.business_date, h.cod_clase, h.num_documento
                               ) AS identity_count
                        FROM silver_fact_compras h
                        WHERE UPPER(TRIM(COALESCE(h.estado_documento, ''))) != 'A'
                          AND h.business_date IS NOT NULL
                          AND TRIM(COALESCE(h.cod_clase, '')) != ''
                          AND TRIM(COALESCE(h.num_documento, '')) != ''
                          AND h.business_date <= ?
                    ) purchase_headers
                    WHERE identity_count = 1
                ), latest_supplier AS (
                    SELECT cod_producto, nit_proveedor, nombre_proveedor
                    FROM (
                        SELECT d.cod_producto, TRIM(h.nit_proveedor) AS nit_proveedor,
                               TRIM(h.nombre_proveedor) AS nombre_proveedor,
                               ROW_NUMBER() OVER (
                                   PARTITION BY d.cod_producto
                                   ORDER BY h.business_date DESC, h.cod_clase DESC,
                                            h.num_documento DESC
                               ) AS supplier_rank
                        FROM silver_fact_compras_detalle d
                        INNER JOIN zero_stock_skus z ON z.cod_producto = d.cod_producto
                        INNER JOIN valid_purchase_headers h
                            ON h.business_date = d.business_date
                           AND h.cod_clase = d.cod_clase
                           AND h.num_documento = d.num_documento
                        WHERE h.nit_proveedor IS NOT NULL AND TRIM(h.nit_proveedor) != ''
                    ) ranked_suppliers
                    WHERE supplier_rank = 1
                ), candidates AS (
                    SELECT p.cod_producto AS sku,
                           COALESCE(NULLIF(TRIM(p.nombre_producto), ''), p.cod_producto) AS nombre,
                           p.existencia AS stock_actual,
                           COALESCE(NULLIF(TRIM(p.presentacion), ''), p.cod_medida, 'u') AS unidad,
                           d.units_sold AS unidades_vendidas,
                           d.revenue AS valor_vendido,
                           GREATEST(0, d.units_sold / ? * ? - p.existencia) AS cantidad_referencia,
                            COALESCE(
                                NULLIF(s.nombre_proveedor, ''), 'Proveedor por verificar'
                            ) AS proveedor,
                           COALESCE(s.nit_proveedor, p.nit_proveedor) AS nit_proveedor
                    FROM latest_products p
                    INNER JOIN demand d ON d.cod_producto = p.cod_producto
                    LEFT JOIN latest_supplier s ON s.cod_producto = p.cod_producto
                    WHERE p.existencia IS NOT NULL AND p.existencia <= 0
                )
                SELECT sku, nombre, stock_actual, unidad, unidades_vendidas,
                       valor_vendido, ROUND(cantidad_referencia, 2), proveedor, nit_proveedor
                FROM candidates
                WHERE cantidad_referencia > 0
                  AND (
                      ? = ''
                      OR contains(LOWER(COALESCE(proveedor, '')), LOWER(?))
                      OR contains(LOWER(COALESCE(nit_proveedor, '')), LOWER(?))
                  )
                ORDER BY cantidad_referencia DESC, valor_vendido DESC, sku ASC
                LIMIT ?
                """,
                [
                    sales_start,
                    sales_cutoff,
                    inventory_cutoff,
                    purchase_cutoff or sales_cutoff,
                    sales_window_days,
                    target_cover_days,
                    normalized_supplier_query,
                    normalized_supplier_query,
                    normalized_supplier_query,
                    limit,
                ],
            ).fetchall()
        except Exception as exc:
            logger.warning(
                "replenishment_query_failed tenant=%s error_type=%s",
                self.tenant,
                type(exc).__name__,
            )
            return {
                "status": "unavailable",
                "respuesta_fallback": (
                    "No pude verificar stock y demanda válidos. No voy a presentar "
                    "productos como faltantes sin confirmar inventario y ventas."
                ),
                "productos": [],
                "sources": [{
                    "source_id": "duckdb-replenishment", "domain": "inventory",
                    "kind": "duckdb", "citation": "DuckDB inventory, sales and purchase snapshots",
                    "cutoff_at": None, "status": "failed",
                }],
                "freshness": [{"domain": "inventory", "cutoff_at": None, "status": "unknown"}],
            }
        finally:
            for cursor in (cutoff_cursor, query_cursor):
                if cursor is not None and hasattr(cursor, "close"):
                    cursor.close()

        products = [
            {
                "sku": str(row[0]).strip(" \r\n\t"), "nombre": str(row[1]).strip(" \r\n\t"),
                "stock_actual": float(row[2]), "unidad": str(row[3] or "u").strip(),
                "unidades_vendidas": float(row[4]), "valor_vendido": float(row[5]),
                "cantidad_referencia": float(row[6]), "proveedor": str(row[7]).strip(" \r\n\t"),
                "nit_proveedor": str(row[8]).strip(" \r\n\t") if row[8] is not None else None,
            }
            for row in rows
        ]
        cutoffs = {
            "sales": sales_cutoff.isoformat(),
            "inventory": inventory_cutoff.isoformat(),
            "purchases": purchase_cutoff.isoformat() if purchase_cutoff else None,
        }
        observed_at = datetime.now(UTC).isoformat()
        sources = [{
            "source_id": f"duckdb-{domain}", "domain": domain, "kind": "duckdb",
            "citation": citation, "cutoff_at": cutoffs[domain], "observed_at": observed_at,
            "status": "used" if cutoffs[domain] else "failed",
        } for domain, citation in (
            ("sales", "Silver valid sales headers and detail"),
            ("inventory", "silver_dim_producto latest snapshot"),
            ("purchases", "Valid purchase headers for supplier attribution"),
        )]
        freshness = [{
            "domain": domain, "cutoff_at": cutoffs[domain], "observed_at": observed_at,
            "status": "current" if cutoffs[domain] else "unknown",
        } for domain in ("sales", "inventory", "purchases")]
        fallback_lines = [
            f"Candidatos a revisar por stock agotado · corte inventario {cutoffs['inventory']} · "
            f"corte ventas {cutoffs['sales']} · demanda de {sales_window_days} días."
        ]
        if supplier_query:
            fallback_lines[0] += f" Proveedor solicitado: {supplier_query}."
        if not products:
            fallback_lines.append(
                "No encontré productos con existencia cero/negativa y ventas positivas "
                f"en esa ventana{f' para {supplier_query}' if supplier_query else ''}."
            )
        for product in products:
            supplier = product["proveedor"]
            if product["nit_proveedor"]:
                supplier += f" (NIT: {product['nit_proveedor']})"
            fallback_lines.append(
                f"- SKU {product['sku']} · {product['nombre']}: stock "
                f"{product['stock_actual']:g} {product['unidad']}; ventas "
                f"{product['unidades_vendidas']:g} {product['unidad']} "
                f"en {sales_window_days} días; "
                f"referencia {product['cantidad_referencia']:g} {product['unidad']} "
                f"para {target_cover_days} días; proveedor: {supplier}."
            )
        fallback_lines.append(
            "La cantidad es una referencia por ventas válidas, no una orden: no incluye lead time, "
            "mínimos, órdenes abiertas, estacionalidad ni stock de seguridad."
        )
        return {
            "status": "complete" if products else "empty",
            "sales_cutoff": cutoffs["sales"], "inventory_cutoff": cutoffs["inventory"],
            "purchase_cutoff": cutoffs["purchases"],
            "sales_window_days": sales_window_days, "target_cover_days": target_cover_days,
            "productos": products, "count": len(products), "supplier_query": supplier_query or None,
            "respuesta_fallback": "\n".join(fallback_lines),
            "sources": sources, "freshness": freshness,
        }

    def get_productos_catalogo(
        self,
        abc: str = "A",
        window_days: int = 180,
        page: int = 1,
        page_size: int = 50,
        estado: str | None = None,
    ) -> dict:
        """List a bounded page from the same ABC/stock/action catalog as the UI."""
        abc = str(abc).strip().upper()
        window_days, page, page_size = int(window_days), int(page), int(page_size)
        if abc not in {"A", "B", "C"}:
            raise ValueError("La categoría ABC debe ser A, B o C.")
        if not 30 <= window_days <= 720:
            raise ValueError("La ventana del catálogo debe estar entre 30 y 720 días.")
        if not 1 <= page <= 1000 or not 1 <= page_size <= 50:
            raise ValueError("La página debe estar entre 1 y 1000 y el tamaño entre 1 y 50.")
        allowed_states = {
            "agotado", "quiebre", "sin_stock", "sobrestock", "dormido",
            "saludable", "sin_movimiento", "servicio",
        }
        estados = [item.strip() for item in estado.split(",")] if estado else []
        if any(item not in allowed_states for item in estados):
            raise ValueError("El estado del catálogo no es válido.")
        normalized_estado = ",".join(dict.fromkeys(estados)) or None

        try:
            from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

            repository = DuckDBMetricsRepo(db_path=self.duckdb_path, tenant=self.tenant)
            snapshot_context = getattr(repository, "product_snapshot_read", None)
            with snapshot_context() if callable(snapshot_context) else nullcontext():
                catalog = repository.get_product_analytics(
                    window_days=window_days,
                    page=page,
                    page_size=page_size,
                    q=None,
                    abc=abc,
                    estado=normalized_estado,
                    sort="revenue_win",
                    order="desc",
                    preset=None,
                    rotacion=None,
                )
            freshness_data = catalog.get("data_freshness")
            if not isinstance(freshness_data, dict):
                freshness_data = self.get_data_freshness()
        except Exception as exc:
            logger.warning(
                "catalog_product_list_failed tenant=%s error_type=%s",
                self.tenant,
                type(exc).__name__,
            )
            return {
                "status": "unavailable",
                "abc": abc,
                "window_days": window_days,
                "page": page,
                "page_size": page_size,
                "total": 0,
                "productos": [],
                "respuesta_fallback": (
                    "No pude verificar el catálogo ABC con stock y acciones. "
                    "No voy a sustituirlo por un Pareto resumido ni por una lista de reposición."
                ),
                "sources": [],
                "freshness": [],
            }

        total = int(catalog.get("total", 0) or 0)
        total_pages = max(1, math.ceil(total / page_size))
        source_dates = freshness_data.get("por_tabla", {})
        if isinstance(source_dates, dict) and source_dates:
            sales_cutoff = source_dates.get("silver_fact_ventas")
            purchase_cutoff = source_dates.get("silver_fact_compras")
            inventory_snapshot = source_dates.get("silver_dim_producto")
            source_generation = None
        else:
            sales_cutoff = freshness_data.get("sales_cutoff")
            purchase_cutoff = freshness_data.get("purchase_cutoff")
            inventory_snapshot = freshness_data.get("inventory_snapshot")
            source_generation = freshness_data.get("snapshot_generation")
        stock_source = freshness_data.get("stock_source") or (
            "catalog_snapshot" if self.tenant.casefold() == "masvital"
            else "purchases_minus_sales_estimate"
        )
        if page > total_pages:
            return {
                "status": "needs_clarification",
                "abc": abc,
                "window_days": window_days,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "productos": [],
                "respuesta_fallback": (
                    f"El catálogo ABC {abc} tiene {total} productos en esta ventana; "
                    f"solo hay páginas de 1 a {total_pages}."
                ),
                "sources": [],
                "freshness": [],
            }

        items = catalog.get("items", [])
        productos = [
            {
                "cod_producto": str(item.get("cod_producto", "")),
                "nombre": str(item.get("nombre", item.get("cod_producto", ""))),
                "abc": str(item.get("abc", "C")),
                "stock_actual": float(item.get("cantidad_actual") or 0),
                "unidades_win": float(item.get("unidades_win") or 0),
                "velocidad_mensual": float(item.get("velocidad_mensual") or 0),
                "dias_stock": (
                    float(item["dias_stock"]) if item.get("dias_stock") is not None else None
                ),
                "estado": str(item.get("estado", "sin_movimiento")),
                "accion": str(item.get("accion", "revisar")),
                "rank_rev": int(item["rank_rev"]) if item.get("rank_rev") is not None else None,
            }
            for item in items
            if isinstance(item, dict) and item.get("cod_producto")
        ]
        metadata = [
            {
                "source_id": "duckdb-product-catalog",
                "domain": "inventory",
                "kind": "duckdb",
                "citation": (
                    "Catalog snapshot and dynamic ABC, estado and action"
                    if stock_source == "catalog_snapshot"
                    else "Canonical product catalog and dynamic ABC, estado and action"
                ),
                "cutoff_at": inventory_snapshot,
                "status": "used" if inventory_snapshot else "unknown",
            },
            {
                "source_id": "duckdb-sales-abc-window",
                "domain": "sales",
                "kind": "duckdb",
                "citation": f"Valid sales detail for the {window_days}-day ABC window",
                "cutoff_at": sales_cutoff,
                "status": "used" if sales_cutoff else "unknown",
            },
        ]
        if stock_source != "catalog_snapshot":
            metadata.append({
                "source_id": "duckdb-purchase-stock-estimate",
                "domain": "purchases",
                "kind": "duckdb",
                "citation": "Valid historical purchase headers used to estimate current stock",
                "cutoff_at": purchase_cutoff,
                "status": "used" if purchase_cutoff else "unknown",
            })
        display_actions = {
            "reabastecer": "reabastecer",
            "liquidar": "liquidar",
            "revisar": "revisar",
            "ok": "no comprar ahora",
            "n/a": "no aplica",
        }
        display_states = {
            "agotado": "agotados",
            "quiebre": "por agotarse",
            "sin_stock": "sin stock",
            "sobrestock": "sobrestock",
            "dormido": "dormidos",
            "saludable": "saludables",
            "sin_movimiento": "sin movimiento",
            "servicio": "servicios",
        }
        filter_label = " o ".join(
            display_states.get(item, item) for item in normalized_estado.split(",")
        ) if normalized_estado else None
        state_suffix = f" · estado {filter_label}" if filter_label else ""
        fallback_lines = [
            f"Catálogo ABC {abc}{state_suffix} · ventas de los últimos {window_days} días · "
            f"página {page}/{total_pages} · {total} productos en total.",
            (
                f"Cortes: ventas {sales_cutoff or 'sin corte'} · "
                f"snapshot inventario {inventory_snapshot or 'sin snapshot'}."
                if stock_source == "catalog_snapshot"
                else "Stock estimado con compras hasta "
                f"{purchase_cutoff or 'sin corte'} menos ventas hasta {sales_cutoff or 'sin corte'}."
            ),
        ]
        if not productos:
            fallback_lines.append("No encontré productos en esa categoría y ventana.")
        for item in productos:
            days = f"{item['dias_stock']:g} días" if item["dias_stock"] is not None else "sin cobertura calculable"
            fallback_lines.append(
                f"- SKU {item['cod_producto']} · {item['nombre']}: "
                f"stock {item['stock_actual']:g}; vendido {item['unidades_win']:g} u; "
                f"velocidad {item['velocidad_mensual']:g}/mes; {days}; "
                f"estado {item['estado']}; acción {display_actions.get(item['accion'], 'revisar')}."
            )
        required_cutoffs_present = bool(sales_cutoff) and bool(
            inventory_snapshot if stock_source == "catalog_snapshot" else purchase_cutoff
        )
        return {
            "status": (
                "unavailable" if not required_cutoffs_present
                else "complete" if productos else "empty"
            ),
            "abc": abc,
            "window_days": window_days,
            "stock_source": (
                "catalog_snapshot" if self.tenant.casefold() == "masvital"
                else "purchases_minus_sales_estimate"
            ),
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "data_freshness": {
                "sales_cutoff": sales_cutoff,
                "purchase_cutoff": purchase_cutoff,
                "inventory_snapshot": inventory_snapshot,
                "snapshot_generation": source_generation,
                "stock_source": stock_source,
            },
            "has_more": page < total_pages,
            "next_page": page + 1 if page < total_pages else None,
            "productos": productos,
            "respuesta_fallback": "\n".join(fallback_lines),
            "sources": metadata,
            "freshness": [
                {
                    "domain": source["domain"],
                    "cutoff_at": source["cutoff_at"],
                    "status": "current" if source["cutoff_at"] else "unknown",
                }
                for source in metadata
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
            ("gold_mart_ventas_diarias_sku", "business_date", ""),
            ("gold_mart_inventario_actual", "snapshot_date", ""),
            ("silver_dim_producto", "snapshot_date", ""),
        )
        result: dict[str, str | None] = {}
        for table, col, where_clause in tables:
            try:
                row = self._con.execute(
                    f"SELECT MAX({col}) FROM {table} {where_clause}"
                ).fetchone()
                result[table] = row[0].isoformat() if row and row[0] else None
            except Exception:
                result[table] = None
        sales_cutoff = self._get_valid_sales_cutoff()
        result["silver_fact_ventas"] = sales_cutoff.isoformat() if sales_cutoff else None
        purchase_cutoff = self._get_valid_purchase_cutoff()
        result["silver_fact_compras"] = (
            purchase_cutoff.isoformat() if purchase_cutoff else None
        )
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
            WHERE num_documento = ? AND cod_clase = ? AND business_date = ?
            ORDER BY total_detalle DESC
            LIMIT 15
        """,
            [row[1], row[2], row[0]],
        ).fetchall()

        estado = str(row[6] or "").strip()
        result = {
            "fecha": row[0].isoformat(),
            "num_documento": row[1],
            "cod_clase": row[2],
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
            SELECT business_date, num_documento, cod_clase, nit_proveedor,
                   nombre_proveedor, total_factura, estado_documento
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
                    "cod_clase": r[2],
                    "nit_proveedor": r[3],
                    "proveedor": r[4],
                    "total_factura": float(r[5] or 0),
                    "estado_documento": str(r[6] or "").strip(),
                }
                for r in rows
            ],
            "count": len(rows),
        }
        return {**result, **self._purchase_metadata(rows[0][0])}

    def get_top_compras_periodos(
        self,
        periods: list[dict[str, str]],
        limit: int = 3,
        supplier_query: str | None = None,
        limit_capped: bool = False,
    ) -> dict:
        """Rank invoices by total independently within each calendar month."""
        return self._query_purchase_periods(
            periods, view="top", limit=limit, page=1, supplier_query=supplier_query,
            limit_capped=limit_capped,
        )

    def get_compras_periodo(
        self,
        periods: list[dict[str, str]],
        view: str = "list",
        limit: int = 50,
        page: int = 1,
        supplier_query: str | None = None,
    ) -> dict:
        """Summarize or page through tenant purchase invoices for calendar months."""
        if view not in {"list", "summary"}:
            raise ValueError("La vista debe ser list o summary.")
        return self._query_purchase_periods(
            periods, view=view, limit=limit, page=page, supplier_query=supplier_query
        )

    def _query_purchase_periods(
        self,
        periods: list[dict[str, str]],
        *,
        view: str,
        limit: int,
        page: int,
        supplier_query: str | None,
        limit_capped: bool = False,
    ) -> dict:
        if periods == []:
            clarification = (
                "No tengo un corte válido de compras para inferir el año; indicame el año."
                if self._get_valid_purchase_cutoff() is None
                else "¿De qué mes y año querés consultar las compras?"
            )
            return {
                "status": "needs_clarification",
                "respuesta_fallback": clarification,
                "compras": [],
                "sources": [],
                "freshness": [],
            }
        if not isinstance(periods, list) or not 1 <= len(periods) <= 6:
            raise ValueError("Indicá entre uno y seis meses calendario.")
        limit, page = int(limit), int(page)
        max_limit = 20 if view == "top" else 50
        if not 1 <= limit <= max_limit or not 1 <= page <= 1000:
            raise ValueError("El límite o la página están fuera del rango permitido.")
        if view != "list" and page != 1:
            raise ValueError("La vista solicitada no admite paginación.")
        if limit_capped and view != "top":
            raise ValueError("La notificación de límite solo aplica a rankings de compras.")
        if view != "top" and len(periods) * limit > 100:
            raise ValueError("El listado está limitado a cien facturas por respuesta.")

        month_names = (
            "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        )
        normalized = []
        seen_months: set[str] = set()
        for period in periods:
            if not isinstance(period, dict):
                raise ValueError("Cada período debe ser un mes calendario completo.")
            try:
                start = date.fromisoformat(str(period.get("date_from", "")))
                end = date.fromisoformat(str(period.get("date_to", "")))
            except ValueError as exc:
                raise ValueError("Las fechas deben usar YYYY-MM-DD.") from exc
            next_month = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
            if (
                start.day != 1
                or (start.year, start.month) != (end.year, end.month)
                or end.day != (next_month - timedelta(days=1)).day
            ):
                raise ValueError("Cada período debe cubrir un mes calendario completo.")
            month = start.strftime("%Y-%m")
            if month in seen_months:
                raise ValueError("No repitas el mismo mes en una consulta.")
            seen_months.add(month)
            normalized.append({
                "month": month,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "label": f"{month_names[start.month - 1]} {start.year}",
            })

        if supplier_query is not None:
            supplier_query = str(supplier_query).strip()
            if len(supplier_query) > 100 or any(ord(char) < 32 for char in supplier_query):
                raise ValueError("El filtro de proveedor debe tener hasta 100 caracteres válidos.")
            terms = [term for term in supplier_query.split() if term]
            if terms and terms[0].casefold() in {"nit", "rut"}:
                terms = terms[1:]
            if len(terms) > 10:
                raise ValueError("Usá hasta diez palabras para buscar el proveedor.")
        else:
            terms = []

        header_date_filters = [
            "(h.business_date >= ? AND h.business_date <= ?)" for _ in normalized
        ]
        month_parameters = [
            value
            for period in normalized
            for value in (period["date_from"], period["date_to"])
        ]
        supplier_filter = "".join(
            " AND (POSITION(LOWER(?) IN LOWER(COALESCE(nombre_proveedor, ''))) > 0 "
            "OR POSITION(LOWER(?) IN LOWER(COALESCE(nit_proveedor, ''))) > 0)"
            for _ in terms
        )
        supplier_parameters = [term for term in terms for _ in range(2)]
        valid_headers = f"""
            SELECT * EXCLUDE (identity_count)
            FROM (
                SELECT h.*,
                       COUNT(*) OVER (
                           PARTITION BY h.business_date, h.cod_clase, h.num_documento
                       ) AS identity_count
                FROM silver_fact_compras h
                WHERE UPPER(TRIM(COALESCE(h.estado_documento, ''))) != 'A'
                  AND h.business_date IS NOT NULL
                  AND h.cod_clase = TRIM(COALESCE(h.cod_clase, ''))
                  AND h.num_documento = TRIM(COALESCE(h.num_documento, ''))
                  AND h.cod_clase != '' AND h.num_documento != ''
                  AND ({' OR '.join(header_date_filters)})
            ) ranked_headers
            WHERE identity_count = 1
        """
        summary_query = f"""
            WITH valid_headers AS ({valid_headers})
            SELECT strftime(business_date, '%Y-%m') AS month,
                   COUNT(*) AS invoice_count,
                   ROUND(COALESCE(SUM(total_factura), 0), 2) AS total_compras
            FROM valid_headers
            WHERE TRUE{supplier_filter}
            GROUP BY month
        """
        sort_order = (
            "total_factura DESC NULLS LAST, business_date DESC, cod_clase, num_documento"
            if view == "top"
            else "business_date DESC, cod_clase, num_documento"
        )
        details_query = f"""
            WITH valid_headers AS ({valid_headers}), ranked AS (
                SELECT CAST(business_date AS VARCHAR) AS business_date,
                       cod_clase, num_documento, nit_proveedor, nombre_proveedor,
                       total_factura, COALESCE(estado_documento, '') AS estado_documento,
                       strftime(business_date, '%Y-%m') AS month,
                       ROW_NUMBER() OVER (
                           PARTITION BY date_trunc('month', business_date)
                           ORDER BY {sort_order}
                       ) AS month_rank
                FROM valid_headers
                WHERE TRUE{supplier_filter}
            )
            SELECT business_date, cod_clase, num_documento, nit_proveedor,
                   nombre_proveedor, total_factura, estado_documento, month, month_rank
            FROM ranked
            WHERE month_rank > ? AND month_rank <= ?
            ORDER BY month, month_rank
        """
        offset = (page - 1) * limit if view == "list" else 0
        summary_cursor = detail_cursor = None
        try:
            cutoff = self._get_valid_purchase_cutoff()
            summary_cursor = self._con.cursor()
            summary_rows = summary_cursor.execute(
                summary_query, [*month_parameters, *supplier_parameters]
            ).fetchall()
            rows = []
            if view != "summary":
                detail_cursor = self._con.cursor()
                rows = detail_cursor.execute(
                    details_query,
                    [*month_parameters, *supplier_parameters, offset, offset + limit],
                ).fetchall()
        except Exception as exc:
            logger.warning(
                "purchase_period_query_failed tenant=%s error_type=%s",
                self.tenant,
                type(exc).__name__,
            )
            return {
                "status": "unavailable",
                "respuesta_fallback": (
                    "No pude consultar las compras del período. La fuente no respondió; "
                    "no voy a reemplazarla por compras recientes ni pedirte proveedores al azar."
                ),
                "compras": [],
                "sources": [{
                    "source_id": "duckdb-purchases", "domain": "purchases", "kind": "duckdb",
                    "citation": "DuckDB purchases snapshot", "cutoff_at": None, "status": "failed",
                }],
                "freshness": [{"domain": "purchases", "cutoff_at": None, "status": "unknown"}],
            }
        finally:
            for cursor in (summary_cursor, detail_cursor):
                if cursor is not None and hasattr(cursor, "close"):
                    cursor.close()

        summaries = {
            str(row[0]): {"invoice_count": int(row[1] or 0), "total_compras": float(row[2] or 0)}
            for row in summary_rows
        }
        purchases = [
            {
                "business_date": str(row[0]), "fecha": str(row[0]), "cod_clase": str(row[1]),
                "num_documento": str(row[2]),
                "nit_proveedor": str(row[3]).strip() if row[3] is not None else None,
                "proveedor": str(row[4]).strip() if row[4] is not None else None,
                "total_factura": float(row[5] or 0), "estado_documento": str(row[6]).strip(),
                "month": str(row[7]), "rank": int(row[8]),
            }
            for row in rows
        ]
        grouped: dict[str, list[dict]] = {}
        for purchase in purchases:
            grouped.setdefault(purchase["month"], []).append(purchase)
        cutoff_date = date.fromisoformat(cutoff.isoformat()) if cutoff else None
        metadata = self._purchase_metadata(cutoff_date)
        period_availability: dict[str, dict[str, str | None]] = {}
        for period in normalized:
            start = date.fromisoformat(period["date_from"])
            end = date.fromisoformat(period["date_to"])
            if cutoff_date is None or start > cutoff_date:
                period_availability[period["month"]] = {
                    "status": "unavailable", "available_through": None,
                }
            elif end > cutoff_date:
                period_availability[period["month"]] = {
                    "status": "partial", "available_through": cutoff_date.isoformat(),
                }
            else:
                period_availability[period["month"]] = {
                    "status": "complete", "available_through": end.isoformat(),
                }
        fallback = [
            "Resumen de compras por mes:"
            if view == "summary"
            else f"Top {limit} facturas por monto:"
            if view == "top"
            else "Compras registradas en el período:"
        ]
        if limit_capped:
            fallback.append(
                "La solicitud superaba el límite permitido; muestro hasta 20 compras por mes."
            )
        for period in normalized:
            summary = summaries.get(period["month"], {"invoice_count": 0, "total_compras": 0})
            availability = period_availability[period["month"]]
            if view == "summary":
                if availability["status"] == "unavailable":
                    fallback.append(
                        f"{period['label'].capitalize()}: no puedo verificar este período; "
                        "empieza después del último corte válido de compras "
                        f"({cutoff_date.isoformat() if cutoff_date else 'sin corte disponible'})."
                    )
                    continue
                total = f"${int(round(summary['total_compras'])):,}".replace(",", ".")
                summary_line = (
                    f"{period['label'].capitalize()}: "
                    + (f"sí, {summary['invoice_count']} facturas por {total} COP."
                       if summary["invoice_count"] else "no encontré compras válidas.")
                )
                if availability["status"] == "partial":
                    summary_line += (
                        f" Datos disponibles hasta {availability['available_through']}; "
                        "los días posteriores no están verificados."
                    )
                fallback.append(summary_line)
                continue
            fallback.extend(["", f"### {period['label'].capitalize()}"])
            if availability["status"] == "unavailable":
                fallback.append(
                    "No puedo verificar este período: empieza después del último corte válido "
                    f"de compras ({cutoff_date.isoformat() if cutoff_date else 'sin corte disponible'})."
                )
                continue
            if availability["status"] == "partial":
                fallback.append(
                    f"Datos disponibles hasta {availability['available_through']}; "
                    "el resto del período no está verificado."
                )
            month_purchases = grouped.get(period["month"], [])
            if not month_purchases:
                if availability["status"] == "partial":
                    fallback.append(
                        f"No encontré compras válidas hasta {availability['available_through']}; "
                        "los días posteriores no están verificados."
                    )
                else:
                    fallback.append(
                        "No encontré compras válidas para este mes."
                        if not summary["invoice_count"]
                        else f"No hay más facturas en esta página; el período tiene {summary['invoice_count']}."
                    )
                continue
            if view == "list":
                fallback.append(
                    f"Mostrando {len(month_purchases)} de {summary['invoice_count']} facturas (página {page})."
                )
            for purchase in month_purchases:
                total = f"${int(round(purchase['total_factura'])):,}".replace(",", ".")
                supplier = purchase["proveedor"] or "Proveedor sin nombre"
                if purchase["nit_proveedor"]:
                    supplier += f" (NIT: {purchase['nit_proveedor']})"
                prefix = f"{purchase['rank']}. " if view == "top" else "- "
                fallback.append(
                    f"{prefix}Documento: {purchase['num_documento']} · Clase: {purchase['cod_clase']} · "
                    f"Fecha: {purchase['business_date']} · Proveedor: {supplier} · Total: {total} COP"
                )
        if cutoff_date:
            fallback.extend(["", f"Corte de compras: {cutoff_date.isoformat()}."])
        total_count = sum(summary["invoice_count"] for summary in summaries.values())
        has_incomplete_period = any(
            availability["status"] != "complete"
            for availability in period_availability.values()
        )
        return {
            "status": (
                "unavailable" if cutoff_date is None
                else "partial" if has_incomplete_period
                else "complete" if total_count else "empty"
            ),
            "view": view,
            "period_results": [
                {
                    **period,
                    **period_availability[period["month"]],
                    **summaries.get(period["month"], {"invoice_count": 0, "total_compras": 0}),
                    "compras": grouped.get(period["month"], []) if view != "summary" else [],
                    "paginacion": {
                        "page": page, "page_size": limit,
                        "total_documentos": summaries.get(period["month"], {"invoice_count": 0})["invoice_count"],
                        "has_more": page * limit < summaries.get(period["month"], {"invoice_count": 0})["invoice_count"],
                    },
                }
                for period in normalized
            ],
            "compras": purchases if view != "summary" else [],
            "count": total_count,
            "supplier_query": supplier_query,
            "limit_capped": limit_capped,
            "page": page,
            "page_size": limit,
            "respuesta_fallback": "\n".join(fallback),
            **metadata,
        }

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
                    "cod_clase": r[2],
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

        requested_codigo = str(codigo or "").strip()
        if not requested_codigo:
            return {"error": "Indicá el código o el nombre del producto a consultar."}
        codigo = requested_codigo

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
            [requested_codigo],
        ).fetchone()
        resolution = None
        if not prod:
            matches = self.search_products(requested_codigo, limit=8)
            if matches.get("productos") and not matches.get("ambiguo"):
                codigo = matches["productos"][0]["codigo"]
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
                resolution = {
                    "consulta": requested_codigo,
                    "codigo_resuelto": codigo,
                    "nombre_resuelto": prod[1] if prod else None,
                }
            elif matches.get("productos"):
                return {
                    "ambiguo": True,
                    "consulta": requested_codigo,
                    "mensaje": (
                        f"Hay {matches['total']} productos que coinciden con "
                        f"'{requested_codigo}'. Pedí el modelo de moto o el código SKU."
                    ),
                    "coincidencias": matches["productos"],
                }
            else:
                return {"error": f"Producto '{requested_codigo}' no encontrado en el catálogo."}
        if not prod:
            return {"error": f"Producto '{requested_codigo}' no encontrado en el catálogo."}

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
            **({"resolucion_busqueda": resolution} if resolution else {}),
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
            "metricas_operativas_disponibles": False,
            "metricas_operativas_mensaje": (
                "No se pudieron calcular las métricas operativas del dashboard; "
                "los valores de catálogo e historial pueden consultarse, pero no "
                "deben interpretarse como la ficha operativa completa."
            ),
        }
        # Reutilizar el cálculo canónico del dashboard evita que el asistente
        # informe stock, costos o estados distintos a los de la ficha web.
        try:
            from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

            dashboard_detail = DuckDBMetricsRepo(
                db_path=self.duckdb_path,
                tenant=self.tenant,
            ).get_product_detail(codigo, window_days)
        except Exception as exc:
            logger.warning(
                "product_metrics_unavailable tenant=%s codigo=%s error_type=%s",
                self.tenant,
                codigo,
                type(exc).__name__,
            )
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
                "metricas_operativas_disponibles": True,
                "metricas_operativas_mensaje": "Métricas calculadas con la misma fuente del dashboard.",
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
        cod_clase: str = "",
    ) -> dict:
        """Detalle resumido y consultable de productos de una compra específica."""
        limit = max(1, min(int(limit), 100))
        # Never choose an arbitrary class/date when a document number is reused.
        where = ["num_documento = ?", "UPPER(TRIM(COALESCE(estado_documento, ''))) != 'A'"]
        params = [num_documento]
        if fecha:
            where.append("business_date = ?")
            params.append(fecha)
        if cod_clase:
            where.append("cod_clase = ?")
            params.append(cod_clase)
        rows = self._con.execute(
            f"""
            SELECT business_date, num_documento, cod_clase, nombre_proveedor,
                   nit_proveedor, total_factura, estado_documento
            FROM silver_fact_compras
            WHERE {' AND '.join(where)}
            ORDER BY business_date DESC, cod_clase ASC
            LIMIT 2
            """,
            params,
        ).fetchall()

        if not rows:
            return {"error": f"No se encontró la compra '{num_documento}' (fecha: {fecha or 'cualquiera'})."}
        if len(rows) > 1:
            return {
                "error": (
                    f"El número '{num_documento}' identifica más de un documento. "
                    "Indicá la fecha y el código de clase para desambiguarlo."
                ),
                "ambiguo": True,
            }
        compra = rows[0]

        # Obtener detalles de productos
        todos_los_detalles = self._con.execute(
            """
            SELECT cod_producto, nombre_detalle, cantidad, valor_unitario,
                   total_detalle, costo_producto
            FROM silver_fact_compras_detalle
            WHERE num_documento = ? AND cod_clase = ? AND business_date = ?
            ORDER BY total_detalle DESC
            """,
            [num_documento, compra[2], compra[0]],
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
                "cod_clase": compra[2],
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

    def analizar_compras_periodo(
        self,
        date_from: str,
        date_to: str,
        target_cover_days: int = 45,
        limit: int = 30,
    ) -> dict:
        """Audit purchased SKUs against prior demand, current stock, and post-buy movement."""
        from motoshop_api.llm.purchase_analysis import analyze_purchase_period

        # MasVital's R2 gold inventory mart is contaminated by retail-price
        # values in the quantity field; its dimension existence matches the
        # recorded physical counts and is the usable inventory snapshot.
        inventory_source = "catalog" if self.tenant.casefold() == "masvital" else "gold"
        return _json_safe(analyze_purchase_period(
            self._con,
            date_from,
            date_to,
            target_cover_days=target_cover_days,
            limit=limit,
            inventory_source=inventory_source,
        ))

    def evaluar_compra_planeada(
        self,
        items: list[dict],
        target_cover_days: int = 45,
        sales_window_days: int = 180,
    ) -> dict:
        """Compare a proposed order with recent sales velocity and current stock."""
        from motoshop_api.llm.purchase_analysis import evaluate_planned_purchase

        if not isinstance(items, list) or not items:
            raise ValueError("Indicá productos con código o nombre y cantidad planeada.")
        if len(items) > 50:
            raise ValueError("Se pueden evaluar hasta 50 productos por consulta.")

        normalized = []
        unresolved = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                unresolved.append({"linea": index, "error": "La línea debe ser un objeto con producto y cantidad."})
                continue
            code_or_name = str(
                item.get("codigo")
                or item.get("sku")
                or item.get("producto")
                or item.get("nombre")
                or ""
            ).strip()
            if not code_or_name:
                unresolved.append({"linea": index, "error": "Falta el código o nombre del producto."})
                continue
            try:
                quantity = float(item.get("cantidad"))
                if not math.isfinite(quantity) or quantity < 0:
                    raise ValueError
            except (TypeError, ValueError):
                unresolved.append({
                    "linea": index,
                    "consulta": code_or_name,
                    "error": "La cantidad debe ser un número mayor o igual a cero.",
                })
                continue

            exact = self._con.execute(
                "SELECT cod_producto, nombre_producto FROM silver_dim_producto WHERE cod_producto = ?",
                [code_or_name],
            ).fetchone()
            if exact:
                normalized.append({
                    "codigo": exact[0], "nombre": exact[1], "cantidad": quantity,
                })
                continue

            matches = self.search_products(code_or_name, limit=8)
            candidates = matches.get("productos", [])
            if not candidates:
                unresolved.append({
                    "linea": index, "consulta": code_or_name,
                    "error": "No se encontró el producto en el catálogo.",
                })
            elif matches.get("ambiguo"):
                unresolved.append({
                    "linea": index,
                    "consulta": code_or_name,
                    "error": "Hay varias coincidencias; indicá el modelo de moto o el SKU.",
                    "coincidencias": [
                        {"codigo": candidate["codigo"], "nombre": candidate["nombre"]}
                        for candidate in candidates[:5]
                    ],
                })
            else:
                normalized.append({
                    "codigo": candidates[0]["codigo"],
                    "nombre": candidates[0]["nombre"],
                    "cantidad": quantity,
                    "consulta_original": code_or_name,
                })

        if unresolved:
            return {
                "status": "needs_clarification",
                "mensaje": "No evalué la compra completa porque hay líneas que necesitan corrección o desambiguación.",
                "lineas_pendientes": unresolved,
                "sources": [],
                "freshness": [],
            }

        # Combine repeated SKU lines so the recommendation compares against the
        # total requested quantity rather than scoring duplicate rows separately.
        grouped: dict[str, dict] = {}
        for item in normalized:
            if item["codigo"] not in grouped:
                grouped[item["codigo"]] = item.copy()
                grouped[item["codigo"]]["lineas_originales"] = 1
            else:
                grouped[item["codigo"]]["cantidad"] += item["cantidad"]
                grouped[item["codigo"]]["lineas_originales"] += 1

        inventory_source = "catalog" if self.tenant.casefold() == "masvital" else "gold"
        return _json_safe(evaluate_planned_purchase(
            self._con,
            list(grouped.values()),
            target_cover_days=target_cover_days,
            sales_window_days=sales_window_days,
            inventory_source=inventory_source,
        ))

    def get_analisis_modulo(
        self,
        date_from: str = "",
        date_to: str = "",
        sections: list[str] | None = None,
        product_limit: int = 10,
    ) -> dict:
        """Return bounded canonical context for the dashboard Analysis tabs."""
        from datetime import date

        from motoshop_api.llm.analysis_context import build_analysis_context
        from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

        requested_sections = list(sections) if sections is not None else None
        tenant_context = getattr(self, "tenant_context", None)
        if tenant_context is not None:
            allowed_domains = set(tenant_context.allowed_domains)
            if "analyses" not in allowed_domains:
                if "forecasts" not in allowed_domains:
                    return {
                        "status": "unavailable",
                        "mensaje": "No tenés permiso para consultar el módulo Análisis.",
                        "sections": {},
                        "sources": [],
                        "freshness": [],
                    }
                if requested_sections and set(requested_sections) - {"proyeccion"}:
                    return {
                        "status": "needs_clarification",
                        "mensaje": "Tu acceso permite consultar la proyección mensual, no las demás pestañas de Análisis.",
                        "sections": {},
                        "sources": [],
                        "freshness": [],
                    }
                requested_sections = ["proyeccion"]

        latest_sales_date = self._get_max_date()
        if latest_sales_date is None:
            return {
                "status": "empty",
                "tenant": self.tenant,
                "mensaje": "No hay datos de ventas para explicar el módulo Análisis.",
                "sections": {},
                "sources": [],
                "freshness": [],
            }
        try:
            end = date.fromisoformat(date_to) if date_to else latest_sales_date
            start = date.fromisoformat(date_from) if date_from else end.replace(day=1)
        except ValueError as exc:
            raise ValueError("date_from y date_to deben estar en formato YYYY-MM-DD.") from exc
        if start > end:
            raise ValueError("date_from debe ser anterior o igual a date_to.")

        requested_end = end
        end = min(end, latest_sales_date)
        if start > end:
            return {
                "status": "empty",
                "tenant": self.tenant,
                "period": {"from": start.isoformat(), "to": end.isoformat()},
                "mensaje": "El rango solicitado está después del último día con ventas disponibles.",
                "sections": {},
                "sources": [],
                "freshness": [],
            }

        result = build_analysis_context(
            DuckDBMetricsRepo(db_path=self.duckdb_path, tenant=self.tenant),
            self._con,
            self.tenant,
            date_from=start.isoformat(),
            date_to=end.isoformat(),
            sections=requested_sections,
            product_limit=product_limit,
        )
        result["period"]["requested_to"] = requested_end.isoformat()
        result["period"]["truncated_to_available_data"] = requested_end > end
        if requested_end > end:
            result["period_note"] = (
                f"El rango se limita al último corte de ventas disponible ({end.isoformat()})."
            )
            result["respuesta_fallback"] += f"\n{result['period_note']}"
        return _json_safe(result)

    def get_cash_closure(self, date: str = "") -> dict:
        """Cierre de caja del día: ventas totales, número de facturas, desglose por forma de pago (efectivo, tarjetas, transferencias) y top 5 facturas."""
        from datetime import UTC, datetime
        from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

        target_date = date.strip() if date else ""
        if not target_date:
            max_date = self._get_max_date()
            if not max_date:
                return {
                    "status": "empty",
                    "mensaje": "No hay datos de ventas disponibles para consultar el cierre de caja.",
                    "sources": [],
                    "freshness": [],
                    "respuesta_fallback": "No hay datos de ventas disponibles para consultar el cierre de caja.",
                }
            target_date = max_date.isoformat()

        repo = DuckDBMetricsRepo(db_path=self.duckdb_path, tenant=self.tenant)
        data = repo.get_cash_closure(target_date)

        formas = data.get("formas_pago", [])
        total_dia = float(data.get("total_dia") or 0.0)
        total_facturas = int(data.get("total_facturas") or 0)

        lines = [
            f"Cierre de caja de {self.tenant} para el {target_date}:",
            f"- Total vendido: ${total_dia:,.0f} COP ({total_facturas} facturas).",
        ]
        if formas:
            lines.append("")
            lines.append("| Forma de pago | Facturas | Total ventas ($ COP) | % del día | Ticket promedio ($ COP) |")
            lines.append("| :--- | ---: | ---: | ---: | ---: |")
            for f in formas:
                lines.append(
                    f"| {f.get('nombre', '—')} | {f.get('num_facturas', 0)} | "
                    f"${float(f.get('total_ventas') or 0):,.0f} | {f.get('porcentaje', 0)}% | "
                    f"${float(f.get('ticket_promedio') or 0):,.0f} |"
                )

        top_grandes = data.get("top_facturas_grandes", [])
        if top_grandes:
            lines.append("")
            lines.append(f"Top {len(top_grandes)} facturas destacadas del día:")
            for item in top_grandes:
                lines.append(
                    f"- Factura {item.get('num_documento')}: ${float(item.get('total') or 0):,.0f} "
                    f"({item.get('nombre_formapago', '—')}) a {item.get('cliente', '—')} "
                    f"a las {item.get('hora', '—')}"
                )

        observed_at = datetime.now(UTC).isoformat()
        sources = [{
            "source_id": f"duckdb-cash-closure-{self.tenant}",
            "domain": "sales",
            "kind": "duckdb",
            "citation": f"Silver ventas del día {target_date}",
            "cutoff_at": target_date,
            "status": "used",
        }]
        freshness = [{
            "domain": "sales",
            "cutoff_at": target_date,
            "observed_at": observed_at,
            "status": "current",
        }]

        return {
            "status": "complete",
            "date": target_date,
            "total_dia": total_dia,
            "total_facturas": total_facturas,
            "formas_pago": formas,
            "top_facturas_grandes": top_grandes,
            "sources": sources,
            "freshness": freshness,
            "respuesta_fallback": "\n".join(lines),
        }

    def get_expiry_alerts(self, days: int = 90) -> dict:
        """Semáforo y alertas de lotes de productos próximos a vencer o vencidos (MasVital)."""
        from datetime import UTC, date, datetime, timedelta
        from motoshop_api.expiry.repo import get_expiry_lots_repo

        if self.tenant != "masvital":
            return {
                "status": "unavailable",
                "mensaje": "El control de lotes y fechas de vencimiento está habilitado únicamente para MasVital.",
                "sources": [],
                "freshness": [],
                "respuesta_fallback": "El control de lotes y fechas de vencimiento está disponible exclusivamente para MasVital.",
            }

        horizon_days = max(1, min(int(days or 90), 730))
        repo = get_expiry_lots_repo()
        today = date.today()
        expires_before = today + timedelta(days=horizon_days)

        try:
            alerts = repo.list_alerts(tenant=self.tenant, expires_before=expires_before)
        except Exception as exc:
            logger.warning("expiry_alerts_failed tenant=%s error_type=%s", self.tenant, type(exc).__name__)
            return {
                "status": "unavailable",
                "mensaje": "No se pudieron consultar los lotes de vencimiento.",
                "sources": [],
                "freshness": [],
                "respuesta_fallback": "La fuente de lotes de vencimiento no está disponible temporalmente.",
            }

        items = []
        for item in alerts:
            exp_date = date.fromisoformat(item["expires_on"])
            days_left = (exp_date - today).days
            items.append({
                **item,
                "days_until_expiry": days_left,
                "urgencia": "vencido" if days_left < 0 else ("critico" if days_left <= 30 else "alerta"),
            })

        lines = [f"Reporte de lotes y vencimientos de {self.tenant} (horizonte {horizon_days} días):"]
        if not items:
            lines.append("No se registran lotes por vencer en el período consultado.")
        else:
            vencidos = sum(1 for i in items if i["days_until_expiry"] < 0)
            por_vencer = len(items) - vencidos
            lines.append(f"- Total lotes en alerta: {len(items)} ({vencidos} ya vencidos, {por_vencer} por vencer).")
            lines.append("")
            lines.append("| SKU | Producto | Lote | Vencimiento | Días restantes | Estado | Stock |")
            lines.append("| :--- | :--- | :--- | :--- | ---: | :--- | ---: |")
            for i in items[:25]:
                stock = i.get("units_remaining", i.get("initial_units", 0))
                lines.append(
                    f"| {i.get('product_sku', '—')} | {i.get('product_name', '—')} | "
                    f"{i.get('lot_number', '—')} | {i.get('expires_on', '—')} | "
                    f"{i.get('days_until_expiry', 0)} d | {i.get('urgencia', '—')} | {stock:,.0f} |"
                )

        observed_at = datetime.now(UTC).isoformat()
        sources = [{
            "source_id": f"supabase-expiry-{self.tenant}",
            "domain": "expiry",
            "kind": "supabase",
            "citation": f"Lotes con vencimiento antes de {expires_before.isoformat()}",
            "cutoff_at": today.isoformat(),
            "status": "used",
        }]
        freshness = [{
            "domain": "expiry",
            "cutoff_at": today.isoformat(),
            "observed_at": observed_at,
            "status": "current",
        }]

        return {
            "status": "complete",
            "horizon_days": horizon_days,
            "total_lotes": len(items),
            "items": items,
            "sources": sources,
            "freshness": freshness,
            "respuesta_fallback": "\n".join(lines),
        }

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
        top_match_is_ambiguous = (
            len(scored_rows) > 1 and scored_rows[0][0] - scored_rows[1][0] <= 0.05
        )
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
                    "similitud": round(score, 3),
                }
                for score, r in scored_rows[:limit]
            ],
            "total": len(matches),
            "ambiguo": top_match_is_ambiguous,
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
            "name": "get_top_productos_periodo",
            "description": (
                "Rankea productos por ventas en rangos de fecha exactos o meses calendario. "
                "'Más vendido' significa unidades, salvo pedido explícito por valor facturado. "
                "Al rankear unidades, compara por separado cada medida del catálogo y conserva "
                "los SKU empatados; no compara, por ejemplo, gramos con unidades. Devuelve cada "
                "período por separado, filtra ventas anuladas y nunca reemplaza un día sin ventas "
                "por el último día disponible."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "periods": {
                        "type": "array", "minItems": 1, "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "date_from": {"type": "string", "description": "Inicio inclusivo YYYY-MM-DD."},
                                "date_to": {"type": "string", "description": "Fin inclusivo YYYY-MM-DD."},
                                "label": {"type": "string", "description": "Etiqueta de período."},
                            },
                            "required": ["date_from", "date_to"],
                        },
                    },
                    "metric": {"type": "string", "enum": ["units", "revenue"], "default": "units"},
                    "limit": {
                        "type": "integer", "default": 1, "minimum": 1, "maximum": 20,
                        "description": "Posiciones a devolver por período y por medida de catálogo.",
                    },
                },
                "required": ["periods"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_productos_para_reponer",
            "description": (
                "Shortlist de productos con stock cero/negativo en el último snapshot y ventas "
                "válidas positivas en la ventana solicitada. La cantidad es una referencia de "
                "cobertura, no una orden, y no conoce compras abiertas ni lead time. Requiere "
                "permisos de compras, ventas e inventario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_cover_days": {"type": "integer", "default": 45, "minimum": 1, "maximum": 365},
                    "sales_window_days": {"type": "integer", "default": 180, "minimum": 7, "maximum": 365},
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
                    "supplier_query": {
                        "type": "string", "maxLength": 100,
                        "description": "Opcional: limitar al proveedor o NIT conocido más reciente por SKU.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_productos_catalogo",
            "description": (
                "Lista una página acotada del catálogo filtrado por categoría ABC, "
                "con stock, días de cobertura, velocidad, estado y acción sugerida. "
                "Usa la misma clasificación dinámica de 180 días que la pantalla Catálogo. "
                "Para productos A con stock y acción, usa esta tool; no la reemplaces por "
                "un resumen Pareto ni por la lista de productos agotados para reponer. "
                "Devuelve hasta 50 productos por página y el total disponible."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "abc": {"type": "string", "enum": ["A", "B", "C"], "default": "A"},
                    "window_days": {"type": "integer", "default": 180, "minimum": 30, "maximum": 720},
                    "page": {"type": "integer", "default": 1, "minimum": 1, "maximum": 1000},
                    "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 50},
                    "estado": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Opcional: estados explícitos solicitados, separados por coma.",
                    },
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
            "name": "get_top_compras_periodos",
            "description": (
                "Rankea compras por total de factura dentro de cada mes solicitado; excluye "
                "anuladas e identidades duplicadas. Acepta filtro opcional por nombre parcial o NIT "
                "del proveedor. No uses get_compras_recientes como sustituto de un período."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "periods": {
                        "type": "array", "minItems": 1, "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "date_from": {"type": "string"},
                                "date_to": {"type": "string"},
                            },
                            "required": ["date_from", "date_to"],
                        },
                    },
                    "limit": {"type": "integer", "default": 3, "minimum": 1, "maximum": 20},
                    "limit_capped": {
                        "type": "boolean", "default": False,
                        "description": "True only when the parsed user request exceeded the 20-invoice cap.",
                    },
                    "supplier_query": {"type": "string", "description": "Nombre parcial o NIT del proveedor."},
                },
                "required": ["periods"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_compras_periodo",
            "description": (
                "Resume si hubo compras o lista facturas con fecha, proveedor/NIT, número, clase y "
                "total dentro de los meses seleccionados. Soporta paginación y filtro de proveedor/NIT; "
                "úsala para 'compras realizadas en agosto' y el seguimiento 'detalla esas compras'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "periods": {
                        "type": "array", "minItems": 1, "maxItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "date_from": {"type": "string"},
                                "date_to": {"type": "string"},
                            },
                            "required": ["date_from", "date_to"],
                        },
                    },
                    "view": {"type": "string", "enum": ["list", "summary"], "default": "list"},
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 50},
                    "page": {"type": "integer", "default": 1, "minimum": 1, "maximum": 1000},
                    "supplier_query": {"type": "string", "description": "Nombre parcial o NIT del proveedor."},
                },
                "required": ["periods"],
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
                        "description": "Fecha de la compra en formato YYYY-MM-DD; necesaria si el número está repetido.",
                    },
                    "cod_clase": {
                        "type": "string",
                        "default": "",
                        "description": "Código de clase del documento; necesario si sigue habiendo más de una coincidencia.",
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
            "name": "analizar_compras_periodo",
            "description": (
                "Audita en una sola llamada las compras de un rango de fechas contra ventas "
                "históricas acumuladas, unidades vendidas antes y después de comprar, velocidad "
                "reciente, stock actual y stock inicial estimado. Identifica productos sin "
                "demanda, compras mayores a la referencia y señales de sobrestock. Úsala para "
                "análisis mensuales o auditorías de compras; no encadenes get_detalle_compra "
                "por cada factura. El stock histórico es estimado y la referencia usa cobertura configurable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Inicio inclusivo YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Fin inclusivo YYYY-MM-DD."},
                    "target_cover_days": {
                        "type": "integer", "default": 45,
                        "description": "Días objetivo de cobertura para calcular cantidad de referencia; por defecto 45, no es una política fija.",
                    },
                    "limit": {
                        "type": "integer", "default": 30,
                        "description": "Máximo de productos individuales devueltos (1-60); el resumen incluye todos.",
                    },
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluar_compra_planeada",
            "description": (
                "Evalúa una lista de productos y cantidades antes de emitir una orden. Compara "
                "cada cantidad con el stock actual, ventas históricas acumuladas, ventas recientes, "
                "velocidad y días de cobertura; sugiere reducir, aumentar, mantener o revisar. "
                "Acepta SKU o nombre; ante nombres ambiguos pide el modelo o SKU. Usa esta herramienta "
                "cuando el usuario comparta una compra que piensa solicitar, no calcula una orden real."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 50,
                        "items": {
                            "type": "object",
                            "properties": {
                                "codigo": {"type": "string", "description": "SKU si se conoce."},
                                "producto": {"type": "string", "description": "Nombre o descripción si no se conoce el SKU."},
                                "cantidad": {"type": "number", "description": "Unidades incluidas en la compra planeada."},
                            },
                            "required": ["cantidad"],
                        },
                        "description": "Líneas de la orden propuesta; cada línea debe incluir codigo o producto y cantidad.",
                    },
                    "target_cover_days": {
                        "type": "integer", "default": 45,
                        "description": "Días objetivo de cobertura; guía ajustable, no incluye lead time ni stock de seguridad.",
                    },
                    "sales_window_days": {
                        "type": "integer", "default": 180,
                        "description": "Ventana principal para estimar velocidad (30-730 días).",
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analisis_modulo",
            "description": (
                "Contexto completo del módulo Análisis del dashboard: Balance, Productos top "
                "(ventas, margen, unidades, compras y Pareto), Proveedores (concentración y "
                "ventas asociadas), Horas pico, Gastos operativos y Proyección mensual. "
                "Úsala para explicar el módulo completo o una/s pestaña/s; usa las métricas "
                "canónicas del dashboard. Devuelve cortes de datos, calidad y limitaciones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Inicio inclusivo YYYY-MM-DD; por defecto inicio del mes del último corte.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Fin inclusivo YYYY-MM-DD; por defecto último día con ventas.",
                    },
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "balance", "productos", "proveedores",
                                "horas_pico", "gastos", "proyeccion",
                            ],
                        },
                        "description": "Pestañas a explicar; omitilo para incluir las seis.",
                    },
                    "product_limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Máximo de filas por ranking, entre 5 y 20.",
                    },
                },
                "required": [],
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
    {
        "type": "function",
        "function": {
            "name": "get_cash_closure",
            "description": (
                "Cierre de caja y arqueo del día: ventas totales, número de facturas, desglose por forma de pago "
                "(efectivo, tarjetas débito/crédito, transferencias bancarias / QR con montos, porcentajes del día "
                "y ticket promedio), y lista de las facturas más grandes del día. Usala cuando pregunten por el "
                "cierre de caja, arqueo, cuadre del día, o cómo se pagaron las ventas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Fecha del cierre de caja en formato ISO YYYY-MM-DD. Si se omite, se usa el último corte de ventas.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expiry_alerts",
            "description": (
                "Semáforo y alertas de lotes de productos por vencer o vencidos (habilitado para MasVital). "
                "Lista los productos con SKU, nombre, número de lote, fecha de vencimiento, días restantes y "
                "unidades disponibles en inventario. Usala cuando pregunten por vencimientos, medicamentos por vencer o lotes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Horizonte en días hacia adelante para detectar lotes por vencer (por defecto 90 días).",
                    },
                },
                "required": [],
            },
        },
    },
]
