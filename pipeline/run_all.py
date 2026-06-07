"""Pipeline orquestador V1.5.

Ejecuta en orden: carga bronze → silver → gold → DuckDB.

Modos:
- seed:  desde JSON exports (build_duckdb_from_export) → reverse-engineer bronze → pipeline
- mysql: lee MySQL bronze → silver → gold (produccion Windows, requiere MySQL accesible)

El DuckDB final es out/motoshop_gold.duckdb y contiene tablas bronze, silver y gold.

Usage:
    python -m pipeline.run_all

No funciona con `python pipeline/run_all.py` directo porque usa imports
relativos (from pipeline import gold, silver). Siempre usar -m.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import duckdb

from pipeline import gold, silver

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("out/motoshop_gold.duckdb")


def _build_bronze_from_silver(con: duckdb.DuckDBPyConnection) -> None:
    """Crea tablas bronze con nombres raw desde las tablas silver ya existentes.

    Hace el reverse-mapping: silver_dim_producto.cod_producto → bronze_productos.codprod, etc.
    Esto permite que silver.py corra sus transformaciones sobre datos reales sin MySQL.
    """

    # ── dim_producto → bronze_productos ────────────────────────────────
    con.execute("""
        CREATE TABLE bronze_productos AS
        SELECT
            cod_producto           AS codprod,
            nombre_producto        AS nomprod,
            codigo_barras          AS codbar,
            cod_medida             AS codmed,
            valor_medida           AS valmed,
            presentacion           AS presen,
            stock_minimo           AS stockmin,
            stock_maximo           AS stockmax,
            existencia             AS exiprod,
            costo_producto         AS cosprod,
            costo_ultima_compra    AS cosulc,
            precio_venta_sin_iva   AS pvsini,
            precio_venta_con_iva   AS pvconi,
            estado_producto        AS actprod,
            cod_grupo              AS codpor,
            cod_linea1             AS codlin1,
            descripcion            AS desprod,
            nit_proveedor          AS nitter,
            cod_bodega_default     AS codbod,
            fecha_actualizacion    AS fecapa
        FROM motoshop_silver_dim_producto
    """)

    # ── dim_bodega → bronze_bodegas ─────────────────────────────────────
    con.execute("""
        CREATE TABLE bronze_bodegas AS
        SELECT
            cod_bodega    AS codbod,
            nombre_bodega AS nombod,
            telefono      AS telbod,
            ubicacion     AS ubibod,
            responsable   AS resbod
        FROM motoshop_silver_dim_bodega
    """)

    # ── fact_ventas → bronze_facventas ──────────────────────────────────
    con.execute("""
        CREATE TABLE bronze_facventas AS
        SELECT
            num_documento       AS numfven,
            cod_clase           AS codclas,
            prefijo             AS prefven,
            CAST(fecha_documento_ts AS TIMESTAMP) AS fecfven,
            nit_cliente         AS nitter,
            nombre_cliente      AS clifven,
            nit_vendedor        AS nitvend,
            nombre_vendedor     AS venfven,
            cod_formapago       AS codpag,
            dias_formapago      AS diasfven,
            subtotal            AS subfven,
            total_descuentos    AS dctofven,
            total_iva           AS ivafven,
            total_impuesto      AS totimp,
            retencion_fuente    AS retefte,
            retencion_iva       AS reteiva,
            retencion_ica       AS reteica,
            total_factura       AS totfven,
            observaciones       AS obsfven,
            estado_documento    AS estfven,
            cod_sucursal        AS codsuc,
            cod_empresa         AS codemp,
            cod_empresa_alt     AS codempal,
            cod_resolucion      AS codres
        FROM motoshop_silver_fact_ventas
    """)

    # ── fact_ventas_detalle → bronze_detfventas ─────────────────────────
    con.execute("""
        CREATE TABLE bronze_detfventas AS
        SELECT
            num_documento        AS numfven,
            cod_clase            AS codclas,
            cod_producto         AS codprod,
            nombre_detalle       AS nomdet,
            cantidad             AS candet,
            valor_unitario       AS valuni,
            descuento_porcentaje AS dctpor,
            descuento_valor      AS dctpes,
            iva_porcentaje       AS ivapor,
            iva_valor            AS ivapes,
            ipo_porcentaje       AS ipopor,
            ipo_valor            AS ipopes,
            total_detalle        AS totdet,
            costo_producto       AS cosprod,
            num_item             AS numite,
            cod_bodega           AS codbod,
            cod_centro_costo     AS codcos
        FROM motoshop_silver_fact_ventas_detalle
    """)

    # ── fact_compras → bronze_faccompras ────────────────────────────────
    # Export usa total_compra (no total_factura como en ventas).
    con.execute("""
        CREATE TABLE bronze_faccompras AS
        SELECT
            num_documento    AS numfcom,
            cod_clase        AS codclas,
            business_date    AS fecfcom,
            nit_proveedor    AS nitpro,
            nombre_proveedor AS profcom,
            cod_formapago    AS codpag,
            total_compra     AS totfcom,
            estado_documento AS estfcom
        FROM motoshop_silver_fact_compras
    """)

    # ── fact_compras_detalle → bronze_detfcompras ───────────────────────
    con.execute("""
        CREATE TABLE bronze_detfcompras AS
        SELECT
            num_documento  AS numfcom,
            cod_clase      AS codclas,
            cod_producto   AS codprod,
            nombre_detalle AS nomdet,
            cantidad       AS candet,
            valor_unitario AS valuni,
            total_detalle  AS totdet,
            costo_producto AS cosprod
        FROM motoshop_silver_fact_compras_detalle
    """)

    logger.info(
        "Bronze built — productos=%d bodegas=%d ventas=%d detalle=%d compras=%d",
        con.execute("SELECT COUNT(*) FROM bronze_productos").fetchone()[0],
        con.execute("SELECT COUNT(*) FROM bronze_bodegas").fetchone()[0],
        con.execute("SELECT COUNT(*) FROM bronze_facventas").fetchone()[0],
        con.execute("SELECT COUNT(*) FROM bronze_detfventas").fetchone()[0],
        con.execute("SELECT COUNT(*) FROM bronze_faccompras").fetchone()[0],
    )


def run_all() -> str:
    """Pipeline completo: bronze → silver → gold.

    Si out/motoshop_gold.duckdb ya existe (seed via build_duckdb_from_export),
    lo usa como base y corre el pipeline encima. Si no existe, intenta
    construirlo desde los exports JSON.
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── Paso 0: preparar el DuckDB base ─────────────────────────────────
    if not OUTPUT_PATH.exists():
        logger.info("DuckDB not found at %s, building from exports...", OUTPUT_PATH)
        from pipeline.build_duckdb_from_export import build_from_databricks
        build_from_databricks(OUTPUT_PATH)

    con = duckdb.connect(str(OUTPUT_PATH))

    # ── Paso 1: Bronze ──────────────────────────────────────────────────
    # Intenta crear bronze desde silver (seed) o desde MySQL (produccion)
    bronze_exists = False
    try:
        count = con.execute("SELECT COUNT(*) FROM bronze_productos").fetchone()[0]
        bronze_exists = count > 0
    except Exception:
        pass

    if not bronze_exists:
        silver_exists = False
        try:
            con.execute("SELECT COUNT(*) FROM motoshop_silver_dim_producto").fetchone()
            silver_exists = True
        except Exception:
            pass

        if silver_exists:
            logger.info("Silver tables found — building bronze via reverse-mapping")
            _build_bronze_from_silver(con)
        else:
            raise RuntimeError(
                "Ni bronze_productos ni motoshop_silver_dim_producto existen — "
                "corre build_duckdb_from_export primero o conecta MySQL"
            )
    else:
        logger.info("Bronze tables already exist, skipping build")

    # ── Paso 2: Silver ──────────────────────────────────────────────────
    logger.info("Running silver transformations...")
    silver.dim_producto(con)
    silver.dim_bodega(con)
    silver.fact_ventas(con)
    silver.fact_ventas_detalle(con)
    silver.fact_compras(con)
    silver.fact_compras_detalle(con)
    silver.fact_inventario(con)
    logger.info("Silver: 7/7 transformations complete")

    # ── Paso 3: Gold ────────────────────────────────────────────────────
    logger.info("Running gold transformations...")
    # 3a. Marts que dependen solo de silver
    gold.mart_ventas_diarias_sku(con)
    gold.mart_inventario_actual(con)
    gold.mart_cohortes_clientes(con)
    gold.mart_productos_dormidos(con)

    # 3b. Marts que dependen de otros gold marts
    gold.mart_rotacion_abc(con)         # depende de mart_ventas_diarias_sku
    gold.forecast_categoria(con)        # depende de mart_ventas_diarias_sku + dim_producto
    gold.alertas_drift(con)             # depende de forecast_categoria
    gold.mart_abc_xyz(con)              # depende de mart_rotacion_abc + mart_ventas_diarias_sku
    gold.mart_rotacion_promedio(con)    # depende de mart_ventas_diarias_sku
    gold.alertas_quiebre(con)           # depende de silver (dim_producto + fact_ventas_detalle)
    logger.info("Gold: 10/10 transformations complete")

    # ── Paso 4: Embeddings (solo si hay productos sin embedding) ──────
    try:
        from pipeline.embeddings_skus import generate_embeddings
        embed_count = generate_embeddings(str(OUTPUT_PATH), mode="delta")
        if embed_count > 0:
            logger.info("Embeddings: %d SKUs processed", embed_count)
    except Exception as exc:
        logger.warning("Embeddings skipped: %s", exc)

    con.close()
    return str(OUTPUT_PATH)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    path = run_all()
    print(f"\nPipeline exitoso → {path}")
