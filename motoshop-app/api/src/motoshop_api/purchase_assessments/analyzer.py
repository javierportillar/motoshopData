"""Invoice-level deterministic purchase analysis over a tenant DuckDB snapshot."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

ANALYZER_REVISION = "purchase-invoice-v4-unclassified-lines"
DEFAULT_TARGET_COVER_DAYS = 45
MAX_STORED_PRODUCT_RESULTS = 500


@dataclass(frozen=True)
class PurchaseInvoice:
    """A unique, non-canceled purchase header with its full-identity detail rows."""

    business_date: date
    cod_clase: str
    num_documento: str
    header: dict[str, Any]
    lines: list[dict[str, Any]]
    content_fingerprint: str

    @property
    def identity(self) -> tuple[date, str, str]:
        return (self.business_date, self.cod_clase, self.num_documento)


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return str(value)
    return str(value)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _purchase_verdict(
    *,
    signal: str,
    quantity: float,
    unit: str,
    prior_units: float,
    stock_before: float | None,
    prior_cover_days: float | None,
    suggested_quantity: float | None,
    target_cover_days: int,
    stock_reconstructed_negative: bool,
) -> tuple[str, str, str]:
    """Turn stock and sales signals into an explainable, non-profitability verdict."""
    if signal == "insufficient_evidence":
        reason = (
            "La reconstrucción del stock previo fue negativa; no se puede evaluar la reposición."
            if stock_reconstructed_negative
            else "No hay stock previo confiable para contrastar la compra con las ventas."
        )
        return "not_evaluable", "No evaluable", reason

    if quantity <= 0:
        return (
            "review_non_positive_quantity",
            "Revisar: cantidad no positiva",
            f"La cantidad neta comprada es {quantity:g} {unit}; "
            "no se clasifica como reposición normal.",
        )

    if prior_units <= 0:
        return (
            "review_no_prior_sales",
            "Revisar: sin ventas previas",
            "No hay unidades vendidas registradas en los 180 días previos; "
            "la demanda no se puede validar.",
        )

    if signal == "stock_previo_estimado_superaba_objetivo":
        cover = (
            f" ({prior_cover_days:g} días de cobertura estimada)"
            if prior_cover_days is not None
            else ""
        )
        return (
            "review_excess_stock",
            "Revisar: stock previo alto",
            f"Antes de esta compra había {stock_before:g} {unit}{cover}; supera el objetivo de "
            f"{target_cover_days} días por más del margen de tolerancia del análisis.",
        )

    if signal == "cantidad_superior_a_referencia":
        reference = suggested_quantity if suggested_quantity is not None else 0.0
        return (
            "review_above_reference",
            "Revisar: compra sobre referencia",
            f"Se compraron {quantity:g} {unit} frente a una referencia de reposición de "
            f"{reference:g} {unit}, calculada con ventas previas y stock estimado.",
        )

    reference = suggested_quantity if suggested_quantity is not None else 0.0
    return (
        "aligned_with_reference",
        "Alineada con referencia",
        f"La compra de {quantity:g} {unit} no supera la referencia de {reference:g} {unit}; "
        f"se observaron {prior_units:g} {unit} vendidos en los 180 días previos y "
        f"{stock_before:g} {unit} de stock previo estimado.",
    )


def normalize_purchase_assessment_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Upgrade persisted assessment payloads to the current product-verdict contract."""
    normalized = dict(metrics)
    totals = dict(metrics.get("totals") or {})
    summary = dict(metrics.get("assessment_summary") or {})
    parameters = dict(metrics.get("parameters") or {})
    window_days = max(1, int(parameters.get("ventana_velocidad_previa_dias") or 180))
    target_days = max(1, min(int(parameters.get("objetivo_cobertura_dias") or 45), 365))
    products = [dict(product) for product in (metrics.get("products") or [])]

    for product in products:
        quantity = _number(product.get("cantidad_comprada")) or 0.0
        prior_sales = _number(product.get("ventas_previas_180d_unidades")) or 0.0
        stock_before = _number(product.get("stock_previo_estimado"))
        daily_velocity = prior_sales / window_days
        target_units = daily_velocity * target_days
        suggested_quantity = _number(product.get("cantidad_referencia_objetivo"))
        if suggested_quantity is None and stock_before is not None:
            suggested_quantity = max(0.0, target_units - stock_before)
            product["cantidad_referencia_objetivo"] = _round(suggested_quantity)

        if stock_before is None:
            signal = "insufficient_evidence"
        elif quantity <= 0:
            signal = "cantidad_no_positiva"
        elif prior_sales <= 0:
            signal = "sin_ventas_previas_en_180d"
        elif stock_before > target_units * 1.2:
            signal = "stock_previo_estimado_superaba_objetivo"
        elif suggested_quantity is not None and quantity > suggested_quantity:
            signal = "cantidad_superior_a_referencia"
        else:
            signal = "cantidad_en_rango_de_referencia"

        verdict, label, reason = _purchase_verdict(
            signal=signal,
            quantity=quantity,
            unit=str(product.get("unidad") or "SIN_DATO"),
            prior_units=prior_sales,
            stock_before=stock_before,
            prior_cover_days=_number(product.get("cobertura_stock_previo_estimada_dias")),
            suggested_quantity=suggested_quantity,
            target_cover_days=target_days,
            stock_reconstructed_negative=bool(product.get("stock_reconstruido_negativo")),
        )
        product.update({
            "senal_deterministica": signal,
            "veredicto_compra": verdict,
            "veredicto_compra_etiqueta": label,
            "razon_veredicto_compra": reason,
        })

    product_count = int(_number(totals.get("productos_distintos")) or len(products))
    omitted_products = max(0, product_count - len(products))
    visible_product_value = sum(
        float(product.get("valor_lineas_compra_cop") or 0) for product in products
    )
    visible_product_exposures: list[float] = []
    exposure_complete = omitted_products == 0
    for product in products:
        exposure = _number(product.get("valor_exposicion_lineas_compra_cop"))
        if exposure is None:
            net_value = float(product.get("valor_lineas_compra_cop") or 0)
            line_count = int(_number(product.get("lineas_factura")) or 1)
            exposure = abs(net_value)
            if line_count > 1:
                exposure_complete = False
            product["valor_exposicion_lineas_compra_cop"] = _round(exposure)
        visible_product_exposures.append(exposure)
    stored_coded_value = _number(summary.get("valor_productos_codificados_cop"))
    if stored_coded_value is None and omitted_products:
        stored_coded_value = _number(summary.get("valor_lineas_compra_cop"))
    coded_value = (
        stored_coded_value if stored_coded_value is not None else visible_product_value
    )
    stored_coded_exposure = _number(
        summary.get("valor_exposicion_productos_codificados_cop")
    )
    if stored_coded_exposure is None:
        if omitted_products:
            exposure_complete = False
            coded_exposure = sum(visible_product_exposures)
        else:
            coded_exposure = sum(visible_product_exposures)
    else:
        coded_exposure = stored_coded_exposure
    line_value = _number(totals.get("total_lineas_cop"))
    if line_value is None:
        line_value = coded_value
    total_exposure = _number(totals.get("valor_exposicion_lineas_cop"))
    unclassified_value = _number(summary.get("valor_lineas_sin_codigo_producto_cop"))
    if unclassified_value is None and not omitted_products:
        unclassified_value = max(0.0, line_value - coded_value)
    uncoded_count = _number(totals.get("lineas_sin_codigo_producto"))
    if uncoded_count is None:
        uncoded_count = _number(summary.get("lineas_sin_codigo_producto"))
    uncoded_exposure = _number(
        summary.get("valor_exposicion_lineas_sin_codigo_producto_cop")
    )
    if uncoded_exposure is None:
        if uncoded_count in (None, 0):
            uncoded_exposure = 0.0 if uncoded_count == 0 else None
        elif uncoded_count == 1 and unclassified_value is not None:
            uncoded_exposure = abs(unclassified_value)
        else:
            exposure_complete = False
    if total_exposure is None:
        if exposure_complete and uncoded_exposure is not None:
            total_exposure = coded_exposure + uncoded_exposure
        else:
            exposure_complete = False
    elif total_exposure < 0:
        exposure_complete = False
    unknown_product_value = sum(
        float(product.get("valor_exposicion_lineas_compra_cop") or 0)
        for product in products
        if product["veredicto_compra"] == "not_evaluable"
    )
    unassessed_value = unknown_product_value + (uncoded_exposure or 0.0)
    if omitted_products and total_exposure is not None:
        unassessed_value += max(
            0.0,
            total_exposure - sum(visible_product_exposures) - (uncoded_exposure or 0.0),
        )

    review_verdicts = {
        "review_above_reference",
        "review_excess_stock",
        "review_no_prior_sales",
        "review_non_positive_quantity",
    }
    review_value = sum(
        float(product.get("valor_exposicion_lineas_compra_cop") or 0)
        for product in products
        if product["veredicto_compra"] in review_verdicts
    )
    risk_value = sum(
        float(product.get("valor_exposicion_lineas_compra_cop") or 0)
        for product in products
        if product["senal_deterministica"] in {
            "stock_previo_estimado_superaba_objetivo",
            "cantidad_superior_a_referencia",
        }
    )
    aligned_count = sum(
        product["veredicto_compra"] == "aligned_with_reference" for product in products
    )
    review_count = sum(
        product["veredicto_compra"] in review_verdicts for product in products
    )
    not_evaluable_count = sum(
        product["veredicto_compra"] == "not_evaluable" for product in products
    )
    uncoded_count_value = int(uncoded_count) if uncoded_count is not None else None

    if (
        not products
        or total_exposure is None
        or total_exposure <= 0
        or not exposure_complete
        or omitted_products > 0
        or unassessed_value / max(total_exposure, 1.0) >= 0.5
    ):
        overall_signal = "evidencia_insuficiente"
    elif review_value / total_exposure >= 0.5:
        overall_signal = "requiere_revision"
    elif review_value > 0 or unassessed_value > 0 or (uncoded_count_value or 0) > 0:
        overall_signal = "mixta_con_senales_de_revision"
    else:
        overall_signal = "alineada_con_evidencia_disponible"

    normalized["products"] = products
    totals.update({
        "lineas_sin_codigo_producto": uncoded_count_value,
        "productos_omitidos": omitted_products,
        "productos_mostrados": len(products),
    })
    summary.update({
        "senal_global": overall_signal,
        "skus_evaluados": len(products),
        "skus_sin_historial_previo_180d": sum(
            product["senal_deterministica"] == "sin_ventas_previas_en_180d"
            for product in products
        ),
        "skus_stock_previo_sobre_objetivo": sum(
            product["senal_deterministica"] == "stock_previo_estimado_superaba_objetivo"
            for product in products
        ),
        "skus_compra_sobre_referencia": sum(
            product["senal_deterministica"] == "cantidad_superior_a_referencia"
            for product in products
        ),
        "skus_cantidad_neta_no_positiva": sum(
            product["senal_deterministica"] == "cantidad_no_positiva"
            for product in products
        ),
        "skus_alineados_con_referencia": aligned_count,
        "skus_requieren_revision": review_count,
        "skus_no_evaluables": not_evaluable_count,
        "skus_omitidos_del_detalle": omitted_products,
        "lineas_sin_codigo_producto": uncoded_count_value,
        "valor_lineas_sin_codigo_producto_cop": _round(unclassified_value),
        "valor_exposicion_lineas_sin_codigo_producto_cop": _round(uncoded_exposure),
        "valor_productos_codificados_cop": _round(coded_value),
        "valor_exposicion_productos_codificados_cop": _round(coded_exposure),
        "valor_lineas_compra_cop": _round(line_value),
        "valor_base_exposicion_lineas_cop": _round(total_exposure),
        "valor_en_senales_de_revision_cop": _round(review_value),
        "porcentaje_valor_en_senales_de_revision": _round(
            review_value / total_exposure * 100
            if total_exposure and exposure_complete and not omitted_products
            else None,
            1,
        ),
        "valor_en_senales_cuantitativas_de_exceso_cop": _round(risk_value),
        "valor_sin_evidencia_suficiente_cop": _round(unassessed_value),
        "porcentaje_valor_sin_evidencia_suficiente": _round(
            unassessed_value / total_exposure * 100
            if total_exposure and exposure_complete and not omitted_products
            else None,
            1,
        ),
        "exposicion_completa": exposure_complete and not omitted_products,
    })
    normalized["totals"] = totals
    normalized["assessment_summary"] = summary
    normalized["parameters"] = parameters
    return normalized


def _fingerprint(header: dict[str, Any], lines: list[dict[str, Any]]) -> str:
    canonical = {
        "header": {key: _json_value(header.get(key)) for key in sorted(header)},
        "lines": [
            {key: _json_value(line.get(key)) for key in sorted(line)}
            for line in sorted(
                lines,
                key=lambda item: json.dumps(
                    {key: _json_value(item.get(key)) for key in sorted(item)},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        ],
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def discover_purchase_invoices(
    connection: Any,
    date_from: date = date(2026, 9, 1),
    *,
    limit: int = 100,
    after: tuple[date, str, str] | None = None,
) -> list[PurchaseInvoice]:
    """Load one valid-header page and its full-identity detail rows."""
    limit = max(1, min(int(limit), 1_000))
    cursor_clause = ""
    parameters: list[Any] = [date_from]
    if after is not None:
        cursor_date, cursor_class, cursor_document = after
        cursor_clause = """
          AND (
            business_date > ?
            OR (business_date = ? AND cod_clase > ?)
            OR (business_date = ? AND cod_clase = ? AND num_documento > ?)
          )
        """
        parameters.extend([
            cursor_date,
            cursor_date,
            cursor_class,
            cursor_date,
            cursor_class,
            cursor_document,
        ])
    parameters.append(limit)
    rows = connection.execute(
        f"""
        WITH ranked_headers AS (
          SELECT CAST(num_documento AS VARCHAR) AS num_documento,
                 CAST(cod_clase AS VARCHAR) AS cod_clase,
                 CAST(business_date AS DATE) AS business_date,
                 nit_proveedor,
                 nombre_proveedor,
                 total_factura,
                 estado_documento,
                 COUNT(*) OVER (
                   PARTITION BY num_documento, cod_clase, business_date
                 ) AS identity_count
          FROM silver_fact_compras
          WHERE CAST(business_date AS DATE) >= ?
            AND COALESCE(estado_documento, '') != 'A'
        ), valid_headers AS (
          SELECT num_documento, cod_clase, business_date, nit_proveedor,
                 nombre_proveedor, total_factura, estado_documento
          FROM ranked_headers
          WHERE identity_count = 1
        ), paged_headers AS (
          SELECT * FROM valid_headers
          WHERE 1 = 1
          {cursor_clause}
          ORDER BY business_date, cod_clase, num_documento
          LIMIT ?
        )
        SELECT h.num_documento, h.cod_clase, h.business_date,
               h.nit_proveedor, h.nombre_proveedor, h.total_factura,
               h.estado_documento,
               CAST(d.num_documento AS VARCHAR) AS detail_document,
               CAST(d.cod_producto AS VARCHAR) AS cod_producto,
               d.nombre_detalle, d.cantidad, d.valor_unitario,
               d.total_detalle, d.costo_producto
        FROM paged_headers h
        LEFT JOIN silver_fact_compras_detalle d
          ON CAST(d.num_documento AS VARCHAR) = h.num_documento
         AND CAST(d.cod_clase AS VARCHAR) = h.cod_clase
         AND CAST(d.business_date AS DATE) = h.business_date
        ORDER BY h.business_date, h.cod_clase, h.num_documento,
                 CAST(d.cod_producto AS VARCHAR), d.nombre_detalle
        """,
        parameters,
    ).fetchall()

    grouped: dict[tuple[date, str, str], tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for row in rows:
        identity = (row[2], row[1], row[0])
        header = {
            "num_documento": row[0],
            "cod_clase": row[1],
            "business_date": row[2],
            "nit_proveedor": row[3],
            "nombre_proveedor": row[4],
            "total_factura": row[5],
            "estado_documento": row[6],
        }
        if identity not in grouped:
            grouped[identity] = (header, [])
        if row[7] is not None:
            grouped[identity][1].append({
                "cod_producto": row[8],
                "nombre_detalle": row[9],
                "cantidad": row[10],
                "valor_unitario": row[11],
                "total_detalle": row[12],
                "costo_producto": row[13],
            })

    invoices = []
    for (business_date, cod_clase, num_documento), (header, lines) in grouped.items():
        invoices.append(PurchaseInvoice(
            business_date=business_date,
            cod_clase=cod_clase,
            num_documento=num_documento,
            header=header,
            lines=lines,
            content_fingerprint=_fingerprint(header, lines),
        ))
    return invoices


def _valid_header_cutoff(connection: Any, table: str) -> date | None:
    row = connection.execute(
        f"""
        SELECT MAX(business_date)
        FROM (
          SELECT business_date,
                 COUNT(*) OVER (
                   PARTITION BY num_documento, cod_clase, business_date
                 ) AS identity_count
          FROM {table}
          WHERE COALESCE(estado_documento, '') != 'A'
        ) valid
        WHERE identity_count = 1
        """
    ).fetchone()
    return row[0] if row else None


def _source_cutoffs(
    connection: Any,
    inventory_source: str,
) -> dict[str, date | str | None]:
    purchase_cutoff = _valid_header_cutoff(connection, "silver_fact_compras")
    sales_cutoff = _valid_header_cutoff(connection, "silver_fact_ventas")
    inventory_table = (
        "silver_dim_producto" if inventory_source == "catalog"
        else "gold_mart_inventario_actual"
    )
    inventory_row = connection.execute(
        f"SELECT MAX(snapshot_date) FROM {inventory_table}"
    ).fetchone()
    inventory_cutoff = inventory_row[0] if inventory_row else None
    abc_cutoff: date | str | None = None
    try:
        abc_row = connection.execute(
            "SELECT MAX(CAST(business_month AS VARCHAR)) FROM gold_mart_abc_xyz"
        ).fetchone()
        abc_cutoff = abc_row[0] if abc_row else None
    except Exception:
        # Some tenant snapshots do not yet include ABC; these SKUs remain unclassified.
        abc_cutoff = None
    return {
        "purchases": purchase_cutoff,
        "sales": sales_cutoff,
        "inventory": inventory_cutoff,
        "abc": abc_cutoff,
    }


def _daily_product_movements(
    connection: Any,
    *,
    header_table: str,
    detail_table: str,
    product_codes: list[str],
    cutoff: date | None,
) -> dict[str, list[tuple[date, float, float]]]:
    if not product_codes or cutoff is None:
        return {}
    placeholders = ",".join("?" for _ in product_codes)
    rows = connection.execute(
        f"""
        WITH ranked_headers AS (
          SELECT CAST(num_documento AS VARCHAR) AS num_documento,
                 CAST(cod_clase AS VARCHAR) AS cod_clase,
                 CAST(business_date AS DATE) AS business_date,
                 COUNT(*) OVER (
                   PARTITION BY num_documento, cod_clase, business_date
                 ) AS identity_count
          FROM {header_table}
          WHERE CAST(business_date AS DATE) <= ?
            AND COALESCE(estado_documento, '') != 'A'
        ), valid_headers AS (
          SELECT * FROM ranked_headers WHERE identity_count = 1
        )
        SELECT CAST(d.cod_producto AS VARCHAR), h.business_date,
               SUM(COALESCE(d.cantidad, 0)),
               SUM(COALESCE(d.total_detalle, 0))
        FROM {detail_table} d
        JOIN valid_headers h
          ON CAST(d.num_documento AS VARCHAR) = h.num_documento
         AND CAST(d.cod_clase AS VARCHAR) = h.cod_clase
         AND CAST(d.business_date AS DATE) = h.business_date
        WHERE CAST(d.cod_producto AS VARCHAR) IN ({placeholders})
        GROUP BY CAST(d.cod_producto AS VARCHAR), h.business_date
        ORDER BY CAST(d.cod_producto AS VARCHAR), h.business_date
        """,
        [cutoff, *product_codes],
    ).fetchall()
    movements: dict[str, list[tuple[date, float, float]]] = defaultdict(list)
    for code, movement_date, quantity, value in rows:
        movements[code].append((movement_date, float(quantity or 0), float(value or 0)))
    return movements


def _product_catalog(
    connection: Any, product_codes: list[str], inventory_source: str
) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    if not product_codes:
        return {}, {}
    placeholders = ",".join("?" for _ in product_codes)
    rows = connection.execute(
        f"""
        SELECT CAST(cod_producto AS VARCHAR),
               MAX(NULLIF(nombre_producto, '')),
               MAX(NULLIF(presentacion, '')),
               MAX(NULLIF(cod_medida, ''))
        FROM silver_dim_producto
        WHERE CAST(cod_producto AS VARCHAR) IN ({placeholders})
        GROUP BY CAST(cod_producto AS VARCHAR)
        """,
        product_codes,
    ).fetchall()
    catalog = {
        code: {
            "name": name,
            "unit": presentation or measure or "SIN_DATO",
        }
        for code, name, presentation, measure in rows
    }

    stock: dict[str, float] = {}
    inventory_table = (
        "silver_dim_producto" if inventory_source == "catalog"
        else "gold_mart_inventario_actual"
    )
    cutoff_row = connection.execute(
        f"SELECT MAX(snapshot_date) FROM {inventory_table}"
    ).fetchone()
    inventory_cutoff = cutoff_row[0] if cutoff_row else None
    if inventory_cutoff is None:
        return catalog, stock
    if inventory_source == "catalog":
        inventory_rows = connection.execute(
            f"""
            SELECT CAST(cod_producto AS VARCHAR), MAX(existencia)
            FROM silver_dim_producto
            WHERE snapshot_date = ?
              AND CAST(cod_producto AS VARCHAR) IN ({placeholders})
            GROUP BY CAST(cod_producto AS VARCHAR)
            """,
            [inventory_cutoff, *product_codes],
        ).fetchall()
    else:
        inventory_rows = connection.execute(
            f"""
            SELECT CAST(cod_producto AS VARCHAR), SUM(cantidad_actual)
            FROM gold_mart_inventario_actual
            WHERE snapshot_date = ?
              AND CAST(cod_producto AS VARCHAR) IN ({placeholders})
            GROUP BY CAST(cod_producto AS VARCHAR)
            """,
            [inventory_cutoff, *product_codes],
        ).fetchall()
    stock.update({
        code: float(quantity)
        for code, quantity in inventory_rows
        if quantity is not None
    })
    return catalog, stock


def _later_purchase_movements(
    connection: Any,
    product_codes: list[str],
    purchase_date: date,
    inventory_cutoff: date | None,
) -> dict[str, float]:
    if not product_codes or inventory_cutoff is None or purchase_date > inventory_cutoff:
        return {}
    placeholders = ",".join("?" for _ in product_codes)
    rows = connection.execute(
        f"""
        WITH ranked_headers AS (
          SELECT CAST(num_documento AS VARCHAR) AS num_documento,
                 CAST(cod_clase AS VARCHAR) AS cod_clase,
                 CAST(business_date AS DATE) AS business_date,
                 COUNT(*) OVER (
                   PARTITION BY num_documento, cod_clase, business_date
                 ) AS identity_count
          FROM silver_fact_compras
          WHERE CAST(business_date AS DATE) >= ?
            AND CAST(business_date AS DATE) <= ?
            AND COALESCE(estado_documento, '') != 'A'
        ), valid_headers AS (
          SELECT * FROM ranked_headers WHERE identity_count = 1
        )
        SELECT CAST(d.cod_producto AS VARCHAR), SUM(COALESCE(d.cantidad, 0))
        FROM silver_fact_compras_detalle d
        JOIN valid_headers h
          ON CAST(d.num_documento AS VARCHAR) = h.num_documento
         AND CAST(d.cod_clase AS VARCHAR) = h.cod_clase
         AND CAST(d.business_date AS DATE) = h.business_date
        WHERE CAST(d.cod_producto AS VARCHAR) IN ({placeholders})
        GROUP BY CAST(d.cod_producto AS VARCHAR)
        """,
        [purchase_date, inventory_cutoff, *product_codes],
    ).fetchall()
    return {code: float(quantity or 0) for code, quantity in rows}


def _abc_classification(
    connection: Any, product_codes: list[str], purchase_month: str
) -> dict[str, tuple[str, str] | None]:
    if not product_codes:
        return {}
    try:
        placeholders = ",".join("?" for _ in product_codes)
        rows = connection.execute(
            f"""
            SELECT CAST(cod_producto AS VARCHAR), CAST(business_month AS VARCHAR), categoria_abc
            FROM gold_mart_abc_xyz
            WHERE CAST(cod_producto AS VARCHAR) IN ({placeholders})
              AND SUBSTR(CAST(business_month AS VARCHAR), 1, 7) <= ?
            QUALIFY ROW_NUMBER() OVER (
              PARTITION BY CAST(cod_producto AS VARCHAR)
              ORDER BY SUBSTR(CAST(business_month AS VARCHAR), 1, 7) DESC
            ) = 1
            """,
            [*product_codes, purchase_month],
        ).fetchall()
    except Exception:
        return {code: None for code in product_codes}
    classifications = {
        code: (str(category), str(month)[:7])
        for code, month, category in rows
        if category is not None
    }
    return {code: classifications.get(code) for code in product_codes}


def analyze_purchase_invoice(
    connection: Any,
    invoice: PurchaseInvoice,
    *,
    inventory_source: str = "gold",
    target_cover_days: int = DEFAULT_TARGET_COVER_DAYS,
) -> dict[str, Any]:
    """Calculate invoice/product evidence, including explicitly estimated historic stock."""
    if inventory_source not in {"gold", "catalog"}:
        raise ValueError("inventory_source debe ser 'gold' o 'catalog'.")
    target_cover_days = max(1, min(int(target_cover_days), 365))
    cutoffs = _source_cutoffs(connection, inventory_source)
    product_codes = sorted({
        str(line["cod_producto"]).strip()
        for line in invoice.lines
        if line.get("cod_producto") is not None and str(line["cod_producto"]).strip()
    })
    catalog, current_stock = _product_catalog(connection, product_codes, inventory_source)
    sales_cutoff = cutoffs["sales"]
    inventory_cutoff = cutoffs["inventory"]
    sales_movements = _daily_product_movements(
        connection,
        header_table="silver_fact_ventas",
        detail_table="silver_fact_ventas_detalle",
        product_codes=product_codes,
        cutoff=sales_cutoff,
    )
    purchase_movements = _later_purchase_movements(
        connection, product_codes, invoice.business_date, inventory_cutoff
    )
    classifications = _abc_classification(
        connection, product_codes, invoice.business_date.strftime("%Y-%m")
    )

    groups: dict[str, dict[str, Any]] = {}
    line_total = 0.0
    line_exposure_value = 0.0
    source_line_count = len(invoice.lines)
    line_total_derived_count = 0
    lines_without_product_code = 0
    value_without_product_code = 0.0
    exposure_without_product_code = 0.0
    for line in invoice.lines:
        quantity = _number(line.get("cantidad")) or 0.0
        unit_price = _number(line.get("valor_unitario"))
        raw_total = _number(line.get("total_detalle"))
        if raw_total is None:
            raw_total = quantity * unit_price if unit_price is not None else 0.0
            line_total_derived_count += 1
        line_total += raw_total
        line_exposure_value += abs(raw_total)
        code_value = line.get("cod_producto")
        if code_value is None or not str(code_value).strip():
            lines_without_product_code += 1
            value_without_product_code += raw_total
            exposure_without_product_code += abs(raw_total)
            continue
        code = str(code_value).strip()
        item = groups.setdefault(code, {
            "quantity": 0.0,
            "purchase_amount": 0.0,
            "purchase_amount_abs": 0.0,
            "purchase_unit_price_weighted": 0.0,
            "purchase_unit_price_quantity": 0.0,
            "unit_cost_weighted": 0.0,
            "unit_cost_quantity": 0.0,
            "line_count": 0,
        })
        item["quantity"] += quantity
        item["purchase_amount"] += raw_total
        item["purchase_amount_abs"] += abs(raw_total)
        item["line_count"] += 1
        if unit_price is not None:
            item["purchase_unit_price_weighted"] += unit_price * quantity
            item["purchase_unit_price_quantity"] += quantity
        unit_cost = _number(line.get("costo_producto"))
        if unit_cost is not None:
            item["unit_cost_weighted"] += unit_cost * quantity
            item["unit_cost_quantity"] += quantity

    header_total = _number(invoice.header.get("total_factura"))
    mismatch = header_total - line_total if header_total is not None else None
    products: list[dict[str, Any]] = []
    quantity_by_unit: dict[str, float] = defaultdict(float)
    for code, grouped in groups.items():
        details = catalog.get(code, {})
        unit = str(details.get("unit") or "SIN_DATO")[:80]
        quantity = grouped["quantity"]
        daily_sales_before = [
            (movement_date, units, value)
            for movement_date, units, value in sales_movements.get(code, [])
            if invoice.business_date - timedelta(days=180) <= movement_date < invoice.business_date
        ]
        prior_units = sum(units for _, units, _ in daily_sales_before)
        daily_velocity = prior_units / 180
        post_sales = [
            (movement_date, units, value)
            for movement_date, units, value in sales_movements.get(code, [])
            if movement_date > invoice.business_date
        ]
        later_sales_units = sum(units for _, units, _ in post_sales)
        later_sales_revenue = sum(value for _, _, value in post_sales)
        sales_on_or_after_purchase_day = [
            (movement_date, units, value)
            for movement_date, units, value in sales_movements.get(code, [])
            if inventory_cutoff is not None
            and invoice.business_date <= movement_date <= inventory_cutoff
        ]
        stock_now = current_stock.get(code)
        later_purchased = purchase_movements.get(code, 0.0)
        reconstructed_stock_before_day = (
            stock_now - later_purchased
            + sum(units for _, units, _ in sales_on_or_after_purchase_day)
            if stock_now is not None and inventory_cutoff is not None
            and invoice.business_date <= inventory_cutoff
            else None
        )
        stock_before_estimate = (
            reconstructed_stock_before_day
            if reconstructed_stock_before_day is not None
            and reconstructed_stock_before_day >= 0
            else None
        )
        unit_cost = (
            grouped["unit_cost_weighted"] / grouped["unit_cost_quantity"]
            if grouped["unit_cost_quantity"] else None
        )
        unit_price = (
            grouped["purchase_unit_price_weighted"] / grouped["purchase_unit_price_quantity"]
            if grouped["purchase_unit_price_quantity"] else None
        )
        margin_cost = unit_cost if unit_cost is not None else unit_price
        margin_cost_source = (
            "costo_producto" if unit_cost is not None
            else "valor_unitario_factura" if unit_price is not None
            else None
        )
        buy_cover_days = quantity / daily_velocity if daily_velocity > 0 else None
        pre_purchase_cover_days = (
            stock_before_estimate / daily_velocity
            if stock_before_estimate is not None and daily_velocity > 0
            else None
        )
        current_stock_date = min(
            (cutoff for cutoff in (sales_cutoff, inventory_cutoff) if cutoff is not None),
            default=None,
        )
        recent_sales_180 = [
            (movement_date, units, value)
            for movement_date, units, value in sales_movements.get(code, [])
            if current_stock_date is not None
            and current_stock_date - timedelta(days=179)
            <= movement_date <= current_stock_date
        ]
        current_velocity = sum(units for _, units, _ in recent_sales_180) / 180
        current_cover = (
            stock_now / current_velocity
            if stock_now is not None and current_velocity > 0
            else None
        )
        target_units = daily_velocity * target_cover_days
        suggested_quantity = (
            max(0.0, target_units - stock_before_estimate)
            if stock_before_estimate is not None else None
        )
        abc = classifications.get(code)
        margin_proxy = None
        if margin_cost is not None and later_sales_revenue > 0:
            margin_proxy = (
                (later_sales_revenue - later_sales_units * margin_cost)
                / later_sales_revenue
                * 100
            )
        if stock_before_estimate is None:
            purchase_signal = "insufficient_evidence"
        elif quantity <= 0:
            purchase_signal = "cantidad_no_positiva"
        elif prior_units <= 0:
            purchase_signal = "sin_ventas_previas_en_180d"
        elif stock_before_estimate > target_units * 1.2:
            purchase_signal = "stock_previo_estimado_superaba_objetivo"
        elif suggested_quantity is not None and quantity > suggested_quantity:
            purchase_signal = "cantidad_superior_a_referencia"
        else:
            purchase_signal = "cantidad_en_rango_de_referencia"
        purchase_verdict, purchase_verdict_label, purchase_verdict_reason = _purchase_verdict(
            signal=purchase_signal,
            quantity=quantity,
            unit=unit,
            prior_units=prior_units,
            stock_before=stock_before_estimate,
            prior_cover_days=pre_purchase_cover_days,
            suggested_quantity=suggested_quantity,
            target_cover_days=target_cover_days,
            stock_reconstructed_negative=(
                reconstructed_stock_before_day is not None
                and reconstructed_stock_before_day < 0
            ),
        )
        products.append({
            "cod_producto": code[:100],
            "nombre": str(
                details.get("name")
                or next(
                    (
                        line.get("nombre_detalle")
                        for line in invoice.lines
                        if str(line.get("cod_producto") or "").strip() == code
                        and line.get("nombre_detalle")
                    ),
                    code,
                )
            )[:180],
            "unidad": unit,
            "lineas_factura": grouped["line_count"],
            "cantidad_comprada": _round(quantity),
            "valor_lineas_compra_cop": _round(grouped["purchase_amount"]),
            "valor_exposicion_lineas_compra_cop": _round(grouped["purchase_amount_abs"]),
            "precio_unitario_compra_promedio_cop": _round(unit_price, 4),
            "costo_producto_unitario_promedio_cop": _round(unit_cost, 4),
            "costo_unitario_referencia_margen_cop": _round(margin_cost, 4),
            "fuente_costo_margen": margin_cost_source,
            "abc_categoria": abc[0] if abc else None,
            "abc_mes_clasificacion": abc[1] if abc else None,
            "abc_etiqueta": abc[0] if abc else "sin clasificación",
            "ventas_previas_180d_unidades": _round(prior_units),
            "velocidad_previa_diaria_unidades": _round(daily_velocity, 4),
            "cobertura_cantidad_comprada_dias": _round(buy_cover_days, 1),
            "stock_actual": _round(stock_now),
            "inventory_controlled": stock_now is not None,
            "control_evidence": (
                "inventory_snapshot" if stock_now is not None else "insufficient_evidence"
            ),
            "stock_previo_estimado": _round(stock_before_estimate),
            "stock_reconstruido_negativo": (
                reconstructed_stock_before_day is not None
                and reconstructed_stock_before_day < 0
            ),
            "stock_estimado_despues_de_compra": (
                _round(stock_before_estimate + quantity)
                if stock_before_estimate is not None else None
            ),
            "cobertura_stock_previo_estimada_dias": _round(pre_purchase_cover_days, 1),
            "cantidad_referencia_objetivo": _round(suggested_quantity),
            "cobertura_stock_actual_dias": _round(current_cover, 1),
            "ventas_posteriores_hasta_corte_unidades": _round(later_sales_units),
            "ingresos_posteriores_hasta_corte_cop": _round(later_sales_revenue),
            "primera_venta_posterior": _as_iso(min((d for d, _, _ in post_sales), default=None)),
            "ultima_venta_posterior": _as_iso(max((d for d, _, _ in post_sales), default=None)),
            "margen_bruto_referencia_pct": _round(margin_proxy, 1),
            "senal_deterministica": purchase_signal,
            "veredicto_compra": purchase_verdict,
            "veredicto_compra_etiqueta": purchase_verdict_label,
            "razon_veredicto_compra": purchase_verdict_reason,
        })
        quantity_by_unit[unit] += quantity

    products.sort(
        key=lambda product: (
            product["valor_lineas_compra_cop"] or 0,
            product["cantidad_comprada"] or 0,
        ),
        reverse=True,
    )
    risk_signals = {
        "stock_previo_estimado_superaba_objetivo",
        "cantidad_superior_a_referencia",
    }
    uncertain_signals = {
        "insufficient_evidence",
    }
    coded_line_value = sum(
        float(product["valor_lineas_compra_cop"] or 0) for product in products
    )
    coded_exposure_value = sum(
        float(product["valor_exposicion_lineas_compra_cop"] or 0) for product in products
    )
    risk_value = sum(
        float(product["valor_exposicion_lineas_compra_cop"] or 0)
        for product in products
        if product["senal_deterministica"] in risk_signals
    )
    uncertain_value = sum(
        float(product["valor_exposicion_lineas_compra_cop"] or 0)
        for product in products
        if product["senal_deterministica"] in uncertain_signals
    )
    unassessed_value = uncertain_value + exposure_without_product_code
    review_verdicts = {
        "review_above_reference",
        "review_excess_stock",
        "review_no_prior_sales",
        "review_non_positive_quantity",
    }
    review_value = sum(
        float(product["valor_exposicion_lineas_compra_cop"] or 0)
        for product in products
        if product["veredicto_compra"] in review_verdicts
    )
    aligned_count = sum(
        product["veredicto_compra"] == "aligned_with_reference" for product in products
    )
    review_count = sum(product["veredicto_compra"] in review_verdicts for product in products)
    not_evaluable_count = sum(
        product["veredicto_compra"] == "not_evaluable" for product in products
    )
    if (
        not products
        or line_exposure_value <= 0
        or unassessed_value / max(line_exposure_value, 1.0) >= 0.5
    ):
        overall_signal = "evidencia_insuficiente"
    elif review_value / line_exposure_value >= 0.5:
        overall_signal = "requiere_revision"
    elif review_value > 0 or unassessed_value > 0 or lines_without_product_code > 0:
        overall_signal = "mixta_con_senales_de_revision"
    else:
        overall_signal = "alineada_con_evidencia_disponible"
    assessment_summary = {
        "senal_global": overall_signal,
        "skus_evaluados": len(products),
        "skus_con_evidencia_de_demanda_y_stock": sum(
            product["ventas_previas_180d_unidades"] is not None
            and product["stock_previo_estimado"] is not None
            for product in products
        ),
        "skus_sin_historial_previo_180d": sum(
            product["senal_deterministica"] == "sin_ventas_previas_en_180d"
            for product in products
        ),
        "skus_stock_previo_sobre_objetivo": sum(
            product["senal_deterministica"] == "stock_previo_estimado_superaba_objetivo"
            for product in products
        ),
        "skus_compra_sobre_referencia": sum(
            product["senal_deterministica"] == "cantidad_superior_a_referencia"
            for product in products
        ),
        "skus_cantidad_neta_no_positiva": sum(
            product["senal_deterministica"] == "cantidad_no_positiva"
            for product in products
        ),
        "skus_alineados_con_referencia": aligned_count,
        "skus_requieren_revision": review_count,
        "skus_no_evaluables": not_evaluable_count,
        "lineas_sin_codigo_producto": lines_without_product_code,
        "valor_lineas_sin_codigo_producto_cop": _round(value_without_product_code),
        "valor_exposicion_lineas_sin_codigo_producto_cop": _round(
            exposure_without_product_code
        ),
        "valor_productos_codificados_cop": _round(coded_line_value),
        "valor_exposicion_productos_codificados_cop": _round(coded_exposure_value),
        "valor_lineas_compra_cop": _round(line_total),
        "valor_base_exposicion_lineas_cop": _round(line_exposure_value),
        "valor_en_senales_de_revision_cop": _round(review_value),
        "porcentaje_valor_en_senales_de_revision": _round(
            review_value / line_exposure_value * 100 if line_exposure_value else None, 1
        ),
        "valor_en_senales_cuantitativas_de_exceso_cop": _round(risk_value),
        "valor_sin_evidencia_suficiente_cop": _round(unassessed_value),
        "porcentaje_valor_sin_evidencia_suficiente": _round(
            unassessed_value / line_exposure_value * 100 if line_exposure_value else None, 1
        ),
        "limitacion": (
            "La alineación es una referencia de reposición según ventas previas y stock estimado; "
            "las líneas sin código quedan sin asignación a SKU; la conclusión no demuestra "
            "rentabilidad ni conveniencia contable. Los porcentajes de revisión se ponderan por "
            "exposición bruta absoluta de líneas y no atribuyen causalidad a ventas posteriores."
        ),
    }
    visible_products = products[:MAX_STORED_PRODUCT_RESULTS]
    metrics: dict[str, Any] = {
        "invoice": {
            "business_date": invoice.business_date.isoformat(),
            "cod_clase": invoice.cod_clase,
            "num_documento": invoice.num_documento,
            "nit_proveedor": str(invoice.header.get("nit_proveedor") or "")[:80] or None,
            "nombre_proveedor": str(invoice.header.get("nombre_proveedor") or "")[:180] or None,
            "total_factura_cop": _round(header_total),
            "estado_documento": invoice.header.get("estado_documento"),
        },
        "totals": {
            "lineas_factura": source_line_count,
            "lineas_sin_codigo_producto": lines_without_product_code,
            "productos_distintos": len(groups),
            "productos_mostrados": len(visible_products),
            "productos_omitidos": max(0, len(products) - len(visible_products)),
            "cantidad_comprada_por_unidad": {
                key: _round(value) for key, value in sorted(quantity_by_unit.items())
            },
            "total_lineas_cop": _round(line_total),
            "lineas_total_calculado_por_cantidad_precio": line_total_derived_count,
            "diferencia_factura_menos_lineas_cop": _round(mismatch),
            "valor_exposicion_lineas_cop": _round(line_exposure_value),
            "diferencia_factura_menos_lineas_pct": (
                _round(mismatch / abs(header_total) * 100, 2)
                if mismatch is not None and header_total else None
            ),
        },
        "assessment_summary": assessment_summary,
        "parameters": {
            "ventana_velocidad_previa_dias": 180,
            "ventana_cobertura_actual_dias": 180,
            "objetivo_cobertura_dias": target_cover_days,
            "fuente_inventario": (
                "silver_dim_producto.existencia" if inventory_source == "catalog"
                else "gold_mart_inventario_actual.cantidad_actual"
            ),
        },
        "source_cutoffs": {
            key: _as_iso(value) for key, value in cutoffs.items()
        },
        "products": visible_products,
        "evidence_notes": [
            (
                "Las ventas posteriores describen movimientos del SKU tras la fecha de compra; "
                "no demuestran que esta factura las haya causado ni que las unidades vendidas "
                "provengan de ella."
            ),
            (
                "El stock previo es una reconstrucción estimada al inicio del día de compra: "
                "snapshot actual - compras + ventas registradas desde esa fecha hasta el corte. "
                "No se conoce el orden intradía entre facturas y faltan ajustes, traslados, "
                "devoluciones y posibles diferencias de integridad; reconstrucciones negativas "
                "se marcan como evidencia insuficiente."
            ),
            (
                "La cantidad de referencia usa ventas de los 180 días calendario previos y un "
                "objetivo de cobertura de 45 días; no incorpora lead time, mínimos, estacionalidad "
                "ni órdenes abiertas."
            ),
            (
                "El margen de referencia, cuando aparece, compara ingresos observados del SKU "
                "después de la compra con costo_producto o precio unitario de factura disponible; "
                "no es margen contable ni atribución por lote."
            ),
            (
                "La categoría ABC usa la última clasificación cuyo mes no supera el mes de "
                "compra; si no existe una fila elegible, se informa sin clasificación."
            ),
            (
                "La comparación factura-líneas es aritmética; impuestos, descuentos, fletes u "
                "otros conceptos pueden explicar diferencias legítimas."
            ),
        ],
    }
    return metrics
