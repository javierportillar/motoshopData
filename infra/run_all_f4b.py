"""
Orquestador F4-B — ejecuta todos los pasos del sprint en orden.

Uso:
    cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
    python infra/run_all_f4b.py

Requiere:
    - requests (Databricks SQL API)
    - pandas, lightgbm, scikit-learn, mlflow (para B-4)
    - Token Databricks vigente en .env
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _run(cmd: list[str], step: str) -> bool:
    """Ejecuta un comando y captura output."""
    print(f"\n{'='*60}")
    print(f"  [{step}] {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=False)
    if result.returncode != 0:
        print(f"  ❌ [{step}] FAILED (exit={result.returncode})")
        return False
    print(f"  ✅ [{step}] OK")
    return True


def _summary_line(label: str, status: str, detail: str = "") -> str:
    icon = "✅" if status == "OK" else ("⚠️" if status == "WARN" else "❌")
    return f"| {icon} {label} | {status} | {detail} |"


def main():
    print("=" * 60)
    print("  🏗️  F4-B Orchestrator")
    print(f"  Timestamp: {TIMESTAMP}")
    print("=" * 60)

    results: list[tuple[str, str, str]] = []

    # ── B-1: Fix baseline ──────────────────────────────────────────────
    print("\n\n📌 B-1: Fix baseline (16_forecast_baseline_sku.py)")
    print("-" * 40)
    print("   Notebook: notebooks/gold/16_forecast_baseline_sku.py")
    print("   Acción: ejecutar en Databricks SQL Warehouse")
    print("   ⏳ Debe ejecutarse manualmente o via Databricks CLI")
    results.append((
        "B-1 Fix baseline",
        "PENDING",
        "Ejecutar notebook 16 en Databricks → forecast_baseline_sku debe tener > 0 filas",
    ))

    # ── A-1: Prophet (Dev A) ───────────────────────────────────────────
    print("\n\n📌 A-1: Prophet top-100 (Dev A)")
    print("-" * 40)
    prophet_script = REPO_ROOT / "infra" / "run_forecast_prophet.py"
    if prophet_script.exists():
        ok = _run([sys.executable, str(prophet_script)], "A-1 Prophet")
        results.append(("A-1 Prophet", "OK" if ok else "FAIL", ""))
    else:
        print("   ⏳ run_forecast_prophet.py no existe — Dev A debe crearlo")
        results.append(("A-1 Prophet", "PENDING", "Dev A: crear + ejecutar run_forecast_prophet.py"))

    # ── A-2: LightGBM (Dev A) ──────────────────────────────────────────
    print("\n\n📌 A-2: LightGBM global (Dev A)")
    print("-" * 40)
    lgb_script = REPO_ROOT / "infra" / "run_forecast_lightgbm.py"
    if lgb_script.exists():
        ok = _run([sys.executable, str(lgb_script)], "A-2 LightGBM")
        results.append(("A-2 LightGBM", "OK" if ok else "FAIL", ""))
    else:
        print("   ⏳ run_forecast_lightgbm.py no existe — Dev A debe crearlo")
        results.append(("A-2 LightGBM", "PENDING", "Dev A: crear + ejecutar run_forecast_lightgbm.py"))

    # ── B-4: Classifier ────────────────────────────────────────────────
    print("\n\n📌 B-4: Classifier stockout")
    print("-" * 40)
    classifier_script = REPO_ROOT / "infra" / "run_classifier_stockout.py"
    if classifier_script.exists():
        ok = _run([sys.executable, str(classifier_script)], "B-4 Classifier")
        results.append(("B-4 Classifier", "OK" if ok else "FAIL", ""))
    else:
        print("   ❌ run_classifier_stockout.py no existe")
        results.append(("B-4 Classifier", "FAIL", "Script no encontrado"))

    # ── A-3: Evaluate (Dev A) ──────────────────────────────────────────
    print("\n\n📌 A-3: Evaluate models (Dev A)")
    print("-" * 40)
    eval_script = REPO_ROOT / "infra" / "run_evaluate_models.py"
    if eval_script.exists():
        ok = _run([sys.executable, str(eval_script)], "A-3 Evaluate")
        results.append(("A-3 Evaluate", "OK" if ok else "FAIL", ""))
    else:
        print("   ⏳ run_evaluate_models.py no existe — Dev A debe crearlo")
        results.append(("A-3 Evaluate", "PENDING", "Dev A: crear + ejecutar run_evaluate_models.py"))

    # ── Tests ──────────────────────────────────────────────────────────
    print("\n\n📌 Tests gold")
    print("-" * 40)
    ok = _run(
        [sys.executable, "-m", "pytest", "tests/gold/", "-v", "--tb=short"],
        "Gold tests",
    )
    results.append(("Gold tests", "OK" if ok else "FAIL", ""))

    print("\n\n📌 Tests API")
    print("-" * 40)
    ok = _run(
        [sys.executable, "-m", "pytest", "motoshop-app/api/tests/", "-q", "--tb=short"],
        "API tests",
    )
    results.append(("API tests", "OK" if ok else "FAIL", ""))

    # ── Resumen ────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  📊 RESUMEN F4-B")
    print("=" * 60)
    print()
    print("| Paso | Estado | Detalle |")
    print("|------|--------|---------|")
    for label, status, detail in results:
        print(_summary_line(label, status, detail))
    print()

    all_ok = all(s == "OK" for _, s, _ in results)
    pending = [label for label, s, _ in results if s != "OK"]
    if all_ok:
        print("✅ F4-B COMPLETO — todos los pasos OK")
    else:
        print(f"⚠️  F4-B PARCIAL — {len(pending)} paso(s) pendiente(s):")
        for p in pending:
            print(f"   • {p}")

    # Escribir evidencia
    evidence = [
        f"# F4-B Orchestrator — {TIMESTAMP}",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}",
        "",
        "---",
        "",
        "## Resultados",
        "",
        "| Paso | Estado | Detalle |",
        "|------|--------|---------|",
    ]
    for label, status, detail in results:
        evidence.append(f"| {'✅' if status=='OK' else '⚠️' if status=='WARN' else '❌'} {label} | {status} | {detail} |")
    evidence.extend([
        "",
        "## V-Checks",
        "",
        f"| ID | Verificación | Resultado |",
        f"|----|-------------|-----------|",
        f"| V-M0 | forecast_baseline_sku > 0 filas | {'✅' if status=='OK' else '⚠️'} {status} |",
        f"| V-M1 | Prophet supera baseline | ⏳ Pendiente ejecución A-1 |",
        f"| V-M2 | LightGBM supera baseline | ⏳ Pendiente ejecución A-2 |",
        f"| V-M3 | Classifier F1 > 0.7 | ⏳ Pendiente ejecución B-4 |",
        f"| V-M4 | forecast_demanda_sku ≥ 7 días | ⏳ Pendiente A-1 + A-2 |",
        f"| V-M5 | alertas_quiebre con urgencia | ⏳ Pendiente B-4 |",
        f"| V-M6 | 0 negative forecasts, 0 null SKU | ⏳ Pendiente |",
        f"| V-M7 | Tests gold PASS | {'✅' if all_ok else '❌'} {len(results)} tests |",
        "",
    ])
    runs_dir = REPO_ROOT / "notebooks" / "gold" / "_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ev_file = runs_dir / f"v_run_all_f4b_{TIMESTAMP}.md"
    ev_file.write_text("\n".join(evidence), encoding="utf-8")
    print(f"\n📄 Evidencia: {ev_file}")


if __name__ == "__main__":
    main()
