# E1 · Diagnóstico organizacional + Arquitectura técnica

> **Curso:** Big Data y Transformación Digital del Negocio · UAO 2025-2  
> **Módulos cubiertos:** 2 (criterios técnicos y stack), 4 (madurez, VPC, BMC)  
> **Estado:** ✅ Listo  
> **Última actualización:** 2026-05-30

---

## 1 · Contexto del caso

**MotoShop** es una tienda colombiana de repuestos de moto que opera con el ERP **sgHermes** sobre una base MySQL 5.0 (`motoshop2024`) en un PC Windows local. Volumen actual: 6,340 facturas, 27,775 líneas de detalle, 6,185 SKUs en catálogo, 26,174 movimientos de inventario, 161 clientes en ~22 meses de histórico (2024-01 → 2026-05).

**Problema:**
- Los datos quedan atrapados en sgHermes y solo se consultan desde el PC del negocio.
- No hay analítica más allá de los reportes operativos del ERP.
- La decisión de qué reabastecer y cuándo se hace por intuición.

**Visión:** llevar a MotoShop de un negocio que **registra datos** a uno que **decide con datos y opera desde cualquier lugar**, sin reemplazar sgHermes.

---

## 2 · Diagnóstico de madurez digital (Módulo 4)

Aplicando el marco del curso:

| Dimensión | Estado inicial | Arquetipo |
|-----------|----------------|-----------|
| Cultura de datos | Decisiones por intuición | Principiante |
| Tecnología | ERP local sin lakehouse | Principiante |
| Procesos | Sin pipeline | Principiante |
| Talento | 1 persona técnica | Principiante |
| Gobierno | Sin políticas de datos | Principiante |

**Diagnóstico:** arquetipo **Principiante** → objetivo **Practicante** en 12 meses.

**Hoja de ruta:** 7 fases (F0 → F6) descritas en [`PLAN.md`](../../PLAN.md).

---

## 3 · Value Proposition Canvas (VPC)

### Customer Profile

- **Jobs:** entender qué se vende, predecir quiebres, consultar inventario desde fuera del negocio.
- **Pains:** datos atrapados, no hay forecasting, decisiones a ciegas.
- **Gains:** decisiones rápidas, visibilidad remota, alertas proactivas.

### Value Map

- **Products:** Lakehouse Databricks + API FastAPI + PWA Next.js + ML forecasting.
- **Pain relievers:** acceso remoto vía túnel Cloudflare, alertas push.
- **Gain creators:** dashboards descriptivos + predictivos.

Detalle completo en [`PLAN.md`](../../PLAN.md) §13.

---

## 4 · Business Model Canvas (BMC)

9 bloques documentados en [`PLAN.md`](../../PLAN.md) §14. Highlights:

- **Key resources:** sgHermes operacional + Databricks Free Edition + PC Windows con Task Scheduler.
- **Channels:** PWA instalable (https://api.fragloesja.uk + frontend Vercel).
- **Cost structure:** $0/mes (Databricks Free + Cloudflare gratis + hosting local).

---

## 5 · Arquitectura técnica (Módulo 2)

### Diagrama lógico

```
sgHermes (MySQL 5.0, PC Windows local)
         │
         ▼ Task Scheduler cada 30 min (07:00-19:30 COL)
mysqldump → Parquet local → UC Volume (Databricks)
         │
         ▼ CREATE OR REPLACE TABLE FROM parquet
Bronze (Delta Lake, partición por ingest_date)
         │
         ▼ business_date derivada (ADR-0013)
Silver (5 dims SCD1 + 5 facts particionados por business_date)
         │
         ▼ Workflow nocturno cron 02:30 COL (idempotente)
Gold (5 marts: ventas, inventario, ABC, cohortes, dormidos)
         │                              │
         ▼                              ▼
Databricks SQL Dashboard         FastAPI /metrics/*
                                         │
                                         ▼
                          PWA Next.js (Vercel) ←→ Cloudflare Tunnel
                                         │
                                         ▼
                                Usuario móvil/desktop
```

### Stack final

| Capa | Tecnología | ADR |
|------|------------|-----|
| Storage analítico | Delta Lake (Databricks Free Edition) | [0001](../decisions/0001-medallion-architecture.md), [0010](../decisions/0010-compute-databricks-free.md) |
| Compute analítico | SQL Warehouse Serverless (auto-stop 10 min) | [0010](../decisions/0010-compute-databricks-free.md) |
| Ingesta | mysqldump + Task Scheduler + Python parquet writer | [0005](../decisions/0005-databricks-mysql-connectivity.md) |
| API | FastAPI + SQLAlchemy 2.0 core + pymysql + JWT/bcrypt | [0007](../decisions/0007-api-hosting.md), [0008](../decisions/0008-auth-provider.md), [0011](../decisions/0011-stack-f1.md) |
| Frontend | Next.js 14 App Router + TypeScript + Tailwind + SWR + Zustand | [0003](../decisions/0003-pwa-nextjs.md), [0014](../decisions/0014-stack-f2.md) |
| PWA | next-pwa + Workbox + idb-keyval + recharts | [0014](../decisions/0014-stack-f2.md), [0015](../decisions/0015-stack-f3.md) |
| Túnel remoto | Cloudflare Tunnel → https://api.fragloesja.uk | [0006](../decisions/0006-remote-tunnel.md) |
| ML tracking | MLflow managed (Databricks) + Prophet + LightGBM + sklearn | [0016](../decisions/0016-stack-f4.md) |

### Cómo cumple criterios del Módulo 2

| Criterio | Cómo lo cumple |
|----------|----------------|
| Escalabilidad | Lakehouse + storage elástico cloud |
| Flexibilidad | Medallion separa ingesta/almacén/proc/consumo |
| Baja latencia | Hoy batch (cada 30 min); streaming diferido a F-E |
| Tolerancia a fallos | Delta Lake ACID + time-travel + backup MySQL + catch-up flag |
| Optimización costo | Auto-stop 10 min + Free Edition ($0/mes) |
| Seguridad/gobernanza | Unity Catalog + users read-only + PII redaction structlog + Cloudflare |
| Integración/orquestación | Task Scheduler hoy; Databricks Workflow diferido (R4) |
| Calidad de datos | `_quality_runs` con reglas CRITICAL incluida `silver_completeness` |
| Elasticidad | Compute serverless por demanda |

---

## 6 · Decisiones críticas (ADRs)

16 decisiones técnicas aceptadas. Las críticas para entender el diseño:

| # | Decisión | Por qué importa para defensa |
|---|----------|------------------------------|
| [0001](../decisions/0001-medallion-architecture.md) | Bronze → Silver → Gold | Robustez del lakehouse (time-travel, reproceso, auditoría) |
| [0010](../decisions/0010-compute-databricks-free.md) | Compute Free Edition | Demuestra resolución del constraint costo $0 |
| [0013](../decisions/0013-fecha-tecnica-vs-negocio.md) | `business_date` derivada en silver | Decisión arquitectónica sutil con impacto en analítica |
| [0014](../decisions/0014-stack-f2.md) | Stack F2 con 16 DT | Tradeoffs MERGE vs INSERT REPLACE, SCD1 vs SCD2 |
| [0015](../decisions/0015-stack-f3.md) | Databricks SQL para BI | Resuelve constraint Mac-friendly (Power BI requiere Windows) |
| [0016](../decisions/0016-stack-f4.md) | MLflow + Prophet + LightGBM | Stack ML coherente con Free Edition |

---

## 7 · Entrega académica E1 — Checklist

- [x] Diagnóstico de madurez con marco del curso
- [x] VPC + BMC documentados ([`PLAN.md`](../../PLAN.md) §13-14)
- [x] Arquitectura técnica con diagrama
- [x] Stack final justificado con ADRs
- [x] Criterios del Módulo 2 cubiertos con evidencia
- [x] Hoja de ruta 7 fases ([`PLAN.md`](../../PLAN.md) §7)

---

## 8 · Evidencia versionada

- Plan maestro: [`PLAN.md`](../../PLAN.md)
- Snapshot ejecutivo: [`docs/contexto-proyecto.md`](../contexto-proyecto.md)
- ADRs: [`docs/decisions/`](../decisions/)
- Setup infra: [`infra/`](../../infra/)

---

## 9 · Limitaciones conscientes

- **Dataset histórico limitado:** ~22 meses (2024-07 → 2026-05) y 6,185 SKUs con cola larga (la mayoría con < 30 ventas) — afecta forecasting (ver E4).
- **Compute Free Edition:** sin clusters, solo SQL Warehouse serverless. Limita train de modelos pesados a procesos batch nocturnos.
- **PC Windows local:** punto único de falla en la ingesta (R10 mitigada con F1.9 pero no eliminada).
