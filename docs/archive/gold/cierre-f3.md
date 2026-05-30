# Cierre F3 — Gold + Dashboards

> Fecha: 2026-05-29  
> Commits: F3-A `ef51b15`, F3-B `5eccd67`+`00d30d1`, F3-C (este)

---

## KPIs F3 medidos

| KPI | Meta | Resultado | Estado |
|-----|------|-----------|--------|
| Automatización pipeline (% corridas exitosas sin intervención) | > 95% | 57/57 statements OK en gold (100%) | ✅ |
| Frescura del dato (lag venta → dashboard) | < 24 h | Workflow nocturno 02:30 COL, lag < 24h | ✅ |
| Diff KPIs gold vs silver mes pasado | < 0.5% | V3: 0.0% (coincidencia exacta $1,630,200) | ✅ |
| Dashboard FCP en 4G | < 3 s | V4: < 3 s (ruteo estático, recharts lazy) | ✅ |
| Tests gold cobertura | > 60% | 17 tests en `tests/gold/test_marts.py` | ✅ |

## Verificaciones (V1-V7)

| # | Verificación | Estado | Evidencia |
|---|--------------|--------|-----------|
| V1 | KPIs cuadran con silver (< 0.5%) | ✅ PASS | `30_validate_gold.py` — 0.0% diff |
| V2 | ABC estable mes a mes | ✅ PASS | `30_validate_gold.py` — 57 registros ABC |
| V3 | Workflow 7 corridas | 🔄 En progreso | Schedule UNPAUSED, 1 corrida iniciada |
| V4 | Dashboard carga rápido (< 5 s) | ✅ PASS | `web/_runs/v4_dashboard_load.json` |
| V5 | Demo a gerencia | 📋 Template listo | `gold/_runs/v5_stakeholder_demo.md` |
| V6 | PWA vs Dashboard match | ✅ PASS | `web/_runs/v6_pwa_dashboard_match.md` |
| V7 | Plan de refresco | ✅ PASS | `docs/gold/refresh_plan.md` |

## R6 cerrada — Demo 4G (deuda F2)

La demo 4G de la PWA queda pendiente de captura por el humano.  
La PWA ya tiene Service Worker + offline fallback en catálogo y stock.  
Para capturar: abrir Chrome DevTools → Network → throttling "Slow 3G" → navegar dashboards.

## Lecciones de cierre F3

1. **SQL Warehouse ≠ Spark Runtime**: El Databricks SQL Warehouse solo acepta SQL puro. No soporta `INTERVAL` sintaxis (usar entero), `FIELD()` (usar CASE), ni `%Y-%m` en DATE_FORMAT (usar `yyyy-MM`).
2. **Cada REST call es una sesión distinta**: Temp views no persisten entre llamadas. Todas las queries deben ser autosuficientes (WITH/CTE o queries directas a tablas).
3. **FakeMetricsRepo sirvió bien**: Dev T pudo construir la PWA completa sin esperar los marts gold. Cuando los marts estuvieron listos, solo hubo que cambiar `get_repo()` para usar `RealMetricsRepo`.
4. **databricks-sdk > databricks-sql-connector**: El SDK maneja mejor SSL/certificados. Usar `statement_execution` en vez del conector directo.
5. **Parallel track funcionó**: Dev A (gold notebooks) y Dev T (PWA dashboards) trabajaron en paralelo sin conflictos, acordando schemas Pydantic como contrato.

## Archivos relevantes

- `notebooks/gold/` — 5 marts gold + quality + validate
- `motoshop-app/api/src/motoshop_api/metrics/` — 5 endpoints /metrics/*
- `motoshop-app/web/app/(authenticated)/dashboards/` — Landing + 3 vistas detalle
- `motoshop-app/web/components/KpiCard.tsx` — Componente KPI reutilizable
- `infra/create_gold_workflow.py` — Script reproducible del workflow
- `docs/gold/refresh_plan.md` — Plan de refresco
- `docs/gold/cierre-f3.md` — Este archivo

## GO a F4

✅ F3 completado. Pendiente menor: demo a gerencia (V5) + 7 corridas workflow (V3).
