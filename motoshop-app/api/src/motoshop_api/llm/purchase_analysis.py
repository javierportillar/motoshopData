"""Deterministic purchase-vs-demand analysis for the assistant tools."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta


def _as_date(value: str | date, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} debe estar en formato YYYY-MM-DD.") from exc


def _cutoffs(connection) -> dict[str, date | None]:
    row = connection.execute(
        """
        SELECT
          (SELECT MAX(business_date) FROM silver_fact_compras
           WHERE COALESCE(estado_documento, '') != 'A'),
          (SELECT MAX(business_date) FROM silver_fact_ventas
           WHERE COALESCE(estado_documento, '') != 'A'),
          (SELECT MAX(snapshot_date) FROM gold_mart_inventario_actual)
        """
    ).fetchone()
    return {"purchases": row[0], "sales": row[1], "inventory": row[2]}


def _freshness_metadata(cutoffs: dict[str, date | None]) -> tuple[list[dict], list[dict]]:
    sources = []
    freshness = []
    for domain in ("purchases", "sales", "inventory"):
        cutoff = cutoffs[domain]
        cutoff_at = cutoff.isoformat() if cutoff else None
        sources.append({
            "source_id": f"duckdb-{domain}",
            "domain": domain,
            "kind": "duckdb",
            "citation": f"DuckDB {domain} snapshot",
            "cutoff_at": cutoff_at,
            "status": "used" if cutoff else "unknown",
        })
        freshness.append({
            "domain": domain,
            "cutoff_at": cutoff_at,
            "status": "current" if cutoff else "unknown",
        })
    return sources, freshness


def _monthly_purchases(connection, date_from: date, date_to: date) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
          strftime(d.business_date, '%Y-%m') AS purchase_month,
          d.cod_producto,
          COALESCE(NULLIF(MAX(p.nombre_producto), ''), NULLIF(MAX(d.nombre_detalle), ''), d.cod_producto) AS nombre,
          SUM(COALESCE(d.cantidad, 0)) AS unidades_compradas,
          SUM(COALESCE(d.total_detalle, COALESCE(d.cantidad, 0) * COALESCE(d.valor_unitario, 0))) AS valor_comprado,
          COUNT(DISTINCT h.num_documento || '|' || h.cod_clase || '|' || CAST(h.business_date AS VARCHAR)) AS facturas,
          MIN(h.business_date) AS primera_compra,
          MAX(h.business_date) AS ultima_compra
        FROM silver_fact_compras_detalle d
        JOIN silver_fact_compras h
          ON h.num_documento = d.num_documento
         AND h.cod_clase = d.cod_clase
         AND h.business_date = d.business_date
        LEFT JOIN silver_dim_producto p ON p.cod_producto = d.cod_producto
        WHERE h.business_date BETWEEN ? AND ?
          AND COALESCE(h.estado_documento, '') != 'A'
          AND NULLIF(TRIM(d.cod_producto), '') IS NOT NULL
        GROUP BY purchase_month, d.cod_producto
        ORDER BY purchase_month, valor_comprado DESC
        """,
        [date_from, date_to],
    ).fetchall()
    return [
        {
            "mes": row[0],
            "codigo": row[1],
            "nombre": row[2],
            "unidades_compradas": float(row[3] or 0),
            "valor_comprado": float(row[4] or 0),
            "facturas": int(row[5] or 0),
            "primera_compra": row[6],
            "ultima_compra": row[7],
        }
        for row in rows
    ]


def _invoice_month_totals(connection, date_from: date, date_to: date) -> dict[str, dict]:
    rows = connection.execute(
        """
        SELECT strftime(business_date, '%Y-%m') AS purchase_month,
               COUNT(*) AS facturas,
               SUM(COALESCE(total_factura, 0)) AS valor_facturado
        FROM silver_fact_compras
        WHERE business_date BETWEEN ? AND ?
          AND COALESCE(estado_documento, '') != 'A'
        GROUP BY purchase_month
        """,
        [date_from, date_to],
    ).fetchall()
    return {
        row[0]: {"facturas": int(row[1] or 0), "valor_facturado": float(row[2] or 0)}
        for row in rows
    }


def _product_day_movements(
    connection,
    product_codes: list[str],
    sales_cutoff: date,
    purchase_start: date,
    inventory_cutoff: date | None,
) -> tuple[dict[str, list[tuple[date, float, float]]], dict[str, list[tuple[date, float]]]]:
    if not product_codes:
        return {}, {}
    placeholders = ",".join("?" for _ in product_codes)
    sales_rows = connection.execute(
        f"""
        SELECT d.cod_producto, h.business_date,
               SUM(COALESCE(d.cantidad, 0)), SUM(COALESCE(d.total_detalle, 0))
        FROM silver_fact_ventas_detalle d
        JOIN silver_fact_ventas h
          ON h.num_documento = d.num_documento
         AND h.cod_clase = d.cod_clase
         AND h.business_date = d.business_date
        WHERE d.cod_producto IN ({placeholders})
          AND h.business_date <= ?
          AND COALESCE(h.estado_documento, '') != 'A'
        GROUP BY d.cod_producto, h.business_date
        """,
        [*product_codes, sales_cutoff],
    ).fetchall()
    purchase_rows = []
    if inventory_cutoff and purchase_start <= inventory_cutoff:
        purchase_rows = connection.execute(
            f"""
            SELECT d.cod_producto, h.business_date, SUM(COALESCE(d.cantidad, 0))
            FROM silver_fact_compras_detalle d
            JOIN silver_fact_compras h
              ON h.num_documento = d.num_documento
             AND h.cod_clase = d.cod_clase
             AND h.business_date = d.business_date
            WHERE d.cod_producto IN ({placeholders})
              AND h.business_date BETWEEN ? AND ?
              AND COALESCE(h.estado_documento, '') != 'A'
            GROUP BY d.cod_producto, h.business_date
            """,
            [*product_codes, purchase_start, inventory_cutoff],
        ).fetchall()
    sales: dict[str, list[tuple[date, float, float]]] = defaultdict(list)
    purchases: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for code, movement_date, units, value in sales_rows:
        sales[code].append((movement_date, float(units or 0), float(value or 0)))
    for code, movement_date, units in purchase_rows:
        purchases[code].append((movement_date, float(units or 0)))
    return sales, purchases


def _current_stock(connection, product_codes: list[str], cutoff: date | None) -> dict[str, float]:
    if not product_codes or not cutoff:
        return {}
    placeholders = ",".join("?" for _ in product_codes)
    rows = connection.execute(
        f"""
        SELECT cod_producto, SUM(COALESCE(cantidad_actual, 0))
        FROM gold_mart_inventario_actual
        WHERE snapshot_date = ? AND cod_producto IN ({placeholders})
        GROUP BY cod_producto
        """,
        [cutoff, *product_codes],
    ).fetchall()
    return {row[0]: float(row[1] or 0) for row in rows}


def _additional_demand_candidates(
    connection,
    excluded_codes: list[str],
    sales_cutoff: date,
    inventory_cutoff: date,
    *,
    target_cover_days: int,
    sales_window_days: int,
    limit: int = 5,
) -> list[dict]:
    exclusions = ",".join("?" for _ in excluded_codes)
    excluded_clause = f"AND p.cod_producto NOT IN ({exclusions})" if excluded_codes else ""
    rows = connection.execute(
        f"""
        WITH sales AS (
          SELECT d.cod_producto,
                 SUM(CASE WHEN h.business_date >= ? THEN COALESCE(d.cantidad, 0) ELSE 0 END) AS units_window,
                 SUM(CASE WHEN h.business_date >= ? THEN COALESCE(d.cantidad, 0) ELSE 0 END) AS units_90d,
                 MAX(h.business_date) AS last_sale
          FROM silver_fact_ventas_detalle d
          JOIN silver_fact_ventas h
            ON h.num_documento = d.num_documento
           AND h.cod_clase = d.cod_clase
           AND h.business_date = d.business_date
          WHERE h.business_date <= ?
            AND COALESCE(h.estado_documento, '') != 'A'
          GROUP BY d.cod_producto
        ), inventory AS (
          SELECT cod_producto, SUM(COALESCE(cantidad_actual, 0)) AS current_stock
          FROM gold_mart_inventario_actual
          WHERE snapshot_date = ?
          GROUP BY cod_producto
        ), purchase_history AS (
          SELECT d.cod_producto, SUM(COALESCE(d.cantidad, 0)) AS purchased_units
          FROM silver_fact_compras_detalle d
          JOIN silver_fact_compras h
            ON h.num_documento = d.num_documento
           AND h.cod_clase = d.cod_clase
           AND h.business_date = d.business_date
          WHERE COALESCE(h.estado_documento, '') != 'A'
          GROUP BY d.cod_producto
        )
        SELECT p.cod_producto, p.nombre_producto, s.units_window, s.units_90d,
               COALESCE(i.current_stock, 0) AS current_stock, s.last_sale,
               CEIL(GREATEST(s.units_window / ? * ? - COALESCE(i.current_stock, 0), 0)) AS suggested_qty
        FROM sales s
        JOIN silver_dim_producto p ON p.cod_producto = s.cod_producto
        LEFT JOIN inventory i ON i.cod_producto = s.cod_producto
        JOIN purchase_history ph ON ph.cod_producto = p.cod_producto AND ph.purchased_units > 0
        WHERE s.units_window > 0
          AND COALESCE(i.current_stock, 0) >= 0
          AND UPPER(COALESCE(p.nombre_producto, '')) NOT LIKE '%SERVICIO%'
          AND s.units_window / ? * ? > COALESCE(i.current_stock, 0)
          {excluded_clause}
        ORDER BY s.units_window DESC, suggested_qty DESC
        LIMIT ?
        """,
        [
            sales_cutoff - timedelta(days=sales_window_days - 1),
            sales_cutoff - timedelta(days=89),
            sales_cutoff,
            inventory_cutoff,
            sales_window_days,
            target_cover_days,
            sales_window_days,
            target_cover_days,
            *excluded_codes,
            limit,
        ],
    ).fetchall()
    return [
        {
            "codigo": row[0],
            "nombre": row[1],
            "unidades_vendidas_ventana": round(float(row[2] or 0), 2),
            "unidades_vendidas_90d": round(float(row[3] or 0), 2),
            "stock_actual": round(float(row[4] or 0), 2),
            "ultima_venta": row[5].isoformat() if row[5] else None,
            "cantidad_guia_para_cobertura": int(row[6] or 0),
        }
        for row in rows
    ]


def analyze_purchase_period(
    connection,
    date_from: str | date,
    date_to: str | date,
    *,
    target_cover_days: int = 45,
    limit: int = 30,
) -> dict:
    """Assess purchased SKUs against prior demand and post-purchase movement."""
    start = _as_date(date_from, "date_from")
    end = _as_date(date_to, "date_to")
    if start > end:
        raise ValueError("date_from debe ser anterior o igual a date_to.")
    target_cover_days = max(1, min(int(target_cover_days), 365))
    limit = max(1, min(int(limit), 60))
    cutoffs = _cutoffs(connection)
    purchases_by_month = _monthly_purchases(connection, start, end)
    sources, freshness = _freshness_metadata(cutoffs)
    if not purchases_by_month:
        return {
            "status": "empty",
            "periodo": {"desde": start.isoformat(), "hasta": end.isoformat()},
            "mensaje": "No se encontraron compras válidas en ese período.",
            "sources": sources,
            "freshness": freshness,
        }

    product_codes = sorted({row["codigo"] for row in purchases_by_month})
    invoice_totals = _invoice_month_totals(connection, start, end)
    stock_cutoff = cutoffs["inventory"]
    sales_cutoff = cutoffs["sales"]
    sales_by_day: dict[str, list[tuple[date, float, float]]] = {}
    purchases_by_day: dict[str, list[tuple[date, float]]] = {}
    if sales_cutoff:
        sales_by_day, purchases_by_day = _product_day_movements(
            connection,
            product_codes,
            sales_cutoff,
            min(date.fromisoformat(f"{row['mes']}-01") for row in purchases_by_month),
            stock_cutoff,
        )
    stock = _current_stock(connection, product_codes, stock_cutoff)

    enriched = []
    for row in purchases_by_month:
        code = row["codigo"]
        month_start = date.fromisoformat(f"{row['mes']}-01")
        next_month = (
            date(month_start.year + 1, 1, 1)
            if month_start.month == 12
            else date(month_start.year, month_start.month + 1, 1)
        )
        month_end = next_month - timedelta(days=1)
        sales = sales_by_day.get(code, [])
        all_sales = [item for item in sales if not sales_cutoff or item[0] <= sales_cutoff]
        sales_before_month = [item for item in all_sales if item[0] < month_start]
        units_sold_before_month = sum(units for _, units, _ in sales_before_month)
        revenue_sold_before_month = sum(value for _, _, value in sales_before_month)
        previous_window_start = month_start - timedelta(days=180)
        prior_180 = sum(
            units for sold_date, units, _ in sales_before_month
            if sold_date >= previous_window_start
        )
        units_all_time = sum(units for _, units, _ in all_sales)
        revenue_all_time = sum(value for _, _, value in all_sales)
        last_sale = max((sold_date for sold_date, _, _ in all_sales), default=None)
        later_purchase_dates = [
            bought_date for bought_date, _ in purchases_by_day.get(code, [])
            if bought_date > row["ultima_compra"]
        ]
        next_purchase_date = min(later_purchase_dates, default=None)
        sold_after_last_month_purchase = sum(
            units for sold_date, units, _ in all_sales
            if sold_date > row["ultima_compra"]
            and (next_purchase_date is None or sold_date < next_purchase_date)
        )
        recent_sales = {}
        for days in (90, 180, 365):
            window_start = (sales_cutoff - timedelta(days=days - 1)) if sales_cutoff else None
            recent_sales[str(days)] = sum(
                units for sold_date, units, _ in all_sales
                if window_start and sold_date >= window_start
            )

        stock_start_estimate = None
        current_stock = stock.get(code) if stock_cutoff else None
        if current_stock is not None and stock_cutoff and month_start <= stock_cutoff:
            purchases_since_start = sum(
                units for bought_date, units in purchases_by_day.get(code, [])
                if month_start <= bought_date <= stock_cutoff
            )
            sales_since_start = sum(
                units for sold_date, units, _ in all_sales
                if month_start <= sold_date <= stock_cutoff
            )
            # Reconstruct opening stock using the latest snapshot and recorded
            # buys/sales only; stock adjustments/transfers are not available here.
            stock_start_estimate = current_stock - purchases_since_start + sales_since_start

        expected_demand = prior_180 / 180 * target_cover_days
        recommended_at_start = None
        if stock_start_estimate is not None and stock_start_estimate >= 0:
            recommended_at_start = math.ceil(max(0.0, expected_demand - stock_start_estimate))

        current_sales_180 = recent_sales["180"]
        current_daily_rate = current_sales_180 / 180
        current_cover = (
            round(current_stock / current_daily_rate, 1)
            if current_stock is not None and current_daily_rate > 0
            else None
        )
        current_expected_stock = current_daily_rate * target_cover_days

        if stock_start_estimate is None or stock_start_estimate < 0:
            assessment = "stock_historico_no_confiable"
        elif prior_180 == 0:
            assessment = (
                "producto_sin_historial_previo"
                if units_sold_before_month == 0
                else "producto_con_historial_sin_rotacion_180d"
            )
        elif stock_start_estimate > expected_demand * 1.2 and row["unidades_compradas"] > 0:
            assessment = "ya_habia_stock_para_la_demanda"
        elif recommended_at_start is not None and row["unidades_compradas"] > recommended_at_start:
            assessment = "cantidad_superior_a_referencia"
        else:
            assessment = "alineada_con_demanda_previa"

        if current_stock is not None and current_sales_180 == 0:
            current_signal = "sin_ventas_ultimos_180d"
        elif current_stock is not None and current_stock > current_expected_stock * 1.2:
            current_signal = "stock_actual_supera_objetivo"
        elif current_stock is not None:
            current_signal = "stock_actual_en_rango"
        else:
            current_signal = "inventario_actual_no_disponible"

        enriched.append({
            **row,
            "unidades_vendidas_acumuladas_antes_del_mes": round(units_sold_before_month, 2),
            "valor_vendido_acumulado_antes_del_mes": round(revenue_sold_before_month, 2),
            "unidades_vendidas_historicas_hasta_corte": round(units_all_time, 2),
            "valor_vendido_historico_hasta_corte": round(revenue_all_time, 2),
            "unidades_vendidas_180d_antes_del_mes": round(prior_180, 2),
            "unidades_vendidas_90d_actuales": round(recent_sales["90"], 2),
            "unidades_vendidas_180d_actuales": round(current_sales_180, 2),
            "unidades_vendidas_365d_actuales": round(recent_sales["365"], 2),
            "ultima_venta": last_sale.isoformat() if last_sale else None,
            "siguiente_compra_registrada": next_purchase_date.isoformat() if next_purchase_date else None,
            "unidades_vendidas_despues_de_ultima_compra_del_mes": round(sold_after_last_month_purchase, 2),
            "stock_actual": round(current_stock, 2) if current_stock is not None else None,
            "stock_estimado_al_inicio_del_mes": round(stock_start_estimate, 2) if stock_start_estimate is not None else None,
            "recomendacion_compra_al_inicio_del_mes_unidades": recommended_at_start,
            "cobertura_stock_actual_dias": current_cover,
            "evaluacion_de_la_compra": assessment,
            "senal_actual": current_signal,
            "ventas_despues_de_la_compra_periodo": round(sold_after_last_month_purchase, 2),
            "limite_objetivo_dias": target_cover_days,
            "mes_hasta": month_end.isoformat(),
        })

    risk_assessments = {
        "producto_con_historial_sin_rotacion_180d",
        "ya_habia_stock_para_la_demanda",
        "cantidad_superior_a_referencia",
    }
    by_month = []
    for month in sorted({row["mes"] for row in enriched}):
        items = [row for row in enriched if row["mes"] == month]
        invoices = invoice_totals.get(month, {"facturas": 0, "valor_facturado": 0.0})
        by_month.append({
            "mes": month,
            "facturas": invoices["facturas"],
            "valor_facturado": round(invoices["valor_facturado"], 2),
            "productos_distintos": len(items),
            "unidades_compradas": round(sum(row["unidades_compradas"] for row in items), 2),
            "productos_sin_rotacion_previa_180d": sum(
                row["evaluacion_de_la_compra"] == "producto_con_historial_sin_rotacion_180d" for row in items
            ),
            "productos_sin_historial_previo": sum(
                row["evaluacion_de_la_compra"] == "producto_sin_historial_previo" for row in items
            ),
            "productos_con_stock_previo_excedente": sum(
                row["evaluacion_de_la_compra"] == "ya_habia_stock_para_la_demanda" for row in items
            ),
            "productos_por_sobre_referencia": sum(
                row["evaluacion_de_la_compra"] == "cantidad_superior_a_referencia" for row in items
            ),
            "productos_con_ventas_antes_de_siguiente_compra": sum(
                row["unidades_vendidas_despues_de_ultima_compra_del_mes"] > 0 for row in items
            ),
            "valor_comprado_en_senales_de_riesgo": round(sum(
                row["valor_comprado"] for row in items
                if row["evaluacion_de_la_compra"] in risk_assessments
            ), 2),
            "unidades_vendidas_despues_de_ultima_compra": round(
                sum(row["unidades_vendidas_despues_de_ultima_compra_del_mes"] for row in items), 2
            ),
        })

    priority = {
        "producto_con_historial_sin_rotacion_180d": 4,
        "ya_habia_stock_para_la_demanda": 3,
        "cantidad_superior_a_referencia": 2,
        "producto_sin_historial_previo": 1,
        "stock_historico_no_confiable": 1,
        "alineada_con_demanda_previa": 0,
    }
    enriched.sort(
        key=lambda row: (
            priority[row["evaluacion_de_la_compra"]],
            row["valor_comprado"],
        ),
        reverse=True,
    )
    visible = enriched[:limit]
    movement_highlights = sorted(
        (
            row for row in enriched
            if row["unidades_vendidas_despues_de_ultima_compra_del_mes"] > 0
        ),
        key=lambda row: row["unidades_vendidas_despues_de_ultima_compra_del_mes"],
        reverse=True,
    )[:5]
    sources, freshness = _freshness_metadata(cutoffs)
    result = {
        "status": "complete",
        "periodo": {"desde": start.isoformat(), "hasta": end.isoformat()},
        "cortes_datos": {key: value.isoformat() if value else None for key, value in cutoffs.items()},
        "periodo_parcial": bool(cutoffs["purchases"] and cutoffs["purchases"] < end),
        "parametros": {
            "objetivo_cobertura_dias": target_cover_days,
            "ventana_previa_demanda_dias": 180,
            "productos_mostrados": len(visible),
            "productos_analizados": len(enriched),
        },
        "resumen_por_mes": by_month,
        "productos": visible,
        "movimiento_posterior_destacado": [
            {
                "mes": row["mes"],
                "codigo": row["codigo"],
                "nombre": row["nombre"],
                "unidades_compradas": row["unidades_compradas"],
                "unidades_vendidas_antes_de_siguiente_compra": row[
                    "unidades_vendidas_despues_de_ultima_compra_del_mes"
                ],
                "stock_actual": row["stock_actual"],
            }
            for row in movement_highlights
        ],
        "productos_omitidos": max(0, len(enriched) - len(visible)),
        "nota_stock_historico": (
            "El stock al inicio de cada mes es una reconstrucción estimada desde el snapshot actual "
            "menos compras más ventas registradas; no hay snapshot histórico inmutable para agosto/septiembre. "
            "Puede diferir por ajustes, traslados o devoluciones no representados en compras/ventas. "
            "Las ventas observadas después de una compra se cuentan hasta la siguiente compra del SKU, "
            "pero no se pueden atribuir exclusivamente a las unidades de esa factura."
        ),
        "nota_recomendacion": (
            f"La cantidad de referencia apunta a {target_cover_days} días de cobertura según las ventas "
            "de los 180 días previos; es una guía, no incorpora lead time, mínimos de proveedor, "
            "estacionalidad ni órdenes abiertas."
        ),
        "sources": sources,
        "freshness": freshness,
    }
    result["respuesta_fallback"] = _historical_fallback_text(result)
    return result


def _historical_fallback_text(result: dict) -> str:
    risk_assessments = {
        "producto_con_historial_sin_rotacion_180d",
        "ya_habia_stock_para_la_demanda",
        "cantidad_superior_a_referencia",
    }
    lines = [
        "Auditoría cuantitativa de compras (no reemplaza la validación del comprador):",
    ]
    for month in result["resumen_por_mes"]:
        lines.append(
            f"- {month['mes']}: ${month['valor_facturado']:,.0f} COP en {month['facturas']} facturas "
            f"{month['productos_distintos']} productos y {month['unidades_compradas']:,.0f} u compradas; "
            f"{month['productos_sin_rotacion_previa_180d']} con historial pero sin venta "
            "en los 180 días previos, "
            f"{month['productos_sin_historial_previo']} sin historial previo (no se deben "
            "clasificar automáticamente como mala compra), "
            f"{month['productos_con_stock_previo_excedente']} con stock previo estimado superior "
            f"a la demanda objetivo y {month['productos_por_sobre_referencia']} por encima "
            f"de la cantidad guía; {month['productos_con_ventas_antes_de_siguiente_compra']} "
            "tuvieron ventas observadas antes de la siguiente reposición. "
            f"${month['valor_comprado_en_senales_de_riesgo']:,.0f} COP "
            "quedaron en señales de riesgo."
        )
    if result["movimiento_posterior_destacado"]:
        lines.append(
            "Movimiento posterior observado (no prueba que las unidades vendidas sean de esa factura):"
        )
        for row in result["movimiento_posterior_destacado"][:3]:
            lines.append(
                f"- {row['mes']} · {row['codigo']} {row['nombre']}: "
                f"compradas {row['unidades_compradas']:g} u, luego se vendieron "
                f"{row['unidades_vendidas_antes_de_siguiente_compra']:g} u antes de otra reposición."
            )
    flagged = [
        row for row in result["productos"]
        if row["evaluacion_de_la_compra"] in risk_assessments
    ][:6]
    if flagged:
        lines.append("Productos para revisar primero:")
        for row in flagged:
            recommended = row["recomendacion_compra_al_inicio_del_mes_unidades"]
            signal_labels = {
                "producto_con_historial_sin_rotacion_180d": "tenía historial, pero no vendió en los 180 días previos",
                "producto_sin_historial_previo": "no tenía historial de ventas previo",
                "ya_habia_stock_para_la_demanda": "el stock previo estimado ya cubría el objetivo",
                "cantidad_superior_a_referencia": "la compra superó la cantidad guía",
                "stock_historico_no_confiable": "no se pudo reconstruir el stock histórico con confianza",
                "alineada_con_demanda_previa": "alineada con la demanda observada",
            }
            lines.append(
                f"- {row['mes']} · {row['codigo']} {row['nombre']}: compradas "
                f"{row['unidades_compradas']:g} u (${row['valor_comprado']:,.0f}); "
                f"venta previa 180d={row['unidades_vendidas_180d_antes_del_mes']:g} u; "
                f"stock previo estimado={row['stock_estimado_al_inicio_del_mes']}; "
                f"guía de compra={recommended}; vendidas tras la última compra="
                f"{row['unidades_vendidas_despues_de_ultima_compra_del_mes']:g} u; "
                f"señal: {signal_labels[row['evaluacion_de_la_compra']]}."
            )
    lines.append(result["nota_stock_historico"])
    lines.append(result["nota_recomendacion"])
    if result["periodo_parcial"]:
        lines.append(
            f"El período solicitado termina el {result['periodo']['hasta']}, pero compras tiene corte "
            f"{result['cortes_datos']['purchases']}; el último mes está incompleto."
        )
    return "\n".join(lines)


def evaluate_planned_purchase(
    connection,
    items: list[dict],
    *,
    target_cover_days: int = 45,
    sales_window_days: int = 180,
) -> dict:
    """Compare planned quantities with recent demand and current stock."""
    target_cover_days = max(1, min(int(target_cover_days), 365))
    sales_window_days = max(30, min(int(sales_window_days), 730))
    if not items:
        raise ValueError("La compra planeada debe incluir al menos un producto.")
    if len(items) > 50:
        raise ValueError("Se pueden evaluar hasta 50 productos por consulta.")

    codes = sorted({item["codigo"] for item in items})
    cutoffs = _cutoffs(connection)
    sales_cutoff = cutoffs["sales"]
    stock_cutoff = cutoffs["inventory"]
    if not sales_cutoff or not stock_cutoff:
        raise ValueError("No están disponibles los cortes de ventas e inventario para evaluar la compra.")

    placeholders = ",".join("?" for _ in codes)
    sales_rows = connection.execute(
        f"""
        SELECT d.cod_producto,
               SUM(COALESCE(d.cantidad, 0)) AS unidades_historicas,
               SUM(CASE WHEN h.business_date >= ? THEN COALESCE(d.cantidad, 0) ELSE 0 END) AS unidades_ventana,
               SUM(CASE WHEN h.business_date >= ? THEN COALESCE(d.cantidad, 0) ELSE 0 END) AS unidades_365d,
               SUM(CASE WHEN h.business_date >= ? THEN COALESCE(d.cantidad, 0) ELSE 0 END) AS unidades_90d,
               SUM(CASE WHEN h.business_date >= ? THEN COALESCE(d.total_detalle, 0) ELSE 0 END) AS ventas_valor_ventana,
               MIN(h.business_date) AS primera_venta,
               MAX(h.business_date) AS ultima_venta
        FROM silver_fact_ventas_detalle d
        JOIN silver_fact_ventas h
          ON h.num_documento = d.num_documento
         AND h.cod_clase = d.cod_clase
         AND h.business_date = d.business_date
        WHERE d.cod_producto IN ({placeholders})
          AND h.business_date <= ?
          AND COALESCE(h.estado_documento, '') != 'A'
        GROUP BY d.cod_producto
        """,
        [
            sales_cutoff - timedelta(days=sales_window_days - 1),
            sales_cutoff - timedelta(days=365 - 1),
            sales_cutoff - timedelta(days=90 - 1),
            sales_cutoff - timedelta(days=sales_window_days - 1),
            *codes,
            sales_cutoff,
        ],
    ).fetchall()
    sales = {
        row[0]: {
            "unidades_historicas": float(row[1] or 0),
            "unidades_ventana": float(row[2] or 0),
            "unidades_365d": float(row[3] or 0),
            "unidades_90d": float(row[4] or 0),
            "ventas_valor_ventana": float(row[5] or 0),
            "primera_venta": row[6],
            "ultima_venta": row[7],
        }
        for row in sales_rows
    }
    stock = _current_stock(connection, codes, stock_cutoff)
    metrics = []
    for item in items:
        code = item["codigo"]
        demand = sales.get(code, {})
        current_stock = stock.get(code, 0.0)
        units_window = demand.get("unidades_ventana", 0.0)
        rate_basis_days = sales_window_days if units_window > 0 else 365
        rate_units = units_window if units_window > 0 else demand.get("unidades_365d", 0.0)
        daily_rate = rate_units / rate_basis_days
        target_units = daily_rate * target_cover_days
        recommended = math.ceil(max(0.0, target_units - current_stock))
        requested = float(item["cantidad"])
        projected_stock = current_stock + requested
        current_cover = round(current_stock / daily_rate, 1) if daily_rate > 0 else None
        projected_cover = round(projected_stock / daily_rate, 1) if daily_rate > 0 else None

        if demand.get("unidades_historicas", 0) == 0:
            recommendation = "revisar_sin_historial_de_ventas"
            recommended = 0
        elif demand.get("unidades_365d", 0) == 0:
            recommendation = "evitar_reponer_sin_ventas_365d"
            recommended = 0
        elif units_window == 0:
            recommendation = "revisar_sin_rotacion_en_ventana"
            recommended = 0
        elif current_stock > target_units * 1.2:
            recommendation = "reducir_o_eliminar_por_stock_actual"
            recommended = 0
        elif requested > recommended:
            recommendation = "reducir_cantidad"
        elif requested < recommended:
            recommendation = "cantidad_insuficiente_para_objetivo"
        else:
            recommendation = "cantidad_alineada_con_objetivo"

        metrics.append({
            "codigo": code,
            "nombre": item["nombre"],
            "cantidad_solicitada": requested,
            "stock_actual": round(current_stock, 2),
            "ventas_historicas_acumuladas_unidades": round(demand.get("unidades_historicas", 0), 2),
            f"ventas_{sales_window_days}d_unidades": round(units_window, 2),
            "ventas_90d_unidades": round(demand.get("unidades_90d", 0), 2),
            "ventas_365d_unidades": round(demand.get("unidades_365d", 0), 2),
            "venta_valor_ventana": round(demand.get("ventas_valor_ventana", 0), 2),
            "primera_venta": demand["primera_venta"].isoformat() if demand.get("primera_venta") else None,
            "ultima_venta": demand["ultima_venta"].isoformat() if demand.get("ultima_venta") else None,
            "velocidad_diaria_estimada": round(daily_rate, 4),
            "ventana_velocidad_dias": rate_basis_days,
            "dias_cobertura_stock_actual": current_cover,
            "unidades_objetivo_para_cobertura": round(target_units, 2),
            "cantidad_sugerida": recommended,
            "exceso_vs_sugerido": round(max(0.0, requested - recommended), 2),
            "faltante_vs_sugerido": round(max(0.0, recommended - requested), 2),
            "stock_proyectado": round(projected_stock, 2),
            "dias_cobertura_tras_compra": projected_cover,
            "recomendacion": recommendation,
        })

    sources, freshness = _freshness_metadata(cutoffs)
    additional_candidates = _additional_demand_candidates(
        connection,
        codes,
        sales_cutoff,
        stock_cutoff,
        target_cover_days=target_cover_days,
        sales_window_days=sales_window_days,
    )
    result = {
        "status": "complete",
        "cortes_datos": {key: value.isoformat() if value else None for key, value in cutoffs.items()},
        "parametros": {
            "objetivo_cobertura_dias": target_cover_days,
            "ventana_ventas_dias": sales_window_days,
            "items_evaluados": len(metrics),
        },
        "resumen": {
            "unidades_solicitadas": round(sum(row["cantidad_solicitada"] for row in metrics), 2),
            "unidades_sugeridas": sum(row["cantidad_sugerida"] for row in metrics),
            "productos_a_reducir": sum(row["recomendacion"] in {
                "reducir_cantidad", "reducir_o_eliminar_por_stock_actual",
                "evitar_reponer_sin_ventas_365d",
            } for row in metrics),
            "productos_con_compra_alineada": sum(
                row["recomendacion"] == "cantidad_alineada_con_objetivo" for row in metrics
            ),
            "productos_aumentar": sum(
                row["recomendacion"] == "cantidad_insuficiente_para_objetivo" for row in metrics
            ),
            "productos_sin_evidencia_suficiente": sum(row["recomendacion"] in {
                "revisar_sin_historial_de_ventas", "revisar_sin_rotacion_en_ventana",
            } for row in metrics),
        },
        "productos": metrics,
        "productos_con_demanda_y_stock_bajo_fuera_de_la_lista": additional_candidates,
        "nota_candidatos_adicionales": (
            "Son productos con ventas recientes y stock menor al objetivo; no son sustitutos "
            "compatibles de los productos planeados. Validá modelo de moto, aplicación y proveedor."
        ),
        "nota": (
            f"La cantidad sugerida apunta a {target_cover_days} días de cobertura con promedio de "
            f"{sales_window_days} días (si no hubo ventas en esa ventana, usa los últimos 365 días). "
            "No contempla lead time, stock de seguridad, mínimos de compra, órdenes abiertas ni estacionalidad. "
            "Validá esos factores antes de emitir la orden."
        ),
        "sources": sources,
        "freshness": freshness,
    }
    result["respuesta_fallback"] = _planned_fallback_text(result)
    return result


def _planned_fallback_text(result: dict) -> str:
    sales_window_label = f"ventas_{result['parametros']['ventana_ventas_dias']}d_unidades"
    lines = [
        "Evaluación cuantitativa de la compra planeada:",
        f"Se propusieron {result['resumen']['unidades_solicitadas']:g} unidades; "
        f"la guía es {result['resumen']['unidades_sugeridas']} unidades "
        f"para {result['parametros']['objetivo_cobertura_dias']} días de cobertura.",
    ]
    for item in result["productos"]:
        label = item["recomendacion"].replace("_", " ")
        lines.append(
            f"- {item['codigo']} {item['nombre']}: pedirían {item['cantidad_solicitada']:g}, "
            f"stock {item['stock_actual']:g}, ventas {result['parametros']['ventana_ventas_dias']}d "
            f"{item[sales_window_label]:g}, "
            f"guía {item['cantidad_sugerida']} u, cobertura tras compra "
            f"{item['dias_cobertura_tras_compra']} días; recomendación: {label}."
        )
    if result["productos_con_demanda_y_stock_bajo_fuera_de_la_lista"]:
        lines.append("Otros productos con demanda y stock bajo que podrías revisar:")
        for item in result["productos_con_demanda_y_stock_bajo_fuera_de_la_lista"][:5]:
            lines.append(
                f"- {item['codigo']} {item['nombre']}: {item['unidades_vendidas_ventana']:g} u "
                f"vendidas en {result['parametros']['ventana_ventas_dias']}d, stock "
                f"{item['stock_actual']:g}, guía {item['cantidad_guia_para_cobertura']} u."
            )
    lines.append(result["nota"])
    lines.append(result["nota_candidatos_adicionales"])
    return "\n".join(lines)
