from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


DB_PATH = Path("/tmp/codex_motoshop_gold_20260910.duckdb")
OUTPUT_DIR = Path("outputs/motoshop_factura_13_2024-07-27_20260910")
DATA_DIR = OUTPUT_DIR / "analysis_data"
PURCHASE_TS = pd.Timestamp("2024-07-27 15:40:22")


def scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)

    max_sale_ts = pd.Timestamp(
        scalar(
            con,
            "SELECT MAX(fecha_documento_ts) FROM silver_fact_ventas "
            "WHERE estado_documento = 'B'",
        )
    )
    as_of_date = max_sale_ts.normalize()

    sku = con.execute(
        f"""
        WITH invoice AS (
            SELECT
                cod_producto,
                MIN(nombre_detalle) AS nombre_factura,
                COUNT(*) AS lineas_factura,
                SUM(cantidad) AS cantidad_comprada,
                SUM(total_detalle) AS costo_factura,
                SUM(total_detalle) / NULLIF(SUM(cantidad), 0) AS costo_unitario_factura
            FROM silver_fact_compras_detalle
            WHERE num_documento = '13' AND cod_clase = 'S18'
            GROUP BY cod_producto
        ),
        sales AS (
            SELECT
                d.cod_producto,
                SUM(d.cantidad) AS unidades_vendidas_desde,
                SUM(d.total_detalle) AS ventas_desde,
                SUM(d.costo_producto * d.cantidad) AS costo_ventas_desde,
                COUNT(DISTINCT h.num_documento || '|' || h.cod_clase) AS facturas_venta_desde,
                COUNT(DISTINCT h.business_date) AS dias_con_venta_desde,
                MIN(h.fecha_documento_ts) AS primera_venta_desde,
                MAX(h.fecha_documento_ts) AS ultima_venta_desde,
                SUM(CASE WHEN h.business_date >= DATE '{(as_of_date - pd.Timedelta(days=29)).date()}' THEN d.cantidad ELSE 0 END) AS unidades_30d,
                SUM(CASE WHEN h.business_date >= DATE '{(as_of_date - pd.Timedelta(days=89)).date()}' THEN d.cantidad ELSE 0 END) AS unidades_90d,
                SUM(CASE WHEN h.business_date >= DATE '{(as_of_date - pd.Timedelta(days=364)).date()}' THEN d.cantidad ELSE 0 END) AS unidades_365d,
                SUM(CASE WHEN h.business_date >= DATE '{(as_of_date - pd.Timedelta(days=364)).date()}' THEN d.total_detalle ELSE 0 END) AS ventas_365d
            FROM silver_fact_ventas_detalle d
            JOIN silver_fact_ventas h USING (num_documento, cod_clase)
            JOIN invoice i USING (cod_producto)
            WHERE h.estado_documento = 'B'
              AND h.fecha_documento_ts > TIMESTAMP '{PURCHASE_TS}'
            GROUP BY d.cod_producto
        ),
        later_purchases AS (
            SELECT
                d.cod_producto,
                SUM(d.cantidad) AS unidades_compradas_despues,
                SUM(d.total_detalle) AS compras_despues,
                COUNT(DISTINCT h.num_documento || '|' || h.cod_clase) AS documentos_compra_despues,
                MAX(h.business_date) AS ultima_compra_despues
            FROM silver_fact_compras_detalle d
            JOIN silver_fact_compras h USING (num_documento, cod_clase)
            JOIN invoice i USING (cod_producto)
            WHERE h.estado_documento = 'B'
              AND h.business_date > DATE '2024-07-27'
            GROUP BY d.cod_producto
        ),
        current_inventory AS (
            SELECT cod_producto, SUM(cantidad_actual) AS stock_actual
            FROM gold_mart_inventario_actual
            GROUP BY cod_producto
        )
        SELECT
            i.cod_producto,
            COALESCE(p.nombre_producto, i.nombre_factura) AS producto,
            i.nombre_factura,
            i.lineas_factura,
            i.cantidad_comprada,
            i.costo_unitario_factura,
            i.costo_factura,
            COALESCE(ci.stock_actual, 0) AS stock_actual,
            p.costo_ultima_compra AS costo_ultima_compra,
            p.precio_venta_con_iva AS precio_venta_actual,
            p.cod_grupo,
            p.cod_linea1,
            COALESCE(s.unidades_vendidas_desde, 0) AS unidades_vendidas_desde,
            COALESCE(s.ventas_desde, 0) AS ventas_desde,
            COALESCE(s.costo_ventas_desde, 0) AS costo_ventas_desde,
            COALESCE(s.facturas_venta_desde, 0) AS facturas_venta_desde,
            COALESCE(s.dias_con_venta_desde, 0) AS dias_con_venta_desde,
            s.primera_venta_desde,
            s.ultima_venta_desde,
            COALESCE(s.unidades_30d, 0) AS unidades_30d,
            COALESCE(s.unidades_90d, 0) AS unidades_90d,
            COALESCE(s.unidades_365d, 0) AS unidades_365d,
            COALESCE(s.ventas_365d, 0) AS ventas_365d,
            COALESCE(lp.unidades_compradas_despues, 0) AS unidades_compradas_despues,
            COALESCE(lp.compras_despues, 0) AS compras_despues,
            COALESCE(lp.documentos_compra_despues, 0) AS documentos_compra_despues,
            lp.ultima_compra_despues
        FROM invoice i
        LEFT JOIN silver_dim_producto p USING (cod_producto)
        LEFT JOIN sales s USING (cod_producto)
        LEFT JOIN later_purchases lp USING (cod_producto)
        LEFT JOIN current_inventory ci USING (cod_producto)
        ORDER BY i.costo_factura DESC, i.cod_producto
        """
    ).fetchdf()

    for col in ["primera_venta_desde", "ultima_venta_desde", "ultima_compra_despues"]:
        sku[col] = pd.to_datetime(sku[col], errors="coerce")

    sku["absorcion_unidades"] = np.minimum(
        sku["cantidad_comprada"], sku["unidades_vendidas_desde"]
    )
    sku["sell_through_aparente"] = (
        sku["absorcion_unidades"] / sku["cantidad_comprada"]
    ).clip(0, 1)
    sku["remanente_minimo_unidades"] = np.minimum(
        sku["stock_actual"].clip(lower=0),
        (sku["cantidad_comprada"] - sku["unidades_vendidas_desde"]).clip(lower=0),
    )
    sku["remanente_minimo_costo"] = (
        sku["remanente_minimo_unidades"] * sku["costo_unitario_factura"]
    )
    sku["costo_absorbido_aparente"] = (
        sku["absorcion_unidades"] * sku["costo_unitario_factura"]
    )
    sku["precio_venta_promedio"] = np.where(
        sku["unidades_vendidas_desde"] > 0,
        sku["ventas_desde"] / sku["unidades_vendidas_desde"],
        np.nan,
    )
    sku["ingreso_cohorte_estimado"] = (
        sku["absorcion_unidades"] * sku["precio_venta_promedio"].fillna(0)
    )
    sku["utilidad_bruta_cohorte_estimada"] = (
        sku["ingreso_cohorte_estimado"] - sku["costo_absorbido_aparente"]
    )
    sku["margen_cohorte_estimado"] = np.where(
        sku["ingreso_cohorte_estimado"] > 0,
        sku["utilidad_bruta_cohorte_estimada"] / sku["ingreso_cohorte_estimado"],
        np.nan,
    )
    sku["valor_stock_a_costo_factura"] = (
        sku["stock_actual"].clip(lower=0) * sku["costo_unitario_factura"]
    )
    sku["valor_venta_potencial_stock"] = (
        sku["stock_actual"].clip(lower=0) * sku["precio_venta_actual"].fillna(0)
    )
    sku["dias_hasta_primera_venta"] = (
        sku["primera_venta_desde"] - PURCHASE_TS
    ).dt.total_seconds().div(86400).round(1)
    sku["dias_sin_venta"] = (
        max_sale_ts - sku["ultima_venta_desde"]
    ).dt.total_seconds().div(86400).round(0)

    sell_through = sku["sell_through_aparente"]
    sku["banda_sell_through"] = np.select(
        [
            sell_through.eq(0),
            sell_through.gt(0) & sell_through.lt(0.5),
            sell_through.ge(0.5) & sell_through.lt(0.8),
            sell_through.ge(0.8) & sell_through.lt(1),
            sell_through.ge(1),
        ],
        ["0%", "1-49%", "50-79%", "80-99%", "100%"],
        default="Sin dato",
    )

    def classify(row: pd.Series) -> str:
        if row.stock_actual < 0:
            return "Stock negativo"
        if row.stock_actual <= 0:
            return "Sin stock actual"
        if row.unidades_vendidas_desde <= 0:
            return "Sin ventas desde compra"
        if row.unidades_365d <= 0:
            return "Con stock, sin ventas 365d"
        if row.sell_through_aparente < 0.5:
            return "Rotación baja"
        if row.sell_through_aparente < 1:
            return "Rotación media"
        return "Compra absorbida; stock repuesto"

    sku["estado_auditoria"] = sku.apply(classify, axis=1)

    band_order = ["0%", "1-49%", "50-79%", "80-99%", "100%"]
    band = (
        sku.groupby("banda_sell_through", observed=False)
        .agg(
            skus=("cod_producto", "count"),
            unidades_compradas=("cantidad_comprada", "sum"),
            costo_factura=("costo_factura", "sum"),
            stock_actual=("stock_actual", "sum"),
            remanente_minimo_unidades=("remanente_minimo_unidades", "sum"),
            remanente_minimo_costo=("remanente_minimo_costo", "sum"),
        )
        .reindex(band_order)
        .reset_index()
    )
    band["porcentaje_costo_factura"] = band["costo_factura"] / sku["costo_factura"].sum()

    state = (
        sku.groupby("estado_auditoria")
        .agg(
            skus=("cod_producto", "count"),
            costo_factura=("costo_factura", "sum"),
            stock_actual=("stock_actual", "sum"),
            valor_stock_a_costo_factura=("valor_stock_a_costo_factura", "sum"),
        )
        .sort_values("costo_factura", ascending=False)
        .reset_index()
    )

    monthly = con.execute(
        f"""
        WITH invoice AS (
            SELECT DISTINCT cod_producto
            FROM silver_fact_compras_detalle
            WHERE num_documento='13' AND cod_clase='S18'
        )
        SELECT
            DATE_TRUNC('month', h.business_date)::DATE AS mes,
            SUM(d.cantidad) AS unidades,
            SUM(d.total_detalle) AS ventas,
            SUM(d.total_detalle - d.costo_producto * d.cantidad) AS utilidad_bruta,
            COUNT(DISTINCT h.num_documento || '|' || h.cod_clase) AS facturas
        FROM silver_fact_ventas_detalle d
        JOIN silver_fact_ventas h USING (num_documento, cod_clase)
        JOIN invoice i USING (cod_producto)
        WHERE h.estado_documento='B'
          AND h.fecha_documento_ts > TIMESTAMP '{PURCHASE_TS}'
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchdf()
    monthly["mes"] = pd.to_datetime(monthly["mes"])

    top_risk = sku[
        (sku["stock_actual"] > 0)
        & ((sku["unidades_365d"] <= 0) | (sku["sell_through_aparente"] < 0.5))
    ].sort_values(
        ["valor_stock_a_costo_factura", "dias_sin_venta"], ascending=[False, False]
    ).head(25)
    all_risk = sku[
        (sku["stock_actual"] > 0)
        & ((sku["unidades_365d"] <= 0) | (sku["sell_through_aparente"] < 0.5))
    ].sort_values(["valor_stock_a_costo_factura", "dias_sin_venta"], ascending=[False, False])
    current_exposure = sku[sku["stock_actual"] > 0].sort_values(
        "valor_stock_a_costo_factura", ascending=False
    )
    top_performers = sku[sku["unidades_vendidas_desde"] > 0].sort_values(
        ["utilidad_bruta_cohorte_estimada", "ventas_desde"], ascending=False
    ).head(25)

    invoice_total = float(sku["costo_factura"].sum())
    estimated_revenue = float(sku["ingreso_cohorte_estimado"].sum())
    estimated_gp = float(sku["utilidad_bruta_cohorte_estimada"].sum())
    low_rotation = sku[sku["sell_through_aparente"] < 0.5]
    unabsorbed_units = float(
        sku["cantidad_comprada"].sum() - sku["absorcion_unidades"].sum()
    )
    unabsorbed_cost = float(invoice_total - sku["costo_absorbido_aparente"].sum())
    summary = {
        "source": {
            "database": "Cloudflare R2 / motoshop_gold.duckdb",
            "downloaded_at_local": datetime.fromtimestamp(DB_PATH.stat().st_mtime).astimezone().isoformat(),
            "latest_sale_timestamp": max_sale_ts.isoformat(),
            "inventory_snapshot_date": str(
                scalar(con, "SELECT MAX(snapshot_date) FROM gold_mart_inventario_actual")
            ),
            "latest_purchase_date": str(
                scalar(
                    con,
                    "SELECT MAX(business_date) FROM silver_fact_compras WHERE estado_documento='B'",
                )
            ),
        },
        "invoice": {
            "num_documento": "13",
            "cod_clase": "S18",
            "purchase_timestamp": PURCHASE_TS.isoformat(),
            "supplier": "KAROL NATALIA BURGOS BUSTOS",
            "supplier_nit": "1116274616",
            "payment_method": "F06",
            "status": "B (vigente/contabilizada en el pipeline)",
            "header_total": 11267897.0,
            "detail_total": invoice_total,
            "detail_lines": 580,
            "distinct_skus": int(len(sku)),
            "units": float(sku["cantidad_comprada"].sum()),
            "duplicate_line_skus": int((sku["lineas_factura"] > 1).sum()),
        },
        "performance": {
            "skus_with_any_sale_since": int((sku["unidades_vendidas_desde"] > 0).sum()),
            "skus_never_sold_since": int((sku["unidades_vendidas_desde"] <= 0).sum()),
            "skus_100pct_apparent_absorption": int((sku["sell_through_aparente"] >= 1).sum()),
            "units_sold_apparent_cap": float(sku["absorcion_unidades"].sum()),
            "unit_weighted_sell_through": float(
                sku["absorcion_unidades"].sum() / sku["cantidad_comprada"].sum()
            ),
            "cost_weighted_sell_through": float(
                sku["costo_absorbido_aparente"].sum() / invoice_total
            ),
            "estimated_cohort_revenue": estimated_revenue,
            "estimated_cohort_gross_profit": estimated_gp,
            "estimated_cohort_gross_margin": float(estimated_gp / estimated_revenue)
            if estimated_revenue
            else None,
            "estimated_revenue_to_invoice_cost": float(estimated_revenue / invoice_total),
            "total_sales_revenue_of_skus_since": float(sku["ventas_desde"].sum()),
            "total_sales_units_of_skus_since": float(sku["unidades_vendidas_desde"].sum()),
            "skus_replenished_after_invoice": int((sku["unidades_compradas_despues"] > 0).sum()),
            "unabsorbed_units": unabsorbed_units,
            "unabsorbed_cost": unabsorbed_cost,
            "skus_below_50pct_absorption": int(len(low_rotation)),
            "units_in_skus_below_50pct_absorption": float(low_rotation["cantidad_comprada"].sum()),
            "cost_in_skus_below_50pct_absorption": float(low_rotation["costo_factura"].sum()),
        },
        "inventory": {
            "skus_with_positive_stock": int((sku["stock_actual"] > 0).sum()),
            "skus_zero_stock": int((sku["stock_actual"] == 0).sum()),
            "skus_negative_stock": int((sku["stock_actual"] < 0).sum()),
            "current_units_across_skus": float(sku["stock_actual"].sum()),
            "current_positive_units": float(sku["stock_actual"].clip(lower=0).sum()),
            "current_stock_value_at_invoice_cost": float(
                sku["valor_stock_a_costo_factura"].sum()
            ),
            "minimum_potential_invoice_residual_units": float(
                sku["remanente_minimo_unidades"].sum()
            ),
            "minimum_potential_invoice_residual_cost": float(
                sku["remanente_minimo_costo"].sum()
            ),
            "skus_with_stock_no_sales_since": int(
                ((sku["stock_actual"] > 0) & (sku["unidades_vendidas_desde"] <= 0)).sum()
            ),
            "skus_with_stock_no_sales_365d": int(
                ((sku["stock_actual"] > 0) & (sku["unidades_365d"] <= 0)).sum()
            ),
            "stock_value_no_sales_365d_at_invoice_cost": float(
                sku.loc[
                    (sku["stock_actual"] > 0) & (sku["unidades_365d"] <= 0),
                    "valor_stock_a_costo_factura",
                ].sum()
            ),
        },
        "data_quality": {
            "header_detail_delta": float(11267897.0 - invoice_total),
            "missing_master_skus": int(sku["producto"].isna().sum()),
            "missing_current_price_skus": int(sku["precio_venta_actual"].isna().sum()),
            "negative_stock_skus": int((sku["stock_actual"] < 0).sum()),
            "lot_traceability": "No lot/serial link exists between a 2024 purchase line and 2026 on-hand units; residual figures are bounded estimates, not exact lot counts.",
        },
    }

    column_order = [
        "cod_producto",
        "producto",
        "lineas_factura",
        "cantidad_comprada",
        "costo_unitario_factura",
        "costo_factura",
        "stock_actual",
        "valor_stock_a_costo_factura",
        "unidades_vendidas_desde",
        "ventas_desde",
        "facturas_venta_desde",
        "dias_con_venta_desde",
        "primera_venta_desde",
        "ultima_venta_desde",
        "dias_hasta_primera_venta",
        "dias_sin_venta",
        "unidades_30d",
        "unidades_90d",
        "unidades_365d",
        "ventas_365d",
        "sell_through_aparente",
        "banda_sell_through",
        "remanente_minimo_unidades",
        "remanente_minimo_costo",
        "unidades_compradas_despues",
        "documentos_compra_despues",
        "ultima_compra_despues",
        "precio_venta_actual",
        "ingreso_cohorte_estimado",
        "utilidad_bruta_cohorte_estimada",
        "margen_cohorte_estimado",
        "estado_auditoria",
    ]
    sku[column_order].to_csv(DATA_DIR / "sku_audit.csv", index=False)
    band.to_csv(DATA_DIR / "sell_through_bands.csv", index=False)
    state.to_csv(DATA_DIR / "audit_states.csv", index=False)
    monthly.to_csv(DATA_DIR / "monthly_sales.csv", index=False)
    top_risk[column_order].to_csv(DATA_DIR / "top_risk.csv", index=False)
    all_risk[column_order].to_csv(DATA_DIR / "all_risk.csv", index=False)
    current_exposure[column_order].to_csv(DATA_DIR / "current_exposure.csv", index=False)
    top_performers[column_order].to_csv(DATA_DIR / "top_performers.csv", index=False)
    duplicate_skus = sku[sku["lineas_factura"] > 1][column_order]
    negative_stock = sku[sku["stock_actual"] < 0][column_order]
    duplicate_skus.to_csv(DATA_DIR / "duplicate_skus.csv", index=False)
    negative_stock.to_csv(DATA_DIR / "negative_stock.csv", index=False)

    def json_ready(frame: pd.DataFrame) -> list[dict]:
        data = frame.copy()
        for col in data.columns:
            if pd.api.types.is_datetime64_any_dtype(data[col]):
                data[col] = data[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        data = data.replace({np.nan: None, pd.NaT: None})
        return data.to_dict(orient="records")

    json_frames = {
        "sku_audit": sku[column_order],
        "sell_through_bands": band,
        "audit_states": state,
        "monthly_sales": monthly,
        "top_risk": top_risk[column_order],
        "all_risk": all_risk[column_order],
        "current_exposure": current_exposure[column_order],
        "top_performers": top_performers[column_order],
        "duplicate_skus": duplicate_skus,
        "negative_stock": negative_stock,
    }
    for name, frame in json_frames.items():
        (DATA_DIR / f"{name}.json").write_text(
            json.dumps(json_ready(frame), ensure_ascii=False), encoding="utf-8"
        )
    (DATA_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
