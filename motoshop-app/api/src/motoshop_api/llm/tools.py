"""Tools registry — 10 tools tipadas para Q&A chat sobre DuckDB.

Cada tool toma args Pydantic, ejecuta query DuckDB, devuelve dict JSON.
TOOL_DEFINITIONS exporta specs OpenAI-compatible para function calling.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Tool execution ─────────────────────────────────────────────────────────

class ToolExecutor:
    """Ejecuta tools contra DuckDB."""

    def __init__(self, duckdb_path: str | None = None):
        import duckdb
        import os
        path = duckdb_path or os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb")
        self._con = duckdb.connect(path, read_only=True)

    def _get_max_date(self) -> date:
        r = self._con.execute(
            "SELECT MAX(business_date) FROM motoshop_gold_mart_ventas_diarias_sku"
        ).fetchone()
        return r[0] if r and r[0] else date.today()

    # ── Tool implementations ──────────────────────────────────────────────

    def get_kpis_today(self) -> dict:
        """KPIs del último día con datos: ventas, facturas, ticket promedio."""
        d = self._get_max_date()
        r = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2) AS ventas,
                   COALESCE(SUM(num_facturas),0) AS facturas,
                   ROUND(COALESCE(SUM(valor_total),0)/NULLIF(COALESCE(SUM(num_facturas),0),0),2) AS ticket
            FROM motoshop_gold_mart_ventas_diarias_sku WHERE business_date = ?
        """, [d.isoformat()]).fetchone()
        return {"fecha": d.isoformat(), "ventas": float(r[0] or 0), "facturas": int(r[1] or 0), "ticket_promedio": float(r[2] or 0)}

    def get_kpis_month(self, month: str | None = None) -> dict:
        """KPIs mensuales: ventas totales, facturas, ticket promedio."""
        if not month:
            month = (self._get_max_date()).strftime("%Y-%m")
        r = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2) AS ventas,
                   COALESCE(SUM(num_facturas),0) AS facturas,
                   ROUND(COALESCE(SUM(valor_total),0)/NULLIF(COALESCE(SUM(num_facturas),0),0),2) AS ticket
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE STRFTIME(business_date, '%Y-%m') = ?
        """, [month]).fetchone()
        return {"month": month, "ventas": float(r[0] or 0), "facturas": int(r[1] or 0), "ticket_promedio": float(r[2] or 0)}

    def get_top_skus(self, period: str = "day", limit: int = 10) -> dict:
        """Top SKUs vendidos en el período (day, week, month)."""
        d = self._get_max_date()
        since = d.isoformat()
        if period == "week":
            since = (d - timedelta(days=7)).isoformat()
        elif period == "month":
            since = (d - timedelta(days=30)).isoformat()

        rows = self._con.execute("""
            SELECT cod_producto, nom_producto, ROUND(SUM(valor_total),2) AS valor, ROUND(SUM(cantidad_total),2) AS cantidad
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date >= ?
            GROUP BY cod_producto, nom_producto ORDER BY valor DESC LIMIT ?
        """, [since, limit]).fetchall()
        return {"period": period, "skus": [{"sku": r[0], "nombre": r[1], "valor": float(r[2]), "cantidad": float(r[3])} for r in rows]}

    def get_dormidos(self, days_min: int = 90, limit: int = 20) -> dict:
        """Productos sin venta hace al menos days_min días. Excluye never-sold (sentinel >5000)."""
        rows = self._con.execute("""
            SELECT cod_producto, nom_producto, stock_actual, dias_sin_venta
            FROM motoshop_gold_mart_productos_dormidos
            WHERE dias_sin_venta >= ? AND dias_sin_venta < 5000
            ORDER BY dias_sin_venta DESC LIMIT ?
        """, [days_min, limit]).fetchall()
        return {"dormidos": [{"sku": r[0], "nombre": r[1], "stock": float(r[2]), "dias_sin_venta": int(r[3] if r[3] else 99999)} for r in rows], "total": len(rows)}

    def get_alerts_by_urgency(self, urgency: str | None = None) -> dict:
        """Alertas de quiebre de stock, filtrables por urgencia."""
        where = "WHERE urgencia = ?" if urgency else ""
        params = [urgency] if urgency else []
        rows = self._con.execute(f"""
            SELECT sku, nom_producto, stock_actual, demanda_predicha, dias_hasta_quiebre, urgencia
            FROM motoshop_gold_alertas_quiebre {where}
            ORDER BY dias_hasta_quiebre ASC LIMIT 20
        """, params).fetchall()
        return {"alerts": [{"sku": r[0], "nombre": r[1], "stock": float(r[2]), "demanda": float(r[3]), "dias": int(r[4]), "urgencia": r[5]} for r in rows], "total": len(rows)}

    def get_vendedor_performance(self, vendedor_id: str | None = None, period: str = "month") -> dict:
        """Performance de vendedores. Si no se especifica ID, top 5."""
        d = self._get_max_date()
        month = d.strftime("%Y-%m")
        where_v = "AND nit_vendedor = ?" if vendedor_id else ""
        params = [month]
        if vendedor_id:
            params.append(vendedor_id)

        rows = self._con.execute(f"""
            SELECT COALESCE(NULLIF(nit_vendedor,''),'SIN_ASIGNAR') AS nit,
                   COALESCE(NULLIF(nombre_vendedor,''),'Sin asignar') AS nombre,
                   COUNT(*) AS facturas, ROUND(SUM(total_factura),2) AS total
            FROM motoshop_silver_fact_ventas
            WHERE STRFTIME(business_date,'%Y-%m') = ? {where_v}
            GROUP BY nit_vendedor, nombre_vendedor ORDER BY total DESC LIMIT 5
        """, params).fetchall()
        return {"vendedores": [{"nit": r[0], "nombre": r[1], "facturas": int(r[2]), "total": float(r[3])} for r in rows]}

    def get_inventory_value(self) -> dict:
        """Valor total del inventario y cantidad de productos."""
        r = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(cantidad_actual),0),2) AS stock,
                   ROUND(COALESCE(SUM(cantidad_actual * costo_promedio),0),0) AS valor_total,
                   COUNT(DISTINCT cod_producto) AS productos
            FROM motoshop_gold_mart_inventario_actual
        """).fetchone()
        return {
            "stock_total": float(r[0] or 0),
            "valor_total_cop": float(r[1] or 0),
            "num_productos": int(r[2] or 0),
        }

    def compare_periods(self, period_1: str, period_2: str) -> dict:
        """Compara ventas entre dos meses (YYYY-MM)."""
        r1 = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COALESCE(SUM(num_facturas),0)
            FROM motoshop_gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
        """, [period_1]).fetchone()
        r2 = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total),0),2), COALESCE(SUM(num_facturas),0)
            FROM motoshop_gold_mart_ventas_diarias_sku WHERE STRFTIME(business_date,'%Y-%m') = ?
        """, [period_2]).fetchone()
        v1 = float(r1[0] or 0); v2 = float(r2[0] or 0)
        delta = round((v2 - v1) / v1 * 100, 1) if v1 else None
        return {"period_1": {"ventas": v1, "facturas": int(r1[1] or 0)}, "period_2": {"ventas": v2, "facturas": int(r2[1] or 0)}, "delta_pct": delta}

    def get_abc_distribution(self) -> dict:
        """Distribución ABC del último mes."""
        rows = self._con.execute("""
            WITH mm AS (SELECT MAX(business_month) AS m FROM motoshop_gold_mart_rotacion_abc)
            SELECT categoria_abc, COUNT(*) AS skus, ROUND(SUM(valor_total),2) AS valor
            FROM motoshop_gold_mart_rotacion_abc, mm WHERE business_month = mm.m
            GROUP BY categoria_abc ORDER BY categoria_abc
        """).fetchall()
        return {"abc": [{"categoria": r[0], "skus": int(r[1]), "valor": float(r[2])} for r in rows]}

    def get_forecast_summary(self) -> dict:
        """Resumen del forecast por categoría."""
        rows = self._con.execute("""
            SELECT cod_grupo, ROUND(SUM(demanda_real),2),
                   ROUND(SUM(demanda_predicha_baseline),2),
                   ROUND(ABS(SUM(demanda_real)-SUM(demanda_predicha_baseline))/NULLIF(SUM(demanda_real),0)*100,2)
            FROM motoshop_gold_forecast_categoria
            WHERE business_date >= CURRENT_DATE - INTERVAL '30' DAY
            GROUP BY cod_grupo ORDER BY 2 DESC
        """).fetchall()
        return {"forecast": [{"grupo": r[0], "real": float(r[1]), "predicho": float(r[2]), "desviacion_pct": float(r[3])} for r in rows]}

    def run(self, name: str, args: dict) -> dict:
        """Ejecuta una tool por nombre. Devuelve dict JSON."""
        method = getattr(self, name, None)
        if not method:
            return {"error": f"Tool '{name}' not found"}
        try:
            return method(**args)
        except Exception as exc:
            logger.warning("tool_error: %s(%s) → %s", name, args, exc)
            return {"error": str(exc)}

    def close(self):
        self._con.close()


# ── Tool definitions (OpenAI-compatible) ────────────────────────────────────

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "get_kpis_today", "description": "KPIs del último día con datos: ventas totales en COP, número de facturas, ticket promedio.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_kpis_month", "description": "KPIs de un mes específico (YYYY-MM) o del mes actual si no se especifica.", "parameters": {"type": "object", "properties": {"month": {"type": "string", "description": "Mes en formato YYYY-MM (ej: 2026-05)"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_top_skus", "description": "Top SKUs más vendidos en un período (day, week, month).", "parameters": {"type": "object", "properties": {"period": {"type": "string", "enum": ["day", "week", "month"]}, "limit": {"type": "integer", "default": 10}}, "required": []}}},
    {"type": "function", "function": {"name": "get_dormidos", "description": "Productos sin venta hace al menos N días.", "parameters": {"type": "object", "properties": {"days_min": {"type": "integer", "default": 90}, "limit": {"type": "integer", "default": 20}}, "required": []}}},
    {"type": "function", "function": {"name": "get_alerts_by_urgency", "description": "Alertas de quiebre de stock. Filtrar por urgencia: alta, media, baja.", "parameters": {"type": "object", "properties": {"urgency": {"type": "string", "enum": ["alta", "media", "baja"]}}, "required": []}}},
    {"type": "function", "function": {"name": "get_vendedor_performance", "description": "Performance de vendedores del mes actual. Si se pasa vendedor_id, solo ese.", "parameters": {"type": "object", "properties": {"vendedor_id": {"type": "string"}, "period": {"type": "string", "default": "month"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_inventory_value", "description": "Valor total del inventario en COP, cantidad de productos distintos, y stock total en unidades.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "compare_periods", "description": "Compara ventas entre dos meses (YYYY-MM). Devuelve delta porcentual.", "parameters": {"type": "object", "properties": {"period_1": {"type": "string"}, "period_2": {"type": "string"}}, "required": ["period_1", "period_2"]}}},
    {"type": "function", "function": {"name": "get_abc_distribution", "description": "Distribución ABC del último mes: cuántos SKUs en A, B, C y su valor.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_forecast_summary", "description": "Resumen del forecast de demanda por categoría (real vs predicho).", "parameters": {"type": "object", "properties": {}, "required": []}}},
]
