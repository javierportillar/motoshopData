#!/usr/bin/env python3
"""Captura incremental de ventas nuevas desde MySQL.

Cada ~2 minutos (17:50-23:59):
  1. Lee MAX(fecha_documento_ts) desde silver_fact_ventas
  2. Consulta MySQL por facventas + detfventas nuevas
  3. Si hay datos nuevos, los inserta en silver y rebuild gold
  4. Sube DuckDB a R2
  5. Refresca API via REFRESH_TOKEN

Uso:
    python scripts/capture_new_sales.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("capture")

DB_PATH = Path(os.environ.get("DUCKDB_PATH", "out/motoshop_gold.duckdb"))

# ── Heler: comparar timestamps ───────────────────────────────────────────────

def _fetchall_dict(cur, sql, params=None):
    """Ejecuta SQL y devuelve lista de dicts."""
    cur.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Paso 1: detectar nuevas ventas ───────────────────────────────────────────

def _get_max_silver_ts(con: duckdb.DuckDBPyConnection):
    """Devuelve el fecha_documento_ts más alto en silver."""
    row = con.execute(
        "SELECT MAX(fecha_documento_ts) FROM motoshop_silver_fact_ventas"
    ).fetchone()
    return row[0] if row and row[0] else "2020-01-01 00:00:00"


def _fetch_new_headers(mysql_cur, since_ts: str) -> list[dict]:
    """Lee facventas nuevas desde MySQL (mayor al timestamp dado)."""
    rows = _fetchall_dict(mysql_cur, """
        SELECT
            numfven, codclas, prefven,
            fecfven, nitter, clifven,
            nitvend, venfven, codpag,
            diasfven, subfven, dctofven,
            ivafven, totimp, retefte,
            reteiva, reteica, totfven,
            obsfven, estfven, codsuc,
            codemp, codres
        FROM facventas
        WHERE fecfven > %s
          AND estfven IN ('A', 'B')
          AND fecfven IS NOT NULL
          AND fecfven <= NOW()
        ORDER BY fecfven ASC
    """, [since_ts])
    return rows


def _fetch_new_details(mysql_cur, headers: list[dict]) -> list[dict]:
    """Lee detfventas para las facturas nuevas."""
    if not headers:
        return []
    # Build IN clause
    pairs = [(h["numfven"], h["codclas"]) for h in headers]
    placeholders = ", ".join([f"(%s,%s)" for _ in pairs])
    flat = [v for p in pairs for v in p]
    rows = _fetchall_dict(mysql_cur, f"""
        SELECT
            d.numfven, d.codclas, d.codprod,
            d.nomdet, d.candet, d.valuni,
            d.dctpor, d.dctpes, d.ivapor,
            d.ivapes, d.ipopor, d.ipopes,
            d.totdet, d.cosprod, d.numite,
            d.codbod, d.codcos
        FROM detfventas d
        WHERE (d.numfven, d.codclas) IN ({placeholders})
        ORDER BY d.numfven, d.numite
    """, flat)
    return rows


# ── Paso 2: insertar en silver ──────────────────────────────────────────────

def _insert_headers(con: duckdb.DuckDBPyConnection, rows: list[dict]) -> int:
    """Inserta nuevas facturas en silver_fact_ventas."""
    if not rows:
        return 0
    count = len(rows)
    # Insert en batches de 500
    batch_size = 500
    total = 0
    for i in range(0, count, batch_size):
        batch = []
        for h in rows[i:i + batch_size]:
            try:
                ts = h["fecfven"]
                if hasattr(ts, "strftime"):
                    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    ts_str = str(ts)
                batch.append((
                    h["numfven"].strip(), h["codclas"].strip(), h.get("prefven", "").strip(),
                    ts_str, ts_str[:10],
                    h.get("nitter", "").strip(), h.get("clifven", "").strip(),
                    h.get("nitvend", "").strip(), h.get("venfven", "").strip(),
                    h.get("codpag", "").strip(),
                    int(h.get("diasfven", 0) or 0),
                    float(h.get("subfven", 0) or 0),
                    float(h.get("dctofven", 0) or 0),
                    float(h.get("ivafven", 0) or 0),
                    float(h.get("totimp", 0) or 0),
                    float(h.get("retefte", 0) or 0),
                    float(h.get("reteiva", 0) or 0),
                    float(h.get("reteica", 0) or 0),
                    float(h.get("totfven", 0) or 0),
                    h.get("obsfven", "").strip(),
                    h.get("estfven", "").strip(),
                    h.get("codsuc", "").strip(),
                    h.get("codemp", "").strip(),
                    None,  # cod_empresa_alt
                    h.get("codres", "").strip(),
                    ts_str[:10],  # ingest_date_silver
                ))
            except (ValueError, TypeError) as e:
                logger.warning("Saltando fila %s: %s", h.get("numfven"), e)
                continue
        if batch:
            con.executemany("""
                INSERT INTO motoshop_silver_fact_ventas
                    (num_documento, cod_clase, prefijo,
                     fecha_documento_ts, business_date,
                     nit_cliente, nombre_cliente,
                     nit_vendedor, nombre_vendedor,
                     cod_formapago, dias_formapago,
                     subtotal, total_descuentos,
                     total_iva, total_impuesto,
                     retencion_fuente, retencion_iva, retencion_ica,
                     total_factura, observaciones,
                     estado_documento, cod_sucursal,
                     cod_empresa, cod_empresa_alt,
                     cod_resolucion, ingest_date_silver)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            total += len(batch)
    return total


def _insert_details(con: duckdb.DuckDBPyConnection, rows: list[dict], headers_date_map: dict) -> int:
    """Inserta nuevo detalle en silver_fact_ventas_detalle."""
    if not rows:
        return 0
    count = len(rows)
    batch_size = 500
    total = 0
    for i in range(0, count, batch_size):
        batch = []
        for d in rows[i:i + batch_size]:
            try:
                key = (d["numfven"].strip(), d["codclas"].strip())
                biz_date = headers_date_map.get(key, "2026-01-01")
                batch.append((
                    d["numfven"].strip(), d["codclas"].strip(), d.get("codprod", "").strip(),
                    d.get("nomdet", "").strip(),
                    float(d.get("candet", 0) or 0),
                    float(d.get("valuni", 0) or 0),
                    float(d.get("dctpor", 0) or 0),
                    float(d.get("dctpes", 0) or 0),
                    float(d.get("ivapor", 0) or 0),
                    float(d.get("ivapes", 0) or 0),
                    float(d.get("ipopor", 0) or 0),
                    float(d.get("ipopes", 0) or 0),
                    float(d.get("totdet", 0) or 0),
                    float(d.get("cosprod", 0) or 0),
                    int(d.get("numite", 0) or 0),
                    d.get("codbod", "").strip(),
                    d.get("codcos", "").strip(),
                    biz_date,
                ))
            except (ValueError, TypeError) as e:
                logger.warning("Saltando detalle %s: %s", d.get("numfven"), e)
                continue
        if batch:
            con.executemany("""
                INSERT INTO motoshop_silver_fact_ventas_detalle
                    (num_documento, cod_clase, cod_producto,
                     nombre_detalle, cantidad, valor_unitario,
                     descuento_porcentaje, descuento_valor,
                     iva_porcentaje, iva_valor,
                     ipo_porcentaje, ipo_valor,
                     total_detalle, costo_producto,
                     num_item, cod_bodega, cod_centro_costo,
                     business_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            total += len(batch)
    return total


# ── Paso 3: Rebuild gold ───────────────────────────────────────────────────

def _rebuild_gold(con: duckdb.DuckDBPyConnection) -> None:
    """Reconstruye gold.mart_ventas_diarias_sku desde silver."""
    from pipeline.gold import mart_ventas_diarias_sku
    mart_ventas_diarias_sku(con)
    logger.info("Gold ventas diarias rebuilt")


# ── Paso 4: Upload + Refresh ────────────────────────────────────────────────

def _upload_to_r2() -> None:
    """Sube DuckDB a R2."""
    from scripts.upload_duckdb_to_r2 import main as upload_main
    upload_main()


def _refresh_api() -> None:
    """Llama a los endpoints de refresh via token compartido."""
    import urllib.request
    import json

    refresh_token = os.environ.get("REFRESH_TOKEN", "")
    if not refresh_token:
        logger.warning("REFRESH_TOKEN no configurado, saltando refresh API")
        return

    api_base = os.environ.get("API_BASE_URL", "http://localhost:8000")
    headers = {
        "Authorization": f"Bearer {refresh_token}",
        "Content-Type": "application/json",
    }

    for endpoint in ["/api/admin/data/refresh", "/api/admin/pipeline/refresh"]:
        url = f"{api_base}{endpoint}"
        try:
            req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
                logger.info("Refresh %s: %s", endpoint, body.get("status"))
        except Exception as e:
            logger.warning("Refresh %s falló: %s", endpoint, e)


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    """Ejecuta captura incremental. Retorna cantidad de facturas nuevas."""
    # ── 0. Conectar DuckDB ─────────────────────────────────────────────────
    if not DB_PATH.exists():
        logger.warning("DuckDB no encontrado en %s", DB_PATH)
        return 0

    con = duckdb.connect(str(DB_PATH))
    try:
        max_ts = _get_max_silver_ts(con)
        logger.info("Silver max fecha_documento_ts: %s", max_ts)

        # ── 1. Conectar MySQL ─────────────────────────────────────────────
        from pipeline.mysql_source import get_mysql_connection
        mysql_conn = get_mysql_connection()
        if mysql_conn is None:
            logger.warning("MySQL no disponible, saltando captura")
            return 0

        try:
            cur = mysql_conn.cursor()

            # ── 2. Leer facturas nuevas ────────────────────────────────────
            headers = _fetch_new_headers(cur, str(max_ts) if max_ts else "2020-01-01 00:00:00")
            if not headers:
                logger.info("No hay ventas nuevas desde %s", max_ts)
                return 0

            logger.info("Nuevas facturas encontradas: %d", len(headers))

            # ── 3. Leer detalle ────────────────────────────────────────────
            details = _fetch_new_details(cur, headers)
            logger.info("Nuevos detalles encontrados: %d", len(details))

        finally:
            mysql_conn.close()

        # ── 4. Insertar en silver ──────────────────────────────────────────
        h_count = _insert_headers(con, headers)
        logger.info("Insertadas %d facturas en silver_fact_ventas", h_count)

        # Build header date map for detail insertion
        header_date_map = {}
        for h in headers:
            key = (h["numfven"].strip(), h["codclas"].strip())
            ts = h["fecfven"]
            if hasattr(ts, "strftime"):
                biz = ts.strftime("%Y-%m-%d")
            else:
                biz = str(ts)[:10]
            header_date_map[key] = biz

        d_count = _insert_details(con, details, header_date_map)
        logger.info("Insertados %d detalles en silver_fact_ventas_detalle", d_count)

        # ── 5. Rebuild gold ───────────────────────────────────────────────
        _rebuild_gold(con)

        # ── 6. Upload + Refresh ───────────────────────────────────────────
        _upload_to_r2()
        _refresh_api()

        return len(headers)

    finally:
        con.close()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    count = main()
    if count > 0:
        print(f"[OK] Capturadas {count} facturas nuevas")
    else:
        print("[OK] Sin datos nuevos")
