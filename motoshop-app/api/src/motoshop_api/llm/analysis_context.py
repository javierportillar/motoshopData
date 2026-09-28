"""Bounded assistant context for the six Analysis dashboard sections."""

from __future__ import annotations

import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date

from motoshop_api.gastos.supabase_client import list_gastos

logger = logging.getLogger(__name__)

ANALYSIS_SECTIONS = frozenset({
    "balance",
    "productos",
    "proveedores",
    "horas_pico",
    "gastos",
    "proyeccion",
})


def _expense_context(tenant: str, start: date, end: date) -> dict:
    try:
        rows = list_gastos(
            tenant=tenant,
            fecha_inicio=start.isoformat(),
            fecha_fin=end.isoformat(),
        )
    except Exception as exc:
        logger.warning(
            "analysis_expenses_unavailable tenant=%s error_type=%s",
            tenant,
            type(exc).__name__,
        )
        return {
            "status": "unavailable",
            "total": None,
            "prorated_in_range": None,
            "records": None,
            "by_month": [],
            "by_category": [],
            "items": [],
            "items_omitted": 0,
            "message": "No pude consultar los gastos operativos; no los interpreto como cero.",
            "daily_proration": None,
        }

    monthly: dict[str, float] = defaultdict(float)
    by_category: dict[str, float] = defaultdict(float)
    daily_proration: dict[str, float] = defaultdict(float)
    for row in rows:
        month = str(row["mes"])
        amount = float(row["monto"] or 0)
        category = str(row.get("categoria") or "sin_categoria")
        monthly[month] += amount
        by_category[category] += amount
        year_text, month_text = month.split("-", 1)
        days_in_month = monthrange(int(year_text), int(month_text))[1]
        daily = amount / days_in_month
        for day_number in range(1, days_in_month + 1):
            day = date(int(year_text), int(month_text), day_number)
            if start <= day <= end:
                daily_proration[day.isoformat()] += daily

    status = "available" if rows else "available_empty"
    sorted_items = sorted(rows, key=lambda row: float(row.get("monto") or 0), reverse=True)
    return {
        "status": status,
        "total": round(sum(float(row["monto"] or 0) for row in rows), 2),
        "prorated_in_range": round(sum(daily_proration.values()), 2),
        "records": len(rows),
        "by_month": [
            {"month": month, "amount": round(amount, 2)}
            for month, amount in sorted(monthly.items())
        ],
        "by_category": [
            {"category": category, "amount": round(amount, 2)}
            for category, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True)
        ],
        "items": [
            {
                "month": row["mes"],
                "category": row["categoria"],
                "amount": float(row["monto"] or 0),
                "description": row.get("descripcion"),
            }
            for row in sorted_items[:10]
        ],
        "items_omitted": max(0, len(rows) - 10),
        "message": "Sin gastos registrados en el rango." if not rows else None,
        "daily_proration": {
            day: round(amount, 2) for day, amount in daily_proration.items()
        },
    }


def _compact_balance(balance: dict, expense_status: str) -> dict:
    net_available = expense_status in {"available", "available_empty"}
    months: dict[str, dict] = {}
    day_rows = balance.get("items", [])
    ranked_days = []
    for row in day_rows:
        month = row["date"][:7]
        bucket = months.setdefault(month, {
            "month": month,
            "sales": 0.0,
            "cost_of_goods": 0.0,
            "operating_expenses": 0.0,
            "gross_profit": 0.0,
            "net_profit": 0.0,
            "days": 0,
            "closing_balance": 0.0,
        })
        for field, output in (
            ("ventas", "sales"),
            ("costo_mercancia", "cost_of_goods"),
            ("gastos_operativos", "operating_expenses"),
            ("ganancia_bruta", "gross_profit"),
            ("ganancia_neta", "net_profit"),
        ):
            bucket[output] += float(row.get(field) or 0)
        bucket["days"] += 1
        bucket["closing_balance"] = float(row.get("balance_acumulado") or 0)
        ranked_days.append({
            "date": row["date"],
            "sales": float(row.get("ventas") or 0),
            "gross_profit": float(row.get("ganancia_bruta") or 0),
            "net_profit": float(row.get("ganancia_neta") or 0) if net_available else None,
        })

    monthly = []
    for month in sorted(months):
        row = months[month]
        monthly.append({
            **{key: round(value, 2) if isinstance(value, float) else value for key, value in row.items()},
            "net_profit": round(row["net_profit"], 2) if net_available else None,
        })
    top_days = sorted(ranked_days, key=lambda row: row["gross_profit"], reverse=True)
    low_days = sorted(ranked_days, key=lambda row: row["gross_profit"])
    return {
        "status": "complete" if net_available else "partial",
        "net_profit_available": net_available,
        "total_sales": balance.get("total_ventas"),
        "total_cost_of_goods": balance.get("total_costo_mercancia"),
        "total_operating_expenses": balance.get("total_gastos_operativos") if net_available else None,
        "gross_profit": balance.get("total_ganancia_bruta"),
        "net_profit": balance.get("total_ganancia_neta") if net_available else None,
        "gross_margin_pct": balance.get("margen_bruto_pct"),
        "net_margin_pct": balance.get("margen_neto_pct") if net_available else None,
        "closing_cumulative_balance": (
            balance.get("items", [])[-1].get("balance_acumulado")
            if net_available and balance.get("items") else None
        ),
        "monthly": monthly,
        "best_gross_profit_days": top_days[:5],
        "weakest_gross_profit_days": low_days[:5],
        "expense_data_status": expense_status,
        "note": (
            "El balance neto no se puede confirmar porque Supabase no devolvió gastos operativos."
            if not net_available else None
        ),
    }


def _analysis_cutoffs(connection, tenant: str) -> dict[str, date | None]:
    inventory_table = "silver_dim_producto" if tenant.casefold() == "masvital" else "gold_mart_inventario_actual"
    return dict(zip(
        ("sales", "purchases", "inventory"),
        connection.execute(
            f"""
            SELECT
              (SELECT MAX(business_date) FROM silver_fact_ventas WHERE COALESCE(estado_documento, '') != 'A'),
              (SELECT MAX(business_date) FROM silver_fact_compras WHERE COALESCE(estado_documento, '') != 'A'),
              (SELECT MAX(snapshot_date) FROM {inventory_table})
            """
        ).fetchone(),
        strict=True,
    ))


def build_analysis_context(
    repo,
    connection,
    tenant: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    sections: list[str] | None = None,
    product_limit: int = 10,
) -> dict:
    """Compose bounded, canonical data for the six Analysis dashboard tabs."""
    cutoffs = _analysis_cutoffs(connection, tenant)
    sales_cutoff = cutoffs["sales"]
    if sales_cutoff is None:
        return {
            "status": "empty",
            "tenant": tenant,
            "sections": {},
            "mensaje": "No hay ventas con fecha disponible para fijar el período de Análisis.",
            "sources": [],
            "freshness": [],
        }

    try:
        start = date.fromisoformat(date_from) if date_from else sales_cutoff.replace(day=1)
        end = date.fromisoformat(date_to) if date_to else sales_cutoff
    except (TypeError, ValueError) as exc:
        raise ValueError("date_from y date_to deben estar en formato YYYY-MM-DD.") from exc
    if start > end:
        raise ValueError("date_from debe ser anterior o igual a date_to.")

    selected = set(sections or ANALYSIS_SECTIONS)
    invalid = selected - ANALYSIS_SECTIONS
    if invalid:
        raise ValueError("Secciones inválidas: " + ", ".join(sorted(invalid)))
    product_limit = max(5, min(int(product_limit), 20))
    output: dict[str, dict] = {}
    sources = []
    freshness = []
    source_keys: set[tuple] = set()
    freshness_keys: set[tuple] = set()
    failed_sections = []

    def add_source(domain: str, source_id: str, citation: str, cutoff: date | None, status: str = "used") -> None:
        cutoff_at = cutoff.isoformat() if cutoff else None
        source = {
            "source_id": source_id,
            "domain": domain,
            "kind": "supabase" if domain == "expenses" else "duckdb",
            "citation": citation,
            "cutoff_at": cutoff_at,
            "status": status if cutoff_at or domain == "expenses" else "unknown",
        }
        source_key = (source_id, domain, cutoff_at)
        if source_key not in source_keys:
            source_keys.add(source_key)
            sources.append(source)
        freshness_row = {
            "domain": domain,
            "cutoff_at": cutoff_at,
            "status": "current" if cutoff_at else "unknown",
        }
        freshness_key = (domain, cutoff_at)
        if freshness_key not in freshness_keys:
            freshness_keys.add(freshness_key)
            freshness.append(freshness_row)

    wants_financials = bool(selected & {"balance", "gastos"})
    expenses = None
    if wants_financials:
        expenses = _expense_context(tenant, start, end)
        add_source(
            "expenses",
            f"supabase-expenses-{tenant}",
            "Supabase gastos_operativos",
            end if expenses["status"] != "unavailable" else None,
            "failed" if expenses["status"] == "unavailable" else "used",
        )
        if expenses["status"] == "unavailable":
            failed_sections.append("gastos")

    if "balance" in selected:
        try:
            daily_expenses = expenses["daily_proration"] if expenses and expenses["daily_proration"] is not None else {}
            raw_balance = repo.get_analisis_balance(start.isoformat(), end.isoformat(), daily_expenses)
            output["balance"] = _compact_balance(
                raw_balance,
                expenses["status"] if expenses else "unavailable",
            )
            add_source("sales", "duckdb-analysis-sales", "Silver sales + cost of goods", cutoffs["sales"])
        except Exception as exc:
            logger.warning("analysis_section_failed tenant=%s section=balance error_type=%s", tenant, type(exc).__name__)
            output["balance"] = {"status": "unavailable", "message": "No se pudo calcular Balance para este rango."}
            failed_sections.append("balance")

    if "productos" in selected:
        try:
            products = repo.get_analisis_productos(start.isoformat(), end.isoformat(), product_limit)
            output["productos"] = {
                key: products.get(key)
                for key in (
                    "fecha_inicio", "fecha_fin", "total_skus_vendidos", "total_skus_comprados",
                    "total_revenue", "total_margen", "total_unidades", "total_compras_periodo",
                    "total_unidades_por_medida",
                    "margen_promedio_pct", "pareto", "top_revenue", "top_margen", "top_unidades",
                    "top_compras", "top_ganadores", "top_perdedores", "periodo_comparado",
                )
            }
            output["productos"]["limite_rankings"] = product_limit
            output["productos"]["nota_ratio_venta_compra"] = (
                "El ratio revenue/compras compara importes del período; no equivale a rotación física de inventario."
            )
            if len(products.get("total_unidades_por_medida", {})) > 1:
                output["productos"]["total_unidades_mezcladas"] = True
                output["productos"]["total_unidades"] = None
                output["productos"]["nota_unidades"] = (
                    "El conteo total del dashboard mezcla unidades de medida; usa el desglose por medida."
                )
            add_source("sales", "duckdb-analysis-sales", "Silver sales detail", cutoffs["sales"])
            add_source("purchases", "duckdb-analysis-purchases", "Silver purchase detail", cutoffs["purchases"])
        except Exception as exc:
            logger.warning("analysis_section_failed tenant=%s section=productos error_type=%s", tenant, type(exc).__name__)
            output["productos"] = {"status": "unavailable", "message": "No se pudo calcular Productos para este rango."}
            failed_sections.append("productos")

    if "proveedores" in selected:
        try:
            suppliers = repo.get_analisis_proveedores(start.isoformat(), end.isoformat())
            rows = suppliers.get("proveedores", [])
            output["proveedores"] = {
                key: suppliers.get(key)
                for key in (
                    "fecha_inicio", "fecha_fin", "total_proveedores", "total_compras",
                    "total_unidades_de_proveedores", "total_ventas_de_proveedores", "total_margen_de_proveedores",
                    "concentracion", "pareto", "alertas",
                )
            }
            output["proveedores"]["proveedores"] = rows[:10]
            output["proveedores"]["proveedores_omitidos"] = max(0, len(rows) - 10)
            output["proveedores"]["nota_asociacion_ventas"] = (
                "Las ventas por proveedor se atribuyen al último proveedor histórico de cada SKU; "
                "no son una cohorte exacta de las unidades recibidas en el período."
            )
            add_source("purchases", "duckdb-analysis-purchases", "Silver purchases by supplier", cutoffs["purchases"])
            add_source("sales", "duckdb-analysis-sales", "Sales attributed to latest supplier per SKU", cutoffs["sales"])
        except Exception as exc:
            logger.warning("analysis_section_failed tenant=%s section=proveedores error_type=%s", tenant, type(exc).__name__)
            output["proveedores"] = {"status": "unavailable", "message": "No se pudo calcular Proveedores para este rango."}
            failed_sections.append("proveedores")

    if "horas_pico" in selected:
        try:
            hours = repo.get_hours_peak(start.isoformat(), end.isoformat())
            heatmap = repo.get_heatmap_dia_hora(start.isoformat(), end.isoformat())
            hour_items = hours.get("items", [])
            heatmap_cells = heatmap.get("cells", [])
            output["horas_pico"] = {
                "fecha_inicio": start.isoformat(),
                "fecha_fin": end.isoformat(),
                "hora_pico_facturas": hours.get("hora_pico_facturas"),
                "hora_pico_ventas": hours.get("hora_pico_ventas"),
                "total_facturas": sum(int(item.get("num_facturas") or 0) for item in hour_items),
                "total_ventas": round(sum(float(item.get("total_ventas") or 0) for item in hour_items), 2),
                "top_horas_por_facturas": sorted(hour_items, key=lambda item: item["num_facturas"], reverse=True)[:5],
                "top_horas_por_ventas": sorted(hour_items, key=lambda item: item["total_ventas"], reverse=True)[:5],
                "top_celdas_dia_hora": sorted(heatmap_cells, key=lambda item: item["num_facturas"], reverse=True)[:8],
                "total_dias_con_venta": sum(item["num_facturas"] > 0 for item in hour_items),
            }
            add_source("sales", "duckdb-analysis-sales", "Sales invoice timestamps", cutoffs["sales"])
        except Exception as exc:
            logger.warning("analysis_section_failed tenant=%s section=horas_pico error_type=%s", tenant, type(exc).__name__)
            output["horas_pico"] = {"status": "unavailable", "message": "No se pudo calcular Horas pico para este rango."}
            failed_sections.append("horas_pico")

    if "gastos" in selected:
        if expenses is not None:
            output["gastos"] = {
                key: expenses[key]
                for key in (
                    "status", "total", "prorated_in_range", "records", "by_month",
                    "by_category", "items", "items_omitted", "message",
                )
            }

    if "proyeccion" in selected:
        try:
            forecast = repo.get_sales_forecast_monthly()
            output["proyeccion"] = forecast
            add_source("sales", "duckdb-analysis-sales", "Sales history for monthly run-rate forecast", cutoffs["sales"])
        except Exception as exc:
            logger.warning("analysis_section_failed tenant=%s section=proyeccion error_type=%s", tenant, type(exc).__name__)
            output["proyeccion"] = {"status": "unavailable", "message": "No se pudo calcular la proyección mensual."}
            failed_sections.append("proyeccion")

    if expenses and expenses["status"] == "unavailable" and "balance" in output:
        failed_sections.append("balance_net")
    return {
        "status": "partial" if failed_sections else "complete",
        "tenant": tenant,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "cutoffs": {key: value.isoformat() if value else None for key, value in cutoffs.items()},
        "sections": output,
        "failed_sections": sorted(set(failed_sections)),
        "sources": sources,
        "freshness": freshness,
        "respuesta_fallback": _analysis_fallback(tenant, start, end, cutoffs, output),
    }


def _analysis_fallback(
    tenant: str,
    start: date,
    end: date,
    cutoffs: dict[str, date | None],
    sections: dict,
) -> str:
    lines = [f"Resumen del módulo Análisis de {tenant} ({start.isoformat()} a {end.isoformat()}):"]
    lines.append(
        "Cortes: " + ", ".join(
            f"{domain} {cutoff.isoformat() if cutoff else 'sin datos'}"
            for domain, cutoff in cutoffs.items()
        ) + "."
    )
    balance = sections.get("balance")
    if balance and balance.get("status") != "unavailable":
        net = (
            f"ganancia neta ${balance['net_profit']:,.0f} COP"
            if balance.get("net_profit_available") and balance.get("net_profit") is not None
            else "ganancia neta no confirmable porque gastos no está disponible"
        )
        lines.append(
            f"- Balance: ventas ${balance.get('total_sales', 0) or 0:,.0f}, "
            f"costo mercancía ${balance.get('total_cost_of_goods', 0) or 0:,.0f}, "
            f"ganancia bruta ${balance.get('gross_profit', 0) or 0:,.0f}, {net}."
        )
        monthly = balance.get("monthly", [])
        if monthly:
            recent_months = []
            for item in monthly[-4:]:
                net_amount = (
                    f"${item['net_profit']:,.0f}"
                    if item.get("net_profit") is not None
                    else "no confirmable"
                )
                recent_months.append(
                    f"{item['month']}: ventas ${item['sales']:,.0f}, neto {net_amount}"
                )
            lines.append("  Meses recientes: " + "; ".join(recent_months) + ".")
        best_days = balance.get("best_gross_profit_days", [])
        weak_days = balance.get("weakest_gross_profit_days", [])
        if best_days and weak_days:
            lines.append(
                f"  Día con mayor utilidad bruta: {best_days[0]['date']} "
                f"(${best_days[0]['gross_profit']:,.0f}); menor: {weak_days[0]['date']} "
                f"(${weak_days[0]['gross_profit']:,.0f})."
            )
    products = sections.get("productos")
    if products and products.get("total_revenue") is not None:
        pareto = products.get("pareto") or {}
        best = (products.get("top_revenue") or [{}])[0]
        lines.append(
            f"- Productos: revenue ${products['total_revenue']:,.0f}, margen "
            f"${products.get('total_margen', 0):,.0f}; Pareto 80% en "
            f"{pareto.get('skus_para_80_pct', 0)} SKUs de {pareto.get('total_skus', 0)}. "
            f"Líder: {best.get('nom_producto', 'sin datos')} ({best.get('cod_producto', '—')})."
        )
        units_by_measure = products.get("total_unidades_por_medida") or {}
        if units_by_measure:
            lines.append("  Unidades vendidas por medida: " + ", ".join(
                f"{amount:,.0f} {unit}" for unit, amount in units_by_measure.items()
            ) + ".")
        top_bought = (products.get("top_compras") or [{}])[0]
        if top_bought.get("cod_producto"):
            lines.append(
                f"  Mayor valor comprado: {top_bought.get('nom_producto', '—')} "
                f"({top_bought.get('cod_producto')}) por ${top_bought.get('valor_comprado', 0):,.0f}; "
                "el ratio revenue/compras compara dinero del período, no stock físico ni cohortes de reposición."
            )
        winners = products.get("top_ganadores") or []
        losers = products.get("top_perdedores") or []
        if winners:
            lines.append(
                f"  Mayor crecimiento comparable: {winners[0].get('nom_producto', '—')} "
                f"({winners[0].get('delta_pct')}%)."
            )
        if losers:
            lines.append(
                f"  Mayor caída comparable: {losers[0].get('nom_producto', '—')} "
                f"({losers[0].get('delta_pct')}%)."
            )
    suppliers = sections.get("proveedores")
    if suppliers and suppliers.get("concentracion"):
        concentration = suppliers["concentracion"]
        top = (suppliers.get("proveedores") or [{}])[0]
        unidades_totales = suppliers.get("total_unidades_de_proveedores")
        unidades_str = f", {unidades_totales:,.0f} unidades vendidas" if unidades_totales is not None else ""
        lines.append(
            f"- Proveedores: {suppliers.get('total_proveedores', 0)} activos en el período{unidades_str}; "
            f"Top 1 concentra {concentration.get('top1_pct', 0)}%, riesgo "
            f"{concentration.get('riesgo', 'n/a')}; mayor compra a {top.get('nombre', '—')}."
        )
        top_suppliers = suppliers.get("proveedores", [])[:3]
        if top_suppliers:
            lines.append("  Top 3 proveedores: " + "; ".join(
                f"{item.get('nombre', '—')} ${item.get('total_compras', 0):,.0f}, "
                f"{item.get('unidades_vendidas', 0):,.0f} u. vendidas (${item.get('revenue_periodo', 0):,.0f}), "
                f"ratio {item.get('ratio_venta_compra')}"
                for item in top_suppliers
            ) + ".")
        all_suppliers = suppliers.get("proveedores", [])
        if all_suppliers:
            lines.append("")
            lines.append("| Proveedor | NIT | Unidades vendidas | Ventas asociadas ($ COP) | Margen ($ COP / %) | Compras ($ COP) | Ratio V/C |")
            lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
            for item in all_suppliers:
                nit = str(item.get("nit_proveedor", "—")).strip()
                nombre = str(item.get("nombre", "—")).strip()
                u_vendidas = float(item.get("unidades_vendidas", 0) or 0)
                rev = float(item.get("revenue_periodo", 0) or 0)
                margen = float(item.get("margen_periodo", 0) or 0)
                pct = item.get("margen_pct")
                pct_str = f" ({pct}%)" if pct is not None else ""
                compras = float(item.get("total_compras", 0) or 0)
                ratio = item.get("ratio_venta_compra") or "n/a"
                lines.append(
                    f"| {nombre} | NIT: {nit} | {u_vendidas:,.0f} | ${rev:,.0f} | ${margen:,.0f}{pct_str} | ${compras:,.0f} | {ratio} |"
                )
    hours = sections.get("horas_pico")
    if hours and hours.get("status") != "unavailable":
        lines.append(
            f"- Horas pico: {hours.get('total_facturas', 0)} facturas; hora pico por facturas "
            f"{hours.get('hora_pico_facturas')}:00, por ventas {hours.get('hora_pico_ventas')}:00."
        )
        top_cells = hours.get("top_celdas_dia_hora", [])[:3]
        if top_cells:
            lines.append("  Mayor actividad día/hora: " + "; ".join(
                f"{cell.get('dow_label')} {cell.get('hora'):02d}:00 "
                f"({cell.get('num_facturas')} facturas)"
                for cell in top_cells
            ) + ".")
    expenses = sections.get("gastos")
    if expenses:
        if expenses.get("status") == "unavailable":
            lines.append("- Gastos: fuente no disponible; no los interpreto como cero.")
        else:
            lines.append(
                f"- Gastos: ${expenses.get('total', 0):,.0f} COP en "
                f"{expenses.get('records', 0)} registros; "
                f"${expenses.get('prorated_in_range', 0):,.0f} prorrateados dentro del rango "
                f"(estado {expenses['status']})."
            )
            categories = expenses.get("by_category", [])[:3]
            if categories:
                lines.append("  Principales categorías: " + "; ".join(
                    f"{item['category']} ${item['amount']:,.0f}" for item in categories
                ) + ".")
    projection = sections.get("proyeccion")
    if projection and projection.get("current_month"):
        accuracy = projection.get("backtest_accuracy") or {}
        lines.append(
            f"- Proyección: {projection['current_month']['month']} → "
            f"${projection['current_month']['projected_amount']:,.0f}; siguiente mes "
            f"${projection['next_month']['projected_amount']:,.0f}; confianza "
            f"{accuracy.get('confidence', projection['next_month'].get('confidence', 'low'))}. "
            f"{accuracy.get('note', '')}"
        )
    for name, section in sections.items():
        if section.get("status") == "unavailable":
            lines.append(f"- {name}: {section.get('message', 'datos no disponibles')}.")
    return "\n".join(lines)
