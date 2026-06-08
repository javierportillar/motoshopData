"""Gold marts ported from Databricks notebooks to DuckDB SQL.
"""

from __future__ import annotations

import duckdb


def mart_ventas_diarias_sku(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_mart_ventas_diarias_sku AS
        SELECT
            fv.business_date,
            fvd.cod_producto,
            COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
            fvd.cod_bodega,
            COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
            ROUND(SUM(fvd.cantidad), 2)         AS cantidad_total,
            ROUND(SUM(fvd.valor_unitario * fvd.cantidad - COALESCE(fvd.descuento_valor, 0)), 2) AS valor_total,
            COUNT(DISTINCT fv.num_documento)    AS num_facturas
        FROM motoshop_silver_fact_ventas_detalle fvd
        INNER JOIN motoshop_silver_fact_ventas fv
            ON fvd.num_documento = fv.num_documento
            AND fvd.cod_clase = fv.cod_clase
            AND fvd.business_date = fv.business_date
        LEFT JOIN motoshop_silver_dim_producto dp
            ON fvd.cod_producto = dp.cod_producto
        LEFT JOIN motoshop_silver_dim_bodega db
            ON fvd.cod_bodega = db.cod_bodega
        WHERE fvd.business_date >= DATE '2020-01-01'
          AND fvd.business_date <= CURRENT_DATE
        GROUP BY fv.business_date, fvd.cod_producto, dp.nombre_producto, fvd.cod_bodega, db.nombre_bodega
    """)


def mart_inventario_actual(con: duckdb.DuckDBPyConnection) -> None:
    # Intenta usar fact_inventario (Databricks original). Si no tiene datos
    # (seed sin MySQL), cae a dim_producto como fallback.
    has_fact_inventario = False
    try:
        count = con.execute("SELECT COUNT(*) FROM motoshop_silver_fact_inventario").fetchone()[0]
        has_fact_inventario = count > 0
    except Exception:
        pass

    if has_fact_inventario:
        con.execute("""
            CREATE OR REPLACE TABLE motoshop_gold_mart_inventario_actual AS
            WITH ultimo_inventario AS (
                SELECT
                    cod_producto,
                    cod_bodega,
                    cantidad,
                    valor_costo,
                    business_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY cod_producto, cod_bodega
                        ORDER BY business_date DESC, id_inventario DESC
                    ) AS rn
                FROM motoshop_silver_fact_inventario
                WHERE business_date >= DATE '2020-01-01'
                  AND business_date <= CURRENT_DATE
            )
            SELECT
                ui.cod_producto,
                COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
                ui.cod_bodega,
                COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
                ROUND(ui.cantidad, 2) AS cantidad_actual,
                CURRENT_DATE AS snapshot_date
            FROM ultimo_inventario ui
            LEFT JOIN motoshop_silver_dim_producto dp
                ON ui.cod_producto = dp.cod_producto
            LEFT JOIN motoshop_silver_dim_bodega db
                ON ui.cod_bodega = db.cod_bodega
            WHERE ui.rn = 1
        """)
    else:
        # Fallback seed: usa dim_producto (todos los productos, no solo los que
        # tienen registro en fact_inventario). Produce ~6185 filas vs 4829 del export.
        con.execute("""
            CREATE OR REPLACE TABLE motoshop_gold_mart_inventario_actual AS
            SELECT
                dp.cod_producto,
                COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
                COALESCE(dp.cod_bodega_default, '') AS cod_bodega,
                COALESCE(db.nombre_bodega, 'SIN NOMBRE') AS nom_bodega,
                COALESCE(dp.existencia, 0) AS cantidad_actual,
                CURRENT_DATE AS snapshot_date
            FROM motoshop_silver_dim_producto dp
            LEFT JOIN motoshop_silver_dim_bodega db
                ON dp.cod_bodega_default = db.cod_bodega
        """)


def mart_rotacion_abc(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_mart_rotacion_abc AS
        WITH monthly_sales AS (
            SELECT
                STRFTIME(business_date, '%Y-%m-01') AS business_month,
                cod_producto,
                SUM(valor_total) AS valor_total
            FROM motoshop_gold_mart_ventas_diarias_sku
            GROUP BY STRFTIME(business_date, '%Y-%m-01'), cod_producto
        ),
        ranked AS (
            SELECT
                business_month,
                cod_producto,
                valor_total,
                SUM(valor_total) OVER (PARTITION BY business_month ORDER BY valor_total DESC
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumsum,
                SUM(valor_total) OVER (PARTITION BY business_month) AS total
            FROM monthly_sales
        )
        SELECT
            business_month,
            cod_producto,
            valor_total,
            CASE
                WHEN cumsum <= total * 0.80 THEN 'A'
                WHEN cumsum <= total * 0.95 THEN 'B'
                ELSE 'C'
            END AS categoria_abc
        FROM ranked
    """)


def mart_cohortes_clientes(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_mart_cohortes_clientes AS
        WITH first_purchase AS (
            SELECT nit_cliente, MIN(business_date) AS first_date
            FROM motoshop_silver_fact_ventas
            WHERE nit_cliente IS NOT NULL AND nit_cliente != ''
            GROUP BY nit_cliente
        ),
        monthly AS (
            SELECT
                fv.nit_cliente,
                STRFTIME(fv.business_date, '%Y-%m-01') AS business_month,
                SUM(fv.total_factura) AS ticket_total,
                COUNT(*) AS facturas
            FROM motoshop_silver_fact_ventas fv
            WHERE fv.nit_cliente IS NOT NULL AND fv.nit_cliente != ''
            GROUP BY fv.nit_cliente, STRFTIME(fv.business_date, '%Y-%m-01')
        )
        SELECT
            STRFTIME(fp.first_date, '%Y-%m-01') AS mes_cohorte,
            m.business_month,
            m.nit_cliente,
            ROUND(m.ticket_total / NULLIF(m.facturas, 0), 2) AS ticket_promedio,
            CASE WHEN m.business_month = STRFTIME(fp.first_date, '%Y-%m-01') THEN TRUE ELSE FALSE END AS compro_este_mes
        FROM monthly m
        INNER JOIN first_purchase fp ON m.nit_cliente = fp.nit_cliente
    """)


def mart_productos_dormidos(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_mart_productos_dormidos AS
        SELECT
            dp.cod_producto,
            COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
            COALESCE(inv.cantidad_actual, 0) AS stock_actual,
            COALESCE(MAX(fvd.business_date), DATE '1970-01-01') AS ultima_fecha_venta,
            CURRENT_DATE - COALESCE(MAX(fvd.business_date), DATE '1970-01-01') AS dias_sin_venta
        FROM motoshop_silver_dim_producto dp
        LEFT JOIN motoshop_gold_mart_inventario_actual inv
            ON dp.cod_producto = inv.cod_producto
        LEFT JOIN motoshop_silver_fact_ventas_detalle fvd
            ON dp.cod_producto = fvd.cod_producto
        GROUP BY dp.cod_producto, dp.nombre_producto, inv.cantidad_actual
        HAVING dias_sin_venta > 90 OR dias_sin_venta IS NULL
    """)


def alertas_quiebre(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_alertas_quiebre AS
        WITH max_date AS (
            SELECT MAX(business_date) AS max_bd FROM motoshop_silver_fact_ventas_detalle
        ),
        demanda_7d AS (
            SELECT cod_producto, SUM(cantidad) / 7.0 AS demanda_promedio
            FROM motoshop_silver_fact_ventas_detalle, max_date
            WHERE business_date >= max_date.max_bd - INTERVAL '7' DAY
            GROUP BY cod_producto
        ),
        stock_actual AS (
            SELECT cod_producto, COALESCE(existencia, 0) AS stock
            FROM motoshop_silver_dim_producto
        )
        SELECT
            sa.cod_producto AS sku,
            COALESCE(dp.nombre_producto, 'SIN NOMBRE') AS nom_producto,
            sa.stock AS stock_actual,
            COALESCE(d7.demanda_promedio, 0) AS demanda_predicha,
            CASE
                WHEN COALESCE(d7.demanda_promedio, 0) <= 0 THEN 999
                ELSE CAST(sa.stock / d7.demanda_promedio AS BIGINT)
            END AS dias_hasta_quiebre,
            CASE
                WHEN COALESCE(d7.demanda_promedio, 0) > 0 AND sa.stock / d7.demanda_promedio <= 3 THEN 'alta'
                WHEN COALESCE(d7.demanda_promedio, 0) > 0 AND sa.stock / d7.demanda_promedio <= 7 THEN 'media'
                WHEN COALESCE(d7.demanda_promedio, 0) > 0 AND sa.stock / d7.demanda_promedio <= 14 THEN 'baja'
                ELSE 'none'
            END AS urgencia
        FROM stock_actual sa
        LEFT JOIN demanda_7d d7 ON sa.cod_producto = d7.cod_producto
        LEFT JOIN motoshop_silver_dim_producto dp ON sa.cod_producto = dp.cod_producto
        WHERE sa.stock <= COALESCE(d7.demanda_promedio * 14, 0)
          AND COALESCE(d7.demanda_promedio, 0) > 0
    """)


def alertas_drift(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_alertas_drift AS
        WITH forecast AS (
            SELECT
                cod_grupo,
                business_date,
                demanda_real,
                demanda_predicha_baseline
            FROM motoshop_gold_forecast_categoria
        ),
        weekly AS (
            SELECT
                cod_grupo,
                DATE_TRUNC('week', business_date) AS week_start,
                SUM(demanda_real) AS real_w,
                SUM(demanda_predicha_baseline) AS pred_w
            FROM forecast
            GROUP BY cod_grupo, DATE_TRUNC('week', business_date)
        )
        SELECT
            cod_grupo,
            week_start AS week_end,
            ROUND(ABS(real_w - pred_w) / NULLIF(pred_w, 0) * 100, 2) AS desviacion_pct,
            30.0 AS threshold_pct,
            CASE
                WHEN ABS(real_w - pred_w) / NULLIF(pred_w, 0) * 100 >= 30 THEN 'Re-entrenar modelo inmediatamente'
                WHEN ABS(real_w - pred_w) / NULLIF(pred_w, 0) * 100 >= 15 THEN 'Monitorear'
                ELSE 'Sin accion requerida'
            END AS alert_msg
        FROM weekly
        WHERE week_start >= CURRENT_DATE - INTERVAL '30' DAY
    """)


def forecast_categoria(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_forecast_categoria AS
        WITH daily_sales AS (
            SELECT
                cod_grupo,
                business_date,
                SUM(valor_total) AS demanda_real
            FROM motoshop_gold_mart_ventas_diarias_sku mv
            INNER JOIN motoshop_silver_dim_producto dp ON mv.cod_producto = dp.cod_producto
            GROUP BY cod_grupo, business_date
        ),
        moving_avg AS (
            SELECT
                cod_grupo,
                business_date,
                demanda_real,
                AVG(demanda_real) OVER (
                    PARTITION BY cod_grupo
                    ORDER BY business_date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS demanda_predicha_baseline
            FROM daily_sales
        )
        SELECT
            cod_grupo,
            business_date,
            demanda_real,
            demanda_predicha_baseline,
            'moving_average_7d' AS metodo_baseline
        FROM moving_avg
        WHERE business_date >= CURRENT_DATE - INTERVAL '90' DAY
    """)


def mart_abc_xyz(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_mart_abc_xyz AS
        SELECT
            abc.business_month,
            abc.cod_producto,
            abc.categoria_abc AS abc,
            CASE
                WHEN COALESCE(stddev.valor_std, 0) / NULLIF(abc.valor_total, 0) < 0.5 THEN 'X'
                WHEN COALESCE(stddev.valor_std, 0) / NULLIF(abc.valor_total, 0) < 1.0 THEN 'Y'
                ELSE 'Z'
            END AS xyz
        FROM motoshop_gold_mart_rotacion_abc abc
        LEFT JOIN (
            SELECT
                STRFTIME(business_date, '%Y-%m-01') AS business_month,
                cod_producto,
                STDDEV(valor_total) AS valor_std
            FROM motoshop_gold_mart_ventas_diarias_sku
            GROUP BY STRFTIME(business_date, '%Y-%m-01'), cod_producto
        ) stddev
            ON abc.business_month = stddev.business_month
            AND abc.cod_producto = stddev.cod_producto
    """)


def mart_rotacion_promedio(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE motoshop_gold_mart_rotacion_promedio AS
        SELECT
            cod_producto,
            ROUND(AVG(valor_total), 2) AS valor_promedio_mensual,
            ROUND(AVG(cantidad_total), 2) AS cantidad_promedio_mensual,
            COUNT(DISTINCT business_date) AS dias_con_venta,
            CURRENT_DATE AS snapshot_date
        FROM motoshop_gold_mart_ventas_diarias_sku
        WHERE business_date >= CURRENT_DATE - INTERVAL '90' DAY
        GROUP BY cod_producto
    """)
