"""Spike V1.5 · Valida el patrón DuckDB con datos seed del snapshot.

Genera out/motoshop_gold.duckdb con la tabla mart_ventas_diarias_sku
poblada con datos que replican EXACTAMENTE (tolerancia 0) las cifras del
snapshot SALES_SUMMARY en docs/audit/raw_responses.json.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import duckdb

OUTPUT_PATH = Path("out/motoshop_gold.duckdb")

MONTH_CURRENT = "2026-05"
MONTH_PREV = "2026-04"
TOTAL_CURRENT = 23_516_508.33
TOTAL_PREV = 26_365_000.0

TOP_SKUS = [
    {"cod_producto": "601325", "nom_producto": "MOBIL SUPER MOTO 4T 20W50 12X1L", "cantidad_total": 40.0, "valor_total": 1_160_000.0},
    {"cod_producto": "MOTS1297", "nom_producto": "ACEITE CASTROS 20 W 50", "cantidad_total": 32.0, "valor_total": 864_000.0},
    {"cod_producto": "14_00021 / 700102/12", "nom_producto": "AC MAGNA 4T 20W50 MA2/SL CJ 12/L / 700102/12", "cantidad_total": 18.0, "valor_total": 360_000.0},
    {"cod_producto": "VY20116", "nom_producto": "BOMBA DE GASOLINA BWS 125 F.I", "cantidad_total": 1.0, "valor_total": 357_000.0},
    {"cod_producto": "MOTS1430", "nom_producto": "SERVICIO-TECNICO MANTENIMIENTO DE MOTOS", "cantidad_total": 7.0, "valor_total": 336_800.0},
    {"cod_producto": "02_00001 / MF-MAGX4L", "nom_producto": "BATERIA MOTO AGM_POL (- +)_12V_4.3AH_MAGNA_MF- MA", "cantidad_total": 4.0, "valor_total": 297_500.0},
    {"cod_producto": "173052", "nom_producto": "KIT CAJA CADENA - ECO DELUXE 100 4 HUECOS (PT44G-PD14G- 428-H-120G) DORADA GAVIRIA", "cantidad_total": 3.0, "valor_total": 270_000.0},
    {"cod_producto": "601324", "nom_producto": "MOBIL SUPER 4T MX 15W50  12X 1L", "cantidad_total": 7.0, "valor_total": 266_000.0},
    {"cod_producto": "IMBRT46", "nom_producto": "REF: IMBRT46 - BARRA TELESCOPICOS C/TAPON FZ-16/FZ 2.0/FZ 2.5 (PAR) 21CF3110-00", "cantidad_total": 2.0, "valor_total": 248_000.0},
    {"cod_producto": "02_00010 / MF-YB5LB", "nom_producto": "BATERIA MOTO AGM_POL (- +)_12V_5.2AH_MAGNA_MF- YB", "cantidad_total": 3.0, "valor_total": 245_000.0},
]
TOP_SKUS_TOTAL = sum(s["valor_total"] for s in TOP_SKUS)

BODEGA_CODE = ""
BODEGA_NAME = "BODEGA PRINCIPAL"


def _month_days(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def _insert_exact_month(con: duckdb.DuckDBPyConnection, year: int, month: int, target_total: float, target_facturas: int | None = None) -> float:
    """Inserta datos para un mes y retorna el total exacto insertado.

    Si target_facturas se pasa, distribuye las facturas para que SUM(num_facturas)
    sea exactamente target_facturas (necesario para que ticket_promedio calce).
    """
    days = _month_days(year, month)
    date_prefix = f"{year}-{month:02d}"
    target_facturas = target_facturas or 0
    
    total_inserted = 0.0
    rows_for_facturas: list[tuple] = []  # acumula rows para distribuir facturas después
    
    # 1. Insert top SKUs diariamente
    for sku in TOP_SKUS:
        target = sku["valor_total"]
        daily_base = round(target / days, 2)
        running = 0.0
        for d in range(1, days + 1):
            val = round(target - running, 2) if d == days else daily_base
            row = (f"{date_prefix}-{d:02d}", sku["cod_producto"], sku["nom_producto"],
                   BODEGA_CODE, BODEGA_NAME, 1.0, val, 0)  # 0 facturas por ahora
            con.execute("INSERT INTO mart_ventas_diarias_sku VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row)
            rows_for_facturas.append(row)
            running += val
        total_inserted += running
    
    # 2. Otros productos para alcanzar target_total exacto
    remaining = round(target_total - total_inserted, 2)
    num_other = 120
    remaining_cents = round(remaining * 100)
    base_cents = remaining_cents // num_other
    extra_cents = remaining_cents - base_cents * num_other
    
    for i in range(num_other):
        prod_code = f"OTH{i:04d}"
        prod_name = f"PRODUCTO GENERICO {i}"
        prod_total = (base_cents + (1 if i < extra_cents else 0)) / 100.0
        
        daily_base = round(prod_total / days, 2)
        running = 0.0
        for d in range(1, days + 1):
            val = round(prod_total - running, 2) if d == days else daily_base
            row = (f"{date_prefix}-{d:02d}", prod_code, prod_name,
                   BODEGA_CODE, BODEGA_NAME, 0.5, val, 0)
            con.execute("INSERT INTO mart_ventas_diarias_sku VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row)
            rows_for_facturas.append(row)
            running += val
        total_inserted += running
    
    # 3. Distribuir target_facturas entre todas las filas (ponderado por valor_total)
    if target_facturas > 0 and rows_for_facturas:
        # Ordenar por valor descendente para dar más facturas a los SKUs de mayor valor
        import random
        rng = random.Random(42)
        # Tomar tantas filas como target_facturas (las de mayor valor tienen más chance)
        total_rows = len(rows_for_facturas)
        # Seleccionar target_facturas filas para asignarles num_facturas=1
        indices = list(range(total_rows))
        # Darles prioridad a las primeras (top SKUs)
        # Las primeras 310 filas son top SKUs, el resto son genéricas
        top_count = days * len(TOP_SKUS)
        # Asignar facturas a las filas de mayor valor (más representativo)
        weighted = sorted(indices, key=lambda i: rows_for_facturas[i][6], reverse=True)
        chosen = set(weighted[:target_facturas])
        # Actualizar num_facturas a 1 para las seleccionadas
        for idx in chosen:
            d_str, cod, nom, bod_c, bod_n, qty, val, _ = rows_for_facturas[idx]
            con.execute("""
                UPDATE mart_ventas_diarias_sku
                SET num_facturas = 1
                WHERE business_date = ? AND cod_producto = ?
            """, [d_str, cod])
    
    return total_inserted


def build_duckdb(duckdb_path: str | Path) -> str:
    """Construye DuckDB con datos exactamente replicando el snapshot."""
    con = duckdb.connect(str(duckdb_path))

    # Siempre recrear desde cero (evita acumulación entre corridas)
    con.execute("DROP TABLE IF EXISTS mart_ventas_diarias_sku")
    con.execute("""
        CREATE TABLE mart_ventas_diarias_sku (
            business_date DATE,
            cod_producto VARCHAR,
            nom_producto VARCHAR,
            cod_bodega VARCHAR,
            nom_bodega VARCHAR,
            cantidad_total DECIMAL(18,2),
            valor_total DECIMAL(18,2),
            num_facturas INTEGER
        )
    """)

    # Insert each month with exact facturas for ticket_promedio match
    # Mayo: snapshot dice 911 facturas para ticket_promedio=25813.95
    total_may = _insert_exact_month(con, 2026, 5, TOTAL_CURRENT, target_facturas=911)
    # Abril: estimado basado en TOTAL_PREV / ticket_promedio
    total_apr = _insert_exact_month(con, 2026, 4, TOTAL_PREV, target_facturas=1050)

    print(f"Mayo:  insertado=${total_may:,.2f}, esperado=${TOTAL_CURRENT:,.2f}, diff=${abs(total_may - TOTAL_CURRENT):.2f}")
    print(f"Abril: insertado=${total_apr:,.2f}, esperado=${TOTAL_PREV:,.2f}, diff=${abs(total_apr - TOTAL_PREV):.2f}")

    # ── Validación final via SQL (como lo haría la API) ──────────────
    row_count = con.execute("SELECT COUNT(*) FROM mart_ventas_diarias_sku").fetchone()[0]

    monthly = con.execute("""
        SELECT
            STRFTIME(business_date, '%Y-%m') AS business_month,
            ROUND(SUM(valor_total), 2) AS ventas_mes,
            SUM(num_facturas) AS num_facturas
        FROM mart_ventas_diarias_sku
        GROUP BY business_month
        ORDER BY business_month DESC
        LIMIT 2
    """).fetchall()

    print(f"\nFilas totales: {row_count}")
    ok = True
    for m in monthly:
        print(f"  {m[0]}: ${m[1]:,.2f} ({m[2]} facturas)")

    expected = [(MONTH_CURRENT, TOTAL_CURRENT), (MONTH_PREV, TOTAL_PREV)]
    for i, m in enumerate(monthly):
        exp_month, exp_total = expected[i]
        diff = abs(float(m[1]) - exp_total)
        if diff > 0.01:
            print(f"  ❌ DIFF {exp_month}: esperado=${exp_total:,.2f}, obtenido=${m[1]:,.2f} (diff=${diff:.2f})")
            ok = False
        else:
            print(f"  ✅ {exp_month}: 0-diff")

    # Validar top 10 SKUs
    top10 = con.execute("""
        SELECT cod_producto, nom_producto,
               ROUND(SUM(valor_total), 2) AS valor_total,
               ROUND(SUM(cantidad_total), 2) AS cantidad_total
        FROM mart_ventas_diarias_sku
        WHERE business_date >= DATE '2026-05-01'
        GROUP BY cod_producto, nom_producto
        ORDER BY valor_total DESC
        LIMIT 10
    """).fetchall()

    print("\nTop 10 SKUs (mayo):")
    for t in top10:
        expected_sku = next((s for s in TOP_SKUS if s["cod_producto"] == t[0]), None)
        if expected_sku:
            diff_val = abs(float(t[2]) - expected_sku["valor_total"])
            status = "✅" if diff_val < 0.01 else "❌"
            print(f"  {status} {t[0]}: ${t[2]:,.2f} (esperado ${expected_sku['valor_total']:,.2f}, diff=${diff_val:.2f})")
        else:
            print(f"  ⚠️  {t[0]}: ${t[2]:,.2f} (OTRO — no esperado)")

    con.close()
    
    if ok:
        print(f"\n✅✅✅ DuckDB listo: {duckdb_path}")
    else:
        print(f"\n❌❌❌ DuckDB CON DIFFS: {duckdb_path}")
    
    return str(duckdb_path)


if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_duckdb(OUTPUT_PATH)
