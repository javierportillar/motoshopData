"""Silver dimensions and facts ported from Databricks notebooks.

Uses DuckDB SQL with data from MySQL bronze (or JSON exports as fallback).
"""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


def dim_producto(con: duckdb.DuckDBPyConnection) -> None:
    # Backup embeddings antes de rebuild (Issue 2 fix)
    has_embedding = False
    try:
        con.execute("SELECT embedding FROM silver_dim_producto LIMIT 0")
        con.execute("""
            CREATE TEMP TABLE _embed_backup AS
            SELECT cod_producto, embedding FROM silver_dim_producto
            WHERE embedding IS NOT NULL
        """)
        count = con.execute("SELECT COUNT(*) FROM _embed_backup").fetchone()[0]
        if count > 0:
            has_embedding = True
            logger.info("Backed up %d embeddings before dim_producto rebuild", count)
    except Exception:
        pass

    con.execute("""
        CREATE OR REPLACE TABLE silver_dim_producto AS
        SELECT
            TRIM(codprod)        AS cod_producto,
            TRIM(nomprod)        AS nombre_producto,
            TRIM(codbar)         AS codigo_barras,
            TRIM(codmed)         AS cod_medida,
            CAST(valmed AS DOUBLE)    AS valor_medida,
            TRIM(presen)         AS presentacion,
            CAST(stockmin AS DOUBLE)  AS stock_minimo,
            CAST(stockmax AS DOUBLE)  AS stock_maximo,
            CAST(exiprod AS DOUBLE)   AS existencia,
            CAST(cosprod AS DOUBLE)   AS costo_producto,
            CAST(cosulc AS DOUBLE)    AS costo_ultima_compra,
            CAST(pvsini AS DOUBLE)    AS precio_venta_sin_iva,
            CAST(pvconi AS DOUBLE)    AS precio_venta_con_iva,
            TRIM(actprod)        AS estado_producto,
            TRIM(codpor)         AS cod_grupo,
            TRIM(codlin1)        AS cod_linea1,
            TRIM(desprod)        AS descripcion,
            TRIM(nitter)         AS nit_proveedor,
            TRIM(codbod)         AS cod_bodega_default,
            CAST(fecapa AS DATE)      AS fecha_actualizacion,
            CURRENT_DATE             AS snapshot_date
        FROM bronze_productos
        WHERE codprod IS NOT NULL
    """)

    # Agregar columna embedding si no existe (la preserva entre corridas)
    try:
        con.execute("SELECT embedding FROM silver_dim_producto LIMIT 0")
    except Exception:
        logger.info("Adding embedding column (FLOAT[384]) to dim_producto")
        con.execute("ALTER TABLE silver_dim_producto ADD COLUMN embedding FLOAT[384]")

    # Restaurar embeddings respaldados
    if has_embedding:
        con.execute("""
            UPDATE silver_dim_producto sdp
            SET embedding = b.embedding
            FROM _embed_backup b
            WHERE sdp.cod_producto = b.cod_producto
        """)
        logger.info("Restored embeddings for silver_dim_producto")


def dim_bodega(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE silver_dim_bodega AS
        SELECT
            TRIM(codbod)   AS cod_bodega,
            TRIM(nombod)   AS nombre_bodega,
            TRIM(telbod)   AS telefono,
            TRIM(ubibod)   AS ubicacion,
            TRIM(resbod)   AS responsable,
            CURRENT_DATE   AS snapshot_date
        FROM bronze_bodegas
        WHERE codbod IS NOT NULL
    """)


def fact_ventas(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE silver_fact_ventas AS
        SELECT
            TRIM(numfven)                      AS num_documento,
            TRIM(codclas)                      AS cod_clase,
            TRIM(prefven)                      AS prefijo,
            CAST(fecfven AS TIMESTAMP)         AS fecha_documento_ts,
            CAST(fecfven AS DATE)              AS business_date,
            TRIM(nitter)                       AS nit_cliente,
            TRIM(clifven)                      AS nombre_cliente,
            TRIM(nitvend)                      AS nit_vendedor,
            TRIM(venfven)                      AS nombre_vendedor,
            TRIM(codpag)                       AS cod_formapago,
            CAST(diasfven AS BIGINT)           AS dias_formapago,
            CAST(subfven AS DOUBLE)            AS subtotal,
            CAST(dctofven AS DOUBLE)           AS total_descuentos,
            CAST(ivafven AS DOUBLE)            AS total_iva,
            CAST(totimp AS DOUBLE)             AS total_impuesto,
            CAST(retefte AS DOUBLE)            AS retencion_fuente,
            CAST(reteiva AS DOUBLE)            AS retencion_iva,
            CAST(reteica AS DOUBLE)            AS retencion_ica,
            CAST(totfven AS DOUBLE)            AS total_factura,
            TRIM(obsfven)                      AS observaciones,
            TRIM(estfven)                      AS estado_documento,
            TRIM(codsuc)                       AS cod_sucursal,
            TRIM(codemp)                       AS cod_empresa,
            TRIM(codempal)                     AS cod_empresa_alt,
            TRIM(codres)                       AS cod_resolucion,
            CURRENT_DATE                       AS ingest_date_silver
        FROM bronze_facventas
        WHERE estfven IN ('A', 'B')
          AND fecfven IS NOT NULL
          AND CAST(fecfven AS DATE) >= DATE '2020-01-01'
          AND CAST(fecfven AS DATE) <= CURRENT_DATE
    """)


def fact_ventas_detalle(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE silver_fact_ventas_detalle AS
        SELECT
            TRIM(d.numfven)      AS num_documento,
            TRIM(d.codclas)      AS cod_clase,
            TRIM(d.codprod)      AS cod_producto,
            TRIM(d.nomdet)       AS nombre_detalle,
            CAST(d.candet AS DOUBLE)   AS cantidad,
            CAST(d.valuni AS DOUBLE)   AS valor_unitario,
            CAST(d.dctpor AS DOUBLE)   AS descuento_porcentaje,
            CAST(d.dctpes AS DOUBLE)   AS descuento_valor,
            CAST(d.ivapor AS DOUBLE)   AS iva_porcentaje,
            CAST(d.ivapes AS DOUBLE)   AS iva_valor,
            CAST(d.ipopor AS DOUBLE)   AS ipo_porcentaje,
            CAST(d.ipopes AS DOUBLE)   AS ipo_valor,
            CAST(d.totdet AS DOUBLE)   AS total_detalle,
            CAST(d.cosprod AS DOUBLE)  AS costo_producto,
            CAST(d.numite AS BIGINT)   AS num_item,
            TRIM(d.codbod)      AS cod_bodega,
            TRIM(d.codcos)      AS cod_centro_costo,
            h.business_date
        FROM bronze_detfventas d
        INNER JOIN silver_fact_ventas h
            ON TRIM(d.numfven) = h.num_documento
            AND TRIM(d.codclas) = h.cod_clase
    """)


def fact_compras(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE silver_fact_compras AS
        SELECT
            TRIM(numfcom)        AS num_documento,
            TRIM(codclas)        AS cod_clase,
            CAST(fecfcom AS DATE) AS business_date,
            TRIM(nitpro)         AS nit_proveedor,
            TRIM(profcom)        AS nombre_proveedor,
            TRIM(codpag)         AS cod_formapago,
            CAST(totfcom AS DOUBLE) AS total_factura,
            TRIM(estfcom)        AS estado_documento,
            CURRENT_DATE         AS ingest_date_silver
        FROM bronze_faccompras
        WHERE estfcom IN ('A', 'B')
          AND fecfcom IS NOT NULL
    """)


def fact_compras_detalle(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE silver_fact_compras_detalle AS
        SELECT
            TRIM(d.numfcom)      AS num_documento,
            TRIM(d.codclas)      AS cod_clase,
            TRIM(d.codprod)      AS cod_producto,
            TRIM(d.nomdet)       AS nombre_detalle,
            CAST(d.candet AS DOUBLE)   AS cantidad,
            CAST(d.valuni AS DOUBLE)   AS valor_unitario,
            CAST(d.totdet AS DOUBLE)   AS total_detalle,
            CAST(d.cosprod AS DOUBLE)  AS costo_producto,
            h.business_date
        FROM bronze_detfcompras d
        INNER JOIN silver_fact_compras h
            ON TRIM(d.numfcom) = h.num_documento
            AND TRIM(d.codclas) = h.cod_clase
    """)


def fact_inventario(con: duckdb.DuckDBPyConnection) -> None:
    """Port de 14_fact_inventario: lee bronze.auxinventario → silver.fact_inventario.

    Solo funciona con MySQL disponible (bronze_auxinventario). En modo seed,
    esta tabla se crea vacía y gold.py usa dim_producto como fallback.
    """
    con.execute("""
        CREATE TABLE IF NOT EXISTS silver_fact_inventario (
            id_inventario BIGINT,
            cod_lista VARCHAR,
            nombre_lista VARCHAR,
            cod_linea1 VARCHAR,
            nombre_linea VARCHAR,
            cod_linea2 VARCHAR,
            nombre_linea2 VARCHAR,
            cod_bodega VARCHAR,
            nombre_bodega VARCHAR,
            nit_tercero VARCHAR,
            nombre_tercero VARCHAR,
            num_documento VARCHAR,
            nombre_documento VARCHAR,
            cod_producto VARCHAR,
            num_serie VARCHAR,
            nombre_producto VARCHAR,
            unidad_medida VARCHAR,
            valor_costo DOUBLE,
            valor_venta DOUBLE,
            cantidad DOUBLE,
            valor4 DOUBLE,
            valor5 DOUBLE,
            business_date DATE,
            num_doc_referencia VARCHAR,
            nombre_sub VARCHAR,
            multiplo DOUBLE,
            cod_centro_costo VARCHAR,
            nombre_centro_costo VARCHAR
        )
    """)

    # Verificar que bronze_auxinventario existe (solo con MySQL)
    has_bronze = False
    try:
        con.execute("SELECT 1 FROM bronze_auxinventario LIMIT 1").fetchone()
        has_bronze = True
    except Exception:
        pass

    if has_bronze:
        con.execute("""
            INSERT INTO silver_fact_inventario
            SELECT
                ROW_NUMBER() OVER ()              AS id_inventario,
                TRIM(codlis)                      AS cod_lista,
                TRIM(nomlis)                      AS nombre_lista,
                TRIM(codlin1)                     AS cod_linea1,
                TRIM(nomlin)                      AS nombre_linea,
                TRIM(codlin2)                     AS cod_linea2,
                TRIM(nomlin2)                     AS nombre_linea2,
                TRIM(codbod)                      AS cod_bodega,
                TRIM(nombod)                      AS nombre_bodega,
                TRIM(nitter)                      AS nit_tercero,
                TRIM(nomter)                      AS nombre_tercero,
                TRIM(numdoc)                      AS num_documento,
                TRIM(nomdoc)                      AS nombre_documento,
                TRIM(codprod)                     AS cod_producto,
                TRIM(sernum)                      AS num_serie,
                TRIM(nomprod)                     AS nombre_producto,
                TRIM(unimed)                      AS unidad_medida,
                CAST(valor1 AS DOUBLE)            AS valor_costo,
                CAST(valor2 AS DOUBLE)            AS valor_venta,
                CAST(valor3 AS DOUBLE)            AS cantidad,
                CAST(valor4 AS DOUBLE)            AS valor4,
                CAST(valor5 AS DOUBLE)            AS valor5,
                CAST(docfec AS DATE)              AS business_date,
                TRIM(docnum)                      AS num_doc_referencia,
                TRIM(nomsub)                      AS nombre_sub,
                CAST(multiplo AS DOUBLE)          AS multiplo,
                TRIM(codcos)                      AS cod_centro_costo,
                TRIM(nomcos)                      AS nombre_centro_costo
            FROM bronze_auxinventario
            WHERE docfec IS NOT NULL
              AND CAST(docfec AS DATE) >= DATE '2020-01-01'
              AND CAST(docfec AS DATE) <= CURRENT_DATE
        """)
