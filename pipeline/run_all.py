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
from pipeline.mysql_source import get_mysql_connection

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("out/motoshop_gold.duckdb")

# Map MySQL tables → bronze table names and their column aliases
# Formato: (mysql_table, bronze_table, [(mysql_col, bronze_col), ...])
_MYSQL_BRONZE_MAP = [
    ("productos", "bronze_productos", [
        ("codprod", "codprod"), ("nomprod", "nomprod"), ("codbar", "codbar"),
        ("codmed", "codmed"), ("valmed", "valmed"), ("presen", "presen"),
        ("stockmin", "stockmin"), ("stockmax", "stockmax"), ("exiprod", "exiprod"),
        ("cosprod", "cosprod"), ("cosulc", "cosulc"), ("pvsini", "pvsini"),
        ("pvconi", "pvconi"), ("actprod", "actprod"), ("codpor", "codpor"),
        ("codlin1", "codlin1"), ("desprod", "desprod"), ("nitter", "nitter"),
        ("codbod", "codbod"), ("fecapa", "fecapa"),
    ]),
    ("bodegas", "bronze_bodegas", [
        ("codbod", "codbod"), ("nombod", "nombod"), ("telbod", "telbod"),
        ("ubibod", "ubibod"), ("resbod", "resbod"),
    ]),
    ("facventas", "bronze_facventas", [
        ("numfven", "numfven"), ("codclas", "codclas"), ("prefven", "prefven"),
        ("fecfven", "fecfven"), ("nitter", "nitter"), ("clifven", "clifven"),
        ("nitvend", "nitvend"), ("venfven", "venfven"), ("codpag", "codpag"),
        ("diasfven", "diasfven"), ("subfven", "subfven"),
        ("totdct", "dctofven"), ("totiva", "ivafven"), ("totipo", "totimp"),
        ("retfte", "retefte"), ("retiva", "reteiva"), ("retica", "reteica"),
        ("totfven", "totfven"), ("obsfven", "obsfven"), ("estfven", "estfven"),
        ("codsuc", "codsuc"), ("codemp", "codemp"),
        (None, "codempal"),  # No existe en MySQL, se setea NULL
        ("codres", "codres"),
    ]),
    ("detfventas", "bronze_detfventas", [
        ("numfven", "numfven"), ("codclas", "codclas"), ("codprod", "codprod"),
        ("nomdet", "nomdet"), ("candet", "candet"), ("valuni", "valuni"),
        ("dctpor", "dctpor"), ("dctpes", "dctpes"), ("ivapor", "ivapor"),
        ("ivapes", "ivapes"), ("ipopor", "ipopor"), ("ipopes", "ipopes"),
        ("totdet", "totdet"), ("cosprod", "cosprod"), ("numite", "numite"),
        ("codbod", "codbod"), ("codcos", "codcos"),
    ]),
    ("compras", "bronze_faccompras", [
        ("numcom", "numfcom"), ("codclas", "codclas"),
        ("feccom", "fecfcom"), ("nitter", "nitpro"),
        ("procom", "profcom"), ("codpag", "codpag"),
        ("totcom", "totfcom"), ("estcom", "estfcom"),
    ]),
    ("detcompras", "bronze_detfcompras", [
        ("numcom", "numfcom"), ("codclas", "codclas"), ("codprod", "codprod"),
        ("nomdet", "nomdet"), ("candet", "candet"), ("valuni", "valuni"),
        ("totdet", "totdet"), ("cosprod", "cosprod"),
    ]),
    ("auxinventario", "bronze_auxinventario", [
        ("codlis", "codlis"), ("nomlis", "nomlis"), ("codlin1", "codlin1"),
        ("nomlin", "nomlin"), ("codlin2", "codlin2"), ("nomlin2", "nomlin2"),
        ("codbod", "codbod"), ("nombod", "nombod"), ("nitter", "nitter"),
        ("nomter", "nomter"), ("numdoc", "numdoc"), ("nomdoc", "nomdoc"),
        ("codprod", "codprod"), ("sernum", "sernum"), ("nomprod", "nomprod"),
        ("unimed", "unimed"), ("valor1", "valor1"), ("valor2", "valor2"),
        ("valor3", "valor3"), ("valor4", "valor4"), ("valor5", "valor5"),
        ("docfec", "docfec"), ("docnum", "docnum"), ("nomsub", "nomsub"),
        ("multiplo", "multiplo"), ("codcos", "codcos"), ("nomcos", "nomcos"),
    ]),
]


def _build_bronze_from_mysql(con: duckdb.DuckDBPyConnection) -> bool:
    """Lee MySQL y reconstruye tablas bronze en DuckDB.

    Returns True si pudo conectar y cargar al menos productos.
    """
    mysql_conn = get_mysql_connection()
    if mysql_conn is None:
        logger.info("MySQL no disponible — usando bronze existente o seed")
        return False

    try:
        _ = mysql_conn  # pacificar linters, usado en finally
        cur = mysql_conn.cursor()
        total_rows = 0

        for mysql_table, bronze_table, columns in _MYSQL_BRONZE_MAP:
            # Build SELECT clause using MySQL backtick quoting
            select_parts = []
            for mysql_col, bronze_col in columns:
                if mysql_col is None:
                    select_parts.append(f"NULL AS `{bronze_col}`")
                else:
                    select_parts.append(f"`{mysql_col}` AS `{bronze_col}`")

            select_sql = ", ".join(select_parts)

            # Read from MySQL (backtick for identifiers, not double quotes)
            cur.execute(f'SELECT {select_sql} FROM `{mysql_table}`')
            rows = cur.fetchall()
            col_names = [bronze_col for _, bronze_col in columns]

            if not rows:
                logger.info("  MySQL %s: 0 rows, skipping", mysql_table)
                continue

            # Drop and recreate bronze table in DuckDB
            con.execute(f"DROP TABLE IF EXISTS {bronze_table}")

            # Create with VARCHAR for everything (DuckDB handles casting)
            col_defs = ", ".join([f'"{c}" VARCHAR' for c in col_names])
            con.execute(f"CREATE TABLE {bronze_table} ({col_defs})")

            # Insert in batches
            placeholders = ", ".join(["?"] * len(col_names))
            col_names_q = ", ".join([f'"{c}"' for c in col_names])
            stmt = f"INSERT INTO {bronze_table} ({col_names_q}) VALUES ({placeholders})"

            batch = []
            for row in rows:
                processed = [str(v) if v is not None else None for v in row]
                batch.append(processed)
                if len(batch) >= 1000:
                    con.executemany(stmt, batch)
                    batch = []
            if batch:
                con.executemany(stmt, batch)

            total_rows += len(rows)
            logger.info("  MySQL %s → %s: %d rows", mysql_table, bronze_table, len(rows))

        try:
            max_date = con.execute("SELECT MAX(fecfven) FROM bronze_facventas").fetchone()[0]
        except Exception:
            max_date = "N/A"

        logger.info(
            "Bronze refreshed from MySQL — %d filas totales, hasta %s",
            total_rows,
            max_date,
        )
        return True

    except Exception as e:
        logger.warning("MySQL bronze refresh failed: %s — usando bronze existente", e)
        return False
    finally:
        mysql_conn.close()


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
    # Intenta leer MySQL primero (fuente más fresca), fallback a bronze existente o seed
    mysql_ok = _build_bronze_from_mysql(con)

    if not mysql_ok:
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
                    "Ni MySQL, ni bronze_productos, ni motoshop_silver_dim_producto existen — "
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
    print(f"\nPipeline exitoso -> {path}")
