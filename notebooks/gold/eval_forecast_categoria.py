"""
eval_forecast_categoria.py — Evaluación del forecasting por categoría.

Propósito:
  1. Leer gold.forecast_categoria desde Databricks SQL Warehouse.
  2. Calcular WAPE del baseline-categoría.
  3. Entrenar Prophet por categoría sobre el agregado.
  4. Calcular WAPE de Prophet-categoría.
  5. Comparar ambos vs Baseline-SKU (45.83% de F4-FIX1).
  6. Generar reporte markdown en _runs/.

Uso:
  python3 notebooks/gold/eval_forecast_categoria.py

Requiere:
  - databricks-sql-connector instalado
  - .env con DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
  - Tabla gold.forecast_categoria poblada (ejecutar 24_forecast_categoria.py primero)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from databricks import sql as db_sql


# ── Config ──────────────────────────────────────────────────────────────────

RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = Path("notebooks/gold/_runs")
BASELINE_SKU_WAPE = 45.83  # Referencia de F4-FIX1


# ── Helpers ──────────────────────────────────────────────────────────────────


def query(sql: str) -> pd.DataFrame:
    """Ejecuta SQL en Databricks SQL Warehouse y devuelve DataFrame."""
    conn = db_sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall_arrow().to_pandas()
    finally:
        conn.close()


def wape(actual: pd.Series, pred: pd.Series) -> float:
    """Weighted Absolute Percentage Error: Σ|actual-pred| / Σactual * 100."""
    denom = actual.sum()
    if denom == 0:
        return float("nan")
    return abs(actual - pred).sum() / denom * 100


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> dict:
    """Ejecuta evaluación completa y devuelve métricas."""
    results: dict = {}

    # 1. Cobertura de categorías
    cov = query("""
        SELECT
            COUNT(DISTINCT cod_grupo) AS categorias_totales,
            COUNT(DISTINCT CASE
                WHEN dias_historia >= 90 THEN cod_grupo
            END) AS categorias_elegibles
        FROM (
            SELECT
                cod_grupo,
                COUNT(DISTINCT business_date) AS dias_historia
            FROM motoshop.gold.forecast_categoria
            GROUP BY cod_grupo
        )
    """)
    results["categorias_totales"] = int(cov["categorias_totales"].iloc[0])
    results["categorias_elegibles"] = int(cov["categorias_elegibles"].iloc[0])
    results["pct_elegible"] = round(
        results["categorias_elegibles"] / results["categorias_totales"] * 100, 2
    )

    # 2. Baseline WAPE (global)
    df_all = query("""
        SELECT cod_grupo, business_date, demanda_real, demanda_predicha_baseline
        FROM motoshop.gold.forecast_categoria
        WHERE demanda_predicha_baseline IS NOT NULL
        ORDER BY cod_grupo, business_date
    """)
    results["wape_baseline_categoria"] = round(
        wape(df_all["demanda_real"], df_all["demanda_predicha_baseline"]), 2
    )

    # 3. Baseline WAPE por categoría
    wape_por_categoria = (
        df_all.groupby("cod_grupo")
        .apply(
            lambda g: round(
                wape(g["demanda_real"], g["demanda_predicha_baseline"]), 2
            ),
            include_groups=False,
        )
        .reset_index(name="wape_baseline_pct")
        .sort_values("wape_baseline_pct", ascending=False)
    )
    results["wape_por_categoria"] = wape_por_categoria.to_dict("records")

    # 4. Baseline WAPE por mes
    df_all["business_month"] = df_all["business_date"].dt.to_period("M").astype(str)
    wape_por_mes = (
        df_all.groupby("business_month")
        .apply(
            lambda g: round(
                wape(g["demanda_real"], g["demanda_predicha_baseline"]), 2
            ),
            include_groups=False,
        )
        .reset_index(name="wape_baseline_pct")
        .sort_values("business_month")
    )
    results["wape_por_mes"] = wape_por_mes.to_dict("records")

    # 5. Prophet por categoría (top-20 por volumen)
    volumen_categoria = (
        df_all.groupby("cod_grupo")["demanda_real"]
        .sum()
        .sort_values(ascending=False)
    )
    top_categorias = volumen_categoria.head(20).index.tolist()

    prophet_results = []
    for cod_grupo in top_categorias:
        serie = df_all[df_all["cod_grupo"] == cod_grupo][
            ["business_date", "demanda_real"]
        ].copy()
        serie = serie.sort_values("business_date")
        serie.columns = ["ds", "y"]

        if len(serie) < 30:
            continue  # Muy pocos datos para Prophet

        # Train/test split temporal (80/20)
        cutoff = int(len(serie) * 0.8)
        train = serie.iloc[:cutoff]
        test = serie.iloc[cutoff:]

        try:
            from prophet import Prophet

            model = Prophet(
                yearly_seasonality=False,
                weekly_seasonality=True,
                daily_seasonality=False,
                seasonality_mode="multiplicative",
            )
            model.fit(train)

            future = test[["ds"]].copy()
            forecast = model.predict(future)

            # Merge predicciones
            merged = test.merge(
                forecast[["ds", "yhat"]], on="ds", how="left"
            )
            wape_val = round(
                wape(merged["y"], merged["yhat"].clip(lower=0)), 2
            )
        except Exception as exc:
            wape_val = None
            print(f"  ⚠ Prophet falló para {cod_grupo}: {exc}")

        prophet_results.append(
            {
                "cod_grupo": cod_grupo,
                "dias_train": len(train),
                "dias_test": len(test),
                "wape_prophet_pct": wape_val,
                "wape_baseline_pct": round(
                    wape(
                        test["y"],
                        df_all[
                            (df_all["cod_grupo"] == cod_grupo)
                            & (df_all["business_date"].isin(test["ds"]))
                        ]["demanda_predicha_baseline"],
                    ),
                    2,
                ),
            }
        )
        print(f"  ✓ Prophet {cod_grupo}: WAPE={wape_val}%")

    results["prophet_por_categoria"] = prophet_results

    # Prophet WAPE global (promedio de WAPEs por categoría)
    wapes_prophet = [
        r["wape_prophet_pct"]
        for r in prophet_results
        if r["wape_prophet_pct"] is not None
    ]
    wapes_baseline_cat = [
        r["wape_baseline_pct"] for r in prophet_results
    ]
    results["wape_prophet_categoria_avg"] = (
        round(sum(wapes_prophet) / len(wapes_prophet), 2) if wapes_prophet else None
    )
    results["wape_baseline_categoria_top20_avg"] = (
        round(sum(wapes_baseline_cat) / len(wapes_baseline_cat), 2)
        if wapes_baseline_cat
        else None
    )

    return results


# ── Reporte ──────────────────────────────────────────────────────────────────


def generate_report(results: dict) -> str:
    """Genera el reporte markdown."""
    lines = [
        f"# Evaluación Forecasting por Categoría — {RUN_TS}",
        "",
        f"**Fecha:** {datetime.now().isoformat()}",
        "**Sprint:** F6-B · Dev B",
        "",
        "---",
        "",
        "## Cobertura",
        "",
        f"| Métrica | Baseline-SKU (F4-FIX1) | Baseline-Categoría |",
        f"|---------|------------------------|---------------------|",
        f"| Categorías totales | — | {results['categorias_totales']} |",
        f"| Categorías elegibles (≥90d) | — | {results['categorias_elegibles']} |",
        f"| % elegible | 0.7% (31/4392 SKUs) | {results['pct_elegible']}% |",
        "",
        "---",
        "",
        "## WAPE Global",
        "",
        f"| Modelo | WAPE | vs Baseline-SKU (45.83%) |",
        f"|--------|------|--------------------------|",
        f"| Baseline-SKU | **45.83%** | — (referencia) |",
        f"| Baseline-Categoría | **{results['wape_baseline_categoria']}%** | "
        f"{'✓ SUPERA' if results['wape_baseline_categoria'] < BASELINE_SKU_WAPE else '✗ NO SUPERA'} |",
    ]

    if results.get("wape_prophet_categoria_avg") is not None:
        prophet_status = (
            "✓ SUPERA"
            if results["wape_prophet_categoria_avg"] < results["wape_baseline_categoria"]
            else "✗ NO SUPERA"
        )
        lines += [
            f"| Prophet-Categoría (top-20) | **{results['wape_prophet_categoria_avg']}%** | "
            f"{prophet_status} baseline-categoría |",
        ]

    lines += [
        "",
        "---",
        "",
        "## WAPE por Categoría (baseline)",
        "",
        "| Categoría | Días | Ventas totales | WAPE % |",
        "|-----------|------|----------------|--------|",
    ]
    for r in results["wape_por_categoria"][:30]:
        lines.append(
            f"| {r['cod_grupo']} | — | — | {r['wape_baseline_pct']}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## Prophet por Categoría (top-20 por volumen)",
        "",
        "| Categoría | Días train | Días test | WAPE Prophet % | WAPE Baseline % | Prophet supera? |",
        "|-----------|-----------|----------|----------------|-----------------|-----------------|",
    ]
    for r in results.get("prophet_por_categoria", []):
        wape_p = f"{r['wape_prophet_pct']}%" if r["wape_prophet_pct"] is not None else "N/A"
        supera = (
            "✓"
            if r["wape_prophet_pct"] is not None
            and r["wape_prophet_pct"] < r["wape_baseline_pct"]
            else "✗" if r["wape_prophet_pct"] is not None else "—"
        )
        lines.append(
            f"| {r['cod_grupo']} | {r['dias_train']} | {r['dias_test']} | "
            f"{wape_p} | {r['wape_baseline_pct']}% | {supera} |"
        )

    # Hipótesis
    lines += [
        "",
        "---",
        "",
        "## Verificación de Hipótesis",
        "",
    ]

    hipotesis_valida = results["wape_baseline_categoria"] < BASELINE_SKU_WAPE
    if hipotesis_valida:
        lines += [
            "**✅ Hipótesis VALIDADA:** El forecasting agregado por categoría "
            f"(WAPE {results['wape_baseline_categoria']}%) supera al baseline "
            f"por SKU individual (45.83%).",
            "",
            "**Implicación:** Producir forecasts a nivel categoría y reconciliar "
            "a SKU como paso post-proceso (F7+).",
        ]
    else:
        lines += [
            "**❌ Hipótesis NO validada:** El forecasting agregado por categoría "
            f"(WAPE {results['wape_baseline_categoria']}%) NO supera al baseline "
            f"por SKU individual (45.83%).",
            "",
            "**Implicación:** Incluso agregando, la demanda de repuestos de moto "
            "es demasiado irregular o el histórico (17 meses) es insuficiente. "
            "La solución puede requerir más datos históricos o features externos.",
        ]

    if results.get("wape_prophet_categoria_avg") is not None:
        prophet_valida = (
            results["wape_prophet_categoria_avg"]
            < results["wape_baseline_categoria"]
        )
        if prophet_valida:
            lines += [
                "",
                "**✅ Prophet categoría supera baseline categoría:** "
                f"Prophet gana en el agregado (WAPE {results['wape_prophet_categoria_avg']}% "
                f"vs {results['wape_baseline_categoria']}%). "
                "La estacionalidad semanal es detectable a nivel categoría.",
            ]
        else:
            lines += [
                "",
                "**❌ Prophet categoría NO supera baseline categoría:** "
                f"Prophet WAPE {results['wape_prophet_categoria_avg']}% "
                f"vs baseline {results['wape_baseline_categoria']}%. "
                "La estacionalidad no es lo suficientemente fuerte incluso a nivel agregado.",
            ]

    lines += [
        "",
        "---",
        "",
        "## Decisión",
        "",
        "| Criterio | Estado |",
        "|----------|--------|",
    ]

    if hipotesis_valida:
        lines += [
            "| ADR-0020 | Proposed → **Accepted** |",
            "| Forecast de producción | Cambiar a nivel categoría |",
            "| Prophet | Usar solo si supera baseline-categoría |",
        ]
    else:
        lines += [
            "| ADR-0020 | **Proposed** (no se valida — documentar hallazgo) |",
            "| Forecast de producción | Mantener baseline-SKU |",
            "| Próximo paso | Investigar features externos o más histórico |",
        ]

    lines += [
        "",
        "---",
        "",
        f"*Generado por eval_forecast_categoria.py · {RUN_TS}*",
    ]

    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=" * 60)
    print("Evaluación de Forecasting por Categoría")
    print("=" * 60)
    print()

    # Validar credenciales
    for var in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"):
        if var not in os.environ:
            print(f"❌ Falta variable de entorno: {var}")
            print("   Creala en .env o exportala antes de ejecutar.")
            sys.exit(1)

    print("Conectando a Databricks SQL Warehouse...")
    results = main()

    print()
    print("Resultados:")
    print(f"  Categorías totales: {results['categorias_totales']}")
    print(f"  Categorías elegibles: {results['categorias_elegibles']}")
    print(f"  WAPE Baseline-Categoría: {results['wape_baseline_categoria']}%")
    print(f"  WAPE Baseline-SKU (ref): {BASELINE_SKU_WAPE}%")
    print(
        f"  → {'✓ SUPERA' if results['wape_baseline_categoria'] < BASELINE_SKU_WAPE else '✗ NO SUPERA'}"
    )

    if results.get("wape_prophet_categoria_avg") is not None:
        print(f"  WAPE Prophet-Categoría (promedio): {results['wape_prophet_categoria_avg']}%")
        print(
            f"  → {'✓ SUPERA' if results['wape_prophet_categoria_avg'] < results['wape_baseline_categoria'] else '✗ NO SUPERA'} baseline-categoría"
        )

    # Generar reporte
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"v_forecast_categoria_eval_{RUN_TS}.md"
    report = generate_report(results)
    report_path.write_text(report)
    print(f"\n✅ Reporte generado: {report_path}")
